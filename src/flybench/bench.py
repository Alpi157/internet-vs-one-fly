"""Frozen M06 calibration and neural-authority evidence generation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from flybench.authority import (
    FORBIDDEN_AMBIENT_TOKENS,
    FORBIDDEN_DECODER_TOKENS,
    audit_callable_dependencies,
)
from flybench.catch import ambient_step, load_environment_config
from flybench.decoder import decode_dnp01
from flybench.encoding import ThreatObservation
from flybench.model import load_candidate_model_spec
from flybench.runner import (
    CONTROL_INTERVAL_MS,
    NEURAL_DT_MS,
    Runner,
    build_direct_visual_to_dnp01_zero,
    load_graph,
)


ROOT = Path(__file__).resolve().parents[2]
GRAPH_DIRECTORY = ROOT / "data/compiled/escape"
MODEL_PROFILE = ROOT / "profiles/model-v0.1.json"
CRITERIA_PROFILE = ROOT / "profiles/numerical-criteria-v0.1.json"
M05_PROFILE = ROOT / "profiles/model-reference-v0.1.json"
ENCODER_PROFILE = ROOT / "profiles/encoder-runtime-v0.1.json"
DECODER_PROFILE = ROOT / "profiles/decoder-runtime-v0.1.json"
ENVIRONMENT_PROFILE = ROOT / "profiles/environment-v0.1.json"
INTERVENTION_PROFILE = (
    ROOT / "profiles/intervention-direct-visual-to-dnp01-zero-v0.1.json"
)
CONTROLLER_PROFILE = ROOT / "profiles/controller-v0.1.json"
ACCEPTED_M05_MODEL_SPEC_SHA256 = (
    "e7bf666f0b9b716d0c6e80af001604b4355ce34ff38e8fa514b90898d6b1dd91"
)
ACCEPTED_MAPPING_DIGEST = (
    "6652462228ddf9af863fae95608fd6cacb44fbd86fd12d0799ec65d8dabcef3d"
)
ACCEPTED_REFERENCE_CODE_SHA256 = (
    "ce53a63c8f22256ad1aed36088734f2132cf8c4b1f70fd8a06365f1593587783"
)
NORMAL_SCENARIOS = (
    "no-threat",
    "standard looming",
    "matched non-looming/static-size",
    "receding",
)
PROTOCOL_PATHS = (
    "src/flybench/authority.py",
    "src/flybench/bench.py",
    "src/flybench/catch.py",
    "src/flybench/cli.py",
    "src/flybench/decoder.py",
    "src/flybench/encoding.py",
    "src/flybench/model.py",
    "src/flybench/reference.py",
    "src/flybench/runner.py",
    "profiles/calibration-plan.json",
    "profiles/decoder-runtime-v0.1.json",
    "profiles/decoder-v0.1.json",
    "profiles/encoder-runtime-v0.1.json",
    "profiles/encoder-v0.1.json",
    "profiles/environment-v0.1.json",
    "profiles/escape-circuit.json",
    "profiles/intervention-direct-visual-to-dnp01-zero-v0.1.json",
    "profiles/looming-controls.json",
    "profiles/model-reference-v0.1.json",
    "profiles/model-v0.1.json",
    "profiles/numerical-criteria-v0.1.json",
    "tests/test_controller_authority.py",
    "tests/test_runner.py",
    "tools/acceptance.json",
    "tools/check_m06_evidence.py",
    "tools/review_bundle.py",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _git(*args: str, binary: bool = False) -> str | bytes:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=not binary
    ).strip() if not binary else subprocess.check_output(["git", *args], cwd=ROOT)


def _format_parameter(value: float) -> str:
    return format(value, ".10g")


def scripted_observation(
    profile: dict[str, Any], scenario: str, control_tick: int
) -> tuple[ThreatObservation, bool]:
    """Resolve the frozen stimulus at an integer control-interval start."""

    if scenario not in NORMAL_SCENARIOS:
        raise ValueError(f"unsupported scripted scenario: {scenario}")
    interval_ms = float(profile["clock"]["control_interval_ms"])
    start_ms = control_tick * interval_ms
    end_ms = (control_tick + 1) * interval_ms
    window_start, window_end = profile["trial"]["stimulus_window_ms"]
    impact = bool(
        scenario == "standard looming"
        and end_ms == float(profile["trial"]["modeled_impact_ms"])
    )
    if scenario == "no-threat" or not window_start <= start_ms < window_end:
        return ThreatObservation(False), impact
    fraction = (start_ms - window_start) / (window_end - window_start)
    if scenario == "standard looming":
        distance = 12.0 + (1.0 - 12.0) * fraction
        velocity = -0.0275
    elif scenario == "matched non-looming/static-size":
        distance = 1.0
        velocity = 0.0
    else:
        distance = 1.0 + (12.0 - 1.0) * fraction
        velocity = 0.0275
    return ThreatObservation(True, distance, velocity), impact


def _response_signature(summary: dict[str, Any]) -> dict[str, Any]:
    spikes = summary["dnp01_spikes"]
    return {
        "total_dnp01_spike_count": summary["dnp01_spike_count"],
        "first_dnp01_spike_neural_tick": (
            spikes[0]["neural_tick"] if spikes else None
        ),
        "escape_command_count": summary["escape_command_count"],
    }


def _run_trial(
    *,
    bundle: Any,
    stimulus_profile: dict[str, Any],
    scenario: str,
    scale: float,
    peak_drive: float,
    trial_seed: int,
    mode: str,
    profile_hashes: dict[str, str],
    pathway_intervention: Any = None,
) -> dict[str, Any]:
    spec = load_candidate_model_spec(
        neural_dt_ms=NEURAL_DT_MS,
        runtime_synaptic_scale=scale,
        seed=trial_seed,
        model_profile_path=MODEL_PROFILE,
        criteria_path=CRITERIA_PROFILE,
    )
    runner = Runner(
        bundle,
        spec,
        peak_sensory_external_drive=peak_drive,
        environment_config=load_environment_config(ENVIRONMENT_PROFILE),
        environment_seed=trial_seed + 1,
        output_clamp=mode == "output_clamp",
        intervention=pathway_intervention,
    )
    interval_count = int(
        stimulus_profile["trial"]["duration_ms"]
        / stimulus_profile["clock"]["control_interval_ms"]
    )
    for control_tick in range(interval_count):
        observation, impact = scripted_observation(
            stimulus_profile, scenario, control_tick
        )
        runner.advance_control_interval(observation, impact_at_end=impact)
    summary = runner.finish_run()
    recovery_start_neural_tick = int(700.0 / NEURAL_DT_MS)
    recovery_start_control_tick = int(700.0 / CONTROL_INTERVAL_MS)
    recovery_spikes = [
        item
        for item in summary["dnp01_spikes"]
        if item["neural_tick"] >= recovery_start_neural_tick
    ]
    recovery_commands = [
        tick
        for tick in summary["escape_command_control_ticks"]
        if tick >= recovery_start_control_tick
    ]
    response = _response_signature(summary)
    trial_id = "-".join(
        (
            mode.replace("_", "-"),
            scenario.replace(" ", "-").replace("/", "-"),
            f"scale-{_format_parameter(scale)}",
            f"drive-{_format_parameter(peak_drive)}",
        )
    )
    impact = summary["impacts"][0] if summary["impacts"] else None
    return {
        "schema_version": 1,
        "trial_id": trial_id,
        "trial_status": "VALID" if summary["finite_state"] else "INVALID",
        "mode": mode,
        "scenario": scenario,
        "runtime_synaptic_scale": scale,
        "peak_sensory_external_drive": peak_drive,
        "seed": trial_seed,
        "environment_seed": trial_seed + 1,
        "graph_circuit_digest": bundle.semantic_graph_digest,
        "mapping_digest": ACCEPTED_MAPPING_DIGEST,
        "accepted_m05_model_spec_sha256": ACCEPTED_M05_MODEL_SPEC_SHA256,
        "runtime_model_spec_sha256": spec.semantic_sha256,
        "runtime_model_spec": spec.canonical_payload(),
        "profile_hashes": profile_hashes,
        "control_interval_ms": CONTROL_INTERVAL_MS,
        "neural_dt_ms": NEURAL_DT_MS,
        "neural_steps_per_control_interval": 20,
        "stimulus_sample_phase": "control-interval start",
        "interval_trace": runner.interval_records,
        "dnp01_spike_logical_ticks": summary["dnp01_spikes"],
        "decoded_command_logical_ticks": summary["escape_command_control_ticks"],
        "impact_logical_tick": impact["control_tick"] if impact else None,
        "impact_outcome": impact["outcome"] if impact else None,
        "finite_state_status": "PASS" if summary["finite_state"] else "FAIL",
        "recovery_status": (
            "PASS" if not recovery_spikes and not recovery_commands else "FAIL"
        ),
        "recovery_dnp01_spikes": recovery_spikes,
        "recovery_escape_command_ticks": recovery_commands,
        "response_signature": response,
        "summary": summary,
    }


def _candidate_result(
    trials: dict[str, dict[str, Any]], *, scale: float, peak_drive: float
) -> dict[str, Any]:
    no_threat = trials["no-threat"]
    looming = trials["standard looming"]
    static = trials["matched non-looming/static-size"]
    receding = trials["receding"]
    first_command = (
        looming["decoded_command_logical_ticks"][0]
        if looming["decoded_command_logical_ticks"]
        else None
    )
    checks = {
        "no_threat_zero": (
            no_threat["response_signature"]["total_dnp01_spike_count"] == 0
            and no_threat["response_signature"]["escape_command_count"] == 0
        ),
        "looming_response": (
            looming["response_signature"]["total_dnp01_spike_count"] >= 1
            and looming["response_signature"]["escape_command_count"] >= 1
        ),
        "looming_command_before_impact": (
            first_command is not None and first_command * CONTROL_INTERVAL_MS < 600.0
        ),
        "differs_from_static": (
            looming["response_signature"] != static["response_signature"]
        ),
        "differs_from_receding": (
            looming["response_signature"] != receding["response_signature"]
        ),
        "all_states_finite": all(
            trial["finite_state_status"] == "PASS" for trial in trials.values()
        ),
        "all_trials_recover": all(
            trial["recovery_status"] == "PASS" for trial in trials.values()
        ),
        "all_trials_valid": all(
            trial["trial_status"] == "VALID" for trial in trials.values()
        ),
    }
    eligible = all(checks.values())
    return {
        "runtime_synaptic_scale": scale,
        "peak_sensory_external_drive": peak_drive,
        "scenario_trial_ids": {
            scenario: trials[scenario]["trial_id"] for scenario in NORMAL_SCENARIOS
        },
        "response_signatures": {
            scenario: trials[scenario]["response_signature"]
            for scenario in NORMAL_SCENARIOS
        },
        "checks": checks,
        "normal_candidate_eligible": eligible,
        "status": "ELIGIBLE" if eligible else "FAILED_NORMAL_CRITERIA",
    }


def _neural_trace_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_trace = left["interval_trace"]
    right_trace = right["interval_trace"]
    if len(left_trace) != len(right_trace):
        return False
    keys = (
        "dnp01_spikes",
        "all_population_spike_count",
        "finite_state",
        "neural_state_sha256",
        "dnp01_voltage",
        "dnp01_synaptic_current",
    )
    return all(
        all(a[key] == b[key] for key in keys)
        for a, b in zip(left_trace, right_trace, strict=True)
    )


def _pathway_response_changed(
    normal: dict[str, Any], intervention: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    normal_signature = normal["response_signature"]
    intervention_signature = intervention["response_signature"]
    count_changed = (
        normal_signature["total_dnp01_spike_count"]
        != intervention_signature["total_dnp01_spike_count"]
    )
    left_tick = normal_signature["first_dnp01_spike_neural_tick"]
    right_tick = intervention_signature["first_dnp01_spike_neural_tick"]
    presence_changed = (left_tick is None) != (right_tick is None)
    first_tick_changed = (
        left_tick is not None
        and right_tick is not None
        and abs(left_tick - right_tick) >= 1
    )
    changed = count_changed or presence_changed or first_tick_changed
    return changed, {
        "normal_response_signature": normal_signature,
        "intervention_response_signature": intervention_signature,
        "total_count_changed": count_changed,
        "response_presence_changed": presence_changed,
        "ordered_first_spike_changed_by_at_least_one_tick": first_tick_changed,
        "criterion_status": "PASS" if changed else "FAIL",
    }


def _protocol_provenance() -> dict[str, Any]:
    current_head = str(_git("rev-parse", "HEAD"))
    if CONTROLLER_PROFILE.is_file():
        existing = json.loads(CONTROLLER_PROFILE.read_text(encoding="utf-8"))
        protocol_commit = existing["calibration_protocol_commit"]
    else:
        protocol_commit = current_head
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", protocol_commit, current_head],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    files: list[dict[str, Any]] = []
    unchanged = True
    for relative in PROTOCOL_PATHS:
        current = (ROOT / relative).read_bytes()
        try:
            committed = subprocess.check_output(
                ["git", "show", f"{protocol_commit}:{relative}"], cwd=ROOT
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"calibration protocol path was not committed before execution: {relative}"
            ) from exc
        same = committed == current
        unchanged = unchanged and same
        files.append(
            {
                "path": relative,
                "sha256": _sha256_bytes(current),
                "matches_calibration_protocol_commit": same,
            }
        )
    status = str(
        subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
        )
    )
    clean = status == ""
    passed = ancestry and unchanged and clean
    if not passed:
        raise RuntimeError(
            "calibration requires a clean tree and protocol bytes identical to the frozen commit"
        )
    return {
        "schema_version": 1,
        "calibration_protocol_commit": protocol_commit,
        "measurement_code_commit": current_head,
        "protocol_commit_is_ancestor": ancestry,
        "protocol_files_unchanged": unchanged,
        "measurement_worktree_clean_at_start": clean,
        "protocol_files": files,
        "status": "PASS",
    }


def _neighbors(
    combinations: list[dict[str, Any]], selected: dict[str, Any], scales: list[float], drives: list[float]
) -> list[dict[str, Any]]:
    scale = selected["runtime_synaptic_scale"]
    drive = selected["peak_sensory_external_drive"]
    scale_index = scales.index(scale)
    drive_index = drives.index(drive)
    requested: set[tuple[float, float]] = set()
    if scale_index:
        requested.add((scales[scale_index - 1], drive))
    if scale_index + 1 < len(scales):
        requested.add((scales[scale_index + 1], drive))
    if drive_index:
        requested.add((scale, drives[drive_index - 1]))
    if drive_index + 1 < len(drives):
        requested.add((scale, drives[drive_index + 1]))
    return [
        combination
        for combination in combinations
        if (
            combination["runtime_synaptic_scale"],
            combination["peak_sensory_external_drive"],
        )
        in requested
    ]


def _controller_profile(
    *,
    selected: dict[str, Any],
    selected_trial: dict[str, Any],
    profile_hashes: dict[str, str],
    stimulus_profile_sha256: str,
    protocol_commit: str,
    intervention_profile_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profile_id": "flybench.m06-controller-candidate.v0.1",
        "classification": "MODEL ASSUMPTION / M06 CANDIDATE — external acceptance pending",
        "claim_scope": "modeled DNp01-dependent escape onset in the declared simplified circuit/controller",
        "selected_circuit_digest": selected_trial["graph_circuit_digest"],
        "mapping_digest": ACCEPTED_MAPPING_DIGEST,
        "accepted_m05": {
            "reference_model_spec_semantic_sha256": ACCEPTED_M05_MODEL_SPEC_SHA256,
            "reference_implementation_sha256": ACCEPTED_REFERENCE_CODE_SHA256,
            "neural_dt_ms": 0.5,
            "delay_ms": 1.0,
            "delay_neural_ticks": 2,
            "refractory_ms": 2.0,
            "refractory_neural_ticks": 4,
            "event_order": "flybench.neural-order.v1",
            "integration": "flybench.exact-linear-lif.v1"
        },
        "control_interval_ms": 10.0,
        "neural_steps_per_control_interval": 20,
        "selected_runtime_synaptic_scale": selected["runtime_synaptic_scale"],
        "selected_peak_sensory_external_drive": selected[
            "peak_sensory_external_drive"
        ],
        "selected_runtime_model_spec_sha256": selected_trial[
            "runtime_model_spec_sha256"
        ],
        "selected_runtime_model_spec": selected_trial["runtime_model_spec"],
        "resolved_encoder_profile_sha256": profile_hashes["encoder"],
        "resolved_decoder_profile_sha256": profile_hashes["decoder"],
        "environment_profile_sha256": profile_hashes["environment"],
        "calibration_plan_sha256": _sha256_file(ROOT / "profiles/calibration-plan.json"),
        "looming_controls_sha256": stimulus_profile_sha256,
        "calibration_protocol_commit": protocol_commit,
        "pathway_intervention": {
            "intervention_id": "direct_visual_to_dnp01_zero",
            "profile_sha256": intervention_profile_sha256,
        },
        "defaults": {
            "trial_seed": 20260916,
            "environment_seed_rule": "trial_seed + 1",
            "trial_duration_ms": 800.0,
            "stimulus_window_ms": [200.0, 600.0],
            "modeled_impact_ms": 600.0,
            "output_clamp": false,
            "pathway_intervention": null,
        },
        "external_milestone_acceptance": "PENDING",
    }


def _write_trials(out: Path, trials: list[dict[str, Any]]) -> None:
    jsonl = out / "trials.jsonl"
    with jsonl.open("w", encoding="utf-8") as stream:
        for trial in trials:
            stream.write(json.dumps(trial, sort_keys=True, allow_nan=False) + "\n")
    fields = (
        "trial_id",
        "mode",
        "scenario",
        "runtime_synaptic_scale",
        "peak_sensory_external_drive",
        "seed",
        "runtime_model_spec_sha256",
        "trial_status",
        "finite_state_status",
        "recovery_status",
        "dnp01_spike_count",
        "first_dnp01_spike_neural_tick",
        "escape_command_count",
        "first_escape_command_control_tick",
        "impact_logical_tick",
        "impact_outcome",
    )
    with (out / "trials.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for trial in trials:
            response = trial["response_signature"]
            commands = trial["decoded_command_logical_ticks"]
            writer.writerow(
                {
                    "trial_id": trial["trial_id"],
                    "mode": trial["mode"],
                    "scenario": trial["scenario"],
                    "runtime_synaptic_scale": trial["runtime_synaptic_scale"],
                    "peak_sensory_external_drive": trial[
                        "peak_sensory_external_drive"
                    ],
                    "seed": trial["seed"],
                    "runtime_model_spec_sha256": trial[
                        "runtime_model_spec_sha256"
                    ],
                    "trial_status": trial["trial_status"],
                    "finite_state_status": trial["finite_state_status"],
                    "recovery_status": trial["recovery_status"],
                    "dnp01_spike_count": response["total_dnp01_spike_count"],
                    "first_dnp01_spike_neural_tick": response[
                        "first_dnp01_spike_neural_tick"
                    ],
                    "escape_command_count": response["escape_command_count"],
                    "first_escape_command_control_tick": commands[0] if commands else "",
                    "impact_logical_tick": trial["impact_logical_tick"] or "",
                    "impact_outcome": trial["impact_outcome"] or "",
                }
            )


def _authority_review(
    *,
    decision: dict[str, Any],
    calibration: dict[str, Any],
    authority: dict[str, Any],
    trials_by_id: dict[str, dict[str, Any]],
    dependencies: dict[str, Any],
    receipt_present: bool,
) -> str:
    selected = calibration.get("selected_combination")
    if selected:
        normal_id = authority["selected_attempt"]["trial_ids"]["normal"]
    else:
        normal_id = calibration["combinations"][0]["scenario_trial_ids"][
            "standard looming"
        ]
    control_id = calibration["combinations"][0]["scenario_trial_ids"]["no-threat"]
    normal = trials_by_id[normal_id]
    control = trials_by_id[control_id]
    lines = [
        "M06 neural-authority human review",
        "",
        f"G-BIO candidate outcome: {decision['outcome']}",
        f"Claim scope: {decision['claim_scope']}",
        f"Selected parameters: {selected if selected else 'none'}",
        f"Manual receipt: {'present' if receipt_present else 'absent'}",
        "",
        "Normal looming trace",
        f"trial: {normal['trial_id']}",
        f"response: {normal['response_signature']}",
        f"DNp01 spike events: {normal['dnp01_spike_logical_ticks']}",
        f"command control ticks: {normal['decoded_command_logical_ticks']}",
        f"impact tick/outcome: {normal['impact_logical_tick']} / {normal['impact_outcome']}",
        f"finite/recovery: {normal['finite_state_status']} / {normal['recovery_status']}",
        "",
        "Control or failed trace",
        f"trial: {control['trial_id']}",
        f"response: {control['response_signature']}",
        f"command control ticks: {control['decoded_command_logical_ticks']}",
        f"finite/recovery: {control['finite_state_status']} / {control['recovery_status']}",
        "",
        "Authority comparisons",
        json.dumps(authority, indent=2, sort_keys=True),
        "",
        "Decoder dependency audit",
        json.dumps(dependencies["decoder"], indent=2, sort_keys=True),
        "",
        "Ambient-walk dependency audit",
        json.dumps(dependencies["ambient_walking"], indent=2, sort_keys=True),
        "",
        "Material limitations",
        "- Feature-level stimulation bypasses early vision and has no retinotopy or direction.",
        "- The ports-only circuit omits all outside neural context.",
        "- Effective signs, normalized LIF dynamics, encoder, decoder, and mechanics are model assumptions.",
        "- The abstract takeoff and ambient walk are not biomechanics or neural locomotion.",
        "- The frozen 12-point search is small and establishes only the stated modeled authority claim.",
        "- No natural-fly behavior, biological validation, wiring superiority, or whole-CNS locomotion is claimed.",
        "- External milestone acceptance remains pending.",
        "",
    ]
    return "\n".join(lines)


def run_bench(stimulus_path: Path, out: Path) -> int:
    """Execute the complete frozen M06 grid and authority selection."""

    stimulus_path = stimulus_path.resolve()
    out = out.resolve()
    stimulus_profile = json.loads(stimulus_path.read_text(encoding="utf-8"))
    if stimulus_profile.get("profile_id") != "flybench.m06-looming-controls.v0.1":
        raise ValueError("bench requires the frozen M06 looming-controls profile")
    if tuple(stimulus_profile["scenarios_in_execution_order"]) != NORMAL_SCENARIOS:
        raise ValueError("scripted control-panel scenarios or ordering changed")
    m05 = json.loads(M05_PROFILE.read_text(encoding="utf-8"))
    if m05.get("model_spec_sha256") != ACCEPTED_M05_MODEL_SPEC_SHA256:
        raise ValueError("accepted M05 ModelSpec identity mismatch")
    if _sha256_file(ROOT / "src/flybench/reference.py") != ACCEPTED_REFERENCE_CODE_SHA256:
        raise ValueError("accepted M05 reference implementation changed")

    provenance = _protocol_provenance()
    bundle = load_graph(GRAPH_DIRECTORY)
    pathway = build_direct_visual_to_dnp01_zero(bundle, INTERVENTION_PROFILE)
    profile_hashes = {
        "encoder": _sha256_file(ENCODER_PROFILE),
        "decoder": _sha256_file(DECODER_PROFILE),
        "environment": _sha256_file(ENVIRONMENT_PROFILE),
        "looming_controls": _sha256_file(stimulus_path),
        "intervention": _sha256_file(INTERVENTION_PROFILE),
    }
    trial_seed = int(stimulus_profile["seed"]["trial_seed"])
    scales = [float(value) for value in stimulus_profile["primary_grid"]["runtime_synaptic_scale"]]
    drives = [
        float(value)
        for value in stimulus_profile["primary_grid"]["peak_sensory_external_drive"]
    ]
    if scales != [0.0001, 0.0003, 0.001, 0.003] or drives != [1.25, 2.0, 4.0]:
        raise ValueError("frozen 12-point primary grid changed")

    trials: list[dict[str, Any]] = []
    combinations: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    normal_trials_by_parameters: dict[tuple[float, float], dict[str, dict[str, Any]]] = {}
    for scale in scales:
        for drive in drives:
            panel: dict[str, dict[str, Any]] = {}
            for scenario in NORMAL_SCENARIOS:
                trial = _run_trial(
                    bundle=bundle,
                    stimulus_profile=stimulus_profile,
                    scenario=scenario,
                    scale=scale,
                    peak_drive=drive,
                    trial_seed=trial_seed,
                    mode="normal",
                    profile_hashes=profile_hashes,
                )
                trials.append(trial)
                panel[scenario] = trial
            normal_trials_by_parameters[(scale, drive)] = panel
            result = _candidate_result(panel, scale=scale, peak_drive=drive)
            combinations.append(result)
            if result["normal_candidate_eligible"]:
                eligible.append(result)
    if len(combinations) != 12 or len(trials) != 48:
        raise RuntimeError("the frozen calibration panel was not executed completely")

    authority_attempts: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    selected_trial: dict[str, Any] | None = None
    for candidate in eligible:
        scale = candidate["runtime_synaptic_scale"]
        drive = candidate["peak_sensory_external_drive"]
        normal = _run_trial(
            bundle=bundle,
            stimulus_profile=stimulus_profile,
            scenario="standard looming",
            scale=scale,
            peak_drive=drive,
            trial_seed=trial_seed,
            mode="authority_normal",
            profile_hashes=profile_hashes,
        )
        clamp = _run_trial(
            bundle=bundle,
            stimulus_profile=stimulus_profile,
            scenario="standard looming",
            scale=scale,
            peak_drive=drive,
            trial_seed=trial_seed,
            mode="output_clamp",
            profile_hashes=profile_hashes,
        )
        intervention = _run_trial(
            bundle=bundle,
            stimulus_profile=stimulus_profile,
            scenario="standard looming",
            scale=scale,
            peak_drive=drive,
            trial_seed=trial_seed,
            mode="direct_visual_to_dnp01_zero",
            profile_hashes=profile_hashes,
            pathway_intervention=pathway,
        )
        trials.extend((normal, clamp, intervention))
        panel = normal_trials_by_parameters[(scale, drive)]
        normal_criteria = _candidate_result(panel, scale=scale, peak_drive=drive)[
            "normal_candidate_eligible"
        ]
        neural_equal = _neural_trace_equal(normal, clamp)
        pathway_changed, pathway_comparison = _pathway_response_changed(
            normal, intervention
        )
        checks = {
            "normal_candidate_criteria": normal_criteria,
            "output_clamp_zero_escape_commands": (
                clamp["response_signature"]["escape_command_count"] == 0
            ),
            "output_clamp_neural_trace_unchanged": neural_equal,
            "pathway_response_changed": pathway_changed,
            "all_states_finite": all(
                item["finite_state_status"] == "PASS"
                for item in (normal, clamp, intervention)
            ),
            "all_post_stimulus_recovery_passes": all(
                item["recovery_status"] == "PASS"
                for item in (normal, clamp, intervention)
            ),
        }
        passed = all(checks.values())
        attempt = {
            "runtime_synaptic_scale": scale,
            "peak_sensory_external_drive": drive,
            "trial_ids": {
                "normal": normal["trial_id"],
                "output_clamp": clamp["trial_id"],
                "direct_visual_to_dnp01_zero": intervention["trial_id"],
            },
            "checks": checks,
            "normal_vs_output_clamp": {
                "neural_trace_identical": neural_equal,
                "normal_escape_command_count": normal["response_signature"][
                    "escape_command_count"
                ],
                "clamped_escape_command_count": clamp["response_signature"][
                    "escape_command_count"
                ],
                "clamp_boundary": "declared DNp01 events immediately before pure decoder",
            },
            "normal_vs_pathway_intervention": pathway_comparison,
            "status": "PASS" if passed else "FAIL",
        }
        authority_attempts.append(attempt)
        if passed:
            selected = candidate
            selected_trial = normal
            break

    selected_attempt = next(
        (attempt for attempt in authority_attempts if attempt["status"] == "PASS"),
        None,
    )
    calibration = {
        "schema_version": 1,
        "status": "PASS" if selected is not None else "BLOCKED",
        "grid_order": "ascending runtime_synaptic_scale then ascending peak_sensory_external_drive",
        "normal_trial_count": 48,
        "primary_combination_count": 12,
        "scenario_count_per_combination": 4,
        "combinations": combinations,
        "failed_combinations": [
            combination
            for combination in combinations
            if not combination["normal_candidate_eligible"]
            or any(
                attempt["runtime_synaptic_scale"]
                == combination["runtime_synaptic_scale"]
                and attempt["peak_sensory_external_drive"]
                == combination["peak_sensory_external_drive"]
                and attempt["status"] == "FAIL"
                for attempt in authority_attempts
            )
        ],
        "eligible_combinations_in_grid_order": [
            {
                "runtime_synaptic_scale": item["runtime_synaptic_scale"],
                "peak_sensory_external_drive": item[
                    "peak_sensory_external_drive"
                ],
            }
            for item in eligible
        ],
        "selected_combination": (
            {
                "runtime_synaptic_scale": selected["runtime_synaptic_scale"],
                "peak_sensory_external_drive": selected[
                    "peak_sensory_external_drive"
                ],
            }
            if selected
            else None
        ),
        "selected_neighborhood_from_primary_grid": (
            _neighbors(combinations, selected, scales, drives) if selected else []
        ),
        "calibration_protocol_commit": provenance["calibration_protocol_commit"],
        "looming_controls_sha256": profile_hashes["looming_controls"],
    }
    authority = {
        "schema_version": 1,
        "status": "PASS" if selected_attempt else "BLOCKED",
        "selection_rule": "first eligible frozen-grid combination satisfying every authority criterion",
        "attempts": authority_attempts,
        "selected_attempt": selected_attempt,
    }
    dependencies = {
        "schema_version": 1,
        "decoder": audit_callable_dependencies(
            decode_dnp01,
            forbidden_tokens=FORBIDDEN_DECODER_TOKENS,
            explicit_state_fields=(),
        ),
        "ambient_walking": audit_callable_dependencies(
            ambient_step,
            forbidden_tokens=FORBIDDEN_AMBIENT_TOKENS,
            explicit_state_fields=("x", "y", "heading_rad", "environment_rng"),
        ),
    }
    dependency_pass = all(
        value["status"] == "PASS"
        for key, value in dependencies.items()
        if key != "schema_version"
    )
    if not dependency_pass:
        selected = None
        selected_trial = None
        selected_attempt = None
        calibration["status"] = "BLOCKED"
        calibration["selected_combination"] = None
        calibration["selected_neighborhood_from_primary_grid"] = []
        authority["status"] = "BLOCKED"
        authority["selected_attempt"] = None

    out.mkdir(parents=True, exist_ok=True)
    receipt_path = out / "manual-authority-review.txt"
    receipt_present = receipt_path.is_file() and receipt_path.stat().st_size > 0
    receipt = {
        "status": "PRESENT_OPERATOR_SUPPLIED" if receipt_present else "ABSENT",
        "path": "evidence/M06/manual-authority-review.txt",
        "bytes": receipt_path.stat().st_size if receipt_present else 0,
        "sha256": _sha256_file(receipt_path) if receipt_present else None,
    }
    outcome = "PASS" if selected is not None else "BLOCKED"
    decision = {
        "schema_version": 1,
        "gate": "G-BIO",
        "outcome": outcome,
        "allowed_next_milestone": "M07" if outcome == "PASS" else None,
        "external_milestone_acceptance": "PENDING",
        "claim_scope": "modeled DNp01-dependent escape onset in the declared simplified circuit/controller",
        "manual_authority_review_receipt": receipt,
        "calibration_protocol_commit": provenance["calibration_protocol_commit"],
        "selected_combination": calibration["selected_combination"],
        "limitations": [
            "not natural fly behavior",
            "not biological validation",
            "not wiring superiority",
            "not whole-CNS locomotion",
            "not proof that the connectome causes living-animal escape",
        ],
    }
    if selected is not None and selected_trial is not None:
        controller = _controller_profile(
            selected=selected,
            selected_trial=selected_trial,
            profile_hashes=profile_hashes,
            stimulus_profile_sha256=profile_hashes["looming_controls"],
            protocol_commit=provenance["calibration_protocol_commit"],
            intervention_profile_sha256=pathway.profile_sha256,
        )
        _write_json(CONTROLLER_PROFILE, controller)
        _write_json(out / "controller-profile.json", controller)
    else:
        _write_json(
            out / "controller-profile.json",
            {
                "schema_version": 1,
                "selection_status": "BLOCKED",
                "reason": "no frozen-grid combination satisfied every G-BIO criterion",
                "calibration_protocol_commit": provenance[
                    "calibration_protocol_commit"
                ],
            },
        )

    trials_by_id = {trial["trial_id"]: trial for trial in trials}
    _write_trials(out, trials)
    _write_json(out / "calibration-summary.json", calibration)
    _write_json(out / "authority.json", authority)
    _write_json(
        out / "stability.json",
        {
            "schema_version": 1,
            "status": (
                "PASS"
                if all(
                    trial["finite_state_status"] == "PASS"
                    and trial["recovery_status"] == "PASS"
                    for trial in trials
                )
                else "FAIL"
            ),
            "trials": [
                {
                    "trial_id": trial["trial_id"],
                    "finite_state_status": trial["finite_state_status"],
                    "recovery_status": trial["recovery_status"],
                    "recovery_dnp01_spikes": trial["recovery_dnp01_spikes"],
                    "recovery_escape_command_ticks": trial[
                        "recovery_escape_command_ticks"
                    ],
                }
                for trial in trials
            ],
        },
    )
    _write_json(out / "decoder-dependency.json", dependencies)
    _write_json(
        out / "intervention.json",
        {
            "schema_version": 1,
            "profile_sha256": pathway.profile_sha256,
            "mask_audit": pathway.audit,
            "authority_attempts": [
                {
                    "runtime_synaptic_scale": attempt[
                        "runtime_synaptic_scale"
                    ],
                    "peak_sensory_external_drive": attempt[
                        "peak_sensory_external_drive"
                    ],
                    "comparison": attempt["normal_vs_pathway_intervention"],
                }
                for attempt in authority_attempts
            ],
        },
    )
    _write_json(out / "calibration-provenance.json", provenance)
    _write_json(out / "decision.json", decision)
    (out / "authority-review.txt").write_text(
        _authority_review(
            decision=decision,
            calibration=calibration,
            authority=authority,
            trials_by_id=trials_by_id,
            dependencies=dependencies,
            receipt_present=receipt_present,
        ),
        encoding="utf-8",
    )
    if not receipt_present:
        print("HUMAN M06 AUTHORITY REVIEW REQUIRED")
        return 3
    if outcome != "PASS":
        print("G-BIO BLOCKED")
        return 4
    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": "G-BIO",
                "out": str(out),
                "selected_combination": calibration["selected_combination"],
                "calibration_protocol_commit": provenance[
                    "calibration_protocol_commit"
                ],
            },
            sort_keys=True,
        )
    )
    return 0
