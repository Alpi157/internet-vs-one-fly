#!/usr/bin/env python3
"""Validate and receipt one operator-created M09 demo recording after Phase A."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from flybench.recording import (
    FLYRUN_FORMAT_ID,
    STATE_DIGEST_INTERVALS,
    canonical_applied_input_sha256,
    load_flyrun,
)


ROOT = Path(__file__).resolve().parents[1]
PROCESS_STATUS = {
    "decision": "D-M08-HUMAN-GATE-DEFER-01",
    "m09_execution": "AT_RISK",
    "m08_g_game": "PENDING_UNMEASURED",
    "m09_is_m08_usability_evidence": False,
    "public_release_blocked": True,
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-dir", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    record_dir = (
        args.record_dir if args.record_dir.is_absolute() else ROOT / args.record_dir
    )
    output = args.out if args.out.is_absolute() else ROOT / args.out
    result: dict[str, object] = {
        "schema_version": 1,
        "status": "FAIL",
        "scope": "operator-created complete round through the actual local demo recording path; not M08 usability evidence",
        "candidate_product_sha": args.candidate,
        "process_status": PROCESS_STATUS,
    }
    try:
        if len(args.candidate) != 40 or any(
            character not in "0123456789abcdef" for character in args.candidate
        ):
            raise ValueError("candidate must be a lowercase 40-character Git SHA")
        paths = sorted(record_dir.glob("*.flyrun"))
        if len(paths) != 1:
            raise ValueError("operator record directory must contain exactly one .flyrun")
        path = paths[0]
        loaded = load_flyrun(path)
        state_events = [
            event for event in loaded.events if event["type"] == "state_digest"
        ]
        expected_ticks = [0]
        expected_ticks.extend(
            range(
                STATE_DIGEST_INTERVALS,
                loaded.summary["final_control_tick"],
                STATE_DIGEST_INTERVALS,
            )
        )
        if loaded.summary["final_control_tick"] not in expected_ticks:
            expected_ticks.append(loaded.summary["final_control_tick"])
        checks = {
            "format_v02": loaded.manifest.get("format_id") == FLYRUN_FORMAT_ID
            and loaded.manifest.get("schema_version") == 2,
            "actual_demo_execution_kind": loaded.manifest.get("run", {}).get(
                "execution_kind"
            )
            == "game-session",
            "exact_candidate_identity": loaded.manifest.get("provenance", {}).get(
                "code_git_sha"
            )
            == args.candidate,
            "completed_round": loaded.summary.get("authoritative_result")
            in {"caught", "fly-survived"},
            "applied_input_hash_valid": loaded.summary.get("applied_input_sha256")
            == canonical_applied_input_sha256(loaded.events),
            "state_digest_sequence_valid": [
                event["control_tick"] for event in state_events
            ]
            == expected_ticks,
            "final_whole_state_present": bool(
                loaded.summary.get("final_whole_state_sha256")
            )
            and loaded.summary.get("final_whole_state_sha256")
            == state_events[-1].get("whole_state_sha256"),
            "reexecution_not_verified": loaded.summary.get("reexecution", {}).get(
                "verified"
            )
            is False,
        }
        if not all(checks.values()):
            raise ValueError(f"operator demo validation failed: {checks}")
        archive = path.read_bytes()
        result.update(
            {
                "status": "PASS",
                "path": str(path.relative_to(ROOT)),
                "bytes": len(archive),
                "archive_sha256": hashlib.sha256(archive).hexdigest(),
                "content_digest": loaded.content_digest,
                "applied_input_sha256": loaded.summary["applied_input_sha256"],
                "final_whole_state_sha256": loaded.summary[
                    "final_whole_state_sha256"
                ],
                "essential_record_count": loaded.summary["recording"][
                    "essential_records"
                ],
                "optional_record_count": loaded.summary["recording"][
                    "optional_records"
                ],
                "optional_trace_status": loaded.summary["recording"][
                    "optional_status"
                ],
                "completion_status": loaded.summary["authoritative_result"],
                "state_digest_ticks": expected_ticks,
                "checks": checks,
            }
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    write_json(output, result)
    print(json.dumps({"status": result["status"], "out": str(output)}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
