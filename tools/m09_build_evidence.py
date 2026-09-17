#!/usr/bin/env python3
"""Build deterministic M09 attempt-2 evidence and reviewable flyrun fixtures."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import stat
from typing import Any
import zipfile

from flybench.game import DemoProtocol, GameInputError, build_live_session
from flybench.recording import (
    EVENT_ORDER_ID,
    FLYRUN_FORMAT_ID,
    FLYRUN_MEMBERS,
    FLYRUN_SCHEMA_VERSION,
    STATE_DIGEST_INTERVALS,
    FlyRunLimitError,
    FlyRunSafetyError,
    RecorderLimits,
    build_recorded_live_session,
    canonical_applied_input_records,
    load_flyrun,
    run_representative_recording,
    run_selected_benchmark,
    scientific_state_digest,
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
ATTEMPT_1 = {
    "candidate_product_sha": "067b3c831469ce2475201074ad47b39853694b60",
    "submission_sha": "d15bae9ccc6e8bf2952b5d14adaaaf06a86fd3dc",
    "review_zip_path": "reviews/M09-a01.zip",
    "review_zip_sha256": "cff7e065c6a45aade81e23614e0a00d7eb0ed379d5422531e68ba4f629f9ea66",
    "external_verdict": "CHANGES_REQUIRED",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def report(path: Path, *, checks: dict[str, bool], **values: object) -> None:
    write_json(
        path,
        {
            "schema_version": 2,
            "status": "PASS" if all(checks.values()) else "FAIL",
            **values,
            "checks": checks,
            "process_status": PROCESS_STATUS,
        },
    )


def complete_round(subject: Any, *, protocol: DemoProtocol | None = None) -> None:
    sequence = 0
    target_index = 0
    while subject.result is None:
        if subject.snapshot()["phase"] == "ready" and target_index < len(TARGETS):
            x, y = TARGETS[target_index]
            sequence += 1
            if protocol is None:
                subject.update_aim(x, y, sequence)
            else:
                protocol.handle(
                    {"type": "aim", "sequence": sequence, "x": x, "y": y}
                )
            sequence += 1
            if protocol is None:
                subject.commit_attack(x, y, sequence)
            else:
                protocol.handle(
                    {"type": "attack", "sequence": sequence, "x": x, "y": y}
                )
            target_index += 1
        if protocol is None:
            subject.advance_interval()
        else:
            protocol.advance()


def zip_bytes(entries: list[tuple[str, bytes, int]]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as bundle:
        for name, payload, mode in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = mode << 16
            bundle.writestr(info, payload)
    return target.getvalue()


def rejection(path: Path) -> str:
    try:
        load_flyrun(path)
    except (FlyRunLimitError, FlyRunSafetyError) as exc:
        return f"{type(exc).__name__}: {exc}"
    raise RuntimeError(f"malformed fixture unexpectedly loaded: {path}")


def artifact_metadata(path: Path) -> dict[str, Any]:
    loaded = load_flyrun(path)
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": loaded.archive_bytes,
        "archive_sha256": sha256_file(path),
        "content_digest": loaded.content_digest,
        "applied_input_sha256": loaded.summary["applied_input_sha256"],
        "final_whole_state_sha256": loaded.summary["final_whole_state_sha256"],
        "essential_record_count": loaded.summary["recording"]["essential_records"],
        "optional_record_count": loaded.summary["recording"]["optional_records"],
        "optional_trace_status": loaded.summary["recording"]["optional_status"],
        "completion_status": loaded.summary["authoritative_result"],
        "code_git_sha": loaded.manifest["provenance"]["code_git_sha"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    profile = args.profile if args.profile.is_absolute() else ROOT / args.profile
    output = args.out if args.out.is_absolute() else ROOT / args.out
    output.mkdir(parents=True, exist_ok=True)
    fixtures = output / "review-fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)

    fixture_session, fixture = run_representative_recording(
        profile, run_id="m09-representative-v2"
    )
    representative_path = output / "representative.flyrun"
    write_flyrun(representative_path, fixture)
    representative = load_flyrun(representative_path)

    first_session, first = run_representative_recording(
        profile, run_id="m09-determinism-v2"
    )
    second_session, second = run_representative_recording(
        profile, run_id="m09-determinism-v2"
    )
    deterministic_checks = {
        "archive_bytes_identical": first.archive_bytes == second.archive_bytes,
        "content_digest_identical": first.content_digest == second.content_digest,
        "applied_input_digest_identical": first.applied_input_digest
        == second.applied_input_digest,
        "scientific_record_digest_identical": first.scientific_record_digest
        == second.scientific_record_digest,
        "final_runner_state_identical": first_session.runner.finish_run()
        == second_session.runner.finish_run(),
    }
    report(
        output / "deterministic-recording.json",
        checks=deterministic_checks,
        scope="same applied schedule, seeds, profile, run identity, and code identity",
        artifact=artifact_metadata(representative_path),
    )

    authority_left = build_recorded_live_session(
        profile, run_id="m09-authority-v2"
    )
    authority_right = build_recorded_live_session(
        profile, run_id="m09-authority-v2"
    )
    before_rejection = tuple(authority_left.recorder.applied_input_events)
    rejected_code = None
    try:
        authority_left.update_aim(float("nan"), 0.0, 1)
    except GameInputError as exc:
        rejected_code = exc.code
    rejected_absent = (
        tuple(authority_left.recorder.applied_input_events) == before_rejection
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
    authority_checks = {
        "rejected_input_not_applied": rejected_absent,
        "rejected_diagnostic_bounded": rejected_code == "non_finite",
        "applied_hash_ignores_rejected_browser_intent": authority_first.applied_input_digest
        == authority_second.applied_input_digest,
        "scientific_record_ignores_rejected_browser_intent": authority_first.scientific_record_digest
        == authority_second.scientific_record_digest,
        "locked_targets_equal_authoritative_impacts": [
            commit["locked_target"] for commit in commits
        ]
        == [impact["locked_target"] for impact in impacts],
        "impact_ticks_equal_committed_ticks": [
            commit["impact_tick"] for commit in commits
        ]
        == [impact["control_tick"] for impact in impacts],
        "dnp01_ticks_match_runner": recorded_spikes
        == runner_summary["dnp01_spikes"],
        "escape_ticks_match_runner": authority_first.summary[
            "decoded_escape_command_control_ticks"
        ]
        == runner_summary["escape_command_control_ticks"],
        "manifest_summary_applied_hash_agree": authority_first.manifest["run"][
            "applied_input_sha256"
        ]
        == authority_first.manifest["integrity"]["applied_input_sha256"]
        == authority_first.summary["applied_input_sha256"],
    }
    report(
        output / "applied-input-authority.json",
        checks=authority_checks,
        scope="only server-applied aim/commit values at authoritative logical ticks",
        applied_input_sha256=authority_first.applied_input_digest,
        applied_input_records=list(
            canonical_applied_input_records(authority_left.recorder.essential_events)
        ),
        rejected_input_diagnostics=authority_first.summary["recording"][
            "rejected_input_diagnostics"
        ],
    )

    state_events = [
        event for event in representative.events if event["type"] == "state_digest"
    ]
    expected_ticks = [0]
    expected_ticks.extend(
        range(
            STATE_DIGEST_INTERVALS,
            representative.summary["final_control_tick"],
            STATE_DIGEST_INTERVALS,
        )
    )
    if representative.summary["final_control_tick"] not in expected_ticks:
        expected_ticks.append(representative.summary["final_control_tick"])
    write_json(
        output / "state-digest-policy.json",
        {
            "schema_version": 2,
            "status": "PASS",
            "boundary": "initial before authoritative inputs; then after each completed control interval and every GameSession update at that boundary",
            "cadence_control_intervals": STATE_DIGEST_INTERVALS,
            "required_ticks_rule": "0, each positive multiple of 100 below final, and final (including periodic-final when final is a multiple of 100)",
            "canonical_encoding": "component-specific domain separator plus UTF-8 canonical JSON and explicit contiguous ndarray dtype/shape/raw-C-order bytes; whole digest binds component digests and Runner context",
            "components": {
                "neural": [
                    "tick",
                    "seed",
                    "RNG state",
                    "voltage",
                    "synaptic current",
                    "refractory-until",
                    "pending spike ring",
                    "pending input ring",
                ],
                "environment": [
                    "position",
                    "heading",
                    "control tick",
                    "takeoff state",
                    "pending/resolved impacts",
                    "seed",
                    "RNG state",
                ],
                "runner": [
                    "control tick",
                    "held command",
                    "backend",
                    "output clamp",
                    "intervention identity",
                ],
                "game": [
                    "aim/pending aim/last sequence",
                    "active locked strike",
                    "cooldown",
                    "attack count",
                    "round horizon",
                    "result/termination",
                    "last impact/motion",
                ],
            },
            "process_status": PROCESS_STATUS,
        },
    )
    same_subject = build_live_session(profile)
    same_left = scientific_state_digest(
        same_subject.runner, game_session=same_subject
    )
    same_right = scientific_state_digest(
        same_subject.runner, game_session=same_subject
    )
    neural_subject = build_live_session(profile)
    neural_before = scientific_state_digest(
        neural_subject.runner, game_session=neural_subject
    )
    neural_subject.runner.neural.voltage[0] += 0.125
    neural_after = scientific_state_digest(
        neural_subject.runner, game_session=neural_subject
    )
    pending_subject = build_live_session(profile)
    pending_before = scientific_state_digest(
        pending_subject.runner, game_session=pending_subject
    )
    pending_subject.runner.neural.pending_inputs[0, 0] = 0.25
    pending_subject.runner.neural.pending_spikes[0, 1] = True
    pending_after = scientific_state_digest(
        pending_subject.runner, game_session=pending_subject
    )
    environment_subject = build_live_session(profile)
    environment_before = scientific_state_digest(
        environment_subject.runner, game_session=environment_subject
    )
    environment_subject.runner.environment.rng.uniform()
    environment_after = scientific_state_digest(
        environment_subject.runner, game_session=environment_subject
    )
    command_subject = build_live_session(profile)
    command_before = scientific_state_digest(
        command_subject.runner, game_session=command_subject
    )
    command_subject.runner.held_command = True
    command_after = scientific_state_digest(
        command_subject.runner, game_session=command_subject
    )
    strike_subject = build_live_session(profile)
    strike_before = scientific_state_digest(
        strike_subject.runner, game_session=strike_subject
    )
    strike_subject.commit_attack(2.5, -1.5, 1)
    strike_after = scientific_state_digest(
        strike_subject.runner, game_session=strike_subject
    )
    actual_final = scientific_state_digest(
        fixture_session.runner, game_session=fixture_session.session
    )
    state_checks = {
        "initial_periodic_final_cadence": [
            event["control_tick"] for event in state_events
        ]
        == expected_ticks,
        "same_state_same_digests": same_left == same_right,
        "neural_change_changes_component_and_whole": neural_before[
            "neural_state_sha256"
        ]
        != neural_after["neural_state_sha256"]
        and neural_before["whole_state_sha256"]
        != neural_after["whole_state_sha256"],
        "pending_neural_change_changes_component_and_whole": pending_before[
            "neural_state_sha256"
        ]
        != pending_after["neural_state_sha256"]
        and pending_before["whole_state_sha256"]
        != pending_after["whole_state_sha256"],
        "environment_rng_change_changes_component_and_whole": environment_before[
            "environment_state_sha256"
        ]
        != environment_after["environment_state_sha256"]
        and environment_before["whole_state_sha256"]
        != environment_after["whole_state_sha256"],
        "held_command_changes_whole": command_before["whole_state_sha256"]
        != command_after["whole_state_sha256"],
        "pending_strike_changes_game_and_whole": strike_before[
            "game_state_sha256"
        ]
        != strike_after["game_state_sha256"]
        and strike_before["whole_state_sha256"]
        != strike_after["whole_state_sha256"],
        "final_digest_matches_actual_state": actual_final["whole_state_sha256"]
        == state_events[-1]["whole_state_sha256"]
        == representative.summary["final_whole_state_sha256"],
        "m10_verification_not_claimed": representative.summary["reexecution"]
        == {
            "capture_envelope_complete": True,
            "verified": False,
            "verification_milestone": "M10",
        },
    }
    report(
        output / "state-digest-validation.json",
        checks=state_checks,
        observed_ticks=[event["control_tick"] for event in state_events],
        expected_ticks=expected_ticks,
        initial=state_events[0],
        final=state_events[-1],
    )

    coalescing = build_recorded_live_session(
        profile, run_id="m09-coalescing-v2"
    )
    coalescing.update_aim(-4.0, 3.0, 1)
    coalescing.update_aim(1.5, -2.25, 4)
    coalescing.update_aim(8.0, 9.0, 7)
    before_application = tuple(coalescing.recorder.applied_input_events)
    rejected_sequences: list[str] = []
    for sequence in (7, 6, 7.0, True):
        try:
            coalescing.update_aim(2.0, 2.0, sequence)
        except GameInputError as exc:
            rejected_sequences.append(exc.code)
    coalescing.advance_interval()
    coalesced_applied = list(coalescing.recorder.applied_input_events)
    coalescing_checks = {
        "nothing_applied_before_boundary": before_application == (),
        "one_latest_aim_applied": len(coalesced_applied) == 1
        and coalesced_applied[0]["sequence"] == 7
        and coalesced_applied[0]["aim"] == {"x": 8.0, "y": 9.0},
        "earlier_valid_aims_counted_as_coalesced": coalescing.session.coalesced_aim_updates
        == 2,
        "duplicate_stale_malformed_rejected": rejected_sequences
        == ["stale_sequence", "stale_sequence", "malformed", "malformed"],
        "rejections_not_applied": len(coalesced_applied) == 1,
    }
    report(
        output / "input-coalescing.json",
        checks=coalescing_checks,
        policy="greatest accepted monotonically increasing sequence pending at an authoritative boundary wins; only that applied aim enters the scientific input stream",
        applied_records=list(canonical_applied_input_records(coalesced_applied)),
        rejected_diagnostics=coalescing.recorder.rejected_diagnostics,
    )

    ordering = build_recorded_live_session(profile, run_id="m09-ordering-v2")
    ordering.update_aim(-8.0, 7.0, 1)
    ordering.update_aim(-2.0, 4.0, 2)
    attack_ack = ordering.commit_attack(2.25, -3.5, 3)
    ordering.update_aim(9.0, 9.0, 4)
    ordering.advance_interval()
    ordering_applied = list(ordering.recorder.applied_input_events)
    ordering_checks = {
        "same_tick_pending_aim_precedes_commit": [
            event["type"] for event in ordering_applied[:2]
        ]
        == ["accepted_aim", "attack_commit"],
        "same_tick_pending_aim_is_latest_sequence": ordering_applied[0]["sequence"]
        == 2,
        "commit_uses_own_exact_coordinates": ordering_applied[1]["locked_target"]
        == attack_ack["locked_target"]
        == {"x": 2.25, "y": -3.5},
        "later_aim_does_not_move_lock": ordering.snapshot()["strike"][
            "locked_target"
        ]
        == {"x": 2.25, "y": -3.5},
        "ordinals_monotonic": [
            event["event_ordinal"] for event in ordering.recorder.essential_events
        ]
        == sorted(
            event["event_ordinal"]
            for event in ordering.recorder.essential_events
        ),
        "archive_event_ordering_explicit": representative.manifest[
            "event_ordering"
        ]["identity"]
        == EVENT_ORDER_ID,
    }
    report(
        output / "input-ordering.json",
        checks=ordering_checks,
        event_ordering=representative.manifest["event_ordering"],
        applied_records=list(canonical_applied_input_records(ordering_applied)),
    )

    coordinate_decision_path = ROOT / "decisions/D-M09-COORDINATE-APPLICATION-01.json"
    coordinate_decision = json.loads(coordinate_decision_path.read_text(encoding="utf-8"))
    coordinate_subject = build_recorded_live_session(
        profile, run_id="m09-coordinate-v2"
    )
    x_value = 0.12345678901234566
    y_value = -0.9876543210123456
    coordinate_subject.update_aim(x_value, y_value, 1)
    coordinate_subject.advance_interval()
    coordinate_event = coordinate_subject.recorder.applied_input_events[0]
    coordinate_checks = {
        "decision_present": coordinate_decision.get("decision_id")
        == "D-M09-COORDINATE-APPLICATION-01",
        "no_arbitrary_quantum_added": coordinate_decision.get("decision", {}).get(
            "quantization_added"
        )
        is False,
        "recorder_x_equals_session_x": coordinate_event["aim"]["x"]
        == coordinate_subject.session.latest_aim[0]
        == x_value,
        "recorder_y_equals_session_y": coordinate_event["aim"]["y"]
        == coordinate_subject.session.latest_aim[1]
        == y_value,
    }
    report(
        output / "coordinate-application.json",
        checks=coordinate_checks,
        decision_path="decisions/D-M09-COORDINATE-APPLICATION-01.json",
        decision_sha256=sha256_file(coordinate_decision_path),
        architecture_finding=coordinate_decision["architecture_finding"],
        authoritative_value=coordinate_decision["decision"]["authoritative_value"],
        applied_example=coordinate_event,
    )

    stimulus = ROOT / "profiles/looming-controls.json"
    plain_bench, no_recording = run_selected_benchmark(stimulus)
    recorded_bench, bench_result = run_selected_benchmark(
        stimulus, record_directory=output
    )
    assert bench_result is not None
    looming_path = output / "looming-seed-0.flyrun"
    looming = load_flyrun(looming_path)
    bench_checks = {
        "disabled_has_no_recorder": no_recording is None,
        "enabled_vs_disabled_summary_identical": plain_bench == recorded_bench,
        "neural_response_identical": plain_bench["dnp01_spikes"]
        == looming.summary["dnp01_spikes"],
        "command_ticks_identical": plain_bench["escape_command_control_ticks"]
        == looming.summary["decoded_escape_command_control_ticks"],
        "impact_identical": plain_bench["impacts"]
        == [
            {
                "control_tick": event["control_tick"],
                "outcome": event["outcome"],
                "takeoff_was_active": event["takeoff_was_active"],
            }
            for event in looming.events
            if event["type"] == "impact"
        ],
        "fixture_is_standard_looming_seed_index_zero": looming.manifest["run"][
            "execution_context"
        ]["scenario"]
        == "standard looming"
        and looming.manifest["run"]["execution_context"]["seed_index"] == 0,
    }
    report(
        output / "bench-recording.json",
        checks=bench_checks,
        command=[
            "uv",
            "run",
            "flybench",
            "bench",
            "profiles/looming-controls.json",
            "--out",
            "evidence/M09/bench-unused",
            "--record-dir",
            "evidence/M09",
        ],
        scenario="existing accepted standard looming",
        artifact=artifact_metadata(looming_path),
    )

    headless = build_recorded_live_session(
        profile, run_id="m09-server-adapter-parity-v2"
    )
    adapted = build_recorded_live_session(
        profile, run_id="m09-server-adapter-parity-v2"
    )
    adapter = DemoProtocol(adapted)
    complete_round(headless)
    complete_round(adapted, protocol=adapter)
    headless_result = headless.finalize()
    adapted_result = adapted.finalize()
    plain_game = build_live_session(profile)
    complete_round(plain_game)
    parity_checks = {
        "headless_vs_protocol_authoritative_state": headless.snapshot()
        == adapted.snapshot(),
        "headless_vs_protocol_runner_summary": headless.runner.finish_run()
        == adapted.runner.finish_run(),
        "headless_vs_protocol_archive_bytes": headless_result.archive_bytes
        == adapted_result.archive_bytes,
        "recorded_vs_unrecorded_game_state": headless.snapshot()
        == plain_game.snapshot(),
        "recorded_vs_unrecorded_runner_state": headless.runner.finish_run()
        == plain_game.runner.finish_run(),
    }
    report(
        output / "headless-server-recorder-parity.json",
        checks=parity_checks,
        scope="direct headless calls, DemoProtocol authoritative adapter, and unrecorded GameSession",
        content_digest=headless_result.content_digest,
        applied_input_sha256=headless_result.applied_input_digest,
    )

    essential = build_recorded_live_session(
        profile,
        run_id="m09-essential-bound-v2",
        limits=RecorderLimits(maximum_essential_records=1),
    )
    complete_round(essential)
    essential_result = essential.finalize()
    optional = build_recorded_live_session(
        profile,
        run_id="m09-optional-bound-v2",
        limits=RecorderLimits(maximum_optional_records=1),
    )
    complete_round(optional)
    optional_result = optional.finalize()
    truncated_path = fixtures / "valid-optional-truncated.flyrun"
    write_flyrun(truncated_path, optional_result)
    truncated = load_flyrun(truncated_path)
    size_subject = build_recorded_live_session(
        profile,
        run_id="m09-size-bound-v2",
        limits=RecorderLimits(maximum_archive_bytes=100),
    )
    complete_round(size_subject)
    archive_size_enforced = False
    try:
        size_subject.finalize()
    except FlyRunLimitError:
        archive_size_enforced = True
    gaps = [event for event in truncated.events if event["type"] == "recorder_gap"]
    bounds_checks = {
        "current_round_duration_covered": representative.manifest["limits"][
            "maximum_round_duration_ms"
        ]
        == 20_000,
        "current_attack_count_covered": representative.manifest["limits"][
            "maximum_attacks"
        ]
        == 6,
        "essential_loss_explicit": essential_result.summary["recording"][
            "essential_status"
        ]
        == "INCOMPLETE"
        and essential_result.summary["reexecution"]["capture_envelope_complete"]
        is False,
        "optional_loss_has_gap_marker": truncated.summary["recording"][
            "optional_status"
        ]
        == "TRUNCATED"
        and len(gaps) == 1,
        "required_state_digests_are_essential": all(
            event["recording_class"] == "essential" for event in state_events
        ),
        "archive_size_limit_enforced": archive_size_enforced,
        "representative_archive_within_limit": representative.archive_bytes
        <= representative.manifest["limits"]["maximum_archive_bytes"],
    }
    report(
        output / "bounds.json",
        checks=bounds_checks,
        declared_limits=representative.manifest["limits"],
        representative=artifact_metadata(representative_path),
        optional_truncated=artifact_metadata(truncated_path),
        gap_marker=gaps[0],
    )

    valid_complete = fixtures / "valid-complete.flyrun"
    valid_complete.write_bytes(representative_path.read_bytes())
    with zipfile.ZipFile(io.BytesIO(fixture.archive_bytes)) as bundle:
        valid_manifest = json.loads(bundle.read("manifest.json"))
        valid_events = bundle.read("events.jsonl")
        valid_summary = bundle.read("summary.json")
    traversal_path = fixtures / "malformed-path-traversal.flyrun"
    traversal_path.write_bytes(
        zip_bytes([("../manifest.json", b"{}\n", stat.S_IFREG | 0o644)])
    )
    executable_path = fixtures / "malformed-executable-member.flyrun"
    executable_path.write_bytes(
        zip_bytes(
            [
                ("manifest.json", b"{}\n", stat.S_IFREG | 0o644),
                ("events.jsonl", b"", stat.S_IFREG | 0o644),
                ("payload.py", b"raise SystemExit\n", stat.S_IFREG | 0o755),
            ]
        )
    )
    integrity_path = fixtures / "malformed-integrity.flyrun"
    valid_manifest["run"]["applied_input_sha256"] = "0" * 64
    integrity_path.write_bytes(
        zip_bytes(
            [
                (
                    "manifest.json",
                    (
                        json.dumps(
                            valid_manifest,
                            allow_nan=False,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                        + "\n"
                    ).encode("utf-8"),
                    stat.S_IFREG | 0o644,
                ),
                ("events.jsonl", valid_events, stat.S_IFREG | 0o644),
                ("summary.json", valid_summary, stat.S_IFREG | 0o644),
            ]
        )
    )
    malformed_rejections = {
        "malformed-path-traversal.flyrun": rejection(traversal_path),
        "malformed-executable-member.flyrun": rejection(executable_path),
        "malformed-integrity.flyrun": rejection(integrity_path),
    }
    safety_checks = {
        "valid_complete_loads": load_flyrun(valid_complete).manifest["format_id"]
        == FLYRUN_FORMAT_ID,
        "valid_optional_truncated_loads": truncated.summary["recording"][
            "optional_status"
        ]
        == "TRUNCATED",
        "path_traversal_rejected": "unsafe flyrun member path"
        in malformed_rejections["malformed-path-traversal.flyrun"],
        "executable_code_member_rejected": "executable or linked"
        in malformed_rejections["malformed-executable-member.flyrun"],
        "integrity_mismatch_rejected": "applied-input identity mismatch"
        in malformed_rejections["malformed-integrity.flyrun"],
        "no_pickle_or_dynamic_execution": "import pickle"
        not in inspect.getsource(recording_module)
        and "pickle.loads" not in inspect.getsource(recording_module)
        and "eval(" not in inspect.getsource(recording_module)
        and "exec(" not in inspect.getsource(recording_module),
        "member_allowlist_exact": tuple(FLYRUN_MEMBERS)
        == ("manifest.json", "events.jsonl", "summary.json"),
    }
    report(
        output / "archive-safety.json",
        checks=safety_checks,
        format="fixed-inventory ZIP containing canonical JSON/JSONL data only",
        valid_fixtures={
            "valid-complete.flyrun": artifact_metadata(valid_complete),
            "valid-optional-truncated.flyrun": artifact_metadata(truncated_path),
        },
        malformed_fixtures={
            name: {
                "path": f"evidence/M09/review-fixtures/{name}",
                "bytes": (fixtures / name).stat().st_size,
                "archive_sha256": sha256_file(fixtures / name),
                "expected_rejection": message,
            }
            for name, message in malformed_rejections.items()
        },
    )

    periodic_examples = [
        event for event in state_events if event["digest_kind"] == "periodic"
    ][:2]
    representative_inputs = [
        event
        for event in representative.events
        if event["type"] in {"accepted_aim", "attack_commit", "impact"}
    ][:5]
    excerpts = {
        "manifest_identity": {
            "format_id": representative.manifest["format_id"],
            "schema_version": representative.manifest["schema_version"],
            "run": representative.manifest["run"],
            "provenance": representative.manifest["provenance"],
        },
        "applied_input_sha256": representative.summary["applied_input_sha256"],
        "initial_state_digest": state_events[0],
        "periodic_state_digest_examples": periodic_examples,
        "final_state_digest": state_events[-1],
        "representative_applied_and_impact_events": representative_inputs,
        "optional_truncation_gap_marker": gaps[0],
        "reexecution": representative.summary["reexecution"],
    }
    (output / "fixture-excerpts.md").write_text(
        "# M09 attempt-2 fixture excerpts\n\n"
        "These bounded excerpts make the capture envelope inspectable without treating "
        "M09 as re-execution verification. M10 owns verification.\n\n"
        "```json\n"
        + json.dumps(excerpts, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )

    demo_smoke_path = output / "demo-recording-smoke.json"
    demo_smoke = json.loads(demo_smoke_path.read_text(encoding="utf-8"))
    if demo_smoke.get("status") != "PASS" or demo_smoke.get(
        "process_status"
    ) != PROCESS_STATUS:
        raise RuntimeError("bounded demo recording smoke evidence is absent or failing")

    event_types = sorted({event["type"] for event in representative.events})
    format_checks = {
        "format_v02": representative.manifest["format_id"]
        == "flybench.flyrun.v0.2",
        "schema_version_2": representative.manifest["schema_version"] == 2,
        "fixed_member_inventory": tuple(FLYRUN_MEMBERS)
        == ("manifest.json", "events.jsonl", "summary.json"),
        "applied_hash_in_manifest": representative.manifest["run"][
            "applied_input_sha256"
        ]
        == representative.summary["applied_input_sha256"],
        "capture_complete_not_verified": representative.summary["reexecution"]
        == {
            "capture_envelope_complete": True,
            "verified": False,
            "verification_milestone": "M10",
        },
    }
    report(
        output / "recorder-format.json",
        checks=format_checks,
        format_id=FLYRUN_FORMAT_ID,
        flyrun_schema_version=FLYRUN_SCHEMA_VERSION,
        archive_members=list(FLYRUN_MEMBERS),
        serialization="UTF-8 canonical finite JSON/JSONL, fixed ZIP metadata and deterministic member order",
        data_only=True,
        event_types_in_representative_fixture=event_types,
        provenance=representative.manifest["provenance"],
        payloads=representative.manifest["payloads"],
        fixture_path=str(representative_path.relative_to(ROOT)),
        fixture_bytes=representative.archive_bytes,
        content_digest=representative.content_digest,
        artifact=artifact_metadata(representative_path),
    )

    write_json(
        output / "attempt-1-superseded.json",
        {
            "schema_version": 1,
            "status": "SUPERSEDED_CHANGES_REQUIRED",
            **ATTEMPT_1,
            "interpretation": "M09-a01 was an incomplete M09 implementation/review submission; this does not characterize its recorded science as invalid.",
            "reason_categories_addressed_by_attempt_2": [
                "recorder integration with demo, bench, and headless execution",
                "periodic/final whole scientific-state digest envelope",
                "authoritative input coalescing and deterministic ordering",
                "directly inspectable valid-truncated and malformed fixtures",
            ],
            "process_status": PROCESS_STATUS,
        },
    )

    required_reports = (
        "recorder-format.json",
        "deterministic-recording.json",
        "applied-input-authority.json",
        "state-digest-policy.json",
        "state-digest-validation.json",
        "bounds.json",
        "archive-safety.json",
        "input-coalescing.json",
        "input-ordering.json",
        "coordinate-application.json",
        "bench-recording.json",
        "demo-recording-smoke.json",
        "headless-server-recorder-parity.json",
    )
    statuses = {
        name: json.loads((output / name).read_text(encoding="utf-8"))["status"]
        for name in required_reports
    }
    passed = all(status == "PASS" for status in statuses.values())
    print(
        json.dumps(
            {
                "status": "PASS" if passed else "FAIL",
                "out": str(output),
                "representative": artifact_metadata(representative_path),
                "looming_seed_0": artifact_metadata(looming_path),
                "reports": statuses,
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
