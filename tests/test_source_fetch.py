from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.feather as feather
import pytest

from flybench.data import OFFICIAL_PAGE, SourceFetchError, fetch_sources, load_source_lock


ROOT = Path(__file__).resolve().parents[1]
FILENAMES = {
    "curated_annotations": "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "aggregate_neurotransmitters": "body-neurotransmitters-male-cns-v1.0.feather",
    "connection_weights": "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
}


def feather_bytes(tmp_path: Path, role: str, *, malformed: bool = False) -> bytes:
    if malformed:
        values = {"garbage": [1, 2]}
    elif role == "curated_annotations":
        values = {"bodyId": [1, 2], "type": ["fixture-a", "fixture-b"]}
    elif role == "aggregate_neurotransmitters":
        values = {"bodyId": [1, 2], "predictedNt": ["fixture-a", "fixture-b"]}
    else:
        values = {"body_pre": [1, 2], "body_post": [2, 3], "weight": [4, 5]}
    path = tmp_path / f"{role}-fixture.feather"
    feather.write_feather(pa.table(values), path)
    return path.read_bytes()


class FixtureServer(ThreadingHTTPServer):
    routes: dict[str, dict]
    requests: list[str]


@contextmanager
def http_fixture(routes: dict[str, dict]) -> Iterator[tuple[str, list[str]]]:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            requests.append(self.path)
            route = routes.get(self.path)
            if route is None:
                self.send_error(404)
                return
            status = route.get("status", 200)
            payload = route.get("payload", b"")
            self.send_response(status)
            self.send_header("Content-Length", str(route.get("declared_length", len(payload))))
            self.end_headers()
            if status < 400:
                self.wfile.write(payload[: route.get("send_bytes", len(payload))])
                self.wfile.flush()
                if route.get("send_bytes") is not None:
                    self.close_connection = True

        def log_message(self, _format: str, *args: object) -> None:
            return

    server = FixtureServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def make_lock(
    path: Path,
    base_url: str,
    payloads: dict[str, bytes],
    *,
    resolved: bool = True,
    url_filename_override: str | None = None,
) -> Path:
    files = []
    for role, filename in FILENAMES.items():
        payload = payloads[role]
        url_filename = url_filename_override if role == "curated_annotations" and url_filename_override else filename
        files.append(
            {
                "role": role,
                "filename": filename,
                "official_url": f"{base_url}/{url_filename}",
                "download_max_bytes": 1024 * 1024,
                "expected_format": "Apache Arrow Feather",
                "upstream_sha256": None,
                "upstream_sha256_provenance": "Fixture has no upstream SHA-256.",
                "observed_bytes": len(payload) if resolved else None,
                "observed_sha256": hashlib.sha256(payload).hexdigest() if resolved else None,
                "observed_sha256_provenance": "Independently calculated fixture identity." if resolved else None,
            }
        )
    value = {
        "schema_version": 1,
        "dataset": {
            "name": "MaleCNS",
            "release": "MaleCNS v1.0",
            "official_page": OFFICIAL_PAGE,
            "license": "CC-BY",
        },
        "files": files,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def make_payloads(tmp_path: Path) -> dict[str, bytes]:
    return {role: feather_bytes(tmp_path, role) for role in FILENAMES}


def routes_for(payloads: dict[str, bytes]) -> dict[str, dict]:
    return {
        f"/{FILENAMES[role]}": {"payload": payload} for role, payload in payloads.items()
    }


def test_committed_lock_pins_only_observed_official_identities() -> None:
    lock, digest = load_source_lock(ROOT / "profiles" / "source-lock.json")
    assert digest == hashlib.sha256((ROOT / "profiles" / "source-lock.json").read_bytes()).hexdigest()
    assert lock["dataset"]["release"] == "MaleCNS v1.0"
    assert set(source["role"] for source in lock["files"]) == set(FILENAMES)
    for source in lock["files"]:
        assert source["filename"] == FILENAMES[source["role"]]
        assert source["official_url"].startswith(
            "https://storage.googleapis.com/flyem-male-cns/v1.0/"
        )
        assert source["upstream_sha256"] is None
        assert "No SHA-256 observed" in source["upstream_sha256_provenance"]
        assert source["observed_bytes"] > 0
        assert len(source["observed_sha256"]) == 64
        assert "Locally computed" in source["observed_sha256_provenance"]


def test_matching_cache_is_hashed_validated_and_reused(tmp_path: Path) -> None:
    payloads = make_payloads(tmp_path)
    with http_fixture(routes_for(payloads)) as (base_url, requests):
        lock = make_lock(tmp_path / "lock.json", base_url, payloads)
        out = tmp_path / "raw"
        out.mkdir()
        for role, filename in FILENAMES.items():
            (out / filename).write_bytes(payloads[role])
        report_path = tmp_path / "report.json"
        report = fetch_sources(
            lock, out, report_path, enforce_official=False, command=["fixture", "reuse"]
        )

    assert requests == []
    assert report["status"] == "PASS"
    assert all(source["cache_disposition"] == "reused" for source in report["sources"])
    for source in report["sources"]:
        payload = payloads[source["role"]]
        # This independent one-shot calculation does not call the fetcher's hash helper.
        assert source["exact_observed_bytes"] == len(payload)
        assert source["observed_sha256"] == hashlib.sha256(payload).hexdigest()
        assert source["feather"]["role_validation"] == "PASS"
    assert json.loads(report_path.read_text())["source_lock_sha256"] == hashlib.sha256(
        lock.read_bytes()
    ).hexdigest()


def test_corrupt_cache_is_quarantined_and_reacquired(tmp_path: Path) -> None:
    payloads = make_payloads(tmp_path)
    with http_fixture(routes_for(payloads)) as (base_url, requests):
        lock = make_lock(tmp_path / "lock.json", base_url, payloads)
        out = tmp_path / "raw"
        out.mkdir()
        first_filename = FILENAMES["curated_annotations"]
        (out / first_filename).write_bytes(b"corrupt cache bytes")
        for role in ("aggregate_neurotransmitters", "connection_weights"):
            (out / FILENAMES[role]).write_bytes(payloads[role])
        report = fetch_sources(lock, out, tmp_path / "report.json", enforce_official=False)

    assert requests == [f"/{first_filename}"]
    assert (out / first_filename).read_bytes() == payloads["curated_annotations"]
    assert len(list(out.glob(f"{first_filename}.corrupt-*"))) == 1
    first = report["sources"][0]
    assert first["cache_disposition"] == "replaced"
    assert first["quarantined_path"]


def test_truncated_transfer_never_becomes_final_file(tmp_path: Path) -> None:
    payloads = make_payloads(tmp_path)
    first_role = "curated_annotations"
    first_filename = FILENAMES[first_role]
    routes = routes_for(payloads)
    routes[f"/{first_filename}"]["declared_length"] = len(payloads[first_role])
    routes[f"/{first_filename}"]["send_bytes"] = len(payloads[first_role]) - 7
    with http_fixture(routes) as (base_url, _requests):
        lock = make_lock(tmp_path / "lock.json", base_url, payloads)
        out = tmp_path / "raw"
        report_path = tmp_path / "report.json"
        with pytest.raises(SourceFetchError):
            fetch_sources(lock, out, report_path, enforce_official=False)

    assert not (out / first_filename).exists()
    partials = list(out.glob(f"{first_filename}.partial-*"))
    assert len(partials) == 1
    report = json.loads(report_path.read_text())
    assert report["status"] == "FAIL"
    assert report["sources"][0]["validation"] == "FAIL"
    assert ".partial-" in report["sources"][0]["incomplete_path"]


def test_obviously_wrong_feather_role_is_rejected(tmp_path: Path) -> None:
    payloads = make_payloads(tmp_path)
    payloads["curated_annotations"] = feather_bytes(tmp_path, "wrong", malformed=True)
    with http_fixture(routes_for(payloads)) as (base_url, _requests):
        lock = make_lock(tmp_path / "lock.json", base_url, payloads)
        out = tmp_path / "raw"
        with pytest.raises(SourceFetchError, match="schema does not satisfy"):
            fetch_sources(lock, out, tmp_path / "report.json", enforce_official=False)
    assert not (out / FILENAMES["curated_annotations"]).exists()


def test_non_success_http_status_fails_without_final_file(tmp_path: Path) -> None:
    payloads = make_payloads(tmp_path)
    routes = routes_for(payloads)
    routes[f"/{FILENAMES['curated_annotations']}"] = {"status": 503, "payload": b"unavailable"}
    with http_fixture(routes) as (base_url, _requests):
        lock = make_lock(tmp_path / "lock.json", base_url, payloads)
        out = tmp_path / "raw"
        with pytest.raises(SourceFetchError, match="HTTP status 503"):
            fetch_sources(lock, out, tmp_path / "report.json", enforce_official=False)
    assert not (out / FILENAMES["curated_annotations"]).exists()


def test_locked_url_and_filename_cannot_silently_diverge(tmp_path: Path) -> None:
    payloads = make_payloads(tmp_path)
    with http_fixture(routes_for(payloads)) as (base_url, requests):
        lock = make_lock(
            tmp_path / "lock.json",
            base_url,
            payloads,
            url_filename_override="different-source.feather",
        )
        with pytest.raises(SourceFetchError, match="URL filename does not match"):
            load_source_lock(lock, enforce_official=False)
    assert requests == []
