#!/usr/bin/env python3
"""Build the compact, evidence-bearing review ZIP used by FlyBench milestones."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ARCHITECTURE_SHA256 = "bae80837d5d6d769ae5b728af3b80c1caa21b7f08efdd7f3eb458f7bb2eab9d1"
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MAX_INCLUDED_FILE_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_BYTES = 15 * 1024 * 1024

CACHE_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}
RAW_PARTS = {"raw", "raw-data", "raw_data", "bulk"}


class BundleError(RuntimeError):
    """A review bundle precondition was not met."""


def git(root: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=text, check=False
    )
    if completed.returncode:
        stderr = completed.stderr if text else completed.stderr.decode("utf-8", "replace")
        raise BundleError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return completed.stdout


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def exclusion_reason(path: PurePosixPath) -> str | None:
    parts_lower = tuple(part.lower() for part in path.parts)
    name = path.name.lower()
    if any(part in CACHE_PARTS for part in parts_lower):
        return "cache, environment, dependency, build, or Git metadata"
    if len(parts_lower) >= 2 and parts_lower[0] == "data" and parts_lower[1] in RAW_PARTS:
        return "bulk or raw data"
    if any("malecns" in part for part in parts_lower) and name.endswith((".csv", ".tsv", ".feather", ".parquet", ".npy", ".npz")):
        return "MaleCNS bulk data"
    if name == ".env" or name.startswith(".env."):
        return "environment secret"
    if name.endswith((".pem", ".key", ".p12", ".pfx")) or name.startswith(("id_rsa", "id_ed25519")):
        return "key material"
    if any(marker in name for marker in ("credential", "credentials", "private_key", "secret", "token")):
        return "credential or secret material"
    if "resume" in name or "curriculum_vitae" in name:
        return "operator resume"
    return None


def tracked_paths(root: Path, commit: str) -> list[str]:
    output = git(root, "ls-tree", "-r", "--name-only", "-z", commit)
    assert isinstance(output, str)
    return sorted(path for path in output.split("\0") if path)


def commit_blob(root: Path, commit: str, path: str) -> bytes:
    output = git(root, "show", f"{commit}:{path}", text=False)
    assert isinstance(output, bytes)
    return output


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def inventory(entries: dict[str, bytes]) -> list[dict[str, Any]]:
    return [
        {"path": path, "bytes": len(entries[path]), "sha256": sha256(entries[path])}
        for path in sorted(entries)
    ]


def load_command_reports(evidence_root: Path) -> list[tuple[str, dict[str, Any]]]:
    reports: list[tuple[str, dict[str, Any]]] = []
    if not evidence_root.is_dir():
        return reports
    for path in sorted(evidence_root.rglob("command-results.json")):
        if exclusion_reason(PurePosixPath(path.relative_to(evidence_root).as_posix())):
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            reports.append((path.relative_to(evidence_root).as_posix(), value))
    return reports


def render_review(
    milestone: str,
    attempt: int,
    base: str,
    submitted: str,
    architecture_sha: str,
    reports: list[tuple[str, dict[str, Any]]],
    tooling: dict[str, Any] | None,
    manual_source_review_present: bool,
    m03_audit: dict[str, Any] | None,
    m03_determinism: dict[str, Any] | None,
    m04_mapping: dict[str, Any] | None,
    m04_decision: dict[str, Any] | None,
    m04_audit: dict[str, Any] | None,
    m05_decision: dict[str, Any] | None,
    m05_convergence: dict[str, Any] | None,
    m05_analytical: dict[str, Any] | None,
    m05_boundary: dict[str, Any] | None,
    m06_decision: dict[str, Any] | None,
    m06_calibration: dict[str, Any] | None,
    m06_authority: dict[str, Any] | None,
    m06_dependencies: dict[str, Any] | None,
) -> bytes:
    primary = next((report for path, report in reports if path == "command-results.json"), None)
    primary_status = primary.get("status") if primary else "NOT_CAPTURED"
    if milestone == "M02":
        objective = (
            "Acquire, validate, and pin the exact official MaleCNS v1.0 source bytes needed "
            "by the architecture without compiling a graph."
        )
        assumptions = [
            "The source set is exactly the three official M02 Feather files.",
            "Upstream SHA-256 values remain null because none was observed on the official page; recorded SHA-256 values are locally observed byte identities.",
            "Bulk source bytes are deliberately excluded and described in large-files.json.",
            "No graph cardinality, biological mapping, or later-milestone result is claimed.",
        ]
    elif milestone == "M03":
        objective = (
            "Compile the pinned MaleCNS v1.0 neuron-level sources into a deterministic, "
            "auditable, source-major sparse graph without implementing neural dynamics."
        )
        assumptions = [
            "Accepted nodes are exact uint64 body IDs with non-null curated superclass, sorted numerically; raw edge endpoints never create nodes.",
            "Raw uint64 contact counts remain separate from provisional float32 executable weights.",
            "Transmitter labels and confidences are source data; effective signs, unit gain, and no-normalization are explicit MODEL ASSUMPTIONS.",
            "Unknown, missing, unsupported, and modulatory signaling contributes zero fast-current weight rather than being silently made excitatory.",
            "Full arrays and pinned source bytes are omitted from this bounded ZIP and identified in large-files.json; the exact synthetic graph is included.",
        ]
    elif milestone == "M04":
        objective = (
            "Resolve exact MaleCNS v1.0 LC4, LPLC2, and DNp01 identities, verify direct "
            "accepted-graph wiring and signs, and freeze an auditable ports-only candidate circuit."
        )
        assumptions = [
            "Exact body IDs and sides come from pinned MaleCNS v1.0 annotation fields; literature grounds biological roles but is not an ID authority.",
            "The circuit is the exact induced graph over all canonical LC4, LPLC2, and DNp01 matches; no context neurons or contact threshold are added.",
            "Raw contact counts remain source data; effective signs and the later model, encoder, decoder, and calibration grid remain explicit MODEL ASSUMPTIONS.",
            "The compact circuit arrays are included; full M03 arrays and raw MaleCNS sources are omitted and identified in large-files.json.",
            "No simulation, calibration execution, numerical acceptance, or behavioral claim is part of M04.",
        ]
    elif milestone == "M05":
        objective = (
            "Implement and validate a deterministic float64 reference oracle for the "
            "accepted normalized-LIF candidate without implementing closed-loop behavior."
        )
        assumptions = [
            "The accepted M04 model, mapping, circuit, encoder, decoder, and calibration profiles remain byte-identical.",
            "The exact linear substep and flybench.neural-order.v1 are project numerical conventions over explicit MODEL ASSUMPTIONS, not physiology.",
            "The runtime synaptic scale 1.0 is used only for bounded numerical fixtures and is not a calibrated controller choice.",
            "The numerical criteria were committed before convergence measurement and were not loosened afterward.",
            "No Runner, encoder/decoder implementation, behavioral calibration, game mechanics, or optimized kernel is part of M05.",
        ]
    elif milestone == "M06":
        objective = (
            "Implement one integer-clock headless Runner and test whether the accepted "
            "ports-only neural model has declared DNp01-dependent escape-command authority."
        )
        assumptions = [
            "The accepted M04 circuit and M05 numerical semantics remain unchanged; M06 adds only the frozen feature encoder, pure DNp01 decoder, abstract environment, and declared interventions.",
            "The 12-point grid and four normal scenarios were committed before calibration and were not expanded after outcomes were observed.",
            "The output clamp acts only at the declared decoder boundary; the direct visual-to-DNp01 intervention zeroes exactly the predeclared in-memory executable weights.",
            "Ambient walking and takeoff are provisional threat-independent game mechanics, not physiology or biomechanics.",
            "The claim is limited to modeled DNp01-dependent escape onset in the declared simplified circuit/controller.",
        ]
    else:
        objective = (
            "Establish the M01 reproducible Python workspace, repository invariants, offline "
            "checks, acceptance runner, and bounded review-bundle mechanism."
        )
        assumptions = [
            "Python 3.12 is the supported M01 development runtime.",
            "Node and npm are not M01 prerequisites and were not installed.",
            "Generated evidence and review archives are ignored repository outputs.",
            "M01 contains no scientific model, biological mapping, runtime, or later-milestone implementation.",
        ]
    lines = [
        f"# {milestone} review submission (attempt {attempt})",
        "",
        "## Objective",
        "",
        objective,
        "",
        "## Summary",
        "",
        f"The repository snapshot is the committed tree at `{submitted}`. The primary captured acceptance status is `{primary_status}`. External review remains pending.",
        "",
        "## Assumptions and decisions",
        "",
        *[f"- {assumption}" for assumption in assumptions],
        "",
        "## Identities",
        "",
        f"- Architecture SHA-256: `{architecture_sha}`",
        f"- Base identity: `{base}`",
        f"- Submitted code SHA: `{submitted}`",
        "",
        "## Commands actually captured",
        "",
    ]
    if reports:
        for report_path, report in reports:
            lines.append(f"Evidence report `{report_path}`: status `{report.get('status', 'UNKNOWN')}`.")
            lines.append("")
            for command in report.get("commands", []):
                argv = json.dumps(command.get("argv", []), ensure_ascii=False)
                lines.append(
                    f"- `{command.get('name', 'unnamed')}`: argv `{argv}`; cwd `{command.get('cwd')}`; "
                    f"exit `{command.get('exit_status')}`; result `{command.get('status')}`."
                )
            lines.append("")
    else:
        lines.extend(["No command-results.json was available.", ""])

    lines.extend(["## Real results", ""])
    if primary:
        for command in primary.get("commands", []):
            lines.append(
                f"- `{command.get('name', 'unnamed')}` exited `{command.get('exit_status')}` "
                f"with status `{command.get('status')}`."
            )
    else:
        lines.append("- Primary acceptance results were not captured.")
    if milestone == "M03" and m03_audit:
        graph = m03_audit.get("graph", {})
        lines.extend(
            [
                f"- Full graph semantic digest: `{m03_audit.get('semantic_graph_digest')}`.",
                f"- Accepted N: `{graph.get('N')}`; source accepted E: `{graph.get('source_accepted_E')}`; executable nonzero E: `{graph.get('executable_nonzero_E')}`.",
                f"- Represented contacts: `{graph.get('represented_source_contacts')}`; disabled contact mass: `{graph.get('disabled_zero_weight_contact_mass')}`; isolated accepted neurons: `{graph.get('isolated_accepted_neurons')}`.",
            ]
        )
    if milestone == "M03" and m03_determinism:
        lines.append(
            f"- Independent repeat-build comparison: `{m03_determinism.get('status')}`; first `{m03_determinism.get('first_semantic_graph_digest')}`, repeat `{m03_determinism.get('second_semantic_graph_digest')}`."
        )
    if milestone == "M04" and m04_mapping:
        claims = m04_mapping.get("mapping_claims", {})
        populations = claims.get("populations", {})
        pathways = claims.get("direct_pathways", [])
        cut = claims.get("cut_context", {})
        lines.append(
            f"- Mapping semantic digest: `{m04_mapping.get('mapping_digest', {}).get('value')}`."
        )
        lines.append(
            "- Exact population counts: "
            + "; ".join(
                f"{name} `{populations.get(name, {}).get('count')}`"
                for name in ("LC4", "LPLC2", "DNp01")
            )
            + "."
        )
        for pathway in pathways:
            lines.append(
                f"- {pathway.get('source_population')} -> DNp01: `{pathway.get('direct_pair_edges')}` pair edges, `{pathway.get('raw_contact_mass')}` contacts, `{pathway.get('executable_nonzero_edges')}` executable nonzero edges."
            )
        lines.append(
            f"- Cut context: incoming `{cut.get('cut_incoming', {}).get('pair_edges')}` edges / `{cut.get('cut_incoming', {}).get('contact_mass')}` contacts; outgoing `{cut.get('cut_outgoing', {}).get('pair_edges')}` edges / `{cut.get('cut_outgoing', {}).get('contact_mass')}` contacts."
        )
    if milestone == "M04" and m04_audit:
        graph = m04_audit.get("graph", {})
        lines.append(
            f"- Circuit semantic digest: `{m04_audit.get('semantic_graph_digest')}`; N `{graph.get('N')}`, E `{graph.get('source_accepted_E')}`, contacts `{graph.get('represented_source_contacts')}`."
        )
    if milestone == "M04" and m04_decision:
        lines.append(
            f"- G-MAP candidate decision: `{m04_decision.get('outcome')}`; external milestone acceptance remains `{m04_decision.get('external_milestone_acceptance')}`."
        )
    if milestone == "M05" and m05_decision:
        lines.extend(
            [
                f"- Numerical-semantics candidate decision: `{m05_decision.get('outcome')}`; external milestone acceptance remains `{m05_decision.get('external_milestone_acceptance')}`.",
                f"- Selected neural dt: `{m05_decision.get('selected_neural_dt_ms')}` ms; delay `{m05_decision.get('delay_ticks')}` ticks; refractory `{m05_decision.get('refractory_ticks')}` ticks.",
                f"- Resolved ModelSpec SHA-256: `{m05_decision.get('model_spec_sha256')}`; event order `{m05_decision.get('event_order_version')}`.",
            ]
        )
    if milestone == "M05" and m05_convergence:
        for dt, result in m05_convergence.get("comparisons", {}).items():
            lines.append(f"- Candidate dt `{dt}` ms convergence: `{result.get('status')}`.")
    if milestone == "M05" and m05_analytical:
        lines.append(f"- Analytical fixtures: `{m05_analytical.get('status')}`.")
    if milestone == "M05" and m05_boundary:
        lines.append(f"- Boundary fixtures: `{m05_boundary.get('status')}`.")
    if milestone == "M06" and m06_decision:
        lines.extend(
            [
                f"- G-BIO candidate decision: `{m06_decision.get('outcome')}`; external milestone acceptance remains `{m06_decision.get('external_milestone_acceptance')}`.",
                f"- Claim scope: `{m06_decision.get('claim_scope')}`.",
                f"- Calibration protocol commit: `{m06_decision.get('calibration_protocol_commit')}`.",
            ]
        )
    if milestone == "M06" and m06_calibration:
        lines.append(
            f"- Frozen normal panel: `{m06_calibration.get('primary_combination_count')}` combinations / `{m06_calibration.get('normal_trial_count')}` trials; selected `{m06_calibration.get('selected_combination')}`."
        )
        lines.append(
            f"- Failed combinations retained: `{len(m06_calibration.get('failed_combinations', []))}`."
        )
    if milestone == "M06" and m06_authority:
        selected_authority = m06_authority.get("selected_attempt") or {}
        lines.append(
            f"- Authority selection: `{m06_authority.get('status')}`; checks `{selected_authority.get('checks')}`."
        )
    if milestone == "M06" and m06_dependencies:
        lines.append(
            f"- Decoder dependency audit: `{m06_dependencies.get('decoder', {}).get('status')}`; ambient-walk dependency audit: `{m06_dependencies.get('ambient_walking', {}).get('status')}`."
        )

    lines.extend(["", "## Failures", ""])
    primary_failures = [
        command for command in (primary or {}).get("commands", []) if command.get("exit_status") != 0
    ]
    if primary_failures:
        for command in primary_failures:
            lines.append(
                f"- `{command.get('name', 'unnamed')}`: {command.get('failure_reason') or 'failed'}"
            )
    else:
        lines.append("- No failure is recorded in the primary acceptance report.")

    lines.extend(["", "## Manual and tooling evidence", ""])
    commands = tooling.get("commands", {}) if isinstance(tooling, dict) else {}
    if commands:
        for name in ("git", "python", "uv", "node", "npm", "uname"):
            receipt = commands.get(name, {})
            lines.append(
                f"- `{name}`: available `{receipt.get('available')}`; exit `{receipt.get('exit_status')}`; "
                f"normalized `{receipt.get('normalized_version')}`."
            )
    else:
        lines.append("- No tooling.json receipt was available.")
    if milestone == "M02":
        lines.append(
            "- `evidence/M02/manual-source-review.txt`: "
            + ("present (operator-supplied)." if manual_source_review_present else "absent; manual review remains pending.")
        )
    if milestone == "M04":
        receipt = (m04_decision or {}).get("manual_mapping_review_receipt", {})
        lines.append(
            "- `evidence/M04/manual-mapping-review.txt`: "
            + (
                "present (operator-supplied)."
                if receipt.get("status") == "PRESENT_OPERATOR_SUPPLIED"
                else "absent; manual mapping review remains pending."
            )
        )
    if milestone == "M05":
        receipt = (m05_decision or {}).get("manual_equation_review_receipt", {})
        lines.append(
            "- `evidence/M05/manual-equation-review.txt`: "
            + (
                "present (operator-supplied)."
                if receipt.get("status") == "PRESENT_OPERATOR_SUPPLIED"
                else "absent; manual equation review remains pending."
            )
        )
    if milestone == "M06":
        receipt = (m06_decision or {}).get("manual_authority_review_receipt", {})
        lines.append(
            "- `evidence/M06/manual-authority-review.txt`: "
            + (
                "present (operator-supplied)."
                if receipt.get("status") == "PRESENT_OPERATOR_SUPPLIED"
                else "absent; manual authority review remains pending."
            )
        )

    lines.extend(["", "## Unresolved issues", "", "- The external reviewer has not issued a verdict."])
    if milestone == "M02" and not manual_source_review_present:
        lines.append("- The operator's manual source-origin receipt is absent.")
    if milestone == "M04" and (m04_decision or {}).get(
        "manual_mapping_review_receipt", {}
    ).get("status") != "PRESENT_OPERATOR_SUPPLIED":
        lines.append("- The operator's manual M04 mapping-review receipt is absent.")
    if milestone == "M05" and (m05_decision or {}).get(
        "manual_equation_review_receipt", {}
    ).get("status") != "PRESENT_OPERATOR_SUPPLIED":
        lines.append("- The operator's manual M05 equation-review receipt is absent.")
    if milestone == "M06" and (m06_decision or {}).get(
        "manual_authority_review_receipt", {}
    ).get("status") != "PRESENT_OPERATOR_SUPPLIED":
        lines.append("- The operator's manual M06 authority-review receipt is absent.")
    lines.extend(
        [
            "- Scientific and product capabilities assigned to later milestones remain intentionally unimplemented.",
            "",
            "## Review limitations",
            "",
            "- Captured output proves what this submission reports running; it is not independent reviewer reproduction.",
            (
                "- This archive covers source identity and acquisition only; it contains no graph-compilation or biological-result evidence."
                if milestone == "M02"
                else (
                    "- Full generated arrays are omitted for bounded review; exact hashes, dtypes, shapes, sizes, generation identities, audit results, and a directly inspectable synthetic graph are included."
                    if milestone == "M03"
                    else (
                        "- Full M03 arrays and raw sources are omitted with exact identities; compact circuit arrays and source-derived mapping evidence are included."
                        if milestone == "M04"
                        else (
                            "- This archive contains the complete small reference implementation, frozen criteria, fixtures, and numerical evidence; no raw MaleCNS or full-graph bulk data is required."
                            if milestone == "M05"
                            else (
                                "- This archive contains the frozen M06 protocol, complete compact trial evidence, authority comparisons, dependency audits, and accepted compact circuit; raw MaleCNS and full M03 arrays remain excluded."
                                if milestone == "M06"
                                else "- This archive covers M01 infrastructure only and contains no scientific-result evidence."
                            )
                        )
                    )
                )
            ),
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def add_evidence(
    entries: dict[str, bytes], evidence_root: Path, omitted: list[dict[str, Any]]
) -> None:
    if not evidence_root.is_dir():
        entries["evidence/README.txt"] = b"No generated evidence directory was present at bundle time.\n"
        return
    included = 0
    for path in sorted(evidence_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = PurePosixPath(path.relative_to(evidence_root).as_posix())
        reason = exclusion_reason(relative)
        size = path.stat().st_size
        if reason or size > MAX_INCLUDED_FILE_BYTES:
            data = path.read_bytes() if not reason else b""
            omitted.append(
                {
                    "path": f"evidence/{relative.as_posix()}",
                    "reason": reason or "file exceeds bounded per-file review size",
                    "bytes": size,
                    "sha256": sha256(data) if data else None,
                }
            )
            continue
        entries[f"evidence/{relative.as_posix()}"] = path.read_bytes()
        included += 1
    if included == 0:
        entries["evidence/README.txt"] = b"No includable generated evidence was present at bundle time.\n"


def add_base(entries: dict[str, bytes], root: Path, base: str, submitted: str) -> None:
    if base == "EMPTY":
        entries["base/README.txt"] = b"M01 has no prior accepted repository; the comparison base is the Git empty tree.\n"
        return
    changed = git(root, "diff", "--name-status", "-z", base, submitted)
    assert isinstance(changed, str)
    tokens = changed.split("\0")
    index = 0
    included = 0
    while index < len(tokens) and tokens[index]:
        status = tokens[index]
        index += 1
        if status.startswith("R") or status.startswith("C"):
            old_path = tokens[index]
            index += 2
        else:
            old_path = tokens[index]
            index += 1
        if status.startswith("A"):
            continue
        reason = exclusion_reason(PurePosixPath(old_path))
        if reason:
            continue
        try:
            data = commit_blob(root, base, old_path)
        except BundleError:
            continue
        if len(data) <= MAX_INCLUDED_FILE_BYTES:
            entries[f"base/{old_path}"] = data
            included += 1
    if included == 0:
        entries["base/README.txt"] = b"No changed or deleted small file required a prior-version copy.\n"


def m02_large_source_inventory(
    root: Path, submitted: str, evidence_root: Path
) -> list[dict[str, Any]]:
    try:
        lock_bytes = commit_blob(root, submitted, "profiles/source-lock.json")
        lock = json.loads(lock_bytes)
        report = json.loads((evidence_root / "source-report.json").read_text(encoding="utf-8"))
    except (BundleError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M02 source lock/report is missing or invalid: {exc}") from exc
    lock_digest = sha256(lock_bytes)
    if report.get("status") != "PASS" or report.get("source_lock_sha256") != lock_digest:
        raise BundleError("M02 source report does not pass or does not identify the committed source lock")
    locked_by_role = {source.get("role"): source for source in lock.get("files", [])}
    report_by_role = {source.get("role"): source for source in report.get("sources", [])}
    if len(locked_by_role) != 3 or set(locked_by_role) != set(report_by_role):
        raise BundleError("M02 source lock/report roles do not identify the same three files")

    result: list[dict[str, Any]] = []
    for role in sorted(locked_by_role):
        locked = locked_by_role[role]
        observed = report_by_role[role]
        if (
            observed.get("validation") != "PASS"
            or observed.get("exact_observed_bytes") != locked.get("observed_bytes")
            or observed.get("observed_sha256") != locked.get("observed_sha256")
            or observed.get("official_url") != locked.get("official_url")
            or observed.get("filename") != locked.get("filename")
        ):
            raise BundleError(f"M02 lock/report identity mismatch for role {role!r}")
        feather = observed.get("feather", {})
        result.append(
            {
                "path": f"data/raw/{locked['filename']}",
                "reason": "official MaleCNS bulk source excluded from the review ZIP",
                "official_url": locked["official_url"],
                "release": lock["dataset"]["release"],
                "role": role,
                "bytes": locked["observed_bytes"],
                "sha256": locked["observed_sha256"],
                "hash_provenance": locked["observed_sha256_provenance"],
                "upstream_sha256": locked.get("upstream_sha256"),
                "format": feather.get("format"),
                "schema_fields": feather.get("fields"),
                "schema_role_validation": feather.get("role_validation"),
                "acquisition_command": report.get("command"),
            }
        )
    return result


def m03_large_graph_inventory(
    root: Path, submitted: str, evidence_root: Path
) -> list[dict[str, Any]]:
    audit_path = evidence_root / "full-audit.json"
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M03 full audit is missing or invalid: {exc}") from exc
    if audit.get("status") != "PASS":
        raise BundleError("M03 full audit does not report PASS")
    compiler = audit.get("compiler", {})
    if compiler.get("code_git_sha") != submitted:
        raise BundleError("M03 full audit was not generated from the submitted commit")
    expected_module_sha = sha256(
        commit_blob(root, submitted, "src/flybench/graph.py")
    )
    if compiler.get("module_sha256") != expected_module_sha:
        raise BundleError("M03 full audit compiler module differs from submitted code")
    graph_digest = audit.get("semantic_graph_digest")
    arrays = audit.get("arrays")
    if not isinstance(graph_digest, str) or not isinstance(arrays, dict) or not arrays:
        raise BundleError("M03 full audit lacks semantic graph or array identities")
    try:
        determinism = json.loads(
            (evidence_root / "determinism.json").read_text(encoding="utf-8")
        )
        synthetic = json.loads(
            (evidence_root / "synthetic" / "synthetic-result.json").read_text(
                encoding="utf-8"
            )
        )
        acceptance = json.loads(
            (evidence_root / "command-results.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M03 determinism/synthetic/acceptance evidence is missing: {exc}") from exc
    if (
        determinism.get("status") != "PASS"
        or determinism.get("first_semantic_graph_digest") != graph_digest
        or determinism.get("second_semantic_graph_digest") != graph_digest
    ):
        raise BundleError("M03 repeat-build evidence does not match the audited graph")
    if synthetic.get("status") != "PASS":
        raise BundleError("M03 exact synthetic evidence does not report PASS")
    if acceptance.get("status") != "PASS" or acceptance.get("submitted_code_sha") != submitted:
        raise BundleError("M03 acceptance evidence does not pass for the submitted commit")
    source_lock = audit.get("source_lock", {})
    selection = audit.get("selection_profile", {})
    transform = audit.get("compile_transform_profile", {})
    generation_command = audit.get("build_resource", {}).get("command")
    result: list[dict[str, Any]] = []
    source_files = source_lock.get("source_files")
    if not isinstance(source_files, list) or len(source_files) != 3:
        raise BundleError("M03 full audit lacks the three pinned source identities")
    for entry in sorted(source_files, key=lambda value: value.get("role", "")):
        filename = entry.get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise BundleError("M03 full audit contains an unsafe source filename")
        path = root / "data" / "raw" / filename
        if not path.is_file():
            raise BundleError(f"audited M03 source is missing: {path}")
        size, digest = sha256_file(path)
        if size != entry.get("bytes") or digest != entry.get("observed_sha256"):
            raise BundleError(f"M03 source differs from full audit: {filename}")
        result.append(
            {
                "path": f"data/raw/{filename}",
                "reason": "official MaleCNS bulk source excluded from bounded review ZIP",
                "role": entry.get("role"),
                "bytes": size,
                "sha256": digest,
                "upstream_sha256": entry.get("upstream_sha256"),
                "source_lock_sha256": source_lock.get("sha256"),
                "generation_command": generation_command,
            }
        )
    for name, entry in sorted(arrays.items()):
        if not isinstance(entry, dict):
            raise BundleError(f"invalid M03 array audit entry {name!r}")
        filename = entry.get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise BundleError(f"unsafe M03 array filename for {name!r}")
        path = root / "data" / "compiled" / "full" / filename
        if not path.is_file():
            raise BundleError(f"audited M03 array is missing: {path}")
        size, digest = sha256_file(path)
        if size != entry.get("bytes") or digest != entry.get("sha256"):
            raise BundleError(f"M03 array differs from full audit: {filename}")
        result.append(
            {
                "path": f"data/compiled/full/{filename}",
                "reason": "full generated graph array omitted from bounded review ZIP",
                "array_name": name,
                "bytes": size,
                "sha256": digest,
                "dtype": entry.get("dtype"),
                "shape": entry.get("shape"),
                "graph_semantic_digest": graph_digest,
                "generation_command": generation_command,
                "source_lock_sha256": source_lock.get("sha256"),
                "selection_profile_sha256": selection.get("sha256"),
                "selection_semantic_sha256": selection.get("semantic_sha256"),
                "compile_transform_profile_sha256": transform.get("sha256"),
            }
        )
    return result


def m04_material(
    root: Path,
    submitted: str,
    evidence_root: Path,
    entries: dict[str, bytes],
) -> list[dict[str, Any]]:
    """Validate M04 review evidence, include the compact circuit, inventory large inputs."""

    required_json = {}
    for name in (
        "mapping.json",
        "mapping-determinism.json",
        "decision.json",
        "circuit-audit.json",
        "circuit-determinism.json",
        "command-results.json",
    ):
        try:
            required_json[name] = json.loads(
                (evidence_root / name).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"M04 {name} is missing or invalid: {exc}") from exc
    mapping = required_json["mapping.json"]
    decision = required_json["decision.json"]
    mapping_determinism = required_json["mapping-determinism.json"]
    audit = required_json["circuit-audit.json"]
    determinism = required_json["circuit-determinism.json"]
    acceptance = required_json["command-results.json"]
    mapping_digest = mapping.get("mapping_digest", {}).get("value")
    circuit_digest = audit.get("semantic_graph_digest")
    if (
        mapping.get("status") != "PASS"
        or mapping.get("producer", {}).get("code_git_sha") != submitted
        or mapping.get("circuit_profile_validation", {}).get("status") != "PASS"
        or mapping.get("compiled_circuit_verification", {}).get("status") != "PASS"
    ):
        raise BundleError("M04 mapping evidence does not pass for submitted code")
    if (
        mapping_determinism.get("status") != "PASS"
        or mapping_determinism.get("mapping_semantic_sha256") != mapping_digest
        or mapping_determinism.get("before_sha256")
        != mapping_determinism.get("after_sha256")
    ):
        raise BundleError("M04 mapping deterministic rerun evidence does not pass")
    if (
        decision.get("outcome") != "PASS"
        or decision.get("external_milestone_acceptance") != "PENDING"
        or decision.get("mapping_semantic_sha256") != mapping_digest
        or decision.get("manual_mapping_review_receipt", {}).get("status")
        != "PRESENT_OPERATOR_SUPPLIED"
    ):
        raise BundleError("M04 G-MAP decision or operator receipt is incomplete")
    receipt_path = evidence_root / "manual-mapping-review.txt"
    if not receipt_path.is_file() or not receipt_path.stat().st_size:
        raise BundleError("M04 manual mapping-review receipt is absent")
    receipt_size, receipt_digest = sha256_file(receipt_path)
    receipt = decision["manual_mapping_review_receipt"]
    if receipt.get("bytes") != receipt_size or receipt.get("sha256") != receipt_digest:
        raise BundleError("M04 manual receipt identity differs from decision evidence")
    expected_module_sha = sha256(commit_blob(root, submitted, "src/flybench/graph.py"))
    if (
        audit.get("status") != "PASS"
        or audit.get("compiler", {}).get("code_git_sha") != submitted
        or audit.get("compiler", {}).get("module_sha256") != expected_module_sha
        or mapping.get("compiled_circuit_verification", {}).get(
            "semantic_graph_digest"
        )
        != circuit_digest
    ):
        raise BundleError("M04 circuit audit does not identify submitted compiler/circuit")
    if (
        determinism.get("status") != "PASS"
        or determinism.get("first_semantic_graph_digest") != circuit_digest
        or determinism.get("second_semantic_graph_digest") != circuit_digest
    ):
        raise BundleError("M04 circuit deterministic rebuild does not match audit")
    if acceptance.get("status") != "PASS" or acceptance.get("submitted_code_sha") != submitted:
        raise BundleError("M04 acceptance evidence does not pass for submitted code")
    circuit_profile = json.loads(
        commit_blob(root, submitted, "profiles/escape-circuit.json").decode("utf-8")
    )
    if circuit_profile.get("mapping_evidence", {}).get("semantic_sha256") != mapping_digest:
        raise BundleError("committed circuit profile does not bind M04 mapping digest")

    circuit_dir = root / "data" / "compiled" / "escape"
    if not circuit_dir.is_dir():
        raise BundleError("compiled M04 circuit directory is missing")
    for path in sorted(circuit_dir.iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if len(data) > MAX_INCLUDED_FILE_BYTES:
            raise BundleError(f"compact circuit artifact is unexpectedly large: {path.name}")
        entries[f"data/compiled/escape/{path.name}"] = data
    for name, item in audit.get("arrays", {}).items():
        filename = item.get("filename")
        path = circuit_dir / str(filename)
        size, digest = sha256_file(path)
        if size != item.get("bytes") or digest != item.get("sha256"):
            raise BundleError(f"M04 compact circuit array differs from audit: {name}")

    try:
        full_manifest = json.loads(
            (root / "data" / "compiled" / "full" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"accepted M03 full manifest is unavailable: {exc}") from exc
    accepted_full_digest = mapping.get("mapping_claims", {}).get(
        "accepted_full_graph", {}
    ).get("semantic_digest")
    if (
        accepted_full_digest
        != "429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0"
        or full_manifest.get("semantic_digest", {}).get("value") != accepted_full_digest
    ):
        raise BundleError("M04 mapping/full graph does not match accepted M03 identity")
    source_lock_bytes = commit_blob(root, submitted, "profiles/source-lock.json")
    source_lock_digest = sha256(source_lock_bytes)
    if source_lock_digest != "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c":
        raise BundleError("M04 committed source lock differs from accepted identity")
    source_lock = json.loads(source_lock_bytes)
    omitted: list[dict[str, Any]] = []
    for source in sorted(source_lock["files"], key=lambda value: value["role"]):
        path = root / "data" / "raw" / source["filename"]
        size, digest = sha256_file(path)
        if size != source["observed_bytes"] or digest != source["observed_sha256"]:
            raise BundleError(f"M04 raw source differs from lock: {source['filename']}")
        omitted.append(
            {
                "path": f"data/raw/{source['filename']}",
                "reason": "official MaleCNS bulk source excluded from bounded review ZIP",
                "role": source["role"],
                "bytes": size,
                "sha256": digest,
                "upstream_sha256": source.get("upstream_sha256"),
                "source_lock_sha256": source_lock_digest,
            }
        )
    for name, item in sorted(full_manifest.get("arrays", {}).items()):
        path = root / "data" / "compiled" / "full" / item["filename"]
        size, digest = sha256_file(path)
        if size != item["bytes"] or digest != item["sha256"]:
            raise BundleError(f"accepted M03 full array differs from manifest: {name}")
        omitted.append(
            {
                "path": f"data/compiled/full/{item['filename']}",
                "reason": "accepted full M03 graph array omitted from bounded review ZIP",
                "array_name": name,
                "bytes": size,
                "sha256": digest,
                "dtype": item["dtype"],
                "shape": item["shape"],
                "graph_semantic_digest": accepted_full_digest,
                "source_lock_sha256": source_lock_digest,
            }
        )
    return omitted


def m05_material(root: Path, submitted: str, evidence_root: Path) -> None:
    """Validate complete, bounded M05 reference evidence before bundling."""

    required: dict[str, dict[str, Any]] = {}
    for name in (
        "criteria-provenance.json",
        "analytical-fixtures.json",
        "boundary-fixtures.json",
        "timestep-convergence.json",
        "model-spec.json",
        "decision.json",
        "command-results.json",
    ):
        try:
            required[name] = json.loads((evidence_root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"M05 {name} is missing or invalid: {exc}") from exc
    provenance = required["criteria-provenance.json"]
    analytical = required["analytical-fixtures.json"]
    boundary = required["boundary-fixtures.json"]
    convergence = required["timestep-convergence.json"]
    model_spec = required["model-spec.json"]
    decision = required["decision.json"]
    acceptance = required["command-results.json"]
    if analytical.get("status") != "PASS" or boundary.get("status") != "PASS":
        raise BundleError("M05 analytical or boundary evidence does not pass")
    if (
        convergence.get("status") != "PASS"
        or convergence.get("reference_run", {}).get("status") != "PASS"
        or not convergence.get("comparisons")
    ):
        raise BundleError("M05 timestep convergence evidence does not pass")
    if (
        decision.get("outcome") != "PASS"
        or decision.get("allowed_next_milestone") != "M06"
        or decision.get("external_milestone_acceptance") != "PENDING"
        or decision.get("manual_equation_review_receipt", {}).get("status")
        != "PRESENT_OPERATOR_SUPPLIED"
    ):
        raise BundleError("M05 decision or operator equation-review receipt is incomplete")
    receipt_path = evidence_root / "manual-equation-review.txt"
    if not receipt_path.is_file() or not receipt_path.stat().st_size:
        raise BundleError("M05 manual equation-review receipt is absent")
    receipt_size, receipt_sha = sha256_file(receipt_path)
    receipt = decision["manual_equation_review_receipt"]
    if receipt.get("bytes") != receipt_size or receipt.get("sha256") != receipt_sha:
        raise BundleError("M05 manual equation-review receipt identity differs from decision")
    criteria_bytes = commit_blob(
        root, submitted, "profiles/numerical-criteria-v0.1.json"
    )
    criteria_sha = sha256(criteria_bytes)
    criteria_commit = provenance.get("criteria_commit_sha")
    if not isinstance(criteria_commit, str):
        raise BundleError("M05 criteria provenance lacks a commit identity")
    if (
        provenance.get("status") != "PASS"
        or provenance.get("criteria_sha256") != criteria_sha
        or provenance.get("criteria_unchanged_since_commit") is not True
        or provenance.get("final_measurement_worktree_clean") is not True
        or provenance.get("final_measurement_code_sha") != submitted
        or commit_blob(root, criteria_commit, "profiles/numerical-criteria-v0.1.json")
        != criteria_bytes
    ):
        raise BundleError("M05 criteria provenance does not bind unchanged committed bytes")
    expected_reference_sha = sha256(
        commit_blob(root, submitted, "src/flybench/reference.py")
    )
    expected_model_sha = sha256(commit_blob(root, submitted, "src/flybench/model.py"))
    if (
        model_spec.get("status") != "PASS"
        or model_spec.get("producer_code_git_sha") != submitted
        or model_spec.get("reference_code_sha256") != expected_reference_sha
        or model_spec.get("model_code_sha256") != expected_model_sha
        or model_spec.get("model_spec_sha256") != decision.get("model_spec_sha256")
    ):
        raise BundleError("M05 ModelSpec evidence does not identify submitted reference code")
    profile_bytes = commit_blob(root, submitted, "profiles/model-reference-v0.1.json")
    profile = json.loads(profile_bytes)
    if (
        profile.get("model_spec_sha256") != model_spec.get("model_spec_sha256")
        or profile.get("model_spec") != model_spec.get("model_spec")
        or profile.get("selected_neural_dt_ms") != convergence.get("selected_dt_ms")
        or model_spec.get("resolved_profile", {}).get("sha256") != sha256(profile_bytes)
    ):
        raise BundleError("M05 committed resolved profile differs from measured ModelSpec")
    if acceptance.get("status") != "PASS" or acceptance.get("submitted_code_sha") != submitted:
        raise BundleError("M05 acceptance evidence does not pass for submitted code")


def m06_material(
    root: Path,
    submitted: str,
    evidence_root: Path,
    entries: dict[str, bytes],
) -> None:
    """Validate complete M06 authority evidence and include the compact circuit."""

    required: dict[str, dict[str, Any]] = {}
    for name in (
        "calibration-summary.json",
        "authority.json",
        "stability.json",
        "decoder-dependency.json",
        "intervention.json",
        "controller-profile.json",
        "calibration-provenance.json",
        "review-repair-comparison.json",
        "decision.json",
        "command-results.json",
    ):
        try:
            required[name] = json.loads((evidence_root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"M06 {name} is missing or invalid: {exc}") from exc
    decision = required["decision.json"]
    calibration = required["calibration-summary.json"]
    authority = required["authority.json"]
    stability = required["stability.json"]
    dependencies = required["decoder-dependency.json"]
    intervention = required["intervention.json"]
    controller_evidence = required["controller-profile.json"]
    provenance = required["calibration-provenance.json"]
    repair_comparison = required["review-repair-comparison.json"]
    acceptance = required["command-results.json"]
    if (
        decision.get("gate") != "G-BIO"
        or decision.get("outcome") != "PASS"
        or decision.get("allowed_next_milestone") != "M07"
        or decision.get("external_milestone_acceptance") != "PENDING"
        or decision.get("manual_authority_review_receipt", {}).get("status")
        != "PRESENT_OPERATOR_SUPPLIED"
    ):
        raise BundleError("M06 G-BIO decision or manual receipt is incomplete")
    if (
        calibration.get("status") != "PASS"
        or calibration.get("primary_combination_count") != 12
        or calibration.get("normal_trial_count") != 48
        or len(calibration.get("combinations", [])) != 12
        or not calibration.get("selected_combination")
    ):
        raise BundleError("M06 frozen calibration evidence is incomplete")
    selected_attempt = authority.get("selected_attempt") or {}
    if authority.get("status") != "PASS" or not all(
        selected_attempt.get("checks", {}).values()
    ):
        raise BundleError("M06 neural-authority checks do not pass")
    if (
        stability.get("status") != "PASS"
        or dependencies.get("decoder", {}).get("status") != "PASS"
        or dependencies.get("ambient_walking", {}).get("status") != "PASS"
        or intervention.get("mask_audit", {}).get("total_pair_edges") != 311
        or intervention.get("mask_audit", {}).get("total_source_contacts") != 11224
    ):
        raise BundleError("M06 stability, dependency, or intervention evidence failed")
    receipt_path = evidence_root / "manual-authority-review.txt"
    if not receipt_path.is_file() or not receipt_path.stat().st_size:
        raise BundleError("M06 manual authority-review receipt is absent")
    receipt_size, receipt_sha = sha256_file(receipt_path)
    receipt = decision["manual_authority_review_receipt"]
    if receipt.get("bytes") != receipt_size or receipt.get("sha256") != receipt_sha:
        raise BundleError("M06 manual authority-review receipt identity differs from decision")
    if not (evidence_root / "authority-review.txt").is_file():
        raise BundleError("M06 human-readable authority review is absent")
    controller_bytes = commit_blob(root, submitted, "profiles/controller-v0.1.json")
    if json.loads(controller_bytes) != controller_evidence:
        raise BundleError("committed M06 controller differs from measured controller evidence")
    protocol_commit = provenance.get("calibration_protocol_commit")
    if (
        not isinstance(protocol_commit, str)
        or provenance.get("measurement_code_commit") != submitted
        or provenance.get("protocol_files_unchanged") is not True
        or provenance.get("measurement_worktree_clean_at_start") is not True
        or decision.get("calibration_protocol_commit") != protocol_commit
        or provenance.get("external_review_attempt") != 2
        or provenance.get("protocol_execution") != 3
        or provenance.get("repair_decision_ids")
        != ["D-M06-PROTOCOL-01", "D-M06-PROTOCOL-02"]
        or provenance.get("external_review_decision_ids") != ["D-M06-REVIEW-01"]
        or provenance.get("superseded_failed_protocol_commit")
        != "5fb91a10604bcfbfffefb1367fa0ea7ebe8e944f"
        or provenance.get("superseded_execution", {}).get("status")
        != "INVALID_NOT_RECORDED"
        or provenance.get("intermediate_mechanical_repair_commit")
        != "d0ac081bacb476d557608746eabca7141ee49e4e"
        or provenance.get("intermediate_commit_calibration_execution") != "NONE"
        or provenance.get("attempt_1", {}).get("valid_calibration_protocol_commit")
        != "52da05dfa21d9c637cd34a5f8cfdce71c5c328da"
        or provenance.get("attempt_1", {}).get("submitted_commit")
        != "69bf4e054d09cbe029a85c45184934cd7707e788"
        or provenance.get("attempt_1", {}).get("review_zip_sha256")
        != "7fefa5f755b1c4ce56710a746b351958fb1cf16c9769980f03b89e477c3fd432"
    ):
        raise BundleError("M06 calibration protocol provenance is incomplete")
    if (
        repair_comparison.get("status") != "PASS"
        or repair_comparison.get("scientific_mismatch_count") != 0
        or not all(repair_comparison.get("checks", {}).values())
        or repair_comparison.get("attempt_2", {}).get("trial_count") != 51
        or repair_comparison.get("attempt_2", {}).get("normal_trial_count") != 48
        or repair_comparison.get("attempt_2", {}).get("authority_trial_count") != 3
    ):
        raise BundleError("M06 attempt-1 versus attempt-2 scientific comparison failed")
    defect_path = evidence_root / "protocol-defect.json"
    if (
        not defect_path.is_file()
        or sha256_file(defect_path)[1]
        != provenance.get("superseded_execution", {}).get("evidence_sha256")
    ):
        raise BundleError("M06 failed protocol execution evidence was not preserved")
    for item in provenance.get("protocol_files", []):
        path = item.get("path")
        if not isinstance(path, str):
            raise BundleError("M06 protocol provenance contains an invalid path")
        current = commit_blob(root, submitted, path)
        frozen = commit_blob(root, protocol_commit, path)
        if current != frozen or sha256(current) != item.get("sha256"):
            raise BundleError(f"M06 protocol bytes changed after calibration: {path}")
    if acceptance.get("status") != "PASS" or acceptance.get("submitted_code_sha") != submitted:
        raise BundleError("M06 acceptance evidence does not pass for submitted code")

    normal_trials = 0
    try:
        with (evidence_root / "trials.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                trial = json.loads(line)
                normal_trials += trial.get("mode") == "normal"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M06 raw trial evidence is missing or invalid: {exc}") from exc
    if normal_trials != 48 or not (evidence_root / "trials.csv").is_file():
        raise BundleError("M06 raw trial outputs do not contain the complete normal panel")

    circuit_dir = root / "data" / "compiled" / "escape"
    try:
        manifest = json.loads((circuit_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M06 accepted compact circuit is unavailable: {exc}") from exc
    if manifest.get("semantic_digest", {}).get("value") != (
        "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5"
    ):
        raise BundleError("M06 compact circuit identity differs from accepted M04")
    for path in sorted(circuit_dir.iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if len(data) > MAX_INCLUDED_FILE_BYTES:
            raise BundleError(f"M06 compact circuit artifact is unexpectedly large: {path.name}")
        entries[f"data/compiled/escape/{path.name}"] = data


def build_bundle(root: Path, milestone: str, attempt: int, base_arg: str) -> bytes:
    submitted = str(git(root, "rev-parse", "HEAD")).strip()
    status = str(git(root, "status", "--porcelain=v1", "--untracked-files=all"))
    if status:
        raise BundleError("working tree has tracked or non-ignored changes; refusing to certify a dirty code tree")

    if base_arg == "EMPTY":
        if milestone != "M01":
            raise BundleError("EMPTY is only valid for M01")
        base = "EMPTY"
        diff_base = EMPTY_TREE_SHA
    else:
        base = str(git(root, "rev-parse", "--verify", f"{base_arg}^{{commit}}")).strip()
        diff_base = base

    architecture_path = root / "docs" / "architecture.md"
    if not architecture_path.is_file():
        raise BundleError("docs/architecture.md is missing")
    architecture_sha = sha256(architecture_path.read_bytes())
    if architecture_sha != ARCHITECTURE_SHA256:
        raise BundleError(
            f"architecture mismatch: computed {architecture_sha}, expected {ARCHITECTURE_SHA256}"
        )

    entries: dict[str, bytes] = {}
    omitted: list[dict[str, Any]] = []
    repo_paths: list[str] = []
    for path in tracked_paths(root, submitted):
        pure = PurePosixPath(path)
        reason = exclusion_reason(pure)
        data = commit_blob(root, submitted, path)
        if reason:
            raise BundleError(f"tracked forbidden path {path!r}: {reason}")
        if len(data) > MAX_INCLUDED_FILE_BYTES:
            raise BundleError(f"tracked path {path!r} exceeds the bounded M01 snapshot limit")
        entries[f"repo/{path}"] = data
        repo_paths.append(path)

    if "ledger.yaml" not in repo_paths:
        raise BundleError("committed ledger.yaml is missing")
    entries["ledger.yaml"] = commit_blob(root, submitted, "ledger.yaml")
    entries["tree.txt"] = ("\n".join(repo_paths) + "\n").encode("utf-8")
    entries["git_status.txt"] = status.encode("utf-8")
    diff = git(root, "diff", "--binary", diff_base, submitted, "--", text=False)
    assert isinstance(diff, bytes)
    entries["git_diff.patch"] = diff

    add_base(entries, root, base, submitted)
    evidence_root = root / "evidence" / milestone
    add_evidence(entries, evidence_root, omitted)
    if milestone == "M02":
        omitted.extend(m02_large_source_inventory(root, submitted, evidence_root))
    if milestone == "M03":
        omitted.extend(m03_large_graph_inventory(root, submitted, evidence_root))
    if milestone == "M04":
        omitted.extend(m04_material(root, submitted, evidence_root, entries))
    if milestone == "M05":
        m05_material(root, submitted, evidence_root)
    if milestone == "M06":
        m06_material(root, submitted, evidence_root, entries)

    large_files = {
        "schema_version": 1,
        "milestone": milestone,
        "omitted": omitted,
        "statement": (
            "No legitimate large files were omitted."
            if not omitted
            else "The listed files were omitted for the stated bounded-review reason; identities come from committed configuration and captured evidence."
        ),
    }
    entries["large-files.json"] = json_bytes(large_files)

    reports = load_command_reports(evidence_root)
    try:
        tooling_value = json.loads(commit_blob(root, submitted, "tooling.json").decode("utf-8"))
    except (BundleError, UnicodeDecodeError, json.JSONDecodeError):
        tooling_value = None
    try:
        m03_audit = json.loads((evidence_root / "full-audit.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m03_audit = None
    try:
        m03_determinism = json.loads(
            (evidence_root / "determinism.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m03_determinism = None
    try:
        m04_mapping = json.loads(
            (evidence_root / "mapping.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m04_mapping = None
    try:
        m04_decision = json.loads(
            (evidence_root / "decision.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m04_decision = None
    try:
        m04_audit = json.loads(
            (evidence_root / "circuit-audit.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m04_audit = None
    try:
        m05_decision = json.loads(
            (evidence_root / "decision.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m05_decision = None
    try:
        m05_convergence = json.loads(
            (evidence_root / "timestep-convergence.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m05_convergence = None
    try:
        m05_analytical = json.loads(
            (evidence_root / "analytical-fixtures.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m05_analytical = None
    try:
        m05_boundary = json.loads(
            (evidence_root / "boundary-fixtures.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m05_boundary = None
    try:
        m06_decision = json.loads(
            (evidence_root / "decision.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m06_decision = None
    try:
        m06_calibration = json.loads(
            (evidence_root / "calibration-summary.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m06_calibration = None
    try:
        m06_authority = json.loads(
            (evidence_root / "authority.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m06_authority = None
    try:
        m06_dependencies = json.loads(
            (evidence_root / "decoder-dependency.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m06_dependencies = None
    entries["REVIEW.md"] = render_review(
        milestone,
        attempt,
        base,
        submitted,
        architecture_sha,
        reports,
        tooling_value,
        (evidence_root / "manual-source-review.txt").is_file(),
        m03_audit,
        m03_determinism,
        m04_mapping,
        m04_decision,
        m04_audit,
        m05_decision,
        m05_convergence,
        m05_analytical,
        m05_boundary,
        m06_decision,
        m06_calibration,
        m06_authority,
        m06_dependencies,
    )

    manifest = {
        "schema": "flybench-review-manifest",
        "version": 1,
        "milestone": milestone,
        "attempt": attempt,
        "base_identity": base,
        "submitted_code_sha": submitted,
        "architecture_sha256": architecture_sha,
        "inventory": inventory(entries),
        "unhashed_entries": ["review-manifest.json"],
    }
    entries["review-manifest.json"] = json_bytes(manifest)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(entries):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, entries[path])
    value = archive.getvalue()
    if len(value) >= MAX_ARCHIVE_BYTES:
        raise BundleError(f"review bundle is {len(value)} bytes, exceeding the 15 MiB review limit")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--milestone", required=True)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.attempt < 1:
        parser.error("--attempt must be positive")

    root = Path.cwd().resolve()
    output = args.out if args.out.is_absolute() else root / args.out
    try:
        bundle = build_bundle(root, args.milestone, args.attempt, args.base)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_bytes(bundle)
        os.replace(temporary, output)
    except (BundleError, OSError) as exc:
        print(f"review bundle failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {output} ({len(bundle)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
