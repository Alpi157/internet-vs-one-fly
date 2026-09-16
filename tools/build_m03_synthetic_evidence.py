#!/usr/bin/env python3
"""Build and verify the committed exact M03 fixture for compact review evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather

from flybench.data import OFFICIAL_PAGE
from flybench.graph import audit_graph, compile_graph, write_json


FILENAMES = {
    "curated_annotations": "annotations.fixture.feather",
    "aggregate_neurotransmitters": "transmitters.fixture.feather",
    "connection_weights": "connections.fixture.feather",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path, fixture_path: Path, out: Path) -> dict:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if out.exists():
        shutil.rmtree(out)
    inputs = out / "input"
    profiles = out / "profiles"
    compiled = out / "compiled"
    inputs.mkdir(parents=True)
    profiles.mkdir()

    annotations = fixture["accepted_annotation_rows"]
    transmitters = fixture["transmitter_rows"]
    connections = fixture["connection_rows"]
    tables = {
        "curated_annotations": pa.table(
            {
                "bodyId": [row["bodyId"] for row in annotations],
                "superclass": [row["superclass"] for row in annotations],
                "status": [row["status"] for row in annotations],
                "statusLabel": [row["statusLabel"] for row in annotations],
            }
        ),
        "aggregate_neurotransmitters": pa.table(
            {
                "body": [row["body"] for row in transmitters],
                "total_nt_predictions": pa.array(
                    [row["total_nt_predictions"] for row in transmitters], type=pa.int32()
                ),
                "predicted_nt_confidence": [
                    row["predicted_nt_confidence"] for row in transmitters
                ],
                "predicted_nt": [row["predicted_nt"] for row in transmitters],
                "ground_truth": [row["ground_truth"] for row in transmitters],
                "consensus_nt": [row["consensus_nt"] for row in transmitters],
            }
        ),
        "connection_weights": pa.table(
            {
                "body_pre": [row["body_pre"] for row in connections],
                "body_post": [row["body_post"] for row in connections],
                "weight": [row["weight"] for row in connections],
            }
        ),
    }
    source_paths: dict[str, Path] = {}
    for role, table in tables.items():
        path = inputs / FILENAMES[role]
        feather.write_feather(table, path)
        source_paths[role] = path

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
        path = source_paths[role]
        lock["files"].append(
            {
                "role": role,
                "filename": path.name,
                "official_url": f"https://example.invalid/{path.name}",
                "download_max_bytes": 10_000_000,
                "expected_format": "Apache Arrow Feather fixture",
                "upstream_sha256": None,
                "upstream_sha256_provenance": "synthetic fixture",
                "observed_bytes": path.stat().st_size,
                "observed_sha256": sha256(path),
                "observed_sha256_provenance": "synthetic fixture byte identity",
            }
        )
    lock_path = profiles / "source-lock.json"
    write_json(lock_path, lock)
    transform_path = profiles / "compile-transform-v1.json"
    transform_path.write_bytes(
        (root / "profiles" / "compile-transform-v1.json").read_bytes()
    )
    selection = json.loads(
        (root / "profiles" / "accepted-neurons.json").read_text(encoding="utf-8")
    )
    selection["profile_id"] = "flybench.accepted-neurons.synthetic-exact.v1"
    selection["source_lock_sha256"] = sha256(lock_path)
    selection["source_semantics"]["basis"] = (
        "Synthetic fixture using the same explicit non-null superclass rule."
    )
    selection["source_semantics"]["reference"] = fixture_path.relative_to(root).as_posix()
    selection_path = profiles / "accepted-neurons.json"
    write_json(selection_path, selection)

    compile_command = [
        "python",
        "tools/build_m03_synthetic_evidence.py",
        "--fixture",
        fixture_path.relative_to(root).as_posix(),
        "--out",
        out.relative_to(root).as_posix(),
    ]
    manifest = compile_graph(
        lock_path,
        selection_path,
        compiled,
        source_dir=inputs,
        enforce_official=False,
        command=compile_command,
    )
    audit = audit_graph(compiled, out / "audit.json", command=compile_command)
    expected = fixture["expected"]
    observed = {
        "ids": np.load(compiled / "ids.npy", allow_pickle=False).tolist(),
        "offsets": np.load(compiled / "offsets.npy", allow_pickle=False).tolist(),
        "targets": np.load(compiled / "targets.npy", allow_pickle=False).tolist(),
        "counts": np.load(compiled / "counts.npy", allow_pickle=False).tolist(),
        "weights": np.load(compiled / "weights.npy", allow_pickle=False).tolist(),
        "N": manifest["graph"]["N"],
        "source_accepted_E": manifest["graph"]["source_accepted_E"],
        "executable_nonzero_E": manifest["graph"]["executable_nonzero_E"],
        "contacts": manifest["graph"]["represented_source_contacts"],
        "disabled_contact_mass": manifest["graph"][
            "disabled_zero_weight_contact_mass"
        ],
        "isolated_accepted_neurons": manifest["graph"]["isolated_accepted_neurons"],
    }
    checks = {
        key: "PASS" if observed[key] == expected[key] else "FAIL" for key in expected
    }
    result = {
        "schema_version": 1,
        "status": (
            "PASS"
            if audit["status"] == "PASS" and all(value == "PASS" for value in checks.values())
            else "FAIL"
        ),
        "fixture": fixture_path.relative_to(root).as_posix(),
        "expected": expected,
        "observed": observed,
        "checks": checks,
        "semantic_graph_digest": manifest["semantic_digest"]["value"],
        "compiled_arrays": manifest["arrays"],
        "audit_status": audit["status"],
    }
    write_json(out / "synthetic-result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture", type=Path, default=Path("tests/fixtures/m03-exact-graph.json")
    )
    parser.add_argument("--out", type=Path, default=Path("evidence/M03/synthetic"))
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    fixture = args.fixture if args.fixture.is_absolute() else root / args.fixture
    out = args.out if args.out.is_absolute() else root / args.out
    try:
        result = build(root, fixture.resolve(), out.resolve())
    except Exception as exc:
        print(f"synthetic evidence failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
