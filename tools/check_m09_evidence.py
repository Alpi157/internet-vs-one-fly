#!/usr/bin/env python3
"""Validate M09 attempt-2 evidence without interpreting deferred M08 usability."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from flybench.recording import (
    ARCHITECTURE_SHA256,
    FLYRUN_FORMAT_ID,
    FLYRUN_MEMBERS,
    FLYRUN_SCHEMA_VERSION,
    M08_DEFER_DECISION_ID,
    M08_DEFER_DECISION_PATH,
    M08_DEFER_DECISION_SHA256,
    FlyRunError,
    canonical_applied_input_sha256,
    load_flyrun,
)


ROOT = Path(__file__).resolve().parents[1]
PROCESS_STATUS = {
    "decision": M08_DEFER_DECISION_ID,
    "m09_execution": "AT_RISK",
    "m08_g_game": "PENDING_UNMEASURED",
    "m09_is_m08_usability_evidence": False,
    "public_release_blocked": True,
}
PASS_REPORTS = (
    "recorder-format.json",
    "deterministic-recording.json",
    "applied-input-authority.json",
    "state-digest-policy.json",
    "state-digest-validation.json",
    "bounds.json",
    "archive-safety.json",
    "input-coalescing.json",
    "input-ordering.json",
    "coordinate-application.json",
    "bench-recording.json",
    "demo-recording-smoke.json",
    "headless-server-recorder-parity.json",
)
VALID_FIXTURES = (
    "representative.flyrun",
    "looming-seed-0.flyrun",
    "review-fixtures/valid-complete.flyrun",
    "review-fixtures/valid-optional-truncated.flyrun",
)
MALFORMED_FIXTURES = {
    "review-fixtures/malformed-path-traversal.flyrun": "unsafe flyrun member path",
    "review-fixtures/malformed-executable-member.flyrun": "executable or linked",
    "review-fixtures/malformed-integrity.flyrun": "applied-input identity mismatch",
}
ATTEMPT_1 = {
    "candidate_product_sha": "067b3c831469ce2475201074ad47b39853694b60",
    "submission_sha": "d15bae9ccc6e8bf2952b5d14adaaaf06a86fd3dc",
    "review_zip_sha256": "cff7e065c6a45aade81e23614e0a00d7eb0ed379d5422531e68ba4f629f9ea66",
    "external_verdict": "CHANGES_REQUIRED",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def validate(evidence: Path, *, phase: str) -> dict[str, Any]:
    decision_path = ROOT / M08_DEFER_DECISION_PATH
    if sha256_file(decision_path) != M08_DEFER_DECISION_SHA256:
        raise ValueError("M08 human-gate deferral decision identity mismatch")
    decision = load_json(decision_path)
    if (
        decision.get("classification")
        != "PROCESS DEVIATION — OPERATOR-AUTHORIZED AT-RISK CONTINUATION"
        or decision.get("m08", {}).get("g_game") != "PENDING_UNMEASURED"
        or decision.get("m08", {}).get("milestone_acceptance") != "NOT_ACCEPTED"
        or decision.get("m09", {}).get("permission") != "BEGIN_AT_RISK_ONLY"
    ):
        raise ValueError("process-deviation decision does not preserve the boundary")

    coordinate_path = ROOT / "decisions/D-M09-COORDINATE-APPLICATION-01.json"
    coordinate = load_json(coordinate_path)
    if (
        coordinate.get("decision_id") != "D-M09-COORDINATE-APPLICATION-01"
        or coordinate.get("decision", {}).get("quantization_added") is not False
        or coordinate.get("decision", {}).get("clamping_added") is not False
    ):
        raise ValueError("coordinate application decision is missing or changed")

    ledger = yaml.safe_load((ROOT / "ledger.yaml").read_text(encoding="utf-8"))
    m09_status = ledger.get("milestone_status", {}).get("M09")
    if phase == "current":
        phase = "submission" if m09_status == "SUBMITTED" else "automated"
    if (
        ledger.get("current_milestone") != "M09"
        or ledger.get("current_attempt") != 2
        or ledger.get("milestone_status", {}).get("M08") != "BLOCKED"
        or m09_status not in {"IN_PROGRESS", "SUBMITTED"}
        or ledger.get("last_accepted_milestone") != "M07"
        or ledger.get("accepted_milestones")
        != ["M01", "M02", "M03", "M04", "M05", "M06", "M07"]
        or ledger.get("last_accepted_code_commit")
        != "c2b0dc064fa1f8d50b01f595f0232f8d9b37d5e5"
        or ledger.get("m08_integration_baseline", {}).get("g_game")
        != "PENDING_UNMEASURED"
        or ledger.get("m09_execution", {}).get("status") != "AT_RISK"
        or ledger.get("m09_execution", {}).get("review_attempt") != 2
        or ledger.get("m09_execution", {}).get("recorder_schema")
        != FLYRUN_FORMAT_ID
    ):
        raise ValueError("ledger does not truthfully represent attempt 2 and M08 risk")
    if phase == "submission" and m09_status != "SUBMITTED":
        raise ValueError("submission validation requires M09 SUBMITTED")
    if phase == "automated" and m09_status != "IN_PROGRESS":
        raise ValueError("automated candidate validation requires M09 IN_PROGRESS")

    reports = {name: load_json(evidence / name) for name in PASS_REPORTS}
    for name, value in reports.items():
        if value.get("status") != "PASS":
            raise ValueError(f"M09 evidence report does not pass: {name}")
        if value.get("process_status") != PROCESS_STATUS:
            raise ValueError(f"M09 at-risk disclosure is missing from {name}")
        checks = value.get("checks")
        if isinstance(checks, dict) and not all(checks.values()):
            raise ValueError(f"M09 evidence contains a failing check: {name}")

    superseded = load_json(evidence / "attempt-1-superseded.json")
    if (
        superseded.get("status") != "SUPERSEDED_CHANGES_REQUIRED"
        or superseded.get("candidate_product_sha")
        != ATTEMPT_1["candidate_product_sha"]
        or superseded.get("submission_sha") != ATTEMPT_1["submission_sha"]
        or superseded.get("review_zip_sha256")
        != ATTEMPT_1["review_zip_sha256"]
        or superseded.get("external_verdict") != ATTEMPT_1["external_verdict"]
        or superseded.get("process_status") != PROCESS_STATUS
    ):
        raise ValueError("attempt-1 supersession provenance is incomplete")
    archive_a01 = ROOT / "reviews/M09-a01.zip"
    if not archive_a01.is_file() or sha256_file(archive_a01) != ATTEMPT_1[
        "review_zip_sha256"
    ]:
        raise ValueError("historical M09-a01 review archive is absent or changed")

    loaded = {name: load_flyrun(evidence / name) for name in VALID_FIXTURES}
    representative = loaded["representative.flyrun"]
    looming = loaded["looming-seed-0.flyrun"]
    truncated = loaded["review-fixtures/valid-optional-truncated.flyrun"]
    if (
        representative.manifest.get("format_id") != FLYRUN_FORMAT_ID
        or representative.manifest.get("schema_version") != FLYRUN_SCHEMA_VERSION
        or reports["recorder-format.json"].get("archive_members")
        != list(FLYRUN_MEMBERS)
        or reports["recorder-format.json"].get("fixture_bytes")
        != representative.archive_bytes
        or reports["recorder-format.json"].get("content_digest")
        != representative.content_digest
        or truncated.summary.get("recording", {}).get("optional_status")
        != "TRUNCATED"
        or not any(event["type"] == "recorder_gap" for event in truncated.events)
        or looming.manifest.get("run", {}).get("execution_context", {}).get(
            "scenario"
        )
        != "standard looming"
    ):
        raise ValueError("valid attempt-2 fixture inventory or identities mismatch")
    for fixture in loaded.values():
        if (
            fixture.summary.get("applied_input_sha256")
            != canonical_applied_input_sha256(fixture.events)
            or fixture.summary.get("reexecution", {}).get("verified") is not False
            or fixture.summary.get("reexecution", {}).get("verification_milestone")
            != "M10"
            or not fixture.summary.get("final_whole_state_sha256")
        ):
            raise ValueError(f"fixture integrity envelope is incomplete: {fixture.path}")
    for relative, expected in MALFORMED_FIXTURES.items():
        try:
            load_flyrun(evidence / relative)
        except FlyRunError as exc:
            if expected not in str(exc):
                raise ValueError(
                    f"malformed fixture rejected for unexpected reason: {relative}: {exc}"
                ) from exc
        else:
            raise ValueError(f"malformed fixture loaded successfully: {relative}")
    excerpts = evidence / "fixture-excerpts.md"
    excerpt_text = excerpts.read_text(encoding="utf-8")
    for required in (
        "applied_input_sha256",
        "initial_state_digest",
        "periodic_state_digest_examples",
        "final_state_digest",
        "optional_truncation_gap_marker",
        '"verified": false',
    ):
        if required not in excerpt_text:
            raise ValueError(f"quick fixture excerpt is missing {required}")

    provenance = representative.manifest["provenance"]
    selected_backend = provenance.get("selected_live_backend", {})
    resolved_configuration = representative.manifest.get(
        "resolved_configuration", {}
    )
    live_sha = sha256_file(ROOT / "profiles/live.json")
    game_sha = sha256_file(ROOT / "profiles/game-v0.3.json")
    if (
        live_sha
        != "abd4c4d216708427e4b959991e0efbf788e6dfa5ba35f5ab5df79fc274dd6ca4"
        or game_sha
        != "5bedee08184b6762e9f6a52f435c4494322f34a794c5dd44034acfc7c7856c0b"
        or provenance.get("architecture_sha256") != ARCHITECTURE_SHA256
        or provenance.get("live_profile_sha256") != live_sha
        or provenance.get("game_spec_sha256") != game_sha
        or provenance.get("graph", {}).get("N") != 313
        or provenance.get("graph", {}).get("E") != 20_607
        or provenance.get("graph", {}).get("represented_contacts") != 79_112
        or selected_backend.get("kernel_id")
        != "flybench.numba-serial-active-source.v1"
        or provenance.get("identities", {}).get("controller_sha256")
        != "0b3577ec2dc257f130d59f0219544ad0dae479080027e25bdeca2182673bf817"
        or resolved_configuration.get("runtime_model_spec", {}).get(
            "runtime_synaptic_scale"
        )
        != 0.001
        or resolved_configuration.get("effective_environment", {}).get(
            "ambient_speed_per_interval"
        )
        != 0.03
    ):
        raise ValueError("representative scientific/runtime identity mismatch")

    head = git_head()
    for name in ("representative.flyrun", "looming-seed-0.flyrun"):
        if loaded[name].manifest["provenance"].get("code_git_sha") != head:
            raise ValueError(f"{name} does not identify the checked commit")
    if reports["demo-recording-smoke.json"].get("checks", {}).get(
        "candidate_code_identity"
    ) is not True:
        raise ValueError("bounded demo recording smoke lacks code identity")

    result: dict[str, Any] = {
        "phase": phase,
        "head": head,
        "decision_sha256": M08_DEFER_DECISION_SHA256,
        "coordinate_decision_sha256": sha256_file(coordinate_path),
        "representative_bytes": representative.archive_bytes,
        "representative_content_digest": representative.content_digest,
        "looming_bytes": looming.archive_bytes,
        "looming_content_digest": looming.content_digest,
        "live_profile_sha256": live_sha,
        "game_spec_sha256": game_sha,
    }
    if phase == "submission":
        candidate = ledger.get("m09_execution", {}).get(
            "attempt_2_candidate_product_sha"
        )
        operator_report = load_json(evidence / "operator-demo.json")
        operator_paths = sorted((evidence / "operator-demo").glob("*.flyrun"))
        if len(operator_paths) != 1:
            raise ValueError("submission requires exactly one real operator demo flyrun")
        operator = load_flyrun(operator_paths[0])
        m09_decision = load_json(evidence / "decision.json")
        if (
            not isinstance(candidate, str)
            or len(candidate) != 40
            or operator.manifest.get("provenance", {}).get("code_git_sha")
            != candidate
            or operator_report.get("status") != "PASS"
            or operator_report.get("candidate_product_sha") != candidate
            or operator_report.get("process_status") != PROCESS_STATUS
            or operator_report.get("archive_sha256")
            != sha256_file(operator_paths[0])
            or m09_decision.get("milestone") != "M09"
            or m09_decision.get("review_attempt") != 2
            or m09_decision.get("candidate_product_sha") != candidate
            or m09_decision.get("proposed_outcome") != "PASS_CANDIDATE"
            or m09_decision.get("external_milestone_acceptance") != "PENDING"
            or m09_decision.get("m08_g_game") != "PENDING_UNMEASURED"
            or m09_decision.get("m09_execution") != "AT_RISK"
            or m09_decision.get("reexecution_verified") is not False
        ):
            raise ValueError("M09 submission/operator evidence is incomplete or overstated")
        result.update(
            {
                "candidate_product_sha": candidate,
                "operator_demo_path": str(operator_paths[0]),
                "operator_demo_bytes": operator.archive_bytes,
                "operator_demo_content_digest": operator.content_digest,
            }
        )
        # command-results.json is written only after this checker returns from
        # inside the acceptance runner. The review-bundle validator checks that
        # completed report against the final submitted SHA, avoiding a circular
        # dependency on evidence that does not yet exist at this boundary.
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--phase",
        choices=("automated", "submission", "current"),
        default="current",
    )
    args = parser.parse_args(argv)
    evidence = args.out if args.out.is_absolute() else ROOT / args.out
    try:
        identities = validate(evidence, phase=args.phase)
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        FlyRunError,
        yaml.YAMLError,
    ) as exc:
        print(f"M09 evidence check failed: {type(exc).__name__}: {exc}")
        return 1
    print(json.dumps({"status": "PASS", **identities}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
