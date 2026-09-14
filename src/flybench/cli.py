"""Small FlyBench command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flybench.data import SourceFetchError, fetch_sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flybench")
    commands = parser.add_subparsers(dest="command", required=True)
    data = commands.add_parser("data", help="Pinned source-data operations")
    data_commands = data.add_subparsers(dest="data_command", required=True)
    fetch = data_commands.add_parser("fetch", help="Acquire or verify the locked M02 sources")
    fetch.add_argument("--lock", required=True, type=Path)
    fetch.add_argument("--out", required=True, type=Path)
    fetch.add_argument(
        "--report", type=Path, default=Path("evidence/M02/source-report.json")
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "data" and args.data_command == "fetch":
        command = ["flybench", *(argv if argv is not None else sys.argv[1:])]
        try:
            report = fetch_sources(args.lock, args.out, args.report, command=command)
        except (OSError, SourceFetchError) as exc:
            print(f"source fetch failed: {exc}", file=sys.stderr)
            print(f"failure report: {args.report}", file=sys.stderr)
            return 1
        summary = {
            "status": report["status"],
            "release": report["release"],
            "source_lock_sha256": report["source_lock_sha256"],
            "sources": [
                {
                    "role": source["role"],
                    "filename": source["filename"],
                    "bytes": source["exact_observed_bytes"],
                    "sha256": source["observed_sha256"],
                    "cache_disposition": source["cache_disposition"],
                    "validation": source["validation"],
                }
                for source in report["sources"]
            ],
            "report": str(args.report.resolve()),
        }
        print(json.dumps(summary, sort_keys=True))
        return 0
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
