from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import pytest

from flybench.authority import (
    FORBIDDEN_AMBIENT_TOKENS,
    FORBIDDEN_DECODER_TOKENS,
    audit_callable_dependencies,
)
from flybench.bench import (
    NORMAL_SCENARIOS,
    PROTOCOL_PATHS,
    _neighbors,
    _pathway_response_changed,
    scripted_observation,
)
from flybench.catch import EnvironmentConfig, ambient_step
from flybench.decoder import decode_dnp01
from flybench.encoding import ThreatObservation, compute_features, encode_population_drive
from flybench.model import load_candidate_model_spec
from flybench.reference import ReferenceGraph
from flybench.runner import (
    ACCEPTED_CIRCUIT_DIGEST,
    GraphBundle,
    Runner,
    build_direct_visual_to_dnp01_zero,
    load_graph,
)
ROOT = Path(__file__).resolve().parents[1]
LOOMING = ROOT / "profiles/looming-controls.json"


def fixture_bundle() -> GraphBundle:
    ids = np.array([10001, 10010, 20000, 30000], dtype=np.uint64)
    counts = np.zeros(0, dtype=np.uint64)
    arrays = (
        np.array([2], dtype=np.int64),
        np.array([3], dtype=np.int64),
        np.array([0, 1], dtype=np.int64),
    )
    ids.flags.writeable = False
    counts.flags.writeable = False
    for array in arrays:
        array.flags.writeable = False
    return GraphBundle(
        directory=ROOT,
        graph=ReferenceGraph.empty(4),
        body_ids=ids,
        counts=counts,
        lc4_indices=arrays[0],
        lplc2_indices=arrays[1],
        dnp01_indices=arrays[2],
        semantic_graph_digest=ACCEPTED_CIRCUIT_DIGEST,
        selection_profile_sha256="fixture",
        source_lock_sha256="fixture",
    )


def fixture_runner(*, clamp: bool) -> Runner:
    spec = load_candidate_model_spec(
        neural_dt_ms=0.5,
        runtime_synaptic_scale=0.001,
        seed=4,
        model_profile_path=ROOT / "profiles/model-v0.1.json",
        criteria_path=ROOT / "profiles/numerical-criteria-v0.1.json",
    )
    config = EnvironmentConfig(-10, 10, 0, 0, 0, 0.02, -0.05, 0.05, 10, 0.2)
    return Runner(
        fixture_bundle(),
        spec,
        peak_sensory_external_drive=2.0,
        environment_config=config,
        environment_seed=5,
        output_clamp=clamp,
    )


def test_scripted_no_threat_control_is_zero() -> None:
    profile = json.loads(LOOMING.read_text())
    for tick in (0, 20, 40, 79):
        observation, impact = scripted_observation(profile, "no-threat", tick)
        features = compute_features(observation)
        assert (
            features.angular_size_rad,
            features.angular_velocity_rad_per_ms,
            features.positive_expansion,
            features.size_feature,
            features.expansion_feature,
        ) == (0.0, 0.0, 0.0, 0.0, 0.0)
        assert impact is False


def test_scripted_standard_looming_static_and_receding_controls() -> None:
    profile = json.loads(LOOMING.read_text())
    looming, _ = scripted_observation(profile, "standard looming", 20)
    static, _ = scripted_observation(profile, "matched non-looming/static-size", 20)
    receding, _ = scripted_observation(profile, "receding", 20)
    assert looming.distance == 12.0 and looming.radial_velocity_per_ms == -0.0275
    assert static.distance == 1.0 and static.radial_velocity_per_ms == 0.0
    assert receding.distance == 1.0 and receding.radial_velocity_per_ms == 0.0275
    assert compute_features(looming).expansion_feature > 0.0
    assert compute_features(static).expansion_feature == 0.0
    assert compute_features(receding).expansion_feature == 0.0
    outside, _ = scripted_observation(profile, "standard looming", 60)
    assert outside.visual_threat_present is False


