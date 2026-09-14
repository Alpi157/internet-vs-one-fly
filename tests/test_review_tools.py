from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_acceptance.py"
BUNDLER = ROOT / "tools" / "review_bundle.py"
ADVERSARIAL_REGISTRY = ROOT / "tests" / "fixtures" / "adversarial_acceptance.json"


def run_acceptance_fixture(milestone: str, output: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            milestone,
            "--registry",
            str(ADVERSARIAL_REGISTRY),
            "--out",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads((output / "command-results.json").read_text(encoding="utf-8"))
    return completed, report


def test_failing_subprocess_propagates_and_captures_stderr(tmp_path: Path) -> None:
    completed, report = run_acceptance_fixture("FAILING_SUBPROCESS", tmp_path / "failing")
    command = report["commands"][0]
    assert completed.returncode != 0
    assert report["status"] == "FAIL"
    assert report["exit_status"] != 0
    assert command["exit_status"] == 23
    assert command["status"] == "FAIL"
    assert "FLYBENCH_CONTROLLED_FAILURE" in command["stderr"]
    assert "PASS text is not evidence" in command["stdout"]
    assert "FLYBENCH_CONTROLLED_FAILURE" in (tmp_path / "failing" / command["stderr_path"]).read_text()


def test_missing_required_executable_cannot_pass(tmp_path: Path) -> None:
    completed, report = run_acceptance_fixture("MISSING_COMMAND", tmp_path / "missing-command")
    command = report["commands"][0]
    assert completed.returncode != 0
    assert report["status"] == "FAIL"
    assert command["exit_status"] == 127
    assert command["failure_reason"] == "required executable was not found"
    assert "FileNotFoundError" in command["stderr"]


def test_missing_required_path_cannot_pass(tmp_path: Path) -> None:
    completed, report = run_acceptance_fixture("MISSING_PATH", tmp_path / "missing-path")
    command = report["commands"][0]
    assert completed.returncode != 0
    assert report["status"] == "FAIL"
    assert command["exit_status"] == 127
    assert "definitely-not-present-m01.fixture" in command["stderr"]
    assert "must not run" not in command["stdout"]


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )


def make_fixture_repository(path: Path) -> str:
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "FlyBench Test")
    git(path, "config", "user.email", "flybench-test@example.invalid")

    (path / "src" / "flybench").mkdir(parents=True)
    (path / "docs").mkdir()
    (path / "src" / "flybench" / "__init__.py").write_text("VALUE = 'legitimate source'\n")
    (path / "docs" / "architecture.md").write_bytes((ROOT / "docs" / "architecture.md").read_bytes())
    (path / "docs" / "review-notes.md").write_text("legitimate unchanged documentation\n")
    (path / "config.ini").write_text("[fixture]\nvalue = legitimate unchanged configuration\n")
    (path / "ledger.yaml").write_text(
        "playbook_version: '0.1'\ncurrent_milestone: M01\n"
        "architecture_sha256: bae80837d5d6d769ae5b728af3b80c1caa21b7f08efdd7f3eb458f7bb2eab9d1\n"
    )
    (path / "tooling.json").write_text('{"schema_version": 1, "commands": {}}\n')
    (path / ".gitignore").write_text("evidence/\n.env\ncredentials.json\n.pytest_cache/\ndata/raw/\n")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "fixture source")

    # These are deliberately fake and ignored. Evidence traversal still sees the
    # planted forbidden entries and must exclude them explicitly.
    (path / ".env").write_text("FAKE_TOKEN=not-a-real-secret\n")
    (path / "credentials.json").write_text('{"fake": "not-a-real-credential"}\n')
    (path / ".pytest_cache").mkdir()
    (path / ".pytest_cache" / "cache").write_text("cache")
    (path / "data" / "raw").mkdir(parents=True)
    (path / "data" / "raw" / "malecns.tsv").write_text("fake raw data")
    evidence = path / "evidence" / "M01"
    (evidence / ".pytest_cache").mkdir(parents=True)
    (evidence / "data" / "raw").mkdir(parents=True)
    (evidence / "ok.txt").write_text("legitimate evidence\n")
    (evidence / ".env").write_text("FAKE_SECRET=exclude-me\n")
    (evidence / ".pytest_cache" / "cache").write_text("exclude cache")
    (evidence / "data" / "raw" / "bulk.tsv").write_text("exclude raw data")
    return git(path, "rev-parse", "HEAD").stdout.strip()


