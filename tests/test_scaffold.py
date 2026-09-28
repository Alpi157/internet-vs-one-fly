from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_SHA256 = "bae80837d5d6d769ae5b728af3b80c1caa21b7f08efdd7f3eb458f7bb2eab9d1"
PLAN_V2_SHA256 = "ef97902c9393d416bf25007643c09e1410cfde3d92a7130ae847559beee73016"
SOURCE_LOCK_SHA256 = "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c"


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


def test_plan_v2_identity() -> None:
    plan = ROOT / "docs" / "plan-v2.md"
    assert plan.is_file()
    assert hashlib.sha256(plan.read_bytes()).hexdigest() == PLAN_V2_SHA256


def test_ledger_v2_consistency() -> None:
    ledger = yaml.safe_load((ROOT / "ledger.yaml").read_text(encoding="utf-8"))
    required_keys = {
        "ledger_version",
        "authority",
        "tooling",
        "source_lock",
        "graphs",
        "accepted_gates",
        "m08",
        "m09",
        "stages",
        "measurements",
        "launch_blockers",
        "next_action",
    }
    assert required_keys <= set(ledger)
    assert ledger["ledger_version"] == 2
    assert ledger["authority"] == {
        "plan_sha256": PLAN_V2_SHA256,
        "architecture_sha256": ARCHITECTURE_SHA256,
    }
    assert ledger["stages"]
    assert set(ledger["stages"].values()) <= {"SUBMITTED", "ACCEPTED"}
    assert ledger["m08"]["status"] == "G-GAME_DEFERRED_SUPERSEDED_BY_PLAN_V2"
    assert ledger["m09"]["status"] == "SUBMITTED_SUPERSEDED_BY_PLAN_V2"
    assert set(ledger["accepted_gates"]) == {
        "G-MAP",
        "M05-NUMERICAL-SEMANTICS",
        "G-BIO",
        "G-FULL",
    }
    source_lock = ROOT / "profiles" / "source-lock.json"
    assert ledger["source_lock"]["digest"] == SOURCE_LOCK_SHA256
    assert hashlib.sha256(source_lock.read_bytes()).hexdigest() == SOURCE_LOCK_SHA256
    assert len(ledger["source_lock"]["files"]) == 3
    assert ledger["graphs"]["full"] == {
        "N": 166700,
        "E": 25582938,
        "contacts": 124177617,
        "digest": "429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0",
    }
    assert ledger["graphs"]["accepted_circuit"] == {
        "N": 313,
        "E": 20607,
        "contacts": 79112,
        "digest": "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5",
    }
    assert ledger["graphs"]["v2_candidates"] == {
        "T1a": {"status": "PROVISIONAL_SEEDS", "N": 2461, "E": 244345, "contacts": 2227343, "digest": "58d6cd4463428c753c8d5fb09a651651582b87282542bc28abc74b73aefc1190"},
        "T1b": {"status": "PROVISIONAL_SEEDS", "N": 5038, "E": 649715, "contacts": 6391268, "digest": "7ee512cea35a6d183c542e46c8daa74103eb636b3162d39e651183c653ee988f"},
        "T2": {"status": "PROVISIONAL_SEEDS", "N": 42845, "E": 7091676, "contacts": 43697352, "digest": "8069495572c0e789892fb4da1a1b828881b575626346a0f0d0c15d6de978315b"},
    }
    for name, digest in {
        "ports-v2.json": "1510d45d8db29739e94d08db55efe8b264099ed0140b5e0657621194a7ca2304",
        "walking-dn-candidates-v2.json": "cddab8a5badbd83fae23f16f79d4f749433bf6e0337ac466a7bf85ba4d36dd8d",
        "circuit-builder-v2.json": "ef15696adce820501226f0b72695e4f0108bc2a953c63e5ae53c68c4774b4f7d",
        "detmath-v2.json": "4af1bc2e12bc442575add8e3798bfb5da47e0e479e9227852056799526f66a3e",
        "calibration-v2-draft.json": "51601e75b5822424f6ab84f6deab224c5d48a4569c52ac774472a49b5cdcb423",
    }.items():
        assert hashlib.sha256((ROOT / "profiles" / name).read_bytes()).hexdigest() == digest
    assert hashlib.sha256(
        (ROOT / "docs/history/ledger-v1.yaml").read_bytes()
    ).hexdigest() == "83c1b68411cac22edb546078862dc9756a1944d3c91cd13da1b52e5685ec8429"


