from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from flybench.bench import NORMAL_SCENARIOS, scripted_observation
from flybench.catch import load_environment_config
from flybench.kernel import KernelState, kernel_configuration
from flybench.model import ModelSpec, load_candidate_model_spec
from flybench.reference import ReferenceGraph, ReferenceState, exact_linear_substep
from flybench.runner import Runner, build_direct_visual_to_dnp01_zero, load_graph


ROOT = Path(__file__).resolve().parents[1]
ATOL = 1e-10
RTOL = 1e-10


def spec(*, seed: int = 17) -> ModelSpec:
    return load_candidate_model_spec(
        neural_dt_ms=0.5,
        runtime_synaptic_scale=0.001,
        seed=seed,
        model_profile_path=ROOT / "profiles/model-v0.1.json",
        criteria_path=ROOT / "profiles/numerical-criteria-v0.1.json",
    )


def states(graph: ReferenceGraph, *, seed: int = 17) -> tuple[ReferenceState, KernelState]:
    model = spec(seed=seed)
    return ReferenceState(model, graph), KernelState(model, graph)


def assert_state_equal(reference: ReferenceState, kernel: KernelState) -> None:
    assert reference.tick == kernel.tick
    assert reference.seed == kernel.seed
    np.testing.assert_allclose(reference.voltage, kernel.voltage, atol=ATOL, rtol=RTOL)
    np.testing.assert_allclose(
        reference.synaptic_current, kernel.synaptic_current, atol=ATOL, rtol=RTOL
    )
    np.testing.assert_array_equal(
        reference.refractory_until_tick, kernel.refractory_until_tick
    )
    np.testing.assert_array_equal(reference.pending_spikes, kernel.pending_spikes)
    np.testing.assert_array_equal(reference.pending_inputs, kernel.pending_inputs)
    assert reference.rng.bit_generator.state == kernel.rng.bit_generator.state


def paired_step(
    reference: ReferenceState, kernel: KernelState, drive: np.ndarray | float
) -> tuple[np.ndarray, np.ndarray]:
    expected = reference.step(drive)
    observed = kernel.step(drive)
    assert expected.start_tick == observed.start_tick
    assert expected.end_tick == observed.end_tick
    np.testing.assert_array_equal(expected.spikes, observed.spikes)
    np.testing.assert_allclose(
        expected.arrival_increment, observed.arrival_increment, atol=ATOL, rtol=RTOL
    )
    assert_state_equal(reference, kernel)
    return expected.spikes, observed.spikes


def test_zero_input_analytical_decay() -> None:
    reference, kernel = states(ReferenceGraph.empty(3))
    initial_voltage = np.array([0.2, -0.1, 0.7])
    initial_current = np.array([0.4, -0.2, 0.1])
    reference.voltage[:] = kernel.voltage[:] = initial_voltage
    reference.synaptic_current[:] = kernel.synaptic_current[:] = initial_current
    expected_v, expected_i = exact_linear_substep(
        initial_voltage, initial_current, 0.0, dt_ms=0.5, tau_m_ms=20.0, tau_s_ms=5.0
    )
    paired_step(reference, kernel, 0.0)
    np.testing.assert_allclose(kernel.voltage, expected_v, atol=ATOL, rtol=RTOL)
    np.testing.assert_allclose(kernel.synaptic_current, expected_i, atol=ATOL, rtol=RTOL)


def test_constant_held_drive() -> None:
    reference, kernel = states(ReferenceGraph.empty(4))
    drive = np.array([0.0, 0.5, 2.0, -0.25])
    for _ in range(40):
        paired_step(reference, kernel, drive)


def test_synaptic_current_decay() -> None:
    reference, kernel = states(ReferenceGraph.empty(3))
    reference.synaptic_current[:] = kernel.synaptic_current[:] = [1.0, -2.0, 0.5]
    for _ in range(12):
        paired_step(reference, kernel, 0.0)


def test_signed_simultaneous_arrivals() -> None:
    graph = ReferenceGraph.from_edges(4, [(0, 3, 5.0), (1, 3, -2.0), (2, 3, -1.0)])
    reference, kernel = states(graph)
    reference.pending_spikes[0, :3] = True
    kernel.pending_spikes[0, :3] = True
    expected, observed = paired_step(reference, kernel, 0.0)
    assert not np.any(expected) and not np.any(observed)
    assert kernel.synaptic_current[3] != 0.0


def test_directed_source_major_fanout() -> None:
    graph = ReferenceGraph.from_edges(
        5, [(0, 1, 1.0), (0, 2, 2.0), (0, 4, 4.0), (3, 0, -3.0)]
    )
    reference, kernel = states(graph)
    reference.pending_spikes[0, [0, 3]] = True
    kernel.pending_spikes[0, [0, 3]] = True
    paired_step(reference, kernel, 0.0)
    assert kernel.work_counters()["propagated_outgoing_edge_visits"] == 4


