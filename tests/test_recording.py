from __future__ import annotations

import inspect
import io
import hashlib
import json
import math
from pathlib import Path
import stat
import zipfile

import numpy as np
import pytest

from flybench.game import DemoProtocol, GameInputError, build_live_session, load_live_profile
from flybench.recording import (
    ARCHITECTURE_SHA256,
    FLYRUN_FORMAT_ID,
    FLYRUN_MEMBERS,
    MAX_ARCHIVE_BYTES,
    MAX_EXPANDED_BYTES,
    FlyRunLimitError,
    FlyRunRecorder,
    FlyRunSafetyError,
    RecordedGameSession,
    RecorderLimits,
    build_recorded_live_session,
    canonical_applied_input_records,
    canonical_applied_input_sha256,
    load_flyrun,
    run_representative_recording,
    run_selected_benchmark,
    scientific_state_digest,
    write_flyrun,
)
import flybench.recording as recording_module


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "profiles/live.json"
FIXED_CODE_SHA = "1" * 40
TARGETS = (
    (10.0, 10.0),
    (-10.0, 10.0),
    (10.0, -10.0),
    (-10.0, -10.0),
    (10.0, 10.0),
    (-10.0, 10.0),
)


def complete_round(subject: object, *, via_protocol: bool = False) -> None:
    protocol = DemoProtocol(subject) if via_protocol else None  # type: ignore[arg-type]
    sequence = 0
    target_index = 0
    while subject.result is None:  # type: ignore[attr-defined]
        state = subject.snapshot()  # type: ignore[attr-defined]
        if state["phase"] == "ready" and target_index < len(TARGETS):
            x, y = TARGETS[target_index]
            sequence += 1
            if protocol is None:
                subject.update_aim(x, y, sequence)  # type: ignore[attr-defined]
            else:
                protocol.handle(
                    {"type": "aim", "sequence": sequence, "x": x, "y": y}
                )
            sequence += 1
            if protocol is None:
                subject.commit_attack(x, y, sequence)  # type: ignore[attr-defined]
            else:
                protocol.handle(
                    {"type": "attack", "sequence": sequence, "x": x, "y": y}
                )
            target_index += 1
        if protocol is None:
            subject.advance_interval()  # type: ignore[attr-defined]
        else:
            protocol.advance()


def recorded(
    run_id: str,
    *,
    limits: RecorderLimits | None = None,
) -> RecordedGameSession:
    return build_recorded_live_session(
        LIVE,
        run_id=run_id,
        limits=limits,
        code_git_sha=FIXED_CODE_SHA,
    )


def test_same_schedule_and_seeds_are_byte_identical() -> None:
    _left_session, left = run_representative_recording(
        LIVE, run_id="determinism-v1", code_git_sha=FIXED_CODE_SHA
    )
    _right_session, right = run_representative_recording(
        LIVE, run_id="determinism-v1", code_git_sha=FIXED_CODE_SHA
    )
    assert left.archive_bytes == right.archive_bytes
    assert left.content_digest == right.content_digest
    assert left.applied_input_digest == right.applied_input_digest
    assert left.scientific_record_digest == right.scientific_record_digest


def test_browser_intent_differences_do_not_change_applied_scientific_record() -> None:
    left = recorded("intent-authority-v1")
    right = recorded("intent-authority-v1")
    with pytest.raises(GameInputError):
        left.update_aim(math.nan, 0.0, 1)
    complete_round(left)
    complete_round(right)
    left_result = left.finalize()
    right_result = right.finalize()
    assert left_result.applied_input_digest == right_result.applied_input_digest
    assert left_result.scientific_record_digest == right_result.scientific_record_digest
    assert left_result.summary["authoritative_result"] == right_result.summary[
        "authoritative_result"
    ]
    assert left_result.summary["recording"]["rejected_input_diagnostics"] == {
        "non_finite": 1
    }
    assert right_result.summary["recording"]["rejected_input_diagnostics"] == {}


