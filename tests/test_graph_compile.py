from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather
import pytest

from flybench.data import OFFICIAL_PAGE
from flybench.graph import (
    GraphAuditError,
    GraphCompileError,
    audit_graph,
    compile_graph,
    validate_int32_index_capacity,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "m03-exact-graph.json").read_text(
        encoding="utf-8"
    )
)
ROLES = {
    "curated_annotations": "annotations.fixture.feather",
    "aggregate_neurotransmitters": "transmitters.fixture.feather",
    "connection_weights": "connections.fixture.feather",
}


def _write_feather_sources(
    source_dir: Path,
    annotations: list[dict],
    transmitters: list[dict],
    connections: list[dict],
    *,
    connection_extra: dict[str, list] | None = None,
) -> dict[str, Path]:
    source_dir.mkdir(parents=True)
    annotation_table = pa.table(
        {
            "bodyId": pa.array([row["bodyId"] for row in annotations]),
            "superclass": pa.array([row.get("superclass") for row in annotations]),
            "status": pa.array([row.get("status") for row in annotations]),
            "statusLabel": pa.array([row.get("statusLabel") for row in annotations]),
        }
    )
    transmitter_table = pa.table(
        {
            "body": pa.array([row["body"] for row in transmitters]),
            "total_nt_predictions": pa.array(
                [row["total_nt_predictions"] for row in transmitters], type=pa.int32()
            ),
            "predicted_nt_confidence": pa.array(
                [row["predicted_nt_confidence"] for row in transmitters],
                type=pa.float64(),
            ),
            "predicted_nt": pa.array([row["predicted_nt"] for row in transmitters]),
            "ground_truth": pa.array([row.get("ground_truth") for row in transmitters]),
            "consensus_nt": pa.array([row["consensus_nt"] for row in transmitters]),
        }
    )
    connection_columns: dict[str, pa.Array | list] = {
        "body_pre": pa.array([row["body_pre"] for row in connections]),
        "body_post": pa.array([row["body_post"] for row in connections]),
        "weight": pa.array([row["weight"] for row in connections]),
    }
    if connection_extra:
        connection_columns.update(connection_extra)
    connection_table = pa.table(connection_columns)
    paths = {
        "curated_annotations": source_dir / ROLES["curated_annotations"],
        "aggregate_neurotransmitters": source_dir
        / ROLES["aggregate_neurotransmitters"],
        "connection_weights": source_dir / ROLES["connection_weights"],
    }
    feather.write_feather(annotation_table, paths["curated_annotations"])
    feather.write_feather(transmitter_table, paths["aggregate_neurotransmitters"])
    feather.write_feather(connection_table, paths["connection_weights"])
    return paths


