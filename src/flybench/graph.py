"""Deterministic M03 compiler and independent audit for immutable sparse graphs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import resource
import shutil
import subprocess
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as feather

from flybench.data import load_source_lock, sha256_file


COMPILER_ID = "flybench.graph-compiler.v1"
MANIFEST_SCHEMA = "flybench.compiled-graph"
MANIFEST_VERSION = 1
AUDIT_SCHEMA = "flybench.graph-audit"
AUDIT_VERSION = 1
SEMANTIC_DIGEST_DOMAIN = b"FlyBench semantic sparse graph v1\0"
INT32_MAX = np.iinfo(np.int32).max
UINT64_MAX = np.iinfo(np.uint64).max

SEMANTIC_ARRAYS = ("ids", "offsets", "targets", "counts", "weights")
ARRAY_FILENAMES = {
    "ids": "ids.npy",
    "offsets": "offsets.npy",
    "targets": "targets.npy",
    "counts": "counts.npy",
    "weights": "weights.npy",
    "nt_record_present": "nt-record-present.npy",
    "predicted_nt_codes": "predicted-nt-codes.npy",
    "predicted_nt_confidence": "predicted-nt-confidence.npy",
    "total_nt_predictions": "total-nt-predictions.npy",
    "ground_truth_nt_codes": "ground-truth-nt-codes.npy",
    "consensus_nt_codes": "consensus-nt-codes.npy",
    "effective_signs": "effective-signs.npy",
}
EXPECTED_DTYPES = {
    "ids": "uint64",
    "offsets": "int64",
    "targets": "int32",
    "counts": "uint64",
    "weights": "float32",
    "nt_record_present": "uint8",
    "predicted_nt_codes": "uint8",
    "predicted_nt_confidence": "float64",
    "total_nt_predictions": "int32",
    "ground_truth_nt_codes": "uint8",
    "consensus_nt_codes": "uint8",
    "effective_signs": "int8",
}


class GraphCompileError(RuntimeError):
    """Compilation could not preserve the declared M03 semantics."""


class GraphAuditError(RuntimeError):
    """A compiled graph failed an independent M03 audit check."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _read_json(path: Path, description: str) -> tuple[dict[str, Any], bytes, str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphCompileError(f"invalid {description} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GraphCompileError(f"{description} must be a JSON object")
    return value, raw, hashlib.sha256(raw).hexdigest()


