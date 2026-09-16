"""Readable deterministic float64 oracle for the normalized FlyBench LIF model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from flybench.model import ModelSpec


def exact_linear_substep(
    voltage: np.ndarray | float,
    synaptic_current: np.ndarray | float,
    external_drive: np.ndarray | float,
    *,
    dt_ms: float,
    tau_m_ms: float,
    tau_s_ms: float,
    rest: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Evolve the linear membrane/current equations exactly for one held-input interval."""

    v0 = np.asarray(voltage, dtype=np.float64)
    i0 = np.asarray(synaptic_current, dtype=np.float64)
    u = np.asarray(external_drive, dtype=np.float64)
    if not all(
        math.isfinite(value) and value > 0 for value in (dt_ms, tau_m_ms, tau_s_ms)
    ):
        raise ValueError("dt and time constants must be finite and positive")
    if not np.all(np.isfinite(v0)) or not np.all(np.isfinite(i0)) or not np.all(
        np.isfinite(u)
    ):
        raise ValueError("reference inputs must be finite")

    em = math.exp(-dt_ms / tau_m_ms)
    es = math.exp(-dt_ms / tau_s_ms)
    i1 = i0 * es
    if tau_m_ms == tau_s_ms:
        coupled = i0 * (dt_ms / tau_m_ms) * em
    else:
        coupled = i0 * tau_s_ms / (tau_s_ms - tau_m_ms) * (es - em)
    v1 = rest + (v0 - rest) * em + u * (1.0 - em) + coupled
    return np.asarray(v1, dtype=np.float64), np.asarray(i1, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class ReferenceGraph:
    """Small immutable source-major compressed adjacency used by the oracle."""

    offsets: np.ndarray
    targets: np.ndarray
    weights: np.ndarray

    def __post_init__(self) -> None:
        offsets = np.array(self.offsets, dtype=np.int64, copy=True)
        targets64 = np.asarray(self.targets)
        if targets64.dtype.kind not in "iu":
            raise ValueError("targets must be integers")
        targets = np.array(targets64, dtype=np.int32, copy=True)
        weights = np.array(self.weights, dtype=np.float64, copy=True)
        if offsets.ndim != 1 or offsets.size < 1 or offsets[0] != 0:
            raise ValueError("offsets must be one-dimensional and start at zero")
        if np.any(offsets[1:] < offsets[:-1]):
            raise ValueError("offsets must be monotonic")
        if targets.ndim != 1 or weights.ndim != 1 or targets.size != weights.size:
            raise ValueError("targets and weights must be aligned one-dimensional arrays")
        if int(offsets[-1]) != targets.size:
            raise ValueError("final offset must equal edge count")
        if np.any(targets < 0) or np.any(targets >= offsets.size - 1):
            raise ValueError("target index is outside graph range")
        if not np.all(np.isfinite(weights)):
            raise ValueError("weights must be finite")
        for source in range(offsets.size - 1):
            start, stop = int(offsets[source]), int(offsets[source + 1])
            if stop - start > 1 and np.any(
                targets[start + 1 : stop] <= targets[start : stop - 1]
            ):
                raise ValueError("targets must be strictly increasing within each source row")
        offsets.flags.writeable = False
        targets.flags.writeable = False
        weights.flags.writeable = False
        object.__setattr__(self, "offsets", offsets)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "weights", weights)

    @property
    def n(self) -> int:
        return int(self.offsets.size - 1)

    @classmethod
    def empty(cls, n: int) -> "ReferenceGraph":
        if type(n) is not int or n < 0:
            raise ValueError("n must be a nonnegative integer")
        return cls(
            offsets=np.zeros(n + 1, dtype=np.int64),
            targets=np.empty(0, dtype=np.int32),
            weights=np.empty(0, dtype=np.float64),
        )

    @classmethod
    def from_edges(
        cls, n: int, edges: Iterable[tuple[int, int, float]]
    ) -> "ReferenceGraph":
        if type(n) is not int or n < 0:
            raise ValueError("n must be a nonnegative integer")
        aggregated: dict[tuple[int, int], float] = {}
        for source, target, weight in edges:
            if type(source) is not int or type(target) is not int:
                raise ValueError("source and target must be integer indices")
            if not (0 <= source < n and 0 <= target < n):
                raise ValueError("edge endpoint is outside graph range")
            if not math.isfinite(weight):
                raise ValueError("edge weight must be finite")
            key = (source, target)
            aggregated[key] = aggregated.get(key, 0.0) + float(weight)
        ordered = sorted(aggregated.items())
        offsets = np.zeros(n + 1, dtype=np.int64)
        targets = np.empty(len(ordered), dtype=np.int32)
        weights = np.empty(len(ordered), dtype=np.float64)
        for index, ((source, target), weight) in enumerate(ordered):
            offsets[source + 1] += 1
            targets[index] = target
            weights[index] = weight
        np.cumsum(offsets, out=offsets)
        return cls(offsets=offsets, targets=targets, weights=weights)

    def propagate(self, spikes: np.ndarray, runtime_synaptic_scale: float) -> np.ndarray:
        """Compute A.T @ spikes by deterministic source-major traversal."""

        spike_vector = np.asarray(spikes, dtype=np.bool_)
        if spike_vector.shape != (self.n,):
            raise ValueError("spike vector shape does not match graph")
        if not math.isfinite(runtime_synaptic_scale) or runtime_synaptic_scale <= 0:
            raise ValueError("runtime_synaptic_scale must be finite and positive")
        increments = np.zeros(self.n, dtype=np.float64)
        for source in np.flatnonzero(spike_vector):
            start = int(self.offsets[source])
            stop = int(self.offsets[source + 1])
            for edge in range(start, stop):
                increments[int(self.targets[edge])] += (
                    float(self.weights[edge]) * runtime_synaptic_scale
                )
        return increments


