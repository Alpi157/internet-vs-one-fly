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
PLAN_V2_SHA256 = "ef97902c9393d416bf25007643c09e1410cfde3d92a7130ae847559beee73016"
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
    m07_decision: dict[str, Any] | None,
    m07_candidate: dict[str, Any] | None,
    m07_circuit_performance: dict[str, Any] | None,
    m07_full_performance: dict[str, Any] | None,
    m08_decision: dict[str, Any] | None,
    m08_identity: dict[str, Any] | None,
    m08_smoke: dict[str, Any] | None,
    m09_evidence: dict[str, dict[str, Any]],
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
    elif milestone == "M07":
        objective = (
            "Implement one restricted deterministic CPU backend, prove reference/kernel "
            "parity, and make the bounded G-FULL initial live-graph decision."
        )
        assumptions = [
            "The accepted M03 graph identities and M05/M06 scientific semantics, controller parameters, and authority boundaries remain unchanged.",
            "The Numba backend is serial, float64-state, source-major over active scheduled sources, and uses neither parallel accumulation nor fast math.",
            "Each full-graph repeat is independently terminable at the predeclared 60 second wall bound; timeout and partial completion are not completed samples.",
            "The 7 ms value is provisional headroom and 10 ms is the control deadline; all measured activity and edge work accompany timings.",
            "The selected live candidate and all host feasibility remain provisional until external M07 review and final M15 host-capacity work.",
        ]
    elif milestone == "M08":
        objective = (
            "Build the first local playable Catch the Fly loop around the accepted Runner, "
            "then evaluate its mechanics through bounded automation and operator-supplied human evidence."
        )
        assumptions = [
            "The accepted 313-neuron circuit, deterministic Numba kernel, ModelSpec, controller, encoder, decoder, environment, clock, and Runner order remain unchanged.",
            "Strike coordinates affect only the M08 geometric collision rule; the neural input remains the accepted non-directional scalar looming schedule and the decoder receives no threat geometry.",
            "Walking, takeoff, strike timing, radius, cooldown, attempt count, and round horizon are provisional game mechanics, not physiology or biomechanics.",
            "The audited 166,700-neuron graph is not executed by the live game and is not presented as the live neuron count.",
            "The human receipts are usability and restricted-host smoke evidence; they are not biological validation, retention evidence, or external milestone acceptance.",
        ]
    elif milestone == "M09":
        objective = (
            "Repair the three remaining M09-a02 review findings while preserving the "
            "bounded v0.2 recorder and its scientific capture envelope."
        )
        assumptions = [
            "M09 attempt 1 received CHANGES REQUIRED; M09 attempt 2 received CHANGES REQUIRED; this is review attempt 3. Both earlier archives remain immutable superseded history.",
            "M09 was implemented AT RISK under D-M08-HUMAN-GATE-DEFER-01; M08 G-GAME remains pending and unmeasured.",
            "M09 implementation and recorder evidence are not evidence that M08 passed usability, and public release remains blocked by the deferred human gate.",
            "The M09 bench recording mode runs the stable selected accepted standard-looming fixture with recording disabled and enabled; it is not a rerun or recalibration of the full frozen M06 protocol.",
            "Accepted coordinates use flybench.coordinate-binary64.v1 before authoritative application, and the recorder copies that exact binary64 without a decimal grid or recorder-only rounding.",
            "Periodic/final hashes capture the declared whole-state envelope without storing full per-neuron arrays; M09 states capture eligibility only, never that exact re-execution has passed.",
            "Exact re-execution is NOT verified by M09. M10 owns re-execution verification and first-divergence testing, and M10 has not started.",
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
        *(
            [
                "- Last accepted product implementation SHA before M08: `c2b0dc064fa1f8d50b01f595f0232f8d9b37d5e5`."
            ]
            if milestone == "M08"
            else []
        ),
        *(
            [
                "- Frozen provisional M08 integration baseline: `76ccadccab5c37626557c6ff4b8a565d3c387c4f`.",
                "- Process-deviation decision: `D-M08-HUMAN-GATE-DEFER-01` (`79d9a7e68e4d2d865411c2bb00fa62295fec503c976f38c4d579f8d077212a89`).",
            ]
            if milestone == "M09"
            else []
        ),
        *(
            [
                "- M09-a01 candidate product SHA: `067b3c831469ce2475201074ad47b39853694b60`.",
                "- M09-a01 final submission SHA: `d15bae9ccc6e8bf2952b5d14adaaaf06a86fd3dc`.",
                "- Superseded M09-a01 review ZIP SHA-256: `cff7e065c6a45aade81e23614e0a00d7eb0ed379d5422531e68ba4f629f9ea66`.",
                "- M09-a01 external verdict: `CHANGES REQUIRED`.",
            ]
            if milestone == "M09" and attempt in {2, 3}
            else []
        ),
        *(
            [
                "- M09-a02 candidate product SHA: `d900fd407119ae7289bcbc2170492e7ee057ae6e`.",
                "- M09-a02 final submission SHA: `057bf62587516bd0e1e12ada0eb0afb454656c1a`.",
                "- Superseded M09-a02 review ZIP SHA-256: `cf3d09f22427eb30e07937867127f1060beed2abc8a6b0b17473d34df2d3a0b7`.",
                "- M09-a02 external verdict: `CHANGES REQUIRED`.",
            ]
            if milestone == "M09" and attempt == 3
            else []
        ),
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
    if milestone == "M07" and m07_decision:
        lines.extend(
            [
                f"- G-FULL candidate decision: `{m07_decision.get('outcome')}`; selection `{m07_decision.get('selection')}`; external milestone acceptance remains `{m07_decision.get('external_milestone_acceptance')}`.",
                f"- Kernel parity: `{m07_decision.get('kernel_parity_status')}`; full authority carryover: `{m07_decision.get('full_authority_carryover_status')}`.",
                f"- Full-graph failed conditions: `{m07_decision.get('failed_full_graph_conditions')}`.",
            ]
        )
    if milestone == "M07" and m07_candidate:
        graph = m07_candidate.get("graph", {})
        lines.append(
            f"- Candidate graph/backend: digest `{graph.get('semantic_digest')}`, N `{graph.get('N')}`, E `{graph.get('E')}`, contacts `{graph.get('contacts')}`, backend `{m07_candidate.get('backend')}`."
        )
        lines.append(
            f"- Measurement evidence digest: `{m07_candidate.get('measurement_evidence_sha256')}`; optimization passes `{m07_candidate.get('optimization_passes_used')}`."
        )
    if milestone == "M07":
        for graph_name, performance in (
            ("circuit", m07_circuit_performance),
            ("full", m07_full_performance),
        ):
            if not performance:
                continue
            for workload, result in performance.get("workloads", {}).items():
                metrics = result.get("metrics") or {}
                lines.append(
                    f"- {graph_name} `{workload}`: complete repeats `{result.get('complete_repeat_count')}`; timeouts `{result.get('timeout_repeat_count')}`; p99 ns `{metrics.get('p99_ns')}`; >10 ms `{metrics.get('count_interval_gt_10_ms')}`."
                )
    if milestone == "M08" and m08_decision:
        lines.extend(
            [
                f"- G-GAME proposed outcome: `{m08_decision.get('proposed_outcome')}`; external milestone acceptance remains `{m08_decision.get('external_milestone_acceptance')}`.",
                f"- Human-evaluation candidate product SHA: `{m08_decision.get('candidate_product_sha')}`.",
                f"- Final M08 submission SHA: `{submitted}`.",
            ]
        )
    if milestone == "M08" and m08_identity:
        graph = m08_identity.get("graph", {})
        lines.extend(
            [
                f"- Live profile SHA-256: `{m08_identity.get('live_profile_sha256')}`; GameSpec SHA-256: `{m08_identity.get('game_spec_sha256')}`.",
                f"- Executed live scope: N `{graph.get('N')}`, E `{graph.get('E')}`, represented contacts `{graph.get('represented_contacts')}`, backend `{m08_identity.get('backend', {}).get('name')}`.",
            ]
        )
    if milestone == "M08" and m08_smoke:
        lines.append(
            f"- Bounded loopback server smoke: `{m08_smoke.get('status')}`; clean termination `{m08_smoke.get('server_terminated_cleanly')}`; bind `{m08_smoke.get('bind_host')}`."
        )
    if milestone == "M09" and m09_evidence:
        recorder = m09_evidence.get("recorder-format.json", {})
        deterministic = m09_evidence.get("deterministic-recording.json", {})
        authority = m09_evidence.get("applied-input-authority.json", {})
        safety = m09_evidence.get("archive-safety.json", {})
        parity = m09_evidence.get("headless-server-recorder-parity.json", {})
        state = m09_evidence.get("state-digest-validation.json", {})
        coalescing = m09_evidence.get("input-coalescing.json", {})
        ordering = m09_evidence.get("input-ordering.json", {})
        bench = m09_evidence.get("bench-recording.json", {})
        quantization = m09_evidence.get("coordinate-quantization.json", {})
        recording_parity = m09_evidence.get("recording-parity.json", {})
        demo = m09_evidence.get("demo-recording-smoke.json", {})
        decision = m09_evidence.get("decision.json", {})
        lines.extend(
            [
                f"- Recorder format: `{recorder.get('format_id')}`; fixture bytes `{recorder.get('fixture_bytes')}`; content digest `{recorder.get('content_digest')}`.",
                f"- Deterministic recording evidence: `{deterministic.get('status')}`; applied-input authority: `{authority.get('status')}`; archive safety: `{safety.get('status')}`; headless/server-recorder parity: `{parity.get('status')}`.",
                f"- Whole-state digest validation: `{state.get('status')}`; coalescing: `{coalescing.get('status')}`; equal-tick ordering: `{ordering.get('status')}`.",
                f"- Bench recording integration: `{bench.get('status')}`; cross-path recording parity: `{recording_parity.get('status')}`; bounded demo recording integration: `{demo.get('status')}`.",
                f"- Coordinate quantization: `{quantization.get('quantization_identity')}`; numerical gameplay change: `{quantization.get('numerical_gameplay_change')}`.",
                f"- M09 attempt-3 product candidate SHA: `{decision.get('candidate_product_sha')}`; final submission SHA: `{submitted}`.",
                f"- M09 proposed outcome: `{decision.get('proposed_outcome')}`; external milestone acceptance remains `{decision.get('external_milestone_acceptance')}`.",
                "- The capture envelope is present and eligible for later M10 checking; exact re-execution remains unverified.",
                "- M08 G-GAME remains `PENDING_UNMEASURED`; this M09 evidence does not establish M08 usability.",
                "- M10 is `NOT_STARTED`.",
            ]
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
    if milestone == "M08":
        lines.extend(
            [
                "- `evidence/M08/manual/playtests.json`: present and schema/hash checked with at least three anonymized unfamiliar-player entries.",
                "- `evidence/M08/manual/host-smoke.json`: present and schema/hash checked as operator-supplied restricted-host evidence.",
                "- `evidence/M08/manual/manual-game-review.txt`: present, non-placeholder, and bound to the candidate product SHA.",
                "- Gameplay screenshot and short actual-execution clip: present and included subject to the bundle size bound.",
            ]
        )
    if milestone == "M09":
        lines.extend(
            [
                "- One operator-created completed local demo recording is included only as real-path recorder integration evidence; it is not an unfamiliar-user test.",
                "- M08 unfamiliar-player playtests remain unavailable and are not claimed in this bundle.",
                "- M08 representative remote-host human smoke remains incomplete and is not claimed in this bundle.",
                "- No M08 G-GAME receipt, media set, or general-user usability claim is supplied by M09.",
            ]
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
    if milestone == "M09":
        lines.extend(
            [
                "- Exact deterministic re-execution has not been tested; M10 owns verification and first-divergence detection.",
                "- M08 G-GAME remains pending/unmeasured under the recorded process deviation.",
                "- Public alpha and public release remain blocked on the deferred M08 human evidence.",
                "- If later M08 testing changes game, UI, or GameSpec behavior, affected M09 integration evidence must be rerun.",
            ]
        )
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
                                else (
                                    "- This archive contains the M07 kernel, frozen parity/probe profiles, raw bounded timing evidence, memory/hardware receipts, and G-FULL candidate decision. Full graph arrays remain omitted with exact identities."
                                    if milestone == "M07"
                                    else (
                                        "- This archive contains the M08 local game/server/frontend implementation, exact lockfiles, automated evidence, operator receipts, bounded media, and compact accepted circuit. Raw MaleCNS and full 166,700-neuron arrays remain excluded."
                                        if milestone == "M08"
                                        else (
                                            "- This archive contains the M09 attempt-3 v0.2 recorder repair, explicit parity tests, meaningful selected-benchmark output, binary64 coordinate decision/evidence, demo/bench/headless evidence, periodic whole-state digests, safety fixtures, the operator demo artifact, and compact accepted circuit. Raw MaleCNS and full graph arrays remain excluded."
                                            if milestone == "M09"
                                            else "- This archive covers M01 infrastructure only and contains no scientific-result evidence."
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            ),
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def render_v2a_review(
    base: str,
    submitted: str,
    architecture_sha: str,
    reports: list[tuple[str, dict[str, Any]]],
    evidence_root: Path,
) -> bytes:
    primary = next((report for path, report in reports if path == "acceptance/command-results.json"), None)
    if primary is None:
        primary = next((report for path, report in reports if path == "command-results.json"), None)
    try:
        p0 = json.loads((evidence_root / "p0/findings.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        p0 = {}
    try:
        p1 = json.loads(
            (evidence_root / "p1/circuit-size-survey.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        p1 = {}
    lines = [
        "# V2A review submission (attempt 1)",
        "",
        "## Status",
        "",
        "V2A is SUBMITTED. External review remains pending. This document does not mark the stage accepted.",
        "",
        "## Identities",
        "",
        f"- BASE_SHA: `{base}`.",
        f"- Submitted commit SHA: `{submitted}`.",
        f"- Plan v2 SHA-256: `{PLAN_V2_SHA256}`.",
        f"- Architecture v1 SHA-256: `{architecture_sha}`.",
        "",
        "## Work completed",
        "",
        "- A0: committed plan v2 unchanged as the first stage commit, preserved the v1 ledger under docs/history, installed ledger schema 2, rewrote repository instructions, updated scaffold checks, and recorded D-V2-01.",
        "- A1: measured the unchanged accepted game with declared bot limits, accepted-neural, fixed-latency, and no-escape controllers, then ran the accepted circuit and full graph context check.",
        "- A2: inventoried annotations, reported walking DN candidates without finalizing ports, split visual ports by somaSide, surveyed deterministic provisional circuits, measured kernel cost, generated null diagnostics, and added the licensed compact fixture.",
        "",
        "## Commands and exit codes",
        "",
    ]
    if primary:
        for command in primary.get("commands", []):
            argv = json.dumps(command.get("argv", []), ensure_ascii=False)
            lines.append(
                f"- `{command.get('name')}`: argv `{argv}`; cwd `{command.get('cwd')}`; exit `{command.get('exit_status')}`; status `{command.get('status')}`."
            )
    else:
        lines.append("- No final acceptance command report was found.")
    failures = [
        command
        for command in (primary or {}).get("commands", [])
        if command.get("exit_status") != 0
    ]
    lines.extend(["", "## Failures", ""])
    if failures:
        for command in failures:
            lines.append(
                f"- `{command.get('name')}` failed with exit `{command.get('exit_status')}`: {command.get('failure_reason')}."
            )
    else:
        lines.append("- No failure is recorded in the final acceptance report.")
    lines.extend(
        [
            "- Pre-final full regression exited `1`: the v1 lifecycle assertion did not recognize ledger schema 2, and six source-fetch tests could not bind a loopback port inside the restricted sandbox. The lifecycle assertion was updated for v2, and the final suite passed with loopback permission.",
            "- Pre-final fresh-clone setup exited `1` because restricted sandbox DNS blocked the locked dependency download. The approved rerun and the final acceptance command passed.",
            "- A pre-final acceptance rerun exited `1` after commands 1 through 5 passed because `/tmp/flybench-clean` already existed, so the required `git clone` command exited `128`. The stale temporary clone was removed before the final acceptance run.",
        ]
    )
    lines.extend(["", "## Blockers", ""])
    lines.extend(
        [
            "- External review of walking DN candidate identities is required before any walking port is finalized.",
            "- V2A external review is pending.",
            "- Soft-launch evidence required by plan v2 has not been collected.",
        ]
    )
    lines.extend(["", "## Surprises", ""])
    bot_checks = p0.get("bot_checks", {})
    fixed_latency = bot_checks.get("fixed_latency_ms_from_global_neural_median")
    if fixed_latency is not None:
        lines.append(
            f"- The accepted-neural global median command offset was `{fixed_latency}` ms before impact."
        )
    degenerate = []
    for name, value in bot_checks.get("strategies", {}).items():
        rate = value.get("controllers", {}).get("accepted-neural", {}).get("catch", {}).get("catch_rate")
        if rate in {0.0, 1.0}:
            degenerate.append(f"{name}={rate}")
    lines.append(
        "- Accepted-neural degenerate catch rates were observed: "
        + (", ".join(degenerate) if degenerate else "none")
        + "."
    )
    context = p0.get("context_check", {})
    circuit_context = context.get("accepted_circuit", {})
    full_context = context.get("full_graph", {})
    lines.append(
        f"- Context status was circuit `{circuit_context.get('status')}` and full graph `{full_context.get('status')}`; full-graph outside-circuit spiking neurons were `{full_context.get('outside_accepted_circuit_spiking_neurons')}`."
    )
    circuits = p1.get("circuits", [])
    if circuits:
        lines.append(
            f"- The provisional survey ranged from N `{min(item['N'] for item in circuits)}` to `{max(item['N'] for item in circuits)}` and E `{min(item['E'] for item in circuits)}` to `{max(item['E'] for item in circuits)}`."
        )
    lines.extend(
        [
            "",
            "## Scope limits",
            "",
            "- No encoder, decoder, accepted controller, accepted model, accepted game profile, or kernel semantic was changed.",
            "- No behavior run was performed on a surveyed circuit or null graph.",
            "- Walking DN matches remain candidates and are not finalized mappings.",
            "- Raw MaleCNS sources and full graph arrays are excluded from this review ZIP.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def render_v2b_review(
    base: str,
    submitted: str,
    architecture_sha: str,
    reports: list[tuple[str, dict[str, Any]]],
    evidence_root: Path,
) -> bytes:
    primary = next((report for path, report in reports if path == "acceptance/command-results.json"), None)
    try:
        circuits = json.loads((evidence_root / "p1/circuits.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        circuits = {}
    try:
        dry_run = json.loads((evidence_root / "p2/dry-run.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        dry_run = {}
    try:
        parity = json.loads((evidence_root / "p3/kernel-ts-parity.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        parity = {}
    try:
        comparison = json.loads((evidence_root / "b0/null-key-comparison.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        comparison = {}
    lines = [
        "# V2B review submission (attempt 1)",
        "",
        "## Status",
        "",
        "V2B is SUBMITTED. External review remains pending. This document does not mark V2B accepted.",
        "",
        "## Identities",
        "",
        f"- BASE_SHA: `{base}`.",
        f"- Submitted commit SHA: `{submitted}`.",
        f"- Plan v2 SHA-256: `{PLAN_V2_SHA256}`.",
        f"- Architecture v1 SHA-256: `{architecture_sha}`.",
        "",
        "## Block status",
        "",
        "- B0 COMPLETE: recorded the external V2A verdict and conditions, corrected V2A findings, changed null reachability keys to body IDs, and generalized lifecycle tests.",
        "- B1 COMPLETE: reported round-two walking candidates, the unresolved DNa01 conflict, literature-edge consistency, and the 11-neuron context follow-up.",
        "- B2 COMPLETE: installed final reviewer-receipt ports and explicitly provisional exact-type ports in `profiles/ports-v2.json`.",
        "- B3 COMPLETE: built and audited T1a, T1b, and T2 with provisional-seed status.",
        "- B4 COMPLETE: added the integer RNG, restricted approximations, vectors, and statistical sanity report.",
        "- B5 COMPLETE: added isolated v2 reference and Numba noise paths, encoder, spike-only decoder, body kinematics, cards, and parity tests.",
        "- B6 COMPLETE AS DRAFT: wrote the calibration protocol and executed only the declared dry run. The protocol remains DRAFT_REVIEW_REQUIRED.",
        "- B7 COMPLETE FOR INITIAL KERNEL: added compact export, dependency-free TypeScript kernel, detmath parity, fixture parity, T1a noise parity, and timings. Browser testing remains out of scope.",
        "",
        "## Commands and exit codes",
        "",
    ]
    if primary:
        for command in primary.get("commands", []):
            argv = json.dumps(command.get("argv", []), ensure_ascii=False)
            lines.append(
                f"- `{command.get('name')}`: argv `{argv}`; cwd `{command.get('cwd')}`; exit `{command.get('exit_status')}`; status `{command.get('status')}`."
            )
    else:
        lines.append("- No final acceptance command report was found.")
    final_failures = [command for command in (primary or {}).get("commands", []) if command.get("exit_status") != 0]
    lines.extend(["", "## Failures", ""])
    if final_failures:
        for command in final_failures:
            lines.append(f"- Final `{command.get('name')}` exited `{command.get('exit_status')}`: {command.get('failure_reason')}.")
    else:
        lines.append("- No failure is recorded in the final acceptance report.")
    lines.extend(
        [
            "- Pre-final scaffold tests exited `1` because the tooling availability branch handled V2A SUBMITTED but not V2A ACCEPTED. The lifecycle test was generalized and passed.",
            "- Three pre-final `uv run` commands exited `2` because the default user cache was read-only in the sandbox. Subsequent commands used the writable declared temporary cache.",
            "- The first calibration dry run exited `1` because T1b contains one source self-loop and simple null graphs forbid self-loops. Null generation now performs one deterministic degree-preserving preliminary swap for T1b and records the repair; the real T1b graph is unchanged.",
            "- Initial Python and Numba noise parity tests exited `1` on bitwise state digests. Float64 executable weights and scalar reference operation order resolved the discrepancy without changing v1 code.",
            "- The first TypeScript parity run exited `1` because a pre-fix T1a binary placed a uint64 section at an unaligned offset. The exporter now aligns every typed-array section and both parity cases pass.",
        ]
    )
    lines.extend(["", "## Review conditions", ""])
    lines.append(
        f"- C3 comparison status: `{comparison.get('status')}` across `{comparison.get('null_diagnostics_compared')}` null diagnostics. All seeds and non-key fields were identical; only reachability and shortest-path keys changed from local indices to body IDs."
    )
    lines.extend(["", "## Blockers", ""])
    lines.extend(
        [
            "- DNp09, DNg13, and DNb02 ports remain provisional pending external review.",
            "- DNa01 versus DNae001 remains unresolved and is excluded from ports.",
            "- Calibration cannot be frozen: every dry-run row was silent without threat and no row produced spontaneous movement.",
            "- The dry run produced matched non-looming escape intervals while looming produced none.",
            "- Soft-launch evidence remains unavailable.",
        ]
    )
    lines.extend(["", "## Surprises", ""])
    circuit_values = circuits.get("circuits", [])
    if circuit_values:
        lines.append(
            "- Circuit sizes were "
            + ", ".join(f"{value['candidate']} N={value['N']} E={value['E']}" for value in circuit_values)
            + "."
        )
    rows = dry_run.get("rows", [])
    if rows:
        lines.append(f"- All `{sum(bool(row.get('silence')) for row in rows)}` of `{len(rows)}` dry-run rows were silent without threat.")
        lines.append(
            f"- Dry-run escape intervals were looming `{sum(row['escape_counts']['looming'] for row in rows)}` and matched non-looming `{sum(row['escape_counts']['matched-non-looming'] for row in rows)}`."
        )
    if parity:
        lines.append(
            f"- TypeScript parity status was `{parity.get('status')}`; fixture wall seconds per simulated second `{parity.get('fixture_v1_v2a_bot_log', {}).get('wall_seconds_per_simulated_second')}` and T1a `{parity.get('t1a_noise_one_second', {}).get('wall_seconds_per_simulated_second')}`."
        )
    lines.extend(
        [
            "",
            "## Scope limits",
            "",
            "- No v1 live profile, accepted game, controller, encoder, decoder, or kernel semantics changed.",
            "- No calibration setting was selected or frozen, and no H1 or H2 conclusion was drawn.",
            "- No provisional port was finalized and the DNa01 conflict was not resolved.",
            "- No browser matrix, web UI, hosting, or server change is included.",
            "- Full MaleCNS sources and generated graph arrays are excluded from this review ZIP.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def add_evidence(
    entries: dict[str, bytes],
    evidence_root: Path,
    omitted: list[dict[str, Any]],
    *,
    preview_limit: int = MAX_INCLUDED_FILE_BYTES,
) -> None:
    if not evidence_root.is_dir():
        entries["evidence/README.txt"] = b"No generated evidence directory was present at bundle time.\n"
        return
    included = 0
    for path in sorted(evidence_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = PurePosixPath(path.relative_to(evidence_root).as_posix())
        if evidence_root.name in {"V2E", "V2F"} and (relative.suffix in {".npy", ".npz", ".webbin"} or
            (len(relative.parts)>2 and relative.parts[0]=="results" and relative.parts[1] in {"H0","calibration","H1","H2","fixed","controls","H0-STR","H0-FULL","H0-T2","E1","E2a","E3-low","E3-high"} and relative.name.endswith(".json.gz") and not (relative.parts[1]=="calibration" and "-REAL-" in relative.name))):
            size, digest = sha256_file(path)
            omitted.append({"path":f"evidence/{relative}","bytes":size,"sha256":digest,
                "reason":"V2E/V2F bounded archive: graph arrays or raw task records; summaries and run status retained"})
            continue
        reason = exclusion_reason(relative)
        size = path.stat().st_size
        if reason or size > preview_limit:
            data = path.read_bytes() if not reason else b""
            preview_path = None
            if data:
                preview_path = f"evidence-previews/{relative.as_posix()}.preview.txt"
                preview = data[:65536]
                if len(data) > 131072:
                    preview += b"\n\n[... middle omitted ...]\n\n" + data[-65536:]
                entries[preview_path] = preview
            omitted.append(
                {
                    "path": f"evidence/{relative.as_posix()}",
                    "reason": reason or "file exceeds bounded per-file review size",
                    "bytes": size,
                    "sha256": sha256(data) if data else None,
                    "preview_path": preview_path,
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


def m07_material(
    root: Path,
    submitted: str,
    evidence_root: Path,
    entries: dict[str, bytes],
) -> list[dict[str, Any]]:
    """Validate M07 decision evidence, include the circuit, and inventory full arrays."""

    required: dict[str, dict[str, Any]] = {}
    for name in (
        "hardware.json",
        "kernel-parity.json",
        "circuit-performance.json",
        "full-performance.json",
        "memory.json",
        "timeout-test.json",
        "full-authority-carryover.json",
        "optimization.json",
        "live-candidate.json",
        "decision.json",
        "command-results.json",
    ):
        try:
            required[name] = json.loads(
                (evidence_root / name).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"M07 {name} is missing or invalid: {exc}") from exc
    decision = required["decision.json"]
    candidate = required["live-candidate.json"]
    parity = required["kernel-parity.json"]
    timeout = required["timeout-test.json"]
    memory = required["memory.json"]
    optimization = required["optimization.json"]
    acceptance = required["command-results.json"]
    if (
        decision.get("gate") != "G-FULL"
        or decision.get("outcome") != "PASS"
        or decision.get("selection") not in {"PROVISIONAL_FULL", "DISCLOSED_CIRCUIT"}
        or decision.get("external_milestone_acceptance") != "PENDING"
    ):
        raise BundleError("M07 G-FULL candidate decision is incomplete")
    if (
        parity.get("status") != "PASS"
        or parity.get("circuit_gbio_preservation", {}).get("status") != "PASS"
        or parity.get("kernel_configuration", {}).get("parallel") is not False
        or parity.get("kernel_configuration", {}).get("fastmath") is not False
    ):
        raise BundleError("M07 kernel/circuit parity evidence does not pass")
    forced = timeout.get("forced_timeout_result", {})
    if (
        timeout.get("status") != "PASS"
        or forced.get("status") != "TIMEOUT"
        or forced.get("worker_alive_after_join") is not False
        or forced.get("temporary_worker_state_released") is not True
    ):
        raise BundleError("M07 timeout evidence does not prove termination and cleanup")
    if memory.get("status") != "COMPLETE" or any(
        memory.get("graphs", {}).get(graph) is None for graph in ("circuit", "full")
    ):
        raise BundleError("M07 graph/state/RSS memory evidence is incomplete")
    if optimization.get("optimization_passes_used") not in (0, 1):
        raise BundleError("M07 optimization-pass count is invalid")
    if (
        acceptance.get("status") != "PASS"
        or acceptance.get("submitted_code_sha") != submitted
    ):
        raise BundleError("M07 acceptance evidence does not pass for submitted code")
    try:
        committed_candidate = json.loads(
            commit_blob(root, submitted, "profiles/live-candidate-v0.1.json")
        )
    except (BundleError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"committed M07 candidate is invalid: {exc}") from exc
    if candidate != committed_candidate:
        raise BundleError("M07 committed and evidence candidate profiles differ")
    if (
        candidate.get("g_full_decision") != decision.get("selection")
        or candidate.get("implementation", {}).get("kernel_source_sha256")
        != sha256(commit_blob(root, submitted, "src/flybench/kernel.py"))
        or candidate.get("optimization_passes_used")
        != optimization.get("optimization_passes_used")
        or candidate.get("external_milestone_acceptance") != "PENDING"
    ):
        raise BundleError("M07 candidate identities are inconsistent")
    raw_path = evidence_root / "raw-interval-timings.jsonl"
    if not raw_path.is_file() or not raw_path.stat().st_size:
        raise BundleError("M07 raw interval timings are missing")

    circuit_dir = root / "data" / "compiled" / "escape"
    full_dir = root / "data" / "compiled" / "full"
    try:
        circuit_manifest = json.loads((circuit_dir / "manifest.json").read_text())
        full_manifest = json.loads((full_dir / "manifest.json").read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M07 compiled graph manifest unavailable: {exc}") from exc
    if circuit_manifest.get("semantic_digest", {}).get("value") != (
        "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5"
    ):
        raise BundleError("M07 circuit identity differs from accepted M04")
    if full_manifest.get("semantic_digest", {}).get("value") != (
        "429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0"
    ):
        raise BundleError("M07 full graph identity differs from accepted M03")
    for path in sorted(circuit_dir.iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if len(data) > MAX_INCLUDED_FILE_BYTES:
            raise BundleError(f"M07 compact circuit artifact is too large: {path.name}")
        entries[f"data/compiled/escape/{path.name}"] = data
    for name in ("manifest.json", "selection-profile.json", "source-lock.json"):
        entries[f"data/compiled/full/{name}"] = (full_dir / name).read_bytes()

    omitted: list[dict[str, Any]] = []
    for name, item in sorted(full_manifest.get("arrays", {}).items()):
        path = full_dir / item["filename"]
        size, digest = sha256_file(path)
        if size != item.get("bytes") or digest != item.get("sha256"):
            raise BundleError(f"M07 full graph array differs from manifest: {name}")
        omitted.append(
            {
                "path": f"data/compiled/full/{item['filename']}",
                "reason": "accepted M03 full graph array omitted from bounded M07 review ZIP",
                "array_name": name,
                "bytes": size,
                "sha256": digest,
                "dtype": item.get("dtype"),
                "shape": item.get("shape"),
                "graph_semantic_digest": full_manifest["semantic_digest"]["value"],
                "source_lock_sha256": full_manifest.get("source_lock_sha256"),
            }
        )
    return omitted


def m08_material(
    root: Path,
    submitted: str,
    evidence_root: Path,
    entries: dict[str, bytes],
) -> list[dict[str, Any]]:
    """Validate M08 receipts/identities and include only the accepted compact circuit."""

    checker = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "check_m08_evidence.py"),
            "--out",
            str(evidence_root),
            "--phase",
            "final",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if checker.returncode:
        raise BundleError(f"M08 evidence validation failed: {checker.stdout}{checker.stderr}")
    required: dict[str, dict[str, Any]] = {}
    for name in (
        "identity-check.json",
        "local-server-smoke.json",
        "headless-server-parity.json",
        "decision.json",
        "command-results.json",
        "candidate.json",
    ):
        try:
            required[name] = json.loads(
                (evidence_root / name).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"M08 {name} is missing or invalid: {exc}") from exc
    decision = required["decision.json"]
    identity = required["identity-check.json"]
    smoke = required["local-server-smoke.json"]
    parity = required["headless-server-parity.json"]
    acceptance = required["command-results.json"]
    candidate = decision.get("candidate_product_sha")
    if (
        decision.get("gate") != "G-GAME"
        or decision.get("proposed_outcome") != "PASS_CANDIDATE"
        or decision.get("external_milestone_acceptance") != "PENDING"
        or candidate != required["candidate.json"].get("candidate_product_sha")
    ):
        raise BundleError("M08 G-GAME candidate decision is incomplete")
    if acceptance.get("status") != "PASS" or acceptance.get("submitted_code_sha") != submitted:
        raise BundleError("M08 acceptance evidence does not pass for the submitted SHA")
    if smoke.get("status") != "PASS" or smoke.get("bind_host") != "127.0.0.1":
        raise BundleError("M08 bounded loopback smoke does not pass")
    if parity.get("status") != "PASS" or not all(parity.get("comparisons", {}).values()):
        raise BundleError("M08 direct-session/server-adapter parity does not pass")
    if not isinstance(candidate, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise BundleError("M08 candidate product SHA is invalid")
    git(root, "merge-base", "--is-ancestor", candidate, submitted)
    changed_after_human = str(
        git(root, "diff", "--name-only", candidate, submitted, "--")
    ).splitlines()
    if set(changed_after_human) - {"ledger.yaml"}:
        raise BundleError(
            "M08 product/config/test files changed after human evaluation: "
            + ", ".join(changed_after_human)
        )
    ledger = commit_blob(root, submitted, "ledger.yaml").decode("utf-8")
    for required_text in (
        "last_accepted_milestone: M07",
        "last_accepted_code_commit: c2b0dc064fa1f8d50b01f595f0232f8d9b37d5e5",
        "M08: SUBMITTED",
        "Do not begin M09",
    ):
        if required_text not in ledger:
            raise BundleError(f"M08 submitted ledger is missing: {required_text}")
    try:
        committed_live = commit_blob(root, submitted, "profiles/live.json")
        game_profile_path = identity.get("game_spec_path")
        if game_profile_path != "profiles/game-v0.3.json":
            raise BundleError("M08 evidence does not select the bounded v0.3 GameSpec")
        committed_game = commit_blob(root, submitted, game_profile_path)
        previous_game = commit_blob(root, submitted, "profiles/game-v0.2.json")
        starting_game = commit_blob(root, submitted, "profiles/game-v0.1.json")
    except BundleError as exc:
        raise BundleError(f"committed M08 profile is unavailable: {exc}") from exc
    if committed_live != (evidence_root / "live-profile.json").read_bytes():
        raise BundleError("M08 live-profile evidence differs from committed bytes")
    if committed_game != (evidence_root / "game-spec.json").read_bytes():
        raise BundleError("M08 GameSpec evidence differs from committed bytes")
    if sha256(starting_game) != "521dc8f33457155b0f5c5438f11da2c6b489d9a5667b7d63421ed863fbb62cd7":
        raise BundleError("M08 historical starting GameSpec identity was not preserved")
    if sha256(previous_game) != "4d28775a7c69f063d7aab0cee44d6f8b1c4eaa72687644f96a59c65ae7220a25":
        raise BundleError("M08 historical v0.2 GameSpec identity was not preserved")
    game_value = json.loads(committed_game)
    previous_game_value = json.loads(previous_game)
    pre_repair_path = evidence_root / "pre-repair" / "operator-usability-finding.json"
    try:
        pre_repair = json.loads(pre_repair_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M08 pre-repair operator evidence is missing: {exc}") from exc
    if (
        pre_repair.get("status") != "REPAIR_REQUIRED"
        or pre_repair.get("candidate_product_sha")
        != "2a68de03f713409f7525c02629d894828debfd32"
        or previous_game_value.get("provenance", {}).get("pre_repair_evidence_sha256")
        != sha256(pre_repair_path.read_bytes())
    ):
        raise BundleError("M08 pre-repair finding was not preserved as repair-required evidence")
    pre_experiment_path = (
        evidence_root
        / "pre-experiment"
        / "operator-ambient-movement-finding.json"
    )
    try:
        pre_experiment = json.loads(pre_experiment_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M08 pre-experiment operator evidence is missing: {exc}") from exc
    if (
        pre_experiment.get("status")
        != "BOUNDED_GAME_MECHANICS_EXPERIMENT_REQUIRED"
        or pre_experiment.get("candidate_product_sha")
        != "70bd9de17308048c5d51df3cc4efe692daab9d32"
        or pre_experiment.get("gate_scope", {}).get("pass_claim") is not False
        or game_value.get("provenance", {}).get("pre_experiment_evidence_sha256")
        != sha256(pre_experiment_path.read_bytes())
    ):
        raise BundleError(
            "M08 pre-experiment finding was not preserved as experiment-required evidence"
        )
    if (
        identity.get("status") != "PASS"
        or identity.get("graph", {}).get("N") != 313
        or identity.get("graph", {}).get("E") != 20607
        or identity.get("graph", {}).get("represented_contacts") != 79112
        or identity.get("backend", {}).get("name") != "kernel"
        or identity.get("identities", {}).get("m07_live_candidate_sha256")
        != "df1f06266c4fb2274ae32a269b538104567c7fc79369b9a88a761ae47fd0cd88"
        or identity.get("identities", {}).get("controller_sha256")
        != "0b3577ec2dc257f130d59f0219544ad0dae479080027e25bdeca2182673bf817"
    ):
        raise BundleError("M08 live graph/kernel/controller identities are inconsistent")

    for path in (
        evidence_root / "manual" / "manual-game-review.txt",
        evidence_root / "manual" / "host-smoke.json",
    ):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|password\s*=|token\s*=", text, re.I):
            raise BundleError(f"M08 operator receipt appears to contain secret material: {path.name}")

    circuit_dir = root / "data" / "compiled" / "escape"
    full_dir = root / "data" / "compiled" / "full"
    try:
        circuit_manifest = json.loads((circuit_dir / "manifest.json").read_text())
        full_manifest = json.loads((full_dir / "manifest.json").read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M08 compiled graph manifest unavailable: {exc}") from exc
    if circuit_manifest.get("semantic_digest", {}).get("value") != (
        "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5"
    ):
        raise BundleError("M08 compact circuit identity differs from accepted M04")
    if full_manifest.get("semantic_digest", {}).get("value") != (
        "429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0"
    ):
        raise BundleError("M08 full graph manifest identity differs from accepted M03")
    for path in sorted(circuit_dir.iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if len(data) > MAX_INCLUDED_FILE_BYTES:
            raise BundleError(f"M08 compact circuit artifact is too large: {path.name}")
        entries[f"data/compiled/escape/{path.name}"] = data

    omitted: list[dict[str, Any]] = []
    for name, item in sorted(full_manifest.get("arrays", {}).items()):
        path = full_dir / item["filename"]
        size, digest = sha256_file(path)
        if size != item.get("bytes") or digest != item.get("sha256"):
            raise BundleError(f"M08 full graph array differs from accepted manifest: {name}")
        omitted.append(
            {
                "path": f"data/compiled/full/{item['filename']}",
                "reason": "accepted M03 full graph array is not executed by M08 and is omitted from the bounded review ZIP",
                "array_name": name,
                "bytes": size,
                "sha256": digest,
                "dtype": item.get("dtype"),
                "shape": item.get("shape"),
                "graph_semantic_digest": full_manifest["semantic_digest"]["value"],
            }
        )
    return omitted


def m09_material(
    root: Path,
    submitted: str,
    evidence_root: Path,
    entries: dict[str, bytes],
) -> list[dict[str, Any]]:
    """Validate the M09-a03 at-risk submission and include the compact circuit."""

    checker = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "check_m09_evidence.py"),
            "--out",
            str(evidence_root),
            "--phase",
            "submission",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if checker.returncode:
        raise BundleError(f"M09 evidence validation failed: {checker.stdout}{checker.stderr}")
    required: dict[str, dict[str, Any]] = {}
    for name in (
        "recorder-format.json",
        "deterministic-recording.json",
        "applied-input-authority.json",
        "state-digest-policy.json",
        "state-digest-validation.json",
        "bounds.json",
        "archive-safety.json",
        "input-coalescing.json",
        "input-ordering.json",
        "coordinate-quantization.json",
        "bench-recording.json",
        "recording-parity.json",
        "demo-recording-smoke.json",
        "headless-server-recorder-parity.json",
        "attempt-1-superseded.json",
        "attempt-2-superseded.json",
        "operator-demo.json",
        "decision.json",
        "command-results.json",
    ):
        try:
            required[name] = json.loads(
                (evidence_root / name).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"M09 {name} is missing or invalid: {exc}") from exc
    acceptance = required["command-results.json"]
    decision = required["decision.json"]
    process = {
        "decision": "D-M08-HUMAN-GATE-DEFER-01",
        "m09_execution": "AT_RISK",
        "m08_g_game": "PENDING_UNMEASURED",
        "m09_is_m08_usability_evidence": False,
        "public_release_blocked": True,
    }
    reports = tuple(
        name
        for name in required
        if name
        not in {
            "decision.json",
            "command-results.json",
            "attempt-1-superseded.json",
            "attempt-2-superseded.json",
        }
    )
    if any(
        required[name].get("status") != "PASS"
        or required[name].get("process_status") != process
        for name in reports
    ):
        raise BundleError("M09 evidence does not pass with the required at-risk disclosure")
    if acceptance.get("status") != "PASS" or acceptance.get("submitted_code_sha") != submitted:
        raise BundleError("M09 acceptance evidence does not pass for the submitted SHA")
    if (
        decision.get("milestone") != "M09"
        or decision.get("review_attempt") != 3
        or decision.get("proposed_outcome") != "PASS_CANDIDATE"
        or decision.get("external_milestone_acceptance") != "PENDING"
        or decision.get("m09_execution") != "AT_RISK"
        or decision.get("m08_g_game") != "PENDING_UNMEASURED"
        or decision.get("m09_is_m08_usability_evidence") is not False
        or decision.get("public_release_blocked") is not True
        or decision.get("reexecution_verified") is not False
    ):
        raise BundleError("M09 candidate decision overstates acceptance or M08 usability")
    decision_bytes = commit_blob(
        root, submitted, "decisions/D-M08-HUMAN-GATE-DEFER-01.json"
    )
    if sha256(decision_bytes) != (
        "79d9a7e68e4d2d865411c2bb00fa62295fec503c976f38c4d579f8d077212a89"
    ):
        raise BundleError("M09 process-deviation decision identity changed")
    ledger = commit_blob(root, submitted, "ledger.yaml").decode("utf-8")
    for required_text in (
        "last_accepted_milestone: M07",
        "last_accepted_code_commit: c2b0dc064fa1f8d50b01f595f0232f8d9b37d5e5",
        "M08: BLOCKED",
        "M09: SUBMITTED",
        "review_attempt: 3",
        "attempt_3_candidate_product_sha:",
        "PENDING_UNMEASURED",
        "Do not begin M10",
    ):
        if required_text not in ledger:
            raise BundleError(f"M09 submitted ledger is missing: {required_text}")
    fixture = evidence_root / "representative.flyrun"
    if not fixture.is_file() or fixture.stat().st_size != required[
        "recorder-format.json"
    ].get("fixture_bytes"):
        raise BundleError("M09 representative flyrun fixture is missing or changed")
    for relative in (
        "looming-seed-0.flyrun",
        "runs/looming-seed-0.flyrun",
        "bench/selected-trial-summary.json",
        "bench/recorder-parity.json",
        "operator-demo.json",
        "fixture-excerpts.md",
        "review-fixtures/valid-complete.flyrun",
        "review-fixtures/valid-optional-truncated.flyrun",
        "review-fixtures/malformed-path-traversal.flyrun",
        "review-fixtures/malformed-executable-member.flyrun",
        "review-fixtures/malformed-integrity.flyrun",
    ):
        if not (evidence_root / relative).is_file():
            raise BundleError(f"M09 attempt-3 review artifact is missing: {relative}")
    operator_runs = sorted((evidence_root / "operator-demo").glob("*.flyrun"))
    if len(operator_runs) != 1:
        raise BundleError("M09-a03 requires exactly one operator demo flyrun")

    circuit_dir = root / "data" / "compiled" / "escape"
    full_dir = root / "data" / "compiled" / "full"
    try:
        circuit_manifest = json.loads((circuit_dir / "manifest.json").read_text())
        full_manifest = json.loads((full_dir / "manifest.json").read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"M09 compiled graph manifest unavailable: {exc}") from exc
    if circuit_manifest.get("semantic_digest", {}).get("value") != (
        "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5"
    ):
        raise BundleError("M09 compact circuit identity differs from the accepted circuit")
    if full_manifest.get("semantic_digest", {}).get("value") != (
        "429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0"
    ):
        raise BundleError("M09 full graph manifest identity differs from accepted M03")
    for path in sorted(circuit_dir.iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if len(data) > MAX_INCLUDED_FILE_BYTES:
            raise BundleError(f"M09 compact circuit artifact is too large: {path.name}")
        entries[f"data/compiled/escape/{path.name}"] = data

    omitted: list[dict[str, Any]] = []
    for name, item in sorted(full_manifest.get("arrays", {}).items()):
        path = full_dir / item["filename"]
        size, digest = sha256_file(path)
        if size != item.get("bytes") or digest != item.get("sha256"):
            raise BundleError(f"M09 full graph array differs from accepted manifest: {name}")
        omitted.append(
            {
                "path": f"data/compiled/full/{item['filename']}",
                "reason": "accepted offline full graph is not executed by M09 and is omitted from the bounded review ZIP",
                "array_name": name,
                "bytes": size,
                "sha256": digest,
                "dtype": item.get("dtype"),
                "shape": item.get("shape"),
                "graph_semantic_digest": full_manifest["semantic_digest"]["value"],
            }
        )
    return omitted


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
    if milestone == "M08" and base != "eca1ea5cae5a4805708d4994395e8e5755212b9d":
        raise BundleError("M08 review base must be the reviewer-approved M07 bookkeeping SHA")
    if milestone == "M09":
        if attempt != 3:
            raise BundleError("the current M09 review bundle contract is attempt 3")
        if base != "9aaa34515bee2c934f3d90909deff4e4e3fff5b3":
            raise BundleError(
                "M09-a03 review base must be the M09-start process-deviation commit"
            )

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
        if milestone in {"V2I", "V2J"} and path.startswith(("docs/design/v4/screens/", "docs/design/v4/source/")):
            omitted.append({"path": f"repo/{path}", "bytes": len(data), "sha256": sha256(data),
                            "reason": "Unchanged design reference images/source; DESIGN.md and all new implementation screenshots are included"})
            continue
        if milestone in {"V2H", "V2I", "V2J"} and ((path.startswith("docs/media/") and not (milestone in {"V2I", "V2J"} and path in {"docs/media/game-hero.gif", "docs/media/game-still.png", "docs/media/coupling-hero.gif", "docs/media/coupling-still.png", "docs/media/media-provenance.json"})) or path in {"archive/raw-records-manifest.json", "docs/results-v2f.json"}):
            omitted.append({"path": f"repo/{path}", "bytes": len(data), "sha256": sha256(data),
                            "reason": "Unchanged prior-stage media/scientific inventory; available in submitted checkout. The current stage includes all new screen evidence."})
            continue
        if milestone == "V2G" and attempt == 2 and path in {"archive/raw-records-manifest.json", "docs/results-v2f.json"}:
            omitted.append({"path": f"repo/{path}", "bytes": len(data), "sha256": sha256(data),
                            "reason": "Unchanged accepted scientific-stage inventory/results; present in submitted checkout. Bounded anatomy repair ZIP retains every new anatomy manifest, preview and decoder screenshot."})
            continue
        if milestone == "V2G" and path.startswith("docs/media/") and not path.startswith("docs/media/anatomy/"):
            omitted.append({"path": f"repo/{path}", "bytes": len(data), "sha256": sha256(data),
                            "reason": "Unchanged legacy publication media; all V2G anatomy previews and decode screenshots are included"})
            continue
        if milestone == "V2G" and (path.endswith(".retention.json.gz") or path.endswith("-desktop.arbors.gz")):
            omitted.append({"path": f"repo/{path}", "bytes": len(data), "sha256": sha256(data), "reason": "Bounded V2G review: detailed source-row provenance or desktop arbor transport; phone transports, all manifests, retention summaries and previews included; full file in submitted checkout"})
            continue
        if milestone in {"V2C", "V2D", "V2E", "V2F", "V2G", "V2H", "V2I", "V2J"} and (pure.parts[0] == "data" or pure.suffix in {".npy", ".npz", ".webbin"} or (milestone in {"V2E", "V2F", "V2G", "V2H", "V2I", "V2J"} and path.startswith("apps/play/public/data/") and not (milestone in {"V2H", "V2I", "V2J"} and path in {"apps/play/public/data/runtime.json", "apps/play/public/data/game.json", "apps/play/public/data/display-v1.json", "apps/play/public/data/HASHES.json"}) and not (milestone == "V2G" and (path.startswith("apps/play/public/data/anatomy/") or path in {"apps/play/public/data/coupling/strength-demo.json", "apps/play/public/data/coupling/strength-targets.json.gz", "apps/play/public/data/brain.json", "apps/play/public/data/HASHES.json", "apps/play/public/data/coupling/brain.json", "apps/play/public/data/coupling/HASHES.json"})))):
            omitted.append({"path": f"repo/{path}", "bytes": len(data), "sha256": sha256(data),
                            "reason": "Stage exclusion of compiled graph arrays and legacy runtime assets; restore from the submitted checkout"})
            continue
        if reason:
            raise BundleError(f"tracked forbidden path {path!r}: {reason}")
        file_limit = 8_000_000 if milestone in {"V2I", "V2J"} and path in {"docs/media/game-hero.gif", "docs/media/coupling-hero.gif"} else MAX_INCLUDED_FILE_BYTES
        if len(data) > file_limit:
            raise BundleError(f"tracked path {path!r} exceeds the bounded M01 snapshot limit")
        entries[f"repo/{path}"] = data
        repo_paths.append(path)

    if "ledger.yaml" not in repo_paths:
        raise BundleError("committed ledger.yaml is missing")
    entries["ledger.yaml"] = commit_blob(root, submitted, "ledger.yaml")
    entries["tree.txt"] = ("\n".join(repo_paths) + "\n").encode("utf-8")
    entries["git_status.txt"] = status.encode("utf-8")
    diff_exclusions = [".", ":(exclude)apps/play/public/data"] if milestone in {"V2E", "V2F", "V2G", "V2H", "V2I", "V2J"} else []
    if milestone in {"V2H", "V2I", "V2J"}:
        diff_exclusions.extend([":(exclude)docs/design/v4/screens", ":(exclude)docs/design/v4/source"])
    if milestone in {"V2I", "V2J"}:
        diff_exclusions.append(":(exclude)docs/media")
    if milestone == "V2G":
        diff_exclusions.append(":(exclude)docs/media/anatomy")
        # Complete new JSON inventories are already included in repo/, so the
        # patch need not duplicate their large additions beside the full files.
        diff_exclusions.extend([":(exclude)profiles/anatomy-lock-v1.json",
                                ":(exclude)docs/anatomy-soma-units.json"])
    diff = git(root, "diff", "--binary", diff_base, submitted, "--", *diff_exclusions, text=False)
    assert isinstance(diff, bytes)
    entries["git_diff.patch"] = diff

    add_base(entries, root, base, submitted)
    evidence_root = root / "evidence" / milestone
    if milestone in {"V2I", "V2J"} and attempt == 2:
        evidence_root /= "a02"
    add_evidence(
        entries,
        evidence_root,
        omitted,
        preview_limit=2 * 1024 * 1024 if milestone in {"V2A", "V2B"} else MAX_INCLUDED_FILE_BYTES,
    )
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
    if milestone == "M07":
        omitted.extend(m07_material(root, submitted, evidence_root, entries))
    if milestone == "M08":
        omitted.extend(m08_material(root, submitted, evidence_root, entries))
    if milestone == "M09":
        omitted.extend(m09_material(root, submitted, evidence_root, entries))

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
    try:
        m07_decision = json.loads(
            (evidence_root / "decision.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m07_decision = None
    try:
        m07_candidate = json.loads(
            (evidence_root / "live-candidate.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m07_candidate = None
    try:
        m07_circuit_performance = json.loads(
            (evidence_root / "circuit-performance.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m07_circuit_performance = None
    try:
        m07_full_performance = json.loads(
            (evidence_root / "full-performance.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m07_full_performance = None
    try:
        m08_decision = json.loads(
            (evidence_root / "decision.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m08_decision = None
    try:
        m08_identity = json.loads(
            (evidence_root / "identity-check.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m08_identity = None
    try:
        m08_smoke = json.loads(
            (evidence_root / "local-server-smoke.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        m08_smoke = None
    m09_evidence: dict[str, dict[str, Any]] = {}
    if milestone == "M09":
        for name in (
            "recorder-format.json",
            "deterministic-recording.json",
            "applied-input-authority.json",
            "state-digest-policy.json",
            "state-digest-validation.json",
            "bounds.json",
            "archive-safety.json",
            "input-coalescing.json",
            "input-ordering.json",
            "coordinate-quantization.json",
            "bench-recording.json",
            "recording-parity.json",
            "demo-recording-smoke.json",
            "headless-server-recorder-parity.json",
            "attempt-1-superseded.json",
            "attempt-2-superseded.json",
            "operator-demo.json",
            "decision.json",
        ):
            try:
                value = json.loads((evidence_root / name).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                m09_evidence[name] = value
    if milestone in {"V2C", "V2D", "V2E", "V2F", "V2G", "V2H", "V2I", "V2J"}:
        if attempt not in ({1, 2} if milestone in {"V2F", "V2G", "V2I", "V2J"} else {1}) or sha256((root / "docs/plan-v2.md").read_bytes()) != PLAN_V2_SHA256:
            raise BundleError(f"{milestone} requires a registered attempt and the pinned plan")
        # Stage registration: the stage narrative is captured evidence, not a new review tool.
        narrative = (evidence_root / "REVIEW.md").read_text(encoding="utf-8")
        entries["REVIEW.md"] = narrative.replace("{{BASE_SHA}}", base).replace("{{SUBMITTED_SHA}}", submitted).encode("utf-8")
    elif milestone in {"V2A", "V2B"}:
        plan_path = root / "docs/plan-v2.md"
        if not plan_path.is_file() or sha256(plan_path.read_bytes()) != PLAN_V2_SHA256:
            raise BundleError("docs/plan-v2.md identity mismatch")
        if attempt != 1:
            raise BundleError(f"{milestone} review bundle contract requires attempt 1")
        entries["REVIEW.md"] = (
            render_v2a_review(base, submitted, architecture_sha, reports, evidence_root)
            if milestone == "V2A"
            else render_v2b_review(base, submitted, architecture_sha, reports, evidence_root)
        )
    else:
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
            m07_decision,
            m07_candidate,
            m07_circuit_performance,
            m07_full_performance,
            m08_decision,
            m08_identity,
            m08_smoke,
            m09_evidence,
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
    # The V2H dry bundle measured 23,966,349 bytes before clip/fallback evidence.
    # Its mandatory 3-browser x 2-viewport screen matrix must remain complete.
    # V2I dry bundle: 54,971,103 bytes, retaining both complete browser matrices and media.
    archive_limit = ((96 if attempt == 2 else 64) if milestone == "V2I" else 48) * 1024 * 1024 if milestone in {"V2H", "V2I", "V2J"} else MAX_ARCHIVE_BYTES
    if milestone == "V2J":
        # Retain six-size/three-engine/locale matrices, regression captures and failed dry runs.
        archive_limit = 256 * 1024 * 1024
    if len(value) >= archive_limit:
        raise BundleError(f"review bundle is {len(value)} bytes, exceeding the {archive_limit // (1024 * 1024)} MiB review limit")
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