def test_rejected_input_is_not_an_applied_input_record() -> None:
    subject = recorded("rejection-v1")
    before = subject.recorder.applied_input_events
    with pytest.raises(GameInputError):
        subject.commit_attack(11.0, 0.0, 1)
    assert subject.recorder.applied_input_events == before
    assert subject.recorder.rejected_diagnostics == {"out_of_arena": 1}


def test_locked_strike_record_is_the_authoritative_server_value() -> None:
    subject = recorded("locked-v1")
    acknowledgement = subject.commit_attack(2.25, -3.5, 1)
    subject.update_aim(9.0, 9.0, 2)
    commit = next(
        event
        for event in subject.recorder.essential_events
        if event["type"] == "attack_commit"
    )
    assert commit["locked_target"] == acknowledgement["locked_target"] == {
        "x": 2.25,
        "y": -3.5,
    }
    assert subject.snapshot()["strike"]["locked_target"] == commit["locked_target"]


def test_impact_tick_and_outcome_match_actual_execution() -> None:
    subject = recorded("impact-v1")
    acknowledgement = subject.commit_attack(10.0, 10.0, 1)
    for _ in range(subject.spec.impact_ticks):
        subject.advance_interval()
    impact = next(
        event for event in subject.recorder.essential_events if event["type"] == "impact"
    )
    assert impact["control_tick"] == acknowledgement["impact_tick"]
    assert impact["control_tick"] == subject.last_impact["control_tick"]
    assert impact["outcome"] == subject.last_impact["outcome"]
    assert impact["locked_target"] == subject.last_impact["locked_target"]


def test_dnp01_and_escape_ticks_match_the_runner() -> None:
    subject = recorded("neural-events-v1")
    complete_round(subject)
    result = subject.finalize()
    runner = subject.runner.finish_run()
    recorded_spikes = [
        spike
        for event in subject.recorder.essential_events
        if event["type"] == "neural_output"
        for spike in event["dnp01_spikes"]
    ]
    assert recorded_spikes == runner["dnp01_spikes"]
    assert result.summary["dnp01_spikes"] == runner["dnp01_spikes"]
    assert result.summary["decoded_escape_command_control_ticks"] == runner[
        "escape_command_control_ticks"
    ]


def test_applied_sensory_stream_matches_every_runner_interval() -> None:
    subject = recorded("sensory-input-v1")
    complete_round(subject)
    subject.finalize()
    sensory = [
        event
        for event in subject.recorder.essential_events
        if event["type"] == "sensory_input"
    ]
    assert len(sensory) == len(subject.runner.interval_records)
    assert [event["control_tick"] for event in sensory] == list(
        range(subject.control_tick)
    )
    assert [event["observation"] for event in sensory] == [
        interval["observation"] for interval in subject.runner.interval_records
    ]


def test_essential_capacity_loss_is_explicit_and_not_certifiable() -> None:
    limits = RecorderLimits(maximum_essential_records=1)
    subject = recorded("essential-cap-v1", limits=limits)
    complete_round(subject)
    result = subject.finalize()
    assert subject.recorder.essential_dropped > 0
    assert result.summary["recording"]["essential_status"] == "INCOMPLETE"
    assert result.summary["recording"]["essential_records_dropped"] > 0
    assert result.summary["reexecution"] == {
        "capture_envelope_complete": False,
        "verified": False,
        "verification_milestone": "M10",
    }
    assert result.manifest["validity"]["essential_input_evidence"] == "INCOMPLETE"


def test_optional_capacity_loss_has_a_gap_marker() -> None:
    limits = RecorderLimits(maximum_optional_records=1)
    subject = recorded("optional-cap-v1", limits=limits)
    complete_round(subject)
    result = subject.finalize()
    assert result.optional_trace_status == "TRUNCATED"
    assert result.summary["recording"]["optional_records_dropped"] > 0
    gaps = [
        event
        for event in subject.recorder.essential_events
        if event["type"] == "recorder_gap"
    ]
    assert gaps == [
        {
            "type": "recorder_gap",
            "control_tick": gaps[0]["control_tick"],
            "phase": "recorder-boundary",
            "stream": "optional",
            "reason": "maximum-optional-records-reached",
            "recording_class": "essential",
            "event_ordinal": gaps[0]["event_ordinal"],
        }
    ]


