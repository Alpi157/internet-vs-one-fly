from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest

from flybench.catch import CatchEnvironment, EnvironmentConfig
from flybench.encoding import ThreatObservation
from flybench.model import load_candidate_model_spec
from flybench.reference import ReferenceGraph
from flybench.runner import (
    ACCEPTED_CIRCUIT_DIGEST,
    CONTROL_INTERVAL_MS,
    GraphBundle,
    NEURAL_STEPS_PER_CONTROL_INTERVAL,
    RUNNER_ORDER,
    Runner,
    load_graph,
)


ROOT = Path(__file__).resolve().parents[1]


def environment_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        arena_min=-10.0,
        arena_max=10.0,
        initial_x=0.0,
        initial_y=0.0,
        initial_heading_rad=0.0,
        ambient_speed_per_interval=0.02,
        heading_jitter_min_rad=-0.05,
        heading_jitter_max_rad=0.05,
        takeoff_duration_intervals=10,
        takeoff_speed_per_interval=0.2,
    )


def fixture_bundle(graph: ReferenceGraph | None = None) -> GraphBundle:
    ids = np.array([10001, 10010, 20000, 30000], dtype=np.uint64)
    counts = np.zeros(0 if graph is None else graph.weights.size, dtype=np.uint64)
    ids.flags.writeable = False
    counts.flags.writeable = False
    indices = [np.array(values, dtype=np.int64) for values in ([2], [3], [0, 1])]
    for value in indices:
        value.flags.writeable = False
    return GraphBundle(
        directory=ROOT,
        graph=graph or ReferenceGraph.empty(4),
        body_ids=ids,
        counts=counts,
        lc4_indices=indices[0],
        lplc2_indices=indices[1],
        dnp01_indices=indices[2],
        semantic_graph_digest=ACCEPTED_CIRCUIT_DIGEST,
        selection_profile_sha256="fixture-selection",
        source_lock_sha256="fixture-source-lock",
    )


def runner(*, seed: int = 17, environment_seed: int = 18, clamp: bool = False) -> Runner:
    spec = load_candidate_model_spec(
        neural_dt_ms=0.5,
        runtime_synaptic_scale=0.001,
        seed=seed,
        model_profile_path=ROOT / "profiles/model-v0.1.json",
        criteria_path=ROOT / "profiles/numerical-criteria-v0.1.json",
    )
    return Runner(
        fixture_bundle(),
        spec,
        peak_sensory_external_drive=2.0,
        environment_config=environment_config(),
        environment_seed=environment_seed,
        output_clamp=clamp,
    )


def snapshots_equal(left: dict[str, object], right: dict[str, object]) -> bool:
    for name in (
        "voltage",
        "synaptic_current",
        "refractory_until_tick",
        "pending_spikes",
        "pending_inputs",
    ):
        if not np.array_equal(left[name], right[name]):
            return False
    return all(left[name] == right[name] for name in ("tick", "seed", "rng_state"))


def test_exactly_twenty_neural_steps_per_control_interval() -> None:
    subject = runner()
    first = subject.advance_control_interval(ThreatObservation(False))
    second = subject.advance_control_interval(ThreatObservation(False))
    assert first["start_neural_tick"] == 0
    assert first["end_neural_tick"] == NEURAL_STEPS_PER_CONTROL_INTERVAL
    assert second["end_neural_tick"] == 2 * NEURAL_STEPS_PER_CONTROL_INTERVAL
    assert subject.control_tick * CONTROL_INTERVAL_MS == 20.0


def test_authoritative_phase_order_is_explicit() -> None:
    record = runner().advance_control_interval(ThreatObservation(False))
    assert tuple(record["phase_order"]) == RUNNER_ORDER
    assert record["held_drive"]["hold_neural_steps"] == 20


def test_new_command_cannot_act_retroactively_and_environment_uses_old_command() -> None:
    subject = runner()
    subject.neural.voltage[0] = 1.1
    first = subject.advance_control_interval(ThreatObservation(False))
    assert first["decoded_next_command"] is True
    assert first["previously_held_command"] is False
    assert first["motion"]["takeoff_started"] is False
    second = subject.advance_control_interval(ThreatObservation(False))
    assert second["previously_held_command"] is True
    assert second["motion"]["takeoff_started"] is True


def test_impact_at_same_boundary_wins_before_newly_decoded_escape() -> None:
    subject = runner()
    subject.neural.voltage[0] = 1.1
    record = subject.advance_control_interval(
        ThreatObservation(False), impact_at_end=True
    )
    assert record["decoded_next_command"] is True
    assert record["impacts"] == [
        {
            "control_tick": 1,
            "outcome": "modeled-contact",
            "takeoff_was_active": False,
        }
    ]


