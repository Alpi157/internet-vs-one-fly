#!/usr/bin/env python3
"""Substantive consistency checks for generated M07 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


EXPECTED = {
    "architecture": "bae80837d5d6d769ae5b728af3b80c1caa21b7f08efdd7f3eb458f7bb2eab9d1",
    "full": "429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0",
    "circuit": "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5",
    "source_lock": "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c",
    "controller": "0b3577ec2dc257f130d59f0219544ad0dae479080027e25bdeca2182673bf817",
    "encoder": "7840fa564c7f34d188797899ced5c87ffd9825469172f3a7c1076e36873c7de7",
    "decoder": "7fec8cef8d5ca3679fbf65456f236bab2c5e15e7902aafc5146ce8d83838ca4f",
    "environment": "9119848704b84416e1eed25ed8ae84735216ccb251e83147ea8970e2754968f7",
    "runtime_model": "8fb910576dd01bb28dece1198274072302e03cd7a00808dcec8948e4b2dac2bc",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    evidence = args.out.resolve()
    try:
        required_names = (
            "hardware.json",
            "kernel-parity.json",
            "circuit-performance.json",
            "full-performance.json",
            "memory.json",
            "timeout-test.json",
            "full-authority-carryover.json",
            "profiler.json",
            "optimization.json",
            "live-candidate.json",
            "decision.json",
        )
        documents = {name: load(evidence / name) for name in required_names}
        raw_path = evidence / "raw-interval-timings.jsonl"
        require(raw_path.is_file() and raw_path.stat().st_size > 0, "raw timings missing")
        raw = [json.loads(line) for line in raw_path.read_text().splitlines() if line]

        require(sha256_file(root / "docs/architecture.md") == EXPECTED["architecture"], "architecture identity mismatch")
        require(sha256_file(root / "profiles/source-lock.json") == EXPECTED["source_lock"], "source lock mismatch")
        for name, path in (
            ("controller", "profiles/controller-v0.1.json"),
            ("encoder", "profiles/encoder-runtime-v0.1.json"),
            ("decoder", "profiles/decoder-runtime-v0.1.json"),
            ("environment", "profiles/environment-v0.1.json"),
        ):
            require(sha256_file(root / path) == EXPECTED[name], f"{name} identity mismatch")
        for graph, digest, n, e, contacts in (
            ("full", EXPECTED["full"], 166700, 25582938, 124177617),
            ("escape", EXPECTED["circuit"], 313, 20607, 79112),
        ):
            manifest = load(root / f"data/compiled/{graph}/manifest.json")
            identity = manifest["graph"]
            require(manifest["semantic_digest"]["value"] == digest, f"{graph} digest mismatch")
            require(identity["N"] == n and identity["source_accepted_E"] == e, f"{graph} cardinality mismatch")
            require(identity["represented_source_contacts"] == contacts, f"{graph} contact mismatch")

        parity = documents["kernel-parity.json"]
        require(parity["status"] == "PASS", "kernel parity failed")
        require(parity["circuit_gbio_preservation"]["status"] == "PASS", "circuit G-BIO parity failed")
        require(parity["kernel_configuration"]["parallel"] is False, "parallel kernel prohibited")
        require(parity["kernel_configuration"]["fastmath"] is False, "fastmath kernel prohibited")
        require(parity["atol"] == 1e-10 and parity["rtol"] == 1e-10, "parity tolerance changed")
        require(
            parity["parity_profile_sha256"]
            == sha256_file(root / "profiles/kernel-parity-v0.1.json"),
            "parity profile mismatch",
        )

        timeout = documents["timeout-test.json"]
        forced = timeout["forced_timeout_result"]
        require(timeout["status"] == "PASS", "timeout evidence failed")
        require(forced["status"] == "TIMEOUT", "forced timeout not classified TIMEOUT")
        require(forced["completed_intervals"] < 3, "timeout was falsely complete")
        require(not forced["worker_alive_after_join"], "timed-out worker still alive")
        require(forced["temporary_worker_state_released"], "worker state not released")

        raw_expected = 0
        performance: dict[str, dict[str, Any]] = {}
        for graph, filename in (("circuit", "circuit-performance.json"), ("full", "full-performance.json")):
            report = documents[filename]
            performance[graph] = report
            for workload in ("quiet", "nominal", "sustained"):
                workload_report = report["workloads"][workload]
                for repeat in workload_report["repeats"]:
                    raw_expected += len(repeat["raw_interval_timings_ns"])
                    require(repeat["status"] in {"COMPLETE", "TIMEOUT", "ERROR"}, "invalid repeat status")
                    require(not repeat["worker_alive_after_join"], "probe worker still alive")
                    require(repeat["temporary_worker_state_released"], "probe temporary state retained")
                    if repeat["status"] == "COMPLETE":
                        require(repeat["completed_intervals"] == 100, "complete repeat is partial")
                        work = repeat["work"]
                        require(work["neural_timesteps"] == 2000, "neural timestep accounting mismatch")
                        require(work["all_neuron_updates"] == 2000 * repeat["graph_identity"]["N"], "all-neuron accounting mismatch")
                        for field in (
                            "total_spikes",
                            "active_presynaptic_source_events",
                            "propagated_outgoing_edge_visits",
                            "mean_active_source_count_per_neural_step",
                            "max_active_source_count_per_neural_step",
                        ):
                            require(field in work, f"activity field missing: {field}")
                require(workload_report["metrics"] is not None or workload_report["complete_repeat_count"] == 0, "timing metrics missing")
        require(len(raw) == raw_expected, "raw timing row count differs from repeat evidence")
        require(all(type(item["elapsed_ns"]) is int and item["elapsed_ns"] >= 0 for item in raw), "raw timings are not exact nonnegative integers")

        memory = documents["memory.json"]
        require(memory["status"] == "COMPLETE", "memory evidence incomplete")
        require(memory["numba_jit_cold_cost_ns"] > 0, "JIT cold cost missing")
        for graph in ("circuit", "full"):
            item = memory["graphs"][graph]
            require(item is not None, f"{graph} memory evidence missing")
            require(item["on_disk_mmap_runtime_graph_array_bytes"] > 0, "graph bytes missing")
            require(item["private_neural_state_array_bytes"]["delay_ring"] > 0, "delay ring bytes missing")
            require(item["mmap_bytes_are_not_claimed_as_private_rss"] is True, "mmap/RSS accounting conflated")

        optimization = documents["optimization.json"]
        require(optimization["optimization_passes_used"] in (0, 1), "invalid optimization count")
        require(optimization["optimization_passes_used"] == documents["decision.json"]["optimization_passes_used"], "optimization count inconsistent")
        decision = documents["decision.json"]
        require(decision["gate"] == "G-FULL" and decision["outcome"] == "PASS", "G-FULL did not pass")
        require(decision["selection"] in {"PROVISIONAL_FULL", "DISCLOSED_CIRCUIT"}, "invalid G-FULL selection")
        require(decision["external_milestone_acceptance"] == "PENDING", "external acceptance claimed")
        if decision["selection"] == "PROVISIONAL_FULL":
            require(documents["full-authority-carryover.json"]["status"] == "PASS", "full authority carryover failed")
        else:
            circuit = performance["circuit"]
            for workload in circuit["workloads"].values():
                metrics = workload["metrics"]
                require(workload["complete_repeat_count"] == 3, "circuit repeat incomplete")
                require(metrics["p99_ns"] <= 7_000_000, "circuit p99 exceeds target")
                require(metrics["count_interval_gt_10_ms"] == 0, "circuit missed deadline")

        candidate = documents["live-candidate.json"]
        committed_candidate = load(root / "profiles/live-candidate-v0.1.json")
        require(candidate == committed_candidate, "candidate profile/evidence mismatch")
        require(candidate["g_full_decision"] == decision["selection"], "candidate decision mismatch")
        require(candidate["controller_profile_sha256"] == EXPECTED["controller"], "candidate controller mismatch")
        require(candidate["runtime_model_spec_sha256"] == EXPECTED["runtime_model"], "candidate ModelSpec mismatch")
        require(candidate["implementation"]["kernel_source_sha256"] == sha256_file(root / "src/flybench/kernel.py"), "candidate kernel source mismatch")
        require(candidate["optimization_passes_used"] == optimization["optimization_passes_used"], "candidate optimization count mismatch")
        require(candidate["provisional_until_m15"] is True, "M15 provisional condition missing")
        require(candidate["external_milestone_acceptance"] == "PENDING", "candidate claims acceptance")
        require(documents["hardware.json"]["hardware_identity_sha256"] == candidate["measured_hardware_identity_sha256"], "hardware identity mismatch")
        require(documents["hardware.json"]["numba"] == candidate["implementation"]["numba"], "Numba version mismatch")
        require(documents["hardware.json"]["llvmlite"] == candidate["implementation"]["llvmlite"], "llvmlite version mismatch")
        require(documents["hardware.json"]["numpy"] == candidate["implementation"]["numpy"], "NumPy version mismatch")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "selection": documents["decision.json"]["selection"],
                "raw_interval_timing_rows": len(raw),
                "optimization_passes_used": documents["optimization.json"]["optimization_passes_used"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