def test_encoder_formulas_against_independent_boundary_values() -> None:
    features = compute_features(ThreatObservation(True, 1.0, -0.0275))
    assert features.angular_size_rad == pytest.approx(math.pi / 2.0)
    assert features.angular_velocity_rad_per_ms == pytest.approx(0.0275)
    assert features.positive_expansion == pytest.approx(0.0275)
    assert features.size_feature == pytest.approx(1.0)
    assert features.expansion_feature == pytest.approx(1.0)
    far = compute_features(ThreatObservation(True, 12.0, -0.0275))
    independent_size = 2.0 * math.atan(1.0 / 12.0) / (math.pi / 2.0)
    independent_expansion = (0.055 / 145.0) / 0.0275
    assert far.size_feature == pytest.approx(independent_size)
    assert far.expansion_feature == pytest.approx(independent_expansion)


def test_population_encoder_is_uniform_and_never_drives_dnp01() -> None:
    features = compute_features(ThreatObservation(True, 1.0, -0.0275))
    encoded = encode_population_drive(
        features,
        2.0,
        neuron_count=6,
        lc4_indices=np.array([0, 2]),
        lplc2_indices=np.array([1, 4]),
        dnp01_indices=np.array([3, 5]),
    )
    np.testing.assert_array_equal(encoded.vector, [2.0, 2.0, 2.0, 0.0, 2.0, 0.0])
    assert encoded.lc4_drive == 2.0
    assert encoded.lplc2_drive == 2.0


def test_forced_dnp01_output_controls_only_the_declared_command() -> None:
    assert decode_dnp01((10001,)) is True
    assert decode_dnp01((10010, 10010)) is True
    assert decode_dnp01(()) is False
    assert decode_dnp01((99999,)) is False


def test_decoder_is_invariant_to_radically_different_geometry() -> None:
    observations = (
        ThreatObservation(False),
        ThreatObservation(True, 0.001, -1000.0),
        ThreatObservation(True, 1_000_000.0, 1000.0),
    )
    assert len({decode_dnp01((10001,)) for _ in observations}) == 1
    assert len({decode_dnp01(()) for _ in observations}) == 1
    assert decode_dnp01((10001,)) is True
    assert decode_dnp01(()) is False


def test_decoder_dependency_audit_has_no_geometry_or_environment_reachability() -> None:
    audit = audit_callable_dependencies(
        decode_dnp01, forbidden_tokens=FORBIDDEN_DECODER_TOKENS
    )
    assert audit["status"] == "PASS"
    assert audit["signature"] == "(dnp01_spike_body_ids: 'tuple[int, ...]') -> 'bool'"
    assert audit["closure_variables"]["nonlocals"] == {}
    assert audit["mutable_referenced_globals"] == []
    assert audit["forbidden_token_scan"]["hits"] == {}
    assert audit["reachable_environment_objects"] == []
    assert audit["helper_call_graph"][0]["same_module_helpers"] == []


def test_ambient_walking_dependency_audit_has_no_sensory_dependency() -> None:
    audit = audit_callable_dependencies(
        ambient_step, forbidden_tokens=FORBIDDEN_AMBIENT_TOKENS
    )
    assert audit["status"] == "PASS"
    assert audit["closure_variables"]["nonlocals"] == {}
    assert audit["mutable_referenced_globals"] == []
    assert audit["forbidden_token_scan"]["hits"] == {}


def test_output_clamp_removes_commands_without_changing_neural_trace() -> None:
    normal = fixture_runner(clamp=False)
    clamped = fixture_runner(clamp=True)
    normal.neural.voltage[0] = 1.1
    clamped.neural.voltage[0] = 1.1
    normal_record = normal.advance_control_interval(ThreatObservation(False))
    clamp_record = clamped.advance_control_interval(ThreatObservation(False))
    assert normal_record["decoded_next_command"] is True
    assert clamp_record["decoded_next_command"] is False
    assert normal_record["dnp01_spikes"] == clamp_record["dnp01_spikes"]
    assert normal_record["neural_state_sha256"] == clamp_record["neural_state_sha256"]
    assert clamped.finish_run()["escape_command_count"] == 0


