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
import zipfile


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
    "decisions/D-M06-PROTOCOL-01.json": "9b1114c32a70a309e4d85620e5c19d4413b103d344309a17f954b9a595f045b0",
    "decisions/D-M06-PROTOCOL-02.json": "abac7e02b47cbcf1e691f680c429ed9d1715b5974a35ce0838256c7e8f1ba63c",
}
EXPECTED_CIRCUIT = "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5"
EXPECTED_MAPPING = "6652462228ddf9af863fae95608fd6cacb44fbd86fd12d0799ec65d8dabcef3d"
EXPECTED_M05_SPEC = "e7bf666f0b9b716d0c6e80af001604b4355ce34ff38e8fa514b90898d6b1dd91"
ATTEMPT_1_PROTOCOL_COMMIT = "52da05dfa21d9c637cd34a5f8cfdce71c5c328da"
ATTEMPT_1_SUBMITTED_COMMIT = "69bf4e054d09cbe029a85c45184934cd7707e788"
ATTEMPT_1_REVIEW_ZIP_SHA256 = "7fefa5f755b1c4ce56710a746b351958fb1cf16c9769980f03b89e477c3fd432"
M06_SCALE_CLASSIFICATION = "MODEL ASSUMPTION / project controller parameter"
M06_SCALE_SELECTION_PROVENANCE = "selected by the frozen M06 calibration protocol"


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


def canonical_json_sha256(value: object) -> str:
    """Hash one expanded ModelSpec using the accepted ModelSpec canonical encoding."""

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_trials_jsonl(path: Path) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            trials.append(value)
    return trials


