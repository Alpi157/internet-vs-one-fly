"""Small FlyBench command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flybench.data import SourceFetchError, fetch_sources
from flybench.graph import (
    GraphAuditError,
    GraphCompileError,
    audit_graph,
    compile_graph,
    write_json,
)


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
    compile_command = data_commands.add_parser(
        "compile", help="Compile pinned sources into an immutable M03 sparse graph"
    )
    compile_command.add_argument("--lock", required=True, type=Path)
    compile_command.add_argument("--selection", required=True, type=Path)
    compile_command.add_argument("--out", required=True, type=Path)
    audit = data_commands.add_parser(
        "audit", help="Independently audit a compiled M03 sparse graph"
    )
    audit.add_argument("graph", type=Path)
    audit.add_argument("--out", required=True, type=Path)
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
    if args.command == "data" and args.data_command == "compile":
        command = ["flybench", *(argv if argv is not None else sys.argv[1:])]
        try:
            manifest = compile_graph(
                args.lock,
                args.selection,
                args.out,
                command=command,
            )
        except (OSError, SourceFetchError, GraphCompileError) as exc:
            print(f"graph compile failed: {exc}", file=sys.stderr)
            return 1
        summary = {
            "status": "PASS",
            "out": str(args.out.resolve()),
            "source_lock_sha256": manifest["source_lock_sha256"],
            "selection_profile_sha256": manifest["selection_profile"]["sha256"],
            "compile_transform_profile_sha256": manifest["compile_transform_profile"]
            ["sha256"],
            "semantic_graph_digest": manifest["semantic_digest"]["value"],
            "graph": manifest["graph"],
            "duration_seconds": manifest["build_resource"]["duration_seconds"],
            "peak_process_rss_bytes": manifest["build_resource"][
                "peak_process_rss_bytes"
            ],
        }
        print(json.dumps(summary, sort_keys=True))
        return 0
    if args.command == "data" and args.data_command == "audit":
        command = ["flybench", *(argv if argv is not None else sys.argv[1:])]
        try:
            report = audit_graph(
                args.graph,
                args.out,
                command=command,
                write_companion_evidence=True,
            )
        except (OSError, GraphAuditError, KeyError, TypeError, ValueError) as exc:
            write_json(
                args.out,
                {
                    "schema": "flybench.graph-audit",
                    "version": 1,
                    "status": "FAIL",
                    "command": command,
                    "graph_directory": str(args.graph.resolve()),
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            print(f"graph audit failed: {exc}", file=sys.stderr)
            print(f"failure report: {args.out.resolve()}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "out": str(args.out.resolve()),
                    "semantic_graph_digest": report["semantic_graph_digest"],
                    "graph": report["graph"],
                },
                sort_keys=True,
            )
        )
        return 0
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