def test_pathway_mask_selects_exact_accepted_edges_and_contacts() -> None:
    bundle = load_graph(ROOT / "data/compiled/escape")
    intervention = build_direct_visual_to_dnp01_zero(
        bundle,
        ROOT / "profiles/intervention-direct-visual-to-dnp01-zero-v0.1.json",
    )
    assert intervention.audit["groups"] == {
        "LC4": {"pair_edges": 126, "source_contacts": 6362},
        "LPLC2": {"pair_edges": 185, "source_contacts": 4862},
    }
    assert np.count_nonzero(intervention.edge_mask) == 311
    assert np.all(intervention.graph.weights[intervention.edge_mask] == 0.0)
    assert np.array_equal(
        intervention.graph.weights[~intervention.edge_mask],
        bundle.graph.weights[~intervention.edge_mask],
    )


def test_pathway_comparison_changes_or_explicitly_fails_gbio_criterion() -> None:
    normal = {
        "response_signature": {
            "total_dnp01_spike_count": 2,
            "first_dnp01_spike_neural_tick": 700,
            "escape_command_count": 2,
        }
    }
    same = {"response_signature": dict(normal["response_signature"])}
    changed = {
        "response_signature": {
            "total_dnp01_spike_count": 2,
            "first_dnp01_spike_neural_tick": 701,
            "escape_command_count": 2,
        }
    }
    passes, evidence = _pathway_response_changed(normal, changed)
    assert passes and evidence["criterion_status"] == "PASS"
    passes, evidence = _pathway_response_changed(normal, same)
    assert not passes and evidence["criterion_status"] == "FAIL"


def test_control_timing_records_contact_before_new_command() -> None:
    subject = fixture_runner(clamp=False)
    subject.neural.voltage[1] = 1.1
    record = subject.advance_control_interval(
        ThreatObservation(True, 1.0, -0.0275), impact_at_end=True
    )
    assert record["impacts"][0]["outcome"] == "modeled-contact"
    assert record["decoded_next_command"] is True
    assert record["phase_order"].index("resolve-impact") < record[
        "phase_order"
    ].index("decode-completed-neural-interval")


def test_frozen_calibration_grid_is_exactly_twelve_complete_panels() -> None:
    profile = json.loads(LOOMING.read_text())
    scales = profile["primary_grid"]["runtime_synaptic_scale"]
    drives = profile["primary_grid"]["peak_sensory_external_drive"]
    combinations = [(scale, drive) for scale in scales for drive in drives]
    assert combinations == [
        (0.0001, 1.25),
        (0.0001, 2.0),
        (0.0001, 4.0),
        (0.0003, 1.25),
        (0.0003, 2.0),
        (0.0003, 4.0),
        (0.001, 1.25),
        (0.001, 2.0),
        (0.001, 4.0),
        (0.003, 1.25),
        (0.003, 2.0),
        (0.003, 4.0),
    ]
    panels = {(scale, drive): tuple(NORMAL_SCENARIOS) for scale, drive in combinations}
    assert len(panels) == 12
    assert all(len(scenarios) == 4 for scenarios in panels.values())


def test_selection_policy_is_first_complete_pass_and_retains_failures() -> None:
    attempts = [
        {"status": "FAIL", "runtime_synaptic_scale": 0.0001, "peak_sensory_external_drive": 1.25},
        {"status": "PASS", "runtime_synaptic_scale": 0.0001, "peak_sensory_external_drive": 2.0},
        {"status": "PASS", "runtime_synaptic_scale": 0.0001, "peak_sensory_external_drive": 4.0},
    ]
    selected = next(item for item in attempts if item["status"] == "PASS")
    failures = [item for item in attempts if item["status"] == "FAIL"]
    assert selected == attempts[1]
    assert failures == [attempts[0]]
    assert len(attempts) == 3


