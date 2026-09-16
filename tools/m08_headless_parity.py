#!/usr/bin/env python3
"""Produce deterministic M08 headless/WebSocket-adapter parity evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from flybench.game import DemoProtocol, build_live_session, load_live_profile


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    profile_path = args.profile if args.profile.is_absolute() else ROOT / args.profile
    output = args.out if args.out.is_absolute() else ROOT / args.out
    resolved = load_live_profile(profile_path)
    direct = build_live_session(resolved)
    adapted = build_live_session(resolved)
    direct.update_aim(10.0, 10.0, 1)
    direct.commit_attack(10.0, 10.0, 2)
    adapter = DemoProtocol(adapted)
    acknowledgements = [
        adapter.handle({"type": "aim", "sequence": 1, "x": 10.0, "y": 10.0}),
        adapter.handle({"type": "attack", "sequence": 2, "x": 10.0, "y": 10.0}),
    ]
    for _ in range(resolved.game_spec.impact_ticks):
        direct.advance_interval()
        adapter.advance()
    direct_state = direct.snapshot()
    adapted_state = adapted.snapshot()
    direct_summary = direct.runner.finish_run()
    adapted_summary = adapted.runner.finish_run()
    comparisons = {
        "authoritative_state": direct_state == adapted_state,
        "impact": direct_state["last_impact"] == adapted_state["last_impact"],
        "neural_state_sha256": direct_summary["final_neural_state_sha256"]
        == adapted_summary["final_neural_state_sha256"],
        "escape_command_ticks": direct_summary["escape_command_control_ticks"]
        == adapted_summary["escape_command_control_ticks"],
        "backend_kernel": direct_state["backend"] == adapted_state["backend"] == "kernel",
    }
    report = {
        "schema_version": 1,
        "status": "PASS" if all(comparisons.values()) else "FAIL",
        "scope": "same deterministic accepted input schedule through the direct session and the DemoProtocol used by /ws/demo",
        "live_profile_sha256": resolved.sha256,
        "game_spec_sha256": resolved.game_spec_sha256,
        "accepted_input_schedule": [
            {"server_tick": 0, "type": "aim", "sequence": 1, "x": 10.0, "y": 10.0},
            {"server_tick": 0, "type": "attack", "sequence": 2, "x": 10.0, "y": 10.0},
        ],
        "adapter_acknowledgements": acknowledgements,
        "intervals_advanced": resolved.game_spec.impact_ticks,
        "comparisons": comparisons,
        "authoritative_outcome": direct_state["last_impact"],
        "final_neural_state_sha256": direct_summary["final_neural_state_sha256"],
    }
    write_json(output, report)
    print(json.dumps({"status": report["status"], "out": str(output)}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
