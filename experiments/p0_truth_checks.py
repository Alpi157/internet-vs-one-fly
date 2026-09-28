"""V2A Phase 0 measurements of the unchanged accepted game and neural model."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any

import numpy as np
import pyarrow.feather as feather

from flybench.encoding import ThreatObservation, compute_features, encode_population_drive
from flybench.game import GameSession, build_live_session, load_live_profile
from flybench.kernel import KernelState
from flybench.runner import (
    CONTROL_INTERVAL_MS,
    NEURAL_STEPS_PER_CONTROL_INTERVAL,
    load_full_graph,
    load_graph,
)


ROOT = Path(__file__).resolve().parents[1]
LIVE_PROFILE = ROOT / "profiles/live.json"
BOT_PROFILE = ROOT / "profiles/p0-bots-v1.json"
PORT_PROFILE = ROOT / "profiles/escape-circuit.json"
ANNOTATIONS = (
    ROOT / "data/raw/body-annotations-male-cns-v1.0-minconf-0.5.feather"
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if type(successes) is not int or type(total) is not int or total <= 0:
        raise ValueError("successes and total must be integers with total positive")
    if not 0 <= successes <= total:
        raise ValueError("successes must lie between zero and total")
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    ) / denominator
    return center - margin, center + margin


def round_seed(profile: dict[str, Any], strategy_index: int, round_index: int) -> int:
    return int(profile["seed_rule"]["base_seed"]) + strategy_index * 1_000_000 + round_index


@dataclass(frozen=True, slots=True)
class PlannedAttack:
    reaction_intervals: int
    target_x: float
    target_y: float


class FixedLatencyController:
    """Experiment-only strike-aware control, never imported by product modules."""

    def __init__(self, command_offset_ms: float):
        if command_offset_ms < 0.0 or command_offset_ms % CONTROL_INTERVAL_MS != 0.0:
            raise ValueError("fixed latency must be a nonnegative control-interval multiple")
        self.offset_ticks = int(command_offset_ms / CONTROL_INTERVAL_MS)

    def before_advance(self, session: GameSession) -> None:
        strike = session.active_strike
        if strike is not None and session.control_tick == strike.impact_tick - self.offset_ticks:
            session.runner.held_command = True


def _reaction_intervals(rng: np.random.Generator, profile: dict[str, Any]) -> int:
    rule = profile["reaction_delay"]
    milliseconds = float(rng.normal(rule["mean_ms"], rule["sigma_ms"]))
    milliseconds = min(max(milliseconds, rule["minimum_ms"]), rule["maximum_ms"])
    return max(1, int(round(milliseconds / CONTROL_INTERVAL_MS)))


def _target(
    session: GameSession,
    strategy: dict[str, Any],
    rng: np.random.Generator,
    sigma: float,
) -> tuple[float, float]:
    environment = session.runner.environment
    x = float(environment.x)
    y = float(environment.y)
    if strategy["kind"] == "heading_lead":
        lead = float(strategy["k_arena_units"])
        x += lead * math.cos(environment.heading_rad)
        y += lead * math.sin(environment.heading_rad)
    elif strategy["kind"] == "far_corner":
        corners = (
            (session.spec.arena_min, session.spec.arena_min),
            (session.spec.arena_min, session.spec.arena_max),
            (session.spec.arena_max, session.spec.arena_min),
            (session.spec.arena_max, session.spec.arena_max),
        )
        x, y = max(corners, key=lambda point: math.hypot(point[0] - x, point[1] - y))
    elif strategy["kind"] != "current_position":
        raise ValueError(f"unsupported bot strategy {strategy['kind']!r}")
    x += float(rng.normal(0.0, sigma))
    y += float(rng.normal(0.0, sigma))
    return (
        min(max(x, session.spec.arena_min), session.spec.arena_max),
        min(max(y, session.spec.arena_min), session.spec.arena_max),
    )


def _reset(session: GameSession, seed: int, *, output_clamp: bool) -> None:
    session.runner.environment_seed = seed
    session.runner.output_clamp = output_clamp
    session.reset_round()


def _advance_until_ready(session: GameSession) -> None:
    while (
        session.result is None
        and (session.active_strike is not None or session.control_tick < session.cooldown_until_tick)
    ):
        session.advance_interval()


def _run_neural_round(
    session: GameSession,
    strategy: dict[str, Any],
    profile: dict[str, Any],
    seed: int,
) -> tuple[dict[str, Any], list[PlannedAttack]]:
    _reset(session, seed, output_clamp=False)
    rng = np.random.Generator(np.random.PCG64(seed))
    attacks: list[dict[str, Any]] = []
    plan: list[PlannedAttack] = []
    sequence = 0
    sigma = float(profile["aim_noise"]["sigma_arena_units"])
    while session.result is None and session.attack_count < session.spec.maximum_committed_attacks:
        _advance_until_ready(session)
        if session.result is not None:
            break
        reaction = _reaction_intervals(rng, profile)
        for _ in range(reaction):
            if session.result is not None:
                break
            session.advance_interval()
        if session.result is not None:
            break
        target_x, target_y = _target(session, strategy, rng, sigma)
        plan.append(PlannedAttack(reaction, target_x, target_y))
        sequence += 1
        acknowledgement = session.commit_attack(target_x, target_y, sequence)
        command_start = len(session.runner.command_control_ticks)
        while session.active_strike is not None and session.result is None:
            session.advance_interval()
        impact = dict(session.last_impact or {})
        command_ticks = session.runner.command_control_ticks[command_start:]
        first_command = min(command_ticks) if command_ticks else None
        impact_tick = int(acknowledgement["impact_tick"])
        attacks.append(
            {
                "target": {"x": target_x, "y": target_y},
                "reaction_intervals": reaction,
                "impact_outcome": impact.get("outcome"),
                "aim_distance_at_impact": impact.get("distance"),
                "first_escape_command_tick": first_command,
                "escape_command_offset_ms": (
                    None
                    if first_command is None
                    else (impact_tick - first_command) * CONTROL_INTERVAL_MS
                ),
            }
        )
    return {
        "seed": seed,
        "result": session.result or "incomplete",
        "caught": session.result == "caught",
        "attacks": attacks,
    }, plan


def _run_replay_round(
    session: GameSession,
    plan: list[PlannedAttack],
    seed: int,
    fixed: FixedLatencyController | None,
) -> dict[str, Any]:
    _reset(session, seed, output_clamp=True)
    sequence = 0
    attacks: list[dict[str, Any]] = []
    for action in plan:
        _advance_until_ready(session)
        if session.result is not None:
            break
        for _ in range(action.reaction_intervals):
            if session.result is not None:
                break
            if fixed is not None:
                fixed.before_advance(session)
            session.advance_interval()
        if session.result is not None:
            break
        sequence += 1
        acknowledgement = session.commit_attack(action.target_x, action.target_y, sequence)
        while session.active_strike is not None and session.result is None:
            if fixed is not None:
                fixed.before_advance(session)
            session.advance_interval()
        impact = dict(session.last_impact or {})
        attacks.append(
            {
                "target": {"x": action.target_x, "y": action.target_y},
                "reaction_intervals": action.reaction_intervals,
                "impact_outcome": impact.get("outcome"),
                "aim_distance_at_impact": impact.get("distance"),
                "escape_command_offset_ms": (
                    None
                    if fixed is None
                    else float((int(acknowledgement["impact_tick"]) - (int(acknowledgement["impact_tick"]) - fixed.offset_ticks)) * CONTROL_INTERVAL_MS)
                ),
            }
        )
    return {
        "seed": seed,
        "result": session.result or "incomplete",
        "caught": session.result == "caught",
        "attacks": attacks,
    }


def _offset_summary(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        float(attack["escape_command_offset_ms"])
        for round_value in rounds
        for attack in round_value["attacks"]
        if attack["escape_command_offset_ms"] is not None
    ]
    return {
        "count": len(values),
        "missing": sum(
            attack["escape_command_offset_ms"] is None
            for round_value in rounds
            for attack in round_value["attacks"]
        ),
        "minimum_ms": min(values) if values else None,
        "median_ms": statistics.median(values) if values else None,
        "maximum_ms": max(values) if values else None,
        "mean_ms": statistics.fmean(values) if values else None,
        "variance_ms2": statistics.pvariance(values) if values else None,
        "values_ms": values,
    }


def _catch_summary(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    caught = sum(bool(value["caught"]) for value in rounds)
    low, high = wilson_interval(caught, len(rounds))
    return {
        "rounds": len(rounds),
        "caught": caught,
        "catch_rate": caught / len(rounds),
        "wilson_95": {"low": low, "high": high},
    }


def _paired_outcomes(
    neural: list[dict[str, Any]], fixed: list[dict[str, Any]]
) -> dict[str, Any]:
    compared = 0
    same = 0
    for neural_round, fixed_round in zip(neural, fixed, strict=True):
        for neural_attack, fixed_attack in zip(
            neural_round["attacks"], fixed_round["attacks"]
        ):
            compared += 1
            same += neural_attack["impact_outcome"] == fixed_attack["impact_outcome"]
    return {
        "paired_attacks": compared,
        "same_outcome": same,
        "fraction_same": same / compared if compared else None,
        "pairing": "same environment seed, reaction delays, and exact locked target coordinates",
    }


def _aim_distance_dependence(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [
        (float(attack["aim_distance_at_impact"]), float(attack["escape_command_offset_ms"]))
        for round_value in rounds
        for attack in round_value["attacks"]
        if attack["aim_distance_at_impact"] is not None
        and attack["escape_command_offset_ms"] is not None
    ]
    if len(pairs) < 2:
        return {"count": len(pairs), "pearson_r": None, "depends_on_aim_distance": None}
    distances = np.asarray([pair[0] for pair in pairs], dtype=np.float64)
    offsets = np.asarray([pair[1] for pair in pairs], dtype=np.float64)
    if float(np.var(distances)) == 0.0 or float(np.var(offsets)) == 0.0:
        correlation = 0.0
    else:
        correlation = float(np.corrcoef(distances, offsets)[0, 1])
    return {
        "count": len(pairs),
        "pearson_r": correlation,
        "depends_on_aim_distance": abs(correlation) >= 0.1,
        "declared_descriptive_threshold_abs_r": 0.1,
    }


def run_bot_checks(rounds: int, profile: dict[str, Any]) -> dict[str, Any]:
    if rounds < 1:
        raise ValueError("rounds must be positive")
    resolved = load_live_profile(LIVE_PROFILE)
    neural_session = build_live_session(resolved)
    neural_by_strategy: dict[str, list[dict[str, Any]]] = {}
    plans_by_strategy: dict[str, list[list[PlannedAttack]]] = {}
    for strategy_index, strategy in enumerate(profile["strategies"]):
        strategy_rounds = []
        strategy_plans = []
        for round_index in range(rounds):
            result, plan = _run_neural_round(
                neural_session,
                strategy,
                profile,
                round_seed(profile, strategy_index, round_index),
            )
            strategy_rounds.append(result)
            strategy_plans.append(plan)
        neural_by_strategy[strategy["id"]] = strategy_rounds
        plans_by_strategy[strategy["id"]] = strategy_plans
    all_neural = [value for values in neural_by_strategy.values() for value in values]
    offsets = _offset_summary(all_neural)
    if offsets["median_ms"] is None:
        raise RuntimeError("accepted neural controller produced no escape command offset")
    fixed_latency_ms = float(offsets["median_ms"])
    fixed_controller = FixedLatencyController(fixed_latency_ms)
    fixed_session = build_live_session(resolved)
    no_escape_session = build_live_session(resolved)
    results: dict[str, Any] = {}
    for strategy_index, strategy in enumerate(profile["strategies"]):
        identifier = strategy["id"]
        fixed_rounds = []
        no_escape_rounds = []
        for round_index, plan in enumerate(plans_by_strategy[identifier]):
            seed = round_seed(profile, strategy_index, round_index)
            fixed_rounds.append(
                _run_replay_round(fixed_session, plan, seed, fixed_controller)
            )
            no_escape_rounds.append(
                _run_replay_round(no_escape_session, plan, seed, None)
            )
        neural_rounds = neural_by_strategy[identifier]
        results[identifier] = {
            "strategy": strategy,
            "controllers": {
                "accepted-neural": {
                    "catch": _catch_summary(neural_rounds),
                    "escape_command_offsets": _offset_summary(neural_rounds),
                },
                "fixed-latency-control": {
                    "catch": _catch_summary(fixed_rounds),
                    "escape_command_offsets": _offset_summary(fixed_rounds),
                },
                "no-escape": {
                    "catch": _catch_summary(no_escape_rounds),
                    "escape_command_offsets": _offset_summary(no_escape_rounds),
                },
            },
            "accepted_vs_fixed_same_outcome": _paired_outcomes(
                neural_rounds, fixed_rounds
            ),
            "determinism_probe": {
                "escape_command_offset_variance_ms2": _offset_summary(neural_rounds)[
                    "variance_ms2"
                ],
                "aim_distance_dependence": _aim_distance_dependence(neural_rounds),
            },
        }
    return {
        "rounds_per_strategy_controller": rounds,
        "fixed_latency_ms_from_global_neural_median": fixed_latency_ms,
        "strategies": results,
    }


def _annotation_lookup() -> dict[int, dict[str, Any]]:
    table = feather.read_table(
        ANNOTATIONS, columns=["bodyId", "type", "instance", "somaSide"], memory_map=True
    )
    return {int(row["bodyId"]): row for row in table.to_pylist()}


def _context_graph_result(
    bundle: Any,
    model_spec: Any,
    spec: Any,
    deadline: float,
    accepted_ids: set[int],
    annotations: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    state = KernelState(model_spec, bundle.graph)
    spike_counts = np.zeros(bundle.n, dtype=np.int64)
    first_ticks: dict[int, int] = {}
    control_intervals = int(1000 / CONTROL_INTERVAL_MS)
    for control_tick in range(control_intervals):
        if time.monotonic() >= deadline:
            return {"status": "TIMEOUT", "completed_control_intervals": control_tick}
        if spec.stimulus_start_ticks <= control_tick < spec.impact_ticks:
            fraction = (control_tick - spec.stimulus_start_ticks) / (
                spec.impact_ticks - spec.stimulus_start_ticks
            )
            distance = spec.stimulus_start_distance + (
                spec.stimulus_end_distance - spec.stimulus_start_distance
            ) * fraction
            observation = ThreatObservation(
                True, distance, spec.stimulus_radial_velocity_per_ms
            )
        else:
            observation = ThreatObservation(False)
        features = compute_features(observation)
        encoded = encode_population_drive(
            features,
            4.0,
            neuron_count=bundle.n,
            lc4_indices=bundle.lc4_indices,
            lplc2_indices=bundle.lplc2_indices,
            dnp01_indices=bundle.dnp01_indices,
        )
        for _ in range(NEURAL_STEPS_PER_CONTROL_INTERVAL):
            result = state.step(encoded.vector)
            fired = np.flatnonzero(result.spikes)
            spike_counts[fired] += 1
            for index in fired:
                first_ticks.setdefault(int(index), int(result.end_tick))
    dnp = []
    for index in bundle.dnp01_indices:
        body_id = int(bundle.body_ids[int(index)])
        row = annotations.get(body_id, {})
        dnp.append(
            {
                "body_id": str(body_id),
                "side": row.get("somaSide"),
                "first_spike_tick": first_ticks.get(int(index)),
                "spike_count": int(spike_counts[int(index)]),
            }
        )
    outside_indices = [
        index
        for index, body_id in enumerate(bundle.body_ids)
        if int(body_id) not in accepted_ids and spike_counts[index] > 0
    ]
    by_type: dict[str, int] = defaultdict(int)
    for index in outside_indices:
        body_id = int(bundle.body_ids[index])
        neuron_type = annotations.get(body_id, {}).get("type") or "<unknown>"
        by_type[str(neuron_type)] += int(spike_counts[index])
    top = sorted(by_type.items(), key=lambda item: (-item[1], item[0]))[:20]
    return {
        "status": "COMPLETE",
        "simulated_ms": 1000,
        "dnp01": dnp,
        "outside_accepted_circuit_spiking_neurons": len(outside_indices),
        "outside_top_20_cell_types_by_spike_count": [
            {"type": name, "spike_count": count} for name, count in top
        ],
        "total_spikes": int(spike_counts.sum()),
    }


def run_context_check(full_graph: Path, timeout_s: float) -> dict[str, Any]:
    if timeout_s <= 0.0:
        raise ValueError("timeout must be positive")
    resolved = load_live_profile(LIVE_PROFILE)
    template = build_live_session(resolved)
    circuit = load_graph(ROOT / resolved.value["graph"]["path"])
    full = load_full_graph(full_graph, PORT_PROFILE)
    accepted_ids = {int(value) for value in circuit.body_ids}
    annotations = _annotation_lookup()
    deadline = time.monotonic() + timeout_s
    circuit_result = _context_graph_result(
        circuit,
        template.runner.model_spec,
        resolved.game_spec,
        deadline,
        accepted_ids,
        annotations,
    )
    full_result = _context_graph_result(
        full,
        template.runner.model_spec,
        resolved.game_spec,
        deadline,
        accepted_ids,
        annotations,
    )
    return {
        "runtime_synaptic_scale": 0.001,
        "peak_sensory_external_drive": 4.0,
        "schedule": "game-v0.3 standard looming from 200 ms inclusive to 600 ms exclusive in a 1000 ms run",
        "timeout_s": timeout_s,
        "accepted_circuit": circuit_result,
        "full_graph": full_result,
    }


def _markdown(findings: dict[str, Any]) -> str:
    lines = [
        "# V2A Phase 0 findings",
        "",
        "These are measurements of the unchanged accepted v1 model and game. They do not validate natural fly behavior.",
        "",
        "## Catch rates",
        "",
        "| Strategy | Controller | Caught / rounds | Catch rate | 95% Wilson interval |",
        "|---|---|---:|---:|---:|",
    ]
    for strategy_id, strategy in findings["bot_checks"]["strategies"].items():
        for controller, value in strategy["controllers"].items():
            catch = value["catch"]
            lines.append(
                f"| {strategy_id} | {controller} | {catch['caught']} / {catch['rounds']} | {catch['catch_rate']:.6f} | [{catch['wilson_95']['low']:.6f}, {catch['wilson_95']['high']:.6f}] |"
            )
    lines.extend(
        [
            "",
            "## Plain conclusions",
            "",
            f"- The fixed-latency control used {findings['bot_checks']['fixed_latency_ms_from_global_neural_median']:.1f} ms before impact, derived from the accepted-neural runs.",
        ]
    )
    for strategy_id, strategy in findings["bot_checks"]["strategies"].items():
        neural = strategy["controllers"]["accepted-neural"]
        same = strategy["accepted_vs_fixed_same_outcome"]
        probe = strategy["determinism_probe"]
        lines.append(
            f"- {strategy_id}: neural offset variance was {probe['escape_command_offset_variance_ms2']!r} ms^2 and accepted-neural versus fixed-latency outcomes matched on {same['fraction_same']!r} of paired attacks."
        )
        if neural["catch"]["catch_rate"] in {0.0, 1.0}:
            lines.append(
                f"- Contrary to the plan-v2 nondegeneracy goal, {strategy_id} had a neural catch rate of {neural['catch']['catch_rate']:.0%}."
            )
    context = findings["context_check"]
    lines.extend(["", "## Context check", ""])
    for name in ("accepted_circuit", "full_graph"):
        value = context[name]
        if value["status"] == "TIMEOUT":
            lines.append(f"- {name}: timed out after {value['completed_control_intervals']} control intervals.")
        else:
            dnp = ", ".join(
                f"{entry['side']} first tick {entry['first_spike_tick']}, spikes {entry['spike_count']}"
                for entry in value["dnp01"]
            )
            lines.append(
                f"- {name}: DNp01 {dnp}; outside-circuit spiking neurons {value['outside_accepted_circuit_spiking_neurons']}."
            )
    lines.extend(
        [
            "",
            "Raw per-attack offset values and all context counts are in `findings.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=500)
    parser.add_argument("--full-graph", type=Path, default=ROOT / "data/compiled/full")
    parser.add_argument("--timeout-s", type=float, default=1800.0)
    args = parser.parse_args()
    profile = json.loads(BOT_PROFILE.read_text(encoding="utf-8"))
    if args.rounds >= 500 and args.rounds < profile["minimum_rounds_per_strategy_controller"]:
        raise ValueError("full protocol requires at least 500 rounds")
    started = time.monotonic()
    findings = {
        "schema": "flybench.v2a.p0-findings",
        "version": 1,
        "status": "SUBMITTED",
        "profile": str(BOT_PROFILE.relative_to(ROOT)),
        "bot_checks": run_bot_checks(args.rounds, profile),
        "context_check": run_context_check(args.full_graph.resolve(), args.timeout_s),
        "wall_seconds": time.monotonic() - started,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "findings.json", findings)
    (args.out / "FINDINGS.md").write_text(_markdown(findings), encoding="utf-8")
    print(json.dumps({"status": "PASS", "out": str(args.out.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
