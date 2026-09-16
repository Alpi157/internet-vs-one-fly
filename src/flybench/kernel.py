"""Restricted deterministic Numba backend for the accepted FlyBench LIF model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any

from numba import njit
import numpy as np

from flybench.model import ModelSpec
from flybench.reference import StepResult


KERNEL_IMPLEMENTATION_ID = "flybench.numba-serial-active-source.v1"


@dataclass(frozen=True, slots=True)
class KernelGraph:
    """Immutable source-major arrays retained without dtype conversion or copying."""

    offsets: np.ndarray
    targets: np.ndarray
    weights: np.ndarray

    def __post_init__(self) -> None:
        offsets = np.asarray(self.offsets)
        targets = np.asarray(self.targets)
        weights = np.asarray(self.weights)
        if offsets.dtype != np.int64 or offsets.ndim != 1 or offsets.size < 2:
            raise ValueError("kernel offsets must be a one-dimensional int64 array")
        if targets.dtype != np.int32 or targets.ndim != 1:
            raise ValueError("kernel targets must be a one-dimensional int32 array")
        if weights.dtype not in (np.dtype("float32"), np.dtype("float64")):
            raise ValueError("kernel weights must be float32 or float64")
        if weights.ndim != 1 or targets.size != weights.size:
            raise ValueError("kernel targets and weights must be aligned")
        if offsets[0] != 0 or int(offsets[-1]) != targets.size:
            raise ValueError("kernel offsets do not span the edge arrays")
        if np.any(offsets[1:] < offsets[:-1]):
            raise ValueError("kernel offsets must be monotonic")
        if targets.size and (np.min(targets) < 0 or np.max(targets) >= offsets.size - 1):
            raise ValueError("kernel target index is outside the graph")
        if not np.all(np.isfinite(weights)):
            raise ValueError("kernel weights must be finite")
        offsets.flags.writeable = False
        targets.flags.writeable = False
        weights.flags.writeable = False
        object.__setattr__(self, "offsets", offsets)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "weights", weights)

    @property
    def n(self) -> int:
        return int(self.offsets.size - 1)


@njit(cache=True)
def _serial_step(
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
) -> tuple[int, int, int, int]:
    """One serial tick; defaults intentionally exclude parallel and fastmath."""

    n = voltage.size
    ring_size = pending_spikes.shape[0]
    slot = tick % ring_size
    active_source_events = 0
    propagated_edge_visits = 0

    for neuron in range(n):
        arrival_increment[neuron] = pending_inputs[slot, neuron]
        pending_inputs[slot, neuron] = 0.0
        spikes[neuron] = False

    # Source-major propagation visits outgoing rows only for scheduled sources.
    for source in range(n):
        if pending_spikes[slot, source]:
            active_source_events += 1
            pending_spikes[slot, source] = False
            start = offsets[source]
            stop = offsets[source + 1]
            for edge in range(start, stop):
                target = targets[edge]
                arrival_increment[target] += weights[edge] * runtime_synaptic_scale
                propagated_edge_visits += 1

    end_tick = tick + 1
    spike_count = 0
    collision = 0
    arrival_slot = (end_tick + delay_ticks) % ring_size
    for neuron in range(n):
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
                spike_count += 1
                voltage[neuron] = reset
                refractory_until_tick[neuron] = end_tick + refractory_ticks
                if pending_spikes[arrival_slot, neuron]:
                    collision = 1
                pending_spikes[arrival_slot, neuron] = True
        else:
            # Current evolves throughout refractory while voltage stays reset.
            voltage[neuron] = reset
    return active_source_events, propagated_edge_visits, spike_count, collision


class KernelState:
    """Independently owned mutable float64 state for the restricted Numba backend."""

    def __init__(self, spec: ModelSpec, graph: Any):
        if graph.n <= 0:
            raise ValueError("kernel graph must contain at least one neuron")
        self.spec = spec
        self.graph = graph
        self.seed = spec.seed
        self._voltage_decay = math.exp(-spec.neural_dt_ms / spec.tau_m_ms)
        self._current_decay = math.exp(-spec.neural_dt_ms / spec.tau_s_ms)
        self._held_drive_factor = 1.0 - self._voltage_decay
        if spec.tau_m_ms == spec.tau_s_ms:
            self._current_coupling_factor = (
                spec.neural_dt_ms / spec.tau_m_ms
            ) * self._voltage_decay
        else:
            self._current_coupling_factor = (
                spec.tau_s_ms
                / (spec.tau_s_ms - spec.tau_m_ms)
                * (self._current_decay - self._voltage_decay)
            )
        self.reset()

    @property
    def n(self) -> int:
        return int(self.graph.n)

    @property
    def time_ms(self) -> float:
        return self.tick * self.spec.neural_dt_ms

    def reset(self, *, seed: int | None = None) -> None:
        if seed is not None:
            if type(seed) is not int or seed < 0:
                raise ValueError("seed must be a nonnegative integer")
            self.seed = seed
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
        self.rng = np.random.Generator(np.random.PCG64(self.seed))
        self.neural_timesteps = 0
        self.all_neuron_updates = 0
        self.total_spikes = 0
        self.active_source_events = 0
        self.propagated_edge_visits = 0
        self.active_source_count_sum = 0
        self.max_active_source_count = 0

    def queue_boundary_input(self, increment: np.ndarray, *, arrival_tick: int) -> None:
        values = np.asarray(increment, dtype=np.float64)
        if values.shape != (self.n,) or not np.all(np.isfinite(values)):
            raise ValueError("queued input must be one finite value per neuron")
        if type(arrival_tick) is not int:
            raise ValueError("arrival_tick must be an integer")
        distance = arrival_tick - self.tick
        if distance < 0 or distance > self.spec.delay_ticks:
            raise ValueError("arrival boundary lies outside the fixed-delay ring horizon")
        self.pending_inputs[arrival_tick % self._ring_size] += values

    def step(self, external_drive: np.ndarray | float) -> StepResult:
        drive = np.asarray(external_drive, dtype=np.float64)
        if drive.ndim == 0:
            self._drive.fill(float(drive))
            drive = self._drive
        if drive.shape != (self.n,) or not np.all(np.isfinite(drive)):
            raise ValueError("external drive must be finite and match graph size")
        if not drive.flags.c_contiguous:
            drive = np.ascontiguousarray(drive)
        start_tick = self.tick
        active, edges, spike_count, collision = _serial_step(
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
        )
        if collision:
            raise RuntimeError("fixed-delay ring collision for a repeated source spike")
        self.tick = start_tick + 1
        self.neural_timesteps += 1
        self.all_neuron_updates += self.n
        self.total_spikes += spike_count
        self.active_source_events += active
        self.propagated_edge_visits += edges
        self.active_source_count_sum += active
        self.max_active_source_count = max(self.max_active_source_count, active)
        return StepResult(
            start_tick=start_tick,
            end_tick=self.tick,
            arrival_increment=self._arrival_increment.copy(),
            spikes=self._spikes.copy(),
        )

    def work_counters(self) -> dict[str, int | float]:
        mean = (
            self.active_source_count_sum / self.neural_timesteps
            if self.neural_timesteps
            else 0.0
        )
        return {
            "neural_timesteps": self.neural_timesteps,
            "all_neuron_updates": self.all_neuron_updates,
            "total_spikes": self.total_spikes,
            "active_presynaptic_source_events": self.active_source_events,
            "propagated_outgoing_edge_visits": self.propagated_edge_visits,
            "active_source_count_sum": self.active_source_count_sum,
            "mean_active_source_count_per_neural_step": mean,
            "max_active_source_count_per_neural_step": self.max_active_source_count,
        }

    def private_state_bytes(self) -> dict[str, int]:
        arrays = {
            "voltage": self.voltage,
            "synaptic_current": self.synaptic_current,
            "refractory_until_tick": self.refractory_until_tick,
            "pending_spikes": self.pending_spikes,
            "pending_inputs": self.pending_inputs,
            "arrival_increment_scratch": self._arrival_increment,
            "spike_scratch": self._spikes,
            "drive_scratch": self._drive,
        }
        result = {name: int(value.nbytes) for name, value in arrays.items()}
        result["delay_ring"] = result["pending_spikes"] + result["pending_inputs"]
        result["total"] = sum(
            size for name, size in result.items() if name != "delay_ring"
        )
        return result

    def snapshot(self) -> dict[str, object]:
        return {
            "tick": self.tick,
            "seed": self.seed,
            "voltage": self.voltage.copy(),
            "synaptic_current": self.synaptic_current.copy(),
            "refractory_until_tick": self.refractory_until_tick.copy(),
            "pending_spikes": self.pending_spikes.copy(),
            "pending_inputs": self.pending_inputs.copy(),
            "rng_state": deepcopy(self.rng.bit_generator.state),
        }


def warm_kernel() -> None:
    """Compile the one supported signature on a small deterministic fixture."""

    from flybench.model import BASE_MODEL_PROFILE_SHA256

    spec = ModelSpec(
        base_model_profile_sha256=BASE_MODEL_PROFILE_SHA256,
        numerical_criteria_sha256="0" * 64,
        tau_m_ms=20.0,
        tau_s_ms=5.0,
        rest=0.0,
        reset=0.0,
        threshold=1.0,
        refractory_ms=2.0,
        delay_ms=1.0,
        neural_dt_ms=0.5,
        runtime_synaptic_scale=0.001,
        seed=0,
    )
    graph = KernelGraph(
        offsets=np.array([0, 1, 1], dtype=np.int64),
        targets=np.array([1], dtype=np.int32),
        weights=np.array([1.0], dtype=np.float32),
    )
    KernelState(spec, graph).step(0.0)


def kernel_configuration() -> dict[str, object]:
    """Expose inspectable compiler options for parity evidence."""

    return {
        "implementation_id": KERNEL_IMPLEMENTATION_ID,
        "decorator": "numba.njit(cache=True)",
        "parallel": bool(_serial_step.targetoptions.get("parallel", False)),
        "fastmath": bool(_serial_step.targetoptions.get("fastmath", False)),
        "targetoptions": dict(_serial_step.targetoptions),
    }