def test_archive_byte_limit_is_enforced() -> None:
    limits = RecorderLimits(maximum_archive_bytes=100)
    subject = recorded("archive-cap-v1", limits=limits)
    complete_round(subject)
    with pytest.raises(FlyRunLimitError, match="archive is"):
        subject.finalize()


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


@pytest.mark.parametrize(
    "entries",
    [
        [("../manifest.json", b"{}", stat.S_IFREG | 0o644)],
        [("/manifest.json", b"{}", stat.S_IFREG | 0o644)],
        [("manifest.json", b"{}", stat.S_IFREG | 0o755)],
        [("manifest.json", b"summary.json", stat.S_IFLNK | 0o644)],
        [
            ("manifest.json", b"{}", stat.S_IFREG | 0o644),
            ("events.jsonl", b"", stat.S_IFREG | 0o644),
            ("summary.json", b"{}", stat.S_IFREG | 0o644),
            ("payload.py", b"raise SystemExit", stat.S_IFREG | 0o644),
        ],
    ],
)
def test_loader_rejects_traversal_executable_and_extra_content(
    tmp_path: Path, entries: list[tuple[str, bytes, int]]
) -> None:
    path = tmp_path / "unsafe.flyrun"
    path.write_bytes(zip_bytes(entries))
    with pytest.raises(FlyRunSafetyError):
        load_flyrun(path)


def test_loader_rejects_oversized_expanded_content(tmp_path: Path) -> None:
    oversized = b"x" * (MAX_EXPANDED_BYTES + 1)
    path = tmp_path / "oversized.flyrun"
    path.write_bytes(
        zip_bytes(
            [
                ("manifest.json", b"{}", stat.S_IFREG | 0o644),
                ("events.jsonl", oversized, stat.S_IFREG | 0o644),
                ("summary.json", b"{}", stat.S_IFREG | 0o644),
            ]
        )
    )
    assert path.stat().st_size < MAX_ARCHIVE_BYTES
    with pytest.raises(FlyRunLimitError, match="expanded flyrun"):
        load_flyrun(path)


