"""Restricted-math planar body kinematics for the v2 model."""

from __future__ import annotations

from dataclasses import dataclass
import math

from flybench.detmath import rotate_unit_step


@dataclass(frozen=True, slots=True)
class BodyStateV2:
    x: float
    y: float
    heading_x: float
    heading_y: float


def advance_body_v2(
    state: BodyStateV2,
    *,
    forward_speed_per_ms: float,
    turn_rate_rad_per_ms: float,
    dt_ms: float,
) -> BodyStateV2:
    if not all(
        math.isfinite(value)
        for value in (
            state.x,
            state.y,
            state.heading_x,
            state.heading_y,
            forward_speed_per_ms,
            turn_rate_rad_per_ms,
            dt_ms,
        )
    ):
        raise ValueError("body inputs must be finite")
    delta = turn_rate_rad_per_ms * dt_ms
    heading_x, heading_y = rotate_unit_step(state.heading_x, state.heading_y, delta)
    return BodyStateV2(
        state.x + heading_x * forward_speed_per_ms * dt_ms,
        state.y + heading_y * forward_speed_per_ms * dt_ms,
        heading_x,
        heading_y,
    )


def takeoff_vector_v2(state: BodyStateV2, speed_per_ms: float) -> tuple[float, float]:
    if not math.isfinite(speed_per_ms) or speed_per_ms < 0.0:
        raise ValueError("takeoff speed must be finite and nonnegative")
    return state.heading_x * speed_per_ms, state.heading_y * speed_per_ms