def test_selected_neighborhood_uses_only_existing_grid_values() -> None:
    scales = [0.0001, 0.0003, 0.001, 0.003]
    drives = [1.25, 2.0, 4.0]
    combinations = [
        {"runtime_synaptic_scale": scale, "peak_sensory_external_drive": drive}
        for scale in scales
        for drive in drives
    ]
    selected = {"runtime_synaptic_scale": 0.001, "peak_sensory_external_drive": 2.0}
    neighbors = _neighbors(combinations, selected, scales, drives)
    pairs = {
        (item["runtime_synaptic_scale"], item["peak_sensory_external_drive"])
        for item in neighbors
    }
    assert pairs == {(0.0003, 2.0), (0.003, 2.0), (0.001, 1.25), (0.001, 4.0)}
    assert all(item in combinations for item in neighbors)


def test_evidence_check_rejects_controller_model_spec_sha_mismatch() -> None:
    checker_spec = importlib.util.spec_from_file_location(
        "flybench_m06_evidence_checker", ROOT / "tools/check_m06_evidence.py"
    )
    assert checker_spec is not None and checker_spec.loader is not None
    checker = importlib.util.module_from_spec(checker_spec)
    checker_spec.loader.exec_module(checker)
    payload = {
        "schema_version": 1,
        "runtime_synaptic_scale": 0.001,
        "seed": 20260916,
    }
    runtime_sha = checker.canonical_json_sha256(payload)
    trial_id = "authority-normal-standard-looming-scale-0.001-drive-4"
    trial = {
        "trial_id": trial_id,
        "runtime_model_spec_sha256": runtime_sha,
        "runtime_model_spec": payload,
        "runtime_synaptic_scale": 0.001,
        "peak_sensory_external_drive": 4.0,
    }
    authority = {
        "selected_attempt": {
            "runtime_synaptic_scale": 0.001,
            "peak_sensory_external_drive": 4.0,
            "trial_ids": {"normal": trial_id},
        }
    }
    controller = {
        "selected_runtime_model_spec_sha256": runtime_sha,
        "selected_runtime_model_spec": payload,
        "selected_runtime_model_spec_payload_role": {
            "classification": "legacy executable identity metadata",
            "note": (
                "The embedded canonical payload preserves historical M05 identity "
                "wording and is not the M06 calibration provenance."
            ),
        },
        "selected_runtime_synaptic_scale": 0.001,
        "selected_peak_sensory_external_drive": 4.0,
        "selected_runtime_synaptic_scale_provenance": {
            "runtime_synaptic_scale": 0.001,
            "classification": checker.M06_SCALE_CLASSIFICATION,
            "selection_provenance": checker.M06_SCALE_SELECTION_PROVENANCE,
            "physiology_claim": "none",
        },
    }
    assert (
        checker.validate_runtime_model_spec_consistency(
            controller, authority, {trial_id: trial}
        )
        is trial
    )

    controller["selected_runtime_model_spec_sha256"] = "0" * 64
    with pytest.raises(
        ValueError,
        match="controller runtime ModelSpec SHA differs from selected normal trial evidence",
    ):
        checker.validate_runtime_model_spec_consistency(
            controller, authority, {trial_id: trial}
        )


def test_protocol_files_match_recorded_calibration_commit_after_execution() -> None:
    controller = ROOT / "profiles/controller-v0.1.json"
    if not controller.is_file():
        pytest.skip("calibration has not yet produced a selected controller")
    commit = json.loads(controller.read_text())["calibration_protocol_commit"]
    for relative in PROTOCOL_PATHS:
        committed = subprocess.check_output(
            ["git", "show", f"{commit}:{relative}"], cwd=ROOT
        )
        current = (ROOT / relative).read_bytes()
        assert committed == current
        assert hashlib.sha256(committed).hexdigest() == hashlib.sha256(current).hexdigest()
