from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from flybench.model import load_candidate_model_spec
from flybench.reference import ReferenceGraph, ReferenceState, exact_linear_substep


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "profiles/model-v0.1.json"
CRITERIA = ROOT / "profiles/numerical-criteria-v0.1.json"
ATOL = 1e-10
RTOL = 1e-10


def spec(dt_ms: float = 0.5, *, scale: float = 1.0, seed: int = 17):
    return load_candidate_model_spec(
        neural_dt_ms=dt_ms,
        runtime_synaptic_scale=scale,
        seed=seed,
        model_profile_path=MODEL,
        criteria_path=CRITERIA,
    )


def test_fixed_analytical_substep_values() -> None:
    cases = [
        (0.8, 0.0, 0.0, 0.4852245277701068, 0.0),
        (0.0, 0.0, 0.5, 0.1967346701436833, 0.0),
        (0.0, 0.75, 0.0, 0.11779884411900518, 0.10150146242745953),
    ]
    for v0, i0, u, expected_v, expected_i in cases:
        voltage, current = exact_linear_substep(
            v0,
            i0,
            u,
            dt_ms=10.0,
            tau_m_ms=20.0,
            tau_s_ms=5.0,
        )
        assert math.isclose(float(voltage), expected_v, rel_tol=RTOL, abs_tol=ATOL)
        assert math.isclose(float(current), expected_i, rel_tol=RTOL, abs_tol=ATOL)

    _, current = exact_linear_substep(
        0.0,
        0.75,
        0.0,
        dt_ms=10.0,
        tau_m_ms=20.0,
        tau_s_ms=5.0,
    )
    independent_current = 0.75 * math.exp(-10.0 / 5.0)
    assert math.isclose(float(current), independent_current, rel_tol=RTOL, abs_tol=ATOL)


def test_reference_state_matches_independent_ten_ms_expectations() -> None:
    graph = ReferenceGraph.empty(1)
    cases = [
        (0.8, 0.0, 0.0, 0.4852245277701068, 0.0),
        (0.0, 0.0, 0.5, 0.1967346701436833, 0.0),
        (0.0, 0.75, 0.0, 0.11779884411900518, 0.10150146242745953),
    ]
    for v0, i0, drive, expected_v, expected_i in cases:
        state = ReferenceState(spec(), graph)
        state.voltage[0] = v0
        state.synaptic_current[0] = i0
        for _ in range(20):
            result = state.step(drive)
            assert not result.spikes[0]
        assert math.isclose(state.voltage[0], expected_v, rel_tol=RTOL, abs_tol=ATOL)
        assert math.isclose(
            state.synaptic_current[0], expected_i, rel_tol=RTOL, abs_tol=ATOL
        )


def test_equal_time_constant_limit_is_exact_formula() -> None:
    v0 = 0.2
    i0 = 0.7
    drive = 0.1
    dt = 0.5
    tau = 5.0
    em = math.exp(-dt / tau)
    independent_v = v0 * em + drive * (1.0 - em) + i0 * (dt / tau) * em
    independent_i = i0 * em
    voltage, current = exact_linear_substep(
        v0,
        i0,
        drive,
        dt_ms=dt,
        tau_m_ms=tau,
        tau_s_ms=tau,
    )
    assert math.isclose(float(voltage), independent_v, rel_tol=RTOL, abs_tol=ATOL)
    assert math.isclose(float(current), independent_i, rel_tol=RTOL, abs_tol=ATOL)


def test_source_major_orientation_and_signed_accumulation() -> None:
    graph = ReferenceGraph.from_edges(
        3,
        [
            (0, 1, 2.0),
            (0, 2, -1.0),
            (1, 2, 3.0),
        ],
    )
    source_spikes = np.array([True, True, False])
    expected_target_increment = np.array([0.0, 2.0, 2.0])
    actual = graph.propagate(source_spikes, 1.0)
    np.testing.assert_array_equal(actual, expected_target_increment)
    assert not np.array_equal(actual, np.array([1.0, 3.0, 0.0]))


def test_model_spec_identity_is_canonical_and_binds_runtime_scale() -> None:
    first = spec(scale=1.0)
    second = spec(scale=1.0)
    changed = spec(scale=0.5)
    assert first == second
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.semantic_sha256 == second.semantic_sha256
    assert first.semantic_sha256 != changed.semantic_sha256
    assert first.delay_ticks == 2
    assert first.refractory_ticks == 4