def test_two_attacks_share_continuing_neural_state() -> None:
    subject = runner()
    stimulus = ThreatObservation(True, 1.0, -0.0275)
    first = subject.advance_control_interval(stimulus, impact_at_end=True)
    after_first = subject.neural.snapshot()
    subject.advance_control_interval(ThreatObservation(False))
    before_second = subject.neural.snapshot()
    second = subject.advance_control_interval(stimulus, impact_at_end=True)
    assert first["end_neural_tick"] == 20
    assert before_second["tick"] == 40
    assert second["start_neural_tick"] == 40
    assert np.any(after_first["voltage"] != 0.0)
    assert np.any(before_second["voltage"] != 0.0)
    assert subject.environment.impacts[0].control_tick == 1
    assert subject.environment.impacts[1].control_tick == 3


def test_explicit_round_reset_is_complete() -> None:
    subject = runner()
    pristine_neural = subject.neural.snapshot()
    pristine_environment = copy.deepcopy(subject.environment.snapshot())
    subject.neural.voltage[0] = 1.1
    subject.advance_control_interval(ThreatObservation(True, 1.0, -0.0275))
    subject.reset_run()
    assert snapshots_equal(subject.neural.snapshot(), pristine_neural)
    assert subject.environment.snapshot() == pristine_environment
    assert subject.control_tick == 0
    assert subject.held_command is False
    assert subject.interval_records == []


def test_runner_instances_own_independent_mutable_state_and_rngs() -> None:
    first = runner()
    second = runner()
    assert first.neural is not second.neural
    assert first.environment is not second.environment
    assert first.neural.rng is not second.neural.rng
    assert first.environment.rng is not second.environment.rng
    first.neural.voltage[0] = 0.75
    first.environment.rng.random()
    assert second.neural.voltage[0] == 0.0
    assert first.environment.snapshot()["rng_state"] != second.environment.snapshot()[
        "rng_state"
    ]


def test_same_reset_seed_and_input_schedule_reproduces_state() -> None:
    first = runner(seed=99, environment_seed=100)
    second = runner(seed=99, environment_seed=100)
    schedule = [
        ThreatObservation(False),
        ThreatObservation(True, 4.0, -0.0275),
        ThreatObservation(True, 1.0, 0.0),
    ]
    first_records = [first.advance_control_interval(item) for item in schedule]
    second_records = [second.advance_control_interval(item) for item in schedule]
    assert [item["neural_state_sha256"] for item in first_records] == [
        item["neural_state_sha256"] for item in second_records
    ]
    assert first.environment.snapshot() == second.environment.snapshot()


def test_ambient_walk_is_invariant_to_different_sensory_geometry_when_escape_disabled() -> None:
    first = runner(clamp=True)
    second = runner(clamp=True)
    first_positions = []
    second_positions = []
    for tick in range(12):
        a = first.advance_control_interval(ThreatObservation(True, 1.0 + tick, -0.1))
        b = second.advance_control_interval(ThreatObservation(True, 50.0 + tick, 0.2))
        first_positions.append((a["motion"]["x"], a["motion"]["y"], a["motion"]["heading_rad"]))
        second_positions.append((b["motion"]["x"], b["motion"]["y"], b["motion"]["heading_rad"]))
    assert first_positions == second_positions


def test_environment_and_neural_rng_owners_are_distinct() -> None:
    subject = runner(seed=55, environment_seed=55)
    assert subject.neural.rng is not subject.environment.rng
    neural_before = copy.deepcopy(subject.neural.rng.bit_generator.state)
    subject.environment.rng.random(4)
    assert subject.neural.rng.bit_generator.state == neural_before


def test_takeoff_direction_is_current_heading_only() -> None:
    environment = CatchEnvironment(environment_config(), seed=3)
    environment.heading_rad = 1.25
    before = environment.position
    result = environment.advance_motion(True)
    assert result.takeoff_started is True
    assert environment.takeoff_heading_rad == pytest.approx(1.25)
    assert result.x - before[0] == pytest.approx(0.2 * np.cos(1.25))
    assert result.y - before[1] == pytest.approx(0.2 * np.sin(1.25))


def test_compiled_circuit_identity_is_checked_before_execution(tmp_path: Path) -> None:
    accepted = load_graph(ROOT / "data/compiled/escape")
    assert accepted.semantic_graph_digest == ACCEPTED_CIRCUIT_DIGEST
    bad = tmp_path / "bad-graph"
    bad.mkdir()
    (bad / "manifest.json").write_text(
        '{"semantic_digest":{"value":"wrong"},"selection_profile":{},"source_lock_sha256":"wrong"}'
    )
    with pytest.raises(ValueError, match="semantic identity"):
        load_graph(bad)