def validate_runtime_model_spec_consistency(
    controller: dict[str, Any],
    authority: dict[str, Any],
    trials_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Bind the controller identity and selected settings to raw authority evidence."""

    selected = authority.get("selected_attempt")
    require(isinstance(selected, dict), "selected authority attempt is absent")
    trial_ids = selected.get("trial_ids")
    require(isinstance(trial_ids, dict), "selected authority trial IDs are absent")
    normal_trial_id = trial_ids.get("normal")
    require(
        isinstance(normal_trial_id, str) and normal_trial_id in trials_by_id,
        "selected normal authority trial is absent from trials.jsonl",
    )
    trial = trials_by_id[normal_trial_id]
    recorded_sha = controller.get("selected_runtime_model_spec_sha256")
    require(
        recorded_sha == trial.get("runtime_model_spec_sha256"),
        "controller runtime ModelSpec SHA differs from selected normal trial evidence",
    )
    require(
        controller.get("selected_runtime_synaptic_scale")
        == trial.get("runtime_synaptic_scale"),
        "controller runtime synaptic scale differs from selected normal trial evidence",
    )
    require(
        controller.get("selected_peak_sensory_external_drive")
        == trial.get("peak_sensory_external_drive"),
        "controller peak sensory drive differs from selected normal trial evidence",
    )
    require(
        selected.get("runtime_synaptic_scale") == trial.get("runtime_synaptic_scale")
        and selected.get("peak_sensory_external_drive")
        == trial.get("peak_sensory_external_drive"),
        "selected authority parameters differ from selected normal trial evidence",
    )

    payload = controller.get("selected_runtime_model_spec")
    if payload is not None:
        require(isinstance(payload, dict), "expanded runtime ModelSpec is not an object")
        require(
            canonical_json_sha256(payload) == recorded_sha,
            "expanded runtime ModelSpec canonical SHA does not match its recorded identity",
        )
        require(
            payload == trial.get("runtime_model_spec"),
            "expanded runtime ModelSpec differs from selected normal trial evidence",
        )

    scale_provenance = controller.get("selected_runtime_synaptic_scale_provenance")
    require(isinstance(scale_provenance, dict), "M06 runtime-scale provenance is absent")
    require(
        scale_provenance.get("runtime_synaptic_scale")
        == controller.get("selected_runtime_synaptic_scale"),
        "M06 runtime-scale provenance value differs from selected controller value",
    )
    require(
        scale_provenance.get("classification") == M06_SCALE_CLASSIFICATION,
        "M06 runtime-scale classification is missing or incorrect",
    )
    require(
        scale_provenance.get("selection_provenance")
        == M06_SCALE_SELECTION_PROVENANCE,
        "M06 runtime-scale provenance does not identify the frozen M06 calibration",
    )
    require(
        scale_provenance.get("physiology_claim") == "none",
        "M06 runtime-scale provenance must disclaim a physiology claim",
    )
    payload_role = controller.get("selected_runtime_model_spec_payload_role")
    require(
        isinstance(payload_role, dict)
        and payload_role.get("classification") == "legacy executable identity metadata"
        and "not the M06 calibration provenance" in payload_role.get("note", ""),
        "legacy ModelSpec payload wording is not distinguished from M06 provenance",
    )
    return trial


def _trial_science(trial: dict[str, Any]) -> dict[str, Any]:
    return {
        "trial_id": trial.get("trial_id"),
        "mode": trial.get("mode"),
        "scenario": trial.get("scenario"),
        "runtime_synaptic_scale": trial.get("runtime_synaptic_scale"),
        "peak_sensory_external_drive": trial.get("peak_sensory_external_drive"),
        "response_signature": trial.get("response_signature"),
        "dnp01_spike_logical_ticks": trial.get("dnp01_spike_logical_ticks"),
        "decoded_command_logical_ticks": trial.get("decoded_command_logical_ticks"),
        "impact_logical_tick": trial.get("impact_logical_tick"),
        "impact_outcome": trial.get("impact_outcome"),
        "finite_state_status": trial.get("finite_state_status"),
        "recovery_status": trial.get("recovery_status"),
        "trial_status": trial.get("trial_status"),
        "interval_neural_state_sha256": [
            interval.get("neural_state_sha256")
            for interval in trial.get("interval_trace", [])
        ],
    }


def _zip_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    value = json.loads(archive.read(name))
    if not isinstance(value, dict):
        raise ValueError(f"attempt-1 archive member {name} is not a JSON object")
    return value


def compare_attempt_1_science(
    *,
    evidence: Path,
    current_trials: list[dict[str, Any]],
    current_calibration: dict[str, Any],
    current_authority: dict[str, Any],
    current_intervention: dict[str, Any],
) -> dict[str, Any]:
    """Compare the rerun's scientific outputs with the immutable attempt-1 archive."""

    archive_path = ROOT / "reviews/M06-a01.zip"
    require(
        sha256_file(archive_path) == ATTEMPT_1_REVIEW_ZIP_SHA256,
        "attempt-1 review ZIP identity changed",
    )
    with zipfile.ZipFile(archive_path) as archive:
        previous_trials = [
            json.loads(line)
            for line in archive.read("evidence/trials.jsonl")
            .decode("utf-8")
            .splitlines()
            if line
        ]
        previous_calibration = _zip_json(archive, "evidence/calibration-summary.json")
        previous_authority = _zip_json(archive, "evidence/authority.json")
        previous_intervention = _zip_json(archive, "evidence/intervention.json")

    mismatches: list[dict[str, Any]] = []

    def compare(name: str, previous: object, current: object) -> None:
        if previous != current:
            mismatches.append({"check": name, "status": "MISMATCH"})

    previous_by_id = {trial["trial_id"]: trial for trial in previous_trials}
    current_by_id = {trial["trial_id"]: trial for trial in current_trials}
    previous_normal = [trial for trial in previous_trials if trial.get("mode") == "normal"]
    current_normal = [trial for trial in current_trials if trial.get("mode") == "normal"]
    compare("total_trial_count", len(previous_trials), len(current_trials))
    compare("normal_trial_count", len(previous_normal), len(current_normal))
    compare("trial_id_order", list(previous_by_id), list(current_by_id))
    compare("trial_id_set", set(previous_by_id), set(current_by_id))
    for trial_id in sorted(set(previous_by_id) | set(current_by_id)):
        compare(
            f"trial:{trial_id}",
            _trial_science(previous_by_id.get(trial_id, {})),
            _trial_science(current_by_id.get(trial_id, {})),
        )

    compare(
        "normal_combinations_and_eligibility",
        previous_calibration.get("combinations"),
        current_calibration.get("combinations"),
    )
    compare(
        "selected_combination",
        previous_calibration.get("selected_combination"),
        current_calibration.get("selected_combination"),
    )
    compare(
        "authority_scientific_result",
        previous_authority,
        current_authority,
    )
    compare(
        "pathway_intervention_scientific_result",
        previous_intervention,
        current_intervention,
    )
    expected_selected = {
        "runtime_synaptic_scale": 0.001,
        "peak_sensory_external_drive": 4.0,
    }
    compare(
        "preserved_selected_combination",
        expected_selected,
        current_calibration.get("selected_combination"),
    )

    exact_shape = (
        len(previous_trials) == 51
        and len(current_trials) == 51
        and len(previous_normal) == 48
        and len(current_normal) == 48
    )
    if not exact_shape:
        mismatches.append({"check": "required_48_normal_plus_3_authority_trials", "status": "MISMATCH"})
    report = {
        "schema_version": 1,
        "comparison_id": "M06-attempt-1-vs-attempt-2-scientific-results",
        "attempt_1": {
            "submitted_commit": ATTEMPT_1_SUBMITTED_COMMIT,
            "valid_calibration_protocol_commit": ATTEMPT_1_PROTOCOL_COMMIT,
            "review_zip_path": "reviews/M06-a01.zip",
            "review_zip_sha256": ATTEMPT_1_REVIEW_ZIP_SHA256,
        },
        "attempt_2": {
            "trial_count": len(current_trials),
            "normal_trial_count": len(current_normal),
            "authority_trial_count": len(current_trials) - len(current_normal),
        },
        "checks": {
            "exactly_48_normal_plus_3_authority_trials": exact_shape,
            "same_trial_ids": list(previous_by_id) == list(current_by_id),
            "same_12_normal_combinations_and_eligibility": (
                previous_calibration.get("combinations")
                == current_calibration.get("combinations")
            ),
            "same_selected_combination": (
                previous_calibration.get("selected_combination")
                == current_calibration.get("selected_combination")
                == expected_selected
            ),
            "same_trial_scientific_outputs": all(
                _trial_science(previous_by_id.get(trial_id, {}))
                == _trial_science(current_by_id.get(trial_id, {}))
                for trial_id in set(previous_by_id) | set(current_by_id)
            ),
            "same_output_clamp_neural_trace_equality": (
                previous_authority.get("selected_attempt", {}).get(
                    "normal_vs_output_clamp"
                )
                == current_authority.get("selected_attempt", {}).get(
                    "normal_vs_output_clamp"
                )
            ),
            "same_pathway_intervention_scientific_result": (
                previous_intervention == current_intervention
            ),
        },
        "compared_scientific_fields": [
            "trial IDs",
            "12 normal combinations and eligibility results",
            "selected combination",
            "response signatures",
            "DNp01 spike events",
            "command ticks",
            "impact timing and outcomes",
            "finite and recovery status",
            "interval neural_state_sha256 values",
            "output-clamp neural-trace equality",
            "pathway-intervention scientific result",
        ],
        "scientific_mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "status": "PASS" if not mismatches else "FAIL",
    }
    (evidence / "review-repair-comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    require(not mismatches, "attempt-1 versus attempt-2 scientific evidence differs")
    return report


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
        review_decision = load(ROOT / "decisions/D-M06-REVIEW-01.json")
        receipt_path = evidence / "manual-authority-review.txt"
        all_trials = load_trials_jsonl(evidence / "trials.jsonl")
        trials_by_id = {trial["trial_id"]: trial for trial in all_trials}
        require(len(trials_by_id) == len(all_trials), "trials.jsonl contains duplicate trial IDs")

        require(decision["gate"] == "G-BIO" and decision["outcome"] == "PASS", "G-BIO does not pass")
        require(
            review_decision.get("decision_id") == "D-M06-REVIEW-01"
            and review_decision.get("scientific_semantics_change_authorized") is False
            and review_decision.get("attempt_1", {}).get("submitted_commit")
            == ATTEMPT_1_SUBMITTED_COMMIT,
            "external-review repair decision is incomplete",
        )
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
        validate_runtime_model_spec_consistency(controller, authority, trials_by_id)

        protocol_commit = provenance["calibration_protocol_commit"]
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        require(provenance["external_review_attempt"] == 2, "external review attempt mismatch")
        require(provenance["protocol_execution"] == 3, "valid protocol execution number mismatch")
        require(
            provenance["repair_decision_ids"]
            == ["D-M06-PROTOCOL-01", "D-M06-PROTOCOL-02"],
            "repair decision identities mismatch",
        )
        require(
            provenance["external_review_decision_ids"] == ["D-M06-REVIEW-01"],
            "external review decision identity mismatch",
        )
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
            provenance["intermediate_mechanical_repair_commit"]
            == "d0ac081bacb476d557608746eabca7141ee49e4e",
            "intermediate repair commit mismatch",
        )
        require(
            provenance["intermediate_commit_calibration_execution"] == "NONE",
            "intermediate commit execution status mismatch",
        )
        require(
            provenance["attempt_1"]
            == {
                "valid_calibration_protocol_commit": ATTEMPT_1_PROTOCOL_COMMIT,
                "submitted_commit": ATTEMPT_1_SUBMITTED_COMMIT,
                "review_zip_path": "reviews/M06-a01.zip",
                "review_zip_sha256": ATTEMPT_1_REVIEW_ZIP_SHA256,
                "protocol_execution": 2,
            },
            "attempt-1 provenance identities mismatch",
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
        for trial in all_trials:
            normal_count += trial["mode"] == "normal"
            require(trial["graph_circuit_digest"] == EXPECTED_CIRCUIT, "trial circuit mismatch")
            require(trial["mapping_digest"] == EXPECTED_MAPPING, "trial mapping mismatch")
            require(trial["accepted_m05_model_spec_sha256"] == EXPECTED_M05_SPEC, "trial M05 identity mismatch")
        require(normal_count == 48, "trials.jsonl lacks exactly 48 normal trials")
        require(len(all_trials) == 51, "trials.jsonl lacks exactly 48 normal plus 3 authority trials")
        require(any(item["mode"] == "output_clamp" for item in all_trials), "clamp trial absent")
        require(any(item["mode"] == "direct_visual_to_dnp01_zero" for item in all_trials), "pathway trial absent")
        require((evidence / "authority-review.txt").stat().st_size > 0, "human review document absent")

        comparison = compare_attempt_1_science(
            evidence=evidence,
            current_trials=all_trials,
            current_calibration=calibration,
            current_authority=authority,
            current_intervention=intervention,
        )
        require(comparison["scientific_mismatch_count"] == 0, "scientific comparison is not exact")
        require(all(comparison["checks"].values()), "scientific comparison checks are incomplete")

        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, text=True
        )
        allowed_bootstrap_status = "?? profiles/controller-v0.1.json\n"
        require(
            status in ("", allowed_bootstrap_status),
            "submitted code worktree is not clean",
        )
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
