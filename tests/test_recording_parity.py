from __future__ import annotations

import copy
from dataclasses import asdict
import json
import math
from pathlib import Path
import struct

import pytest

from flybench.cli import main as cli_main
from flybench.game import (
    COORDINATE_QUANTIZATION_ID,
    DemoProtocol,
    GameInputError,
    build_live_session,
    load_live_profile,
    quantize_coordinate_binary64,
)
from flybench.recording import (
    build_recorded_live_session,
    canonical_applied_input_records,
    load_flyrun,
    scientific_state_digest,
)


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "profiles/live.json"
STIMULUS = ROOT / "profiles/looming-controls.json"
FIXED_CODE_SHA = "3" * 40
TARGETS = (
    (10.0, 10.0),
    (-10.0, 10.0),
    (10.0, -10.0),
    (-10.0, -10.0),
    (10.0, 10.0),
    (-10.0, 10.0),
)


def binary64(value: float) -> bytes:
    return struct.pack(">d", value)


def complete_round(subject: object, *, protocol: DemoProtocol | None = None) -> None:
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


def test_recorded_and_unrecorded_game_session_final_scientific_state_parity() -> None:
    plain = build_live_session(LIVE)
    recorded = build_recorded_live_session(
        LIVE, run_id="game-session-parity-a03", code_git_sha=FIXED_CODE_SHA
    )

    complete_round(plain)
    complete_round(recorded)

    plain_digest = scientific_state_digest(plain.runner, game_session=plain)
    recorded_digest = scientific_state_digest(
        recorded.runner, game_session=recorded.session
    )
    assert plain.applied_input_records == list(
        canonical_applied_input_records(recorded.recorder.applied_input_events)
    )
    assert plain_digest == recorded_digest
    assert plain.runner.finish_run() == recorded.runner.finish_run()
    assert plain.result == recorded.result


def test_selected_benchmark_cli_writes_out_and_record_dir_with_full_parity(
    tmp_path: Path,
) -> None:
    output = tmp_path / "bench"
    recordings = tmp_path / "runs"

    assert (
        cli_main(
            [
                "bench",
                str(STIMULUS),
                "--out",
                str(output),
                "--record-dir",
                str(recordings),
            ]
        )
        == 0
    )

    selected = json.loads(
        (output / "selected-trial-summary.json").read_text(encoding="utf-8")
    )
    parity = json.loads(
        (output / "recorder-parity.json").read_text(encoding="utf-8")
    )
    loaded = load_flyrun(recordings / "looming-seed-0.flyrun")
    assert selected["status"] == parity["status"] == "PASS"
    assert selected["selected_fixture"]["scenario"] == "standard looming"
    assert selected["selected_fixture"]["not_full_m06_calibration"] is True
    assert all(parity["checks"].values())
    assert parity["recording_disabled"]["final_scientific_state"] == parity[
        "recording_enabled"
    ]["final_scientific_state"]
    assert parity["recording_disabled"]["dnp01_spike_ticks"] == parity[
        "recording_enabled"
    ]["dnp01_spike_ticks"]
    assert parity["recording_disabled"]["decoded_command_ticks"] == parity[
        "recording_enabled"
    ]["decoded_command_ticks"]
    assert parity["recording_disabled"]["impacts"] == parity["recording_enabled"][
        "impacts"
    ]
    assert parity["recording_disabled"]["finite_state"] is True
    assert loaded.summary["final_whole_state_sha256"] == parity[
        "recording_enabled"
    ]["final_scientific_state"]["whole_state_sha256"]


def test_direct_headless_and_demo_protocol_authoritative_parity() -> None:
    direct = build_live_session(LIVE)
    adapted = build_live_session(LIVE)
    protocol = DemoProtocol(adapted)

    complete_round(direct)
    complete_round(adapted, protocol=protocol)

    assert direct.applied_input_records == adapted.applied_input_records
    assert scientific_state_digest(
        direct.runner, game_session=direct
    ) == scientific_state_digest(adapted.runner, game_session=adapted)
    assert direct.snapshot() == adapted.snapshot()


def test_recorder_observation_does_not_mutate_authoritative_state() -> None:
    subject = build_recorded_live_session(
        LIVE, run_id="observer-purity-a03", code_git_sha=FIXED_CODE_SHA
    )
    before_digest = scientific_state_digest(
        subject.runner, game_session=subject.session
    )
    before_neural_rng = copy.deepcopy(subject.runner.neural.rng.bit_generator.state)
    before_environment_rng = copy.deepcopy(
        subject.runner.environment.rng.bit_generator.state
    )
    before_snapshot = subject.snapshot()
    before_held = subject.runner.held_command
    before_result = subject.result

    subject._record_state_digest("test-observation")

    after_digest = scientific_state_digest(subject.runner, game_session=subject.session)
    assert after_digest == before_digest
    assert subject.runner.neural.rng.bit_generator.state == before_neural_rng
    assert subject.runner.environment.rng.bit_generator.state == before_environment_rng
    assert subject.snapshot() == before_snapshot
    assert subject.runner.held_command == before_held
    assert subject.result == before_result


