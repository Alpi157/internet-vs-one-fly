#!/usr/bin/env python3
"""Run the small, argv-only milestone acceptance registry."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    return cleaned or "command"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def git_head(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def failure_result(index: int, name: str, argv: list[str], cwd: Path, reason: str) -> dict[str, Any]:
    now = utc_now()
    return {
        "index": index,
        "name": name,
        "argv": argv,
        "cwd": str(cwd),
        "required": True,
        "start_time_utc": now,
        "end_time_utc": now,
        "duration_seconds": 0.0,
        "exit_status": 127,
        "stdout": "",
        "stderr": reason + "\n",
        "status": "FAIL",
        "failure_reason": reason,
    }


def run_command(index: int, raw: object, root: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return failure_result(index, f"command-{index}", [], root, "command entry is not an object")

    name = raw.get("name")
    argv = raw.get("argv")
    required = raw.get("required")
    if not isinstance(name, str) or not name:
        name = f"command-{index}"
    if required is not True:
        return failure_result(index, name, argv if isinstance(argv, list) else [], root, "every registered command must be required")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        return failure_result(index, name, [], root, "argv must be a non-empty list of non-empty strings")

    cwd_value = raw.get("cwd", ".")
    if not isinstance(cwd_value, str):
        return failure_result(index, name, argv, root, "cwd must be a string")
    cwd = (root / cwd_value).resolve()
    if not cwd.is_relative_to(root) or not cwd.is_dir():
        return failure_result(index, name, argv, cwd, "command cwd is missing or outside repository root")

    required_paths = raw.get("required_paths", [])
    if not isinstance(required_paths, list) or not all(isinstance(item, str) for item in required_paths):
        return failure_result(index, name, argv, cwd, "required_paths must be a list of strings")
    missing = []
    for value in required_paths:
        candidate = (root / value).resolve()
        if not candidate.is_relative_to(root) or not candidate.exists():
            missing.append(value)
    if missing:
        return failure_result(index, name, argv, cwd, f"missing required path(s): {', '.join(missing)}")

    timeout = raw.get("timeout_seconds", 300)
    if not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 2400:
        return failure_result(index, name, argv, cwd, "timeout_seconds must be greater than 0 and at most 2400")

    started_at = utc_now()
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=float(timeout),
        )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_status = completed.returncode
        reason = None if exit_status == 0 else f"command exited with status {exit_status}"
    except FileNotFoundError as exc:
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}\n"
        exit_status = 127
        reason = "required executable was not found"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stderr += f"command timed out after {float(timeout):g} seconds\n"
        exit_status = 124
        reason = "command timed out"

    duration = time.monotonic() - started
    return {
        "index": index,
        "name": name,
        "argv": argv,
        "cwd": str(cwd),
        "required": True,
        "start_time_utc": started_at,
        "end_time_utc": utc_now(),
        "duration_seconds": round(duration, 6),
        "exit_status": exit_status,
        "stdout": stdout,
        "stderr": stderr,
        "status": "PASS" if exit_status == 0 else "FAIL",
        "failure_reason": reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("milestone")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--registry", type=Path, default=Path("tools/acceptance.json"))
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    out = args.out if args.out.is_absolute() else root / args.out
    registry_path = args.registry if args.registry.is_absolute() else root / args.registry
    overall_start = utc_now()

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if registry.get("schema_version") != 1 or not isinstance(registry.get("milestones"), dict):
            raise ValueError("unsupported or malformed acceptance registry")
        milestone = registry["milestones"].get(args.milestone)
        if not isinstance(milestone, dict):
            raise ValueError(f"milestone {args.milestone!r} is not registered")
        commands = milestone.get("commands")
        if not isinstance(commands, list) or not commands:
            raise ValueError(f"milestone {args.milestone!r} has no required commands")
        results = [run_command(index, command, root) for index, command in enumerate(commands, start=1)]
        registry_error = None
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        registry_error = f"{type(exc).__name__}: {exc}"
        results = [failure_result(1, "registry-validation", [], root, registry_error)]

    for result in results:
        prefix = f"{result['index']:02d}-{safe_name(result['name'])}"
        stdout_path = out / f"{prefix}.stdout.txt"
        stderr_path = out / f"{prefix}.stderr.txt"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(result["stdout"], encoding="utf-8")
        stderr_path.write_text(result["stderr"], encoding="utf-8")
        result["stdout_path"] = stdout_path.relative_to(out).as_posix()
        result["stderr_path"] = stderr_path.relative_to(out).as_posix()

    passed = all(result["exit_status"] == 0 for result in results)
    report = {
        "schema_version": 1,
        "milestone": args.milestone,
        "registry": str(registry_path),
        "repository_root": str(root),
        "submitted_code_sha": git_head(root),
        "start_time_utc": overall_start,
        "end_time_utc": utc_now(),
        "status": "PASS" if passed else "FAIL",
        "exit_status": 0 if passed else 1,
        "registry_error": registry_error,
        "commands": results,
    }
    write_json(out / "command-results.json", report)

    for result in results:
        print(f"[{result['status']}] {result['index']}: {result['name']} (exit {result['exit_status']})")
        if result["stderr"]:
            print(result["stderr"], file=sys.stderr, end="")
    print(f"Acceptance {report['status']}: {args.milestone}; evidence: {out / 'command-results.json'}")
    return report["exit_status"]


if __name__ == "__main__":
    raise SystemExit(main())