def test_bundle_exclusions_inventory_hashes_and_clean_identity(tmp_path: Path) -> None:
    repo = tmp_path / "fixture-repo"
    submitted = make_fixture_repository(repo)
    output = tmp_path / "fixture-review.zip"
    completed = subprocess.run(
        [
            sys.executable,
            str(BUNDLER),
            "--milestone",
            "M01",
            "--attempt",
            "1",
            "--base",
            "EMPTY",
            "--out",
            str(output),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "repo/src/flybench/__init__.py" in names
        assert "repo/config.ini" in names
        assert "repo/docs/review-notes.md" in names
        assert "repo/docs/architecture.md" in names
        assert "evidence/ok.txt" in names
        assert "base/README.txt" in names
        assert "git_diff.patch" in names
        assert "review-manifest.json" in names

        forbidden_fragments = (
            ".env",
            "credentials.json",
            ".pytest_cache",
            "data/raw",
            ".git/",
        )
        assert not any(fragment in name for name in names for fragment in forbidden_fragments)

        manifest = json.loads(archive.read("review-manifest.json"))
        assert manifest["submitted_code_sha"] == submitted
        assert manifest["base_identity"] == "EMPTY"
        assert manifest["unhashed_entries"] == ["review-manifest.json"]
        assert not any(item["path"] == "review-manifest.json" for item in manifest["inventory"])

        recorded_paths = {item["path"] for item in manifest["inventory"]}
        assert recorded_paths == names - {"review-manifest.json"}
        for item in manifest["inventory"]:
            actual = archive.read(item["path"])
            assert item["bytes"] == len(actual)
            assert item["sha256"] == hashlib.sha256(actual).hexdigest()

        assert submitted.encode() in archive.read("REVIEW.md")
        assert b"ACCEPTED" not in archive.read("REVIEW.md")
        assert b"legitimate unchanged configuration" in archive.read("repo/config.ini")

    (repo / "config.ini").write_text("dirty product change\n")
    dirty_output = tmp_path / "dirty-review.zip"
    dirty = subprocess.run(
        [
            sys.executable,
            str(BUNDLER),
            "--milestone",
            "M01",
            "--attempt",
            "1",
            "--base",
            "EMPTY",
            "--out",
            str(dirty_output),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert dirty.returncode != 0
    assert "dirty code tree" in dirty.stderr
    assert not dirty_output.exists()


def test_m02_bundle_uses_bounded_report_for_large_source_inventory(tmp_path: Path) -> None:
    repo = tmp_path / "m02-fixture-repo"
    base = make_fixture_repository(repo)
    lock_files = []
    report_sources = []
    roles = ("curated_annotations", "aggregate_neurotransmitters", "connection_weights")
    for index, role in enumerate(roles, start=1):
        filename = f"official-{role}.feather"
        digest = hashlib.sha256(f"fixture-{role}".encode()).hexdigest()
        size = index * 100
        url = f"https://example.invalid/{filename}"
        lock_files.append(
            {
                "role": role,
                "filename": filename,
                "official_url": url,
                "observed_bytes": size,
                "observed_sha256": digest,
                "observed_sha256_provenance": "locally observed fixture",
                "upstream_sha256": None,
            }
        )
        report_sources.append(
            {
                "role": role,
                "filename": filename,
                "official_url": url,
                "exact_observed_bytes": size,
                "observed_sha256": digest,
                "validation": "PASS",
                "feather": {
                    "format": "Apache Arrow Feather V2 / Arrow IPC file",
                    "fields": [{"name": "fixture", "type": "int64"}],
                    "role_validation": "PASS",
                },
            }
        )
    lock = {
        "schema_version": 1,
        "dataset": {"name": "MaleCNS", "release": "MaleCNS v1.0"},
        "files": lock_files,
    }
    (repo / "profiles").mkdir()
    lock_path = repo / "profiles" / "source-lock.json"
    lock_path.write_text(json.dumps(lock, sort_keys=True) + "\n")
    git(repo, "add", "profiles/source-lock.json")
    git(repo, "commit", "-q", "-m", "resolved M02 fixture lock")

    evidence = repo / "evidence" / "M02"
    evidence.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "PASS",
        "source_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "command": ["flybench", "data", "fetch"],
        "sources": report_sources,
    }
    (evidence / "source-report.json").write_text(json.dumps(report))
    (evidence / "manual-source-review.txt").write_text("operator-supplied fixture receipt\n")

    output = tmp_path / "m02-review.zip"
    completed = subprocess.run(
        [
            sys.executable,
            str(BUNDLER),
            "--milestone",
            "M02",
            "--attempt",
            "1",
            "--base",
            base,
            "--out",
            str(output),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    with zipfile.ZipFile(output) as archive:
        large_files = json.loads(archive.read("large-files.json"))
        source_entries = [
            item for item in large_files["omitted"] if item["reason"].startswith("official MaleCNS")
        ]
        assert len(source_entries) == 3
        assert {item["sha256"] for item in source_entries} == {
            source["observed_sha256"] for source in lock_files
        }
        assert all(item["schema_role_validation"] == "PASS" for item in source_entries)
        assert not any(name.startswith("repo/data/raw/") for name in archive.namelist())
        assert "evidence/manual-source-review.txt" in archive.namelist()
        assert b"present (operator-supplied)" in archive.read("REVIEW.md")
