#!/usr/bin/env python3
"""Build deterministic M09 recorder evidence and a small representative flyrun."""

from __future__ import annotations

import argparse
import inspect
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any
import zipfile

from flybench.game import DemoProtocol, GameInputError
from flybench.recording import (
    FLYRUN_FORMAT_ID,
    FLYRUN_MEMBERS,
    FlyRunLimitError,
    FlyRunSafetyError,
    RecorderLimits,
    build_recorded_live_session,
    load_flyrun,
    run_representative_recording,
    write_flyrun,
)
import flybench.recording as recording_module


ROOT = Path(__file__).resolve().parents[1]
PROCESS_STATUS = {
    "decision": "D-M08-HUMAN-GATE-DEFER-01",
    "m09_execution": "AT_RISK",
    "m08_g_game": "PENDING_UNMEASURED",
    "m09_is_m08_usability_evidence": False,
    "public_release_blocked": True,
}
TARGETS = (
    (10.0, 10.0),
    (-10.0, 10.0),
    (10.0, -10.0),
    (-10.0, -10.0),
    (10.0, 10.0),
    (-10.0, 10.0),
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def complete_round(subject: Any, *, protocol: DemoProtocol | None = None) -> None:
    sequence = 0
    target_index = 0
    while subject.result is None:
        if subject.snapshot()["phase"] == "ready" and target_index < len(TARGETS):
            x, y = TARGETS[target_index]
            sequence += 1
            payload = {"type": "aim", "sequence": sequence, "x": x, "y": y}
            if protocol is None:
                subject.update_aim(x, y, sequence)
            else:
                protocol.handle(payload)
            sequence += 1
            payload = {"type": "attack", "sequence": sequence, "x": x, "y": y}
            if protocol is None:
                subject.commit_attack(x, y, sequence)
            else:
                protocol.handle(payload)
            target_index += 1
        if protocol is None:
            subject.advance_interval()
        else:
            protocol.advance()


def zip_bytes(entries: list[tuple[str, bytes, int]]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, payload, mode in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = mode << 16
            bundle.writestr(info, payload)
    return target.getvalue()


def safety_probe(path: Path, entries: list[tuple[str, bytes, int]]) -> bool:
    path.write_bytes(zip_bytes(entries))
    try:
        load_flyrun(path)
    except (FlyRunLimitError, FlyRunSafetyError):
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    profile = args.profile if args.profile.is_absolute() else ROOT / args.profile
    output = args.out if args.out.is_absolute() else ROOT / args.out
    output.mkdir(parents=True, exist_ok=True)

    _fixture_session, fixture = run_representative_recording(
        profile, run_id="m09-representative-v1"
    )
    fixture_path = output / "representative.flyrun"
    write_flyrun(fixture_path, fixture)
    loaded = load_flyrun(fixture_path)

    _first_session, first = run_representative_recording(
        profile, run_id="m09-determinism-v1"
    )
    _second_session, second = run_representative_recording(
        profile, run_id="m09-determinism-v1"
    )
    deterministic_checks = {
        "archive_bytes_identical": first.archive_bytes == second.archive_bytes,
        "content_digest_identical": first.content_digest == second.content_digest,
        "applied_input_digest_identical": first.applied_input_digest
        == second.applied_input_digest,
        "scientific_record_digest_identical": first.scientific_record_digest
        == second.scientific_record_digest,
    }
    write_json(
        output / "deterministic-recording.json",
        {
            "schema_version": 1,
            "status": "PASS" if all(deterministic_checks.values()) else "FAIL",
            "scope": "same accepted schedule, seeds, profile, run identity, and code identity",
            "checks": deterministic_checks,
            "content_digest": first.content_digest,
            "archive_bytes": len(first.archive_bytes),
            "process_status": PROCESS_STATUS,
        },
    )

    authority_left = build_recorded_live_session(
        profile, run_id="m09-authority-v1"
    )
    authority_right = build_recorded_live_session(
        profile, run_id="m09-authority-v1"
    )
    applied_before_rejection = tuple(authority_left.recorder.applied_input_events)
    rejected_code = None
    try:
        authority_left.update_aim(float("nan"), 0.0, 1)
    except GameInputError as exc:
        rejected_code = exc.code
    rejected_absent = (
        tuple(authority_left.recorder.applied_input_events) == applied_before_rejection
    )
    complete_round(authority_left)
    complete_round(authority_right)
    authority_first = authority_left.finalize()
    authority_second = authority_right.finalize()
    commits = [
        event
        for event in authority_left.recorder.essential_events
        if event["type"] == "attack_commit"
    ]
    impacts = [
        event
        for event in authority_left.recorder.essential_events
        if event["type"] == "impact"
    ]
    runner_summary = authority_left.runner.finish_run()
    recorded_spikes = [
        spike
        for event in authority_left.recorder.essential_events
        if event["type"] == "neural_output"
        for spike in event["dnp01_spikes"]
    ]
    recorded_sensory = [
        event["observation"]
        for event in authority_left.recorder.essential_events
        if event["type"] == "sensory_input"
    ]
    authority_checks = {
        "rejected_input_not_applied": rejected_absent,
        "rejected_diagnostic_bounded": rejected_code == "non_finite",
        "applied_digest_ignores_rejected_browser_intent": authority_first.applied_input_digest
        == authority_second.applied_input_digest,
        "scientific_record_ignores_rejected_browser_intent": authority_first.scientific_record_digest
        == authority_second.scientific_record_digest,
        "locked_targets_equal_authoritative_impacts": [
            commit["locked_target"] for commit in commits
        ]
        == [impact["locked_target"] for impact in impacts],
        "impact_ticks_equal_committed_ticks": [commit["impact_tick"] for commit in commits]
        == [impact["control_tick"] for impact in impacts],
        "dnp01_ticks_match_runner": recorded_spikes == runner_summary["dnp01_spikes"],
        "escape_ticks_match_runner": authority_first.summary[
            "decoded_escape_command_control_ticks"
        ]
        == runner_summary["escape_command_control_ticks"],
        "applied_sensory_stream_matches_runner": recorded_sensory
        == [
            interval["observation"]
            for interval in authority_left.runner.interval_records
        ],
    }
    write_json(
        output / "applied-input-authority.json",
        {
            "schema_version": 1,
            "status": "PASS" if all(authority_checks.values()) else "FAIL",
            "scope": "server-accepted and server-applied inputs only; browser timestamps and rejected intent excluded",
            "checks": authority_checks,
            "applied_input_sha256": authority_first.applied_input_digest,
            "applied_input_records": list(authority_left.recorder.applied_input_events),
            "rejected_input_diagnostics": authority_first.summary["recording"][
                "rejected_input_diagnostics"
            ],
            "process_status": PROCESS_STATUS,
        },
    )

    essential = build_recorded_live_session(
        profile,
        run_id="m09-essential-bound-v1",
        limits=RecorderLimits(maximum_essential_records=1),
    )
    complete_round(essential)
    essential_result = essential.finalize()
    optional = build_recorded_live_session(
        profile,
        run_id="m09-optional-bound-v1",
        limits=RecorderLimits(maximum_optional_records=1),
    )
    complete_round(optional)
    optional_result = optional.finalize()
    size_subject = build_recorded_live_session(
        profile,
        run_id="m09-size-bound-v1",
        limits=RecorderLimits(maximum_archive_bytes=100),
    )
    complete_round(size_subject)
    archive_size_enforced = False
    try:
        size_subject.finalize()
    except FlyRunLimitError:
        archive_size_enforced = True
    bounds_checks = {
        "current_round_duration_covered": loaded.manifest["limits"][
            "maximum_round_duration_ms"
        ]
        == 20_000,
        "current_attack_count_covered": loaded.manifest["limits"][
            "maximum_attacks"
        ]
        == 6,
        "essential_loss_explicit": essential_result.summary["recording"][
            "essential_status"
        ]
        == "INCOMPLETE"
        and essential_result.summary["recording"]["reexecution_certifiable"]
        is False,
        "optional_loss_has_gap_marker": optional_result.summary["recording"][
            "optional_status"
        ]
        == "TRUNCATED"
        and any(
            event["type"] == "recorder_gap"
            for event in optional.recorder.essential_events
        ),
        "archive_size_limit_enforced": archive_size_enforced,
        "representative_archive_within_limit": loaded.archive_bytes
        <= loaded.manifest["limits"]["maximum_archive_bytes"],
    }
    write_json(
        output / "bounds.json",
        {
            "schema_version": 1,
            "status": "PASS" if all(bounds_checks.values()) else "FAIL",
            "declared_limits": loaded.manifest["limits"],
            "representative_archive_bytes": loaded.archive_bytes,
            "representative_expanded_payload_bytes": sum(
                item["bytes"] for item in loaded.manifest["payloads"].values()
            ),
            "checks": bounds_checks,
            "process_status": PROCESS_STATUS,
        },
    )

    with tempfile.TemporaryDirectory(prefix="flybench-m09-safety-") as directory:
        temporary = Path(directory)
        safety_checks = {
            "path_traversal_rejected": safety_probe(
                temporary / "traversal.flyrun",
                [("../manifest.json", b"{}", stat.S_IFREG | 0o644)],
            ),
            "executable_member_rejected": safety_probe(
                temporary / "executable.flyrun",
                [("manifest.json", b"{}", stat.S_IFREG | 0o755)],
            ),
            "extra_code_member_rejected": safety_probe(
                temporary / "code.flyrun",
                [
                    ("manifest.json", b"{}", stat.S_IFREG | 0o644),
                    ("events.jsonl", b"", stat.S_IFREG | 0o644),
                    ("summary.json", b"{}", stat.S_IFREG | 0o644),
                    ("payload.py", b"raise SystemExit", stat.S_IFREG | 0o644),
                ],
            ),
            "nonfinite_json_rejected": safety_probe(
                temporary / "nonfinite.flyrun",
                [
                    (
                        "manifest.json",
                        b'{"format_id":"flybench.flyrun.v0.1","schema_version":1,"executable_content":false,"limits":NaN}\n',
                        stat.S_IFREG | 0o644,
                    ),
                    ("events.jsonl", b"", stat.S_IFREG | 0o644),
                    ("summary.json", b"{}\n", stat.S_IFREG | 0o644),
                ],
            ),
            "no_pickle_import_or_load": "import pickle"
            not in inspect.getsource(recording_module)
            and "pickle.loads" not in inspect.getsource(recording_module),
            "representative_inventory_exact": False,
        }
        with zipfile.ZipFile(fixture_path) as representative:
            safety_checks["representative_inventory_exact"] = (
                tuple(info.filename for info in representative.infolist())
                == FLYRUN_MEMBERS
            )
    write_json(
        output / "archive-safety.json",
        {
            "schema_version": 1,
            "status": "PASS" if all(safety_checks.values()) else "FAIL",
            "format": "standard ZIP containing canonical JSON/JSONL data only",
            "checks": safety_checks,
            "process_status": PROCESS_STATUS,
        },
    )

    headless = build_recorded_live_session(
        profile, run_id="m09-server-adapter-parity-v1"
    )
    adapted = build_recorded_live_session(
        profile, run_id="m09-server-adapter-parity-v1"
    )
    adapter = DemoProtocol(adapted)
    complete_round(headless)
    complete_round(adapted, protocol=adapter)
    headless_result = headless.finalize()
    adapted_result = adapted.finalize()
    parity_checks = {
        "authoritative_state": headless.snapshot() == adapted.snapshot(),
        "runner_summary": headless.runner.finish_run() == adapted.runner.finish_run(),
        "archive_bytes": headless_result.archive_bytes == adapted_result.archive_bytes,
        "content_digest": headless_result.content_digest
        == adapted_result.content_digest,
        "applied_input_digest": headless_result.applied_input_digest
        == adapted_result.applied_input_digest,
    }
    write_json(
        output / "headless-server-recorder-parity.json",
        {
            "schema_version": 1,
            "status": "PASS" if all(parity_checks.values()) else "FAIL",
            "scope": "direct headless calls versus DemoProtocol, the authoritative adapter used by the local /ws/demo server",
            "checks": parity_checks,
            "content_digest": headless_result.content_digest,
            "process_status": PROCESS_STATUS,
        },
    )

    event_types = sorted({event["type"] for event in loaded.events})
    write_json(
        output / "recorder-format.json",
        {
            "schema_version": 1,
            "status": "PASS",
            "format_id": FLYRUN_FORMAT_ID,
            "archive_members": list(FLYRUN_MEMBERS),
            "serialization": "UTF-8 canonical JSON/JSONL with sorted keys, finite numbers, fixed ZIP metadata and deterministic member order",
            "data_only": True,
            "event_types_in_representative_fixture": event_types,
            "provenance": loaded.manifest["provenance"],
            "payloads": loaded.manifest["payloads"],
            "content_digest": loaded.content_digest,
            "fixture_path": str(fixture_path.relative_to(ROOT)),
            "fixture_bytes": loaded.archive_bytes,
            "process_status": PROCESS_STATUS,
        },
    )

    reports = (
        "deterministic-recording.json",
        "applied-input-authority.json",
        "bounds.json",
        "archive-safety.json",
        "headless-server-recorder-parity.json",
        "recorder-format.json",
    )
    statuses = {
        name: json.loads((output / name).read_text(encoding="utf-8"))["status"]
        for name in reports
    }
    passed = all(status == "PASS" for status in statuses.values())
    print(
        json.dumps(
            {
                "status": "PASS" if passed else "FAIL",
                "out": str(output),
                "fixture": str(fixture_path),
                "fixture_bytes": loaded.archive_bytes,
                "content_digest": loaded.content_digest,
                "reports": statuses,
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
