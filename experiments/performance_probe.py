#!/usr/bin/env python3
"""Bounded M07 CPU parity, performance, memory, and live-candidate decision probe."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from typing import Any, Callable

import llvmlite
import numba
import numpy as np

from flybench.bench import NORMAL_SCENARIOS, scripted_observation
from flybench.catch import load_environment_config
from flybench.encoding import ThreatObservation
from flybench.kernel import KERNEL_IMPLEMENTATION_ID, kernel_configuration, warm_kernel
from flybench.model import load_candidate_model_spec
from flybench.runner import (
    ACCEPTED_CIRCUIT_DIGEST,
    ACCEPTED_FULL_GRAPH_DIGEST,
    Runner,
    build_direct_visual_to_dnp01_zero,
    load_full_graph,
    load_graph,
)


ROOT = Path(__file__).resolve().parents[1]
PROCESS_START_NS = time.perf_counter_ns()
PARITY_PROFILE = ROOT / "profiles/kernel-parity-v0.1.json"
CONTROLLER_PROFILE = ROOT / "profiles/controller-v0.1.json"
PORTS_PROFILE = ROOT / "profiles/escape-circuit.json"
MODEL_PROFILE = ROOT / "profiles/model-v0.1.json"
CRITERIA_PROFILE = ROOT / "profiles/numerical-criteria-v0.1.json"
ENVIRONMENT_PROFILE = ROOT / "profiles/environment-v0.1.json"
LOOMING_PROFILE = ROOT / "profiles/looming-controls.json"
INTERVENTION_PROFILE = (
    ROOT / "profiles/intervention-direct-visual-to-dnp01-zero-v0.1.json"
)
EXPECTED_IDENTITIES = {
    "full_graph_semantic_digest": ACCEPTED_FULL_GRAPH_DIGEST,
    "circuit_semantic_digest": ACCEPTED_CIRCUIT_DIGEST,
    "source_lock_sha256": "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c",
    "mapping_digest": "6652462228ddf9af863fae95608fd6cacb44fbd86fd12d0799ec65d8dabcef3d",
    "accepted_m05_model_spec_sha256": "e7bf666f0b9b716d0c6e80af001604b4355ce34ff38e8fa514b90898d6b1dd91",
    "selected_runtime_model_spec_sha256": "8fb910576dd01bb28dece1198274072302e03cd7a00808dcec8948e4b2dac2bc",
    "controller_profile_sha256": "0b3577ec2dc257f130d59f0219544ad0dae479080027e25bdeca2182673bf817",
    "encoder_profile_sha256": "7840fa564c7f34d188797899ced5c87ffd9825469172f3a7c1076e36873c7de7",
    "decoder_profile_sha256": "7fec8cef8d5ca3679fbf65456f236bab2c5e15e7902aafc5146ce8d83838ca4f",
    "environment_profile_sha256": "9119848704b84416e1eed25ed8ae84735216ccb251e83147ea8970e2754968f7",
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def current_rss_bytes() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def peak_rss_bytes() -> int | None:
    try:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value * 1024) if sys.platform.startswith("linux") else int(value)
    except (ValueError, OSError):
        return None


def _child_entry(
    connection: Any,
    progress: Any,
    timing_buffer: Any,
    temporary_directory: str,
    launched_ns: int,
    worker: Callable[..., dict[str, Any]],
    worker_args: tuple[Any, ...],
) -> None:
    worker_process_startup_ns = time.perf_counter_ns() - launched_ns
    try:
        result = worker(progress, timing_buffer, temporary_directory, *worker_args)
        result["worker_process_startup_ns"] = worker_process_startup_ns
        connection.send({"status": "COMPLETE", "payload": result})
    except BaseException as exc:  # child must always communicate a classified failure
        connection.send(
            {
                "status": "ERROR",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        connection.close()


def run_worker_with_timeout(
    worker: Callable[..., dict[str, Any]],
    worker_args: tuple[Any, ...],
    *,
    timeout_seconds: float,
    interval_capacity: int,
    temporary_parent: Path | None = None,
) -> dict[str, Any]:
    """Run one worker in a terminable process and classify COMPLETE/TIMEOUT/ERROR."""

    if timeout_seconds <= 0 or interval_capacity < 0:
        raise ValueError("timeout and interval capacity must be bounded and nonnegative")
    context = mp.get_context("fork")
    progress = context.Value("i", 0)
    timing_buffer = context.Array("q", max(interval_capacity, 1), lock=False)
    parent_connection, child_connection = context.Pipe(duplex=False)
    temporary_directory = tempfile.mkdtemp(
        prefix="flybench-m07-worker-",
        dir=str(temporary_parent) if temporary_parent is not None else None,
    )
    launched_ns = time.perf_counter_ns()
    process = context.Process(
        target=_child_entry,
        args=(
            child_connection,
            progress,
            timing_buffer,
            temporary_directory,
            launched_ns,
            worker,
            worker_args,
        ),
    )
    process.start()
    child_connection.close()
    deadline = time.monotonic() + timeout_seconds
    message: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if parent_connection.poll(0.01):
            message = parent_connection.recv()
            break
        if not process.is_alive():
            if parent_connection.poll(0.1):
                message = parent_connection.recv()
            break
    timed_out = message is None and process.is_alive()
    if timed_out:
        process.terminate()
    process.join(timeout=5.0)
    if process.is_alive():
        process.kill()
        process.join(timeout=5.0)
    completed = min(int(progress.value), interval_capacity)
    timings = [int(timing_buffer[index]) for index in range(completed)]
    parent_connection.close()
    shutil.rmtree(temporary_directory, ignore_errors=True)
    resources_released = not Path(temporary_directory).exists()
    base = {
        "schema_version": 1,
        "timeout_seconds": timeout_seconds,
        "completed_intervals": completed,
        "raw_interval_timings_ns": timings,
        "worker_alive_after_join": process.is_alive(),
        "worker_exitcode": process.exitcode,
        "temporary_worker_state_released": resources_released,
    }
    if timed_out:
        return {**base, "status": "TIMEOUT"}
    if message is None:
        return {
            **base,
            "status": "ERROR",
            "error_type": "WorkerProtocolError",
            "error": "worker exited without a result",
        }
    if message["status"] == "ERROR":
        return {**base, **message}
    payload = message["payload"]
    payload_timings = payload.get("raw_interval_timings_ns", timings)
    if completed != interval_capacity or len(payload_timings) != interval_capacity:
        return {
            **base,
            "status": "ERROR",
            "error_type": "PartialCompletionError",
            "error": "partial completion cannot be classified COMPLETE",
        }
    return {**base, "status": "COMPLETE", **payload}


def finite_delay_worker(
    progress: Any,
    timing_buffer: Any,
    temporary_directory: str,
    delay_seconds: float,
    completed_before_delay: int,
) -> dict[str, Any]:
    """Finite test worker used to prove forced timeout cleanup without hanging tests."""

    Path(temporary_directory, "worker-state.txt").write_text("temporary\n")
    for index in range(completed_before_delay):
        timing_buffer[index] = index + 1
        progress.value = index + 1
    time.sleep(delay_seconds)
    return {"raw_interval_timings_ns": list(range(1, completed_before_delay + 1))}


def error_worker(
    progress: Any,
    timing_buffer: Any,
    temporary_directory: str,
) -> dict[str, Any]:
    Path(temporary_directory, "worker-state.txt").write_text("temporary\n")
    raise RuntimeError("deliberate bounded worker error")


def _model_spec(seed: int) -> Any:
    model = load_candidate_model_spec(
        neural_dt_ms=0.5,
        runtime_synaptic_scale=0.001,
        seed=seed,
        model_profile_path=MODEL_PROFILE,
        criteria_path=CRITERIA_PROFILE,
    )
    if model.semantic_sha256 != EXPECTED_IDENTITIES["selected_runtime_model_spec_sha256"]:
        raise ValueError("selected runtime ModelSpec identity mismatch")
    return model


def _load_bundle(graph_name: str, graph_path: Path) -> Any:
    if graph_name == "circuit":
        return load_graph(graph_path)
    if graph_name == "full":
        return load_full_graph(graph_path, PORTS_PROFILE)
    raise ValueError(f"unsupported graph {graph_name!r}")


def _observation_for_workload(
    workload: str, control_tick: int, looming_profile: dict[str, Any]
) -> tuple[ThreatObservation, bool]:
    if workload == "quiet":
        return ThreatObservation(False), False
    if workload == "nominal":
        if control_tick < 80:
            return scripted_observation(looming_profile, "standard looming", control_tick)
        return ThreatObservation(False), False
    if workload == "sustained":
        return ThreatObservation(True, 1.0, -0.0275), False
    raise ValueError(f"unsupported workload {workload!r}")


def probe_worker(
    progress: Any,
    timing_buffer: Any,
    temporary_directory: str,
    graph_name: str,
    graph_path: str,
    workload: str,
    interval_count: int,
    seed: int,
) -> dict[str, Any]:
    del temporary_directory
    graph_load_start = time.perf_counter_ns()
    bundle = _load_bundle(graph_name, Path(graph_path))
    graph_load_ns = time.perf_counter_ns() - graph_load_start
    rss_after_graph_load = current_rss_bytes()

    allocation_start = time.perf_counter_ns()
    runner = Runner(
        bundle,
        _model_spec(seed),
        peak_sensory_external_drive=4.0,
        environment_config=load_environment_config(ENVIRONMENT_PROFILE),
        environment_seed=seed + 1,
        backend="kernel",
    )
    state_allocation_ns = time.perf_counter_ns() - allocation_start
    reset_start = time.perf_counter_ns()
    runner.reset_run()
    reset_ns = time.perf_counter_ns() - reset_start
    rss_after_warmup = current_rss_bytes()
    looming_profile = json.loads(LOOMING_PROFILE.read_text(encoding="utf-8"))
    timings: list[int] = []
    steady_start = time.perf_counter_ns()
    for control_tick in range(interval_count):
        observation, impact = _observation_for_workload(
            workload, control_tick, looming_profile
        )
        interval_start = time.perf_counter_ns()
        runner.advance_control_interval(observation, impact_at_end=impact)
        elapsed = time.perf_counter_ns() - interval_start
        timing_buffer[control_tick] = elapsed
        timings.append(elapsed)
        progress.value = control_tick + 1
    steady_execution_ns = time.perf_counter_ns() - steady_start
    manifest = json.loads((bundle.directory / "manifest.json").read_text())
    all_graph_bytes = sum(int(item["bytes"]) for item in manifest["arrays"].values())
    runtime_names = ("ids", "offsets", "targets", "counts", "weights")
    runtime_graph_bytes = sum(
        int(manifest["arrays"][name]["bytes"]) for name in runtime_names
    )
    summary = runner.finish_run()
    return {
        "graph": graph_name,
        "workload": workload,
        "graph_semantic_digest": bundle.semantic_graph_digest,
        "graph_identity": {
            "N": bundle.n,
            "E": int(bundle.graph.targets.size),
            "contacts": int(np.sum(bundle.counts, dtype=np.uint64)),
        },
        "graph_load_mmap_ns": graph_load_ns,
        "state_allocation_ns": state_allocation_ns,
        "state_reset_ns": reset_ns,
        "steady_execution_ns": steady_execution_ns,
        "raw_interval_timings_ns": timings,
        "work": runner.neural.work_counters(),
        "memory": {
            "on_disk_all_compiled_array_bytes": all_graph_bytes,
            "on_disk_mmap_runtime_graph_array_bytes": runtime_graph_bytes,
            "private_neural_state_array_bytes": runner.neural.private_state_bytes(),
            "process_rss_after_graph_load_bytes": rss_after_graph_load,
            "process_rss_after_warmup_and_reset_bytes": rss_after_warmup,
            "peak_process_rss_bytes": peak_rss_bytes(),
            "mmap_bytes_are_not_claimed_as_private_rss": True,
        },
        "summary": {
            "finite_state": summary["finite_state"],
            "dnp01_spike_count": summary["dnp01_spike_count"],
            "escape_command_count": summary["escape_command_count"],
        },
    }


def _state_comparison(left: Any, right: Any) -> tuple[bool, float, float]:
    exact = (
        left.tick == right.tick
        and left.seed == right.seed
        and np.array_equal(left.refractory_until_tick, right.refractory_until_tick)
        and np.array_equal(left.pending_spikes, right.pending_spikes)
        and np.array_equal(left.pending_inputs, right.pending_inputs)
        and left.rng.bit_generator.state == right.rng.bit_generator.state
    )
    voltage_error = float(np.max(np.abs(left.voltage - right.voltage)))
    current_error = float(
        np.max(np.abs(left.synaptic_current - right.synaptic_current))
    )
    numerical = np.allclose(left.voltage, right.voltage, atol=1e-10, rtol=1e-10)
    numerical = numerical and np.allclose(
        left.synaptic_current, right.synaptic_current, atol=1e-10, rtol=1e-10
    )
    return bool(exact and numerical), voltage_error, current_error


def _response_signature(summary: dict[str, Any]) -> dict[str, Any]:
    spikes = summary["dnp01_spikes"]
    return {
        "total_dnp01_spike_count": summary["dnp01_spike_count"],
        "first_dnp01_spike_neural_tick": spikes[0]["neural_tick"] if spikes else None,
        "escape_command_count": summary["escape_command_count"],
    }


def circuit_parity_evidence() -> dict[str, Any]:
    bundle = load_graph(ROOT / "data/compiled/escape")
    model = _model_spec(20260916)
    looming = json.loads(LOOMING_PROFILE.read_text())
    scenarios: dict[str, Any] = {}
    kernel_trials: dict[str, tuple[Runner, dict[str, Any]]] = {}
    maximum_voltage_error = 0.0
    maximum_current_error = 0.0
    exact_checks = True
    cases = [(scenario, "normal") for scenario in NORMAL_SCENARIOS] + [
        ("standard looming", "output_clamp"),
        ("standard looming", "pathway_intervention"),
    ]
    for scenario, mode in cases:
        intervention = (
            build_direct_visual_to_dnp01_zero(bundle, INTERVENTION_PROFILE)
            if mode == "pathway_intervention"
            else None
        )
        common = {
            "peak_sensory_external_drive": 4.0,
            "environment_config": load_environment_config(ENVIRONMENT_PROFILE),
            "environment_seed": 20260917,
            "output_clamp": mode == "output_clamp",
            "intervention": intervention,
        }
        reference = Runner(bundle, model, backend="reference", **common)
        kernel = Runner(bundle, model, backend="kernel", **common)
        boundary_pass = True
        for control_tick in range(80):
            observation, impact = scripted_observation(looming, scenario, control_tick)
            left_record = reference.advance_control_interval(
                observation, impact_at_end=impact
            )
            right_record = kernel.advance_control_interval(
                observation, impact_at_end=impact
            )
            state_pass, voltage_error, current_error = _state_comparison(
                reference.neural, kernel.neural
            )
            maximum_voltage_error = max(maximum_voltage_error, voltage_error)
            maximum_current_error = max(maximum_current_error, current_error)
            record_keys = (
                "dnp01_spikes",
                "all_population_spike_count",
                "decoded_next_command",
                "impacts",
                "finite_state",
            )
            records_equal = all(
                left_record[key] == right_record[key] for key in record_keys
            )
            boundary_pass = boundary_pass and state_pass and records_equal
        left_summary = reference.finish_run()
        right_summary = kernel.finish_run()
        summary_keys = (
            "dnp01_spikes",
            "escape_command_control_ticks",
            "impacts",
            "finite_state",
        )
        summary_equal = all(
            left_summary[key] == right_summary[key] for key in summary_keys
        )
        exact_checks = exact_checks and boundary_pass and summary_equal
        key = f"{mode}:{scenario}"
        scenarios[key] = {
            "status": "PASS" if boundary_pass and summary_equal else "FAIL",
            "control_boundaries_compared": 80,
            "reference_response_signature": _response_signature(left_summary),
            "kernel_response_signature": _response_signature(right_summary),
            "dnp01_spikes_exact": left_summary["dnp01_spikes"]
            == right_summary["dnp01_spikes"],
            "command_ticks_exact": left_summary["escape_command_control_ticks"]
            == right_summary["escape_command_control_ticks"],
            "impact_outcomes_exact": left_summary["impacts"] == right_summary["impacts"],
            "finite_status_exact": left_summary["finite_state"]
            == right_summary["finite_state"],
        }
        kernel_trials[key] = (kernel, right_summary)

    normal_no_threat = kernel_trials["normal:no-threat"][1]
    normal_looming_runner, normal_looming = kernel_trials["normal:standard looming"]
    static = kernel_trials["normal:matched non-looming/static-size"][1]
    receding = kernel_trials["normal:receding"][1]
    clamped_runner, clamped = kernel_trials["output_clamp:standard looming"]
    pathway = kernel_trials["pathway_intervention:standard looming"][1]
    looming_signature = _response_signature(normal_looming)
    pathway_signature = _response_signature(pathway)
    first_command = (
        normal_looming["escape_command_control_ticks"][0]
        if normal_looming["escape_command_control_ticks"]
        else None
    )
    recovery_start = 70
    recovery_ok = not any(
        tick >= recovery_start
        for tick in normal_looming["escape_command_control_ticks"]
    ) and not any(
        spike["neural_tick"] >= recovery_start * 20
        for spike in normal_looming["dnp01_spikes"]
    )
    gbio_checks = {
        "no_threat_zero_commands": normal_no_threat["escape_command_count"] == 0,
        "standard_looming_dnp01_response": normal_looming["dnp01_spike_count"] >= 1,
        "standard_looming_escape_command": normal_looming["escape_command_count"] >= 1,
        "first_command_before_600_ms": first_command is not None and first_command < 60,
        "differs_from_static": looming_signature != _response_signature(static),
        "differs_from_receding": looming_signature != _response_signature(receding),
        "output_clamp_zero_commands": clamped["escape_command_count"] == 0,
        "output_clamp_neural_trace_unchanged": [
            item["neural_state_sha256"] for item in normal_looming_runner.interval_records
        ]
        == [item["neural_state_sha256"] for item in clamped_runner.interval_records],
        "pathway_response_signature_differs": looming_signature != pathway_signature,
        "finite_state": all(
            summary["finite_state"] for _, summary in kernel_trials.values()
        ),
        "post_stimulus_recovery": recovery_ok,
    }
    parity_profile_sha = sha256_file(PARITY_PROFILE)
    configuration = kernel_configuration()
    passed = exact_checks and all(gbio_checks.values()) and not configuration["parallel"]
    passed = passed and not configuration["fastmath"]
    return {
        "schema_version": 1,
        "status": "PASS" if passed else "FAIL",
        "parity_profile_sha256": parity_profile_sha,
        "atol": 1e-10,
        "rtol": 1e-10,
        "kernel_configuration": configuration,
        "maximum_voltage_absolute_error": maximum_voltage_error,
        "maximum_synaptic_current_absolute_error": maximum_current_error,
        "scenarios": scenarios,
        "circuit_gbio_preservation": {
            "status": "PASS" if all(gbio_checks.values()) else "FAIL",
            "checks": gbio_checks,
            "normal_standard_looming_signature": looming_signature,
            "pathway_intervention_signature": pathway_signature,
        },
        "required_unit_test_file": "tests/test_kernel_parity.py",
    }


def timing_summary(results: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    complete = [item for item in results if item["status"] == "COMPLETE"]
    pooled = [value for item in complete for value in item["raw_interval_timings_ns"]]
    target_ns = int(float(profile["headroom_target_ms"]) * 1_000_000)
    deadline_ns = int(float(profile["control_deadline_ms"]) * 1_000_000)
    metrics: dict[str, Any] | None = None
    if pooled:
        values = np.asarray(pooled, dtype=np.int64)
        metrics = {
            "sample_count": int(values.size),
            "p50_ns": float(np.percentile(values, 50)),
            "p95_ns": float(np.percentile(values, 95)),
            "p99_ns": float(np.percentile(values, 99)),
            "max_ns": int(np.max(values)),
            "mean_ns": float(np.mean(values)),
            "count_interval_gt_7_ms": int(np.count_nonzero(values > target_ns)),
            "count_interval_gt_10_ms": int(np.count_nonzero(values > deadline_ns)),
            "deadline_miss_fraction": float(np.count_nonzero(values > deadline_ns) / values.size),
        }
    return {
        "repeat_count_requested": len(results),
        "complete_repeat_count": len(complete),
        "timeout_repeat_count": sum(item["status"] == "TIMEOUT" for item in results),
        "error_repeat_count": sum(item["status"] == "ERROR" for item in results),
        "metrics": metrics,
        "repeat_wall_seconds_per_simulated_second": [
            item["steady_execution_ns"] / 1_000_000_000 for item in complete
        ],
        "repeats": results,
    }


def _graph_performance(
    graph: str, results: dict[str, list[dict[str, Any]]], profile: dict[str, Any]
) -> dict[str, Any]:
    workloads = {
        workload: timing_summary(results[workload], profile)
        for workload in ("quiet", "nominal", "sustained")
    }
    return {
        "schema_version": 1,
        "graph": graph,
        "backend": "kernel",
        "probe_profile_sha256": sha256_file(ROOT / "profiles/full-probe.json"),
        "status": "COMPLETE" if all(
            value["complete_repeat_count"] == 3
            and value["timeout_repeat_count"] == 0
            and value["error_repeat_count"] == 0
            for value in workloads.values()
        ) else "INCOMPLETE",
        "workloads": workloads,
    }


def _interactive_checks(performance: dict[str, Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for workload, report in performance["workloads"].items():
        metrics = report["metrics"]
        result[f"{workload}_all_repeats_complete"] = (
            report["complete_repeat_count"] == 3
            and report["timeout_repeat_count"] == 0
            and report["error_repeat_count"] == 0
        )
        result[f"{workload}_p99_le_7_ms"] = bool(
            metrics is not None and metrics["p99_ns"] <= 7_000_000
        )
        result[f"{workload}_zero_intervals_gt_10_ms"] = bool(
            metrics is not None and metrics["count_interval_gt_10_ms"] == 0
        )
    return result


def full_authority_carryover() -> dict[str, Any]:
    bundle = load_full_graph(ROOT / "data/compiled/full", PORTS_PROFILE)
    model = _model_spec(20260916)
    looming = json.loads(LOOMING_PROFILE.read_text())

    def run(mode: str, scenario: str, intervention: Any = None) -> tuple[Runner, dict[str, Any]]:
        runner = Runner(
            bundle,
            model,
            peak_sensory_external_drive=4.0,
            environment_config=load_environment_config(ENVIRONMENT_PROFILE),
            environment_seed=20260917,
            output_clamp=mode == "output_clamp",
            intervention=intervention,
            backend="kernel",
        )
        for tick in range(80):
            observation, impact = scripted_observation(looming, scenario, tick)
            runner.advance_control_interval(observation, impact_at_end=impact)
        return runner, runner.finish_run()

    no_threat_runner, no_threat = run("normal", "no-threat")
    del no_threat_runner
    normal_runner, normal = run("normal", "standard looming")
    clamp_runner, clamp = run("output_clamp", "standard looming")
    intervention = build_direct_visual_to_dnp01_zero(bundle, INTERVENTION_PROFILE)
    pathway_runner, pathway = run(
        "pathway_intervention", "standard looming", intervention
    )
    del pathway_runner
    first_command = (
        normal["escape_command_control_ticks"][0]
        if normal["escape_command_control_ticks"]
        else None
    )
    normal_signature = _response_signature(normal)
    pathway_signature = _response_signature(pathway)
    checks = {
        "no_threat_zero_escape_commands": no_threat["escape_command_count"] == 0,
        "standard_looming_dnp01_spike": normal["dnp01_spike_count"] >= 1,
        "standard_looming_escape_command": normal["escape_command_count"] >= 1,
        "first_command_before_600_ms_impact": first_command is not None
        and first_command < 60,
        "output_clamp_zero_escape_commands": clamp["escape_command_count"] == 0,
        "output_clamp_neural_trace_unchanged": [
            item["neural_state_sha256"] for item in normal_runner.interval_records
        ]
        == [item["neural_state_sha256"] for item in clamp_runner.interval_records],
        "pathway_response_signature_differs": normal_signature != pathway_signature,
        "finite_state": no_threat["finite_state"]
        and normal["finite_state"]
        and clamp["finite_state"]
        and pathway["finite_state"],
        "post_stimulus_recovery": not any(
            spike["neural_tick"] >= 1400 for spike in normal["dnp01_spikes"]
        )
        and not any(tick >= 70 for tick in normal["escape_command_control_ticks"]),
    }
    return {
        "schema_version": 1,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "graph_semantic_digest": bundle.semantic_graph_digest,
        "checks": checks,
        "normal_standard_looming_signature": normal_signature,
        "pathway_intervention_signature": pathway_signature,
        "circuit_exact_spike_reproduction_required": False,
        "context_difference_note": "Any circuit/full signature difference is a measured graph-context effect; no full-graph recalibration was performed.",
    }


def hardware_receipt() -> dict[str, Any]:
    cpu_model = None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    total_ram = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                total_ram = int(line.split()[1]) * 1024
                break
    except OSError:
        pass
    release = platform.release()
    wsl = "microsoft" in release.lower() or bool(os.environ.get("WSL_DISTRO_NAME"))
    try:
        affinity = sorted(os.sched_getaffinity(0))
    except AttributeError:
        affinity = None
    uv_result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
    thread_keys = (
        "NUMBA_NUM_THREADS",
        "NUMBA_THREADING_LAYER",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    )
    receipt = {
        "schema_version": 1,
        "measurement_machine_classification": (
            "current WSL2 development machine; not claimed as production host; feasibility provisional until M15"
            if wsl
            else "current measurement machine; not claimed as production host; feasibility provisional until M15"
        ),
        "cpu_model": cpu_model,
        "logical_cpu_count": os.cpu_count(),
        "process_cpu_affinity": affinity,
        "total_ram_bytes": total_ram,
        "os": platform.system(),
        "kernel_release": release,
        "platform": platform.platform(),
        "wsl_status": "WSL2" if wsl and "wsl2" in release.lower() else ("WSL" if wsl else "native_or_unidentified"),
        "python": platform.python_version(),
        "python_full": sys.version,
        "numpy": np.__version__,
        "numba": numba.__version__,
        "llvmlite": llvmlite.__version__,
        "uv": uv_result.stdout.strip() if uv_result.returncode == 0 else None,
        "thread_environment": {key: os.environ.get(key) for key in thread_keys},
    }
    receipt["hardware_identity_sha256"] = hashlib.sha256(canonical_bytes(receipt)).hexdigest()
    return receipt


def validate_profile(profile: dict[str, Any], profile_path: Path) -> None:
    if profile["graphs"]["circuit"]["semantic_digest"] != ACCEPTED_CIRCUIT_DIGEST:
        raise ValueError("probe circuit identity changed")
    if profile["graphs"]["full"]["semantic_digest"] != ACCEPTED_FULL_GRAPH_DIGEST:
        raise ValueError("probe full graph identity changed")
    if profile["model"]["selected_runtime_model_spec_sha256"] != EXPECTED_IDENTITIES[
        "selected_runtime_model_spec_sha256"
    ]:
        raise ValueError("probe ModelSpec identity changed")
    if profile["controller"]["profile_sha256"] != sha256_file(CONTROLLER_PROFILE):
        raise ValueError("probe controller identity changed")
    if profile["repeats_per_graph_workload"] != 3:
        raise ValueError("M07 requires three independent repeats")
    if profile["full_repeat_hard_wall_timeout_seconds"] != 60.0:
        raise ValueError("M07 full timeout must remain exactly 60 seconds")
    if profile_path.resolve() != (ROOT / "profiles/full-probe.json").resolve():
        raise ValueError("M07 measurements require the tracked full-probe profile")


def main() -> int:
    process_interpreter_startup_to_main_ns = time.perf_counter_ns() - PROCESS_START_NS
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    profile_path = args.profile.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    validate_profile(profile, profile_path)

    hardware = hardware_receipt()
    write_json(out / "hardware.json", hardware)
    warm_start = time.perf_counter_ns()
    warm_kernel()
    jit_warmup_ns = time.perf_counter_ns() - warm_start
    parity = circuit_parity_evidence()
    write_json(out / "kernel-parity.json", parity)

    timeout_result = run_worker_with_timeout(
        finite_delay_worker,
        (0.2, 2),
        timeout_seconds=0.05,
        interval_capacity=3,
        temporary_parent=out,
    )
    timeout_evidence = {
        "schema_version": 1,
        "status": "PASS"
        if timeout_result["status"] == "TIMEOUT"
        and timeout_result["completed_intervals"] == 2
        and not timeout_result["worker_alive_after_join"]
        and timeout_result["temporary_worker_state_released"]
        else "FAIL",
        "forced_timeout_result": timeout_result,
        "result_status_schema": ["TIMEOUT", "COMPLETE", "ERROR"],
        "partial_completion_is_complete": False,
    }
    write_json(out / "timeout-test.json", timeout_evidence)

    all_results: dict[str, dict[str, list[dict[str, Any]]]] = {
        graph: {workload: [] for workload in ("quiet", "nominal", "sustained")}
        for graph in ("circuit", "full")
    }
    for graph in ("circuit", "full"):
        graph_path = ROOT / profile["graphs"][graph]["path"]
        timeout = float(
            profile[
                "full_repeat_hard_wall_timeout_seconds"
                if graph == "full"
                else "circuit_repeat_hard_wall_timeout_seconds"
            ]
        )
        for workload in ("quiet", "nominal", "sustained"):
            intervals = int(profile["workloads"][workload]["control_intervals"])
            for repeat in range(3):
                result = run_worker_with_timeout(
                    probe_worker,
                    (
                        graph,
                        str(graph_path),
                        workload,
                        intervals,
                        int(profile["model"]["seed"]),
                    ),
                    timeout_seconds=timeout,
                    interval_capacity=intervals,
                    temporary_parent=out,
                )
                result["repeat_index"] = repeat
                result["graph"] = graph
                result["workload"] = workload
                all_results[graph][workload].append(result)
                print(
                    f"{graph}/{workload}/repeat-{repeat}: {result['status']} "
                    f"({result['completed_intervals']}/{intervals} intervals)",
                    flush=True,
                )

    raw_path = out / "raw-interval-timings.jsonl"
    with raw_path.open("w", encoding="utf-8") as stream:
        for graph in ("circuit", "full"):
            for workload in ("quiet", "nominal", "sustained"):
                for result in all_results[graph][workload]:
                    for interval, elapsed in enumerate(
                        result["raw_interval_timings_ns"]
                    ):
                        stream.write(
                            json.dumps(
                                {
                                    "schema_version": 1,
                                    "graph": graph,
                                    "workload": workload,
                                    "repeat_index": result["repeat_index"],
                                    "repeat_status": result["status"],
                                    "control_interval_index": interval,
                                    "elapsed_ns": elapsed,
                                },
                                sort_keys=True,
                            )
                            + "\n"
                        )

    circuit_performance = _graph_performance("circuit", all_results["circuit"], profile)
    full_performance = _graph_performance("full", all_results["full"], profile)
    write_json(out / "circuit-performance.json", circuit_performance)
    write_json(out / "full-performance.json", full_performance)

    memory = {
        "schema_version": 1,
        "status": "COMPLETE"
        if all(
            any(item["status"] == "COMPLETE" for item in all_results[graph]["quiet"])
            for graph in ("circuit", "full")
        )
        else "INCOMPLETE",
        "numba_jit_cold_cost_ns": jit_warmup_ns,
        "process_interpreter_startup_to_main_ns": process_interpreter_startup_to_main_ns,
        "graphs": {
            graph: next(
                (
                    item["memory"]
                    for workload in ("quiet", "nominal", "sustained")
                    for item in all_results[graph][workload]
                    if item["status"] == "COMPLETE"
                ),
                None,
            )
            for graph in ("circuit", "full")
        },
        "worker_stage_receipts": {
            graph: [
                {
                    "workload": workload,
                    "repeat_index": item["repeat_index"],
                    "status": item["status"],
                    "worker_process_startup_ns": item.get("worker_process_startup_ns"),
                    "graph_load_mmap_ns": item.get("graph_load_mmap_ns"),
                    "state_allocation_ns": item.get("state_allocation_ns"),
                    "state_reset_ns": item.get("state_reset_ns"),
                }
                for workload in ("quiet", "nominal", "sustained")
                for item in all_results[graph][workload]
            ]
            for graph in ("circuit", "full")
        },
        "accounting_note": "Mapped graph file bytes and process RSS are separate observations; mmap bytes are not claimed as private RSS. No multi-worker host-capacity extrapolation is made in M07.",
    }
    write_json(out / "memory.json", memory)

    circuit_checks = _interactive_checks(circuit_performance)
    full_checks = _interactive_checks(full_performance)
    full_otherwise_qualifies = (
        parity["status"] == "PASS"
        and timeout_evidence["status"] == "PASS"
        and memory["status"] == "COMPLETE"
        and all(full_checks.values())
    )
    if full_otherwise_qualifies:
        full_authority = full_authority_carryover()
    else:
        full_authority = {
            "schema_version": 1,
            "status": "NOT_RUN",
            "reason": "Full graph did not otherwise satisfy every computational PROVISIONAL_FULL condition; authority carryover is conditionally required only for an otherwise qualifying full graph.",
        }
    write_json(out / "full-authority-carryover.json", full_authority)

    optimization = {
        "schema_version": 1,
        "optimization_passes_used": 0,
        "candidate_alpha_full_graph_optimization_passes_used": 0,
        "status": "NOT_USED",
        "reason": (
            "Initial full-graph measurements satisfied the computational target; no optimization was justified."
            if full_otherwise_qualifies
            else "Selected the disclosed accepted circuit after the initial bounded full-graph measurement; no full-graph optimization pass was used."
        ),
        "before_after_comparison": None,
    }
    profiler = {
        "schema_version": 1,
        "status": "NOT_PERFORMED",
        "reason": "No optimization pass was used; workload timing and explicit activity/edge-work counters are the retained initial implementation evidence.",
        "initial_measurement_reference": "full-performance.json",
    }
    write_json(out / "optimization.json", optimization)
    write_json(out / "profiler.json", profiler)

    full_failed = [name for name, passed in full_checks.items() if not passed]
    authority_pass = full_authority["status"] == "PASS"
    selection = (
        "PROVISIONAL_FULL"
        if full_otherwise_qualifies and authority_pass
        else "DISCLOSED_CIRCUIT"
    )
    circuit_valid = parity["status"] == "PASS" and all(circuit_checks.values())
    gate_outcome = "PASS" if (
        selection == "PROVISIONAL_FULL" or circuit_valid
    ) else "FAIL"
    decision = {
        "schema_version": 1,
        "gate": "G-FULL",
        "outcome": gate_outcome,
        "selection": selection,
        "selected_backend": "kernel" if circuit_valid or selection == "PROVISIONAL_FULL" else None,
        "kernel_status": "serving-candidate" if circuit_valid else "experimental-not-serving",
        "external_milestone_acceptance": "PENDING",
        "kernel_parity_status": parity["status"],
        "circuit_conditions": circuit_checks,
        "full_conditions": full_checks,
        "full_authority_carryover_status": full_authority["status"],
        "failed_full_graph_conditions": full_failed
        + (
            ["full_authority_carryover_pass"]
            if full_otherwise_qualifies and not authority_pass
            else []
        ),
        "failed_full_graph_condition_details": {
            workload: {
                "p99_ns": full_performance["workloads"][workload]["metrics"]["p99_ns"],
                "count_interval_gt_7_ms": full_performance["workloads"][workload]["metrics"]["count_interval_gt_7_ms"],
                "count_interval_gt_10_ms": full_performance["workloads"][workload]["metrics"]["count_interval_gt_10_ms"],
                "timeout_repeat_count": full_performance["workloads"][workload]["timeout_repeat_count"],
                "error_repeat_count": full_performance["workloads"][workload]["error_repeat_count"],
            }
            for workload in ("quiet", "nominal", "sustained")
        },
        "reasons": (
            ["Every predeclared full-graph computational, memory, parity, and authority condition passed on the measurement CPU."]
            if selection == "PROVISIONAL_FULL"
            else [
                "The full graph did not satisfy every PROVISIONAL_FULL condition.",
                "The accepted disclosed circuit with the parity-validated kernel is the bounded live candidate.",
            ]
        ),
        "optimization_passes_used": 0,
        "provisional_until_m15": True,
    }
    write_json(out / "decision.json", decision)

    evidence_names = (
        "hardware.json",
        "kernel-parity.json",
        "circuit-performance.json",
        "full-performance.json",
        "raw-interval-timings.jsonl",
        "memory.json",
        "timeout-test.json",
        "full-authority-carryover.json",
        "profiler.json",
        "optimization.json",
        "decision.json",
    )
    evidence_manifest = {
        name: {"sha256": sha256_file(out / name), "bytes": (out / name).stat().st_size}
        for name in evidence_names
    }
    measurement_digest = hashlib.sha256(canonical_bytes(evidence_manifest)).hexdigest()
    selected_graph = profile["graphs"][
        "full" if selection == "PROVISIONAL_FULL" else "circuit"
    ]
    candidate = {
        "schema_version": 1,
        "profile_id": "flybench.live-candidate.v0.1",
        "classification": "M07 CANDIDATE — external acceptance pending; not profiles/live.json",
        "g_full_decision": selection,
        "graph": {
            "semantic_digest": selected_graph["semantic_digest"],
            "N": selected_graph["N"],
            "E": selected_graph["E"],
            "contacts": selected_graph["contacts"],
        },
        "backend": "kernel",
        "controller_profile_sha256": EXPECTED_IDENTITIES["controller_profile_sha256"],
        "runtime_model_spec_sha256": EXPECTED_IDENTITIES["selected_runtime_model_spec_sha256"],
        "encoder_profile_sha256": EXPECTED_IDENTITIES["encoder_profile_sha256"],
        "decoder_profile_sha256": EXPECTED_IDENTITIES["decoder_profile_sha256"],
        "environment_profile_sha256": EXPECTED_IDENTITIES["environment_profile_sha256"],
        "neural_dt_ms": 0.5,
        "control_interval_ms": 10.0,
        "neural_steps_per_control_interval": 20,
        "implementation": {
            "kernel_id": KERNEL_IMPLEMENTATION_ID,
            "kernel_source_sha256": sha256_file(ROOT / "src/flybench/kernel.py"),
            "reference_source_sha256": sha256_file(ROOT / "src/flybench/reference.py"),
            "numba": numba.__version__,
            "llvmlite": llvmlite.__version__,
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
        "measured_hardware_identity_sha256": hardware["hardware_identity_sha256"],
        "measurement_evidence_sha256": measurement_digest,
        "measurement_evidence_manifest": evidence_manifest,
        "probe_profile_sha256": sha256_file(ROOT / "profiles/full-probe.json"),
        "optimization_passes_used": 0,
        "provisional_until_m15": True,
        "external_milestone_acceptance": "PENDING",
    }
    write_json(ROOT / "profiles/live-candidate-v0.1.json", candidate)
    write_json(out / "live-candidate.json", candidate)
    print(
        json.dumps(
            {
                "status": gate_outcome,
                "selection": selection,
                "candidate_profile": "profiles/live-candidate-v0.1.json",
            },
            sort_keys=True,
        )
    )
    return 0 if gate_outcome == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
