from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import pytest

from flybench.model import (
    BASE_MODEL_PROFILE_SHA256,
    EVENT_ORDER_VERSION,
    ModelSpec,
    load_candidate_model_spec,
    select_supported_timestep,
)
from flybench.reference import ReferenceGraph, ReferenceState


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "profiles/model-v0.1.json"
CRITERIA = ROOT / "profiles/numerical-criteria-v0.1.json"


def spec(dt_ms: float = 0.5, *, seed: int = 41, scale: float = 1.0) -> ModelSpec:
    return load_candidate_model_spec(
        neural_dt_ms=dt_ms,
        runtime_synaptic_scale=scale,
        seed=seed,
        model_profile_path=MODEL,
        criteria_path=CRITERIA,
    )


def snapshot_equal(left: dict[str, object], right: dict[str, object]) -> bool:
    for key in (
        "voltage",
        "synaptic_current",
        "refractory_until_tick",
        "pending_spikes",
        "pending_inputs",
    ):
        if not np.array_equal(left[key], right[key]):
            return False
    return all(left[key] == right[key] for key in ("tick", "seed", "rng_state"))


@pytest.mark.parametrize(
    ("dt_ms", "delay_ticks", "refractory_ticks"),
    [(0.5, 2, 4), (0.25, 4, 8), (0.1, 10, 20)],
)
def test_delay_and_refractory_ticks(dt_ms: float, delay_ticks: int, refractory_ticks: int) -> None:
    candidate = spec(dt_ms)
    assert candidate.delay_ticks == delay_ticks
    assert candidate.refractory_ticks == refractory_ticks


def test_unsupported_time_grid_fails_instead_of_rounding() -> None:
    with pytest.raises(ValueError, match="not an integer"):
        spec(0.3)


def test_simultaneous_signed_arrivals_are_accumulated_before_evolution() -> None:
    state = ReferenceState(spec(), ReferenceGraph.empty(1))
    state.queue_boundary_input(np.array([2.0]), arrival_tick=0)
    state.queue_boundary_input(np.array([-0.75]), arrival_tick=0)
    result = state.step(0.0)
    np.testing.assert_array_equal(result.arrival_increment, np.array([1.25]))
    expected_current = 1.25 * math.exp(-0.5 / 5.0)
    assert math.isclose(state.synaptic_current[0], expected_current, abs_tol=1e-12)


def test_source_major_scheduled_propagation_uses_at_spike_vector() -> None:
    graph = ReferenceGraph.from_edges(3, [(0, 1, 2.0), (0, 2, -1.0), (1, 2, 3.0)])
    state = ReferenceState(spec(), graph)
    state.pending_spikes[0] = np.array([True, True, False])
    result = state.step(np.zeros(3))
    np.testing.assert_array_equal(result.arrival_increment, np.array([0.0, 2.0, 2.0]))


@pytest.mark.parametrize("dt_ms", [0.5, 0.25, 0.1])
def test_exact_delay_and_no_retroactive_delivery(dt_ms: float) -> None:
    candidate = spec(dt_ms)
    graph = ReferenceGraph.from_edges(2, [(0, 1, 0.5)])
    state = ReferenceState(candidate, graph)
    em = math.exp(-dt_ms / candidate.tau_m_ms)
    tie_drive = np.nextafter(
        candidate.threshold / (1.0 - em), math.inf
    )
    spike = state.step(np.array([tie_drive, 0.0]))
    assert spike.spikes.tolist() == [True, False]
    spike_tick = spike.end_tick
    arrival_tick = spike_tick + candidate.delay_ticks
    assert state.voltage[0] == candidate.reset

    while state.tick < arrival_tick:
        before = state.tick
        result = state.step(np.zeros(2))
        assert result.start_tick == before
        assert result.arrival_increment[1] == 0.0
        assert state.voltage[1] == 0.0
    arrival = state.step(np.zeros(2))
    assert arrival.start_tick == arrival_tick
    assert arrival.arrival_increment[1] == 0.5
    assert state.voltage[1] > 0.0
    assert arrival_tick * dt_ms == pytest.approx(spike_tick * dt_ms + 1.0)


def test_threshold_tie_spikes_and_resets_immediately() -> None:
    candidate = spec()
    state = ReferenceState(candidate, ReferenceGraph.empty(1))
    em = math.exp(-candidate.neural_dt_ms / candidate.tau_m_ms)
    independently_constructed_drive = np.nextafter(1.0 / (1.0 - em), math.inf)
    independent_endpoint = independently_constructed_drive * (1.0 - em)
    assert math.isclose(independent_endpoint, candidate.threshold, abs_tol=1e-10)
    result = state.step(independently_constructed_drive)
    assert result.spikes[0]
    assert state.voltage[0] == candidate.reset
    assert state.refractory_until_tick[0] == 1 + candidate.refractory_ticks


