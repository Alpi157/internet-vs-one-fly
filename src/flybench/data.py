"""Pinned, streaming acquisition of the three M02 MaleCNS source files."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa


RELEASE = "MaleCNS v1.0"
OFFICIAL_PAGE = "https://male-cns.janelia.org/download/"
OFFICIAL_FILES = {
    "curated_annotations": (
        "body-annotations-male-cns-v1.0-minconf-0.5.feather",
        "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/"
        "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    ),
    "aggregate_neurotransmitters": (
        "body-neurotransmitters-male-cns-v1.0.feather",
        "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/"
        "body-neurotransmitters-male-cns-v1.0.feather",
    ),
    "connection_weights": (
        "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
        "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/"
        "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
    ),
}
CHUNK_BYTES = 8 * 1024 * 1024


class SourceFetchError(RuntimeError):
    """Source acquisition or validation failed safely."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def load_source_lock(path: Path, *, enforce_official: bool = True) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        lock = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SourceFetchError(f"invalid source lock JSON: {exc}") from exc
    if not isinstance(lock, dict) or lock.get("schema_version") != 1:
        raise SourceFetchError("source lock schema_version must be 1")
    dataset = lock.get("dataset")
    if not isinstance(dataset, dict) or dataset.get("release") != RELEASE:
        raise SourceFetchError(f"source lock release must be {RELEASE!r}")
    if dataset.get("official_page") != OFFICIAL_PAGE:
        raise SourceFetchError("source lock official page does not match the M02 authority")
    files = lock.get("files")
    if not isinstance(files, list) or len(files) != len(OFFICIAL_FILES):
        raise SourceFetchError("source lock must contain exactly the three M02 source files")

    seen: set[str] = set()
    for source in files:
        if not isinstance(source, dict):
            raise SourceFetchError("each source-lock file entry must be an object")
        role = source.get("role")
        filename = source.get("filename")
        url = source.get("official_url")
        if role not in OFFICIAL_FILES or role in seen:
            raise SourceFetchError(f"invalid or duplicate source role: {role!r}")
        seen.add(role)
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise SourceFetchError(f"unsafe source filename for role {role!r}")
        if not isinstance(url, str):
            raise SourceFetchError(f"missing source URL for role {role!r}")
        parsed = urllib.parse.urlparse(url)
        if Path(urllib.parse.unquote(parsed.path)).name != filename:
            raise SourceFetchError(f"URL filename does not match locked filename for role {role!r}")
        if enforce_official:
            expected_filename, expected_url = OFFICIAL_FILES[role]
            if filename != expected_filename or url != expected_url or parsed.scheme != "https":
                raise SourceFetchError(f"source identity for role {role!r} is not the official M02 source")
        elif parsed.scheme not in {"http", "https"}:
            raise SourceFetchError("test source URLs must use HTTP(S)")

        observed_size = source.get("observed_bytes")
        observed_hash = source.get("observed_sha256")
        if (observed_size is None) != (observed_hash is None):
            raise SourceFetchError(f"observed size and SHA-256 must resolve together for role {role!r}")
        if observed_size is not None and (not isinstance(observed_size, int) or observed_size <= 0):
            raise SourceFetchError(f"invalid observed byte size for role {role!r}")
        if observed_hash is not None and not _valid_sha256(observed_hash):
            raise SourceFetchError(f"invalid observed SHA-256 for role {role!r}")
        upstream_hash = source.get("upstream_sha256")
        if upstream_hash is not None and not _valid_sha256(upstream_hash):
            raise SourceFetchError(f"invalid upstream SHA-256 for role {role!r}")
        maximum = source.get("download_max_bytes")
        if not isinstance(maximum, int) or maximum <= 0:
            raise SourceFetchError(f"download_max_bytes must be a positive integer for role {role!r}")
        if observed_size is not None and observed_size > maximum:
            raise SourceFetchError(f"observed size exceeds the download safety bound for role {role!r}")
    if seen != set(OFFICIAL_FILES):
        raise SourceFetchError("source lock roles do not match the M02 source set")
    return lock, hashlib.sha256(raw).hexdigest()


