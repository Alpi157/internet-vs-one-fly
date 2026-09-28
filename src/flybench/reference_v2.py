"""Readable v2 LIF reference with deterministic counter-based background noise."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from flybench.detmath import bernoulli
from flybench.model import ModelSpec
from flybench.reference import ReferenceGraph, StepResult


@dataclass(frozen=True, slots=True)
class NoiseSpec:
    seed: int
    stream_id: int
    threshold: int
    current_increment: float
    population_mask: np.ndarray

    def __post_init__(self) -> None:
        mask = np.array(self.population_mask, dtype=np.bool_, copy=True)
        if mask.ndim != 1:
            raise ValueError("noise population mask must be one-dimensional")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("noise seed must be a nonnegative integer")
        if type(self.stream_id) is not int or self.stream_id < 0:
            raise ValueError("noise stream must be a nonnegative integer")
        if type(self.threshold) is not int or not 0 <= self.threshold <= 2**32:
            raise ValueError("noise threshold must be within [0, 2**32]")
        if not math.isfinite(self.current_increment) or self.current_increment < 0.0:
            raise ValueError("noise current increment must be finite and nonnegative")
        mask.flags.writeable = False
        object.__setattr__(self, "population_mask", mask)


class ReferenceStateV2:
    """Reference implementation of neural-order.v2-noise-1."""

    def __init__(self, spec: ModelSpec, graph: ReferenceGraph, noise: NoiseSpec):
        if graph.n <= 0 or noise.population_mask.shape != (graph.n,):
            raise ValueError("graph and noise population sizes must match")
        self.spec = spec
        self.graph = graph
        self.noise = noise
        self._voltage_decay = float.fromhex("0x1.f35bd21f40adcp-1")
        self._current_decay = float.fromhex("0x1.cf46d99d52b3ap-1")
        if spec.neural_dt_ms != 0.5 or spec.tau_m_ms != 20.0 or spec.tau_s_ms != 5.0:
            self._voltage_decay = math.exp(-spec.neural_dt_ms / spec.tau_m_ms)
            self._current_decay = math.exp(-spec.neural_dt_ms / spec.tau_s_ms)
        self._held_drive_factor = 1.0 - self._voltage_decay
        self._current_coupling_factor = (
            spec.tau_s_ms
            / (spec.tau_s_ms - spec.tau_m_ms)
            * (self._current_decay - self._voltage_decay)
        )
        self.reset()

    @property
    def n(self) -> int:
        return self.graph.n

    def reset(self) -> None:
        self.voltage = np.full(self.n, self.spec.rest, dtype=np.float64)
        self.synaptic_current = np.zeros(self.n, dtype=np.float64)
        self.refractory_until_tick = np.zeros(self.n, dtype=np.int64)
        self.tick = 0
        self._ring_size = self.spec.delay_ticks + 1
        self.pending_spikes = np.zeros((self._ring_size, self.n), dtype=np.bool_)
        self.pending_inputs = np.zeros((self._ring_size, self.n), dtype=np.float64)

    def step(self, external_drive: np.ndarray | float) -> StepResult:
        drive = np.asarray(external_drive, dtype=np.float64)
        if drive.ndim == 0:
            drive = np.full(self.n, float(drive), dtype=np.float64)
        if drive.shape != (self.n,) or not np.all(np.isfinite(drive)):
            raise ValueError("external drive must be finite and match graph size")
        start_tick = self.tick
        slot = start_tick % self._ring_size
        scheduled = self.pending_spikes[slot].copy()
        arrival = self.pending_inputs[slot].copy()
        self.pending_spikes[slot].fill(False)
        self.pending_inputs[slot].fill(0.0)
        arrival += self.graph.propagate(scheduled, self.spec.runtime_synaptic_scale)
        for neuron in np.flatnonzero(self.noise.population_mask):
            if bernoulli(
                self.noise.seed,
                self.noise.stream_id,
                start_tick,
                int(neuron),
                self.noise.threshold,
            ):
                arrival[int(neuron)] += self.noise.current_increment
        end_tick = start_tick + 1
        arrival_slot = (end_tick + self.spec.delay_ticks) % self._ring_size
        spikes = np.zeros(self.n, dtype=np.bool_)
        for neuron in range(self.n):
            current_at_boundary = self.synaptic_current[neuron] + arrival[neuron]
            self.synaptic_current[neuron] = current_at_boundary * self._current_decay
            if start_tick >= self.refractory_until_tick[neuron]:
                evolved_voltage = (
                    self.spec.rest
                    + (self.voltage[neuron] - self.spec.rest) * self._voltage_decay
                    + drive[neuron] * self._held_drive_factor
                    + current_at_boundary * self._current_coupling_factor
                )
                self.voltage[neuron] = evolved_voltage
                if evolved_voltage >= self.spec.threshold:
                    spikes[neuron] = True
                    self.voltage[neuron] = self.spec.reset
                    self.refractory_until_tick[neuron] = end_tick + self.spec.refractory_ticks
                    if self.pending_spikes[arrival_slot, neuron]:
                        raise RuntimeError("fixed-delay ring collision for a repeated source spike")
                    self.pending_spikes[arrival_slot, neuron] = True
            else:
                self.voltage[neuron] = self.spec.reset
        self.tick = end_tick
        return StepResult(start_tick, end_tick, arrival, spikes.copy())
