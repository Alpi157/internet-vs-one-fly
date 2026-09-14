#!/usr/bin/env python3
"""Build the compact, evidence-bearing review ZIP used by FlyBench milestones."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ARCHITECTURE_SHA256 = "bae80837d5d6d769ae5b728af3b80c1caa21b7f08efdd7f3eb458f7bb2eab9d1"
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MAX_INCLUDED_FILE_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_BYTES = 15 * 1024 * 1024

CACHE_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}
RAW_PARTS = {"raw", "raw-data", "raw_data", "bulk"}


class BundleError(RuntimeError):
    """A review bundle precondition was not met."""


def git(root: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=text, check=False
    )
    if completed.returncode:
        stderr = completed.stderr if text else completed.stderr.decode("utf-8", "replace")
        raise BundleError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return completed.stdout


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exclusion_reason(path: PurePosixPath) -> str | None:
    parts_lower = tuple(part.lower() for part in path.parts)
    name = path.name.lower()
    if any(part in CACHE_PARTS for part in parts_lower):
        return "cache, environment, dependency, build, or Git metadata"
    if len(parts_lower) >= 2 and parts_lower[0] == "data" and parts_lower[1] in RAW_PARTS:
        return "bulk or raw data"
    if any("malecns" in part for part in parts_lower) and name.endswith((".csv", ".tsv", ".feather", ".parquet", ".npy", ".npz")):
        return "MaleCNS bulk data"
    if name == ".env" or name.startswith(".env."):
        return "environment secret"
    if name.endswith((".pem", ".key", ".p12", ".pfx")) or name.startswith(("id_rsa", "id_ed25519")):
        return "key material"
    if any(marker in name for marker in ("credential", "credentials", "private_key", "secret", "token")):
        return "credential or secret material"
    if "resume" in name or "curriculum_vitae" in name:
        return "operator resume"
    return None


def tracked_paths(root: Path, commit: str) -> list[str]:
    output = git(root, "ls-tree", "-r", "--name-only", "-z", commit)
    assert isinstance(output, str)
    return sorted(path for path in output.split("\0") if path)


def commit_blob(root: Path, commit: str, path: str) -> bytes:
    output = git(root, "show", f"{commit}:{path}", text=False)
    assert isinstance(output, bytes)
    return output


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def inventory(entries: dict[str, bytes]) -> list[dict[str, Any]]:
    return [
        {"path": path, "bytes": len(entries[path]), "sha256": sha256(entries[path])}
        for path in sorted(entries)
    ]


def load_command_reports(evidence_root: Path) -> list[tuple[str, dict[str, Any]]]:
    reports: list[tuple[str, dict[str, Any]]] = []
    if not evidence_root.is_dir():
        return reports
    for path in sorted(evidence_root.rglob("command-results.json")):
        if exclusion_reason(PurePosixPath(path.relative_to(evidence_root).as_posix())):
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            reports.append((path.relative_to(evidence_root).as_posix(), value))
    return reports


def render_review(
    milestone: str,
    attempt: int,
    base: str,
    submitted: str,
    architecture_sha: str,
    reports: list[tuple[str, dict[str, Any]]],
    tooling: dict[str, Any] | None,
    manual_source_review_present: bool,
) -> bytes:
    primary = next((report for path, report in reports if path == "command-results.json"), None)
    primary_status = primary.get("status") if primary else "NOT_CAPTURED"
    if milestone == "M02":
        objective = (
            "Acquire, validate, and pin the exact official MaleCNS v1.0 source bytes needed "
            "by the architecture without compiling a graph."
        )
        assumptions = [
            "The source set is exactly the three official M02 Feather files.",
            "Upstream SHA-256 values remain null because none was observed on the official page; recorded SHA-256 values are locally observed byte identities.",
            "Bulk source bytes are deliberately excluded and described in large-files.json.",
            "No graph cardinality, biological mapping, or later-milestone result is claimed.",
        ]
    else:
        objective = (
            "Establish the M01 reproducible Python workspace, repository invariants, offline "
            "checks, acceptance runner, and bounded review-bundle mechanism."
        )
        assumptions = [
            "Python 3.12 is the supported M01 development runtime.",
            "Node and npm are not M01 prerequisites and were not installed.",
            "Generated evidence and review archives are ignored repository outputs.",
            "M01 contains no scientific model, biological mapping, runtime, or later-milestone implementation.",
        ]
    lines = [
        f"# {milestone} review submission (attempt {attempt})",
        "",
        "## Objective",
        "",
        objective,
        "",
        "## Summary",
        "",
        f"The repository snapshot is the committed tree at `{submitted}`. The primary captured acceptance status is `{primary_status}`. External review remains pending.",
        "",
        "## Assumptions and decisions",
        "",
        *[f"- {assumption}" for assumption in assumptions],
        "",
        "## Identities",
        "",
        f"- Architecture SHA-256: `{architecture_sha}`",
        f"- Base identity: `{base}`",
        f"- Submitted code SHA: `{submitted}`",
        "",
        "## Commands actually captured",
        "",
    ]
    if reports:
        for report_path, report in reports:
            lines.append(f"Evidence report `{report_path}`: status `{report.get('status', 'UNKNOWN')}`.")
            lines.append("")
            for command in report.get("commands", []):
                argv = json.dumps(command.get("argv", []), ensure_ascii=False)
                lines.append(
                    f"- `{command.get('name', 'unnamed')}`: argv `{argv}`; cwd `{command.get('cwd')}`; "
                    f"exit `{command.get('exit_status')}`; result `{command.get('status')}`."
                )
            lines.append("")
    else:
        lines.extend(["No command-results.json was available.", ""])

    lines.extend(["## Real results", ""])
    if primary:
        for command in primary.get("commands", []):
            lines.append(
                f"- `{command.get('name', 'unnamed')}` exited `{command.get('exit_status')}` "
                f"with status `{command.get('status')}`."
            )
    else:
        lines.append("- Primary acceptance results were not captured.")

    lines.extend(["", "## Failures", ""])
    primary_failures = [
        command for command in (primary or {}).get("commands", []) if command.get("exit_status") != 0
    ]
    if primary_failures:
        for command in primary_failures:
            lines.append(
                f"- `{command.get('name', 'unnamed')}`: {command.get('failure_reason') or 'failed'}"
            )
    else:
        lines.append("- No failure is recorded in the primary acceptance report.")

    lines.extend(["", "## Manual and tooling evidence", ""])
    commands = tooling.get("commands", {}) if isinstance(tooling, dict) else {}
    if commands:
        for name in ("git", "python", "uv", "node", "npm", "uname"):
            receipt = commands.get(name, {})
            lines.append(
                f"- `{name}`: available `{receipt.get('available')}`; exit `{receipt.get('exit_status')}`; "
                f"normalized `{receipt.get('normalized_version')}`."
            )
    else:
        lines.append("- No tooling.json receipt was available.")
    if milestone == "M02":
        lines.append(
            "- `evidence/M02/manual-source-review.txt`: "
            + ("present (operator-supplied)." if manual_source_review_present else "absent; manual review remains pending.")
        )

    lines.extend(["", "## Unresolved issues", "", "- The external reviewer has not issued a verdict."])
    if milestone == "M02" and not manual_source_review_present:
        lines.append("- The operator's manual source-origin receipt is absent.")
    lines.extend(
        [
            "- Scientific and product capabilities assigned to later milestones remain intentionally unimplemented.",
            "",
            "## Review limitations",
            "",
            "- Captured output proves what this submission reports running; it is not independent reviewer reproduction.",
            (
                "- This archive covers source identity and acquisition only; it contains no graph-compilation or biological-result evidence."
                if milestone == "M02"
                else "- This archive covers M01 infrastructure only and contains no scientific-result evidence."
            ),
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def add_evidence(
    entries: dict[str, bytes], evidence_root: Path, omitted: list[dict[str, Any]]
) -> None:
    if not evidence_root.is_dir():
        entries["evidence/README.txt"] = b"No generated evidence directory was present at bundle time.\n"
        return
    included = 0
    for path in sorted(evidence_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = PurePosixPath(path.relative_to(evidence_root).as_posix())
        reason = exclusion_reason(relative)
        size = path.stat().st_size
        if reason or size > MAX_INCLUDED_FILE_BYTES:
            data = path.read_bytes() if not reason else b""
            omitted.append(
                {
                    "path": f"evidence/{relative.as_posix()}",
                    "reason": reason or "file exceeds bounded per-file review size",
                    "bytes": size,
                    "sha256": sha256(data) if data else None,
                }
            )
            continue
        entries[f"evidence/{relative.as_posix()}"] = path.read_bytes()
        included += 1
    if included == 0:
        entries["evidence/README.txt"] = b"No includable generated evidence was present at bundle time.\n"


def add_base(entries: dict[str, bytes], root: Path, base: str, submitted: str) -> None:
    if base == "EMPTY":
        entries["base/README.txt"] = b"M01 has no prior accepted repository; the comparison base is the Git empty tree.\n"
        return
    changed = git(root, "diff", "--name-status", "-z", base, submitted)
    assert isinstance(changed, str)
    tokens = changed.split("\0")
    index = 0
    included = 0
    while index < len(tokens) and tokens[index]:
        status = tokens[index]
        index += 1
        if status.startswith("R") or status.startswith("C"):
            old_path = tokens[index]
            index += 2
        else:
            old_path = tokens[index]
            index += 1
        if status.startswith("A"):
            continue
        reason = exclusion_reason(PurePosixPath(old_path))
        if reason:
            continue
        try:
            data = commit_blob(root, base, old_path)
        except BundleError:
            continue
        if len(data) <= MAX_INCLUDED_FILE_BYTES:
            entries[f"base/{old_path}"] = data
            included += 1
    if included == 0:
        entries["base/README.txt"] = b"No changed or deleted small file required a prior-version copy.\n"


def m02_large_source_inventory(
    root: Path, submitted: str, evidence_root: Path
) -> list[dict[str, Any]]:
    try:
        lock_bytes = commit_blob(root, submitted, "profiles/source-lock.json")
        lock = json.loads(lock_bytes)
        report = json.loads((evidence_root / "source-report.json").read_text(encoding="utf-8"))
    except (BundleError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M02 source lock/report is missing or invalid: {exc}") from exc
    lock_digest = sha256(lock_bytes)
    if report.get("status") != "PASS" or report.get("source_lock_sha256") != lock_digest:
        raise BundleError("M02 source report does not pass or does not identify the committed source lock")
    locked_by_role = {source.get("role"): source for source in lock.get("files", [])}
    report_by_role = {source.get("role"): source for source in report.get("sources", [])}
    if len(locked_by_role) != 3 or set(locked_by_role) != set(report_by_role):
        raise BundleError("M02 source lock/report roles do not identify the same three files")

    result: list[dict[str, Any]] = []
    for role in sorted(locked_by_role):
        locked = locked_by_role[role]
        observed = report_by_role[role]
        if (
            observed.get("validation") != "PASS"
            or observed.get("exact_observed_bytes") != locked.get("observed_bytes")
            or observed.get("observed_sha256") != locked.get("observed_sha256")
            or observed.get("official_url") != locked.get("official_url")
            or observed.get("filename") != locked.get("filename")
        ):
            raise BundleError(f"M02 lock/report identity mismatch for role {role!r}")
        feather = observed.get("feather", {})
        result.append(
            {
                "path": f"data/raw/{locked['filename']}",
                "reason": "official MaleCNS bulk source excluded from the review ZIP",
                "official_url": locked["official_url"],
                "release": lock["dataset"]["release"],
                "role": role,
                "bytes": locked["observed_bytes"],
                "sha256": locked["observed_sha256"],
                "hash_provenance": locked["observed_sha256_provenance"],
                "upstream_sha256": locked.get("upstream_sha256"),
                "format": feather.get("format"),
                "schema_fields": feather.get("fields"),
                "schema_role_validation": feather.get("role_validation"),
                "acquisition_command": report.get("command"),
            }
        )
    return result


def build_bundle(root: Path, milestone: str, attempt: int, base_arg: str) -> bytes:
    submitted = str(git(root, "rev-parse", "HEAD")).strip()
    status = str(git(root, "status", "--porcelain=v1", "--untracked-files=all"))
    if status:
        raise BundleError("working tree has tracked or non-ignored changes; refusing to certify a dirty code tree")

    if base_arg == "EMPTY":
        if milestone != "M01":
            raise BundleError("EMPTY is only valid for M01")
        base = "EMPTY"
        diff_base = EMPTY_TREE_SHA
    else:
        base = str(git(root, "rev-parse", "--verify", f"{base_arg}^{{commit}}")).strip()
        diff_base = base

    architecture_path = root / "docs" / "architecture.md"
    if not architecture_path.is_file():
        raise BundleError("docs/architecture.md is missing")
    architecture_sha = sha256(architecture_path.read_bytes())
    if architecture_sha != ARCHITECTURE_SHA256:
        raise BundleError(
            f"architecture mismatch: computed {architecture_sha}, expected {ARCHITECTURE_SHA256}"
        )

    entries: dict[str, bytes] = {}
    omitted: list[dict[str, Any]] = []
    repo_paths: list[str] = []
    for path in tracked_paths(root, submitted):
        pure = PurePosixPath(path)
        reason = exclusion_reason(pure)
        data = commit_blob(root, submitted, path)
        if reason:
            raise BundleError(f"tracked forbidden path {path!r}: {reason}")
        if len(data) > MAX_INCLUDED_FILE_BYTES:
            raise BundleError(f"tracked path {path!r} exceeds the bounded M01 snapshot limit")
        entries[f"repo/{path}"] = data
        repo_paths.append(path)

    if "ledger.yaml" not in repo_paths:
        raise BundleError("committed ledger.yaml is missing")
    entries["ledger.yaml"] = commit_blob(root, submitted, "ledger.yaml")
    entries["tree.txt"] = ("\n".join(repo_paths) + "\n").encode("utf-8")
    entries["git_status.txt"] = status.encode("utf-8")
    diff = git(root, "diff", "--binary", diff_base, submitted, "--", text=False)
    assert isinstance(diff, bytes)
    entries["git_diff.patch"] = diff

    add_base(entries, root, base, submitted)
    evidence_root = root / "evidence" / milestone
    add_evidence(entries, evidence_root, omitted)
    if milestone == "M02":
        omitted.extend(m02_large_source_inventory(root, submitted, evidence_root))

    large_files = {
        "schema_version": 1,
        "milestone": milestone,
        "omitted": omitted,
        "statement": (
            "No legitimate large files were omitted."
            if not omitted
            else "The listed files were omitted for the stated bounded-review reason; identities come from the committed lock and captured report."
        ),
    }
    entries["large-files.json"] = json_bytes(large_files)

    reports = load_command_reports(evidence_root)
    try:
        tooling_value = json.loads(commit_blob(root, submitted, "tooling.json").decode("utf-8"))
    except (BundleError, UnicodeDecodeError, json.JSONDecodeError):
        tooling_value = None
    entries["REVIEW.md"] = render_review(
        milestone,
        attempt,
        base,
        submitted,
        architecture_sha,
        reports,
        tooling_value,
        (evidence_root / "manual-source-review.txt").is_file(),
    )

    manifest = {
        "schema": "flybench-review-manifest",
        "version": 1,
        "milestone": milestone,
        "attempt": attempt,
        "base_identity": base,
        "submitted_code_sha": submitted,
        "architecture_sha256": architecture_sha,
        "inventory": inventory(entries),
        "unhashed_entries": ["review-manifest.json"],
    }
    entries["review-manifest.json"] = json_bytes(manifest)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(entries):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, entries[path])
    value = archive.getvalue()
    if len(value) >= MAX_ARCHIVE_BYTES:
        raise BundleError(f"review bundle is {len(value)} bytes, exceeding the 15 MiB review limit")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--milestone", required=True)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.attempt < 1:
        parser.error("--attempt must be positive")

    root = Path.cwd().resolve()
    output = args.out if args.out.is_absolute() else root / args.out
    try:
        bundle = build_bundle(root, args.milestone, args.attempt, args.base)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_bytes(bundle)
        os.replace(temporary, output)
    except (BundleError, OSError) as exc:
        print(f"review bundle failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {output} ({len(bundle)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