def _normal(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def inspect_feather(path: Path, role: str) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            magic_start = stream.read(6)
            stream.seek(-6, os.SEEK_END)
            magic_end = stream.read(6)
        with pa.memory_map(str(path), "r") as source:
            reader = pa.ipc.open_file(source)
            schema = reader.schema
            batch_count = reader.num_record_batches
    except (OSError, pa.ArrowException) as exc:
        raise SourceFetchError(f"not a readable Arrow Feather V2 file: {exc}") from exc

    fields = [{"name": field.name, "type": str(field.type)} for field in schema]
    normalized = [_normal(field.name) for field in schema]
    has_body = any("body" in name or "segment" in name for name in normalized)
    if role == "curated_annotations":
        role_ok = has_body and any(
            marker in name for name in normalized for marker in ("type", "class", "side", "status")
        )
        expectation = "body/segment identifier plus annotation type/class/side/status field"
    elif role == "aggregate_neurotransmitters":
        role_ok = has_body and any("neurotrans" in name or name.endswith("nt") or "ntprob" in name for name in normalized)
        expectation = "body/segment identifier plus neurotransmitter prediction field"
    elif role == "connection_weights":
        pre = any(("pre" in name and ("body" in name or "segment" in name)) or name == "source" for name in normalized)
        post = any(("post" in name and ("body" in name or "segment" in name)) or name == "target" for name in normalized)
        weight = any("weight" in name or "count" in name for name in normalized)
        role_ok = pre and post and weight
        expectation = "pre/source endpoint, post/target endpoint, and weight/count field"
    else:
        raise SourceFetchError(f"unknown source role {role!r}")
    if not role_ok:
        raise SourceFetchError(
            f"Feather schema does not satisfy {role!r} expectation: {expectation}; "
            f"observed fields {[field['name'] for field in fields]!r}"
        )
    return {
        "format": "Apache Arrow Feather V2 / Arrow IPC file",
        "magic_start_hex": magic_start.hex(),
        "magic_end_hex": magic_end.hex(),
        "column_count": len(fields),
        "record_batch_count": batch_count,
        "fields": fields,
        "schema_metadata_keys": sorted(
            key.decode("utf-8", "replace") for key in (schema.metadata or {}).keys()
        ),
        "role_expectation": expectation,
        "role_validation": "PASS",
    }


def _quarantine(path: Path, observed_hash: str) -> Path:
    quarantine = path.with_name(f"{path.name}.corrupt-{utc_now().replace(':', '')}-{observed_hash[:12]}")
    os.replace(path, quarantine)
    return quarantine


def _download(source: dict[str, Any], partial: Path) -> tuple[int, str, dict[str, Any]]:
    request = urllib.request.Request(
        source["official_url"], headers={"User-Agent": "FlyBench-M02/0.1"}
    )
    digest = hashlib.sha256()
    size = 0
    response_info: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("xb") as output:
            status = response.getcode()
            if status is None or not 200 <= status < 300:
                raise SourceFetchError(f"HTTP status {status} for {source['official_url']}")
            content_length_text = response.headers.get("Content-Length")
            content_length = int(content_length_text) if content_length_text is not None else None
            response_info = {
                "http_status": status,
                "content_length": content_length,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
            while chunk := response.read(CHUNK_BYTES):
                size += len(chunk)
                if size > source["download_max_bytes"]:
                    raise SourceFetchError("download exceeded the locked safety byte bound")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if content_length is not None and size != content_length:
            raise SourceFetchError(
                f"truncated transfer: received {size} bytes but HTTP Content-Length was {content_length}"
            )
    except urllib.error.HTTPError as exc:
        raise SourceFetchError(f"HTTP status {exc.code} for {source['official_url']}") from exc
    except urllib.error.URLError as exc:
        raise SourceFetchError(f"transport error for {source['official_url']}: {exc.reason}") from exc
    return size, digest.hexdigest(), response_info


def fetch_sources(
    lock_path: Path,
    out_dir: Path,
    report_path: Path,
    *,
    enforce_official: bool = True,
    command: list[str] | None = None,
) -> dict[str, Any]:
    lock_path = lock_path.resolve()
    out_dir = out_dir.resolve()
    report_path = report_path.resolve()
    started = utc_now()
    lock, lock_digest = load_source_lock(lock_path, enforce_official=enforce_official)
    report: dict[str, Any] = {
        "schema_version": 1,
        "dataset": lock["dataset"]["name"],
        "release": lock["dataset"]["release"],
        "official_page": lock["dataset"]["official_page"],
        "lock_path": str(lock_path),
        "source_lock_sha256": lock_digest,
        "command": command,
        "started_at_utc": started,
        "completed_at_utc": None,
        "status": "IN_PROGRESS",
        "sources": [],
    }
    out_dir.mkdir(parents=True, exist_ok=True)

    for source in lock["files"]:
        target = out_dir / source["filename"]
        entry: dict[str, Any] = {
            "role": source["role"],
            "release": lock["dataset"]["release"],
            "official_url": source["official_url"],
            "filename": source["filename"],
            "local_path": str(target),
            "upstream_expected_sha256": source.get("upstream_sha256"),
            "upstream_sha256_provenance": source.get("upstream_sha256_provenance"),
            "observed_sha256_provenance": source.get("observed_sha256_provenance"),
            "cache_disposition": None,
            "quarantined_path": None,
            "download_response": None,
            "validation": "FAIL",
        }
        report["sources"].append(entry)
        partial: Path | None = None
        try:
            expected_size = source.get("observed_bytes")
            expected_hash = source.get("observed_sha256")
            if target.exists():
                actual_size, actual_hash = sha256_file(target)
                if expected_size == actual_size and expected_hash == actual_hash:
                    schema = inspect_feather(target, source["role"])
                    entry.update(
                        {
                            "exact_observed_bytes": actual_size,
                            "observed_sha256": actual_hash,
                            "cache_disposition": "reused",
                            "feather": schema,
                            "validation": "PASS",
                        }
                    )
                    continue
                quarantine = _quarantine(target, actual_hash)
                entry["cache_disposition"] = "rejected"
                entry["quarantined_path"] = str(quarantine)

            partial = target.with_name(f"{target.name}.partial-{uuid.uuid4().hex}")
            actual_size, actual_hash, response_info = _download(source, partial)
            entry["download_response"] = response_info
            if expected_size is not None and actual_size != expected_size:
                raise SourceFetchError(
                    f"downloaded size {actual_size} does not match locked size {expected_size}"
                )
            if expected_hash is not None and actual_hash != expected_hash:
                raise SourceFetchError(
                    f"downloaded SHA-256 {actual_hash} does not match locked SHA-256 {expected_hash}"
                )
            schema = inspect_feather(partial, source["role"])
            os.replace(partial, target)
            entry.update(
                {
                    "exact_observed_bytes": actual_size,
                    "observed_sha256": actual_hash,
                    "cache_disposition": (
                        "replaced" if entry["quarantined_path"] is not None else "downloaded"
                    ),
                    "feather": schema,
                    "validation": "PASS",
                }
            )
        except (OSError, SourceFetchError) as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            if partial is not None:
                entry["incomplete_path"] = str(partial)
            report["status"] = "FAIL"
            report["completed_at_utc"] = utc_now()
            _write_json(report_path, report)
            raise SourceFetchError(str(exc)) from exc

    report["status"] = "PASS"
    report["completed_at_utc"] = utc_now()
    _write_json(report_path, report)
    return report
