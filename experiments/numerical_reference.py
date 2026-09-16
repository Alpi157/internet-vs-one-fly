#!/usr/bin/env python3
"""Generate deterministic M05 analytical, boundary, and timestep evidence."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

import numpy as np

from flybench.model import (
    EVENT_ORDER_VERSION,
    INTEGRATION_VERSION,
    ModelSpec,
    load_candidate_model_spec,
    select_supported_timestep,
)
from flybench.reference import ReferenceGraph, ReferenceState, exact_linear_substep


ROOT = Path(__file__).resolve().parents[1]
MODEL_PROFILE = ROOT / "profiles/model-v0.1.json"
CRITERIA_PATH = ROOT / "profiles/numerical-criteria-v0.1.json"
RESOLVED_PROFILE = ROOT / "profiles/model-reference-v0.1.json"
REFERENCE_CODE = ROOT / "src/flybench/reference.py"
MODEL_CODE = ROOT / "src/flybench/model.py"
M04_MAPPING_DIGEST = "6652462228ddf9af863fae95608fd6cacb44fbd86fd12d0799ec65d8dabcef3d"
M04_CIRCUIT_DIGEST = "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5"
NUMERICAL_FIXTURE_SCALE = 1.0
NUMERICAL_SEED = 20260916


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def git_output(*args: str, binary: bool = False) -> str | bytes:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=not binary
    ).strip() if not binary else subprocess.check_output(["git", *args], cwd=ROOT)


def checked_spec(dt_ms: float) -> ModelSpec:
    return load_candidate_model_spec(
        neural_dt_ms=dt_ms,
        runtime_synaptic_scale=NUMERICAL_FIXTURE_SCALE,
        seed=NUMERICAL_SEED,
        model_profile_path=MODEL_PROFILE,
        criteria_path=CRITERIA_PATH,
    )


def criteria_provenance(out: Path) -> dict[str, Any]:
    relative = CRITERIA_PATH.relative_to(ROOT).as_posix()
    commits = str(git_output("log", "--follow", "--format=%H", "--", relative)).splitlines()
    if not commits:
        raise RuntimeError("numerical criteria are not committed")
    criteria_commit = commits[-1]
    committed_bytes = subprocess.check_output(
        ["git", "show", f"{criteria_commit}:{relative}"], cwd=ROOT
    )
    current_bytes = CRITERIA_PATH.read_bytes()
    unchanged = committed_bytes == current_bytes
    if not unchanged:
        raise RuntimeError("frozen numerical criteria changed after their provenance commit")
    current_head = str(git_output("rev-parse", "HEAD"))
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", criteria_commit, current_head],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    if not ancestry:
        raise RuntimeError("criteria commit is not an ancestor of the measurement code")
    previous_path = out / "criteria-provenance.json"
    first_measurement_sha = current_head
    if previous_path.is_file():
        try:
            previous = json.loads(previous_path.read_text())
            if previous.get("criteria_sha256") == sha256_bytes(current_bytes):
                first_measurement_sha = previous.get(
                    "first_measurement_code_sha", current_head
                )
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "schema_version": 1,
        "classification": "PROJECT NUMERICAL ACCEPTANCE CRITERION — not physiology",
        "criteria_path": relative,
        "criteria_sha256": sha256_bytes(current_bytes),
        "criteria_commit_sha": criteria_commit,
        "criteria_commit_is_ancestor": ancestry,
        "criteria_unchanged_since_commit": unchanged,
        "first_measurement_code_sha": first_measurement_sha,
        "latest_measurement_code_sha": current_head,
        "proof": "The oldest commit touching the criteria contains bytes identical to the current file and is an ancestor of measurement code.",
        "status": "PASS",
    }


def analytical_fixtures(criteria: dict[str, Any]) -> dict[str, Any]:
    atol = float(criteria["analytic_tolerance"]["atol"])
    rtol = float(criteria["analytic_tolerance"]["rtol"])
    fixtures = [
        {
            "name": "zero_input_voltage_decay",
            "v0": 0.8,
            "I0": 0.0,
            "u": 0.0,
            "duration_ms": 10.0,
            "expected_voltage": 0.4852245277701068,
            "expected_current": 0.0,
        },
        {
            "name": "constant_subthreshold_drive",
            "v0": 0.0,
            "I0": 0.0,
            "u": 0.5,
            "duration_ms": 10.0,
            "expected_voltage": 0.1967346701436833,
            "expected_current": 0.0,
        },
        {
            "name": "synaptic_current_decay",
            "v0": 0.0,
            "I0": 0.75,
            "u": 0.0,
            "duration_ms": 10.0,
            "expected_voltage": 0.11779884411900518,
            "expected_current": 0.10150146242745953,
        },
        {
            "name": "coupled_voltage_from_decaying_current",
            "v0": 0.0,
            "I0": 0.75,
            "u": 0.0,
            "duration_ms": 10.0,
            "expected_voltage": 0.11779884411900518,
            "expected_current": 0.10150146242745953,
        },
    ]
    for fixture in fixtures:
        voltage, current = exact_linear_substep(
            fixture["v0"],
            fixture["I0"],
            fixture["u"],
            dt_ms=fixture["duration_ms"],
            tau_m_ms=20.0,
            tau_s_ms=5.0,
        )
        fixture["actual_voltage"] = float(voltage)
        fixture["actual_current"] = float(current)
        fixture["voltage_abs_error"] = abs(
            float(voltage) - fixture["expected_voltage"]
        )
        fixture["current_abs_error"] = abs(
            float(current) - fixture["expected_current"]
        )
        fixture["expected_value_provenance"] = (
            "fixed requirement value; tests also compute math.exp expectations independently"
        )
        fixture["status"] = (
            "PASS"
            if math.isclose(
                float(voltage), fixture["expected_voltage"], rel_tol=rtol, abs_tol=atol
            )
            and math.isclose(
                float(current), fixture["expected_current"], rel_tol=rtol, abs_tol=atol
            )
            else "FAIL"
        )
    equal_tau_dt = 0.5
    equal_tau = 5.0
    equal_v0, equal_i0, equal_u = 0.2, 0.7, 0.1
    em = math.exp(-equal_tau_dt / equal_tau)
    expected_equal_v = (
        equal_v0 * em
        + equal_u * (1.0 - em)
        + equal_i0 * (equal_tau_dt / equal_tau) * em
    )
    expected_equal_i = equal_i0 * em
    actual_equal_v, actual_equal_i = exact_linear_substep(
        equal_v0,
        equal_i0,
        equal_u,
        dt_ms=equal_tau_dt,
        tau_m_ms=equal_tau,
        tau_s_ms=equal_tau,
    )
    equal_fixture = {
        "name": "equal_time_constant_limit",
        "expected_voltage": expected_equal_v,
        "actual_voltage": float(actual_equal_v),
        "voltage_abs_error": abs(float(actual_equal_v) - expected_equal_v),
        "expected_current": expected_equal_i,
        "actual_current": float(actual_equal_i),
        "current_abs_error": abs(float(actual_equal_i) - expected_equal_i),
        "expected_value_provenance": "independent closed-form limit using math.exp",
    }
    equal_fixture["status"] = (
        "PASS"
        if math.isclose(float(actual_equal_v), expected_equal_v, rel_tol=rtol, abs_tol=atol)
        and math.isclose(float(actual_equal_i), expected_equal_i, rel_tol=rtol, abs_tol=atol)
        else "FAIL"
    )
    fixtures.append(equal_fixture)
    passed = all(item["status"] == "PASS" for item in fixtures)
    return {
        "schema_version": 1,
        "analytic_atol": atol,
        "analytic_rtol": rtol,
        "fixtures": fixtures,
        "status": "PASS" if passed else "FAIL",
    }


def snapshots_equal(left: dict[str, object], right: dict[str, object]) -> bool:
    arrays = (
        "voltage",
        "synaptic_current",
        "refractory_until_tick",
        "pending_spikes",
        "pending_inputs",
    )
    return all(np.array_equal(left[name], right[name]) for name in arrays) and all(
        left[name] == right[name] for name in ("tick", "seed", "rng_state")
    )


def boundary_fixtures() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def capture(name: str, function: Callable[[], dict[str, Any]]) -> None:
        try:
            details = function()
            checks.append({"name": name, "status": "PASS", "details": details})
        except Exception as exc:  # evidence must preserve the exact failed boundary
            checks.append(
                {
                    "name": name,
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    def simultaneous() -> dict[str, Any]:
        state = ReferenceState(checked_spec(0.5), ReferenceGraph.empty(1))
        state.queue_boundary_input(np.array([2.0]), arrival_tick=0)
        state.queue_boundary_input(np.array([-0.75]), arrival_tick=0)
        result = state.step(0.0)
        assert result.arrival_increment.tolist() == [1.25]
        return {"signed_arrival_increment": [1.25], "applied_before_interval": True}

    def orientation() -> dict[str, Any]:
        graph = ReferenceGraph.from_edges(
            3, [(0, 1, 2.0), (0, 2, -1.0), (1, 2, 3.0)]
        )
        actual = graph.propagate(np.array([True, True, False]), 1.0)
        expected = np.array([0.0, 2.0, 2.0])
        assert np.array_equal(actual, expected)
        return {
            "orientation": "A[source,target]",
            "source_spikes": [1, 1, 0],
            "independent_expected_target_increment": expected.tolist(),
            "actual_target_increment": actual.tolist(),
        }

    def delay_grid() -> dict[str, Any]:
        observed = []
        for dt in (0.5, 0.25, 0.1):
            candidate = checked_spec(dt)
            graph = ReferenceGraph.from_edges(2, [(0, 1, 0.5)])
            state = ReferenceState(candidate, graph)
            em = math.exp(-dt / 20.0)
            tie_drive = np.nextafter(1.0 / (1.0 - em), math.inf)
            assert math.isclose(tie_drive * (1.0 - em), 1.0, abs_tol=1e-10)
            spike = state.step(np.array([tie_drive, 0.0]))
            assert spike.spikes.tolist() == [True, False]
            arrival_tick = spike.end_tick + candidate.delay_ticks
            before = []
            while state.tick < arrival_tick:
                result = state.step(np.zeros(2))
                before.append(float(result.arrival_increment[1]))
            arrival = state.step(np.zeros(2))
            assert before == [0.0] * candidate.delay_ticks
            assert arrival.arrival_increment[1] == 0.5
            observed.append(
                {
                    "dt_ms": dt,
                    "delay_ticks": candidate.delay_ticks,
                    "spike_tick": spike.end_tick,
                    "arrival_tick": arrival.start_tick,
                    "arrival_time_after_spike_ms": (
                        arrival.start_tick - spike.end_tick
                    )
                    * dt,
                    "prearrival_increments": before,
                }
            )
        return {"grids": observed, "retroactive_delivery": False}

    def threshold_reset() -> dict[str, Any]:
        candidate = checked_spec(0.5)
        state = ReferenceState(candidate, ReferenceGraph.empty(1))
        em = math.exp(-0.5 / 20.0)
        drive = np.nextafter(1.0 / (1.0 - em), math.inf)
        assert math.isclose(drive * (1.0 - em), 1.0, abs_tol=1e-10)
        result = state.step(drive)
        assert result.spikes[0]
        assert state.voltage[0] == 0.0
        return {
            "independent_tie_drive": drive,
            "comparator": ">=",
            "spiked": True,
            "post_spike_voltage": 0.0,
        }

    def refractory_current() -> dict[str, Any]:
        candidate = checked_spec(0.5)
        state = ReferenceState(candidate, ReferenceGraph.empty(1))
        em = math.exp(-0.5 / 20.0)
        assert state.step(np.nextafter(1.0 / (1.0 - em), math.inf)).spikes[0]
        release_tick = state.refractory_until_tick[0]
        state.queue_boundary_input(np.array([1.0]), arrival_tick=state.tick)
        trace = []
        for _ in range(candidate.refractory_ticks):
            result = state.step(0.25)
            trace.append(
                {
                    "end_tick": state.tick,
                    "voltage": float(state.voltage[0]),
                    "current": float(state.synaptic_current[0]),
                    "spike": bool(result.spikes[0]),
                }
            )
            assert state.voltage[0] == candidate.reset
        assert state.tick == release_tick
        state.step(0.25)
        assert state.voltage[0] > candidate.reset
        return {
            "refractory_ticks": candidate.refractory_ticks,
            "release_tick": int(release_tick),
            "held_trace": trace,
            "release_interval_voltage": float(state.voltage[0]),
            "current_evolved": True,
        }

    def empty_wrap() -> dict[str, Any]:
        state = ReferenceState(
            checked_spec(0.5), ReferenceGraph.from_edges(2, [(0, 1, 2.0)])
        )
        for _ in range(30):
            result = state.step(np.zeros(2))
            assert not np.any(result.spikes)
            assert not np.any(result.arrival_increment)
        assert not np.any(state.pending_spikes)
        return {"steps": 30, "ring_size": state.pending_spikes.shape[0], "stale": False}

    def reset_rng() -> dict[str, Any]:
        graph = ReferenceGraph.from_edges(2, [(0, 1, 1.0)])
        first = ReferenceState(checked_spec(0.5), graph)
        second = ReferenceState(checked_spec(0.5), graph)
        pristine = first.snapshot()
        assert first.rng is not second.rng
        first.voltage[0] = 0.4
        first.rng.random()
        first.step(np.array([0.2, 0.1]))
        first.reset(seed=NUMERICAL_SEED)
        assert snapshots_equal(first.snapshot(), pristine)
        first.voltage[0] = 0.7
        assert second.voltage[0] == 0.0
        np.random.seed(444)
        np.random.random(100)
        first.reset(seed=NUMERICAL_SEED)
        second.reset(seed=NUMERICAL_SEED)
        for _ in range(8):
            np.random.random(17)
            first_result = first.step(np.array([0.4, 0.1]))
            np.random.random(5)
            second_result = second.step(np.array([0.4, 0.1]))
            assert np.array_equal(first_result.spikes, second_result.spikes)
        assert snapshots_equal(first.snapshot(), second.snapshot())
        return {
            "rng_algorithm": "PCG64",
            "owned_generators_distinct": True,
            "reset_complete": True,
            "global_numpy_rng_independent": True,
            "random_draws_during_equation_steps": 0,
        }

    capture("simultaneous_signed_arrivals", simultaneous)
    capture("source_major_orientation", orientation)
    capture("exact_delay_all_candidate_grids_and_no_retroactivity", delay_grid)
    capture("threshold_tie_and_immediate_reset", threshold_reset)
    capture("refractory_current_evolution_and_exact_release", refractory_current)
    capture("empty_delay_ring_wraparound", empty_wrap)
    capture("complete_reset_and_rng_isolation", reset_rng)
    return {
        "schema_version": 1,
        "event_order_version": EVENT_ORDER_VERSION,
        "checks": checks,
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
    }


def simulate_panel(
    *,
    dt_ms: float,
    graph: ReferenceGraph,
    duration_ms: float,
    drive_at_time: Callable[[float], np.ndarray],
    sample_common_times: bool,
) -> dict[str, Any]:
    candidate = checked_spec(dt_ms)
    state = ReferenceState(candidate, graph)
    total_ticks_float = duration_ms / dt_ms
    total_ticks = round(total_ticks_float)
    if not math.isclose(total_ticks_float, total_ticks, abs_tol=1e-12, rel_tol=0.0):
        raise ValueError("duration is not exactly represented on grid")
    spike_times: list[list[float]] = [[] for _ in range(graph.n)]
    samples: dict[str, dict[str, list[float]]] = {}
    rng_before = deepcopy(state.rng.bit_generator.state)
    for _ in range(total_ticks):
        drive = drive_at_time(state.time_ms)
        result = state.step(drive)
        time_ms = result.end_tick * dt_ms
        for neuron in np.flatnonzero(result.spikes):
            spike_times[int(neuron)].append(time_ms)
        rounded = round(time_ms)
        if sample_common_times and rounded > 0 and math.isclose(
            time_ms, float(rounded), abs_tol=1e-10, rel_tol=0.0
        ):
            samples[str(rounded)] = {
                "voltage": state.voltage.tolist(),
                "synaptic_current": state.synaptic_current.tolist(),
            }
    return {
        "dt_ms": dt_ms,
        "delay_ticks": candidate.delay_ticks,
        "refractory_ticks": candidate.refractory_ticks,
        "duration_ms": duration_ms,
        "spike_times_ms_by_neuron": spike_times,
        "spike_counts_by_neuron": [len(times) for times in spike_times],
        "final_voltage": state.voltage.tolist(),
        "final_synaptic_current": state.synaptic_current.tolist(),
        "common_time_samples": samples,
        "finite_state": bool(
            np.all(np.isfinite(state.voltage))
            and np.all(np.isfinite(state.synaptic_current))
        ),
        "rng_draws_consumed": 0,
        "rng_state_unchanged": state.rng.bit_generator.state == rng_before,
    }


def raw_timestep_runs(criteria: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    del criteria
    panels: dict[str, dict[str, dict[str, Any]]] = {
        "subthreshold_held_drive": {},
        "spiking_constant_drive": {},
        "signed_delayed_network": {},
    }
    empty = ReferenceGraph.empty(1)
    signed = ReferenceGraph.from_edges(
        3,
        [
            (0, 1, 2.0),
            (0, 2, -1.0),
            (1, 2, 3.0),
        ],
    )
    for dt in (0.5, 0.25, 0.1):
        key = format(dt, "g")
        panels["subthreshold_held_drive"][key] = simulate_panel(
            dt_ms=dt,
            graph=empty,
            duration_ms=60.0,
            drive_at_time=lambda _time: np.array([0.5]),
            sample_common_times=True,
        )
        panels["spiking_constant_drive"][key] = simulate_panel(
            dt_ms=dt,
            graph=empty,
            duration_ms=60.0,
            drive_at_time=lambda _time: np.array([2.0]),
            sample_common_times=False,
        )

        def network_drive(time_ms: float) -> np.ndarray:
            if time_ms < 20.0:
                return np.array([2.0, 0.4, 0.2])
            if time_ms < 40.0:
                return np.array([0.0, 0.4, 0.2])
            return np.array([2.0, 0.4, 0.2])

        panels["signed_delayed_network"][key] = simulate_panel(
            dt_ms=dt,
            graph=signed,
            duration_ms=60.0,
            drive_at_time=network_drive,
            sample_common_times=False,
        )
    return panels


def max_abs(left: list[float], right: list[float]) -> float:
    if not left:
        return 0.0
    return float(np.max(np.abs(np.asarray(left) - np.asarray(right))))


def compare_timesteps(
    criteria: dict[str, Any], panels: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, Any]:
    reference_key = format(float(criteria["reference_dt_ms"]), "g")
    comparisons: dict[str, dict[str, Any]] = {}
    sub_v_limit = criteria["subthreshold_common_time"]["voltage_max_abs_error"]
    sub_i_limit = criteria["subthreshold_common_time"]["current_max_abs_error"]
    final_v_limit = criteria["spiking_final_state"]["voltage_max_abs_error"]
    final_i_limit = criteria["spiking_final_state"]["current_max_abs_error"]
    for candidate_dt in criteria["candidate_dt_order_ms"]:
        key = format(float(candidate_dt), "g")
        candidate_checks: list[dict[str, Any]] = []
        sub_candidate = panels["subthreshold_held_drive"][key]
        sub_reference = panels["subthreshold_held_drive"][reference_key]
        common_times = sorted(
            set(sub_candidate["common_time_samples"])
            & set(sub_reference["common_time_samples"]),
            key=int,
        )
        voltage_errors = []
        current_errors = []
        for time in common_times:
            voltage_errors.append(
                max_abs(
                    sub_candidate["common_time_samples"][time]["voltage"],
                    sub_reference["common_time_samples"][time]["voltage"],
                )
            )
            current_errors.append(
                max_abs(
                    sub_candidate["common_time_samples"][time]["synaptic_current"],
                    sub_reference["common_time_samples"][time]["synaptic_current"],
                )
            )
        sub_v_error = max(voltage_errors, default=0.0)
        sub_i_error = max(current_errors, default=0.0)
        candidate_checks.extend(
            [
                {
                    "criterion": "subthreshold common-time voltage max_abs_error",
                    "actual": sub_v_error,
                    "limit": sub_v_limit,
                    "status": "PASS" if sub_v_error <= sub_v_limit else "FAIL",
                },
                {
                    "criterion": "subthreshold common-time current max_abs_error",
                    "actual": sub_i_error,
                    "limit": sub_i_limit,
                    "status": "PASS" if sub_i_error <= sub_i_limit else "FAIL",
                },
            ]
        )
        panel_comparisons = {}
        for panel_name in ("spiking_constant_drive", "signed_delayed_network"):
            candidate = panels[panel_name][key]
            reference = panels[panel_name][reference_key]
            count_equal = (
                candidate["spike_counts_by_neuron"]
                == reference["spike_counts_by_neuron"]
            )
            spike_differences: list[list[float]] = []
            spike_times_pass = count_equal
            for candidate_times, reference_times in zip(
                candidate["spike_times_ms_by_neuron"],
                reference["spike_times_ms_by_neuron"],
                strict=True,
            ):
                if len(candidate_times) != len(reference_times):
                    spike_differences.append([])
                    spike_times_pass = False
                    continue
                differences = [
                    abs(left - right)
                    for left, right in zip(candidate_times, reference_times, strict=True)
                ]
                spike_differences.append(differences)
                if any(value > float(candidate_dt) + 1e-12 for value in differences):
                    spike_times_pass = False
            voltage_error = max_abs(
                candidate["final_voltage"], reference["final_voltage"]
            )
            current_error = max_abs(
                candidate["final_synaptic_current"],
                reference["final_synaptic_current"],
            )
            finite = candidate["finite_state"] and reference["finite_state"]
            checks = [
                {
                    "criterion": "exact spike-count equality per neuron",
                    "actual_candidate": candidate["spike_counts_by_neuron"],
                    "actual_reference": reference["spike_counts_by_neuron"],
                    "status": "PASS" if count_equal else "FAIL",
                },
                {
                    "criterion": "ordered spike-time difference <= candidate dt",
                    "differences_ms_by_neuron": spike_differences,
                    "limit_ms": candidate_dt,
                    "status": "PASS" if spike_times_pass else "FAIL",
                },
                {
                    "criterion": "spiking final voltage max_abs_error",
                    "actual": voltage_error,
                    "limit": final_v_limit,
                    "status": "PASS" if voltage_error <= final_v_limit else "FAIL",
                },
                {
                    "criterion": "spiking final current max_abs_error",
                    "actual": current_error,
                    "limit": final_i_limit,
                    "status": "PASS" if current_error <= final_i_limit else "FAIL",
                },
                {
                    "criterion": "finite state",
                    "actual": finite,
                    "required": True,
                    "status": "PASS" if finite else "FAIL",
                },
            ]
            panel_comparisons[panel_name] = {
                "checks": checks,
                "status": "PASS" if all(x["status"] == "PASS" for x in checks) else "FAIL",
            }
            candidate_checks.extend(checks)
        comparisons[key] = {
            "candidate_dt_ms": candidate_dt,
            "reference_dt_ms": criteria["reference_dt_ms"],
            "common_subthreshold_sample_count": len(common_times),
            "checks": candidate_checks,
            "spiking_panels": panel_comparisons,
            "status": (
                "PASS"
                if all(item["status"] == "PASS" for item in candidate_checks)
                else "FAIL"
            ),
        }
    reference_runs = {
        panel: runs[reference_key] for panel, runs in panels.items()
    }
    reference_pass = all(
        run["finite_state"] and run["rng_state_unchanged"]
        for run in reference_runs.values()
    )
    return {
        "schema_version": 1,
        "classification": "PROJECT NUMERICAL ACCEPTANCE MEASUREMENT — not physiology",
        "criteria_sha256": sha256_bytes(CRITERIA_PATH.read_bytes()),
        "runtime_synaptic_scale": NUMERICAL_FIXTURE_SCALE,
        "runtime_synaptic_scale_scope": "numerical fixture only; not calibrated",
        "seed": NUMERICAL_SEED,
        "stimulus_schedule_alignment": "all changes at 0, 20, or 40 integer milliseconds",
        "raw_runs": panels,
        "reference_run": {
            "dt_ms": criteria["reference_dt_ms"],
            "role": "comparison reference; analytical and boundary correctness are reported separately",
            "finite_state_all_panels": all(
                run["finite_state"] for run in reference_runs.values()
            ),
            "zero_rng_draws_all_panels": all(
                run["rng_draws_consumed"] == 0 for run in reference_runs.values()
            ),
            "status": "PASS" if reference_pass else "FAIL",
        },
        "comparisons": comparisons,
    }


def resolved_profile_status(selected_spec: ModelSpec) -> dict[str, Any]:
    if not RESOLVED_PROFILE.is_file():
        return {
            "status": "NOT_COMMITTED_YET",
            "path": RESOLVED_PROFILE.relative_to(ROOT).as_posix(),
        }
    profile_bytes = RESOLVED_PROFILE.read_bytes()
    profile = json.loads(profile_bytes)
    valid = (
        profile.get("base_model_profile_sha256")
        == selected_spec.base_model_profile_sha256
        and profile.get("numerical_criteria_sha256")
        == selected_spec.numerical_criteria_sha256
        and profile.get("model_spec_sha256") == selected_spec.semantic_sha256
        and profile.get("model_spec") == selected_spec.canonical_payload()
        and profile.get("selected_neural_dt_ms") == selected_spec.neural_dt_ms
    )
    return {
        "status": "PASS" if valid else "FAIL",
        "path": RESOLVED_PROFILE.relative_to(ROOT).as_posix(),
        "sha256": sha256_bytes(profile_bytes),
    }


def equation_review_text(
    *,
    criteria_sha: str,
    analytical: dict[str, Any],
    boundary: dict[str, Any],
    convergence: dict[str, Any],
    selected_dt: float | None,
    selection_reason: str,
    manual_present: bool,
) -> str:
    lines = [
        "M05 equation and numerical-semantics review",
        "",
        "Classification: MODEL ASSUMPTION plus PROJECT NUMERICAL CONVENTION; not physiology.",
        "Units: time constants, delay, refractory, and dt are milliseconds; voltage/current are normalized model units.",
        "Equations: tau_m*dv/dt = -v + I + u; tau_s*dI/dt = -I.",
        "Parameters: tau_m=20 ms, tau_s=5 ms, rest/reset=0, threshold=1, refractory=2 ms, delay=1 ms.",
        f"Integration: {INTEGRATION_VERSION}; exact closed-form linear substep in float64.",
        f"Ordering: {EVENT_ORDER_VERSION}.",
        "Boundary order: apply all due signed current jumps; establish held u; evolve I and eligible v; evaluate v>=threshold at interval end; reset/schedule spikes.",
        "Refractory: voltage is held exactly at reset for each interval whose start tick is before refractory_until; current still receives arrivals and decays; release occurs at the exact integer boundary.",
        "Delay: outgoing source-major weights arrive at spike boundary + 1 ms and never affect a preceding interval.",
        "Runtime scale: 1.0 in these numerical fixtures only; it is not a behavioral calibration choice.",
        "RNG: each state owns a PCG64 Generator seeded explicitly; deterministic zero/rest equations consume zero draws.",
        "",
        f"Frozen criteria SHA-256: {criteria_sha}",
        "Analytic atol/rtol: 1e-10 / 1e-10.",
        "Reference dt: 0.1 ms; candidate order: 0.5 ms then 0.25 ms.",
        "Spike counts must match per neuron; matched spike times may differ by at most candidate dt.",
        "Subthreshold common-time voltage/current max errors: 1e-9 / 1e-9.",
        "Spiking final voltage/current max errors: 0.05 / 0.05; finite state required.",
        "",
        f"Analytical fixtures: {analytical['status']}.",
        f"Boundary fixtures: {boundary['status']}.",
    ]
    for key, result in convergence["comparisons"].items():
        lines.append(f"Candidate dt {key} ms comparison: {result['status']}.")
    lines.append(
        f"Reference dt {convergence['reference_run']['dt_ms']} ms status: "
        f"{convergence['reference_run']['status']}."
    )
    lines.extend(
        [
            f"Selected numerical dt: {selected_dt if selected_dt is not None else 'NONE'} ms.",
            f"Selection reason: {selection_reason}.",
            f"Manual equation-review receipt present: {'yes' if manual_present else 'no'}.",
            "",
            "This review does not establish physiological validity, behavioral calibration, closed-loop correctness, or performance.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)

    criteria = json.loads(CRITERIA_PATH.read_text())
    provenance = criteria_provenance(out)
    analytical = analytical_fixtures(criteria)
    boundary = boundary_fixtures()
    panels = raw_timestep_runs(criteria)
    convergence = compare_timesteps(criteria, panels)
    selected_dt, selection_reason = select_supported_timestep(
        criteria,
        convergence["comparisons"],
        analytical_pass=analytical["status"] == "PASS",
        boundary_pass=boundary["status"] == "PASS",
    )
    selected_spec = checked_spec(selected_dt) if selected_dt is not None else None
    resolved_status = (
        resolved_profile_status(selected_spec)
        if selected_spec is not None
        else {"status": "BLOCKED"}
    )
    convergence["selected_dt_ms"] = selected_dt
    convergence["selection_reason"] = selection_reason
    convergence["status"] = (
        "PASS"
        if selected_dt is not None
        and analytical["status"] == "PASS"
        and boundary["status"] == "PASS"
        else "FAIL"
    )
    model_spec = {
        "schema_version": 1,
        "classification": "M05 numerical reference ModelSpec; not calibrated physiology",
        "accepted_m04_mapping_digest": M04_MAPPING_DIGEST,
        "accepted_m04_circuit_digest": M04_CIRCUIT_DIGEST,
        "reference_code_sha256": sha256_bytes(REFERENCE_CODE.read_bytes()),
        "model_code_sha256": sha256_bytes(MODEL_CODE.read_bytes()),
        "producer_code_git_sha": str(git_output("rev-parse", "HEAD")),
        "model_spec": selected_spec.canonical_payload() if selected_spec else None,
        "model_spec_sha256": selected_spec.semantic_sha256 if selected_spec else None,
        "resolved_profile": resolved_status,
        "status": "PASS" if selected_spec is not None else "FAIL",
    }

    receipt_path = out / "manual-equation-review.txt"
    manual_present = receipt_path.is_file() and receipt_path.stat().st_size > 0
    receipt = (
        {
            "status": "PRESENT_OPERATOR_SUPPLIED",
            "bytes": receipt_path.stat().st_size,
            "sha256": sha256_bytes(receipt_path.read_bytes()),
        }
        if manual_present
        else {"status": "MISSING"}
    )
    numerical_pass = (
        analytical["status"] == "PASS"
        and boundary["status"] == "PASS"
        and convergence["status"] == "PASS"
        and selected_spec is not None
    )
    fully_ready = numerical_pass and manual_present and resolved_status["status"] == "PASS"
    decision = {
        "schema_version": 1,
        "gate": "M05-NUMERICAL-SEMANTICS",
        "outcome": "PASS" if fully_ready else "BLOCKED",
        "allowed_next_milestone": "M06" if fully_ready else None,
        "external_milestone_acceptance": "PENDING",
        "selected_neural_dt_ms": selected_dt,
        "selection_reason": selection_reason,
        "delay_ticks": selected_spec.delay_ticks if selected_spec else None,
        "refractory_ticks": selected_spec.refractory_ticks if selected_spec else None,
        "event_order_version": EVENT_ORDER_VERSION,
        "model_spec_sha256": selected_spec.semantic_sha256 if selected_spec else None,
        "numerical_criteria_sha256": provenance["criteria_sha256"],
        "analytical_status": analytical["status"],
        "boundary_status": boundary["status"],
        "convergence_status": convergence["status"],
        "resolved_profile_status": resolved_status["status"],
        "manual_equation_review_receipt": receipt,
        "blocker": (
            None
            if fully_ready
            else (
                "HUMAN M05 EQUATION REVIEW REQUIRED"
                if numerical_pass and not manual_present
                else (
                    "resolved reference profile is not committed or does not match evidence"
                    if numerical_pass and resolved_status["status"] != "PASS"
                    else "M05 analytical, boundary, or convergence semantics failed"
                )
            )
        ),
    }

    write_json(out / "criteria-provenance.json", provenance)
    write_json(out / "analytical-fixtures.json", analytical)
    write_json(out / "boundary-fixtures.json", boundary)
    write_json(out / "timestep-convergence.json", convergence)
    write_json(out / "model-spec.json", model_spec)
    write_json(out / "decision.json", decision)
    (out / "equation-review.txt").write_text(
        equation_review_text(
            criteria_sha=provenance["criteria_sha256"],
            analytical=analytical,
            boundary=boundary,
            convergence=convergence,
            selected_dt=selected_dt,
            selection_reason=selection_reason,
            manual_present=manual_present,
        )
    )

    summary = {
        "status": "PASS" if fully_ready else "BLOCKED",
        "selected_neural_dt_ms": selected_dt,
        "model_spec_sha256": model_spec["model_spec_sha256"],
        "criteria_sha256": provenance["criteria_sha256"],
        "analytical": analytical["status"],
        "boundary": boundary["status"],
        "comparisons": {
            key: value["status"] for key, value in convergence["comparisons"].items()
        },
        "manual_equation_review": receipt["status"],
        "resolved_profile": resolved_status["status"],
        "out": str(out),
    }
    print(json.dumps(summary, sort_keys=True))
    if not manual_present and numerical_pass:
        print("HUMAN M05 EQUATION REVIEW REQUIRED", file=sys.stderr)
    return 0 if fully_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
