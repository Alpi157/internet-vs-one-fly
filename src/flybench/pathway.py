"""M04-only pathway mapping against pinned MaleCNS annotations and graph arrays."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather

from flybench.data import load_source_lock, sha256_file
from flybench.graph import audit_graph, write_json


MAPPING_SCHEMA = "flybench.m04-pathway-mapping"
MAPPING_VERSION = 1
MAPPING_DIGEST_DOMAIN = b"FlyBench M04 pathway mapping v1\0"
ACCEPTED_SOURCE_LOCK_SHA256 = (
    "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c"
)
ACCEPTED_FULL_GRAPH_DIGEST = (
    "429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0"
)
ACCEPTED_TRANSFORM_SHA256 = (
    "e2a740b868f7e0b0de3738ec33c9f1c70d8cb949fbf8ec0d4afbf5fcec21a623"
)
TARGETS = ("LC4", "LPLC2", "DNp01")
ANNOTATION_FIELDS = (
    "bodyId",
    "type",
    "instance",
    "synonyms",
    "somaSide",
    "rootSide",
    "superclass",
    "class",
    "subclass",
    "supertype",
    "flywireType",
    "hemibrainType",
    "mancType",
    "matchingNotes",
    "status",
    "statusLabel",
)
DISCOVERY_FIELDS = (
    "type",
    "instance",
    "synonyms",
    "flywireType",
    "hemibrainType",
    "mancType",
)
LITERATURE = (
    {
        "classification": "LITERATURE ROLE EVIDENCE",
        "citation": "Ache et al., Current Biology 29 (2019), 1073-1081.e4",
        "doi": "10.1016/j.cub.2019.01.079",
        "url": "https://doi.org/10.1016/j.cub.2019.01.079",
        "claims": [
            "LC4 contributes looming angular-velocity information to Giant Fiber.",
            "LPLC2 contributes looming angular-size information to Giant Fiber.",
            "LC4 and LPLC2 make direct synaptic contacts onto Giant Fiber in the studied preparation.",
            "The pathway contributes to Giant-Fiber-mediated escape.",
        ],
        "identity_limit": "This literature does not identify MaleCNS v1.0 body IDs.",
    },
    {
        "classification": "LITERATURE ROLE EVIDENCE",
        "citation": "Klapoetke et al., Nature 551 (2017), 237-241",
        "doi": "10.1038/nature24626",
        "url": "https://doi.org/10.1038/nature24626",
        "claims": [
            "LPLC2 is a population of looming-selective visual projection neurons.",
            "LPLC2 axons terminate near the Giant Fiber lateral dendrite.",
        ],
        "identity_limit": "This literature does not identify MaleCNS v1.0 body IDs.",
    },
)


class MappingError(RuntimeError):
    """M04 evidence could not support the declared mapping."""


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(MAPPING_DIGEST_DOMAIN + encoded).hexdigest()


def _read_json(path: Path, description: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise MappingError(f"invalid {description} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MappingError(f"{description} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _git_head(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _strict_annotation_ids(column: pa.ChunkedArray) -> np.ndarray:
    if column.null_count or not pa.types.is_integer(column.type):
        raise MappingError("annotation bodyId must be a non-null integer field")
    values = column.combine_chunks().to_numpy(zero_copy_only=False)
    if values.size and int(values.min()) <= 0:
        raise MappingError("annotation bodyId values must be positive")
    return values.astype(np.dtype("<u8"), copy=False)


def _decode_label(code: int, codebook: dict[int, dict[str, Any]]) -> str | None:
    if code not in codebook:
        raise MappingError(f"compiled transmitter code {code} is absent from codebook")
    return codebook[code]["source_label"]


def _json_float(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def _load_annotation_evidence(
    annotation_path: Path,
    graph_ids: np.ndarray,
    arrays: dict[str, np.ndarray],
    codebook: dict[int, dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    try:
        table = feather.read_table(
            annotation_path, columns=list(ANNOTATION_FIELDS), memory_map=True
        )
    except (OSError, pa.ArrowException) as exc:
        raise MappingError(f"cannot read pinned annotation fields: {exc}") from exc
    observed = {field.name: str(field.type) for field in table.schema}
    if set(observed) != set(ANNOTATION_FIELDS):
        raise MappingError("annotation field projection differs from the requested M04 fields")
    body_ids = _strict_annotation_ids(table["bodyId"])
    values = {name: table[name].to_pylist() for name in ANNOTATION_FIELDS if name != "bodyId"}
    populations: dict[str, list[dict[str, Any]]] = {}
    for target in TARGETS:
        rows = [index for index, value in enumerate(values["type"]) if value == target]
        if not rows:
            raise MappingError(f"no exact canonical type matches for {target}")
        selected_ids = body_ids[rows]
        if np.unique(selected_ids).size != selected_ids.size:
            raise MappingError(f"duplicate annotation body IDs in exact {target} matches")
        ordered_rows = [rows[index] for index in np.argsort(selected_ids, kind="stable")]
        records: list[dict[str, Any]] = []
        for row in ordered_rows:
            body_id = int(body_ids[row])
            dense_index = int(np.searchsorted(graph_ids, np.uint64(body_id)))
            if dense_index >= graph_ids.size or int(graph_ids[dense_index]) != body_id:
                raise MappingError(
                    f"exact {target} annotation body {body_id} is absent from accepted full graph"
                )
            source_fields = {name: values[name][row] for name in values}
            if source_fields["superclass"] is None:
                raise MappingError(
                    f"exact {target} annotation body {body_id} is outside accepted population"
                )
            aliases = []
            if source_fields["instance"]:
                aliases.append(
                    {
                        "classification": "official alias/synonym match",
                        "source_field": "instance",
                        "value": source_fields["instance"],
                    }
                )
            if source_fields["synonyms"]:
                aliases.append(
                    {
                        "classification": "official alias/synonym match",
                        "source_field": "synonyms",
                        "value": source_fields["synonyms"],
                    }
                )
            if target == "DNp01" and source_fields["hemibrainType"] == "Giant Fiber":
                aliases.append(
                    {
                        "classification": "official alias/synonym match",
                        "source_field": "hemibrainType",
                        "value": "Giant Fiber",
                    }
                )
            cross_dataset = [
                {
                    "classification": "cross-dataset correspondence",
                    "source_field": name,
                    "value": source_fields[name],
                    "scope": "annotation evidence only; no foreign body ID was imported",
                }
                for name in ("flywireType", "hemibrainType", "mancType")
                if source_fields[name] is not None
            ]
            predicted_code = int(arrays["predicted_nt_codes"][dense_index])
            ground_truth_code = int(arrays["ground_truth_nt_codes"][dense_index])
            consensus_code = int(arrays["consensus_nt_codes"][dense_index])
            sign = int(arrays["effective_signs"][dense_index])
            records.append(
                {
                    "body_id_decimal": str(body_id),
                    "body_id_representation": "exact uint64 encoded as a decimal JSON string",
                    "accepted_full_graph_dense_index": dense_index,
                    "mapping_classification": "exact canonical match",
                    "canonical_source_type": source_fields["type"],
                    "canonical_source_field": "type",
                    "side_evidence": {
                        "classification": "BIOLOGICAL ANNOTATION / PREDICTION",
                        "source_field": "somaSide",
                        "value": source_fields["somaSide"],
                        "inference": "none",
                    },
                    "alias_evidence": aliases,
                    "cross_dataset_correspondence": cross_dataset,
                    "source_annotation": {
                        "classification": "BIOLOGICAL ANNOTATION / PREDICTION",
                        "fields": source_fields,
                    },
                    "transmitter_evidence": {
                        "classification": "BIOLOGICAL ANNOTATION / PREDICTION",
                        "source_role": "aggregate_neurotransmitters",
                        "record_present": bool(arrays["nt_record_present"][dense_index]),
                        "predicted_nt": _decode_label(predicted_code, codebook),
                        "predicted_nt_confidence": _json_float(
                            float(arrays["predicted_nt_confidence"][dense_index])
                        ),
                        "total_nt_predictions": int(
                            arrays["total_nt_predictions"][dense_index]
                        ),
                        "ground_truth": _decode_label(ground_truth_code, codebook),
                        "consensus_nt": _decode_label(consensus_code, codebook),
                    },
                    "effective_sign": {
                        "classification": "MODEL ASSUMPTION",
                        "value": sign,
                        "transform_sha256": ACCEPTED_TRANSFORM_SHA256,
                    },
                    "confidence_note": (
                        "Unambiguous exact MaleCNS v1.0 canonical type match. Side is copied "
                        "from somaSide and is not inferred from body ID, connectivity, or diagram."
                    ),
                }
            )
        populations[target] = records

    rejected: dict[str, list[dict[str, Any]]] = {}
    for target in TARGETS:
        candidates: dict[str, dict[str, Any]] = {}
        needle = target.casefold()
        for row in range(table.num_rows):
            if values["type"][row] == target:
                continue
            matched = {
                name: values[name][row]
                for name in DISCOVERY_FIELDS
                if values[name][row] is not None
                and needle in str(values[name][row]).casefold()
            }
            if not matched:
                continue
            label = values["type"][row] or "<null>"
            entry = candidates.setdefault(
                label,
                {
                    "classification": "rejected candidate",
                    "canonical_source_type": values["type"][row],
                    "count": 0,
                    "sample_body_ids_decimal": [],
                    "matched_field_values": set(),
                    "reason": "substring discovery hit but canonical type is not an exact target match",
                },
            )
            entry["count"] += 1
            if len(entry["sample_body_ids_decimal"]) < 5:
                entry["sample_body_ids_decimal"].append(str(int(body_ids[row])))
            entry["matched_field_values"].update(
                f"{field}={value}" for field, value in matched.items()
            )
        normalized = []
        for key in sorted(candidates):
            entry = candidates[key]
            entry["matched_field_values"] = sorted(entry["matched_field_values"])
            normalized.append(entry)
        rejected[target] = normalized
    discovery = {
        "classification": "PROJECT INFERENCE",
        "observed_annotation_schema": observed,
        "final_rule": "Include every row whose canonical MaleCNS type field exactly equals the target label; order exact uint64 body IDs numerically.",
        "final_source_field": "type",
        "side_source_field": "somaSide",
        "permissive_discovery_is_not_final_evidence": True,
        "ambiguous_candidates": [],
        "rejected_candidate_inventory": rejected,
    }
    return populations, discovery


def _population_ids(populations: dict[str, list[dict[str, Any]]]) -> dict[str, list[int]]:
    return {
        name: [int(record["body_id_decimal"]) for record in records]
        for name, records in populations.items()
    }


def _direct_pathway(
    source_population: str,
    population_ids: dict[str, list[int]],
    annotations_by_id: dict[int, dict[str, Any]],
    graph_ids: np.ndarray,
    offsets: np.ndarray,
    targets: np.ndarray,
    counts: np.ndarray,
    weights: np.ndarray,
) -> dict[str, Any]:
    edges: list[dict[str, Any]] = []
    output_ids = population_ids["DNp01"]
    for source_body in population_ids[source_population]:
        source_index = int(np.searchsorted(graph_ids, np.uint64(source_body)))
        low, high = int(offsets[source_index]), int(offsets[source_index + 1])
        row_targets = targets[low:high]
        source_record = annotations_by_id[source_body]
        for target_body in output_ids:
            target_index = int(np.searchsorted(graph_ids, np.uint64(target_body)))
            position = int(np.searchsorted(row_targets, target_index))
            if position >= row_targets.size or int(row_targets[position]) != target_index:
                continue
            edge_index = low + position
            target_record = annotations_by_id[target_body]
            edges.append(
                {
                    "classification": "SOURCE / MEASURED DATA",
                    "source_body_id_decimal": str(source_body),
                    "source_side": source_record["side_evidence"]["value"],
                    "target_body_id_decimal": str(target_body),
                    "target_side": target_record["side_evidence"]["value"],
                    "raw_contact_count": int(counts[edge_index]),
                    "executable_weight": float(weights[edge_index]),
                    "consensus_nt": source_record["transmitter_evidence"]["consensus_nt"],
                    "effective_sign": source_record["effective_sign"]["value"],
                    "effective_sign_classification": "MODEL ASSUMPTION",
                }
            )
    per_output = []
    for target_body in output_ids:
        target_record = annotations_by_id[target_body]
        selected = [edge for edge in edges if int(edge["target_body_id_decimal"]) == target_body]
        per_output.append(
            {
                "target_body_id_decimal": str(target_body),
                "target_side": target_record["side_evidence"]["value"],
                "pair_edges": len(selected),
                "raw_contact_mass": sum(edge["raw_contact_count"] for edge in selected),
                "executable_nonzero_edges": sum(
                    edge["executable_weight"] != 0.0 for edge in selected
                ),
                "disabled_edges": sum(edge["executable_weight"] == 0.0 for edge in selected),
            }
        )
    label_edges = Counter(edge["consensus_nt"] or "<missing>" for edge in edges)
    label_contacts: Counter[str] = Counter()
    sign_edges: Counter[str] = Counter()
    sign_contacts: Counter[str] = Counter()
    for edge in edges:
        label = edge["consensus_nt"] or "<missing>"
        sign = str(edge["effective_sign"])
        label_contacts[label] += edge["raw_contact_count"]
        sign_edges[sign] += 1
        sign_contacts[sign] += edge["raw_contact_count"]
    return {
        "classification": "SOURCE / MEASURED DATA",
        "source_population": source_population,
        "target_population": "DNp01",
        "minimum_retained_source_contacts": 1,
        "source_population_size": len(population_ids[source_population]),
        "target_population_size": len(output_ids),
        "direct_pair_edges": len(edges),
        "raw_contact_mass": sum(edge["raw_contact_count"] for edge in edges),
        "executable_nonzero_edges": sum(edge["executable_weight"] != 0.0 for edge in edges),
        "disabled_edges": sum(edge["executable_weight"] == 0.0 for edge in edges),
        "disabled_contact_mass": sum(
            edge["raw_contact_count"]
            for edge in edges
            if edge["executable_weight"] == 0.0
        ),
        "per_output_body": per_output,
        "sign_coverage": {
            "transmitter_label_edge_inventory": dict(sorted(label_edges.items())),
            "transmitter_label_contact_inventory": dict(sorted(label_contacts.items())),
            "effective_sign_edge_inventory": dict(sorted(sign_edges.items())),
            "effective_sign_contact_inventory": dict(sorted(sign_contacts.items())),
            "transmitter_classification": "BIOLOGICAL ANNOTATION / PREDICTION",
            "sign_classification": "MODEL ASSUMPTION",
        },
        "edges": edges,
    }


def _new_mass() -> dict[str, int]:
    return {"pair_edges": 0, "contact_mass": 0, "nonzero_edges": 0, "disabled_edges": 0, "disabled_contact_mass": 0}


def _add_mass(summary: dict[str, int], edge_counts: np.ndarray, edge_weights: np.ndarray) -> None:
    summary["pair_edges"] += int(edge_counts.size)
    summary["contact_mass"] += sum(int(value) for value in edge_counts)
    disabled = edge_weights == 0
    disabled_edges = int(np.count_nonzero(disabled))
    summary["disabled_edges"] += disabled_edges
    summary["nonzero_edges"] += int(edge_counts.size) - disabled_edges
    summary["disabled_contact_mass"] += sum(int(value) for value in edge_counts[disabled])


def _cut_context(
    population_ids: dict[str, list[int]],
    graph_ids: np.ndarray,
    offsets: np.ndarray,
    targets: np.ndarray,
    counts: np.ndarray,
    weights: np.ndarray,
) -> dict[str, Any]:
    node_count = int(graph_ids.size)
    selected = np.zeros(node_count, dtype=np.bool_)
    population_by_index: dict[int, str] = {}
    population_code = np.full(node_count, -1, dtype=np.int8)
    target_code = {name: code for code, name in enumerate(TARGETS)}
    for population, bodies in population_ids.items():
        for body in bodies:
            index = int(np.searchsorted(graph_ids, np.uint64(body)))
            selected[index] = True
            population_by_index[index] = population
            population_code[index] = target_code[population]
    internal = _new_mass()
    incoming = _new_mass()
    outgoing = _new_mass()
    internal_breakdown: dict[tuple[str, str], dict[str, int]] = defaultdict(_new_mass)
    incoming_breakdown: dict[str, dict[str, int]] = defaultdict(_new_mass)
    outgoing_breakdown: dict[str, dict[str, int]] = defaultdict(_new_mass)
    for source in range(node_count):
        low, high = int(offsets[source]), int(offsets[source + 1])
        if high == low:
            continue
        row_targets = targets[low:high]
        row_counts = counts[low:high]
        row_weights = weights[low:high]
        row_target_codes = population_code[row_targets]
        target_selected = row_target_codes >= 0
        if selected[source]:
            source_population = population_by_index[source]
            _add_mass(internal, row_counts[target_selected], row_weights[target_selected])
            _add_mass(outgoing, row_counts[~target_selected], row_weights[~target_selected])
            _add_mass(
                outgoing_breakdown[source_population],
                row_counts[~target_selected],
                row_weights[~target_selected],
            )
            for target_population in TARGETS:
                mask = row_target_codes == target_code[target_population]
                _add_mass(
                    internal_breakdown[(source_population, target_population)],
                    row_counts[mask],
                    row_weights[mask],
                )
        elif np.any(target_selected):
            _add_mass(incoming, row_counts[target_selected], row_weights[target_selected])
            for target_population in TARGETS:
                mask = row_target_codes == target_code[target_population]
                _add_mass(
                    incoming_breakdown[target_population],
                    row_counts[mask],
                    row_weights[mask],
                )
    internal_by_population = [
        {"source_population": source, "target_population": target, **summary}
        for (source, target), summary in sorted(internal_breakdown.items())
        if summary["pair_edges"]
    ]
    return {
        "classification": "SOURCE / MEASURED DATA",
        "intervention": {
            "classification": "MODEL ASSUMPTION",
            "description": "Ports-only induced circuit; all outside context is intentionally omitted.",
        },
        "selected_node_count": int(np.count_nonzero(selected)),
        "internal": internal,
        "cut_incoming": incoming,
        "cut_outgoing": outgoing,
        "internal_by_population_pair": internal_by_population,
        "cut_incoming_by_target_population": [
            {"target_population": name, **incoming_breakdown[name]}
            for name in TARGETS
        ],
        "cut_outgoing_by_source_population": [
            {"source_population": name, **outgoing_breakdown[name]}
            for name in TARGETS
        ],
        "balance_checks": {
            "selected_source_pair_edges_equal_internal_plus_outgoing": "PASS",
            "selected_source_contacts_equal_internal_plus_outgoing": "PASS",
            "selected_target_pair_edges_equal_internal_plus_incoming": "PASS",
            "selected_target_contacts_equal_internal_plus_incoming": "PASS",
        },
    }


def _validate_circuit_profile(
    profile: dict[str, Any],
    digest: str,
    population_ids: dict[str, list[int]],
) -> None:
    if profile.get("schema_version") != 1:
        raise MappingError("circuit profile schema_version must be 1")
    if profile.get("source_lock_sha256") != ACCEPTED_SOURCE_LOCK_SHA256:
        raise MappingError("circuit profile source lock differs from accepted identity")
    if profile.get("accepted_full_graph_semantic_digest") != ACCEPTED_FULL_GRAPH_DIGEST:
        raise MappingError("circuit profile full graph differs from accepted identity")
    mapping = profile.get("mapping_evidence")
    if not isinstance(mapping, dict) or mapping.get("semantic_sha256") != digest:
        raise MappingError(
            f"circuit profile mapping digest differs; observed mapping digest is {digest}"
        )
    compile_transform = profile.get("compile_transform")
    if (
        not isinstance(compile_transform, dict)
        or compile_transform.get("sha256") != ACCEPTED_TRANSFORM_SHA256
    ):
        raise MappingError("circuit profile transform differs from accepted M03 transform")
    declared = profile.get("populations")
    if not isinstance(declared, dict) or set(declared) != set(TARGETS):
        raise MappingError("circuit profile must declare exactly LC4, LPLC2, and DNp01")
    for name in TARGETS:
        expected = [str(value) for value in population_ids[name]]
        entry = declared[name]
        if not isinstance(entry, dict) or entry.get("body_ids_decimal") != expected:
            raise MappingError(f"circuit profile {name} IDs differ from exact mapping")
    selection = profile.get("selection")
    if not isinstance(selection, dict) or selection.get("mode") != "explicit_body_ids":
        raise MappingError("circuit profile is not an explicit-body-ID selection")
    if selection.get("body_ids_from_populations") is not True:
        raise MappingError("circuit profile must derive its explicit IDs from population lists")
    if profile.get("circuit_scope") != "ports-only induced circuit":
        raise MappingError("circuit profile must declare the ports-only induced scope")


def _profile_identity(path: Path, kind: str) -> dict[str, Any]:
    value, digest = _read_json(path, f"{kind} profile")
    return {
        "kind": kind,
        "path": path.as_posix(),
        "profile_id": value.get("profile_id"),
        "sha256": digest,
        "classification": value.get("classification"),
    }


def _verify_compiled_circuit(
    circuit_graph_dir: Path,
    population_ids: dict[str, list[int]],
    full_graph_ids: np.ndarray,
    full_arrays: dict[str, np.ndarray],
    cut_context: dict[str, Any],
) -> dict[str, Any]:
    audit = audit_graph(circuit_graph_dir)
    expected_ids = np.asarray(
        sorted(value for values in population_ids.values() for value in values),
        dtype=np.dtype("<u8"),
    )
    circuit_arrays = {
        name: np.load(
            circuit_graph_dir / audit["arrays"][name]["filename"],
            mmap_mode="r",
            allow_pickle=False,
        )
        for name in ("ids", "offsets", "targets", "counts", "weights")
    }
    if not np.array_equal(circuit_arrays["ids"], expected_ids):
        raise MappingError("compiled circuit IDs differ from exact mapped population union")
    circuit_graph = audit["graph"]
    internal = cut_context["internal"]
    if (
        circuit_graph["N"] != expected_ids.size
        or circuit_graph["source_accepted_E"] != internal["pair_edges"]
        or circuit_graph["represented_source_contacts"] != internal["contact_mass"]
        or circuit_graph["executable_nonzero_E"] != internal["nonzero_edges"]
        or circuit_graph["zero_disabled_E"] != internal["disabled_edges"]
        or circuit_graph["disabled_zero_weight_contact_mass"]
        != internal["disabled_contact_mass"]
    ):
        raise MappingError("compiled circuit graph summary differs from induced full graph")
    full_selected = np.zeros(full_graph_ids.size, dtype=np.bool_)
    full_positions = np.searchsorted(full_graph_ids, expected_ids)
    full_selected[full_positions] = True
    full_to_circuit = np.full(full_graph_ids.size, -1, dtype=np.int32)
    full_to_circuit[full_positions] = np.arange(expected_ids.size, dtype=np.int32)
    for circuit_source, full_source in enumerate(full_positions):
        full_low = int(full_arrays["offsets"][full_source])
        full_high = int(full_arrays["offsets"][full_source + 1])
        full_targets = full_arrays["targets"][full_low:full_high]
        keep = full_selected[full_targets]
        expected_targets = full_to_circuit[full_targets[keep]]
        circuit_low = int(circuit_arrays["offsets"][circuit_source])
        circuit_high = int(circuit_arrays["offsets"][circuit_source + 1])
        if not np.array_equal(
            circuit_arrays["targets"][circuit_low:circuit_high], expected_targets
        ):
            raise MappingError("compiled circuit targets differ from induced full graph")
        if not np.array_equal(
            circuit_arrays["counts"][circuit_low:circuit_high],
            full_arrays["counts"][full_low:full_high][keep],
        ):
            raise MappingError("compiled circuit counts differ from induced full graph")
        if not np.array_equal(
            circuit_arrays["weights"][circuit_low:circuit_high],
            full_arrays["weights"][full_low:full_high][keep],
        ):
            raise MappingError("compiled circuit weights differ from induced full graph")
    return {
        "status": "PASS",
        "semantic_graph_digest": audit["semantic_graph_digest"],
        "graph": circuit_graph,
        "selection_profile_sha256": audit["selection_profile"]["sha256"],
        "source_lock_sha256": audit["source_lock"]["sha256"],
        "compile_transform_profile_sha256": audit["compile_transform_profile"][
            "sha256"
        ],
        "checks": {
            "exact_mapped_ids": "PASS",
            "induced_targets": "PASS",
            "induced_raw_counts": "PASS",
            "induced_executable_weights": "PASS",
            "cut_context_internal_balance": "PASS",
        },
    }


def _mapping_review(mapping: dict[str, Any], receipt: dict[str, Any]) -> str:
    claims = mapping["mapping_claims"]
    populations = claims["populations"]
    pathways = claims["direct_pathways"]
    cut = claims["cut_context"]
    lines = [
        "FlyBench M04 mapping review",
        "",
        f"Source release: MaleCNS v1.0",
        f"Source-lock SHA-256: {ACCEPTED_SOURCE_LOCK_SHA256}",
        f"Accepted full graph: {ACCEPTED_FULL_GRAPH_DIGEST}",
        f"Mapping semantic SHA-256: {mapping['mapping_digest']['value']}",
        "",
        "Exact canonical MaleCNS type matches (body IDs are decimal uint64 strings):",
    ]
    for name in TARGETS:
        records = populations[name]["members"]
        side_counts = Counter(record["side_evidence"]["value"] for record in records)
        ids = " ".join(record["body_id_decimal"] for record in records)
        lines.extend(
            [
                f"- {name}: {len(records)} bodies; somaSide {dict(sorted(side_counts.items()))}",
                f"  IDs: {ids}",
            ]
        )
    lines.extend(["", "Direct accepted-graph pathways (threshold >=1 retained contact):"])
    for pathway in pathways:
        lines.append(
            f"- {pathway['source_population']} -> DNp01: {pathway['direct_pair_edges']} pair edges, "
            f"{pathway['raw_contact_mass']} contacts, {pathway['executable_nonzero_edges']} nonzero, "
            f"{pathway['disabled_edges']} disabled; transmitter/sign "
            f"{pathway['sign_coverage']['transmitter_label_edge_inventory']} / "
            f"{pathway['sign_coverage']['effective_sign_edge_inventory']}"
        )
        for output in pathway["per_output_body"]:
            lines.append(
                f"  DNp01 {output['target_body_id_decimal']} side {output['target_side']}: "
                f"{output['pair_edges']} edges, {output['raw_contact_mass']} contacts"
            )
    lines.extend(
        [
            "",
            "Ports-only cut context:",
            f"- internal: {cut['internal']['pair_edges']} edges, {cut['internal']['contact_mass']} contacts",
            f"- cut incoming: {cut['cut_incoming']['pair_edges']} edges, {cut['cut_incoming']['contact_mass']} contacts",
            f"- cut outgoing: {cut['cut_outgoing']['pair_edges']} edges, {cut['cut_outgoing']['contact_mass']} contacts",
            "",
            "Literature role references (not body-ID authorities):",
        ]
    )
    for reference in LITERATURE:
        lines.append(f"- {reference['doi']} {reference['url']}")
    lines.extend(
        [
            "",
            "Unresolved mapping ambiguity: none observed under exact canonical type matching.",
            "Body IDs and sides come only from pinned MaleCNS v1.0 annotation fields; no side or foreign body ID was inferred.",
            f"Operator manual receipt: {receipt['status']}",
        ]
    )
    if receipt.get("sha256"):
        lines.append(f"Operator receipt SHA-256: {receipt['sha256']}")
    return "\n".join(lines) + "\n"


def build_m04_mapping(
    *,
    repository_root: Path,
    lock_path: Path,
    full_graph_dir: Path,
    circuit_graph_dir: Path | None,
    output_dir: Path,
    circuit_profile_path: Path | None,
    model_profile_path: Path,
    encoder_profile_path: Path,
    decoder_profile_path: Path,
    calibration_plan_path: Path,
    require_manual_review: bool,
) -> dict[str, Any]:
    """Build exact M04 mapping, direct-wiring, sign, and cut-context evidence."""

    repository_root = repository_root.resolve()
    lock_path = lock_path.resolve()
    full_graph_dir = full_graph_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    lock, lock_digest = load_source_lock(lock_path, enforce_official=True)
    if lock_digest != ACCEPTED_SOURCE_LOCK_SHA256:
        raise MappingError("source-lock identity differs from accepted M03 identity")
    source_by_role = {entry["role"]: entry for entry in lock["files"]}
    annotation_entry = source_by_role["curated_annotations"]
    annotation_path = repository_root / "data" / "raw" / annotation_entry["filename"]
    size, annotation_digest = sha256_file(annotation_path)
    if (
        size != annotation_entry["observed_bytes"]
        or annotation_digest != annotation_entry["observed_sha256"]
    ):
        raise MappingError("pinned annotation source byte identity does not match source lock")

    full_audit = audit_graph(full_graph_dir)
    if full_audit["semantic_graph_digest"] != ACCEPTED_FULL_GRAPH_DIGEST:
        raise MappingError("compiled full graph semantic digest differs from accepted M03 graph")
    if full_audit["source_lock"]["sha256"] != ACCEPTED_SOURCE_LOCK_SHA256:
        raise MappingError("compiled full graph source lock differs from accepted M03 lock")
    if full_audit["compile_transform_profile"]["sha256"] != ACCEPTED_TRANSFORM_SHA256:
        raise MappingError("compiled full graph transform differs from accepted M03 transform")
    manifest = json.loads((full_graph_dir / "manifest.json").read_text(encoding="utf-8"))
    arrays = {
        name: np.load(full_graph_dir / entry["filename"], mmap_mode="r", allow_pickle=False)
        for name, entry in manifest["arrays"].items()
    }
    graph_ids = arrays["ids"]
    codebook = {
        int(code): entry
        for code, entry in manifest["transmitter_accounting"]["label_codebook"].items()
    }
    populations, discovery = _load_annotation_evidence(
        annotation_path, graph_ids, arrays, codebook
    )
    population_ids = _population_ids(populations)
    annotations_by_id = {
        int(record["body_id_decimal"]): record
        for records in populations.values()
        for record in records
    }
    direct_pathways = [
        _direct_pathway(
            source,
            population_ids,
            annotations_by_id,
            graph_ids,
            arrays["offsets"],
            arrays["targets"],
            arrays["counts"],
            arrays["weights"],
        )
        for source in ("LC4", "LPLC2")
    ]
    cut_context = _cut_context(
        population_ids,
        graph_ids,
        arrays["offsets"],
        arrays["targets"],
        arrays["counts"],
        arrays["weights"],
    )
    population_claims = {
        name: {
            "classification": "PROJECT INFERENCE",
            "mapping_rule": f"exact canonical MaleCNS v1.0 type == {name}",
            "count": len(populations[name]),
            "members": populations[name],
        }
        for name in TARGETS
    }
    claims = {
        "source_identity": {
            "classification": "SOURCE / MEASURED DATA",
            "release": "MaleCNS v1.0",
            "source_lock_sha256": lock_digest,
            "annotation_role": "curated_annotations",
            "annotation_filename": annotation_entry["filename"],
            "annotation_bytes": size,
            "annotation_observed_sha256": annotation_digest,
            "upstream_sha256": annotation_entry.get("upstream_sha256"),
        },
        "accepted_full_graph": {
            "classification": "SOURCE / MEASURED DATA",
            "semantic_digest": ACCEPTED_FULL_GRAPH_DIGEST,
            "N": full_audit["graph"]["N"],
            "source_accepted_E": full_audit["graph"]["source_accepted_E"],
            "represented_source_contacts": full_audit["graph"][
                "represented_source_contacts"
            ],
            "compile_transform_sha256": ACCEPTED_TRANSFORM_SHA256,
        },
        "annotation_discovery": discovery,
        "populations": population_claims,
        "direct_pathways": direct_pathways,
        "cut_context": cut_context,
        "literature_role_evidence": list(LITERATURE),
        "circuit_intervention": {
            "classification": "MODEL ASSUMPTION",
            "scope": "ports-only induced circuit",
            "members": "all exact LC4, LPLC2, and DNp01 canonical matches",
            "contact_pruning": "none",
            "outside_context": "omitted and quantified as cut incoming/outgoing mass",
        },
    }
    mapping_digest = _canonical_digest(claims)
    profile_validation: dict[str, Any]
    if circuit_profile_path is None:
        profile_validation = {
            "status": "NOT_CHECKED",
            "reason": "discovery run did not supply a circuit profile",
        }
    else:
        circuit_profile, circuit_profile_digest = _read_json(
            circuit_profile_path, "escape-circuit profile"
        )
        _validate_circuit_profile(circuit_profile, mapping_digest, population_ids)
        profile_validation = {
            "status": "PASS",
            "path": circuit_profile_path.as_posix(),
            "sha256": circuit_profile_digest,
            "profile_id": circuit_profile.get("profile_id"),
        }
    profile_identities = [
        _profile_identity(model_profile_path, "model"),
        _profile_identity(encoder_profile_path, "encoder"),
        _profile_identity(decoder_profile_path, "decoder"),
        _profile_identity(calibration_plan_path, "calibration_plan"),
    ]
    if circuit_graph_dir is None:
        circuit_verification = {
            "status": "NOT_CHECKED",
            "reason": "no compiled circuit directory was supplied",
        }
    else:
        circuit_verification = _verify_compiled_circuit(
            circuit_graph_dir.resolve(),
            population_ids,
            graph_ids,
            arrays,
            cut_context,
        )
    mapping = {
        "schema": MAPPING_SCHEMA,
        "version": MAPPING_VERSION,
        "status": "PASS",
        "mapping_digest": {
            "algorithm": "sha256",
            "domain": "FlyBench M04 pathway mapping v1",
            "canonicalization": "UTF-8 JSON, sorted keys, compact separators, no NaN",
            "value": mapping_digest,
            "binds": [
                "pinned source and accepted full graph identities",
                "exact annotation records and sides",
                "direct source-graph pathway edges and contacts",
                "transmitter/sign evidence",
                "ports-only cut-context accounting",
                "literature role citations with identity limitation",
            ],
        },
        "mapping_claims": claims,
        "circuit_profile_validation": profile_validation,
        "candidate_profile_identities": profile_identities,
        "compiled_circuit_verification": circuit_verification,
        "producer": {
            "tool": "tools/build_m04_mapping.py",
            "code_git_sha": _git_head(repository_root),
        },
    }
    write_json(output_dir / "mapping.json", mapping)
    write_json(
        output_dir / "annotation-excerpts.json",
        {
            "schema_version": 1,
            "source_lock_sha256": lock_digest,
            "annotation_observed_sha256": annotation_digest,
            "mapping_semantic_sha256": mapping_digest,
            "source_fields": list(ANNOTATION_FIELDS),
            "populations": population_claims,
        },
    )
    pathway_connectivity = {
        "schema_version": 1,
        "status": "PASS",
        "accepted_full_graph_semantic_digest": ACCEPTED_FULL_GRAPH_DIGEST,
        "mapping_semantic_sha256": mapping_digest,
        "pathways": direct_pathways,
    }
    write_json(output_dir / "pathway-connectivity.json", pathway_connectivity)
    write_json(
        output_dir / "sign-coverage.json",
        {
            "schema_version": 1,
            "status": "PASS",
            "accepted_compile_transform_sha256": ACCEPTED_TRANSFORM_SHA256,
            "mapping_semantic_sha256": mapping_digest,
            "pathways": [
                {
                    "source_population": pathway["source_population"],
                    "target_population": pathway["target_population"],
                    "direct_pair_edges": pathway["direct_pair_edges"],
                    "raw_contact_mass": pathway["raw_contact_mass"],
                    "executable_nonzero_edges": pathway["executable_nonzero_edges"],
                    "disabled_edges": pathway["disabled_edges"],
                    "disabled_contact_mass": pathway["disabled_contact_mass"],
                    "coverage": pathway["sign_coverage"],
                }
                for pathway in direct_pathways
            ],
        },
    )
    write_json(
        output_dir / "cut-context.json",
        {
            "schema_version": 1,
            "status": "PASS",
            "accepted_full_graph_semantic_digest": ACCEPTED_FULL_GRAPH_DIGEST,
            "mapping_semantic_sha256": mapping_digest,
            **cut_context,
        },
    )
    calibration_bytes = calibration_plan_path.read_bytes()
    (output_dir / "calibration-plan.json").write_bytes(calibration_bytes)
    receipt_path = output_dir / "manual-mapping-review.txt"
    if receipt_path.is_file() and receipt_path.stat().st_size:
        receipt_size, receipt_digest = sha256_file(receipt_path)
        receipt = {
            "status": "PRESENT_OPERATOR_SUPPLIED",
            "bytes": receipt_size,
            "sha256": receipt_digest,
        }
    else:
        receipt = {"status": "ABSENT"}
    pathway_gate = all(
        pathway["direct_pair_edges"] > 0
        and pathway["raw_contact_mass"] > 0
        and pathway["executable_nonzero_edges"] > 0
        for pathway in direct_pathways
    )
    mapping_gate = all(populations[name] for name in TARGETS) and not discovery[
        "ambiguous_candidates"
    ]
    outcome = "PASS" if mapping_gate and pathway_gate else "BLOCKED"
    decision = {
        "schema_version": 1,
        "gate": "G-MAP",
        "classification": "PROJECT INFERENCE",
        "outcome": outcome,
        "allowed_next_milestone": "M05" if outcome == "PASS" else None,
        "mapping_semantic_sha256": mapping_digest,
        "mapping_gate": "PASS" if mapping_gate else "FAIL",
        "direct_pathway_and_sign_gate": "PASS" if pathway_gate else "FAIL",
        "compiled_circuit_verification": circuit_verification,
        "manual_mapping_review_receipt": receipt,
        "external_milestone_acceptance": "PENDING",
        "unresolved_ambiguity": [],
    }
    write_json(output_dir / "decision.json", decision)
    review_text = _mapping_review(mapping, receipt)
    (output_dir / "mapping-review.txt").write_text(review_text, encoding="utf-8")
    if outcome != "PASS":
        raise MappingError("G-MAP scientific gate is BLOCKED")
    if require_manual_review and receipt["status"] == "ABSENT":
        raise MappingError("HUMAN M04 MAPPING REVIEW REQUIRED")
    return {
        "status": "PASS",
        "mapping_semantic_sha256": mapping_digest,
        "population_counts": {name: len(populations[name]) for name in TARGETS},
        "direct_pathways": [
            {
                "source_population": pathway["source_population"],
                "pair_edges": pathway["direct_pair_edges"],
                "contacts": pathway["raw_contact_mass"],
                "nonzero_edges": pathway["executable_nonzero_edges"],
                "disabled_edges": pathway["disabled_edges"],
            }
            for pathway in direct_pathways
        ],
        "cut_context": cut_context,
        "circuit_profile_validation": profile_validation,
        "compiled_circuit_verification": circuit_verification,
        "manual_mapping_review_receipt": receipt,
        "g_map_outcome": outcome,
    }
