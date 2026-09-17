from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_SHA256 = "bae80837d5d6d769ae5b728af3b80c1caa21b7f08efdd7f3eb458f7bb2eab9d1"


def test_package_imports() -> None:
    package = importlib.import_module("flybench")
    assert package.__version__ == "0.0.0"


def test_architecture_identity() -> None:
    architecture = ROOT / "docs" / "architecture.md"
    assert architecture.is_file()
    assert hashlib.sha256(architecture.read_bytes()).hexdigest() == ARCHITECTURE_SHA256
    assert architecture.read_text(encoding="utf-8").startswith(
        "**Catch the Fly: architecture for a fast public release**"
    )


def test_ledger_lifecycle_consistency() -> None:
    ledger = yaml.safe_load((ROOT / "ledger.yaml").read_text(encoding="utf-8"))
    required_keys = {
        "playbook_version",
        "current_milestone",
        "current_attempt",
        "last_accepted_milestone",
        "accepted_milestones",
        "milestone_status",
        "architecture_sha256",
        "working_name",
        "demo_name",
        "last_accepted_code_commit",
        "source_lock_digest",
        "dataset_release",
        "source_files",
        "full_graph",
        "live_graph",
        "ports",
        "profiles",
        "measurements",
        "reviews",
        "deferred_scope",
    }
    allowed_statuses = {
        "NOT_STARTED",
        "IN_PROGRESS",
        "SUBMITTED",
        "ACCEPTED",
        "CHANGES_REQUIRED",
        "BLOCKED",
    }

    assert required_keys <= ledger.keys()
    assert ledger["playbook_version"] == "0.1"
    assert ledger["architecture_sha256"] == ARCHITECTURE_SHA256
    assert ledger["working_name"] == "FlyBench"
    assert ledger["demo_name"] == "Catch the Fly"
    assert ledger["deferred_scope"] == "architecture_section_17"

    assert type(ledger["current_attempt"]) is int
    assert ledger["current_attempt"] >= 1
    assert isinstance(ledger["current_milestone"], str)
    assert ledger["current_milestone"] in ledger["milestone_status"]
    assert set(ledger["milestone_status"].values()) <= allowed_statuses

    accepted_milestones = ledger["accepted_milestones"]
    assert isinstance(accepted_milestones, list)
    assert "M01" in accepted_milestones
    assert len(accepted_milestones) == len(set(accepted_milestones))
    assert ledger["last_accepted_milestone"] == accepted_milestones[-1]
    assert all(
        ledger["milestone_status"][milestone] == "ACCEPTED"
        for milestone in accepted_milestones
    )

    reviews = ledger["reviews"]
    assert isinstance(reviews, list)
    assert any(
        review["milestone"] == "M01"
        and review["attempt"] == 1
        and review["verdict"] == "ACCEPTED"
        for review in reviews
    )
    assert any(
        review["milestone"] == ledger["last_accepted_milestone"]
        and review["verdict"] == "ACCEPTED"
        and review["code_sha"] == ledger["last_accepted_code_commit"]
        for review in reviews
    )

    source_lock = ROOT / "profiles" / "source-lock.json"
    if "M02" in accepted_milestones:
        assert ledger["source_lock_digest"] == hashlib.sha256(
            source_lock.read_bytes()
        ).hexdigest()
        assert ledger["dataset_release"] == "MaleCNS v1.0"
        assert len(ledger["source_files"]) == 3
        assert all(
            source.get("bytes", source.get("observed_bytes", 0)) > 0
            for source in ledger["source_files"]
        )
        assert all(
            len(source["observed_sha256"]) == 64
            for source in ledger["source_files"]
        )
        assert all(
            source["upstream_sha256"] is None for source in ledger["source_files"]
        )
    else:
        assert ledger["source_lock_digest"] is None
        assert ledger["dataset_release"] is None
        assert ledger["source_files"] == []


def test_observed_tooling_is_honest() -> None:
    tooling = json.loads((ROOT / "tooling.json").read_text(encoding="utf-8"))
    ledger = yaml.safe_load((ROOT / "ledger.yaml").read_text(encoding="utf-8"))
    commands = tooling["commands"]
    assert commands["git"]["normalized_version"] == "2.43.0"
    assert commands["python"]["normalized_version"] == "3.12.3"
    assert commands["uv"]["normalized_version"] == "0.12.13"
    if ledger["current_milestone"] in {"M08", "M09"}:
        assert commands["node"]["available"] is True
        assert commands["node"]["exit_status"] == 0
        assert commands["node"]["normalized_version"] == "24.21.0"
        assert commands["npm"]["available"] is True
        assert commands["npm"]["exit_status"] == 0
        assert commands["npm"]["normalized_version"] == "11.19.0"
    else:
        for missing in ("node", "npm"):
            assert commands[missing]["available"] is False
            assert commands[missing]["exit_status"] != 0
            assert commands[missing]["normalized_version"] is None
    assert "WSL2" in commands["uname"]["normalized_version"]
    assert "x86_64" in commands["uname"]["normalized_version"]