@dataclass(frozen=True, slots=True)
class StepResult:
    start_tick: int
    end_tick: int
    arrival_increment: np.ndarray
    spikes: np.ndarray


class ReferenceState:
    """One independently owned mutable reference-neural state."""

    def __init__(self, spec: ModelSpec, graph: ReferenceGraph):
        if graph.n <= 0:
            raise ValueError("reference graph must contain at least one neuron")
        self.spec = spec
        self.graph = graph
        self.seed = spec.seed
        self.reset()

    @property
    def n(self) -> int:
        return self.graph.n

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
        self.rng = np.random.Generator(np.random.PCG64(self.seed))

    def queue_boundary_input(self, increment: np.ndarray, *, arrival_tick: int) -> None:
        """Queue a fixture/external synaptic-current jump at an exact near boundary."""

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
        """Advance exactly one interval under flybench.neural-order.v1."""

        drive = np.asarray(external_drive, dtype=np.float64)
        if drive.ndim == 0:
            drive = np.full(self.n, float(drive), dtype=np.float64)
        if drive.shape != (self.n,) or not np.all(np.isfinite(drive)):
            raise ValueError("external drive must be finite and match graph size")

        start_tick = self.tick
        slot = start_tick % self._ring_size
        scheduled_spikes = self.pending_spikes[slot].copy()
        direct_increment = self.pending_inputs[slot].copy()
        self.pending_spikes[slot].fill(False)
        self.pending_inputs[slot].fill(0.0)
        arrival_increment = direct_increment + self.graph.propagate(
            scheduled_spikes, self.spec.runtime_synaptic_scale
        )
        current_at_boundary = self.synaptic_current + arrival_increment

        eligible = start_tick >= self.refractory_until_tick
        evolved_voltage, evolved_current = exact_linear_substep(
            self.voltage,
            current_at_boundary,
            drive,
            dt_ms=self.spec.neural_dt_ms,
            tau_m_ms=self.spec.tau_m_ms,
            tau_s_ms=self.spec.tau_s_ms,
            rest=self.spec.rest,
        )
        self.synaptic_current[:] = evolved_current
        self.voltage[eligible] = evolved_voltage[eligible]
        self.voltage[~eligible] = self.spec.reset

        end_tick = start_tick + 1
        spikes = eligible & (self.voltage >= self.spec.threshold)
        if np.any(spikes):
            self.voltage[spikes] = self.spec.reset
            self.refractory_until_tick[spikes] = (
                end_tick + self.spec.refractory_ticks
            )
            arrival_tick = end_tick + self.spec.delay_ticks
            arrival_slot = arrival_tick % self._ring_size
            if np.any(self.pending_spikes[arrival_slot] & spikes):
                raise RuntimeError("fixed-delay ring collision for a repeated source spike")
            self.pending_spikes[arrival_slot] |= spikes

        self.tick = end_tick
        return StepResult(
            start_tick=start_tick,
            end_tick=end_tick,
            arrival_increment=arrival_increment,
            spikes=spikes.copy(),
        )

    def snapshot(self) -> dict[str, object]:
        """Return a complete copy suitable for deterministic reset/state tests."""

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