def test_loader_rejects_duplicate_members(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.flyrun"
    with pytest.warns(UserWarning, match="Duplicate name"):
        path.write_bytes(
            zip_bytes(
                [
                    ("manifest.json", b"{}\n", stat.S_IFREG | 0o644),
                    ("manifest.json", b"{}\n", stat.S_IFREG | 0o644),
                    ("events.jsonl", b"", stat.S_IFREG | 0o644),
                ]
            )
        )
    with pytest.raises(FlyRunSafetyError, match="duplicate flyrun members"):
        load_flyrun(path)


def test_loader_rejects_payload_hash_mismatch(tmp_path: Path) -> None:
    _subject, result = run_representative_recording(
        LIVE, run_id="payload-mismatch-v2", code_git_sha=FIXED_CODE_SHA
    )
    with zipfile.ZipFile(io.BytesIO(result.archive_bytes)) as bundle:
        manifest = bundle.read("manifest.json")
        events = bundle.read("events.jsonl") + b"{}\n"
        summary = bundle.read("summary.json")
    path = tmp_path / "payload-mismatch.flyrun"
    path.write_bytes(
        zip_bytes(
            [
                ("manifest.json", manifest, stat.S_IFREG | 0o644),
                ("events.jsonl", events, stat.S_IFREG | 0o644),
                ("summary.json", summary, stat.S_IFREG | 0o644),
            ]
        )
    )
    with pytest.raises(FlyRunSafetyError, match="payload identity mismatch"):
        load_flyrun(path)


def test_loader_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    _subject, result = run_representative_recording(
        LIVE, run_id="schema-mismatch-v2", code_git_sha=FIXED_CODE_SHA
    )
    with zipfile.ZipFile(io.BytesIO(result.archive_bytes)) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        events = bundle.read("events.jsonl")
        summary = bundle.read("summary.json")
    manifest["schema_version"] = 1
    path = tmp_path / "schema-mismatch.flyrun"
    path.write_bytes(
        zip_bytes(
            [
                (
                    "manifest.json",
                    (json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n").encode(),
                    stat.S_IFREG | 0o644,
                ),
                ("events.jsonl", events, stat.S_IFREG | 0o644),
                ("summary.json", summary, stat.S_IFREG | 0o644),
            ]
        )
    )
    with pytest.raises(FlyRunSafetyError, match="unsupported or executable"):
        load_flyrun(path)


def test_loader_rejects_nonfinite_json_constants(tmp_path: Path) -> None:
    path = tmp_path / "nonfinite.flyrun"
    manifest = b'{"format_id":"flybench.flyrun.v0.1","schema_version":1,"executable_content":false,"limits":NaN}\n'
    path.write_bytes(
        zip_bytes(
            [
                ("manifest.json", manifest, stat.S_IFREG | 0o644),
                ("events.jsonl", b"", stat.S_IFREG | 0o644),
                ("summary.json", b"{}\n", stat.S_IFREG | 0o644),
            ]
        )
    )
    with pytest.raises(FlyRunSafetyError, match="non-finite JSON constant"):
        load_flyrun(path)


def test_recorder_uses_no_pickle_or_dynamic_execution() -> None:
    source = inspect.getsource(recording_module)
    assert "import pickle" not in source
    assert "pickle.loads" not in source
    assert "eval(" not in source
    assert "exec(" not in source


def test_current_live_identities_are_embedded_and_validated(tmp_path: Path) -> None:
    _subject, result = run_representative_recording(
        LIVE, run_id="identity-v1", code_git_sha=FIXED_CODE_SHA
    )
    path = tmp_path / "identity.flyrun"
    write_flyrun(path, result)
    loaded = load_flyrun(path)
    resolved = load_live_profile(LIVE)
    provenance = loaded.manifest["provenance"]
    assert loaded.manifest["format_id"] == FLYRUN_FORMAT_ID
    assert provenance["architecture_sha256"] == ARCHITECTURE_SHA256
    assert provenance["live_profile_sha256"] == resolved.sha256
    assert provenance["game_spec_sha256"] == resolved.game_spec_sha256
    assert provenance["graph"] == resolved.value["graph"]
    assert provenance["selected_live_backend"] == resolved.value["backend"]
    assert provenance["executed_backend"] == "kernel"
    assert provenance["identities"] == {
        "m07_live_candidate_sha256": resolved.value["m07_live_candidate"]["sha256"],
        "runtime_model_spec_sha256": resolved.value["model"][
            "runtime_model_spec_sha256"
        ],
        "controller_sha256": resolved.value["controller"]["sha256"],
        "encoder_sha256": resolved.value["encoder"]["sha256"],
        "decoder_sha256": resolved.value["decoder"]["sha256"],
        "environment_sha256": resolved.value["environment"]["sha256"],
    }
    assert loaded.manifest["process_deviation"]["m08_g_game"] == (
        "PENDING_UNMEASURED"
    )
    resolved_configuration = loaded.manifest["resolved_configuration"]
    assert resolved_configuration["live_profile"] == resolved.value
    assert resolved_configuration["runtime_model_spec"]["schema_version"] == 1
    assert resolved_configuration["effective_environment"][
        "ambient_speed_per_interval"
    ] == 0.03
    assert set(resolved_configuration["profiles"]) == {
        "game_spec",
        "base_model",
        "numerical_criteria",
        "controller",
        "encoder",
        "decoder",
        "accepted_base_environment",
    }


def test_recording_does_not_change_game_outcome_or_runner_state() -> None:
    recorded_subject = recorded("noninterference-v1")
    plain = build_live_session(LIVE)
    complete_round(recorded_subject)
    complete_round(plain)
    assert recorded_subject.snapshot() == plain.snapshot()
    assert recorded_subject.runner.finish_run() == plain.runner.finish_run()


def test_headless_and_local_server_protocol_adapter_record_identically() -> None:
    headless = recorded("adapter-parity-v1")
    server_adapter = recorded("adapter-parity-v1")
    complete_round(headless)
    complete_round(server_adapter, via_protocol=True)
    headless_result = headless.finalize()
    adapter_result = server_adapter.finalize()
    assert headless.snapshot() == server_adapter.snapshot()
    assert headless_result.archive_bytes == adapter_result.archive_bytes
    assert headless_result.content_digest == adapter_result.content_digest
    assert headless_result.applied_input_digest == adapter_result.applied_input_digest


def test_flyrun_inventory_is_exact_and_bounded(tmp_path: Path) -> None:
    _subject, result = run_representative_recording(
        LIVE, run_id="inventory-v1", code_git_sha=FIXED_CODE_SHA
    )
    path = tmp_path / "inventory.flyrun"
    write_flyrun(path, result)
    assert path.stat().st_size <= MAX_ARCHIVE_BYTES
    with zipfile.ZipFile(path) as bundle:
        assert tuple(bundle.namelist()) == FLYRUN_MEMBERS
        assert sum(info.file_size for info in bundle.infolist()) <= MAX_EXPANDED_BYTES


def test_state_digests_are_initial_periodic_and_final() -> None:
    subject = recorded("state-cadence-v2")
    complete_round(subject)
    result = subject.finalize()
    digests = [
        event
        for event in subject.recorder.essential_events
        if event["type"] == "state_digest"
    ]
    expected = [0, *range(100, subject.control_tick, 100)]
    if subject.control_tick not in expected:
        expected.append(subject.control_tick)
    assert [event["control_tick"] for event in digests] == expected
    assert digests[0]["digest_kind"] == "initial"
    assert digests[-1]["digest_kind"] in {"final", "periodic-final"}
    assert all(event["recording_class"] == "essential" for event in digests)
    assert result.summary["reexecution"] == {
        "capture_envelope_complete": True,
        "verified": False,
        "verification_milestone": "M10",
    }


def test_same_complete_state_has_identical_component_and_whole_digests() -> None:
    subject = build_live_session(LIVE)
    left = scientific_state_digest(subject.runner, game_session=subject)
    right = scientific_state_digest(subject.runner, game_session=subject)
    assert left == right


def test_neural_state_change_changes_neural_and_whole_digest() -> None:
    subject = build_live_session(LIVE)
    before = scientific_state_digest(subject.runner, game_session=subject)
    subject.runner.neural.voltage[0] += 0.125
    after = scientific_state_digest(subject.runner, game_session=subject)
    assert after["neural_state_sha256"] != before["neural_state_sha256"]
    assert after["whole_state_sha256"] != before["whole_state_sha256"]
    assert after["environment_state_sha256"] == before["environment_state_sha256"]


def test_environment_rng_change_changes_environment_and_whole_digest() -> None:
    subject = build_live_session(LIVE)
    before = scientific_state_digest(subject.runner, game_session=subject)
    subject.runner.environment.rng.uniform()
    after = scientific_state_digest(subject.runner, game_session=subject)
    assert after["environment_state_sha256"] != before["environment_state_sha256"]
    assert after["whole_state_sha256"] != before["whole_state_sha256"]
    assert after["neural_state_sha256"] == before["neural_state_sha256"]


def test_pending_neural_state_changes_neural_and_whole_digest() -> None:
    subject = build_live_session(LIVE)
    before = scientific_state_digest(subject.runner, game_session=subject)
    subject.runner.neural.pending_inputs[0, 0] = 0.25
    subject.runner.neural.pending_spikes[0, 1] = True
    after = scientific_state_digest(subject.runner, game_session=subject)
    assert after["neural_state_sha256"] != before["neural_state_sha256"]
    assert after["whole_state_sha256"] != before["whole_state_sha256"]


def test_held_command_change_changes_whole_digest() -> None:
    subject = build_live_session(LIVE)
    before = scientific_state_digest(subject.runner, game_session=subject)
    subject.runner.held_command = True
    after = scientific_state_digest(subject.runner, game_session=subject)
    assert after["whole_state_sha256"] != before["whole_state_sha256"]
    assert after["neural_state_sha256"] == before["neural_state_sha256"]
    assert after["environment_state_sha256"] == before["environment_state_sha256"]
    assert after["game_state_sha256"] == before["game_state_sha256"]


def test_pending_strike_changes_game_and_whole_digest() -> None:
    subject = build_live_session(LIVE)
    before = scientific_state_digest(subject.runner, game_session=subject)
    subject.commit_attack(2.5, -1.5, 1)
    after = scientific_state_digest(subject.runner, game_session=subject)
    assert after["game_state_sha256"] != before["game_state_sha256"]
    assert after["whole_state_sha256"] != before["whole_state_sha256"]
    assert after["neural_state_sha256"] == before["neural_state_sha256"]


def test_final_state_digest_matches_actual_authoritative_state() -> None:
    subject = recorded("final-state-v2")
    complete_round(subject)
    actual = scientific_state_digest(subject.runner, game_session=subject.session)
    result = subject.finalize()
    final = [
        event
        for event in subject.recorder.essential_events
        if event["type"] == "state_digest"
    ][-1]
    for key, value in actual.items():
        assert final[key] == value
    assert result.summary["final_whole_state_sha256"] == actual[
        "whole_state_sha256"
    ]


def test_manifest_applied_hash_matches_independent_canonical_projection() -> None:
    subject = recorded("applied-hash-v2")
    complete_round(subject)
    result = subject.finalize()
    records = canonical_applied_input_records(subject.recorder.essential_events)
    canonical = b"".join(
        (
            json.dumps(
                record,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        for record in records
    )
    independent = hashlib.sha256(canonical).hexdigest()
    assert independent == canonical_applied_input_sha256(
        subject.recorder.essential_events
    )
    assert result.applied_input_digest == independent
    assert result.manifest["run"]["applied_input_sha256"] == independent
    assert result.manifest["integrity"]["applied_input_sha256"] == independent
    assert result.summary["applied_input_sha256"] == independent


def test_loader_rejects_manifest_summary_applied_hash_disagreement(
    tmp_path: Path,
) -> None:
    _subject, result = run_representative_recording(
        LIVE, run_id="applied-mismatch-v2", code_git_sha=FIXED_CODE_SHA
    )
    with zipfile.ZipFile(io.BytesIO(result.archive_bytes)) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        events = bundle.read("events.jsonl")
        summary = bundle.read("summary.json")
    manifest["run"]["applied_input_sha256"] = "0" * 64
    path = tmp_path / "applied-mismatch.flyrun"
    path.write_bytes(
        zip_bytes(
            [
                (
                    "manifest.json",
                    (json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n").encode(),
                    stat.S_IFREG | 0o644,
                ),
                ("events.jsonl", events, stat.S_IFREG | 0o644),
                ("summary.json", summary, stat.S_IFREG | 0o644),
            ]
        )
    )
    with pytest.raises(FlyRunSafetyError, match="applied-input identity mismatch"):
        load_flyrun(path)


def test_aim_updates_coalesce_to_latest_sequence_at_application_boundary() -> None:
    subject = recorded("aim-coalesce-v2")
    subject.update_aim(-4.0, 3.0, 1)
    subject.update_aim(1.5, -2.25, 4)
    subject.update_aim(8.0, 9.0, 7)
    assert subject.recorder.applied_input_events == ()
    subject.advance_interval()
    applied = subject.recorder.applied_input_events
    assert len(applied) == 1
    assert applied[0]["type"] == "accepted_aim"
    assert applied[0]["sequence"] == 7
    assert applied[0]["aim"] == {"x": 8.0, "y": 9.0}
    assert subject.recorder.essential_events[0]["type"] == "lifecycle"
    assert subject.session.coalesced_aim_updates == 2


def test_duplicate_stale_and_malformed_sequences_never_become_applied() -> None:
    subject = recorded("sequence-rejection-v2")
    subject.update_aim(1.0, 1.0, 4)
    for sequence in (4, 3, 4.0, True):
        with pytest.raises(GameInputError):
            subject.update_aim(2.0, 2.0, sequence)
    subject.advance_interval()
    applied = subject.recorder.applied_input_events
    assert len(applied) == 1
    assert applied[0]["sequence"] == 4
    assert subject.recorder.rejected_diagnostics == {
        "malformed": 2,
        "stale_sequence": 2,
    }


def test_same_tick_aim_then_commit_order_and_locked_target_are_deterministic() -> None:
    subject = recorded("same-tick-order-v2")
    subject.update_aim(-8.0, 7.0, 1)
    subject.update_aim(-2.0, 4.0, 2)
    acknowledgement = subject.commit_attack(2.25, -3.5, 3)
    subject.update_aim(9.0, 9.0, 4)
    subject.advance_interval()
    applied = list(subject.recorder.applied_input_events)
    assert [event["type"] for event in applied] == [
        "accepted_aim",
        "attack_commit",
        "accepted_aim",
    ]
    assert applied[0]["aim"] == {"x": -2.0, "y": 4.0}
    assert applied[1]["locked_target"] == acknowledgement["locked_target"] == {
        "x": 2.25,
        "y": -3.5,
    }
    assert subject.snapshot()["strike"]["locked_target"] == {
        "x": 2.25,
        "y": -3.5,
    }
    assert [event["event_ordinal"] for event in applied] == sorted(
        event["event_ordinal"] for event in applied
    )


def test_archive_event_order_is_explicit_and_stable(tmp_path: Path) -> None:
    _subject, result = run_representative_recording(
        LIVE, run_id="event-order-v2", code_git_sha=FIXED_CODE_SHA
    )
    path = tmp_path / "event-order.flyrun"
    write_flyrun(path, result)
    loaded = load_flyrun(path)
    keys = [
        (event["control_tick"], event["event_ordinal"])
        for event in loaded.events
    ]
    assert keys == sorted(keys)
    assert len({ordinal for _tick, ordinal in keys}) == len(keys)
    assert loaded.manifest["event_ordering"]["sort_key"] == [
        "control_tick",
        "event_ordinal",
    ]


def test_benchmark_recording_is_observational_and_writes_valid_flyrun(
    tmp_path: Path,
) -> None:
    stimulus = ROOT / "profiles/looming-controls.json"
    plain_summary, plain_recording = run_selected_benchmark(stimulus)
    recorded_summary, result = run_selected_benchmark(
        stimulus,
        record_directory=tmp_path,
        code_git_sha=FIXED_CODE_SHA,
    )
    assert plain_recording is None
    assert result is not None
    assert recorded_summary == plain_summary
    path = tmp_path / "looming-seed-0.flyrun"
    loaded = load_flyrun(path)
    assert loaded.manifest["run"]["execution_kind"] == "bench-trial"
    assert loaded.summary["dnp01_spikes"] == plain_summary["dnp01_spikes"]
    assert loaded.summary["decoded_escape_command_control_ticks"] == plain_summary[
        "escape_command_control_ticks"
    ]
    assert loaded.summary["authoritative_result"] == "trial-complete"


def test_no_m09_archive_claims_reexecution_was_verified() -> None:
    _subject, result = run_representative_recording(
        LIVE, run_id="not-m10-v2", code_git_sha=FIXED_CODE_SHA
    )
    assert result.manifest["validity"]["reexecution"] == {
        "capture_envelope_complete": True,
        "verified": False,
        "verification_milestone": "M10",
    }
    assert result.manifest["tested_runtime_envelope"]["reexecution_verified"] is False
    serialized = json.dumps({"manifest": result.manifest, "summary": result.summary})
    assert '"verified": true' not in serialized.lower()
    assert '"reexecution_certifiable"' not in serialized
