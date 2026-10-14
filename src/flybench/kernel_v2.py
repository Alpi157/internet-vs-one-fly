"""Restricted Numba v2 kernel with counter-based background noise."""

from __future__ import annotations

import math

from numba import njit
import numpy as np

from flybench.kernel import KernelGraph
from flybench.model import ModelSpec
from flybench.reference import StepResult
from flybench.reference_v2 import NoiseSpec


@njit(cache=True)
def _counter_u32_v1(seed: int, stream: int, tick: int, index: int) -> np.uint32:
    value = np.uint32(seed) + np.uint32(0x9E3779B9)
    value = np.uint32(value ^ np.uint32(np.uint32(stream) * np.uint32(0x85EBCA6B)))
    value = np.uint32(value + np.uint32(np.uint32(tick) * np.uint32(0xC2B2AE35)))
    value = np.uint32(value ^ np.uint32(np.uint32(index) * np.uint32(0x27D4EB2F)))
    value = np.uint32(value ^ np.uint32(value >> np.uint32(16)))
    value = np.uint32(value * np.uint32(0x7FEB352D))
    value = np.uint32(value ^ np.uint32(value >> np.uint32(15)))
    value = np.uint32(value * np.uint32(0x846CA68B))
    return np.uint32(value ^ np.uint32(value >> np.uint32(16)))


@njit(cache=True)
def _fmix32(value: int) -> np.uint32:
    x = np.uint32(value)
    x = np.uint32(x ^ (x >> np.uint32(16)))
    x = np.uint32(x * np.uint32(0x85EBCA6B))
    x = np.uint32(x ^ (x >> np.uint32(13)))
    x = np.uint32(x * np.uint32(0xC2B2AE35))
    return np.uint32(x ^ (x >> np.uint32(16)))


@njit(cache=True)
def _counter_u32(seed: int, stream: int, tick: int, index: int) -> np.uint32:
    h = _fmix32(np.uint32(seed) + np.uint32(0x9E3779B9))
    h = _fmix32(np.uint32(h ^ np.uint32(stream)))
    h = _fmix32(np.uint32(h + np.uint32(tick)))
    return _fmix32(np.uint32(h ^ np.uint32(index)))


@njit(cache=True)
def _serial_step_v2(
    offsets: np.ndarray,
    targets: np.ndarray,
    weights: np.ndarray,
    voltage: np.ndarray,
    synaptic_current: np.ndarray,
    refractory_until_tick: np.ndarray,
    pending_spikes: np.ndarray,
    pending_inputs: np.ndarray,
    arrival_increment: np.ndarray,
    spikes: np.ndarray,
    drive: np.ndarray,
    tick: int,
    runtime_synaptic_scale: float,
    current_decay: float,
    voltage_decay: float,
    held_drive_factor: float,
    current_coupling_factor: float,
    rest: float,
    reset: float,
    threshold: float,
    refractory_ticks: int,
    delay_ticks: int,
    noise_seed: int,
    noise_stream: int,
    noise_threshold: int,
    noise_increment: float,
    noise_population: np.ndarray,
) -> int:
    n = voltage.size
    ring_size = pending_spikes.shape[0]
    slot = tick % ring_size
    for neuron in range(n):
        arrival_increment[neuron] = pending_inputs[slot, neuron]
        pending_inputs[slot, neuron] = 0.0
        spikes[neuron] = False
    for source in range(n):
        if pending_spikes[slot, source]:
            pending_spikes[slot, source] = False
            for edge in range(offsets[source], offsets[source + 1]):
                arrival_increment[targets[edge]] += weights[edge] * runtime_synaptic_scale
    end_tick = tick + 1
    arrival_slot = (end_tick + delay_ticks) % ring_size
    collision = 0
    for neuron in range(n):
        if noise_population[neuron] and np.uint64(
            _counter_u32(noise_seed, noise_stream, tick, neuron)
        ) < np.uint64(noise_threshold):
            arrival_increment[neuron] += noise_increment
        current_at_boundary = synaptic_current[neuron] + arrival_increment[neuron]
        synaptic_current[neuron] = current_at_boundary * current_decay
        if tick >= refractory_until_tick[neuron]:
            evolved_voltage = (
                rest
                + (voltage[neuron] - rest) * voltage_decay
                + drive[neuron] * held_drive_factor
                + current_at_boundary * current_coupling_factor
            )
            voltage[neuron] = evolved_voltage
            if evolved_voltage >= threshold:
                spikes[neuron] = True
                voltage[neuron] = reset
                refractory_until_tick[neuron] = end_tick + refractory_ticks
                if pending_spikes[arrival_slot, neuron]:
                    collision = 1
                pending_spikes[arrival_slot, neuron] = True
        else:
            voltage[neuron] = reset
    return collision


