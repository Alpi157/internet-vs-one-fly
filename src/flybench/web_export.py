"""Compact little-endian graph export and parity fixtures for kernel-ts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from typing import Any

import numpy as np

from flybench.game import build_live_session, load_live_profile
from flybench.graph import write_json
from flybench.kernel import KernelGraph
from flybench.reference import ReferenceGraph
from flybench.reference_v2 import NoiseSpec, ReferenceStateV2


ROOT = Path(__file__).resolve().parents[2]
MAGIC = b"FLYWEB1\0"
ARRAY_ORDER = ("ids", "offsets", "targets", "counts", "weights")
DTYPES = {
    "ids": "<u8",
    "offsets": "<i8",
    "targets": "<i4",
    "counts": "<u8",
    "weights": "<f8",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _state_digest(state: Any, domain: bytes) -> str:
    digest = hashlib.sha256(domain)
    digest.update(int(state.tick).to_bytes(8, "little", signed=False))
    for value in (
        state.voltage,
        state.synaptic_current,
        state.refractory_until_tick,
        state.pending_spikes,
        state.pending_inputs,
    ):
        digest.update(np.ascontiguousarray(value).tobytes())
    return digest.hexdigest()


def export_web_graph(directory: Path, output: Path) -> dict[str, Any]:
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    arrays = {
        name: np.asarray(np.load(directory / f"{name}.npy", allow_pickle=False), dtype=np.dtype(DTYPES[name]))
        for name in ARRAY_ORDER
    }
    sections = {}
    offset = 0
    payload = bytearray()
    for name in ARRAY_ORDER:
        alignment = np.dtype(DTYPES[name]).itemsize
        padding = (-offset) % alignment
        if padding:
            payload.extend(b"\0" * padding)
            offset += padding
        data = np.ascontiguousarray(arrays[name]).tobytes()
        sections[name] = {
            "byte_offset": offset,
            "byte_length": len(data),
            "length": int(arrays[name].size),
            "dtype": DTYPES[name],
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        payload.extend(data)
        offset += len(data)
    header = {
        "format": "flybench.web-graph.v1",
        "byte_order": "little-endian",
        "semantic_graph_digest": manifest["semantic_digest"]["value"],
        "source_lock_sha256": manifest["source_lock_sha256"],
        "N": int(arrays["ids"].size),
        "E": int(arrays["targets"].size),
        "sections": sections,
    }
    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    prefix_size = len(MAGIC) + 4 + len(header_bytes)
    padding = (-prefix_size) % 8
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        MAGIC
        + struct.pack("<I", len(header_bytes))
        + header_bytes
        + b"\0" * padding
        + payload
    )
    try:
        reported_path = str(output.resolve().relative_to(ROOT))
    except ValueError:
        reported_path = str(output.resolve())
    result = {
        **header,
        "path": reported_path,
        "bytes": output.stat().st_size,
        "sha256": _sha256(output),
        "payload_offset": prefix_size + padding,
    }
    write_json(output.with_suffix(output.suffix + ".json"), result)
    return result


def export_v2a_bot_log(output: Path) -> dict[str, Any]:
    from experiments.p0_truth_checks import _run_neural_round

    profile = json.loads((ROOT / "profiles/p0-bots-v1.json").read_text(encoding="utf-8"))
    resolved = load_live_profile(ROOT / "profiles/live.json")
    session = build_live_session(resolved)
    result, plan = _run_neural_round(session, profile["strategies"][0], profile, 202609280000)
    intervals = [
        {
            "held_lc4": record["held_drive"]["LC4"],
            "held_lplc2": record["held_drive"]["LPLC2"],
            "expected_state_sha256": record["neural_state_sha256"],
        }
        for record in session.runner.interval_records
    ]
    report = {
        "schema": "flybench.v2a.bot-input-parity-log",
        "version": 1,
        "strategy": "current-position",
        "seed": 202609280000,
        "source_profile": "profiles/p0-bots-v1.json",
        "result": result["result"],
        "planned_attacks": [
            {
                "reaction_intervals": value.reaction_intervals,
                "target_x": value.target_x,
                "target_y": value.target_y,
            }
            for value in plan
        ],
        "model": {
            "runtime_synaptic_scale": 0.001,
            "current_decay": 0.9048374180359595,
            "voltage_decay": 0.9753099120283326,
            "held_drive_factor": 0.024690087971667385,
            "current_coupling_factor": 0.02349083133079103,
            "rest": 0.0,
            "reset": 0.0,
            "threshold": 1.0,
            "refractory_ticks": 4,
            "delay_ticks": 2,
        },
        "digest_domain_utf8_nul": "FlyBench M06 complete neural state v1",
        "input_populations": {
            name: json.loads((ROOT / "profiles/escape-circuit.json").read_text(encoding="utf-8"))["populations"][name]["body_ids_decimal"]
            for name in ("LC4", "LPLC2")
        },
        "intervals": intervals,
    }
    write_json(output, report)
    return report


def export_t1a_noise_parity(directory: Path, output: Path) -> dict[str, Any]:
    arrays = {
        name: np.load(directory / f"{name}.npy", allow_pickle=False)
        for name in ("offsets", "targets", "weights")
    }
    graph = ReferenceGraph(**arrays)
    spec = build_live_session(load_live_profile(ROOT / "profiles/live.json")).runner.model_spec
    noise = NoiseSpec(2026092802, 17, 42949673, 0.05, np.ones(graph.n, dtype=np.bool_))
    state = ReferenceStateV2(spec, graph, noise)
    drive = np.zeros(graph.n, dtype=np.float64)
    domain = b"FlyBench v2 complete neural state v1\0"
    intervals = []
    for interval in range(100):
        for _ in range(20):
            state.step(drive)
        intervals.append({"control_interval": interval + 1, "expected_state_sha256": _state_digest(state, domain)})
    report = {
        "schema": "flybench.v2b.t1a-noise-parity",
        "version": 1,
        "simulated_ms": 1000,
        "model": {
            "runtime_synaptic_scale": spec.runtime_synaptic_scale,
            "current_decay": 0.9048374180359595,
            "voltage_decay": 0.9753099120283326,
            "held_drive_factor": 0.024690087971667385,
            "current_coupling_factor": 0.02349083133079103,
            "rest": 0.0,
            "reset": 0.0,
            "threshold": 1.0,
            "refractory_ticks": 4,
            "delay_ticks": 2,
        },
        "noise": {"seed": 2026092802, "stream_id": 17, "threshold": 42949673, "current_increment": 0.05},
        "digest_domain_utf8_nul": "FlyBench v2 complete neural state v1",
        "intervals": intervals,
    }
    write_json(output, report)
    return report
