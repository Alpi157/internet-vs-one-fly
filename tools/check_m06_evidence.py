#!/usr/bin/env python3
"""Check the complete M06 evidence contract without rerunning calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_IDENTITIES = {
    "docs/architecture.md": "bae80837d5d6d769ae5b728af3b80c1caa21b7f08efdd7f3eb458f7bb2eab9d1",
    "profiles/source-lock.json": "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c",
    "profiles/escape-circuit.json": "29a6b4fb98d29f2fbf76fc031bea2f75d7ed534540666fc50279168358f5232b",
    "profiles/encoder-v0.1.json": "f6879937ec2e7efbdb888d336f2041d980f61a8981d7970314a53641bda14bfa",
    "profiles/decoder-v0.1.json": "71acbe641fc2c9ef4f9cee514f99e3dfdc392482d9c77483fc1334fdacb37544",
    "profiles/calibration-plan.json": "b00b9066365b25153ab3c8c56adf866cf1659bc669836345fd1617d9eff0f6d4",
    "profiles/model-v0.1.json": "564c553f750ab9ef275014bbfc67d2b62ed5992fceb80185e09d7966d52b451a",
    "profiles/model-reference-v0.1.json": "3c497fc6c6f6aba051e2c19e3f9bfd7ed4688ed181b5fb4ef5431e8a72548239",
    "profiles/numerical-criteria-v0.1.json": "f49c383d028078c27eeaaa986e75f41b9199ce72d6646f9082b6376b831f8422",
    "src/flybench/reference.py": "ce53a63c8f22256ad1aed36088734f2132cf8c4b1f70fd8a06365f1593587783",
}
EXPECTED_CIRCUIT = "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5"
EXPECTED_MAPPING = "6652462228ddf9af863fae95608fd6cacb44fbd86fd12d0799ec65d8dabcef3d"
EXPECTED_M05_SPEC = "e7bf666f0b9b716d0c6e80af001604b4355ce34ff38e8fa514b90898d6b1dd91"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("evidence/M06"))
    args = parser.parse_args(argv)
    evidence = args.out if args.out.is_absolute() else ROOT / args.out
    try:
        for relative, expected in EXPECTED_IDENTITIES.items():
            require(sha256_file(ROOT / relative) == expected, f"accepted identity changed: {relative}")
        manifest = load(ROOT / "data/compiled/escape/manifest.json")
        full_manifest = load(ROOT / "data/compiled/full/manifest.json")
        require(
            full_manifest["semantic_digest"]["value"]
            == "429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0",
            "accepted full-graph digest changed",
        )
        require(
            manifest["semantic_digest"]["value"] == EXPECTED_CIRCUIT,
            "accepted circuit digest changed",
        )

        decision = load(evidence / "decision.json")
        calibration = load(evidence / "calibration-summary.json")
        authority = load(evidence / "authority.json")
        stability = load(evidence / "stability.json")
        dependencies = load(evidence / "decoder-dependency.json")
        intervention = load(evidence / "intervention.json")
        controller_evidence = load(evidence / "controller-profile.json")
        controller = load(ROOT / "profiles/controller-v0.1.json")
        provenance = load(evidence / "calibration-provenance.json")
        receipt_path = evidence / "manual-authority-review.txt"

        require(decision["gate"] == "G-BIO" and decision["outcome"] == "PASS", "G-BIO does not pass")
        require(decision["allowed_next_milestone"] == "M07", "G-BIO next milestone mismatch")
        require(decision["external_milestone_acceptance"] == "PENDING", "external status is not pending")
        require(calibration["status"] == "PASS", "calibration does not pass")
        require(calibration["primary_combination_count"] == 12, "primary grid is not 12 combinations")
        require(calibration["normal_trial_count"] == 48, "normal panel is not 12 x 4")
        require(len(calibration["combinations"]) == 12, "combination evidence is incomplete")
        require(all(len(item["scenario_trial_ids"]) == 4 for item in calibration["combinations"]), "scenario panels are incomplete")
        require(authority["status"] == "PASS" and authority["selected_attempt"], "authority selection does not pass")
        selected_attempt = authority["selected_attempt"]
        require(all(selected_attempt["checks"].values()), "selected authority checks are incomplete")
        require(
            selected_attempt["normal_vs_output_clamp"]["clamped_escape_command_count"] == 0
            and selected_attempt["normal_vs_output_clamp"]["neural_trace_identical"] is True,
            "output clamp authority evidence failed",
        )
        require(
            selected_attempt["normal_vs_pathway_intervention"]["criterion_status"] == "PASS",
            "pathway authority evidence failed",
        )
        require(stability["status"] == "PASS", "stability/recovery evidence failed")
        require(dependencies["decoder"]["status"] == "PASS", "decoder dependency audit failed")
        require(dependencies["ambient_walking"]["status"] == "PASS", "ambient dependency audit failed")
        require(intervention["mask_audit"]["total_pair_edges"] == 311, "intervention edge count changed")
        require(intervention["mask_audit"]["total_source_contacts"] == 11224, "intervention contacts changed")

        require(receipt_path.is_file() and receipt_path.stat().st_size > 0, "manual authority receipt is absent")
        receipt = decision["manual_authority_review_receipt"]
        require(receipt["status"] == "PRESENT_OPERATOR_SUPPLIED", "manual receipt status is not present")
        require(receipt["bytes"] == receipt_path.stat().st_size, "manual receipt byte count mismatch")
        require(receipt["sha256"] == sha256_file(receipt_path), "manual receipt SHA mismatch")

        require(controller == controller_evidence, "committed controller differs from evidence")
        require(controller["selected_circuit_digest"] == EXPECTED_CIRCUIT, "controller circuit mismatch")
        require(controller["mapping_digest"] == EXPECTED_MAPPING, "controller mapping mismatch")
        require(
            controller["accepted_m05"]["reference_model_spec_semantic_sha256"] == EXPECTED_M05_SPEC,
            "controller accepted M05 identity mismatch",
        )
        require(
            controller["selected_runtime_model_spec_sha256"]
            == authority["selected_attempt"]["normal_vs_pathway_intervention"][
                "normal_response_signature"
            ]
            .get("runtime_model_spec_sha256", controller["selected_runtime_model_spec_sha256"]),
            "controller runtime ModelSpec mismatch",
        )

        protocol_commit = provenance["calibration_protocol_commit"]
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        require(provenance["protocol_execution"] == 2, "valid protocol execution number mismatch")
        require(provenance["repair_decision_id"] == "D-M06-PROTOCOL-01", "repair decision identity mismatch")
        require(
            provenance["superseded_failed_protocol_commit"]
            == "5fb91a10604bcfbfffefb1367fa0ea7ebe8e944f",
            "superseded protocol commit mismatch",
        )
        require(
            provenance["superseded_execution"]["status"] == "INVALID_NOT_RECORDED",
            "failed execution status was not preserved",
        )
        require(
            provenance["superseded_execution"]["evidence_sha256"]
            == sha256_file(evidence / "protocol-defect.json"),
            "preserved protocol-defect evidence changed",
        )
        require(controller["calibration_protocol_commit"] == protocol_commit, "controller protocol commit mismatch")
        require(decision["calibration_protocol_commit"] == protocol_commit, "decision protocol commit mismatch")
        require(provenance["measurement_code_commit"] == head, "evidence was not rerun at submitted code")
        require(provenance["protocol_files_unchanged"] is True, "protocol bytes changed")
        require(provenance["measurement_worktree_clean_at_start"] is True, "measurement tree was dirty")
        for item in provenance["protocol_files"]:
            current = (ROOT / item["path"]).read_bytes()
            committed = subprocess.check_output(
                ["git", "show", f"{protocol_commit}:{item['path']}"], cwd=ROOT
            )
            require(current == committed, f"protocol file changed: {item['path']}")
            require(sha256_file(ROOT / item["path"]) == item["sha256"], f"protocol SHA mismatch: {item['path']}")

        normal_count = 0
        all_trials = []
        with (evidence / "trials.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                trial = json.loads(line)
                all_trials.append(trial)
                normal_count += trial["mode"] == "normal"
                require(trial["graph_circuit_digest"] == EXPECTED_CIRCUIT, "trial circuit mismatch")
                require(trial["mapping_digest"] == EXPECTED_MAPPING, "trial mapping mismatch")
                require(trial["accepted_m05_model_spec_sha256"] == EXPECTED_M05_SPEC, "trial M05 identity mismatch")
        require(normal_count == 48, "trials.jsonl lacks exactly 48 normal trials")
        require(any(item["mode"] == "output_clamp" for item in all_trials), "clamp trial absent")
        require(any(item["mode"] == "direct_visual_to_dnp01_zero" for item in all_trials), "pathway trial absent")
        require((evidence / "authority-review.txt").stat().st_size > 0, "human review document absent")

        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, text=True
        )
        require(status == "", "submitted code worktree is not clean")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"M06 evidence check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": decision["gate"],
                "selected_combination": decision["selected_combination"],
                "calibration_protocol_commit": provenance["calibration_protocol_commit"],
                "submitted_code_sha": head,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
