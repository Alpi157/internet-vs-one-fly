"""Spike-only v2 motor decoder."""

from __future__ import annotations


def decode_spikes_v2(
    spike_body_ids: tuple[int, ...],
    prior_rates: tuple[float, float, float, float, float, float],
    groups: tuple[
        tuple[int, ...],
        tuple[int, ...],
        tuple[int, ...],
        tuple[int, ...],
        tuple[int, ...],
        tuple[int, ...],
    ],
    decay: float,
    interval_seconds: float,
    forward_gain: float,
    turn_gain: float,
    minimum_speed: float,
    maximum_speed: float,
    maximum_turn_rate: float,
) -> tuple[bool, float, float, tuple[float, float, float, float, float, float]]:
    fired = set(spike_body_ids)
    next_rates = []
    for group_index in range(6):
        group = groups[group_index]
        if not group:
            next_rates.append(0.0)
        else:
            count = sum(1 for value in spike_body_ids if value in group)
            next_rates.append(
                decay * prior_rates[group_index]
                + (1.0 - decay) * count / interval_seconds
            )
    escape = any(value in fired for value in groups[0]) or any(
        value in fired for value in groups[1]
    )
    speed = forward_gain * (next_rates[5] - next_rates[2])
    if speed < minimum_speed:
        speed = minimum_speed
    elif speed > maximum_speed:
        speed = maximum_speed
    turn = turn_gain * (next_rates[3] - next_rates[4])
    if turn < -maximum_turn_rate:
        turn = -maximum_turn_rate
    elif turn > maximum_turn_rate:
        turn = maximum_turn_rate
    return escape, speed, turn, tuple(next_rates)

