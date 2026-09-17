from __future__ import annotations

import ast
import copy
from dataclasses import replace
import hashlib
import inspect
import json
import math
from pathlib import Path
import textwrap

import numpy as np
import pytest

from flybench.authority import FORBIDDEN_AMBIENT_TOKENS, audit_callable_dependencies
from flybench.catch import (
    CatchEnvironment,
    EnvironmentConfig,
    ambient_step,
    load_environment_config,
)
from flybench.game import (
    ACCEPTED_CONTACTS,
    ACCEPTED_CONTROLLER_SHA256,
    ACCEPTED_DECODER_SHA256,
    ACCEPTED_E,
    ACCEPTED_ENCODER_SHA256,
    ACCEPTED_ENVIRONMENT_SHA256,
    ACCEPTED_GAME_SPEC_SHA256,
    ACCEPTED_KERNEL_SOURCE_SHA256,
    ACCEPTED_LIVE_CANDIDATE_SHA256,
    ACCEPTED_MODEL_SPEC_SHA256,
    ACCEPTED_N,
    DemoProtocol,
    GameInputError,
    GameSession,
    M08_GAME_SPEC_V02_SHA256,
    apply_game_environment_overrides,
    build_live_session,
    load_game_spec,
    load_live_profile,
    M08_STARTING_GAME_SPEC_SHA256,
    sha256_file,
)
from flybench.model import load_candidate_model_spec
from flybench.reference import ReferenceGraph
from flybench.runner import ACCEPTED_CIRCUIT_DIGEST, GraphBundle, Runner


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "profiles/live.json"
GAME = ROOT / "profiles/game-v0.3.json"


def environment(
    *, speed: float = 0.0, jitter_bounds: tuple[float, float] = (0.0, 0.0)
) -> EnvironmentConfig:
    return EnvironmentConfig(
        arena_min=-10.0,
        arena_max=10.0,
        initial_x=0.0,
        initial_y=0.0,
        initial_heading_rad=0.0,
        ambient_speed_per_interval=speed,
        heading_jitter_min_rad=jitter_bounds[0],
        heading_jitter_max_rad=jitter_bounds[1],
        takeoff_duration_intervals=10,
        takeoff_speed_per_interval=0.2,
    )


def bundle() -> GraphBundle:
    ids = np.array([10001, 10010, 20000, 30000], dtype=np.uint64)
    counts = np.zeros(0, dtype=np.uint64)
    lc4 = np.array([2], dtype=np.int64)
    lplc2 = np.array([3], dtype=np.int64)
    dnp01 = np.array([0, 1], dtype=np.int64)
    for value in (ids, counts, lc4, lplc2, dnp01):
        value.flags.writeable = False
    return GraphBundle(
        directory=ROOT,
        graph=ReferenceGraph.empty(4),
        body_ids=ids,
        counts=counts,
        lc4_indices=lc4,
        lplc2_indices=lplc2,
        dnp01_indices=dnp01,
        semantic_graph_digest=ACCEPTED_CIRCUIT_DIGEST,
        selection_profile_sha256="fixture",
        source_lock_sha256="fixture",
    )


def session(
    *,
    speed: float = 0.0,
    jitter_bounds: tuple[float, float] = (0.0, 0.0),
    environment_seed: int = 20260917,
    output_clamp: bool = False,
    maximum_attacks: int = 6,
    horizon_ms: int = 20000,
) -> GameSession:
    model = load_candidate_model_spec(
        neural_dt_ms=0.5,
        runtime_synaptic_scale=0.001,
        seed=20260916,
        model_profile_path=ROOT / "profiles/model-v0.1.json",
        criteria_path=ROOT / "profiles/numerical-criteria-v0.1.json",
    )
    runner = Runner(
        bundle(),
        model,
        peak_sensory_external_drive=4.0,
        environment_config=environment(speed=speed, jitter_bounds=jitter_bounds),
        environment_seed=environment_seed,
        output_clamp=output_clamp,
        backend="reference",
    )
    spec = replace(
        load_game_spec(GAME),
        maximum_committed_attacks=maximum_attacks,
        round_horizon_ms=horizon_ms,
    )
    return GameSession(runner, spec)


def advance(subject: GameSession, intervals: int) -> None:
    for _ in range(intervals):
        subject.advance_interval()


def ambient_trajectory(subject: GameSession, intervals: int) -> list[tuple[float, float, float]]:
    trajectory = []
    for _ in range(intervals):
        subject.advance_interval()
        environment_state = subject.runner.environment
        trajectory.append(
            (environment_state.x, environment_state.y, environment_state.heading_rad)
        )
    return trajectory