def test_exact_one_ms_delay() -> None:
    graph = ReferenceGraph.from_edges(2, [(0, 1, 1000.0)])
    reference, kernel = states(graph)
    drive = np.array([100.0, 0.0])
    spikes, _ = paired_step(reference, kernel, drive)
    assert np.flatnonzero(spikes).tolist() == [0]
    paired_step(reference, kernel, 0.0)
    paired_step(reference, kernel, 0.0)
    assert kernel.synaptic_current[1] == 0.0
    paired_step(reference, kernel, 0.0)
    assert kernel.synaptic_current[1] > 0.0


def test_threshold_equality_and_reset() -> None:
    reference, kernel = states(ReferenceGraph.empty(1))
    exactly_one_before_decay = 1.0 / math.exp(-0.5 / 20.0)
    reference.voltage[0] = kernel.voltage[0] = exactly_one_before_decay
    spikes, _ = paired_step(reference, kernel, 0.0)
    assert spikes.tolist() == [True]
    assert reference.voltage[0] == kernel.voltage[0] == 0.0


def test_refractory_evolution_with_continued_current() -> None:
    reference, kernel = states(ReferenceGraph.empty(1))
    reference.voltage[0] = kernel.voltage[0] = 1.0 / math.exp(-0.5 / 20.0)
    paired_step(reference, kernel, 0.0)
    reference.synaptic_current[0] = kernel.synaptic_current[0] = 2.0
    previous = kernel.synaptic_current[0]
    for _ in range(3):
        paired_step(reference, kernel, 0.0)
        assert kernel.voltage[0] == 0.0
        assert abs(kernel.synaptic_current[0]) < abs(previous)
        previous = kernel.synaptic_current[0]


def test_delay_ring_wraparound() -> None:
    graph = ReferenceGraph.from_edges(2, [(0, 1, 2.0)])
    reference, kernel = states(graph)
    for _ in range(8):
        if reference.tick in (0, 4):
            slot = reference.tick % reference.pending_spikes.shape[0]
            reference.pending_spikes[slot, 0] = True
            kernel.pending_spikes[slot, 0] = True
        paired_step(reference, kernel, 0.0)


def test_repeated_reset() -> None:
    reference, kernel = states(ReferenceGraph.from_edges(2, [(0, 1, 2.0)]), seed=44)
    pristine_reference = reference.snapshot()
    pristine_kernel = kernel.snapshot()
    for _ in range(12):
        paired_step(reference, kernel, np.array([4.0, 0.0]))
    reference.reset(seed=44)
    kernel.reset(seed=44)
    for name in pristine_reference:
        if isinstance(pristine_reference[name], np.ndarray):
            np.testing.assert_array_equal(reference.snapshot()[name], pristine_reference[name])
            np.testing.assert_array_equal(kernel.snapshot()[name], pristine_kernel[name])
        else:
            assert reference.snapshot()[name] == pristine_reference[name]
            assert kernel.snapshot()[name] == pristine_kernel[name]


def test_independent_state_instances() -> None:
    graph = ReferenceGraph.empty(2)
    first = KernelState(spec(), graph)
    second = KernelState(spec(), graph)
    first.voltage[0] = 0.5
    first.pending_spikes[0, 1] = True
    assert second.voltage[0] == 0.0
    assert not np.any(second.pending_spikes)
    assert first.rng is not second.rng


def test_same_explicit_seed_and_state_ownership() -> None:
    graph = ReferenceGraph.empty(2)
    reference, kernel = states(graph, seed=901)
    assert reference.rng is not kernel.rng
    assert reference.rng.bit_generator.state == kernel.rng.bit_generator.state
    assert copy.deepcopy(reference.rng.bit_generator.state) == kernel.rng.bit_generator.state
    for drive in (0.0, 1.0, np.array([0.25, -0.5])):
        paired_step(reference, kernel, drive)


def test_sparse_active_source_propagation_counts_only_active_rows() -> None:
    graph = ReferenceGraph.from_edges(
        20,
        [(source, (source + 1) % 20, 1.0) for source in range(20)]
        + [(7, 11, 2.0), (7, 13, 3.0)],
    )
    reference, kernel = states(graph)
    reference.pending_spikes[0, 7] = True
    kernel.pending_spikes[0, 7] = True
    paired_step(reference, kernel, 0.0)
    work = kernel.work_counters()
    assert work["all_neuron_updates"] == 20
    assert work["active_presynaptic_source_events"] == 1
    assert work["propagated_outgoing_edge_visits"] == 3
    assert work["propagated_outgoing_edge_visits"] < graph.weights.size


def test_fanout_contains_positive_and_negative_weights() -> None:
    graph = ReferenceGraph.from_edges(4, [(0, 1, 2.0), (0, 2, -3.0), (0, 3, 0.5)])
    reference, kernel = states(graph)
    reference.pending_spikes[0, 0] = True
    kernel.pending_spikes[0, 0] = True
    paired_step(reference, kernel, 0.0)
    assert kernel.synaptic_current[1] > 0
    assert kernel.synaptic_current[2] < 0
    assert kernel.synaptic_current[3] > 0


