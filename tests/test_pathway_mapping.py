from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather

from flybench.data import OFFICIAL_PAGE
from flybench.graph import compare_compiled_graphs, compile_graph
from flybench.pathway import (
    ACCEPTED_FULL_GRAPH_DIGEST,
    ACCEPTED_SOURCE_LOCK_SHA256,
    ACCEPTED_TRANSFORM_SHA256,
    _canonical_digest,
    _load_annotation_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads(
    (ROOT / "tests" / "fixtures" / "m04-reference.json").read_text(encoding="utf-8")
)
CIRCUIT = json.loads(
    (ROOT / "profiles" / "escape-circuit.json").read_text(encoding="utf-8")
)


def _population_ids(name: str) -> list[str]:
    return CIRCUIT["populations"][name]["body_ids_decimal"]


def test_committed_ids_resolve_to_exact_annotation_and_full_graph_evidence() -> None:
    all_ids: list[str] = []
    all_indices: list[int] = []
    expected_counts = {"LC4": 126, "LPLC2": 185, "DNp01": 2}
    for population, expected_count in expected_counts.items():
        records = REFERENCE["populations"][population]
        profile_ids = _population_ids(population)
        assert len(records) == expected_count
        assert [record["body_id_decimal"] for record in records] == profile_ids
        assert all(record["canonical_type"] == population for record in records)
        assert all(record["soma_side"] in {"L", "R"} for record in records)
        assert [int(value) for value in profile_ids] == sorted(map(int, profile_ids))
        assert [str(int(np.uint64(value))) for value in profile_ids] == profile_ids
        indices = [record["full_graph_dense_index"] for record in records]
        assert indices == sorted(indices)
        assert all(index >= 0 for index in indices)
        all_ids.extend(profile_ids)
        all_indices.extend(indices)
    assert len(all_ids) == len(set(all_ids)) == 313
    assert len(all_indices) == len(set(all_indices)) == 313
    assert CIRCUIT["selection"]["body_ids_from_populations"] is True
    assert REFERENCE["annotation_source_fields"][:5] == [
        "bodyId",
        "type",
        "instance",
        "synonyms",
        "somaSide",
    ]


def test_direct_pathways_are_recomputed_from_source_edges_and_sign_evidence() -> None:
    hard_expected = {
        "LC4": {"edges": 126, "contacts": 6362, "R": (55, 2580), "L": (71, 3782)},
        "LPLC2": {
            "edges": 185,
            "contacts": 4862,
            "R": (91, 2220),
            "L": (94, 2642),
        },
    }
    for pathway in REFERENCE["direct_pathways"]:
        expected = hard_expected[pathway["source_population"]]
        edges = pathway["edges"]
        assert len(edges) == expected["edges"] == pathway["pair_edges"]
        assert sum(edge["contacts"] for edge in edges) == expected["contacts"]
        assert sum(edge["contacts"] for edge in edges) == pathway["contacts"]
        assert all(edge["contacts"] >= 1 for edge in edges)
        assert all(edge["consensus_nt"] == "acetylcholine" for edge in edges)
        assert all(edge["effective_sign"] == 1 for edge in edges)
        assert all(edge["executable_weight"] == edge["contacts"] for edge in edges)
        assert pathway["nonzero_edges"] == len(edges)
        assert pathway["disabled_edges"] == pathway["disabled_contact_mass"] == 0
        assert {edge["source_body_id_decimal"] for edge in edges} == set(
            _population_ids(pathway["source_population"])
        )
        output_by_side = {
            output["target_side"]: (output["pair_edges"], output["raw_contact_mass"])
            for output in pathway["per_output_body"]
        }
        assert output_by_side == {"R": expected["R"], "L": expected["L"]}


def test_cut_context_and_accepted_m03_identities_are_frozen() -> None:
    assert REFERENCE["source_lock_sha256"] == ACCEPTED_SOURCE_LOCK_SHA256
    assert REFERENCE["accepted_full_graph_semantic_digest"] == ACCEPTED_FULL_GRAPH_DIGEST
    assert REFERENCE["compile_transform_profile_sha256"] == ACCEPTED_TRANSFORM_SHA256
    assert CIRCUIT["accepted_full_graph_semantic_digest"] == ACCEPTED_FULL_GRAPH_DIGEST
    assert CIRCUIT["source_lock_sha256"] == ACCEPTED_SOURCE_LOCK_SHA256
    assert CIRCUIT["compile_transform"]["sha256"] == ACCEPTED_TRANSFORM_SHA256
    assert CIRCUIT["mapping_evidence"]["semantic_sha256"] == REFERENCE[
        "mapping_semantic_sha256"
    ]
    cut = REFERENCE["cut_context"]
    assert cut["selected_node_count"] == 313
    assert cut["internal"]["pair_edges"] == 20607
    assert cut["internal"]["contact_mass"] == 79112
    assert cut["cut_incoming"]["pair_edges"] == 146852
    assert cut["cut_incoming"]["contact_mass"] == 614628
    assert cut["cut_outgoing"]["pair_edges"] == 47620
    assert cut["cut_outgoing"]["contact_mass"] == 254696
    assert REFERENCE["circuit_expected"]["source_accepted_E"] == cut["internal"][
        "pair_edges"
    ]
    assert REFERENCE["circuit_expected"]["represented_source_contacts"] == cut[
        "internal"
    ]["contact_mass"]
    assert all(value == "PASS" for value in cut["balance_checks"].values())


def test_mapping_discovery_is_deterministic_and_never_infers_missing_side(
    tmp_path: Path,
) -> None:
    ids = [2**53 + 1, 2**53 + 3, 2**53 + 5]
    columns: dict[str, pa.Array] = {
        "bodyId": pa.array(ids, type=pa.int64()),
        "type": pa.array(["LC4", "LPLC2", "DNp01"]),
        "instance": pa.array(["LC4_L", "LPLC2_R", "DNp01(GF)_R"]),
        "synonyms": pa.array([None, None, "GF"]),
        "somaSide": pa.array([None, "R", "R"]),
        "rootSide": pa.array([None, None, None]),
        "superclass": pa.array(["visual_projection", "visual_projection", "descending_neuron"]),
        "class": pa.array([None, None, None]),
        "subclass": pa.array([None, None, "lt"]),
        "supertype": pa.array([None, "fixture", None]),
        "flywireType": pa.array(["LC4", "LPLC2", "DNp01"]),
        "hemibrainType": pa.array(["LC4", "LPLC2", "Giant Fiber"]),
        "mancType": pa.array([None, None, "DNp01"]),
        "matchingNotes": pa.array([None, None, None]),
        "status": pa.array(["Traced", "Traced", "Traced"]),
        "statusLabel": pa.array(["Reviewed", "Reviewed", "Reviewed"]),
    }
    path = tmp_path / "annotations.feather"
    feather.write_feather(pa.table(columns), path)
    arrays = {
        "nt_record_present": np.ones(3, dtype=np.uint8),
        "predicted_nt_codes": np.ones(3, dtype=np.uint8),
        "predicted_nt_confidence": np.asarray([0.9, 0.8, 0.7], dtype=np.float64),
        "total_nt_predictions": np.asarray([10, 10, 10], dtype=np.int32),
        "ground_truth_nt_codes": np.zeros(3, dtype=np.uint8),
        "consensus_nt_codes": np.ones(3, dtype=np.uint8),
        "effective_signs": np.ones(3, dtype=np.int8),
    }
    codebook = {0: {"source_label": None}, 1: {"source_label": "acetylcholine"}}
    first, discovery_first = _load_annotation_evidence(
        path, np.asarray(ids, dtype=np.uint64), arrays, codebook
    )
    second, discovery_second = _load_annotation_evidence(
        path, np.asarray(ids, dtype=np.uint64), arrays, codebook
    )
    assert first == second
    assert discovery_first == discovery_second
    assert first["LC4"][0]["body_id_decimal"] == str(2**53 + 1)
    assert first["LC4"][0]["side_evidence"]["value"] is None
    assert first["LC4"][0]["side_evidence"]["inference"] == "none"
    payload = {"populations": first, "discovery": discovery_first}
    reversed_payload = {"discovery": discovery_first, "populations": first}
    assert _canonical_digest(payload) == _canonical_digest(reversed_payload)


def _write_explicit_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    source_dir = tmp_path / "raw"
    profiles = tmp_path / "profiles"
    source_dir.mkdir()
    profiles.mkdir()
    members = [
        record
        for population in ("LC4", "LPLC2", "DNp01")
        for record in REFERENCE["populations"][population]
    ]
    ids = sorted(int(record["body_id_decimal"]) for record in members)
    type_by_id = {
        int(record["body_id_decimal"]): record["canonical_type"] for record in members
    }
    side_by_id = {
        int(record["body_id_decimal"]): record["soma_side"] for record in members
    }
    annotation = pa.table(
        {
            "bodyId": pa.array(ids, type=pa.int64()),
            "superclass": pa.array(
                [
                    "descending_neuron" if type_by_id[value] == "DNp01" else "visual_projection"
                    for value in ids
                ]
            ),
            "type": pa.array([type_by_id[value] for value in ids]),
            "somaSide": pa.array([side_by_id[value] for value in ids]),
            "status": pa.array(["Traced"] * len(ids)),
            "statusLabel": pa.array(["Reviewed"] * len(ids)),
        }
    )
    transmitter = pa.table(
        {
            "body": pa.array(ids, type=pa.int64()),
            "total_nt_predictions": pa.array([10] * len(ids), type=pa.int32()),
            "predicted_nt_confidence": pa.array([0.9] * len(ids), type=pa.float64()),
            "predicted_nt": pa.array(["acetylcholine"] * len(ids)),
            "ground_truth": pa.array([None] * len(ids), type=pa.string()),
            "consensus_nt": pa.array(["acetylcholine"] * len(ids)),
        }
    )
    direct_edges = [
        edge
        for pathway in REFERENCE["direct_pathways"]
        for edge in pathway["edges"]
    ]
    connections = pa.table(
        {
            "body_pre": pa.array(
                [int(edge["source_body_id_decimal"]) for edge in direct_edges],
                type=pa.int64(),
            ),
            "body_post": pa.array(
                [int(edge["target_body_id_decimal"]) for edge in direct_edges],
                type=pa.int64(),
            ),
            "weight": pa.array([edge["contacts"] for edge in direct_edges], type=pa.int64()),
        }
    )
    source_paths = {
        "curated_annotations": source_dir / "annotations.feather",
        "aggregate_neurotransmitters": source_dir / "transmitters.feather",
        "connection_weights": source_dir / "connections.feather",
    }
    feather.write_feather(annotation, source_paths["curated_annotations"])
    feather.write_feather(transmitter, source_paths["aggregate_neurotransmitters"])
    feather.write_feather(connections, source_paths["connection_weights"])
    lock = {
        "schema_version": 1,
        "dataset": {
            "name": "MaleCNS",
            "release": "MaleCNS v1.0",
            "official_page": OFFICIAL_PAGE,
            "license": "CC-BY",
        },
        "files": [],
    }
    for role, path in source_paths.items():
        payload = path.read_bytes()
        lock["files"].append(
            {
                "role": role,
                "filename": path.name,
                "official_url": f"https://example.invalid/{path.name}",
                "download_max_bytes": 10_000_000,
                "expected_format": "Apache Arrow Feather",
                "upstream_sha256": None,
                "upstream_sha256_provenance": "fixture",
                "observed_bytes": len(payload),
                "observed_sha256": hashlib.sha256(payload).hexdigest(),
                "observed_sha256_provenance": "fixture",
            }
        )
    lock_path = profiles / "source-lock.json"
    lock_path.write_text(json.dumps(lock, sort_keys=True) + "\n", encoding="utf-8")
    (profiles / "compile-transform-v1.json").write_bytes(
        (ROOT / "profiles" / "compile-transform-v1.json").read_bytes()
    )
    selection = json.loads(json.dumps(CIRCUIT))
    selection["source_lock_sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    selection_path = profiles / "escape-circuit.json"
    selection_path.write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return source_dir, lock_path, selection_path


def test_explicit_circuit_compilation_contains_exact_ids_and_is_deterministic(
    tmp_path: Path,
) -> None:
    source_dir, lock_path, selection_path = _write_explicit_fixture(tmp_path)
    outputs = []
    manifests = []
    for name in ("first", "second"):
        output = tmp_path / name
        manifests.append(
            compile_graph(
                lock_path,
                selection_path,
                output,
                source_dir=source_dir,
                enforce_official=False,
                command=["fixture", name],
            )
        )
        outputs.append(output)
    expected_ids = np.asarray(
        sorted(
            int(value)
            for population in ("LC4", "LPLC2", "DNp01")
            for value in _population_ids(population)
        ),
        dtype=np.uint64,
    )
    compiled_ids = np.load(outputs[0] / "ids.npy", mmap_mode="r")
    assert np.array_equal(compiled_ids, expected_ids)
    assert manifests[0]["graph"]["N"] == 313
    assert manifests[0]["graph"]["source_accepted_E"] == 311
    assert manifests[0]["graph"]["represented_source_contacts"] == 11224
    comparison = compare_compiled_graphs(outputs[0], outputs[1])
    assert all(value == "PASS" for value in comparison["checks"].values())


def test_candidate_profiles_freeze_scope_without_implementing_later_milestones() -> None:
    model = json.loads((ROOT / "profiles" / "model-v0.1.json").read_text())
    encoder = json.loads((ROOT / "profiles" / "encoder-v0.1.json").read_text())
    decoder = json.loads((ROOT / "profiles" / "decoder-v0.1.json").read_text())
    calibration = json.loads((ROOT / "profiles" / "calibration-plan.json").read_text())
    assert model["implementation_status"] == "NOT_IMPLEMENTED"
    assert model["candidate_timestep_study_ms"] == [0.5, 0.25, 0.1]
    assert model["synaptic_scale_convention"]["runtime_parameter"] == "runtime_synaptic_scale"
    assert encoder["mode"] == "feature-level stimulation"
    assert [port["population"] for port in encoder["ports"]] == ["LC4", "LPLC2"]
    assert "threat bearing" in decoder["forbidden_inputs"]
    assert decoder["only_external_scientific_input"] == "declared DNp01 model spike output"
    grid = calibration["primary_grid"]
    assert grid["runtime_synaptic_scale"] == [0.0001, 0.0003, 0.001, 0.003]
    assert grid["peak_sensory_external_drive"] == [1.25, 2.0, 4.0]
    assert len(grid["runtime_synaptic_scale"]) * len(
        grid["peak_sensory_external_drive"]
    ) == grid["maximum_primary_combinations"] == 12
    assert calibration["execution_status"] == "FROZEN_NOT_EXECUTED"
