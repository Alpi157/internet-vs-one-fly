"""Deterministic V2A annotation inventory and provisional circuit survey."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather

from flybench.encoding import ThreatObservation, compute_features, encode_population_drive
from flybench.game import build_live_session, load_live_profile
from flybench.graph import (
    ARRAY_FILENAMES,
    MANIFEST_SCHEMA,
    MANIFEST_VERSION,
    SEMANTIC_ARRAYS,
    _array_inventory,
    _selection_semantic_digest,
    audit_graph,
    semantic_graph_digest,
    utc_now,
    write_json,
)
from flybench.kernel import KernelGraph, KernelState, warm_kernel
from flybench.runner import CONTROL_INTERVAL_MS, NEURAL_STEPS_PER_CONTROL_INTERVAL


ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS = ROOT / "data/raw/body-annotations-male-cns-v1.0-minconf-0.5.feather"
FULL_GRAPH = ROOT / "data/compiled/full"
PORTS = ROOT / "profiles/escape-circuit.json"
SOURCE_LOCK = ROOT / "profiles/source-lock.json"
TRANSFORM = ROOT / "profiles/compile-transform-v1.json"
BUILDER_PROFILE = ROOT / "profiles/circuit-builder-v1.json"
CANDIDATE_PROFILE = ROOT / "profiles/walking-dn-candidates-v1.json"
SIDE_PROFILE = ROOT / "profiles/visual-ports-sides-v1.json"
LITERATURE_NAMES = ("MDN", "P9", "oDN1", "BPN", "DNa01", "DNa02", "DNp01")


def _json_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def annotation_inventory() -> dict[str, Any]:
    table = feather.read_table(ANNOTATIONS, memory_map=True)
    columns = []
    for field in table.schema:
        column = table[field.name]
        examples = []
        seen = set()
        for value in column.to_pylist():
            if value is None:
                continue
            clean = _json_value(value)
            marker = json.dumps(clean, sort_keys=True)
            if marker in seen:
                continue
            seen.add(marker)
            examples.append(clean)
            if len(examples) == 5:
                break
        columns.append(
            {
                "name": field.name,
                "dtype": str(field.type),
                "null_fraction": column.null_count / table.num_rows,
                "example_values": examples,
            }
        )
    return {
        "schema": "flybench.v2a.annotation-columns",
        "version": 1,
        "source": str(ANNOTATIONS.relative_to(ROOT)),
        "rows": table.num_rows,
        "columns": columns,
        "spatial_coordinates": {
            "present": True,
            "coordinate_shaped_columns": ["somaLocation", "tosomaLocation"],
            "soma_coordinate_column": "somaLocation",
            "explicit_arbor_position_column_present": False,
            "use_in_v2a": False,
            "statement": "The pinned annotation file contains somaLocation and tosomaLocation list columns. somaLocation explicitly holds soma coordinates. No column is explicitly named as an arbor-position field. V2A inventories these fields and does not use coordinates.",
        },
    }


def _tokens(value: str | None) -> list[str]:
    return [token for token in re.split(r"[^A-Za-z0-9]+", value or "") if token]


def _normalized_name(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def _match_kind(name: str, neuron_type: str | None, instance: str | None) -> str | None:
    if neuron_type == name:
        return "exact type"
    instance_tokens = _tokens(instance)
    if name in instance_tokens:
        return "exact instance token"
    candidate_tokens = _tokens(neuron_type) + instance_tokens
    normalized_name = _normalized_name(name)
    if any(
        token != name and _normalized_name(token) == normalized_name
        for token in candidate_tokens
    ):
        return "near match"
    return None


def _full_arrays() -> dict[str, np.ndarray]:
    return {
        name: np.load(FULL_GRAPH / filename, mmap_mode="r", allow_pickle=False)
        for name, filename in ARRAY_FILENAMES.items()
    }


def _seed_contact_counts(
    body_id: int,
    seed_ids: set[int],
    arrays: dict[str, np.ndarray],
    index_by_id: dict[int, int],
) -> tuple[int, int]:
    source_index = index_by_id.get(body_id)
    if source_index is None:
        return 0, 0
    seed_indices = np.asarray(
        sorted(index_by_id[value] for value in seed_ids if value in index_by_id and value != body_id),
        dtype=np.int32,
    )
    offsets = arrays["offsets"]
    targets = arrays["targets"]
    counts = arrays["counts"]
    start = int(offsets[source_index])
    stop = int(offsets[source_index + 1])
    outgoing = int(counts[start:stop][np.isin(targets[start:stop], seed_indices)].sum())
    incoming_mask = np.isin(targets, np.asarray([source_index], dtype=np.int32))
    incoming_edges = np.flatnonzero(incoming_mask)
    incoming_sources = np.searchsorted(offsets, incoming_edges, side="right") - 1
    incoming = int(counts[incoming_edges][np.isin(incoming_sources, seed_indices)].sum())
    return outgoing, incoming


def walking_candidates(arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    fields = ["bodyId", "type", "instance", "somaSide", "superclass", "class"]
    rows = feather.read_table(ANNOTATIONS, columns=fields, memory_map=True).to_pylist()
    matches: dict[str, list[dict[str, Any]]] = {name: [] for name in LITERATURE_NAMES}
    matched_ids: set[int] = set()
    for name in LITERATURE_NAMES:
        for row in rows:
            kind = _match_kind(name, row["type"], row["instance"])
            if kind is None:
                continue
            matched_ids.add(int(row["bodyId"]))
            matches[name].append(
                {
                    "body_id": str(row["bodyId"]),
                    "type": row["type"],
                    "instance": row["instance"],
                    "somaSide": row["somaSide"],
                    "superclass": row["superclass"],
                    "class": row["class"],
                    "match_kind": kind,
                }
            )
    ports = json.loads(PORTS.read_text(encoding="utf-8"))["populations"]
    visual_ids = {
        int(value)
        for population in ("LC4", "LPLC2")
        for value in ports[population]["body_ids_decimal"]
    }
    seed_ids = visual_ids | matched_ids
    index_by_id = {int(value): index for index, value in enumerate(arrays["ids"])}
    for name in LITERATURE_NAMES:
        for match in matches[name]:
            outgoing, incoming = _seed_contact_counts(
                int(match["body_id"]), seed_ids, arrays, index_by_id
            )
            match["synapse_contacts_to_other_seeds"] = outgoing
            match["synapse_contacts_from_other_seeds"] = incoming
        matches[name].sort(
            key=lambda value: (
                {"exact type": 0, "exact instance token": 1, "near match": 2}[
                    value["match_kind"]
                ],
                int(value["body_id"]),
            )
        )
    return {
        "schema_version": 1,
        "profile_id": "flybench.walking-dn-candidates.v1",
        "status": "CANDIDATE_REVIEW_REQUIRED",
        "source_lock_sha256": "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c",
        "annotation_source": str(ANNOTATIONS.relative_to(ROOT)),
        "match_rule": {
            "priority": ["exact type", "exact instance token", "near match"],
            "exact_instance_token": "case-sensitive alphanumeric token equality",
            "near_match": "case-insensitive equality after removing punctuation from one complete type or instance token",
            "substring_only_matches": "excluded",
        },
        "synapse_count_scope": "Raw source contacts to and from all accepted visual seeds and all reported candidate matches, excluding self edges.",
        "names": matches,
        "finalized_ports": False,
    }


def visual_port_sides() -> dict[str, Any]:
    table = feather.read_table(
        ANNOTATIONS, columns=["bodyId", "somaSide"], memory_map=True
    )
    side_by_id = {
        int(body_id): side
        for body_id, side in zip(
            table["bodyId"].to_pylist(), table["somaSide"].to_pylist(), strict=True
        )
    }
    ports = json.loads(PORTS.read_text(encoding="utf-8"))["populations"]
    populations: dict[str, Any] = {}
    for population in ("LC4", "LPLC2"):
        split: dict[str, list[str]] = {"L": [], "R": [], "missing_or_ambiguous": []}
        for value in ports[population]["body_ids_decimal"]:
            side = side_by_id.get(int(value))
            key = side if side in {"L", "R"} else "missing_or_ambiguous"
            split[key].append(value)
        populations[population] = {
            "left_body_ids_decimal": split["L"],
            "right_body_ids_decimal": split["R"],
            "missing_or_ambiguous": [
                {"body_id": value, "somaSide": side_by_id.get(int(value))}
                for value in split["missing_or_ambiguous"]
            ],
            "counts": {
                "left": len(split["L"]),
                "right": len(split["R"]),
                "missing_or_ambiguous": len(split["missing_or_ambiguous"]),
                "total": len(ports[population]["body_ids_decimal"]),
            },
        }
    return {
        "schema_version": 1,
        "profile_id": "flybench.visual-ports-sides.v1",
        "status": "ANNOTATION_DERIVED",
        "source_field": "somaSide",
        "source_lock_sha256": "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c",
        "populations": populations,
    }


def _provisional_seed_sets(candidate_profile: dict[str, Any]) -> tuple[set[int], set[int], set[int]]:
    ports = json.loads(PORTS.read_text(encoding="utf-8"))["populations"]
    visual = {
        int(value)
        for population in ("LC4", "LPLC2")
        for value in ports[population]["body_ids_decimal"]
    }
    outputs = {int(value) for value in ports["DNp01"]["body_ids_decimal"]}
    for name in ("MDN", "P9", "oDN1", "BPN", "DNa01", "DNa02"):
        outputs.update(
            int(match["body_id"])
            for match in candidate_profile["names"][name]
            if match["match_kind"] == "exact type"
        )
    return visual, outputs, visual | outputs


def select_indices(
    arrays: dict[str, np.ndarray],
    visual_body_ids: set[int],
    output_body_ids: set[int],
    threshold: int,
    hops: int,
) -> np.ndarray:
    ids = arrays["ids"]
    index_by_id = {int(value): index for index, value in enumerate(ids)}
    visual_frontier = {index_by_id[value] for value in visual_body_ids}
    output_frontier = {index_by_id[value] for value in output_body_ids}
    selected = set(visual_frontier | output_frontier)
    offsets = arrays["offsets"]
    targets = arrays["targets"]
    counts = arrays["counts"]
    for _ in range(hops):
        downstream: set[int] = set()
        for source_index in visual_frontier:
            start = int(offsets[source_index])
            stop = int(offsets[source_index + 1])
            keep = counts[start:stop] >= threshold
            downstream.update(int(value) for value in targets[start:stop][keep])
        target_mask = np.isin(
            targets, np.asarray(sorted(output_frontier), dtype=np.int32)
        )
        eligible_edges = np.flatnonzero(target_mask & (counts >= threshold))
        upstream = set(
            int(value)
            for value in np.searchsorted(offsets, eligible_edges, side="right") - 1
        )
        selected.update(downstream)
        selected.update(upstream)
        visual_frontier = downstream
        output_frontier = upstream
    return np.asarray(sorted(selected), dtype=np.int64)


def _write_array(path: Path, value: np.ndarray, dtype: str) -> None:
    array = np.ascontiguousarray(value, dtype=np.dtype(dtype).newbyteorder("<"))
    np.save(path, array, allow_pickle=False)


def build_bundle(
    arrays: dict[str, np.ndarray],
    selected_indices: np.ndarray,
    output_dir: Path,
    threshold: int,
    hops: int,
    *,
    profile_id: str | None = None,
    seed_status: str = "PROVISIONAL_SEEDS",
    selection_rule: str | None = None,
    build_command: list[str] | None = None,
    compiler_id: str = "flybench.v2-circuit-builder.v1",
) -> dict[str, Any]:
    started = time.monotonic()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    selected_mask = np.zeros(arrays["ids"].size, dtype=np.bool_)
    selected_mask[selected_indices] = True
    remap = np.full(arrays["ids"].size, -1, dtype=np.int32)
    remap[selected_indices] = np.arange(selected_indices.size, dtype=np.int32)
    target_chunks = []
    count_chunks = []
    weight_chunks = []
    offsets = np.zeros(selected_indices.size + 1, dtype=np.int64)
    cut_outgoing = 0
    edge_count = 0
    for dense_source, full_source in enumerate(selected_indices):
        start = int(arrays["offsets"][full_source])
        stop = int(arrays["offsets"][full_source + 1])
        full_targets = arrays["targets"][start:stop]
        keep = selected_mask[full_targets]
        target_chunks.append(remap[full_targets[keep]])
        count_chunks.append(np.asarray(arrays["counts"][start:stop][keep]))
        weight_chunks.append(np.asarray(arrays["weights"][start:stop][keep]))
        cut_outgoing += int(arrays["counts"][start:stop][~keep].sum())
        edge_count += int(np.count_nonzero(keep))
        offsets[dense_source + 1] = edge_count
    targets = np.concatenate(target_chunks).astype(np.int32, copy=False)
    counts = np.concatenate(count_chunks).astype(np.uint64, copy=False)
    weights = np.concatenate(weight_chunks).astype(np.float32, copy=False)
    incoming_total = int(arrays["counts"][selected_mask[arrays["targets"]]].sum())
    represented_contacts = int(counts.sum(dtype=np.uint64))
    cut_incoming = incoming_total - represented_contacts
    _write_array(output_dir / ARRAY_FILENAMES["ids"], arrays["ids"][selected_indices], "uint64")
    _write_array(output_dir / ARRAY_FILENAMES["offsets"], offsets, "int64")
    _write_array(output_dir / ARRAY_FILENAMES["targets"], targets, "int32")
    _write_array(output_dir / ARRAY_FILENAMES["counts"], counts, "uint64")
    _write_array(output_dir / ARRAY_FILENAMES["weights"], weights, "float32")
    for name in ARRAY_FILENAMES:
        if name in SEMANTIC_ARRAYS:
            continue
        _write_array(
            output_dir / ARRAY_FILENAMES[name],
            arrays[name][selected_indices],
            str(arrays[name].dtype),
        )
    selected_ids = [str(int(value)) for value in arrays["ids"][selected_indices]]
    selection_profile = {
        "schema_version": 1,
        "profile_id": profile_id or f"flybench.v2a-provisional.s{threshold}.h{hops}",
        "status": seed_status,
        "source_lock_sha256": "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c",
        "annotation_source_role": "curated_annotations",
        "selection": {
            "mode": "explicit_body_ids",
            "biological_id_field": "bodyId",
            "accepted_when": {"field": "superclass", "operator": "not_null"},
            "body_ids_decimal": selected_ids,
            "invalid_id_policy": "error",
            "duplicate_id_policy": "error",
            "missing_id_policy": "error",
            "rule": selection_rule
            or f"V2A provisional plan-v2 expansion with S={threshold} and hops={hops}",
        },
        "compile_transform": {
            "path": "compile-transform-v1.json",
            "profile_id": "flybench.fast-current-compile.v1",
        },
    }
    selection_bytes = (json.dumps(selection_profile, indent=2, sort_keys=True) + "\n").encode()
    (output_dir / "selection-profile.json").write_bytes(selection_bytes)
    shutil.copyfile(SOURCE_LOCK, output_dir / "source-lock.json")
    shutil.copyfile(TRANSFORM, output_dir / "compile-transform-profile.json")
    transform_bytes = TRANSFORM.read_bytes()
    transform = json.loads(transform_bytes)
    selection_semantic = _selection_semantic_digest(selection_profile)
    semantic_digest = semantic_graph_digest(
        output_dir, selection_semantic, hashlib.sha256(transform_bytes).hexdigest()
    )
    signs = arrays["effective_signs"][selected_indices]
    unknown_source_edges = int(
        sum(
            int(offsets[index + 1] - offsets[index])
            for index in np.flatnonzero(signs == 0)
        )
    )
    indegree = np.bincount(targets, minlength=selected_indices.size)
    outdegree = np.diff(offsets)
    isolated = int(np.count_nonzero((indegree == 0) & (outdegree == 0)))
    zero_mask = weights == 0
    graph = {
        "N": int(selected_indices.size),
        "source_accepted_E": int(targets.size),
        "executable_nonzero_E": int(np.count_nonzero(weights)),
        "zero_disabled_E": int(np.count_nonzero(zero_mask)),
        "represented_source_contacts": represented_contacts,
        "disabled_zero_weight_contact_mass": int(counts[zero_mask].sum(dtype=np.uint64)),
        "isolated_accepted_neurons": isolated,
    }
    source_lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    source_files = [
        {
            "role": entry["role"],
            "filename": entry["filename"],
            "bytes": entry["observed_bytes"],
            "observed_sha256": entry["observed_sha256"],
            "upstream_sha256": entry.get("upstream_sha256"),
        }
        for entry in source_lock["files"]
    ]
    inventory = _array_inventory(output_dir)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "version": MANIFEST_VERSION,
        "compiler": {
            "compiler_id": compiler_id,
            "module": "flybench.circuit",
            "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "code_git_sha": None,
        },
        "source_lock_sha256": hashlib.sha256(SOURCE_LOCK.read_bytes()).hexdigest(),
        "source_files": source_files,
        "selection_profile": {
            "profile_id": selection_profile["profile_id"],
            "sha256": hashlib.sha256(selection_bytes).hexdigest(),
            "semantic_sha256": selection_semantic,
            "copied_filename": "selection-profile.json",
            "rule": selection_profile["selection"]["rule"],
        },
        "compile_transform_profile": {
            "profile_id": transform["profile_id"],
            "sha256": hashlib.sha256(transform_bytes).hexdigest(),
            "copied_filename": "compile-transform-profile.json",
            "classification": "MODEL ASSUMPTION",
            "global_gain": 1.0,
            "normalization": "none",
        },
        "orientation": {
            "adjacency": "A[source,target]",
            "row_semantics": "presynaptic/source neuron",
            "propagation": "A.T @ spike_vector",
        },
        "semantic_digest": {
            "algorithm": "sha256",
            "version": 1,
            "value": semantic_digest,
            "canonical_byte_order": "little-endian",
            "array_order": list(SEMANTIC_ARRAYS),
        },
        "graph": graph,
        "selection_accounting": {
            "selection_mode": "explicit_body_ids",
            "requested_body_ids": int(selected_indices.size),
            "status": seed_status,
        },
        "transmitter_accounting": {
            "unknown_sign_nodes": int(np.count_nonzero(signs == 0)),
            "unknown_sign_edges": unknown_source_edges,
        },
        "endpoint_and_contact_accounting": {
            "cut_incoming_contact_mass": cut_incoming,
            "cut_outgoing_contact_mass": cut_outgoing,
        },
        "connection_table_semantics": {
            "source": "accepted M03 full graph induced subgraph",
            "aggregation_rule": "unchanged from accepted M03 full graph",
        },
        "arrays": inventory,
        "build_resource": {
            "classification": "V2A provisional circuit build; not runtime session memory",
            "command": build_command
            or ["python", "-m", "flybench.circuit", "survey"],
            "duration_seconds": time.monotonic() - started,
            "output_array_total_bytes": sum(entry["bytes"] for entry in inventory.values()),
        },
        "operational_metadata": {"completed_at_utc": utc_now()},
        "circuit_builder_audit": {
            "synapse_threshold": threshold,
            "hops": hops,
            "cut_incoming_contact_mass": cut_incoming,
            "cut_outgoing_contact_mass": cut_outgoing,
            "unknown_sign_nodes": int(np.count_nonzero(signs == 0)),
            "unknown_sign_edges": unknown_source_edges,
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    report = audit_graph(output_dir, output_dir / "audit.json")
    return {
        "bundle_path": str(output_dir.relative_to(ROOT)),
        "semantic_graph_digest": semantic_digest,
        "N": graph["N"],
        "E": graph["source_accepted_E"],
        "contacts": graph["represented_source_contacts"],
        "cut_incoming_contact_mass": cut_incoming,
        "cut_outgoing_contact_mass": cut_outgoing,
        "isolated_nodes": graph["isolated_accepted_neurons"],
        "unknown_sign_nodes": manifest["circuit_builder_audit"]["unknown_sign_nodes"],
        "unknown_sign_edges": unknown_source_edges,
        "unknown_sign_contact_mass": graph["disabled_zero_weight_contact_mass"],
        "audit_status": report["status"],
        "array_bytes": manifest["build_resource"]["output_array_total_bytes"],
    }


def _load_survey_graph(directory: Path) -> tuple[KernelGraph, dict[str, np.ndarray], str]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    arrays = {
        name: np.load(directory / filename, mmap_mode="r", allow_pickle=False)
        for name, filename in ARRAY_FILENAMES.items()
    }
    graph = KernelGraph(
        offsets=arrays["offsets"], targets=arrays["targets"], weights=arrays["weights"]
    )
    return graph, arrays, manifest["semantic_digest"]["value"]


def kernel_cost(
    directory: Path,
    visual_body_ids: set[int],
    output_body_ids: set[int],
    repeats: int,
    timeout_s: float,
) -> dict[str, Any]:
    resolved = load_live_profile(ROOT / "profiles/live.json")
    model = build_live_session(resolved).runner.model_spec
    graph, arrays, digest = _load_survey_graph(directory)
    ids = arrays["ids"]
    index_by_id = {int(value): index for index, value in enumerate(ids)}
    lc4_ids = set(
        int(value)
        for value in json.loads(PORTS.read_text(encoding="utf-8"))["populations"]["LC4"]["body_ids_decimal"]
    )
    lplc2_ids = visual_body_ids - lc4_ids
    lc4 = np.asarray(sorted(index_by_id[value] for value in lc4_ids), dtype=np.int64)
    lplc2 = np.asarray(sorted(index_by_id[value] for value in lplc2_ids), dtype=np.int64)
    outputs = np.asarray(sorted(index_by_id[value] for value in output_body_ids), dtype=np.int64)
    workloads: dict[str, list[float]] = {"quiet": [], "accepted-looming": []}
    state_bytes = 0
    deadline = time.monotonic() + timeout_s
    for workload in workloads:
        for repeat_index in range(repeats):
            state = KernelState(model, graph)
            state_bytes = state.private_state_bytes()["total"]
            started = time.perf_counter()
            for control_tick in range(int(1000 / CONTROL_INTERVAL_MS)):
                if time.monotonic() >= deadline:
                    return {
                        "classification": "DEVELOPMENT-MACHINE NUMBERS",
                        "status": "TIMEOUT",
                        "semantic_graph_digest": digest,
                        "timeout_s": timeout_s,
                        "completed_workloads": workloads,
                        "interrupted_workload": workload,
                        "interrupted_repeat_index": repeat_index,
                        "interrupted_control_tick": control_tick,
                    }
                if workload == "accepted-looming" and 20 <= control_tick < 60:
                    fraction = (control_tick - 20) / 40
                    distance = 12.0 + (1.0 - 12.0) * fraction
                    observation = ThreatObservation(True, distance, -0.0275)
                else:
                    observation = ThreatObservation(False)
                features = compute_features(observation)
                encoded = encode_population_drive(
                    features,
                    4.0,
                    neuron_count=ids.size,
                    lc4_indices=lc4,
                    lplc2_indices=lplc2,
                    dnp01_indices=outputs,
                )
                for _ in range(NEURAL_STEPS_PER_CONTROL_INTERVAL):
                    state.step(encoded.vector)
            workloads[workload].append(time.perf_counter() - started)
    graph_bytes = sum(int(value.nbytes) for value in arrays.values())
    return {
        "classification": "DEVELOPMENT-MACHINE NUMBERS",
        "status": "COMPLETE",
        "semantic_graph_digest": digest,
        "simulated_seconds_per_repeat": 1,
        "repeats": repeats,
        "wall_seconds_per_simulated_second": workloads,
        "memory_bytes": {
            "compiled_graph_arrays": graph_bytes,
            "mutable_kernel_arrays": state_bytes,
            "total_arrays": graph_bytes + state_bytes,
        },
    }


def _candidate_markdown(profile: dict[str, Any]) -> str:
    lines = [
        "# Walking descending neuron candidates",
        "",
        "Status: CANDIDATE_REVIEW_REQUIRED. No walking port is finalized by this table.",
        "",
        "| Literature name | Body ID | Type | Instance | Side | Superclass | Class | Match kind | Contacts to other seeds | Contacts from other seeds |",
        "|---|---:|---|---|---|---|---|---|---:|---:|",
    ]
    for name in LITERATURE_NAMES:
        matches = profile["names"][name]
        if not matches:
            lines.append(f"| {name} | No match |  |  |  |  |  |  |  |  |")
        for match in matches:
            lines.append(
                f"| {name} | {match['body_id']} | {match['type'] or ''} | {match['instance'] or ''} | {match['somaSide'] or ''} | {match['superclass'] or ''} | {match['class'] or ''} | {match['match_kind']} | {match['synapse_contacts_to_other_seeds']} | {match['synapse_contacts_from_other_seeds']} |"
            )
    lines.append("")
    return "\n".join(lines)


def _findings_markdown(survey: dict[str, Any], side_profile: dict[str, Any]) -> str:
    lines = [
        "# V2A Phase 1 findings",
        "",
        "All surveyed circuits use PROVISIONAL_SEEDS. No behavior was run on them.",
        "",
        "## Visual port side split",
        "",
        "| Population | Left | Right | Missing or ambiguous | Total |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, value in side_profile["populations"].items():
        counts = value["counts"]
        lines.append(
            f"| {name} | {counts['left']} | {counts['right']} | {counts['missing_or_ambiguous']} | {counts['total']} |"
        )
    lines.extend(
        [
            "",
            "## Circuit size survey",
            "",
            "| S | Hops | N | E | Contacts | Cut incoming | Cut outgoing | Isolated | Unknown signs | Quiet wall s/s, median | Looming wall s/s, median | Array MiB |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for value in survey["circuits"]:
        cost = value["kernel_cost"]
        if cost["status"] == "COMPLETE":
            quiet = f"{float(np.median(cost['wall_seconds_per_simulated_second']['quiet'])):.6f}"
            looming = f"{float(np.median(cost['wall_seconds_per_simulated_second']['accepted-looming'])):.6f}"
            memory = f"{cost['memory_bytes']['total_arrays'] / 1048576:.3f}"
        else:
            quiet = looming = memory = "TIMEOUT"
        lines.append(
            f"| {value['synapse_threshold']} | {value['hops']} | {value['N']} | {value['E']} | {value['contacts']} | {value['cut_incoming_contact_mass']} | {value['cut_outgoing_contact_mass']} | {value['isolated_nodes']} | {value['unknown_sign_nodes']} | {quiet} | {looming} | {memory} |"
        )
    lines.extend(
        [
            "",
            "Kernel timings are development-machine measurements, not deployment capacity claims.",
            "",
        ]
    )
    return "\n".join(lines)


def run_survey(out: Path) -> dict[str, Any]:
    profile = json.loads(BUILDER_PROFILE.read_text(encoding="utf-8"))
    arrays = _full_arrays()
    inventory = annotation_inventory()
    candidates = walking_candidates(arrays)
    sides = visual_port_sides()
    write_json(out / "annotation-columns.json", inventory)
    write_json(CANDIDATE_PROFILE, candidates)
    write_json(SIDE_PROFILE, sides)
    out.mkdir(parents=True, exist_ok=True)
    (out / "walking-dn-candidates.md").write_text(
        _candidate_markdown(candidates), encoding="utf-8"
    )
    visual, outputs, seeds = _provisional_seed_sets(candidates)
    warm_kernel()
    circuits = []
    output_root = ROOT / profile["bundle_output_root"]
    for threshold in profile["synapse_thresholds"]:
        for hops in profile["hop_counts"]:
            selected = select_indices(arrays, visual, outputs, int(threshold), int(hops))
            bundle_dir = output_root / f"s{threshold}-h{hops}"
            value = build_bundle(
                arrays, selected, bundle_dir, int(threshold), int(hops)
            )
            value.update(
                {
                    "synapse_threshold": int(threshold),
                    "hops": int(hops),
                    "seed_count": len(seeds),
                    "seed_status": "PROVISIONAL_SEEDS",
                    "kernel_cost": kernel_cost(
                        bundle_dir,
                        visual,
                        outputs,
                        int(profile["kernel_cost"]["repeats"]),
                        float(profile["kernel_cost"]["timeout_s_per_circuit"]),
                    ),
                }
            )
            circuits.append(value)
    survey = {
        "schema": "flybench.v2a.circuit-size-survey",
        "version": 1,
        "status": "SUBMITTED",
        "profile": str(BUILDER_PROFILE.relative_to(ROOT)),
        "seed_status": "PROVISIONAL_SEEDS",
        "provisional_seed_body_ids": [str(value) for value in sorted(seeds)],
        "behavior_runs_on_survey_circuits": 0,
        "circuits": circuits,
    }
    write_json(out / "circuit-size-survey.json", survey)
    (out / "FINDINGS.md").write_text(
        _findings_markdown(survey, sides), encoding="utf-8"
    )
    return survey


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m flybench.circuit")
    commands = parser.add_subparsers(dest="command", required=True)
    survey = commands.add_parser("survey")
    survey.add_argument("--out", type=Path, required=True)
    build_v2_parser = commands.add_parser("build-v2")
    build_v2_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "survey":
        result = run_survey(args.out.resolve())
        print(
            json.dumps(
                {"status": "PASS", "circuits": len(result["circuits"]), "out": str(args.out.resolve())},
                sort_keys=True,
            )
        )
        return 0
    if args.command == "build-v2":
        from flybench.v2_data import build_v2

        result = build_v2(args.out.resolve())
        print(
            json.dumps(
                {"status": "PASS", "circuits": len(result["circuits"]), "out": str(args.out.resolve())},
                sort_keys=True,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