def neural_snapshots_equal(left: dict[str, object], right: dict[str, object]) -> bool:
    arrays = (
        "voltage",
        "synaptic_current",
        "refractory_until_tick",
        "pending_spikes",
        "pending_inputs",
    )
    return all(np.array_equal(left[name], right[name]) for name in arrays) and all(
        left[name] == right[name] for name in ("tick", "seed", "rng_state")
    )


def test_locked_strike_target_remains_unchanged_after_later_aim_updates() -> None:
    subject = session()
    accepted = subject.commit_attack(1.25, -2.5, 1)
    subject.update_aim(8.0, 9.0, 2)
    assert accepted["locked_target"] == {"x": 1.25, "y": -2.5}
    assert subject.snapshot()["strike"]["locked_target"] == {
        "x": 1.25,
        "y": -2.5,
    }
    subject.advance_interval()
    assert subject.snapshot()["aim"] == {"x": 8.0, "y": 9.0}


def test_attack_cannot_be_recommitted_while_one_is_active() -> None:
    subject = session()
    subject.commit_attack(0.0, 0.0, 1)
    with pytest.raises(GameInputError, match="already active") as caught:
        subject.commit_attack(1.0, 1.0, 2)
    assert caught.value.code == "attack_active"
    assert subject.attack_count == 1


def test_cooldown_is_enforced_after_a_miss() -> None:
    subject = session(maximum_attacks=2)
    subject.commit_attack(10.0, 10.0, 1)
    advance(subject, 60)
    assert subject.last_impact["outcome"] == "missed"
    assert subject.snapshot()["cooldown_remaining_ms"] == 600
    with pytest.raises(GameInputError) as caught:
        subject.commit_attack(0.0, 0.0, 2)
    assert caught.value.code == "cooldown"
    advance(subject, 60)
    subject.commit_attack(0.0, 0.0, 3)
    assert subject.attack_count == 2


def test_maximum_attacks_and_round_horizon_both_end_a_round() -> None:
    exhausted = session(maximum_attacks=1)
    exhausted.commit_attack(10.0, 10.0, 1)
    advance(exhausted, 60)
    assert exhausted.result == "fly-survived"
    assert exhausted.result_reason == "maximum-attacks-consumed"

    horizon = session(horizon_ms=30)
    advance(horizon, 3)
    assert horizon.result == "fly-survived"
    assert horizon.result_reason == "round-horizon-reached"
    assert horizon.control_tick == 3


def test_caught_and_missed_outcomes_are_both_scriptable() -> None:
    caught = session()
    caught.commit_attack(0.0, 0.0, 1)
    advance(caught, 60)
    assert caught.result == "caught"
    assert caught.last_impact["outcome"] == "caught"

    missed = session()
    missed.commit_attack(10.0, 10.0, 1)
    advance(missed, 60)
    assert missed.result is None
    assert missed.last_impact["outcome"] == "missed"


def test_authoritative_collision_uses_configured_point_55_strike_radius() -> None:
    inside = session()
    assert inside.spec.strike_radius == 0.55
    inside.commit_attack(0.54, 0.0, 1)
    assert inside.snapshot()["strike"]["strike_radius"] == 0.55
    advance(inside, 60)
    assert inside.last_impact["strike_radius"] == 0.55
    assert inside.last_impact["outcome"] == "caught"

    outside = session()
    outside.commit_attack(0.56, 0.0, 1)
    advance(outside, 60)
    assert outside.last_impact["strike_radius"] == 0.55
    assert outside.last_impact["outcome"] == "missed"


def test_game_spec_v03_changes_only_declared_ambient_mechanics() -> None:
    previous = json.loads((ROOT / "profiles/game-v0.2.json").read_text(encoding="utf-8"))
    current = json.loads(GAME.read_text(encoding="utf-8"))
    assert current["provenance"]["bounded_changes"] == [
        {
            "field": "ambient_walking.speed_per_control_interval",
            "previous": 0.02,
            "current": 0.03,
            "units": "abstract arena units per control interval",
        },
        {
            "field": "ambient_walking.heading_jitter_uniform_rad",
            "previous": [-0.05, 0.05],
            "current": [-0.09, 0.09],
            "units": "radians per ambient control interval",
        },
    ]
    assert previous["attack"]["strike_radius"] == current["attack"]["strike_radius"] == 0.55
    current.pop("ambient_walking_overrides")
    current.pop("provenance")
    for value in (previous, current):
        value.pop("provenance", None)
        value.pop("profile_id")
        value.pop("classification")
    assert current == previous


