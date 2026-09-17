"""Small FlyBench command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path

from flybench.bench import run_bench
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
    bench = commands.add_parser(
        "bench", help="Run the frozen M06 headless calibration and authority protocol"
    )
    bench.add_argument("profile", type=Path)
    bench.add_argument("--out", required=True, type=Path)
    bench.add_argument(
        "--record-dir",
        type=Path,
        help="run the selected accepted standard-looming trial with M09 recording",
    )
    demo = commands.add_parser(
        "demo", help="Run the M08 Catch the Fly demo on the loopback interface"
    )
    demo.add_argument("--profile", required=True, type=Path)
    demo.add_argument("--port", type=int, default=8000)
    demo.add_argument("--no-browser", action="store_true")
    demo.add_argument(
        "--record-dir",
        type=Path,
        help="write one bounded .flyrun for each completed local demo round",
    )
    record = commands.add_parser(
        "record", help="Write one bounded M09 authoritative .flyrun example"
    )
    record.add_argument("--profile", required=True, type=Path)
    record.add_argument("--out", required=True, type=Path)
    record.add_argument("--run-id", default="m09-representative-v1")
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
    if args.command == "bench":
        try:
            if args.record_dir is not None:
                from flybench.recording import run_selected_benchmark

                summary, result = run_selected_benchmark(
                    args.profile,
                    record_directory=args.record_dir,
                )
                assert result is not None
                print(
                    json.dumps(
                        {
                            "status": "PASS",
                            "scope": "M09 selected accepted standard-looming benchmark recording",
                            "path": str(
                                (args.record_dir / "looming-seed-0.flyrun").resolve()
                            ),
                            "bytes": len(result.archive_bytes),
                            "content_digest": result.content_digest,
                            "applied_input_sha256": result.applied_input_digest,
                            "final_whole_state_sha256": result.summary[
                                "final_whole_state_sha256"
                            ],
                            "essential_record_count": result.essential_record_count,
                            "optional_record_count": result.optional_record_count,
                            "optional_trace_status": result.optional_trace_status,
                            "dnp01_spike_count": summary["dnp01_spike_count"],
                            "escape_command_control_ticks": summary[
                                "escape_command_control_ticks"
                            ],
                        },
                        sort_keys=True,
                    )
                )
                return 0
            return run_bench(args.profile, args.out)
        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            print(f"M06 bench failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    if args.command == "demo":
        if not 1 <= args.port <= 65535:
            print("M08 demo failed: port must be between 1 and 65535", file=sys.stderr)
            return 1
        try:
            import uvicorn

            from flybench.game import build_live_session, load_live_profile
            from flybench.server import create_app

            resolved = load_live_profile(args.profile)
            frontend = resolved.root / "apps" / "web" / "dist"
            if not (frontend / "index.html").is_file():
                raise FileNotFoundError(
                    "built frontend is missing; run: npm --prefix apps/web run build"
                )
            # Fail before binding if the compact accepted graph is absent or invalid,
            # and warm the exact scored kernel signature once.
            preflight = build_live_session(resolved)
            preflight.advance_interval()
            app = create_app(
                resolved.path,
                frontend,
                record_directory=args.record_dir,
            )
        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            print(f"M08 demo failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        url = f"http://127.0.0.1:{args.port}/"
        print(f"FlyBench M08 local demo: {url}", flush=True)
        print("Bound to loopback only. Press Ctrl+C to stop.", flush=True)
        if args.record_dir is not None:
            print(
                f"Completed-round recordings: {args.record_dir.resolve()}",
                flush=True,
            )
        if not args.no_browser:
            threading.Timer(0.5, webbrowser.open, args=(url,)).start()
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
        return 0
    if args.command == "record":
        try:
            from flybench.recording import (
                load_flyrun,
                run_representative_recording,
                write_flyrun,
            )

            _subject, result = run_representative_recording(
                args.profile, run_id=args.run_id
            )
            write_flyrun(args.out, result)
            loaded = load_flyrun(args.out)
        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            print(f"M09 record failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "path": str(args.out.resolve()),
                    "bytes": loaded.archive_bytes,
                    "content_digest": loaded.content_digest,
                    "format_id": loaded.manifest["format_id"],
                    "schema_version": loaded.manifest["schema_version"],
                    "applied_input_sha256": result.applied_input_digest,
                    "final_whole_state_sha256": result.summary[
                        "final_whole_state_sha256"
                    ],
                    "essential_record_count": result.essential_record_count,
                    "optional_record_count": result.optional_record_count,
                    "optional_trace_status": result.optional_trace_status,
                    "authoritative_result": result.summary["authoritative_result"],
                    "m09_execution": "AT_RISK",
                    "m08_g_game": "PENDING_UNMEASURED",
                },
                sort_keys=True,
            )
        )
        return 0
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