def test_m09_at_risk_process_state_does_not_claim_m08_acceptance() -> None:
    ledger = yaml.safe_load((ROOT / "ledger.yaml").read_text(encoding="utf-8"))
    if ledger["current_milestone"] != "M09":
        pytest.skip("M09 at-risk process state is not active")
    decision = json.loads(
        (ROOT / "decisions/D-M08-HUMAN-GATE-DEFER-01.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["milestone_status"]["M08"] == "BLOCKED"
    assert ledger["milestone_status"]["M09"] in {"IN_PROGRESS", "SUBMITTED"}
    assert ledger["last_accepted_milestone"] == "M07"
    assert ledger["accepted_milestones"] == [
        "M01",
        "M02",
        "M03",
        "M04",
        "M05",
        "M06",
        "M07",
    ]
    assert ledger["m08_integration_baseline"]["g_game"] == "PENDING_UNMEASURED"
    assert ledger["m09_execution"]["status"] == "AT_RISK"
    assert decision["classification"].startswith("PROCESS DEVIATION")
    assert decision["m08"]["milestone_acceptance"] == "NOT_ACCEPTED"
    assert decision["m08"]["unfamiliar_player_evidence_collected"] is False
    assert (
        decision["m08"]["representative_remote_host_human_smoke_completed"]
        is False
    )


def test_required_m01_paths_and_registry() -> None:
    required = [
        "pyproject.toml",
        "uv.lock",
        "AGENTS.md",
        "ledger.yaml",
        "tooling.json",
        "docs/architecture.md",
        "docs/data-attribution.md",
        "docs/graph-format.md",
        "docs/pathway-card.md",
        "docs/model-card.md",
        "docs/encoder-card.md",
        "docs/decoder-card.md",
        "docs/calibration-plan.md",
        "docs/numerical-semantics.md",
        "profiles/source-lock.json",
        "profiles/accepted-neurons.json",
        "profiles/compile-transform-v1.json",
        "profiles/escape-circuit.json",
        "profiles/model-v0.1.json",
        "profiles/encoder-v0.1.json",
        "profiles/decoder-v0.1.json",
        "profiles/calibration-plan.json",
        "profiles/numerical-criteria-v0.1.json",
        "profiles/model-reference-v0.1.json",
        "profiles/looming-controls.json",
        "profiles/encoder-runtime-v0.1.json",
        "profiles/decoder-runtime-v0.1.json",
        "profiles/environment-v0.1.json",
        "profiles/intervention-direct-visual-to-dnp01-zero-v0.1.json",
        "profiles/kernel-parity-v0.1.json",
        "profiles/full-probe.json",
        "src/flybench/__init__.py",
        "src/flybench/cli.py",
        "src/flybench/data.py",
        "src/flybench/graph.py",
        "src/flybench/pathway.py",
        "src/flybench/model.py",
        "src/flybench/reference.py",
        "src/flybench/encoding.py",
        "src/flybench/decoder.py",
        "src/flybench/catch.py",
        "src/flybench/runner.py",
        "src/flybench/authority.py",
        "src/flybench/bench.py",
        "src/flybench/kernel.py",
        "tools/acceptance.json",
        "tools/check_m06_evidence.py",
        "tools/check_m07_evidence.py",
        "tools/run_acceptance.py",
        "tools/review_bundle.py",
        "tests/test_scaffold.py",
        "tests/test_review_tools.py",
        "tests/test_source_fetch.py",
        "tests/test_graph_compile.py",
        "tests/test_pathway_mapping.py",
        "tests/test_reference.py",
        "tests/test_numerical_semantics.py",
        "tests/test_runner.py",
        "tests/test_controller_authority.py",
        "tests/test_kernel_parity.py",
        "tests/test_probe_limits.py",
        "tests/fixtures/m04-reference.json",
        "tools/build_m04_mapping.py",
        "experiments/numerical_reference.py",
        "experiments/performance_probe.py",
        ".github/workflows/m01-offline.yml",
    ]
    assert all((ROOT / path).is_file() for path in required)

    registry = json.loads((ROOT / "tools" / "acceptance.json").read_text(encoding="utf-8"))
    assert {"M01", "M02", "M03", "M04", "M05", "M06", "M07"} <= set(
        registry["milestones"]
    )
    for milestone in registry["milestones"].values():
        commands = milestone["commands"]
        assert commands
        assert all(command["required"] is True for command in commands)
        assert all(command["argv"] for command in commands)
        assert not any(
            "run_acceptance.py" in argument
            for command in commands
            for argument in command["argv"]
        )