def test_reference_kernel_equality_over_multiple_consecutive_spikes() -> None:
    graph = ReferenceGraph.from_edges(
        4, [(0, 1, 80.0), (1, 2, 60.0), (2, 3, -40.0), (3, 0, 20.0)]
    )
    reference, kernel = states(graph)
    spike_log_reference: list[tuple[int, tuple[int, ...]]] = []
    spike_log_kernel: list[tuple[int, tuple[int, ...]]] = []
    for tick in range(120):
        drive = np.array([4.0 if tick < 80 else 0.0, 2.0, 1.5, 0.25])
        expected = reference.step(drive)
        observed = kernel.step(drive)
        spike_log_reference.append((expected.end_tick, tuple(np.flatnonzero(expected.spikes))))
        spike_log_kernel.append((observed.end_tick, tuple(np.flatnonzero(observed.spikes))))
        np.testing.assert_array_equal(expected.spikes, observed.spikes)
        assert_state_equal(reference, kernel)
    assert spike_log_reference == spike_log_kernel
    assert sum(bool(ids) for _, ids in spike_log_reference) > 1


def test_no_unsafe_numba_fastmath_or_parallel_configuration() -> None:
    configuration = kernel_configuration()
    assert configuration["parallel"] is False
    assert configuration["fastmath"] is False
    assert configuration["targetoptions"].get("parallel", False) is False
    assert configuration["targetoptions"].get("fastmath", False) is False


def _assert_runner_boundary(reference: Runner, kernel: Runner) -> None:
    assert reference.control_tick == kernel.control_tick
    assert reference.held_command == kernel.held_command
    assert reference.command_control_ticks == kernel.command_control_ticks
    assert reference.dnp01_spikes == kernel.dnp01_spikes
    assert reference.environment.snapshot() == kernel.environment.snapshot()
    assert_state_equal(reference.neural, kernel.neural)
    left = reference.interval_records[-1]
    right = kernel.interval_records[-1]
    for key in (
        "start_control_tick",
        "end_control_tick",
        "start_neural_tick",
        "end_neural_tick",
        "phase_order",
        "dnp01_spikes",
        "all_population_spike_count",
        "previously_held_command",
        "decoded_next_command",
        "impacts",
        "finite_state",
    ):
        assert left[key] == right[key]


@pytest.mark.parametrize(
    ("scenario", "mode"),
    [(scenario, "normal") for scenario in NORMAL_SCENARIOS]
    + [("standard looming", "output_clamp"), ("standard looming", "pathway")],
)
def test_circuit_end_to_end_reference_kernel_parity(scenario: str, mode: str) -> None:
    profile = json.loads((ROOT / "profiles/looming-controls.json").read_text())
    bundle = load_graph(ROOT / "data/compiled/escape")
    model = spec(seed=20260916)
    intervention = (
        build_direct_visual_to_dnp01_zero(
            bundle, ROOT / "profiles/intervention-direct-visual-to-dnp01-zero-v0.1.json"
        )
        if mode == "pathway"
        else None
    )
    arguments = dict(
        peak_sensory_external_drive=4.0,
        environment_config=load_environment_config(ROOT / "profiles/environment-v0.1.json"),
        environment_seed=20260917,
        output_clamp=mode == "output_clamp",
        intervention=intervention,
    )
    reference = Runner(bundle, model, backend="reference", **arguments)
    kernel = Runner(bundle, model, backend="kernel", **arguments)
    for tick in range(80):
        observation, impact = scripted_observation(profile, scenario, tick)
        reference.advance_control_interval(observation, impact_at_end=impact)
        kernel.advance_control_interval(observation, impact_at_end=impact)
        _assert_runner_boundary(reference, kernel)
    left = reference.finish_run()
    right = kernel.finish_run()
    for key in (
        "control_intervals",
        "control_tick",
        "neural_tick",
        "dnp01_spike_count",
        "dnp01_spikes",
        "escape_command_count",
        "escape_command_control_ticks",
        "impacts",
        "finite_state",
    ):
        assert left[key] == right[key]


def test_graph_arrays_remain_read_only_and_unmodified() -> None:
    bundle = load_graph(ROOT / "data/compiled/escape")
    before = hashlib.sha256(bundle.graph.weights.tobytes()).hexdigest()
    runner = Runner(
        bundle,
        spec(seed=20260916),
        peak_sensory_external_drive=4.0,
        environment_config=load_environment_config(ROOT / "profiles/environment-v0.1.json"),
        environment_seed=20260917,
        backend="kernel",
    )
    runner.advance_control_interval(scripted_observation(
        json.loads((ROOT / "profiles/looming-controls.json").read_text()),
        "standard looming",
        20,
    )[0])
    assert bundle.graph.offsets.flags.writeable is False
    assert bundle.graph.targets.flags.writeable is False
    assert bundle.graph.weights.flags.writeable is False
    assert hashlib.sha256(bundle.graph.weights.tobytes()).hexdigest() == before