def test_live_game_session_applies_ambient_overrides_to_an_immutable_base() -> None:
    resolved = load_live_profile(LIVE)
    base = load_environment_config(ROOT / resolved.value["environment"]["path"])
    effective = apply_game_environment_overrides(base, resolved.game_spec)
    subject = build_live_session(resolved)

    assert base.ambient_speed_per_interval == 0.02
    assert (base.heading_jitter_min_rad, base.heading_jitter_max_rad) == (-0.05, 0.05)
    assert effective is not base
    assert effective.ambient_speed_per_interval == 0.03
    assert (effective.heading_jitter_min_rad, effective.heading_jitter_max_rad) == (
        -0.09,
        0.09,
    )
    assert subject.runner.environment.config == effective
    assert subject.runner.environment.rng.bit_generator.__class__.__name__ == "PCG64"
    assert resolved.value["game_mechanics"]["ambient_walking_overrides"] == {
        "speed_per_control_interval": 0.03,
        "heading_jitter_uniform_rad": [-0.09, 0.09],
    }


def test_same_seed_and_authoritative_schedule_produce_identical_ambient_trajectory() -> None:
    left = session(
        speed=0.03,
        jitter_bounds=(-0.09, 0.09),
        environment_seed=42,
        output_clamp=True,
    )
    right = session(
        speed=0.03,
        jitter_bounds=(-0.09, 0.09),
        environment_seed=42,
        output_clamp=True,
    )
    for subject in (left, right):
        subject.update_aim(9.0, 9.0, 1)
        subject.commit_attack(9.0, 9.0, 2)

    assert ambient_trajectory(left, 120) == ambient_trajectory(right, 120)
    for subject in (left, right):
        subject.update_aim(-9.0, 9.0, 3)
        subject.commit_attack(-9.0, 9.0, 4)
    assert ambient_trajectory(left, 60) == ambient_trajectory(right, 60)
    assert left.runner.environment.snapshot() == right.runner.environment.snapshot()


def test_different_environment_seeds_produce_different_ambient_trajectories() -> None:
    first = session(
        speed=0.03,
        jitter_bounds=(-0.09, 0.09),
        environment_seed=17,
        output_clamp=True,
    )
    second = session(
        speed=0.03,
        jitter_bounds=(-0.09, 0.09),
        environment_seed=23,
        output_clamp=True,
    )
    assert ambient_trajectory(first, 100) != ambient_trajectory(second, 100)


def test_aim_and_strike_geometry_do_not_change_output_clamped_walking() -> None:
    left = session(
        speed=0.03,
        jitter_bounds=(-0.09, 0.09),
        environment_seed=31,
        output_clamp=True,
    )
    right = session(
        speed=0.03,
        jitter_bounds=(-0.09, 0.09),
        environment_seed=31,
        output_clamp=True,
    )
    left.update_aim(10.0, 10.0, 1)
    left.commit_attack(10.0, 10.0, 2)
    right.update_aim(-10.0, -10.0, 1)
    right.commit_attack(-10.0, -10.0, 2)

    assert ambient_trajectory(left, 120) == ambient_trajectory(right, 120)
    assert left.last_impact["outcome"] == right.last_impact["outcome"] == "missed"
    assert left.runner.finish_run()["escape_command_count"] == 0
    assert right.runner.finish_run()["escape_command_count"] == 0