def _write_profiles_and_lock(
    root: Path, paths: dict[str, Path]
) -> tuple[Path, Path]:
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
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
    for role in (
        "curated_annotations",
        "aggregate_neurotransmitters",
        "connection_weights",
    ):
        payload = paths[role].read_bytes()
        lock["files"].append(
            {
                "role": role,
                "filename": paths[role].name,
                "official_url": f"https://example.invalid/{paths[role].name}",
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
    transform_name = "compile-transform-v1.json"
    (profiles / transform_name).write_bytes(
        (ROOT / "profiles" / "compile-transform-v1.json").read_bytes()
    )
    transform = json.loads((profiles / transform_name).read_text(encoding="utf-8"))
    selection = {
        "schema_version": 1,
        "profile_id": "fixture.accepted-neurons.v1",
        "source_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "annotation_source_role": "curated_annotations",
        "selection": {
            "biological_id_field": "bodyId",
            "accepted_when": {"field": "superclass", "operator": "not_null"},
            "rule": "Fixture rows with non-null superclass.",
            "invalid_id_policy": "error",
            "duplicate_id_policy": "deduplicate_after_rule_and_account",
        },
        "exclusion_rule": "Fixture null superclass rows are excluded.",
        "ordering_rule": "Exact ascending uint64.",
        "compile_transform": {
            "path": transform_name,
            "profile_id": transform["profile_id"],
        },
    }
    selection_path = profiles / "accepted-neurons.json"
    selection_path.write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return lock_path, selection_path


def _compile_fixture(
    tmp_path: Path,
    *,
    annotations: list[dict] | None = None,
    transmitters: list[dict] | None = None,
    connections: list[dict] | None = None,
    connection_extra: dict[str, list] | None = None,
    name: str = "compiled",
) -> tuple[Path, dict]:
    annotations = list(annotations or FIXTURE["accepted_annotation_rows"])
    transmitters = list(transmitters or FIXTURE["transmitter_rows"])
    connections = list(connections or FIXTURE["connection_rows"])
    source_dir = tmp_path / f"{name}-sources"
    paths = _write_feather_sources(
        source_dir,
        annotations,
        transmitters,
        connections,
        connection_extra=connection_extra,
    )
    lock_path, selection_path = _write_profiles_and_lock(tmp_path / f"{name}-config", paths)
    out = tmp_path / name
    manifest = compile_graph(
        lock_path,
        selection_path,
        out,
        source_dir=source_dir,
        enforce_official=False,
        command=["fixture", "compile"],
    )
    return out, manifest


def _load_arrays(graph: Path) -> dict[str, np.ndarray]:
    return {
        name: np.load(graph / filename, mmap_mode="r", allow_pickle=False)
        for name, filename in {
            "ids": "ids.npy",
            "offsets": "offsets.npy",
            "targets": "targets.npy",
            "counts": "counts.npy",
            "weights": "weights.npy",
        }.items()
    }


def test_exact_fixture_arrays_counts_orientation_and_audit(tmp_path: Path) -> None:
    graph, manifest = _compile_fixture(tmp_path)
    arrays = _load_arrays(graph)
    expected = FIXTURE["expected"]

    assert arrays["ids"].dtype == np.dtype("uint64")
    assert arrays["offsets"].dtype == np.dtype("int64")
    assert arrays["targets"].dtype == np.dtype("int32")
    assert arrays["counts"].dtype == np.dtype("uint64")
    assert arrays["weights"].dtype == np.dtype("float32")
    assert arrays["ids"].tolist() == expected["ids"]
    assert arrays["offsets"].tolist() == expected["offsets"]
    assert arrays["targets"].tolist() == expected["targets"]
    assert arrays["counts"].tolist() == expected["counts"]
    assert arrays["weights"].tolist() == expected["weights"]
    assert all(not array.flags.writeable for array in arrays.values())

    graph_counts = manifest["graph"]
    for key in (
        "N",
        "source_accepted_E",
        "executable_nonzero_E",
        "represented_source_contacts",
        "disabled_zero_weight_contact_mass",
        "isolated_accepted_neurons",
    ):
        expected_key = "contacts" if key == "represented_source_contacts" else key
        expected_key = (
            "disabled_contact_mass"
            if key == "disabled_zero_weight_contact_mass"
            else expected_key
        )
        assert graph_counts[key] == expected[expected_key]
    assert graph_counts["duplicate_input_rows_aggregated"] == 1
    assert graph_counts["pairs_with_multiple_input_rows"] == 1

    # Independent source-major propagation: each stored row is presynaptic and
    # contributes to its target, i.e. the sparse equivalent of A.T @ spikes.
    spikes = np.asarray([2.0, 3.0, 5.0, 7.0], dtype=np.float32)
    incoming = np.zeros(4, dtype=np.float32)
    for source in range(4):
        low, high = arrays["offsets"][source : source + 2]
        for edge in range(int(low), int(high)):
            incoming[arrays["targets"][edge]] += arrays["weights"][edge] * spikes[source]
    assert incoming.tolist() == [0.0, -10.0, -9.0, 0.0]

    audit = audit_graph(graph, tmp_path / "fixture-audit.json")
    assert audit["status"] == "PASS"
    assert audit["graph"]["represented_source_contacts"] == 15
    assert audit["checks"]["orientation_source_major"] == "PASS"


def test_committed_profiles_pin_source_rule_and_model_assumptions() -> None:
    selection_path = ROOT / "profiles" / "accepted-neurons.json"
    transform_path = ROOT / "profiles" / "compile-transform-v1.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    transform = json.loads(transform_path.read_text(encoding="utf-8"))
    assert selection["source_lock_sha256"] == hashlib.sha256(
        (ROOT / "profiles" / "source-lock.json").read_bytes()
    ).hexdigest()
    assert selection["selection"]["accepted_when"] == {
        "field": "superclass",
        "operator": "not_null",
    }
    assert selection["ordering_rule"].startswith("Sort accepted biological body IDs")
    assumption = transform["model_assumption"]
    assert assumption["classification"] == "MODEL ASSUMPTION"
    assert assumption["global_gain"] == 1.0
    assert assumption["normalization"] == "none"
    assert assumption["labels"]["acetylcholine"]["effective_sign"] == 1
    for label in ("gaba", "histamine", "glutamate"):
        assert assumption["labels"][label]["effective_sign"] == -1
    for label in ("unclear", "octopamine", "serotonin", "dopamine"):
        assert assumption["labels"][label]["effective_sign"] == 0


def test_reordered_inputs_have_identical_semantic_graph_and_arrays(tmp_path: Path) -> None:
    first, _ = _compile_fixture(tmp_path, name="first")
    annotations = list(FIXTURE["accepted_annotation_rows"])
    transmitters = list(FIXTURE["transmitter_rows"])
    connections = list(FIXTURE["connection_rows"])
    random.Random(11).shuffle(annotations)
    random.Random(12).shuffle(transmitters)
    random.Random(13).shuffle(connections)
    second, _ = _compile_fixture(
        tmp_path,
        annotations=annotations,
        transmitters=transmitters,
        connections=connections,
        name="second",
    )
    first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    assert (
        first_manifest["semantic_digest"]["value"]
        == second_manifest["semantic_digest"]["value"]
    )
    assert (
        first_manifest["selection_profile"]["semantic_sha256"]
        == second_manifest["selection_profile"]["semantic_sha256"]
    )
    assert (
        first_manifest["selection_profile"]["sha256"]
        != second_manifest["selection_profile"]["sha256"]
    )
    for filename in ("ids.npy", "offsets.npy", "targets.npy", "counts.npy", "weights.npy"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_invalid_endpoints_are_filtered_and_mass_is_accounted(tmp_path: Path) -> None:
    connections = list(FIXTURE["connection_rows"]) + [
        {"body_pre": 10, "body_post": 777, "weight": 11},
        {"body_pre": 888, "body_post": 20, "weight": 13},
        {"body_pre": 888, "body_post": 777, "weight": 17},
    ]
    _, manifest = _compile_fixture(tmp_path, connections=connections)
    accounting = manifest["endpoint_and_contact_accounting"]
    assert accounting["source_weight_rows_read"] == 8
    assert accounting["rows_source_endpoint_not_accepted"] == 2
    assert accounting["rows_target_endpoint_not_accepted"] == 2
    assert accounting["rows_both_endpoints_accepted"] == 5
    assert accounting["source_contact_mass_retained"] == 15
    assert accounting["source_contact_mass_excluded"] == 41
    by_reason = {entry["reason"]: entry for entry in accounting["exclusions"]}
    assert by_reason["source_endpoint_not_accepted_target_accepted"]["contact_mass"] == 13
    assert by_reason["target_endpoint_not_accepted_source_accepted"]["contact_mass"] == 11
    assert by_reason["both_endpoints_not_accepted"]["contact_mass"] == 17


def test_non_integer_and_negative_ids_fail_instead_of_coercing(tmp_path: Path) -> None:
    graph_source = tmp_path / "bad-type-sources"
    paths = _write_feather_sources(
        graph_source,
        FIXTURE["accepted_annotation_rows"],
        FIXTURE["transmitter_rows"],
        FIXTURE["connection_rows"],
    )
    bad_connections = pa.table(
        {
            "body_pre": ["10"],
            "body_post": [20],
            "weight": [1],
        }
    )
    feather.write_feather(bad_connections, paths["connection_weights"])
    lock, selection = _write_profiles_and_lock(tmp_path / "bad-type-config", paths)
    with pytest.raises(GraphCompileError, match="must be an integer Arrow field"):
        compile_graph(
            lock,
            selection,
            tmp_path / "bad-type-out",
            source_dir=graph_source,
            enforce_official=False,
        )

    annotations = list(FIXTURE["accepted_annotation_rows"])
    annotations[0] = {**annotations[0], "bodyId": -10}
    with pytest.raises(GraphCompileError, match="must be positive"):
        _compile_fixture(tmp_path, annotations=annotations, name="negative")


def test_actual_pair_schema_has_no_roi_partition_and_extra_columns_fail(tmp_path: Path) -> None:
    _, manifest = _compile_fixture(tmp_path, name="plain-schema")
    semantics = manifest["connection_table_semantics"]
    assert semantics["observed_fields"] == ["body_pre", "body_post", "weight"]
    assert semantics["roi_partition_columns"] == []
    assert "same exact biological source-target pair" in semantics["aggregation_rule"]

    with pytest.raises(GraphCompileError, match="counting ambiguous"):
        _compile_fixture(
            tmp_path,
            connection_extra={"roi": ["A"] * len(FIXTURE["connection_rows"])},
            name="roi-schema",
        )


def test_large_biological_ids_round_trip_exactly_as_uint64(tmp_path: Path) -> None:
    large = 2**53 + 17
    annotations = [
        {"bodyId": large + 2, "superclass": "fixture", "status": "Traced", "statusLabel": "Reviewed"},
        {"bodyId": 10, "superclass": "fixture", "status": "Traced", "statusLabel": "Reviewed"},
        {"bodyId": large, "superclass": "fixture", "status": "Traced", "statusLabel": "Reviewed"},
    ]
    transmitters = [
        {
            "body": body,
            "total_nt_predictions": 1,
            "predicted_nt_confidence": 1.0,
            "predicted_nt": "acetylcholine",
            "ground_truth": None,
            "consensus_nt": "acetylcholine",
        }
        for body in (10, large, large + 2)
    ]
    connections = [{"body_pre": large, "body_post": large + 2, "weight": 9}]
    graph, _ = _compile_fixture(
        tmp_path,
        annotations=annotations,
        transmitters=transmitters,
        connections=connections,
        name="large-ids",
    )
    ids = np.load(graph / "ids.npy", allow_pickle=False)
    assert ids.dtype == np.dtype("uint64")
    assert ids.tolist() == [10, large, large + 2]
    assert int(ids[1]) == large


def test_unknown_transmitter_label_stops_compilation(tmp_path: Path) -> None:
    transmitters = list(FIXTURE["transmitter_rows"])
    transmitters[0] = {
        **transmitters[0],
        "predicted_nt": "invented-alias",
        "consensus_nt": "invented-alias",
    }
    with pytest.raises(GraphCompileError, match="unrecognized transmitter label"):
        _compile_fixture(tmp_path, transmitters=transmitters, name="unknown-nt")


def test_missing_transmitter_record_remains_explicit_and_disabled(tmp_path: Path) -> None:
    transmitters = [row for row in FIXTURE["transmitter_rows"] if row["body"] != 40]
    graph, manifest = _compile_fixture(
        tmp_path, transmitters=transmitters, name="missing-nt"
    )
    assert manifest["transmitter_accounting"]["accepted_ids_missing_source_record"] == 1
    present = np.load(graph / "nt-record-present.npy", allow_pickle=False)
    consensus = np.load(graph / "consensus-nt-codes.npy", allow_pickle=False)
    signs = np.load(graph / "effective-signs.npy", allow_pickle=False)
    confidence = np.load(graph / "predicted-nt-confidence.npy", allow_pickle=False)
    assert present.tolist() == [1, 1, 0, 1]
    assert consensus[2] == 0
    assert signs[2] == 0
    assert np.isnan(confidence[2])
    weights = np.load(graph / "weights.npy", allow_pickle=False)
    assert weights.tolist() == [1.0, -4.0, -3.0, 0.0]


def test_duplicate_annotation_ids_are_deduplicated_and_accounted(tmp_path: Path) -> None:
    annotations = list(FIXTURE["accepted_annotation_rows"]) + [
        dict(FIXTURE["accepted_annotation_rows"][0])
    ]
    graph, manifest = _compile_fixture(
        tmp_path, annotations=annotations, name="duplicate-annotation"
    )
    assert np.load(graph / "ids.npy", allow_pickle=False).tolist() == [10, 20, 40, 99]
    accounting = manifest["selection_accounting"]
    assert accounting["accepted_annotation_rows"] == 5
    assert accounting["accepted_unique_ids"] == 4
    assert accounting["duplicate_accepted_annotation_rows"] == 1


def test_all_filtered_edges_produce_valid_empty_adjacency(tmp_path: Path) -> None:
    connections = [{"body_pre": 777, "body_post": 888, "weight": 9}]
    graph, manifest = _compile_fixture(
        tmp_path, connections=connections, name="empty-adjacency"
    )
    assert manifest["graph"]["source_accepted_E"] == 0
    assert manifest["graph"]["represented_source_contacts"] == 0
    assert manifest["graph"]["isolated_accepted_neurons"] == 4
    assert np.load(graph / "offsets.npy", allow_pickle=False).tolist() == [0, 0, 0, 0, 0]
    assert audit_graph(graph)["status"] == "PASS"


def test_int32_node_bound_is_explicit() -> None:
    validate_int32_index_capacity(np.iinfo(np.int32).max)
    with pytest.raises(GraphCompileError, match="exceeds int32"):
        validate_int32_index_capacity(int(np.iinfo(np.int32).max) + 1)


def test_audit_detects_array_byte_change(tmp_path: Path) -> None:
    graph, _ = _compile_fixture(tmp_path)
    counts = np.load(graph / "counts.npy", mmap_mode="r+", allow_pickle=False)
    counts[0] = 123
    counts.flush()
    with pytest.raises(GraphAuditError, match="differs from manifest"):
        audit_graph(graph)