def _git_head(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def validate_int32_index_capacity(node_count: int) -> None:
    """Reject a graph whose dense targets cannot be represented by int32."""

    if not isinstance(node_count, int) or isinstance(node_count, bool) or node_count < 1:
        raise GraphCompileError("accepted node count must be a positive integer")
    if node_count > INT32_MAX:
        raise GraphCompileError(
            f"accepted node count {node_count} exceeds int32 target-index capacity {INT32_MAX}"
        )


def _validate_selection_profile(
    profile: dict[str, Any], source_lock_digest: str
) -> dict[str, Any]:
    if profile.get("schema_version") != 1:
        raise GraphCompileError("selection profile schema_version must be 1")
    if profile.get("source_lock_sha256") != source_lock_digest:
        raise GraphCompileError("selection profile does not identify the supplied source lock")
    if profile.get("annotation_source_role") != "curated_annotations":
        raise GraphCompileError("selection profile must use curated_annotations")
    selection_value = profile.get("selection")
    if not isinstance(selection_value, dict):
        raise GraphCompileError("selection profile is missing selection rules")
    # Resolve compiler-only convenience fields on a copy. The committed profile bytes
    # remain the sole input to selection semantic identity and audit reproduction.
    selection = dict(selection_value)
    if selection.get("biological_id_field") != "bodyId":
        raise GraphCompileError("selection biological ID field must be bodyId")
    if selection.get("invalid_id_policy") != "error":
        raise GraphCompileError("invalid biological IDs must use the error policy")
    mode = selection.get("mode", "annotation_rule")
    accepted_when = selection.get("accepted_when")
    if accepted_when != {"field": "superclass", "operator": "not_null"}:
        raise GraphCompileError(
            "selection must explicitly require membership in the accepted non-null-superclass population"
        )
    if mode == "annotation_rule":
        if selection.get("duplicate_id_policy") != "deduplicate_after_rule_and_account":
            raise GraphCompileError(
                "annotation-rule selection duplicate-ID policy is missing or unsupported"
            )
    elif mode == "explicit_body_ids":
        if selection.get("duplicate_id_policy") != "error":
            raise GraphCompileError("explicit selection must reject duplicate body IDs")
        if selection.get("missing_id_policy") != "error":
            raise GraphCompileError("explicit selection must reject missing body IDs")
        raw_ids = selection.get("body_ids_decimal")
        if raw_ids is None and selection.get("body_ids_from_populations") is True:
            populations = profile.get("populations")
            if not isinstance(populations, dict) or not populations:
                raise GraphCompileError(
                    "explicit selection population source is missing populations"
                )
            population_ids: list[str] = []
            for population in sorted(populations):
                entry = populations[population]
                if not isinstance(entry, dict) or not isinstance(
                    entry.get("body_ids_decimal"), list
                ):
                    raise GraphCompileError(
                        f"explicit population {population!r} lacks body_ids_decimal"
                    )
                population_ids.extend(entry["body_ids_decimal"])
            raw_ids = sorted(population_ids, key=lambda value: int(value))
            selection["body_ids_decimal"] = raw_ids
        if not isinstance(raw_ids, list) or not raw_ids:
            raise GraphCompileError(
                "explicit selection requires body_ids_decimal or population ID lists"
            )
        parsed: list[int] = []
        for value in raw_ids:
            if (
                not isinstance(value, str)
                or not value.isascii()
                or not value.isdecimal()
                or value != str(int(value))
            ):
                raise GraphCompileError(
                    "explicit body IDs must be canonical positive decimal strings"
                )
            integer = int(value)
            if not 1 <= integer <= UINT64_MAX:
                raise GraphCompileError("explicit body ID is outside positive uint64 range")
            parsed.append(integer)
        if parsed != sorted(parsed) or len(parsed) != len(set(parsed)):
            raise GraphCompileError(
                "explicit body IDs must be unique and strictly numerically ordered"
            )
    else:
        raise GraphCompileError(f"unsupported selection mode {mode!r}")
    transform = profile.get("compile_transform")
    if not isinstance(transform, dict) or not isinstance(transform.get("path"), str):
        raise GraphCompileError("selection profile must reference a compile transform path")
    return selection


def _validate_transform_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if profile.get("schema_version") != 1:
        raise GraphCompileError("compile-transform schema_version must be 1")
    source = profile.get("source_data")
    assumption = profile.get("model_assumption")
    if not isinstance(source, dict) or not isinstance(assumption, dict):
        raise GraphCompileError("compile-transform source and model sections are required")
    expected_source = {
        "role": "aggregate_neurotransmitters",
        "body_id_field": "body",
        "predicted_label_field": "predicted_nt",
        "predicted_confidence_field": "predicted_nt_confidence",
        "prediction_count_field": "total_nt_predictions",
        "ground_truth_field": "ground_truth",
        "effective_label_field": "consensus_nt",
        "classification": "SOURCE DATA",
    }
    if any(source.get(key) != value for key, value in expected_source.items()):
        raise GraphCompileError("compile-transform source fields do not match M03")
    if assumption.get("classification") != "MODEL ASSUMPTION":
        raise GraphCompileError("compile-transform signs must be marked MODEL ASSUMPTION")
    if assumption.get("global_gain") != 1.0 or assumption.get("normalization") != "none":
        raise GraphCompileError("M03 requires unit compile gain and no normalization")
    if assumption.get("unrecognized_label_policy") != "error":
        raise GraphCompileError("unrecognized transmitter labels must fail explicitly")
    null_entry = assumption.get("null_or_missing")
    if not isinstance(null_entry, dict) or null_entry.get("code") != 0 or null_entry.get(
        "effective_sign"
    ) != 0:
        raise GraphCompileError("null/missing transmitter data must map explicitly to code/sign 0")
    labels = assumption.get("labels")
    if not isinstance(labels, dict) or not labels:
        raise GraphCompileError("compile-transform must enumerate source labels")
    seen_codes = {0}
    for label, entry in labels.items():
        if not isinstance(label, str) or not label or not isinstance(entry, dict):
            raise GraphCompileError("invalid transmitter mapping entry")
        code = entry.get("code")
        sign = entry.get("effective_sign")
        if (
            not isinstance(code, int)
            or isinstance(code, bool)
            or not 1 <= code <= np.iinfo(np.uint8).max
            or code in seen_codes
        ):
            raise GraphCompileError(f"invalid or duplicate transmitter code for {label!r}")
        if sign not in {-1, 0, 1}:
            raise GraphCompileError(f"invalid effective sign for {label!r}")
        seen_codes.add(code)
    return assumption


def _selection_semantic_digest(profile: dict[str, Any]) -> str:
    """Identify the selection rule independently of locked source byte ordering."""

    semantic_profile = dict(profile)
    semantic_profile.pop("source_lock_sha256", None)
    canonical = json.dumps(
        semantic_profile, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(b"FlyBench accepted-node selection v1\0" + canonical).hexdigest()


def _source_entries(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = {entry.get("role"): entry for entry in lock.get("files", [])}
    required = {
        "curated_annotations",
        "aggregate_neurotransmitters",
        "connection_weights",
    }
    if set(entries) != required:
        raise GraphCompileError("source lock does not contain the exact M03 source roles")
    return entries


def _verify_source_files(
    lock: dict[str, Any], source_dir: Path
) -> tuple[dict[str, Path], list[dict[str, Any]]]:
    paths: dict[str, Path] = {}
    identities: list[dict[str, Any]] = []
    for role, entry in sorted(_source_entries(lock).items()):
        path = source_dir / entry["filename"]
        if not path.is_file():
            raise GraphCompileError(f"required source is missing: {path}")
        size, digest = sha256_file(path)
        if size != entry.get("observed_bytes") or digest != entry.get("observed_sha256"):
            raise GraphCompileError(
                f"source identity mismatch for {role}: observed {size} bytes/{digest}"
            )
        paths[role] = path
        identities.append(
            {
                "role": role,
                "filename": entry["filename"],
                "bytes": size,
                "observed_sha256": digest,
                "upstream_sha256": entry.get("upstream_sha256"),
            }
        )
    return paths, identities


def _strict_uint64_array(
    column: pa.Array | pa.ChunkedArray,
    field_name: str,
    *,
    positive: bool,
) -> np.ndarray:
    if column.null_count:
        raise GraphCompileError(f"{field_name} contains null values")
    value_type = column.type
    if not (pa.types.is_signed_integer(value_type) or pa.types.is_unsigned_integer(value_type)):
        raise GraphCompileError(
            f"{field_name} must be an integer Arrow field, observed {value_type}"
        )
    if isinstance(column, pa.ChunkedArray):
        column = column.combine_chunks()
    values = column.to_numpy(zero_copy_only=False)
    if pa.types.is_signed_integer(value_type) and values.size:
        minimum = int(values.min())
        if minimum < (1 if positive else 0):
            requirement = "positive" if positive else "nonnegative"
            raise GraphCompileError(f"{field_name} values must be {requirement}")
    elif positive and values.size and int(values.min()) == 0:
        raise GraphCompileError(f"{field_name} values must be positive")
    return values.astype(np.dtype("<u8"), copy=False)


def _inventory(values: list[Any]) -> dict[str, int]:
    counts = Counter("<null>" if value is None else str(value) for value in values)
    return {key: counts[key] for key in sorted(counts)}


def _load_annotation_rule_ids(
    path: Path, selection: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any]]:
    id_field = selection["biological_id_field"]
    class_field = selection["accepted_when"]["field"]
    required = [id_field, class_field, "status", "statusLabel"]
    try:
        table = feather.read_table(path, columns=required, memory_map=True)
    except (OSError, pa.ArrowException) as exc:
        raise GraphCompileError(f"cannot read annotation selection fields: {exc}") from exc
    ids = _strict_uint64_array(table[id_field], id_field, positive=True)
    classes = table[class_field].to_pylist()
    statuses = table["status"].to_pylist()
    status_labels = table["statusLabel"].to_pylist()
    mask = np.fromiter((value is not None for value in classes), dtype=np.bool_, count=len(classes))
    accepted_rows = ids[mask]
    accepted_ids = np.unique(accepted_rows).astype(np.dtype("<u8"), copy=False)
    if accepted_ids.size == 0:
        raise GraphCompileError("selection produced no accepted neurons")
    validate_int32_index_capacity(int(accepted_ids.size))
    duplicate_rows = int(accepted_rows.size - accepted_ids.size)
    accepted_statuses = [value for value, keep in zip(statuses, mask, strict=True) if keep]
    excluded_statuses = [value for value, keep in zip(statuses, mask, strict=True) if not keep]
    accepted_status_labels = [
        value for value, keep in zip(status_labels, mask, strict=True) if keep
    ]
    excluded_status_labels = [
        value for value, keep in zip(status_labels, mask, strict=True) if not keep
    ]
    report = {
        "annotation_rows": int(table.num_rows),
        "accepted_annotation_rows": int(accepted_rows.size),
        "accepted_unique_ids": int(accepted_ids.size),
        "duplicate_accepted_annotation_rows": duplicate_rows,
        "excluded_annotation_rows_null_superclass": int(table.num_rows - accepted_rows.size),
        "accepted_status_inventory": _inventory(accepted_statuses),
        "excluded_status_inventory": _inventory(excluded_statuses),
        "accepted_status_label_inventory": _inventory(accepted_status_labels),
        "excluded_status_label_inventory": _inventory(excluded_status_labels),
        "observed_superclass_inventory": _inventory(classes),
    }
    return accepted_ids, report


def _load_explicit_ids(
    path: Path, selection: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any]]:
    """Validate an exact circuit ID list against the pinned accepted population."""

    id_field = selection["biological_id_field"]
    class_field = selection["accepted_when"]["field"]
    required = [id_field, class_field, "type", "somaSide", "status", "statusLabel"]
    try:
        table = feather.read_table(path, columns=required, memory_map=True)
    except (OSError, pa.ArrowException) as exc:
        raise GraphCompileError(f"cannot read explicit selection evidence fields: {exc}") from exc
    annotation_ids = _strict_uint64_array(table[id_field], id_field, positive=True)
    order = np.argsort(annotation_ids, kind="stable")
    sorted_annotation_ids = annotation_ids[order]
    requested = np.asarray(
        [int(value) for value in selection["body_ids_decimal"]], dtype=np.dtype("<u8")
    )
    validate_int32_index_capacity(int(requested.size))
    positions = np.searchsorted(sorted_annotation_ids, requested)
    present = positions < sorted_annotation_ids.size
    if np.any(present):
        present[present] = sorted_annotation_ids[positions[present]] == requested[present]
    missing = [str(int(value)) for value in requested[~present]]
    if missing:
        raise GraphCompileError(f"explicit body IDs are absent from annotations: {missing}")
    selected_rows = order[positions]
    if sorted_annotation_ids.size > 1:
        duplicated_annotation_ids = set(
            int(value)
            for value in sorted_annotation_ids[1:][
                sorted_annotation_ids[1:] == sorted_annotation_ids[:-1]
            ]
        )
    else:
        duplicated_annotation_ids = set()
    selected_duplicates = sorted(
        duplicated_annotation_ids.intersection(int(value) for value in requested)
    )
    if selected_duplicates:
        raise GraphCompileError(
            "explicit body IDs have duplicate annotation rows: "
            + repr([str(value) for value in selected_duplicates])
        )
    classes = table[class_field].to_pylist()
    rejected = [
        str(int(requested[index]))
        for index, row in enumerate(selected_rows)
        if classes[int(row)] is None
    ]
    if rejected:
        raise GraphCompileError(
            "explicit body IDs are outside the accepted non-null-superclass population: "
            + repr(rejected)
        )
    types = table["type"].to_pylist()
    sides = table["somaSide"].to_pylist()
    statuses = table["status"].to_pylist()
    status_labels = table["statusLabel"].to_pylist()
    rows = [int(row) for row in selected_rows]
    report = {
        "selection_mode": "explicit_body_ids",
        "annotation_rows": int(table.num_rows),
        "requested_body_ids": int(requested.size),
        "accepted_annotation_rows": int(requested.size),
        "accepted_unique_ids": int(requested.size),
        "duplicate_requested_ids": 0,
        "missing_requested_ids": 0,
        "requested_ids_outside_accepted_population": 0,
        "selected_type_inventory": _inventory([types[row] for row in rows]),
        "selected_soma_side_inventory": _inventory([sides[row] for row in rows]),
        "selected_status_inventory": _inventory([statuses[row] for row in rows]),
        "selected_status_label_inventory": _inventory(
            [status_labels[row] for row in rows]
        ),
        "accepted_population_rule": selection["accepted_when"],
    }
    return requested, report


def _load_accepted_ids(
    path: Path, selection: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any]]:
    mode = selection.get("mode", "annotation_rule")
    if mode == "annotation_rule":
        return _load_annotation_rule_ids(path, selection)
    if mode == "explicit_body_ids":
        return _load_explicit_ids(path, selection)
    raise GraphCompileError(f"unsupported selection mode {mode!r}")