class KernelStateV2:
    def __init__(self, spec: ModelSpec, graph: KernelGraph, noise: NoiseSpec):
        if graph.n <= 0 or noise.population_mask.shape != (graph.n,):
            raise ValueError("graph and noise population sizes must match")
        self.spec = spec
        self.graph = (
            graph
            if graph.weights.dtype == np.float64
            else KernelGraph(graph.offsets, graph.targets, graph.weights.astype(np.float64))
        )
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
        self._arrival_increment = np.zeros(self.n, dtype=np.float64)
        self._spikes = np.zeros(self.n, dtype=np.bool_)
        self._drive = np.zeros(self.n, dtype=np.float64)

    def step(self, external_drive: np.ndarray | float) -> StepResult:
        drive = np.asarray(external_drive, dtype=np.float64)
        if drive.ndim == 0:
            self._drive.fill(float(drive))
            drive = self._drive
        if drive.shape != (self.n,) or not np.all(np.isfinite(drive)):
            raise ValueError("external drive must be finite and match graph size")
        if not drive.flags.c_contiguous:
            drive = np.ascontiguousarray(drive)
        if not 0 <= self.tick < 2**32 - 1:
            raise ValueError("u32 clock exhausted")
        start_tick = self.tick
        collision = _serial_step_v2(
            self.graph.offsets,
            self.graph.targets,
            self.graph.weights,
            self.voltage,
            self.synaptic_current,
            self.refractory_until_tick,
            self.pending_spikes,
            self.pending_inputs,
            self._arrival_increment,
            self._spikes,
            drive,
            start_tick,
            self.spec.runtime_synaptic_scale,
            self._current_decay,
            self._voltage_decay,
            self._held_drive_factor,
            self._current_coupling_factor,
            self.spec.rest,
            self.spec.reset,
            self.spec.threshold,
            self.spec.refractory_ticks,
            self.spec.delay_ticks,
            self.noise.seed,
            self.noise.stream_id,
            self.noise.threshold,
            self.noise.current_increment,
            self.noise.population_mask,
        )
        if collision:
            raise RuntimeError("fixed-delay ring collision for a repeated source spike")
        self.tick = start_tick + 1
        return StepResult(
            start_tick,
            self.tick,
            self._arrival_increment.copy(),
            self._spikes.copy(),
        )


@njit(cache=True)
def _interval_counts(offsets, targets, weights, voltage, current, refractory,
                     pending_spikes, pending_inputs, arrivals, spikes, drive, tick,
                     scale, current_decay, voltage_decay, held_factor, coupling,
                     rest, reset, threshold, refractory_ticks, delay_ticks,
                     seed, stream, noise_threshold, noise_increment, population, steps):
    counts = np.zeros(voltage.size, dtype=np.int64)
    for i in range(steps):
        collision = _serial_step_v2(offsets, targets, weights, voltage, current, refractory,
            pending_spikes, pending_inputs, arrivals, spikes, drive, tick+i, scale,
            current_decay, voltage_decay, held_factor, coupling, rest, reset, threshold,
            refractory_ticks, delay_ticks, seed, stream, noise_threshold, noise_increment, population)
        if collision:
            raise RuntimeError('fixed-delay ring collision')
        for neuron in range(voltage.size):
            counts[neuron] += int(spikes[neuron])
    return counts


def interval_counts(state: KernelStateV2, drive: np.ndarray, steps: int = 20) -> np.ndarray:
    """Advance using precisely the same serial step, counting spikes per neuron."""
    if type(steps) is not int or steps < 1 or state.tick + steps >= 2**32:
        raise ValueError('invalid interval or exhausted u32 clock')
    if drive.shape != (state.n,) or not np.all(np.isfinite(drive)):
        raise ValueError('invalid drive')
    s = state.spec
    result = _interval_counts(state.graph.offsets, state.graph.targets, state.graph.weights,
        state.voltage, state.synaptic_current, state.refractory_until_tick,
        state.pending_spikes, state.pending_inputs, state._arrival_increment, state._spikes,
        drive, state.tick, s.runtime_synaptic_scale, state._current_decay, state._voltage_decay,
        state._held_drive_factor, state._current_coupling_factor, s.rest, s.reset, s.threshold,
        s.refractory_ticks, s.delay_ticks, state.noise.seed, state.noise.stream_id,
        state.noise.threshold, state.noise.current_increment, state.noise.population_mask, steps)
    state.tick += steps
    return result
