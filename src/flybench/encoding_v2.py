"""Declared 3D hand-disk encoder for the v2 model."""

from __future__ import annotations

from dataclasses import dataclass
import math

from flybench.detmath import atan_approx


@dataclass(frozen=True, slots=True)
class HandStrikeV2:
    active: bool
    aim_x: float = 0.0
    aim_y: float = 0.0
    elapsed_ms: float = 0.0
    downward_speed_per_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class EncoderOutputV2:
    angular_radius: float
    angular_expansion_per_ms: float
    left_fraction: float
    right_fraction: float
    lc4_left_drive: float
    lc4_right_drive: float
    lplc2_left_drive: float
    lplc2_right_drive: float


def encode_hand_v2(
    strike: HandStrikeV2,
    *,
    fly_x: float,
    fly_y: float,
    heading_x: float,
    heading_y: float,
    hand_radius: float,
    initial_height: float,
    dt_ms: float,
    input_gain: float,
) -> EncoderOutputV2:
    values = (
        fly_x,
        fly_y,
        heading_x,
        heading_y,
        hand_radius,
        initial_height,
        dt_ms,
        input_gain,
        strike.aim_x,
        strike.aim_y,
        strike.elapsed_ms,
        strike.downward_speed_per_ms,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("encoder inputs must be finite")
    if hand_radius <= 0.0 or initial_height <= 0.0 or dt_ms <= 0.0 or input_gain < 0.0:
        raise ValueError("encoder scale values are outside their declared domains")
    if not strike.active:
        return EncoderOutputV2(0.0, 0.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0)
    height = initial_height - strike.downward_speed_per_ms * strike.elapsed_ms
    if height < 0.0:
        height = 0.0
    previous_height = height + strike.downward_speed_per_ms * dt_ms
    dx = strike.aim_x - fly_x
    dy = strike.aim_y - fly_y
    planar_distance = math.sqrt(dx * dx + dy * dy)
    distance = math.sqrt(planar_distance * planar_distance + height * height)
    previous_distance = math.sqrt(
        planar_distance * planar_distance + previous_height * previous_height
    )
    minimum_distance = hand_radius / 8.0
    bounded_distance = distance if distance > minimum_distance else minimum_distance
    bounded_previous = previous_distance if previous_distance > minimum_distance else minimum_distance
    angular_radius = atan_approx(hand_radius / bounded_distance)
    previous_radius = atan_approx(hand_radius / bounded_previous)
    expansion = (angular_radius - previous_radius) / dt_ms
    if expansion < 0.0:
        expansion = 0.0
    if planar_distance > 0.0:
        direction_x = dx / planar_distance
        direction_y = dy / planar_distance
        cross = heading_x * direction_y - heading_y * direction_x
        if cross < -1.0:
            cross = -1.0
        elif cross > 1.0:
            cross = 1.0
    else:
        cross = 0.0
    left_fraction = 0.5 * (1.0 + cross)
    right_fraction = 1.0 - left_fraction
    size_drive = input_gain * angular_radius
    expansion_drive = input_gain * expansion
    return EncoderOutputV2(
        angular_radius,
        expansion,
        left_fraction,
        right_fraction,
        size_drive * left_fraction,
        size_drive * right_fraction,
        expansion_drive * left_fraction,
        expansion_drive * right_fraction,
    )

