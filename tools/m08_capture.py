#!/usr/bin/env python3
"""Run one bounded command and retain stdout, stderr, and exit status as M08 evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    output = args.out if args.out.is_absolute() else ROOT / args.out
    started_at = utc_now()
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=args.timeout,
        )
        exit_status = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        exit_status = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr if isinstance(exc.stderr, str) else "") + "\ncommand timed out\n"
        timed_out = True
    report = {
        "schema_version": 1,
        "command": command,
        "cwd": str(ROOT),
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "duration_seconds": round(time.monotonic() - started, 6),
        "timeout_seconds": args.timeout,
        "timed_out": timed_out,
        "exit_status": exit_status,
        "status": "PASS" if exit_status == 0 else "FAIL",
        "stdout": stdout,
        "stderr": stderr,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    if output.suffix == ".json":
        content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    else:
        content = (
            f"command: {json.dumps(command)}\n"
            f"exit_status: {exit_status}\n"
            f"status: {report['status']}\n"
            f"started_at_utc: {started_at}\n"
            f"ended_at_utc: {report['ended_at_utc']}\n"
            f"duration_seconds: {report['duration_seconds']}\n"
            "\n[stdout]\n"
            f"{stdout}"
            "\n[stderr]\n"
            f"{stderr}"
        )
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, output)
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
