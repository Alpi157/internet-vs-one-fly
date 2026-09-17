from __future__ import annotations

import inspect
import io
import math
from pathlib import Path
import stat
import zipfile

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
    load_flyrun,
    run_representative_recording,
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
    assert result.summary["recording"]["reexecution_certifiable"] is False
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
        [("manifest.json", b"{}", stat.S_IFREG | 0o755)],
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
    assert provenance["backend"] == resolved.value["backend"]
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