def test_observed_tooling_is_honest() -> None:
    tooling = json.loads((ROOT / "tooling.json").read_text(encoding="utf-8"))
    ledger = yaml.safe_load((ROOT / "ledger.yaml").read_text(encoding="utf-8"))
    commands = tooling["commands"]
    assert commands["git"]["normalized_version"] == "2.43.0"
    assert commands["python"]["normalized_version"] == "3.12.3"
    assert commands["uv"]["normalized_version"] == "0.12.13"
    if ledger["stages"].get("V2A") in {"SUBMITTED", "ACCEPTED"}:
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


def test_v2_process_acceptance_requires_reviewer_verdict() -> None:
    ledger = yaml.safe_load((ROOT / "ledger.yaml").read_text(encoding="utf-8"))
    review_records = ledger.get("stage_review_records", {})
    for stage, status in ledger["stages"].items():
        if status != "ACCEPTED":
            continue
        record = review_records[stage]
        decision_path = ROOT / record["decision"]
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        assert decision["stage"] == stage
        assert decision["reviewer"] == "external (operator relay)"
        assert decision["verdict_status"] == "ACCEPTED WITH CONDITIONS"
        assert record["verdict"] == decision["verdict"]


def test_required_m01_paths_and_registry() -> None:
    required = [
        "pyproject.toml",
        "uv.lock",
        "AGENTS.md",
        "ledger.yaml",
        "tooling.json",
        "docs/architecture.md",
        "docs/plan-v2.md",
        "docs/history/ledger-v1.yaml",
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
        "profiles/p0-bots-v1.json",
        "profiles/circuit-builder-v1.json",
        "profiles/nulls-v1.json",
        "profiles/walking-dn-candidates-v1.json",
        "profiles/visual-ports-sides-v1.json",
        "profiles/walking-dn-candidates-v2.json",
        "profiles/ports-v2.json",
        "profiles/circuit-builder-v2.json",
        "profiles/detmath-v2.json",
        "profiles/model-v2-draft.json",
        "profiles/encoder-v2-draft.json",
        "profiles/decoder-v2-draft.json",
        "profiles/body-v2-draft.json",
        "profiles/calibration-v2-draft.json",
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
        "src/flybench/circuit.py",
        "src/flybench/nulls.py",
        "src/flybench/v2_data.py",
        "src/flybench/detmath.py",
        "src/flybench/reference_v2.py",
        "src/flybench/kernel_v2.py",
        "src/flybench/encoding_v2.py",
        "src/flybench/decoder_v2.py",
        "src/flybench/body_v2.py",
        "src/flybench/web_export.py",
        "packages/kernel-ts/package.json",
        "packages/kernel-ts/package-lock.json",
        "packages/kernel-ts/src/kernel.ts",
        "packages/kernel-ts/test/parity.test.ts",
        "tests/vectors/detmath-v1.json",
        "tools/acceptance.json",
        "tools/check_m06_evidence.py",
        "tools/check_m07_evidence.py",
        "tools/run_acceptance.py",
        "tools/review_bundle.py",
        "decisions/D-V2-01.json",
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
        "tests/test_p0_truth_checks.py",
        "tests/test_nulls.py",
        "tests/fixtures/m04-reference.json",
        "tools/build_m04_mapping.py",
        "experiments/numerical_reference.py",
        "experiments/performance_probe.py",
        "experiments/p0_truth_checks.py",
        "fixtures/escape-circuit-v1/LICENSE-DATA.md",
        "fixtures/escape-circuit-v1/manifest.json",
        ".github/workflows/m01-offline.yml",
    ]
    assert all((ROOT / path).is_file() for path in required)

    registry = json.loads((ROOT / "tools" / "acceptance.json").read_text(encoding="utf-8"))
    assert {"M01", "M02", "M03", "M04", "M05", "M06", "M07", "V2A", "V2B"} <= set(
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
