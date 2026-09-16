"""Minimal abstract body mechanics for the M06 headless experiment."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np


@dataclass(frozen=True, slots=True)
class EnvironmentConfig:
    arena_min: float
    arena_max: float
    initial_x: float
    initial_y: float
    initial_heading_rad: float
    ambient_speed_per_interval: float
    heading_jitter_min_rad: float
    heading_jitter_max_rad: float
    takeoff_duration_intervals: int
    takeoff_speed_per_interval: float


@dataclass(frozen=True, slots=True)
class MotionResult:
    start_control_tick: int
    end_control_tick: int
    held_escape_request: bool
    takeoff_started: bool
    takeoff_active: bool
    x: float
    y: float
    heading_rad: float


@dataclass(frozen=True, slots=True)
class ImpactResult:
    control_tick: int
    outcome: str
    takeoff_was_active: bool


def ambient_step(
    position: tuple[float, float],
    heading_rad: float,
    jitter_rad: float,
    config: EnvironmentConfig,
) -> tuple[tuple[float, float], float]:
    """Advance seeded ambient motion using only body state, jitter, and mechanics."""

    heading = heading_rad + jitter_rad
    x = position[0] + config.ambient_speed_per_interval * math.cos(heading)
    y = position[1] + config.ambient_speed_per_interval * math.sin(heading)
    if x < config.arena_min or x > config.arena_max:
        x = min(max(x, config.arena_min), config.arena_max)
        heading = math.pi - heading
    if y < config.arena_min or y > config.arena_max:
        y = min(max(y, config.arena_min), config.arena_max)
        heading = -heading
    heading = math.atan2(math.sin(heading), math.cos(heading))
    return (x, y), heading


def load_environment_config(path: Path) -> EnvironmentConfig:
    """Load the resolved, deliberately provisional M06 mechanics profile."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("unsupported environment profile")
    arena = value["arena"]
    initial = value["initial_body_state"]
    ambient = value["ambient_walking"]
    takeoff = value["takeoff"]
    config = EnvironmentConfig(
        arena_min=float(arena["minimum"]),
        arena_max=float(arena["maximum"]),
        initial_x=float(initial["x"]),
        initial_y=float(initial["y"]),
        initial_heading_rad=float(initial["heading_rad"]),
        ambient_speed_per_interval=float(ambient["speed_per_control_interval"]),
        heading_jitter_min_rad=float(ambient["heading_jitter_uniform_rad"][0]),
        heading_jitter_max_rad=float(ambient["heading_jitter_uniform_rad"][1]),
        takeoff_duration_intervals=int(takeoff["duration_control_intervals"]),
        takeoff_speed_per_interval=float(takeoff["speed_per_control_interval"]),
    )
    if not config.arena_min < config.arena_max:
        raise ValueError("arena bounds must be strictly ordered")
    if config.takeoff_duration_intervals <= 0:
        raise ValueError("takeoff duration must be positive")
    return config


class CatchEnvironment:
    """One independently owned mutable abstract body/environment state."""

    def __init__(self, config: EnvironmentConfig, *, seed: int):
        self.config = config
        self.seed = seed
        self.reset()

    def reset(self, *, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("environment seed must be a nonnegative integer")
        self.x = self.config.initial_x
        self.y = self.config.initial_y
        self.heading_rad = self.config.initial_heading_rad
        self.control_tick = 0
        self.takeoff_ticks_remaining = 0
        self.takeoff_heading_rad: float | None = None
        self.takeoff_active_last_interval = False
        self.scheduled_impact_ticks: list[int] = []
        self.impacts: list[ImpactResult] = []
        self.rng = np.random.Generator(np.random.PCG64(self.seed))

    @property
    def position(self) -> tuple[float, float]:
        return self.x, self.y

    def schedule_impact(self, control_tick: int) -> None:
        if type(control_tick) is not int or control_tick <= self.control_tick:
            raise ValueError("impact must be scheduled at a future control boundary")
        self.scheduled_impact_ticks.append(control_tick)

    def advance_motion(self, held_escape_request: bool) -> MotionResult:
        """Advance one interval under the command held at its start."""

        start_tick = self.control_tick
        takeoff_started = bool(held_escape_request and self.takeoff_ticks_remaining == 0)
        if takeoff_started:
            self.takeoff_ticks_remaining = self.config.takeoff_duration_intervals
            self.takeoff_heading_rad = self.heading_rad

        takeoff_active = self.takeoff_ticks_remaining > 0
        if takeoff_active:
            assert self.takeoff_heading_rad is not None
            self.x += self.config.takeoff_speed_per_interval * math.cos(
                self.takeoff_heading_rad
            )
            self.y += self.config.takeoff_speed_per_interval * math.sin(
                self.takeoff_heading_rad
            )
            self.x = min(max(self.x, self.config.arena_min), self.config.arena_max)
            self.y = min(max(self.y, self.config.arena_min), self.config.arena_max)
            self.takeoff_ticks_remaining -= 1
        else:
            jitter = float(
                self.rng.uniform(
                    self.config.heading_jitter_min_rad,
                    self.config.heading_jitter_max_rad,
                )
            )
            (self.x, self.y), self.heading_rad = ambient_step(
                (self.x, self.y), self.heading_rad, jitter, self.config
            )

        self.takeoff_active_last_interval = takeoff_active
        self.control_tick += 1
        return MotionResult(
            start_control_tick=start_tick,
            end_control_tick=self.control_tick,
            held_escape_request=bool(held_escape_request),
            takeoff_started=takeoff_started,
            takeoff_active=takeoff_active,
            x=self.x,
            y=self.y,
            heading_rad=self.heading_rad,
        )

    def resolve_due_impacts(self) -> tuple[ImpactResult, ...]:
        """Resolve impacts only after motion for the just-completed interval."""

        due = [tick for tick in self.scheduled_impact_ticks if tick == self.control_tick]
        self.scheduled_impact_ticks = [
            tick for tick in self.scheduled_impact_ticks if tick != self.control_tick
        ]
        resolved: list[ImpactResult] = []
        for tick in due:
            item = ImpactResult(
                control_tick=tick,
                outcome=(
                    "takeoff-active-at-impact"
                    if self.takeoff_active_last_interval
                    else "modeled-contact"
                ),
                takeoff_was_active=self.takeoff_active_last_interval,
            )
            self.impacts.append(item)
            resolved.append(item)
        return tuple(resolved)

    def snapshot(self) -> dict[str, object]:
        return {
            "x": self.x,
            "y": self.y,
            "heading_rad": self.heading_rad,
            "control_tick": self.control_tick,
            "takeoff_ticks_remaining": self.takeoff_ticks_remaining,
            "takeoff_heading_rad": self.takeoff_heading_rad,
            "takeoff_active_last_interval": self.takeoff_active_last_interval,
            "scheduled_impact_ticks": tuple(self.scheduled_impact_ticks),
            "impacts": tuple(self.impacts),
            "rng_state": self.rng.bit_generator.state,
            "seed": self.seed,
        }
