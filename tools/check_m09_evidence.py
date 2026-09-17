#!/usr/bin/env python3
"""Validate M09 recorder evidence without interpreting deferred M08 usability."""

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
    M08_DEFER_DECISION_ID,
    M08_DEFER_DECISION_PATH,
    M08_DEFER_DECISION_SHA256,
    load_flyrun,
)


ROOT = Path(__file__).resolve().parents[1]
REPORTS = (
    "recorder-format.json",
    "deterministic-recording.json",
    "applied-input-authority.json",
    "bounds.json",
    "archive-safety.json",
    "headless-server-recorder-parity.json",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def process_status_valid(value: object) -> bool:
    return value == {
        "decision": M08_DEFER_DECISION_ID,
        "m09_execution": "AT_RISK",
        "m08_g_game": "PENDING_UNMEASURED",
        "m09_is_m08_usability_evidence": False,
        "public_release_blocked": True,
    }


def validate(evidence: Path, *, require_submission: bool) -> dict[str, Any]:
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
        raise ValueError("process-deviation decision does not preserve the declared boundary")
    ledger = yaml.safe_load((ROOT / "ledger.yaml").read_text(encoding="utf-8"))
    if (
        ledger.get("current_milestone") != "M09"
        or ledger.get("milestone_status", {}).get("M08") != "BLOCKED"
        or ledger.get("milestone_status", {}).get("M09")
        not in {"IN_PROGRESS", "SUBMITTED"}
        or ledger.get("last_accepted_milestone") != "M07"
        or ledger.get("accepted_milestones")
        != ["M01", "M02", "M03", "M04", "M05", "M06", "M07"]
        or ledger.get("last_accepted_code_commit")
        != "c2b0dc064fa1f8d50b01f595f0232f8d9b37d5e5"
        or ledger.get("m08_integration_baseline", {}).get("g_game")
        != "PENDING_UNMEASURED"
        or ledger.get("m09_execution", {}).get("status") != "AT_RISK"
    ):
        raise ValueError("ledger does not truthfully represent M08 deferral and M09 risk")

    reports = {name: load_json(evidence / name) for name in REPORTS}
    for name, report in reports.items():
        if report.get("status") != "PASS":
            raise ValueError(f"M09 evidence report does not pass: {name}")
        if not process_status_valid(report.get("process_status")):
            raise ValueError(f"M09 at-risk disclosure is missing from {name}")
    for name in (
        "deterministic-recording.json",
        "applied-input-authority.json",
        "bounds.json",
        "archive-safety.json",
        "headless-server-recorder-parity.json",
    ):
        if not all(reports[name].get("checks", {}).values()):
            raise ValueError(f"M09 evidence contains a failing check: {name}")

    fixture_path = evidence / "representative.flyrun"
    loaded = load_flyrun(fixture_path)
    format_report = reports["recorder-format.json"]
    if (
        format_report.get("format_id") != FLYRUN_FORMAT_ID
        or format_report.get("archive_members") != list(FLYRUN_MEMBERS)
        or format_report.get("fixture_bytes") != loaded.archive_bytes
        or format_report.get("content_digest") != loaded.content_digest
        or loaded.manifest.get("process_deviation", {}).get("decision_sha256")
        != M08_DEFER_DECISION_SHA256
        or loaded.manifest.get("process_deviation", {}).get("m08_g_game")
        != "PENDING_UNMEASURED"
        or loaded.manifest.get("process_deviation", {}).get(
            "m09_is_m08_usability_evidence"
        )
        is not False
    ):
        raise ValueError("representative flyrun format or at-risk identity mismatch")
    provenance = loaded.manifest["provenance"]
    resolved_configuration = loaded.manifest.get("resolved_configuration", {})
    live_sha = sha256_file(ROOT / "profiles/live.json")
    game_sha = sha256_file(ROOT / "profiles/game-v0.3.json")
    if (
        provenance.get("architecture_sha256") != ARCHITECTURE_SHA256
        or provenance.get("live_profile_sha256") != live_sha
        or provenance.get("game_spec_sha256") != game_sha
        or provenance.get("graph", {}).get("N") != 313
        or provenance.get("graph", {}).get("E") != 20_607
        or provenance.get("graph", {}).get("represented_contacts") != 79_112
        or provenance.get("backend", {}).get("kernel_id")
        != "flybench.numba-serial-active-source.v1"
        or provenance.get("identities", {}).get("controller_sha256")
        != "0b3577ec2dc257f130d59f0219544ad0dae479080027e25bdeca2182673bf817"
        or resolved_configuration.get("live_profile", {}).get("graph", {}).get("N")
        != 313
        or resolved_configuration.get("runtime_model_spec", {}).get(
            "runtime_synaptic_scale"
        )
        != 0.001
        or resolved_configuration.get("effective_environment", {}).get(
            "ambient_speed_per_interval"
        )
        != 0.03
    ):
        raise ValueError("representative flyrun scientific/runtime identity mismatch")

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if require_submission:
        commands = load_json(evidence / "command-results.json")
        m09_decision = load_json(evidence / "decision.json")
        if (
            commands.get("status") != "PASS"
            or commands.get("submitted_code_sha") != head
            or m09_decision.get("milestone") != "M09"
            or m09_decision.get("proposed_outcome") != "PASS_CANDIDATE"
            or m09_decision.get("external_milestone_acceptance") != "PENDING"
            or m09_decision.get("m08_g_game") != "PENDING_UNMEASURED"
            or m09_decision.get("m09_execution") != "AT_RISK"
        ):
            raise ValueError("M09 submission evidence or candidate decision is incomplete")
    return {
        "head": head,
        "decision_sha256": M08_DEFER_DECISION_SHA256,
        "fixture_bytes": loaded.archive_bytes,
        "content_digest": loaded.content_digest,
        "live_profile_sha256": live_sha,
        "game_spec_sha256": game_sha,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--phase", choices=("automated", "submission"), default="automated")
    args = parser.parse_args(argv)
    evidence = args.out if args.out.is_absolute() else ROOT / args.out
    try:
        identities = validate(evidence, require_submission=args.phase == "submission")
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f"M09 evidence check failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        json.dumps(
            {"status": "PASS", "phase": args.phase, **identities}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