def test_current_evolves_during_full_refractory_and_release_is_exact() -> None:
    candidate = spec()
    state = ReferenceState(candidate, ReferenceGraph.empty(1))
    em = math.exp(-candidate.neural_dt_ms / candidate.tau_m_ms)
    result = state.step(np.nextafter(1.0 / (1.0 - em), math.inf))
    assert result.spikes[0]
    state.queue_boundary_input(np.array([1.0]), arrival_tick=state.tick)

    for interval in range(candidate.refractory_ticks):
        current_before = state.synaptic_current[0]
        step = state.step(0.25)
        assert not step.spikes[0]
        assert state.voltage[0] == candidate.reset
        if interval == 0:
            expected = (current_before + 1.0) * math.exp(-0.5 / 5.0)
            assert state.synaptic_current[0] == pytest.approx(expected)
    assert state.tick == 1 + candidate.refractory_ticks
    released = state.step(0.25)
    assert not released.spikes[0]
    assert state.voltage[0] > candidate.reset


def test_empty_delay_ring_wraparound_has_no_stale_spikes() -> None:
    state = ReferenceState(spec(), ReferenceGraph.from_edges(2, [(0, 1, 2.0)]))
    for _ in range(30):
        result = state.step(np.zeros(2))
        assert not np.any(result.spikes)
        assert not np.any(result.arrival_increment)
    assert not np.any(state.pending_spikes)
    assert not np.any(state.pending_inputs)


def test_reset_is_complete_and_owned_rngs_are_independent() -> None:
    graph = ReferenceGraph.from_edges(2, [(0, 1, 1.0)])
    first = ReferenceState(spec(seed=123), graph)
    second = ReferenceState(spec(seed=123), graph)
    assert first.rng is not second.rng
    pristine = first.snapshot()
    first.voltage[:] = [0.3, 0.4]
    first.synaptic_current[:] = [0.5, -0.2]
    first.queue_boundary_input(np.array([1.0, 0.0]), arrival_tick=0)
    first.step(np.array([0.1, 0.2]))
    first.rng.random()
    assert not snapshot_equal(first.snapshot(), pristine)
    first.reset(seed=123)
    assert snapshot_equal(first.snapshot(), pristine)
    first.voltage[0] = 0.9
    assert second.voltage[0] == 0.0


def test_global_numpy_rng_activity_cannot_change_reference_evolution() -> None:
    graph = ReferenceGraph.from_edges(2, [(0, 1, 0.4)])
    first = ReferenceState(spec(seed=8), graph)
    second = ReferenceState(spec(seed=8), graph)
    rng_state_before = first.snapshot()["rng_state"]
    for drive in ([2.0, 0.0], [0.0, 0.1], [0.0, 0.1], [0.0, 0.1]):
        np.random.seed(999)
        np.random.random(500)
        first_result = first.step(np.array(drive))
        np.random.seed(1)
        np.random.random(3)
        second_result = second.step(np.array(drive))
        np.testing.assert_array_equal(first_result.spikes, second_result.spikes)
    assert snapshot_equal(first.snapshot(), second.snapshot())
    assert first.snapshot()["rng_state"] == rng_state_before


def test_frozen_selection_policy_prefers_coarsest_complete_pass() -> None:
    criteria = json.loads(CRITERIA.read_text())
    comparisons = {"0.5": {"status": "FAIL"}, "0.25": {"status": "PASS"}}
    selected, reason = select_supported_timestep(
        criteria, comparisons, analytical_pass=True, boundary_pass=True
    )
    assert selected == 0.25
    assert "coarsest" in reason
    comparisons["0.25"]["status"] = "FAIL"
    selected, reason = select_supported_timestep(
        criteria, comparisons, analytical_pass=True, boundary_pass=True
    )
    assert selected == 0.1
    assert "finest" in reason
    selected, _ = select_supported_timestep(
        criteria, comparisons, analytical_pass=False, boundary_pass=True
    )
    assert selected is None


def test_criteria_and_accepted_m04_profiles_are_immutable() -> None:
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == BASE_MODEL_PROFILE_SHA256
    accepted = {
        "profiles/escape-circuit.json": "29a6b4fb98d29f2fbf76fc031bea2f75d7ed534540666fc50279168358f5232b",
        "profiles/encoder-v0.1.json": "f6879937ec2e7efbdb888d336f2041d980f61a8981d7970314a53641bda14bfa",
        "profiles/decoder-v0.1.json": "71acbe641fc2c9ef4f9cee514f99e3dfdc392482d9c77483fc1334fdacb37544",
        "profiles/calibration-plan.json": "b00b9066365b25153ab3c8c56adf866cf1659bc669836345fd1617d9eff0f6d4",
    }
    for relative, digest in accepted.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest

    commits = subprocess.check_output(
        ["git", "log", "--follow", "--format=%H", "--", CRITERIA.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        text=True,
    ).splitlines()
    assert commits, "criteria must be committed before numerical tests execute"
    introduction_commit = commits[-1]
    committed = subprocess.check_output(
        ["git", "show", f"{introduction_commit}:{CRITERIA.relative_to(ROOT).as_posix()}"],
        cwd=ROOT,
    )
    assert committed == CRITERIA.read_bytes(), "frozen criteria changed after provenance commit"
    provenance = ROOT / "evidence/M05/criteria-provenance.json"
    if provenance.is_file():
        receipt = json.loads(provenance.read_text())
        assert receipt["criteria_commit_sha"] == introduction_commit
        assert receipt["criteria_sha256"] == hashlib.sha256(committed).hexdigest()
        assert receipt["criteria_unchanged_since_commit"] is True
    assert EVENT_ORDER_VERSION == "flybench.neural-order.v1"