def _map_ids(ordered_ids: np.ndarray, endpoints: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    positions = np.searchsorted(ordered_ids, endpoints)
    accepted = positions < ordered_ids.size
    matching = np.zeros(endpoints.shape, dtype=np.bool_)
    if np.any(accepted):
        valid_positions = positions[accepted]
        matching[accepted] = ordered_ids[valid_positions] == endpoints[accepted]
    return positions, matching


def _save_array(path: Path, values: np.ndarray, dtype: str) -> None:
    array = np.asarray(values, dtype=np.dtype(dtype), order="C")
    np.save(path, array, allow_pickle=False)


def _load_transmitter_arrays(
    path: Path,
    accepted_ids: np.ndarray,
    transform: dict[str, Any],
    staging: Path,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    source_fields = {
        "body": "body",
        "total": "total_nt_predictions",
        "confidence": "predicted_nt_confidence",
        "predicted": "predicted_nt",
        "ground_truth": "ground_truth",
        "consensus": "consensus_nt",
    }
    try:
        table = feather.read_table(
            path, columns=list(source_fields.values()), memory_map=True
        )
    except (OSError, pa.ArrowException) as exc:
        raise GraphCompileError(f"cannot read neurotransmitter source: {exc}") from exc

    source_ids = _strict_uint64_array(table[source_fields["body"]], "body", positive=True)
    order = np.argsort(source_ids, kind="stable")
    sorted_ids = source_ids[order]
    if sorted_ids.size > 1 and np.any(sorted_ids[1:] == sorted_ids[:-1]):
        raise GraphCompileError("neurotransmitter table contains duplicate body IDs")
    positions = np.searchsorted(sorted_ids, accepted_ids)
    present = positions < sorted_ids.size
    matching = np.zeros(accepted_ids.shape, dtype=np.bool_)
    if np.any(present):
        matching[present] = sorted_ids[positions[present]] == accepted_ids[present]
    present = matching
    accepted_positions = np.flatnonzero(present)
    source_positions = order[positions[present]]
    take_indices = pa.array(source_positions, type=pa.int64())

    labels = transform["labels"]
    label_codes = {label: int(entry["code"]) for label, entry in labels.items()}
    label_signs = {label: int(entry["effective_sign"]) for label, entry in labels.items()}
    size = accepted_ids.size
    record_present = present.astype(np.dtype("<u1"), copy=False)
    predicted_codes = np.zeros(size, dtype=np.dtype("<u1"))
    confidence = np.full(size, np.nan, dtype=np.dtype("<f8"))
    totals = np.zeros(size, dtype=np.dtype("<i4"))
    ground_truth_codes = np.zeros(size, dtype=np.dtype("<u1"))
    consensus_codes = np.zeros(size, dtype=np.dtype("<u1"))
    effective_signs = np.zeros(size, dtype=np.dtype("<i1"))

    def selected_values(field: str) -> list[Any]:
        return pc.take(table[source_fields[field]], take_indices).to_pylist()

    predicted = selected_values("predicted")
    ground_truth = selected_values("ground_truth")
    consensus = selected_values("consensus")

    def encode(values: list[Any], field: str) -> np.ndarray:
        result = np.zeros(len(values), dtype=np.dtype("<u1"))
        unknown = sorted({value for value in values if value is not None and value not in labels})
        if unknown:
            raise GraphCompileError(
                f"unrecognized transmitter label(s) in {field}: {unknown!r}"
            )
        for index, value in enumerate(values):
            if value is not None:
                result[index] = label_codes[value]
        return result

    predicted_codes[accepted_positions] = encode(predicted, "predicted_nt")
    ground_truth_codes[accepted_positions] = encode(ground_truth, "ground_truth")
    consensus_codes[accepted_positions] = encode(consensus, "consensus_nt")
    for target_index, value in zip(accepted_positions, consensus, strict=True):
        if value is not None:
            effective_signs[target_index] = label_signs[value]

    selected_confidence = pc.take(table[source_fields["confidence"]], take_indices)
    if selected_confidence.null_count:
        confidence_values = selected_confidence.to_pylist()
        confidence[accepted_positions] = [
            math.nan if value is None else float(value) for value in confidence_values
        ]
    else:
        confidence[accepted_positions] = selected_confidence.to_numpy(zero_copy_only=False)

    selected_totals = pc.take(table[source_fields["total"]], take_indices)
    if selected_totals.null_count:
        raise GraphCompileError("total_nt_predictions contains null for an accepted body")
    total_values = selected_totals.to_numpy(zero_copy_only=False)
    if total_values.size and (int(total_values.min()) < 0 or int(total_values.max()) > INT32_MAX):
        raise GraphCompileError("total_nt_predictions is outside int32 bounds")
    totals[accepted_positions] = total_values.astype(np.dtype("<i4"), copy=False)

    arrays = {
        "nt_record_present": record_present,
        "predicted_nt_codes": predicted_codes,
        "predicted_nt_confidence": confidence,
        "total_nt_predictions": totals,
        "ground_truth_nt_codes": ground_truth_codes,
        "consensus_nt_codes": consensus_codes,
        "effective_signs": effective_signs,
    }
    for name, values in arrays.items():
        _save_array(staging / ARRAY_FILENAMES[name], values, np.dtype(values.dtype).str)

    missing_count = int(size - accepted_positions.size)
    report = {
        "source_rows": int(table.num_rows),
        "source_unique_body_ids": int(source_ids.size),
        "accepted_ids_with_source_record": int(accepted_positions.size),
        "accepted_ids_missing_source_record": missing_count,
        "predicted_nt_inventory": _inventory(predicted + (["<missing-record>"] * missing_count)),
        "ground_truth_inventory": _inventory(
            ground_truth + (["<missing-record>"] * missing_count)
        ),
        "consensus_nt_inventory": _inventory(consensus + (["<missing-record>"] * missing_count)),
        "effective_sign_inventory": {
            str(sign): int(np.count_nonzero(effective_signs == sign)) for sign in (-1, 0, 1)
        },
        "label_codebook": {
            "0": {"source_label": None, **transform["null_or_missing"]},
            **{
                str(entry["code"]): {"source_label": label, **entry}
                for label, entry in sorted(labels.items(), key=lambda item: item[1]["code"])
            },
        },
    }
    return arrays, report


def _contact_sum(values: np.ndarray) -> int:
    if values.size == 0:
        return 0
    return int(values.sum(dtype=np.uint64))


def _scan_and_sort_edges(
    path: Path,
    accepted_ids: np.ndarray,
    temporary_path: Path,
) -> tuple[np.memmap, dict[str, Any], dict[str, Any]]:
    try:
        memory = pa.memory_map(str(path), "r")
        reader = pa.ipc.open_file(memory)
    except (OSError, pa.ArrowException) as exc:
        raise GraphCompileError(f"cannot open connection source: {exc}") from exc
    expected_fields = ["body_pre", "body_post", "weight"]
    observed_fields = [field.name for field in reader.schema]
    if observed_fields != expected_fields:
        memory.close()
        raise GraphCompileError(
            "connection source must contain exactly body_pre, body_post, weight; "
            f"observed {observed_fields!r}. Additional partition fields would make counting ambiguous."
        )

    record_dtype = np.dtype(
        [("source", "<i4"), ("target", "<i4"), ("count", "<u8")], align=False
    )
    rows_read = 0
    retained_rows = 0
    source_not_accepted = 0
    target_not_accepted = 0
    exclusive_rows = {"source_only": 0, "target_only": 0, "both": 0}
    exclusive_contacts = {"source_only": 0, "target_only": 0, "both": 0}
    all_contacts = 0
    retained_contacts = 0
    maximum_source_count = 0

    try:
        with temporary_path.open("wb") as output:
            for batch_index in range(reader.num_record_batches):
                batch = reader.get_batch(batch_index)
                presynaptic = _strict_uint64_array(
                    batch.column(0), "body_pre", positive=True
                )
                postsynaptic = _strict_uint64_array(
                    batch.column(1), "body_post", positive=True
                )
                counts = _strict_uint64_array(batch.column(2), "weight", positive=False)
                rows_read += int(batch.num_rows)
                if counts.size:
                    maximum_source_count = max(maximum_source_count, int(counts.max()))
                all_contacts += _contact_sum(counts)
                source_indices, source_ok = _map_ids(accepted_ids, presynaptic)
                target_indices, target_ok = _map_ids(accepted_ids, postsynaptic)
                keep = source_ok & target_ok
                source_not_accepted += int(np.count_nonzero(~source_ok))
                target_not_accepted += int(np.count_nonzero(~target_ok))
                source_only = (~source_ok) & target_ok
                target_only = source_ok & (~target_ok)
                both = (~source_ok) & (~target_ok)
                for name, mask in (
                    ("source_only", source_only),
                    ("target_only", target_only),
                    ("both", both),
                ):
                    exclusive_rows[name] += int(np.count_nonzero(mask))
                    exclusive_contacts[name] += _contact_sum(counts[mask])
                kept_count = int(np.count_nonzero(keep))
                retained_rows += kept_count
                retained_contacts += _contact_sum(counts[keep])
                if kept_count:
                    records = np.empty(kept_count, dtype=record_dtype)
                    records["source"] = source_indices[keep].astype(
                        np.dtype("<i4"), copy=False
                    )
                    records["target"] = target_indices[keep].astype(
                        np.dtype("<i4"), copy=False
                    )
                    records["count"] = counts[keep]
                    records.tofile(output)
            output.flush()
            os.fsync(output.fileno())
    finally:
        memory.close()

    expected_bytes = retained_rows * record_dtype.itemsize
    actual_bytes = temporary_path.stat().st_size
    if actual_bytes != expected_bytes:
        raise GraphCompileError(
            f"temporary edge record size mismatch: {actual_bytes} != {expected_bytes}"
        )
    if retained_rows:
        records: np.ndarray = np.memmap(
            temporary_path, mode="r+", dtype=record_dtype, shape=(retained_rows,)
        )
        records.sort(order=("source", "target"), kind="quicksort")
        records.flush()
    else:
        records = np.empty(0, dtype=record_dtype)

    excluded_contacts = all_contacts - retained_contacts
    if excluded_contacts != sum(exclusive_contacts.values()):
        raise GraphCompileError("exclusive contact exclusion accounting does not balance")
    accounting = {
        "source_weight_rows_read": rows_read,
        "rows_source_endpoint_not_accepted": source_not_accepted,
        "rows_target_endpoint_not_accepted": target_not_accepted,
        "rows_both_endpoints_accepted": retained_rows,
        "source_contact_mass_all_rows": all_contacts,
        "source_contact_mass_retained": retained_contacts,
        "source_contact_mass_excluded": excluded_contacts,
        "exclusions": [
            {
                "reason": "source_endpoint_not_accepted_target_accepted",
                "rows": exclusive_rows["source_only"],
                "contact_mass": exclusive_contacts["source_only"],
            },
            {
                "reason": "target_endpoint_not_accepted_source_accepted",
                "rows": exclusive_rows["target_only"],
                "contact_mass": exclusive_contacts["target_only"],
            },
            {
                "reason": "both_endpoints_not_accepted",
                "rows": exclusive_rows["both"],
                "contact_mass": exclusive_contacts["both"],
            },
        ],
    }
    semantics = {
        "observed_fields": observed_fields,
        "roi_partition_columns": [],
        "source_observation": "The pinned table has one body_pre/body_post/count schema and no ROI partition field.",
        "aggregation_rule": "Sum every retained row sharing the same exact biological source-target pair once; this also deterministically handles unexpected duplicate pair rows.",
        "maximum_source_row_count": maximum_source_count,
    }
    return records, accounting, semantics


def _build_sparse_arrays(
    records: np.memmap,
    accepted_ids: np.ndarray,
    effective_signs: np.ndarray,
    gain: float,
    staging: Path,
) -> dict[str, Any]:
    node_count = int(accepted_ids.size)
    validate_int32_index_capacity(node_count)
    raw_rows = int(records.shape[0])
    if raw_rows:
        row_bounds = np.searchsorted(
            records["source"], np.arange(node_count, dtype=np.int32), side="left"
        ).astype(np.dtype("<i8"), copy=False)
    else:
        row_bounds = np.zeros(node_count, dtype=np.dtype("<i8"))
    row_bounds = np.concatenate(
        [row_bounds, np.asarray([raw_rows], dtype=np.dtype("<i8"))]
    )

    unique_degrees = np.zeros(node_count, dtype=np.dtype("<i8"))
    duplicate_pairs = 0
    maximum_aggregated_count = 0
    for source in range(node_count):
        low = int(row_bounds[source])
        high = int(row_bounds[source + 1])
        if high == low:
            continue
        row_targets = records["target"][low:high]
        unique_count = 1 + int(np.count_nonzero(row_targets[1:] != row_targets[:-1]))
        unique_degrees[source] = unique_count
        if unique_count < high - low:
            duplicate_pairs += int(
                np.count_nonzero(
                    np.bincount(
                        np.searchsorted(np.unique(row_targets), row_targets)
                    )
                    > 1
                )
            )

    offsets = np.lib.format.open_memmap(
        staging / ARRAY_FILENAMES["offsets"],
        mode="w+",
        dtype=np.dtype("<i8"),
        shape=(node_count + 1,),
    )
    offsets[0] = 0
    np.cumsum(unique_degrees, dtype=np.int64, out=offsets[1:])
    edge_count = int(offsets[-1])
    targets = np.lib.format.open_memmap(
        staging / ARRAY_FILENAMES["targets"],
        mode="w+",
        dtype=np.dtype("<i4"),
        shape=(edge_count,),
    )
    counts = np.lib.format.open_memmap(
        staging / ARRAY_FILENAMES["counts"],
        mode="w+",
        dtype=np.dtype("<u8"),
        shape=(edge_count,),
    )
    weights = np.lib.format.open_memmap(
        staging / ARRAY_FILENAMES["weights"],
        mode="w+",
        dtype=np.dtype("<f4"),
        shape=(edge_count,),
    )

    pairs_with_multiple_rows = 0
    for source in range(node_count):
        raw_low = int(row_bounds[source])
        raw_high = int(row_bounds[source + 1])
        out_low = int(offsets[source])
        out_high = int(offsets[source + 1])
        if raw_high == raw_low:
            continue
        raw_targets = records["target"][raw_low:raw_high]
        raw_counts = records["count"][raw_low:raw_high]
        starts = np.concatenate(
            [
                np.asarray([0], dtype=np.int64),
                np.flatnonzero(raw_targets[1:] != raw_targets[:-1]) + 1,
            ]
        )
        targets[out_low:out_high] = raw_targets[starts]
        if starts.size == raw_targets.size:
            aggregated = np.asarray(raw_counts, dtype=np.dtype("<u8"))
        else:
            aggregated = np.empty(starts.size, dtype=np.dtype("<u8"))
            ends = np.concatenate([starts[1:], np.asarray([raw_targets.size])])
            for index, (start, end) in enumerate(zip(starts, ends, strict=True)):
                total = sum(int(value) for value in raw_counts[int(start) : int(end)])
                if total > UINT64_MAX:
                    raise GraphCompileError("aggregated source contact count exceeds uint64")
                aggregated[index] = total
                if end - start > 1:
                    pairs_with_multiple_rows += 1
        counts[out_low:out_high] = aggregated
        if aggregated.size:
            maximum_aggregated_count = max(maximum_aggregated_count, int(aggregated.max()))
        row_weights = aggregated.astype(np.float32) * np.float32(
            int(effective_signs[source]) * gain
        )
        if not np.all(np.isfinite(row_weights)):
            raise GraphCompileError("float32 executable weight overflowed or became non-finite")
        weights[out_low:out_high] = row_weights

    _save_array(staging / ARRAY_FILENAMES["ids"], accepted_ids, "<u8")
    offsets.flush()
    targets.flush()
    counts.flush()
    weights.flush()

    represented_contacts = _contact_sum(np.asarray(counts))
    nonzero_edges = int(np.count_nonzero(weights))
    zero_edges = edge_count - nonzero_edges
    disabled_contacts = _contact_sum(np.asarray(counts)[np.asarray(weights) == 0])
    indegree = np.bincount(np.asarray(targets), minlength=node_count)
    outdegree = np.diff(np.asarray(offsets))
    isolated = int(np.count_nonzero((indegree == 0) & (outdegree == 0)))
    if raw_rows - edge_count != sum(
        max(0, int(row_bounds[index + 1] - row_bounds[index] - unique_degrees[index]))
        for index in range(node_count)
    ):
        raise GraphCompileError("duplicate aggregation accounting does not balance")
    if duplicate_pairs != pairs_with_multiple_rows:
        raise GraphCompileError("duplicate pair accounting differs between compiler passes")
    return {
        "N": node_count,
        "source_accepted_E": edge_count,
        "executable_nonzero_E": nonzero_edges,
        "zero_disabled_E": zero_edges,
        "represented_source_contacts": represented_contacts,
        "disabled_zero_weight_contact_mass": disabled_contacts,
        "isolated_accepted_neurons": isolated,
        "retained_input_rows": raw_rows,
        "duplicate_input_rows_aggregated": raw_rows - edge_count,
        "pairs_with_multiple_input_rows": pairs_with_multiple_rows,
        "maximum_aggregated_count": maximum_aggregated_count,
    }


def _array_inventory(directory: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, filename in ARRAY_FILENAMES.items():
        path = directory / filename
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        size, digest = sha256_file(path)
        result[name] = {
            "filename": filename,
            "dtype": array.dtype.name,
            "shape": list(array.shape),
            "bytes": size,
            "sha256": digest,
            "read_only_mmap_supported": bool(not array.flags.writeable),
            "semantic_digest_member": name in SEMANTIC_ARRAYS,
        }
    return result


def semantic_graph_digest(
    directory: Path, selection_semantic_sha256: str, transform_sha256: str
) -> str:
    """Hash canonical array values and profile identities, not .npy headers or paths."""

    digest = hashlib.sha256()
    digest.update(SEMANTIC_DIGEST_DOMAIN)
    descriptor = {
        "array_order": list(SEMANTIC_ARRAYS),
        "canonical_byte_order": "little-endian",
        "canonical_dtypes": {name: EXPECTED_DTYPES[name] for name in SEMANTIC_ARRAYS},
        "orientation": "A[source,target]; propagation A.T @ spike_vector",
        "accepted_node_selection_semantic_sha256": selection_semantic_sha256,
        "compile_transform_profile_sha256": transform_sha256,
    }
    digest.update(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest.update(b"\0")
    for name in SEMANTIC_ARRAYS:
        array = np.load(directory / ARRAY_FILENAMES[name], mmap_mode="r", allow_pickle=False)
        expected = np.dtype(EXPECTED_DTYPES[name]).newbyteorder("<")
        if array.dtype != expected:
            raise GraphAuditError(
                f"semantic array {name} dtype {array.dtype} != canonical {expected}"
            )
        header = {
            "name": name,
            "dtype": expected.str,
            "shape": list(array.shape),
        }
        digest.update(json.dumps(header, sort_keys=True, separators=(",", ":")).encode())
        digest.update(b"\0")
        flat = array.reshape(-1)
        elements_per_chunk = max(1, (8 * 1024 * 1024) // max(1, array.dtype.itemsize))
        for start in range(0, flat.size, elements_per_chunk):
            digest.update(flat[start : start + elements_per_chunk].tobytes(order="C"))
    return digest.hexdigest()


def _install_staging(staging: Path, output: Path) -> None:
    backup = output.with_name(f".{output.name}.backup-{uuid.uuid4().hex}")
    moved_old = False
    try:
        if output.exists():
            os.replace(output, backup)
            moved_old = True
        os.replace(staging, output)
        if moved_old:
            shutil.rmtree(backup)
    except OSError:
        if not output.exists() and moved_old and backup.exists():
            os.replace(backup, output)
        raise


def compile_graph(
    lock_path: Path,
    selection_path: Path,
    output_dir: Path,
    *,
    source_dir: Path | None = None,
    enforce_official: bool = True,
    command: list[str] | None = None,
) -> dict[str, Any]:
    """Compile pinned Arrow sources into deterministic source-major .npy arrays."""

    started_at = utc_now()
    started = time.monotonic()
    lock_path = lock_path.resolve()
    selection_path = selection_path.resolve()
    output_dir = output_dir.resolve()
    source_dir = (
        source_dir.resolve()
        if source_dir is not None
        else lock_path.parent.parent.joinpath("data", "raw").resolve()
    )
    if output_dir == output_dir.parent:
        raise GraphCompileError("refusing to compile into a filesystem root")
    lock, source_lock_digest = load_source_lock(
        lock_path, enforce_official=enforce_official
    )
    selection_profile, selection_bytes, selection_digest = _read_json(
        selection_path, "accepted-neuron selection profile"
    )
    selection = _validate_selection_profile(selection_profile, source_lock_digest)
    selection_semantic_digest = _selection_semantic_digest(selection_profile)
    transform_ref = selection_profile["compile_transform"]
    transform_path = (selection_path.parent / transform_ref["path"]).resolve()
    transform_profile, transform_bytes, transform_digest = _read_json(
        transform_path, "compile-transform profile"
    )
    if transform_profile.get("profile_id") != transform_ref.get("profile_id"):
        raise GraphCompileError("selection profile references a different transform identity")
    transform = _validate_transform_profile(transform_profile)
    source_paths, source_identities = _verify_source_files(lock, source_dir)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.with_name(f".{output_dir.name}.staging-{uuid.uuid4().hex}")
    staging.mkdir()
    temporary_edges = staging / ".retained-edge-records.bin"
    try:
        accepted_ids, selection_report = _load_accepted_ids(
            source_paths["curated_annotations"], selection
        )
        transmitter_arrays, transmitter_report = _load_transmitter_arrays(
            source_paths["aggregate_neurotransmitters"],
            accepted_ids,
            transform,
            staging,
        )
        records, edge_accounting, connection_semantics = _scan_and_sort_edges(
            source_paths["connection_weights"], accepted_ids, temporary_edges
        )
        temporary_bytes = temporary_edges.stat().st_size
        graph = _build_sparse_arrays(
            records,
            accepted_ids,
            transmitter_arrays["effective_signs"],
            float(transform["global_gain"]),
            staging,
        )
        del records
        temporary_edges.unlink()
        if graph["represented_source_contacts"] != edge_accounting[
            "source_contact_mass_retained"
        ]:
            raise GraphCompileError("retained contact mass changed during aggregation")

        (staging / "source-lock.json").write_bytes(lock_path.read_bytes())
        (staging / "selection-profile.json").write_bytes(selection_bytes)
        (staging / "compile-transform-profile.json").write_bytes(transform_bytes)
        arrays = _array_inventory(staging)
        semantic_digest = semantic_graph_digest(
            staging, selection_semantic_digest, transform_digest
        )
        completed_at = utc_now()
        duration = time.monotonic() - started
        peak_rss_bytes = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
        compiler_path = Path(__file__).resolve()
        repository_root = lock_path.parent.parent
        build_resource = {
            "schema_version": 1,
            "classification": "M03 build-resource evidence; not runtime session memory",
            "command": command,
            "started_at_utc": started_at,
            "completed_at_utc": completed_at,
            "duration_seconds": round(duration, 6),
            "peak_process_rss_bytes": peak_rss_bytes,
            "peak_process_rss_method": "resource.getrusage(resource.RUSAGE_SELF).ru_maxrss on Linux, reported KiB and converted to bytes",
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "logical_cpu_count": os.cpu_count(),
            },
            "input_source_bytes": {
                entry["role"]: entry["bytes"] for entry in source_identities
            },
            "output_array_bytes": {
                name: entry["bytes"] for name, entry in arrays.items()
            },
            "output_array_total_bytes": sum(entry["bytes"] for entry in arrays.values()),
            "maximum_material_temporary_bytes": temporary_bytes,
            "temporary_artifact": "retained structured source/target/count records; removed after successful array generation",
        }
        write_json(staging / "build-resource.json", build_resource)
        compiler_identity = {
            "compiler_id": COMPILER_ID,
            "module": "flybench.graph",
            "module_sha256": hashlib.sha256(compiler_path.read_bytes()).hexdigest(),
            "code_git_sha": _git_head(repository_root),
        }
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "version": MANIFEST_VERSION,
            "compiler": compiler_identity,
            "source_lock_sha256": source_lock_digest,
            "source_files": source_identities,
            "selection_profile": {
                "profile_id": selection_profile.get("profile_id"),
                "sha256": selection_digest,
                "semantic_sha256": selection_semantic_digest,
                "copied_filename": "selection-profile.json",
                "rule": selection["rule"],
            },
            "compile_transform_profile": {
                "profile_id": transform_profile.get("profile_id"),
                "sha256": transform_digest,
                "copied_filename": "compile-transform-profile.json",
                "classification": "MODEL ASSUMPTION",
                "global_gain": transform["global_gain"],
                "normalization": transform["normalization"],
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
                "binds": [
                    "ordered biological IDs",
                    "source-major offsets and targets",
                    "raw aggregated counts",
                    "executable float32 weights",
                    "accepted-node selection semantic SHA-256",
                    "compile-transform profile SHA-256",
                ],
                "excludes": [
                    "filesystem paths",
                    "timestamps",
                    "temporary filenames",
                    "memory addresses",
                    ".npy container headers",
                ],
            },
            "graph": graph,
            "selection_accounting": selection_report,
            "transmitter_accounting": transmitter_report,
            "endpoint_and_contact_accounting": edge_accounting,
            "connection_table_semantics": connection_semantics,
            "arrays": arrays,
            "build_resource": build_resource,
            "operational_metadata": {
                "started_at_utc": started_at,
                "completed_at_utc": completed_at,
            },
        }
        write_json(staging / "manifest.json", manifest)
        _install_staging(staging, output_dir)
        return manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _audit_profile_copy(
    graph_dir: Path, manifest_entry: dict[str, Any], expected_filename: str
) -> dict[str, Any]:
    filename = manifest_entry.get("copied_filename")
    if filename != expected_filename:
        raise GraphAuditError(f"unexpected copied profile filename {filename!r}")
    path = graph_dir / filename
    size, digest = sha256_file(path)
    if digest != manifest_entry.get("sha256"):
        raise GraphAuditError(f"copied profile digest mismatch for {filename}")
    return {"filename": filename, "bytes": size, "sha256": digest}


def audit_graph(
    graph_dir: Path,
    output_path: Path | None = None,
    *,
    command: list[str] | None = None,
    write_companion_evidence: bool = False,
) -> dict[str, Any]:
    """Independently reopen and validate generated graph artifacts."""

    started_at = utc_now()
    started = time.monotonic()
    graph_dir = graph_dir.resolve()
    try:
        manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphAuditError(f"cannot read compiled manifest: {exc}") from exc
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("version") != 1:
        raise GraphAuditError("unsupported compiled graph manifest")
    manifest_arrays = manifest.get("arrays")
    if not isinstance(manifest_arrays, dict) or set(manifest_arrays) != set(ARRAY_FILENAMES):
        raise GraphAuditError("manifest array inventory is incomplete")

    arrays: dict[str, np.ndarray] = {}
    audited_inventory: dict[str, dict[str, Any]] = {}
    for name, filename in ARRAY_FILENAMES.items():
        entry = manifest_arrays[name]
        if entry.get("filename") != filename or Path(filename).name != filename:
            raise GraphAuditError(f"unsafe or mismatched array filename for {name}")
        path = graph_dir / filename
        try:
            array = np.load(path, mmap_mode="r", allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise GraphAuditError(f"cannot memory-map {name}: {exc}") from exc
        if array.dtype.name != EXPECTED_DTYPES[name]:
            raise GraphAuditError(
                f"{name} dtype {array.dtype.name} != {EXPECTED_DTYPES[name]}"
            )
        if array.flags.writeable:
            raise GraphAuditError(f"{name} did not open as a read-only memory map")
        size, digest = sha256_file(path)
        observed = {
            "filename": filename,
            "dtype": array.dtype.name,
            "shape": list(array.shape),
            "bytes": size,
            "sha256": digest,
            "read_only_mmap": True,
        }
        for field in ("dtype", "shape", "bytes", "sha256"):
            if observed[field] != entry.get(field):
                raise GraphAuditError(f"{name} {field} differs from manifest")
        arrays[name] = array
        audited_inventory[name] = observed

    ids = arrays["ids"]
    offsets = arrays["offsets"]
    targets = arrays["targets"]
    counts = arrays["counts"]
    weights = arrays["weights"]
    node_count = int(ids.shape[0])
    if ids.ndim != 1 or offsets.shape != (node_count + 1,):
        raise GraphAuditError("ID/offset shapes do not define a source-major graph")
    if node_count < 1 or (node_count > 1 and np.any(ids[1:] <= ids[:-1])):
        raise GraphAuditError("biological IDs are not unique and strictly increasing")
    if offsets[0] != 0 or np.any(offsets[1:] < offsets[:-1]):
        raise GraphAuditError("offsets are not monotonic from zero")
    edge_count = int(offsets[-1])
    if targets.shape != (edge_count,) or counts.shape != (edge_count,) or weights.shape != (
        edge_count,
    ):
        raise GraphAuditError("edge-array shapes do not match final offset")
    if edge_count and (int(targets.min()) < 0 or int(targets.max()) >= node_count):
        raise GraphAuditError("target index lies outside [0, N)")
    if not np.all(np.isfinite(weights)):
        raise GraphAuditError("executable weights contain non-finite values")
    for name in (
        "nt_record_present",
        "predicted_nt_codes",
        "predicted_nt_confidence",
        "total_nt_predictions",
        "ground_truth_nt_codes",
        "consensus_nt_codes",
        "effective_signs",
    ):
        if arrays[name].shape != (node_count,):
            raise GraphAuditError(f"{name} is not node-aligned")

    gain = manifest["compile_transform_profile"].get("global_gain")
    if gain != 1.0 or manifest["compile_transform_profile"].get("normalization") != "none":
        raise GraphAuditError("manifest transform is not the M03 unit/no-normalization profile")
    signs = arrays["effective_signs"]
    target_order_ok = True
    executable_weight_ok = True
    for source in range(node_count):
        low = int(offsets[source])
        high = int(offsets[source + 1])
        if high - low > 1 and np.any(targets[low + 1 : high] <= targets[low : high - 1]):
            target_order_ok = False
            break
        expected_weights = counts[low:high].astype(np.float32) * np.float32(
            int(signs[source]) * gain
        )
        if not np.array_equal(weights[low:high], expected_weights):
            executable_weight_ok = False
            break
    if not target_order_ok:
        raise GraphAuditError("targets are not strictly ordered within source rows")
    if not executable_weight_ok:
        raise GraphAuditError("weights do not equal count * presynaptic sign * unit gain")

    represented_contacts = _contact_sum(np.asarray(counts))
    nonzero_edges = int(np.count_nonzero(weights))
    disabled_contacts = _contact_sum(np.asarray(counts)[np.asarray(weights) == 0])
    indegree = np.bincount(np.asarray(targets), minlength=node_count)
    outdegree = np.diff(np.asarray(offsets))
    isolated = int(np.count_nonzero((indegree == 0) & (outdegree == 0)))
    observed_graph = {
        "N": node_count,
        "source_accepted_E": edge_count,
        "executable_nonzero_E": nonzero_edges,
        "zero_disabled_E": edge_count - nonzero_edges,
        "represented_source_contacts": represented_contacts,
        "disabled_zero_weight_contact_mass": disabled_contacts,
        "isolated_accepted_neurons": isolated,
    }
    for key, value in observed_graph.items():
        if manifest["graph"].get(key) != value:
            raise GraphAuditError(f"audited graph value {key} differs from manifest")

    selection_copy = _audit_profile_copy(
        graph_dir, manifest["selection_profile"], "selection-profile.json"
    )
    try:
        copied_selection = json.loads(
            (graph_dir / "selection-profile.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphAuditError(f"copied selection profile is invalid: {exc}") from exc
    selection_semantic_digest = _selection_semantic_digest(copied_selection)
    if selection_semantic_digest != manifest["selection_profile"].get("semantic_sha256"):
        raise GraphAuditError("copied selection semantic identity differs from manifest")
    transform_copy = _audit_profile_copy(
        graph_dir,
        manifest["compile_transform_profile"],
        "compile-transform-profile.json",
    )
    source_lock_path = graph_dir / "source-lock.json"
    source_lock_size, source_lock_digest = sha256_file(source_lock_path)
    if source_lock_digest != manifest.get("source_lock_sha256"):
        raise GraphAuditError("copied source-lock digest differs from manifest")
    try:
        copied_lock = json.loads(source_lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphAuditError(f"copied source lock is invalid: {exc}") from exc
    copied_sources = {
        entry["role"]: (
            entry["filename"],
            entry["observed_bytes"],
            entry["observed_sha256"],
            entry.get("upstream_sha256"),
        )
        for entry in copied_lock.get("files", [])
    }
    manifested_sources = {
        entry["role"]: (
            entry["filename"],
            entry["bytes"],
            entry["observed_sha256"],
            entry.get("upstream_sha256"),
        )
        for entry in manifest.get("source_files", [])
    }
    if copied_sources != manifested_sources:
        raise GraphAuditError("manifest source identities differ from copied source lock")

    semantic_digest = semantic_graph_digest(
        graph_dir, selection_semantic_digest, transform_copy["sha256"]
    )
    if semantic_digest != manifest["semantic_digest"].get("value"):
        raise GraphAuditError("recomputed semantic graph digest differs from manifest")

    report = {
        "schema": AUDIT_SCHEMA,
        "version": AUDIT_VERSION,
        "status": "PASS",
        "command": command,
        "graph_directory": str(graph_dir),
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "duration_seconds": round(time.monotonic() - started, 6),
        "compiler": manifest["compiler"],
        "source_lock": {
            "filename": "source-lock.json",
            "bytes": source_lock_size,
            "sha256": source_lock_digest,
            "source_files": manifest["source_files"],
        },
        "selection_profile": selection_copy | {
            "profile_id": manifest["selection_profile"].get("profile_id"),
            "semantic_sha256": selection_semantic_digest,
        },
        "compile_transform_profile": transform_copy
        | {
            "profile_id": manifest["compile_transform_profile"].get("profile_id"),
            "classification": "MODEL ASSUMPTION",
            "global_gain": gain,
            "normalization": "none",
        },
        "semantic_graph_digest": semantic_digest,
        "graph": observed_graph,
        "selection_accounting": manifest["selection_accounting"],
        "transmitter_accounting": manifest["transmitter_accounting"],
        "endpoint_and_contact_accounting": manifest["endpoint_and_contact_accounting"],
        "connection_table_semantics": manifest["connection_table_semantics"],
        "arrays": audited_inventory,
        "build_resource": manifest["build_resource"],
        "checks": {
            "ids_unique_strictly_increasing": "PASS",
            "offsets_monotonic_from_zero": "PASS",
            "final_offset_equals_source_accepted_E": "PASS",
            "targets_in_range": "PASS",
            "counts_nonnegative_uint64": "PASS",
            "contact_total_recomputed": "PASS",
            "weights_float32_finite": "PASS",
            "targets_strictly_sorted_within_source": "PASS",
            "orientation_source_major": "PASS",
            "weights_recomputed_from_counts_and_presynaptic_sign": "PASS",
            "isolated_nodes_recomputed": "PASS",
            "array_shapes_dtypes_hashes": "PASS",
            "semantic_digest_recomputed": "PASS",
            "profile_identities_recomputed": "PASS",
            "source_identity_matches_copied_lock": "PASS",
        },
    }
    if output_path is not None:
        output_path = output_path.resolve()
        write_json(output_path, report)
        if write_companion_evidence:
            generation = manifest["build_resource"].get("command")
            array_inventory = {
                "schema_version": 1,
                "semantic_graph_digest": semantic_digest,
                "generation_command": generation,
                "source_lock_sha256": source_lock_digest,
                "selection_profile_sha256": selection_copy["sha256"],
                "selection_semantic_sha256": selection_semantic_digest,
                "compile_transform_profile_sha256": transform_copy["sha256"],
                "arrays": audited_inventory,
            }
            write_json(output_path.parent / "array-inventory.json", array_inventory)
            write_json(output_path.parent / "compiled-manifest.json", manifest)
            resource_receipt = dict(manifest["build_resource"])
            resource_receipt.update(
                {
                    "semantic_graph_digest": semantic_digest,
                    "source_lock_sha256": source_lock_digest,
                    "selection_profile_sha256": selection_copy["sha256"],
                    "selection_semantic_sha256": selection_semantic_digest,
                    "compile_transform_profile_sha256": transform_copy["sha256"],
                    "compiler": manifest["compiler"],
                }
            )
            write_json(output_path.parent / "resource-receipt.json", resource_receipt)
            write_json(
                output_path.parent / "exclusion-accounting.json",
                {
                    "schema_version": 1,
                    "semantic_graph_digest": semantic_digest,
                    "selection": manifest["selection_accounting"],
                    "endpoints_and_contacts": manifest[
                        "endpoint_and_contact_accounting"
                    ],
                    "connection_table_semantics": manifest[
                        "connection_table_semantics"
                    ],
                },
            )
    return report


def compare_compiled_graphs(first_dir: Path, second_dir: Path) -> dict[str, Any]:
    first = json.loads((first_dir / "manifest.json").read_text(encoding="utf-8"))
    second = json.loads((second_dir / "manifest.json").read_text(encoding="utf-8"))
    comparison_fields = {
        "semantic_graph_digest": (
            first["semantic_digest"]["value"],
            second["semantic_digest"]["value"],
        ),
        "graph": (first["graph"], second["graph"]),
        "source_lock_sha256": (
            first["source_lock_sha256"],
            second["source_lock_sha256"],
        ),
        "selection_profile_byte_identity": (
            first["selection_profile"]["sha256"],
            second["selection_profile"]["sha256"],
        ),
        "selection_semantic_identity": (
            first["selection_profile"]["semantic_sha256"],
            second["selection_profile"]["semantic_sha256"],
        ),
        "compile_transform_profile_sha256": (
            first["compile_transform_profile"]["sha256"],
            second["compile_transform_profile"]["sha256"],
        ),
        "compiler_identity": (
            first["compiler"],
            second["compiler"],
        ),
        "array_semantic_contents": (
            {
                name: {
                    "sha256": first["arrays"][name]["sha256"],
                    "dtype": first["arrays"][name]["dtype"],
                    "shape": first["arrays"][name]["shape"],
                }
                for name in sorted(first["arrays"])
            },
            {
                name: {
                    "sha256": second["arrays"][name]["sha256"],
                    "dtype": second["arrays"][name]["dtype"],
                    "shape": second["arrays"][name]["shape"],
                }
                for name in sorted(second["arrays"])
            },
        ),
    }
    checks = {
        name: "PASS" if left == right else "FAIL"
        for name, (left, right) in comparison_fields.items()
    }
    return {
        "schema_version": 1,
        "status": "PASS" if all(value == "PASS" for value in checks.values()) else "FAIL",
        "first_directory": str(first_dir.resolve()),
        "second_directory": str(second_dir.resolve()),
        "first_semantic_graph_digest": first["semantic_digest"]["value"],
        "second_semantic_graph_digest": second["semantic_digest"]["value"],
        "checks": checks,
        "compared": {
            "graph": first["graph"],
            "selection_profile_sha256": first["selection_profile"]["sha256"],
            "selection_semantic_sha256": first["selection_profile"][
                "semantic_sha256"
            ],
            "compile_transform_profile_sha256": first["compile_transform_profile"][
                "sha256"
            ],
            "array_semantic_contents": comparison_fields["array_semantic_contents"][0],
        },
        "incidental_manifest_fields_excluded": [
            "operational timestamps",
            "build duration",
            "peak process RSS",
            "output directory path",
        ],
    }