def test_ambient_motion_dependency_audit_has_no_hidden_evasion_path() -> None:
    forbidden_evasion_tokens = FORBIDDEN_AMBIENT_TOKENS + (
        "aim",
        "aim_x",
        "aim_y",
        "locked_strike",
        "strike_target",
        "cursor_position",
        "attack_bearing",
        "threat_bearing",
        "distance_to_attack",
        "future_collision",
        "away_from_attack",
    )
    for function in (ambient_step, apply_game_environment_overrides):
        audit = audit_callable_dependencies(
            function, forbidden_tokens=forbidden_evasion_tokens
        )
        assert audit["status"] == "PASS", audit
        assert audit["closure_variables"]["nonlocals"] == {}
        assert audit["mutable_referenced_globals"] == []
        assert audit["forbidden_token_scan"]["hits"] == {}
        assert audit["reachable_environment_objects"] == []

    motion = CatchEnvironment.advance_motion
    motion_source = textwrap.dedent(inspect.getsource(motion))
    motion_tree = ast.parse(motion_source)
    closure = inspect.getclosurevars(motion)
    scanned_source = "\n".join(
        (motion_source, inspect.getsource(closure.globals["ambient_step"]))
    ).lower()
    assert {
        token: scanned_source.count(token)
        for token in forbidden_evasion_tokens
        if token in scanned_source
    } == {}
    assert closure.nonlocals == {}
    assert not any(
        isinstance(value, (dict, list, set, bytearray))
        for value in closure.globals.values()
    )
    direct_calls = {
        node.func.id
        for node in ast.walk(motion_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "ambient_step" in direct_calls
    assert tuple(inspect.signature(motion).parameters) == (
        "self",
        "held_escape_request",
    )

    owned_environment = CatchEnvironment(
        environment(speed=0.03, jitter_bounds=(-0.09, 0.09)), seed=41
    )
    assert not set(vars(owned_environment)).intersection(
        {
            "aim_x",
            "aim_y",
            "cursor_position",
            "strike_target",
            "attack_bearing",
            "threat_bearing",
            "distance_to_attack",
            "future_collision_location",
            "away_from_attack",
        }
    )


def test_catch_uses_authoritative_post_motion_server_position() -> None:
    subject = session(speed=0.1)
    subject.commit_attack(6.0, 0.0, 1)
    advance(subject, 60)
    impact = subject.last_impact
    assert impact["locked_target"] == {"x": 6.0, "y": 0.0}
    assert impact["authoritative_fly_position"]["x"] == pytest.approx(6.0)
    assert impact["authoritative_fly_position"]["y"] == pytest.approx(0.0)
    assert impact["outcome"] == "caught"


def test_new_command_at_impact_cannot_retroactively_change_catch() -> None:
    subject = session()
    subject.commit_attack(0.0, 0.0, 1)
    advance(subject, 59)
    subject.runner.neural.voltage[0] = 1.1
    subject.advance_interval()
    impact = subject.last_impact
    assert impact["outcome"] == "caught"
    assert impact["previously_held_command"] is False
    assert impact["decoded_next_command"] is True
    assert subject.last_motion["takeoff_started"] is False
    assert impact["phase_order"].index("resolve-impact") < impact["phase_order"].index(
        "decode-completed-neural-interval"
    )


def test_neural_state_continues_across_attacks_and_cooldown() -> None:
    subject = session(maximum_attacks=3)
    neural_owner = subject.runner.neural
    environment_owner = subject.runner.environment
    subject.commit_attack(10.0, 10.0, 1)
    advance(subject, 60)
    first_neural_tick = subject.runner.neural.tick
    first_environment_tick = subject.runner.environment.control_tick
    advance(subject, 60)
    assert subject.runner.neural is neural_owner
    assert subject.runner.environment is environment_owner
    assert subject.runner.neural.tick == first_neural_tick + 60 * 20
    assert subject.runner.environment.control_tick == first_environment_tick + 60
    subject.commit_attack(-10.0, 10.0, 2)
    subject.advance_interval()
    assert subject.runner.neural.tick == first_neural_tick + 61 * 20
    assert subject.runner.environment.control_tick == first_environment_tick + 61
    assert subject.control_tick == 121


def test_explicit_new_round_reset_is_complete() -> None:
    subject = session()
    pristine = session()
    subject.commit_attack(10.0, 10.0, 1)
    advance(subject, 70)
    subject.reset_round()
    assert subject.snapshot() == pristine.snapshot()
    assert neural_snapshots_equal(
        subject.runner.neural.snapshot(), pristine.runner.neural.snapshot()
    )
    assert subject.runner.environment.snapshot() == pristine.runner.environment.snapshot()


def test_aim_geometry_never_enters_decoder_or_ambient_motion() -> None:
    left = session()
    right = session()
    left.commit_attack(10.0, 10.0, 1)
    right.commit_attack(-10.0, -10.0, 1)
    advance(left, 60)
    advance(right, 60)
    assert left.last_impact["outcome"] == right.last_impact["outcome"] == "missed"
    assert left.runner.finish_run()["final_neural_state_sha256"] == right.runner.finish_run()[
        "final_neural_state_sha256"
    ]
    assert left.runner.finish_run()["escape_command_control_ticks"] == right.runner.finish_run()[
        "escape_command_control_ticks"
    ]
    assert left.runner.environment.position == right.runner.environment.position
    assert [record["observation"] for record in left.runner.interval_records] == [
        record["observation"] for record in right.runner.interval_records
    ]


def test_live_profile_resolves_actual_accepted_graph_counts() -> None:
    resolved = load_live_profile(LIVE)
    actual = build_live_session(resolved).snapshot()["model"]
    assert actual == {
        "N": ACCEPTED_N,
        "E": ACCEPTED_E,
        "represented_contacts": ACCEPTED_CONTACTS,
    }
    assert actual == {"N": 313, "E": 20607, "represented_contacts": 79112}


def test_actual_scored_m08_session_uses_kernel_backend() -> None:
    subject = build_live_session(LIVE)
    assert subject.runner.backend == "kernel"
    assert subject.snapshot()["backend"] == "kernel"


def test_all_accepted_live_identities_match_exact_bytes() -> None:
    resolved = load_live_profile(LIVE)
    value = resolved.value
    assert value["m07_live_candidate"]["sha256"] == ACCEPTED_LIVE_CANDIDATE_SHA256
    assert value["backend"]["source_sha256"] == ACCEPTED_KERNEL_SOURCE_SHA256
    assert value["model"]["runtime_model_spec_sha256"] == ACCEPTED_MODEL_SPEC_SHA256
    assert value["controller"]["sha256"] == ACCEPTED_CONTROLLER_SHA256
    assert value["encoder"]["sha256"] == ACCEPTED_ENCODER_SHA256
    assert value["decoder"]["sha256"] == ACCEPTED_DECODER_SHA256
    assert value["environment"]["sha256"] == ACCEPTED_ENVIRONMENT_SHA256
    assert resolved.game_spec_sha256 == ACCEPTED_GAME_SPEC_SHA256
    provenance = json.loads(GAME.read_text(encoding="utf-8"))["provenance"]
    assert provenance["previous_game_spec_sha256"] == M08_GAME_SPEC_V02_SHA256
    assert sha256_file(ROOT / provenance["previous_game_spec_path"]) == (
        M08_GAME_SPEC_V02_SHA256
    )
    assert sha256_file(ROOT / "profiles/game-v0.1.json") == M08_STARTING_GAME_SPEC_SHA256
    for key in ("controller", "encoder", "decoder", "environment"):
        assert sha256_file(ROOT / value[key]["path"]) == value[key]["sha256"]


def test_canonical_strike_uses_the_accepted_scalar_looming_schedule() -> None:
    subject = session()
    subject.commit_attack(7.0, -4.0, 1)
    observed = []
    for _ in range(60):
        observation = subject.observation_for_current_interval()
        observed.append(observation)
        subject.advance_interval()
    assert all(not item.visual_threat_present for item in observed[:20])
    assert observed[20].visual_threat_present is True
    assert observed[20].distance == 12.0
    assert observed[20].radial_velocity_per_ms == -0.0275
    assert observed[59].distance == pytest.approx(1.275)
    assert all(item.visual_threat_present for item in observed[20:60])
    assert subject.last_impact["control_tick"] == 60
    assert "x" not in subject.runner.interval_records[20]["observation"]
    assert "bearing" not in subject.runner.interval_records[20]["observation"]


def test_headless_session_and_server_protocol_adapter_have_matching_outcomes() -> None:
    direct = session(maximum_attacks=1)
    adapted = session(maximum_attacks=1)
    direct.update_aim(10.0, 10.0, 1)
    direct.commit_attack(10.0, 10.0, 2)
    protocol = DemoProtocol(adapted)
    protocol.handle({"type": "aim", "x": 10.0, "y": 10.0, "sequence": 1})
    protocol.handle({"type": "attack", "x": 10.0, "y": 10.0, "sequence": 2})
    for _ in range(60):
        direct.advance_interval()
        protocol.advance()
    assert direct.snapshot() == adapted.snapshot()
    assert direct.runner.finish_run()["final_neural_state_sha256"] == adapted.runner.finish_run()[
        "final_neural_state_sha256"
    ]


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"type": "attack", "x": math.nan, "y": 0.0, "sequence": 1}, "non_finite"),
        ({"type": "aim", "x": math.inf, "y": 0.0, "sequence": 1}, "non_finite"),
        ({"type": "attack", "x": 10.1, "y": 0.0, "sequence": 1}, "out_of_arena"),
        ({"type": "attack", "x": "0", "y": 0.0, "sequence": 1}, "malformed"),
    ],
)
def test_protocol_rejects_nonfinite_malformed_and_out_of_arena_input(
    payload: dict[str, object], code: str
) -> None:
    with pytest.raises(GameInputError) as caught:
        DemoProtocol(session()).handle(payload)
    assert caught.value.code == code


def test_live_profile_file_has_no_recursive_self_hash() -> None:
    value = load_live_profile(LIVE).value
    assert "live_profile_sha256" not in value
    assert hashlib.sha256(LIVE.read_bytes()).hexdigest() == load_live_profile(LIVE).sha256
