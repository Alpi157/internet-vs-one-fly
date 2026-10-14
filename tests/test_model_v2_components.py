from __future__ import annotations

import json
from pathlib import Path

import pytest

from flybench.authority import FORBIDDEN_DECODER_TOKENS, audit_callable_dependencies
from flybench.body_v2 import BodyStateV2, advance_body_v2, takeoff_vector_v2
from flybench.decoder_v2 import decode_spikes_v2
from flybench.encoding_v2 import HandStrikeV2, encode_hand_v2


ROOT = Path(__file__).resolve().parents[1]


def _encode(aim_x: float, aim_y: float):
    return encode_hand_v2(
        HandStrikeV2(True, aim_x, aim_y, 100.0, 0.02),
        fly_x=0.0,
        fly_y=0.0,
        heading_x=1.0,
        heading_y=0.0,
        hand_radius=0.75,
        initial_height=8.0,
        dt_ms=0.5,
        input_gain=4.0,
    )


def test_encoder_mirror_symmetry() -> None:
    left = _encode(2.0, 3.0)
    right = _encode(2.0, -3.0)
    assert left.lc4_left_drive == pytest.approx(right.lc4_right_drive)
    assert left.lplc2_left_drive == pytest.approx(right.lplc2_right_drive)


def test_encoder_decreases_with_aim_distance() -> None:
    near = _encode(1.0, 0.0)
    far = _encode(20.0, 0.0)
    assert near.angular_radius > far.angular_radius
    assert near.lc4_left_drive + near.lc4_right_drive > far.lc4_left_drive + far.lc4_right_drive


def test_encoder_no_strike_is_zero() -> None:
    value = encode_hand_v2(
        HandStrikeV2(False), fly_x=0.0, fly_y=0.0, heading_x=1.0, heading_y=0.0,
        hand_radius=0.75, initial_height=8.0, dt_ms=0.5, input_gain=4.0,
    )
    assert value.lc4_left_drive == value.lc4_right_drive == 0.0
    assert value.lplc2_left_drive == value.lplc2_right_drive == 0.0


def test_decoder_uses_spikes_only_and_empty_group_is_zero() -> None:
    groups = ((1,), (2,), (3,), (4,), (5,), ())
    result = decode_spikes_v2((1, 4), (0.0,) * 6, groups, 0.8, 0.01, 0.001, 0.001, -1.0, 1.0, 1.0)
    assert result[0] is True
    assert result[3][5] == 0.0


def test_decoder_i3_structural_audit() -> None:
    audit = audit_callable_dependencies(decode_spikes_v2, forbidden_tokens=FORBIDDEN_DECODER_TOKENS)
    assert audit["status"] == "PASS"
    assert audit["forbidden_token_scan"]["hits"] == {}
    assert audit["closure_variables"]["nonlocals"] == {}
    assert audit["mutable_referenced_globals"] == []
    assert audit["reachable_environment_objects"] == []


def test_body_update_and_takeoff_follow_heading() -> None:
    state = BodyStateV2(0.0, 0.0, 1.0, 0.0)
    moved = advance_body_v2(state, forward_speed_per_ms=0.01, turn_rate_rad_per_ms=0.001, dt_ms=10.0)
    assert moved.x > 0.0 and moved.y > 0.0
    assert takeoff_vector_v2(moved, 0.02) == pytest.approx((moved.heading_x * 0.02, moved.heading_y * 0.02))


def test_final_port_receipt_is_exact() -> None:
    profile = json.loads((ROOT / "profiles/ports-v2.json").read_text(encoding="utf-8"))
    final_ids = {
        int(entry["body_id"])
        for entries in profile["groups"].values()
        for entry in entries
        if entry["status"] == "FINAL"
    }
    assert final_ids == {10001,10010,10763,11332,11288,12348,11177,10783,10360,523769,10760,10442,512006,11074,10805,13922,12767,529488}
