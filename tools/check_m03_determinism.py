#!/usr/bin/env python3
"""Perform a genuine second M03 compile and compare semantic graph contents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flybench.graph import (
    audit_graph,
    compare_compiled_graphs,
    compile_graph,
    write_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--repeat-out", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    primary = (root / args.primary).resolve() if not args.primary.is_absolute() else args.primary
    lock = (root / args.lock).resolve() if not args.lock.is_absolute() else args.lock
    selection = (
        (root / args.selection).resolve()
        if not args.selection.is_absolute()
        else args.selection
    )
    repeat = (
        (root / args.repeat_out).resolve()
        if not args.repeat_out.is_absolute()
        else args.repeat_out
    )
    output = (root / args.out).resolve() if not args.out.is_absolute() else args.out
    command = [
        "python",
        "tools/check_m03_determinism.py",
        "--primary",
        args.primary.as_posix(),
        "--lock",
        args.lock.as_posix(),
        "--selection",
        args.selection.as_posix(),
        "--repeat-out",
        args.repeat_out.as_posix(),
        "--out",
        args.out.as_posix(),
    ]
    try:
        primary_audit = audit_graph(primary)
        repeat_manifest = compile_graph(
            lock,
            selection,
            repeat,
            command=command,
        )
        repeat_audit_path = output.parent / "repeat-audit.json"
        repeat_audit = audit_graph(repeat, repeat_audit_path, command=command)
        comparison = compare_compiled_graphs(primary, repeat)
        comparison.update(
            {
                "command": command,
                "primary_audit_status": primary_audit["status"],
                "repeat_audit_status": repeat_audit["status"],
                "repeat_build_resource": repeat_manifest["build_resource"],
                "primary_compiler": primary_audit["compiler"],
                "repeat_compiler": repeat_audit["compiler"],
            }
        )
        write_json(output, comparison)
    except Exception as exc:
        write_json(
            output,
            {
                "schema_version": 1,
                "status": "FAIL",
                "command": command,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        print(f"determinism check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(comparison, sort_keys=True))
    return 0 if comparison["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