def test_final_recorder_whole_state_digest_matches_authoritative_object() -> None:
    subject = build_recorded_live_session(
        LIVE, run_id="final-digest-a03", code_git_sha=FIXED_CODE_SHA
    )
    complete_round(subject)
    independent = scientific_state_digest(
        subject.runner, game_session=subject.session
    )

    result = subject.finalize()

    final_event = [
        event
        for event in subject.recorder.essential_events
        if event["type"] == "state_digest"
    ][-1]
    assert result.summary["final_whole_state_sha256"] == independent[
        "whole_state_sha256"
    ]
    assert final_event["whole_state_sha256"] == independent["whole_state_sha256"]
    assert result.manifest["applied_input_hash"]["coordinate_quantization"] == {
        "identity": COORDINATE_QUANTIZATION_ID,
        "application_boundary": "before authoritative GameSession application",
        "recorder_rule": "copy the exact applied binary64; no recorder-side rounding",
    }


def test_coordinate_quantizer_canonicalizes_integer_and_decimal_inputs() -> None:
    resolved = load_live_profile(LIVE)
    for supplied in (3, 0.1, -0.9876543210123456):
        quantized = quantize_coordinate_binary64(
            supplied,
            name="x",
            arena_min=resolved.game_spec.arena_min,
            arena_max=resolved.game_spec.arena_max,
        )
        assert type(quantized) is float
        assert binary64(quantized) == binary64(float(supplied))
        assert quantized.hex() == float(supplied).hex()


def test_pending_aim_attack_and_recorder_share_exact_binary64() -> None:
    subject = build_recorded_live_session(
        LIVE, run_id="coordinate-binary64-a03", code_git_sha=FIXED_CODE_SHA
    )
    pending_x = 0.10000000000000002
    pending_y = -0.30000000000000004
    attack_x = 1.2345678901234567
    attack_y = -9.876543210123455

    subject.update_aim(pending_x, pending_y, 1)
    assert subject.session.pending_aim is not None
    assert binary64(subject.session.pending_aim[0]) == binary64(float(pending_x))
    assert binary64(subject.session.pending_aim[1]) == binary64(float(pending_y))
    acknowledgement = subject.commit_attack(attack_x, attack_y, 2)
    events = subject.recorder.applied_input_events

    assert binary64(events[0]["aim"]["x"]) == binary64(pending_x)
    assert binary64(events[0]["aim"]["y"]) == binary64(pending_y)
    assert subject.session.active_strike is not None
    assert binary64(events[1]["locked_target"]["x"]) == binary64(
        subject.session.active_strike.target_x
    ) == binary64(acknowledgement["locked_target"]["x"])
    assert binary64(events[1]["locked_target"]["y"]) == binary64(
        subject.session.active_strike.target_y
    ) == binary64(acknowledgement["locked_target"]["y"])
    assert events[1]["locked_target"]["x"].hex() == attack_x.hex()
    assert events[1]["locked_target"]["y"].hex() == attack_y.hex()


def test_supported_coordinate_canonical_json_round_trip_preserves_binary64() -> None:
    values = [0.1, -0.30000000000000004, 1.2345678901234567]
    payload = json.dumps(values, allow_nan=False, separators=(",", ":"))
    restored = json.loads(payload)
    assert [binary64(value) for value in restored] == [
        binary64(value) for value in values
    ]


def test_coordinate_rejections_and_gamespec_identity_are_unchanged() -> None:
    resolved = load_live_profile(LIVE)
    spec_before = asdict(resolved.game_spec)
    kwargs = {
        "name": "x",
        "arena_min": resolved.game_spec.arena_min,
        "arena_max": resolved.game_spec.arena_max,
    }
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(GameInputError, match="must be finite") as error:
            quantize_coordinate_binary64(value, **kwargs)
        assert error.value.code == "non_finite"
    for value in (
        resolved.game_spec.arena_min - 0.01,
        resolved.game_spec.arena_max + 0.01,
    ):
        with pytest.raises(GameInputError, match="outside the arena") as error:
            quantize_coordinate_binary64(value, **kwargs)
        assert error.value.code == "out_of_arena"
    with pytest.raises(GameInputError) as error:
        quantize_coordinate_binary64(True, **kwargs)
    assert error.value.code == "malformed"
    assert asdict(resolved.game_spec) == spec_before
