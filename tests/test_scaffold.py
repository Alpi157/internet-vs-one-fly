from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

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


def test_ledger_records_accepted_m01_and_keeps_science_unmeasured() -> None:
    ledger = yaml.safe_load((ROOT / "ledger.yaml").read_text(encoding="utf-8"))
    assert ledger["playbook_version"] == "0.1"
    assert ledger["current_milestone"] == "M02"
    assert ledger["current_attempt"] == 1
    assert ledger["last_accepted_milestone"] == "M01"
    assert ledger["accepted_milestones"] == ["M01"]
    assert ledger["milestone_status"] == {"M01": "ACCEPTED"}
    assert ledger["architecture_sha256"] == ARCHITECTURE_SHA256
    assert ledger["repository_url"] is None
    assert ledger["last_accepted_code_commit"] == "58c42226442e6a57b97779833d92f759e31e3d81"

    source_lock = ROOT / "profiles" / "source-lock.json"
    assert ledger["source_lock_digest"] == hashlib.sha256(source_lock.read_bytes()).hexdigest()
    assert ledger["dataset_release"] == "MaleCNS v1.0"
    assert len(ledger["source_files"]) == 3
    assert all(source["observed_bytes"] > 0 for source in ledger["source_files"])
    assert all(len(source["observed_sha256"]) == 64 for source in ledger["source_files"])
    assert all(source["upstream_sha256"] is None for source in ledger["source_files"])
    for graph_name in ("full_graph", "live_graph"):
        assert ledger[graph_name]["digest"] is None
        assert ledger[graph_name]["N"] is None
        assert ledger[graph_name]["E"] is None
        assert ledger[graph_name]["contacts"] is None
    assert ledger["ports"]["input_body_ids"] == []
    assert ledger["ports"]["output_body_ids"] == []
    assert all(value is None for value in ledger["profiles"].values())
    assert all(value == "UNMEASURED" for value in ledger["measurements"].values())
    assert ledger["reexecution"]["result"] == "UNMEASURED"
    assert ledger["alpha_full_graph_optimization_passes_used"] == 0
    assert ledger["publication"] == {
        "repository": "NOT_PUBLISHED",
        "beta": "NOT_PUBLISHED",
        "alpha": "NOT_PUBLISHED",
    }
    assert ledger["deferred_scope"] == "architecture_section_17"


def test_observed_tooling_is_honest() -> None:
    tooling = json.loads((ROOT / "tooling.json").read_text(encoding="utf-8"))
    commands = tooling["commands"]
    assert commands["git"]["normalized_version"] == "2.43.0"
    assert commands["python"]["normalized_version"] == "3.12.3"
    assert commands["uv"]["normalized_version"] == "0.12.13"
    for missing in ("node", "npm"):
        assert commands[missing]["available"] is False
        assert commands[missing]["exit_status"] != 0
        assert commands[missing]["normalized_version"] is None
    assert "WSL2" in commands["uname"]["normalized_version"]
    assert "x86_64" in commands["uname"]["normalized_version"]


def test_required_m01_paths_and_registry() -> None:
    required = [
        "pyproject.toml",
        "uv.lock",
        "AGENTS.md",
        "ledger.yaml",
        "tooling.json",
        "docs/architecture.md",
        "docs/data-attribution.md",
        "profiles/source-lock.json",
        "src/flybench/__init__.py",
        "src/flybench/cli.py",
        "src/flybench/data.py",
        "tools/acceptance.json",
        "tools/run_acceptance.py",
        "tools/review_bundle.py",
        "tests/test_scaffold.py",
        "tests/test_review_tools.py",
        "tests/test_source_fetch.py",
        ".github/workflows/m01-offline.yml",
    ]
    assert all((ROOT / path).is_file() for path in required)

    registry = json.loads((ROOT / "tools" / "acceptance.json").read_text(encoding="utf-8"))
    assert set(registry["milestones"]) == {"M01", "M02"}
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
