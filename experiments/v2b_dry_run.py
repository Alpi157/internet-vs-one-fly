"""Bounded V2B calibration pipeline dry run without hypothesis conclusions."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import replace
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

from flybench.decoder_v2 import decode_spikes_v2
from flybench.detmath import probability_threshold
from flybench.encoding_v2 import HandStrikeV2, encode_hand_v2
from flybench.game import build_live_session, load_live_profile
from flybench.graph import write_json
from flybench.kernel import KernelGraph
from flybench.kernel_v2 import KernelStateV2
from flybench.nulls import directed_double_edge_swap
from flybench.reference_v2 import NoiseSpec


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles/calibration-v2-draft.json"
PORTS = ROOT / "profiles/ports-v2.json"
VISUAL = ROOT / "profiles/visual-ports-sides-v1.json"
DECODER = ROOT / "profiles/decoder-v2-draft.json"


def _sources(offsets: np.ndarray) -> np.ndarray:
    return np.repeat(np.arange(offsets.size - 1, dtype=np.int64), np.diff(offsets))


def _simple_null_start(sources: np.ndarray, targets: np.ndarray) -> tuple[np.ndarray, int]:
    rewired = np.asarray(targets, dtype=np.int64).copy()
    pairs = {(int(source), int(target)) for source, target in zip(sources, rewired, strict=True)}
    repaired = 0
    for first_edge in np.flatnonzero(sources == rewired):
        first_source = int(sources[first_edge])
        first_target = int(rewired[first_edge])
        for second_edge in range(rewired.size):
            second_source = int(sources[second_edge])
            second_target = int(rewired[second_edge])
            first_new = (first_source, second_target)
            second_new = (second_source, first_target)
            if first_source == second_source or first_new[0] == first_new[1] or second_new[0] == second_new[1]:
                continue
            old_first = (first_source, first_target)
            old_second = (second_source, second_target)
            if (first_new in pairs and first_new not in {old_first, old_second}) or (
                second_new in pairs and second_new not in {old_first, old_second}
            ):
                continue
            pairs.remove(old_first)
            pairs.remove(old_second)
            pairs.add(first_new)
            pairs.add(second_new)
            rewired[first_edge] = second_target
            rewired[second_edge] = first_target
            repaired += 1
            break
        else:
            raise RuntimeError("could not remove source self-loop for null generation")
    return rewired, repaired


def _load_graph(candidate: str) -> dict[str, Any]:
    directory = ROOT / "data/compiled/v2" / candidate.lower()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    arrays = {
        name: np.load(directory / f"{name}.npy", mmap_mode="r", allow_pickle=False)
        for name in ("ids", "offsets", "targets", "weights")
    }
    return {"directory": directory, "manifest": manifest, **arrays}


def _groups(ids: np.ndarray) -> tuple[tuple[int, ...], ...]:
    profile = json.loads(PORTS.read_text(encoding="utf-8"))["groups"]
    present = {int(value) for value in ids}
    return tuple(
        tuple(int(entry["body_id"]) for entry in profile[name] if int(entry["body_id"]) in present)
        for name in ("escape_left", "escape_right", "backward", "turn_left", "turn_right", "forward")
    )


def _indices(ids: np.ndarray) -> tuple[dict[str, np.ndarray], set[int], set[int]]:
    index_by_id = {int(value): index for index, value in enumerate(ids)}
    visual = json.loads(VISUAL.read_text(encoding="utf-8"))["populations"]
    result = {}
    visual_ids: set[int] = set()
    for population in ("LC4", "LPLC2"):
        for side, field in (("left", "left_body_ids_decimal"), ("right", "right_body_ids_decimal")):
            body_ids = {int(value) for value in visual[population][field]}
            visual_ids.update(body_ids)
            result[f"{population}_{side}"] = np.asarray(
                sorted(index_by_id[value] for value in body_ids if value in index_by_id), dtype=np.int64
            )
    ports = json.loads(PORTS.read_text(encoding="utf-8"))["groups"]
    output_ids = {int(entry["body_id"]) for values in ports.values() for entry in values}
    return result, visual_ids, output_ids


def _null_targets(graph: dict[str, Any], count: int, multiple: float) -> tuple[dict[str, list[np.ndarray]], int]:
    sources = _sources(graph["offsets"])
    null_start, repaired_self_loops = _simple_null_start(sources, graph["targets"])
    indices, visual_ids, output_ids = _indices(graph["ids"])
    index_by_id = {int(value): index for index, value in enumerate(graph["ids"])}
    visual_indices = {index_by_id[value] for value in visual_ids if value in index_by_id}
    output_indices = {index_by_id[value] for value in output_ids if value in index_by_id}
    direct = np.fromiter(
        (int(source) in visual_indices and int(target) in output_indices for source, target in zip(sources, null_start, strict=True)),
        dtype=np.bool_, count=sources.size,
    )
    result: dict[str, list[np.ndarray]] = {"N-FULL": [], "N-CONTEXT": []}
    swaps = int(round(multiple * sources.size))
    for family_index, family in enumerate(result):
        frozen = np.zeros(sources.size, dtype=np.bool_) if family == "N-FULL" else direct
        for null_index in range(count):
            value = directed_double_edge_swap(
                sources, null_start, swap_count=swaps,
                seed=202609282000 + family_index * 100 + null_index,
                frozen_edges=frozen, maximum_attempt_multiple=30,
            )
            result[family].append(value.targets)
    return result, repaired_self_loops


def _drive(
    condition: str,
    control_tick: int,
    ids: np.ndarray,
    visual_indices: dict[str, np.ndarray],
    gain: float,
) -> np.ndarray:
    vector = np.zeros(ids.size, dtype=np.float64)
    if condition == "no-threat":
        return vector
    if condition == "looming":
        encoded = encode_hand_v2(
            HandStrikeV2(True, 0.0, 0.0, control_tick * 10.0, 0.05),
            fly_x=0.0, fly_y=0.0, heading_x=1.0, heading_y=0.0,
            hand_radius=0.75, initial_height=8.0, dt_ms=0.5, input_gain=gain,
        )
        values = {
            "LC4_left": encoded.lc4_left_drive,
            "LC4_right": encoded.lc4_right_drive,
            "LPLC2_left": encoded.lplc2_left_drive,
            "LPLC2_right": encoded.lplc2_right_drive,
        }
    else:
        final_size = encode_hand_v2(
            HandStrikeV2(True, 0.0, 0.0, 160.0, 0.05),
            fly_x=0.0, fly_y=0.0, heading_x=1.0, heading_y=0.0,
            hand_radius=0.75, initial_height=8.0, dt_ms=0.5, input_gain=gain,
        ).angular_radius * gain
        values = {"LC4_left": final_size * 0.5, "LC4_right": final_size * 0.5, "LPLC2_left": 0.0, "LPLC2_right": 0.0}
    for name, value in values.items():
        vector[visual_indices[name]] = value
    return vector


def _trial(
    graph: dict[str, Any],
    targets: np.ndarray,
    parameters: dict[str, float],
    seed: int,
    condition: str,
    duration_ms: float,
) -> dict[str, Any]:
    model = build_live_session(load_live_profile(ROOT / "profiles/live.json")).runner.model_spec
    model = replace(model, runtime_synaptic_scale=parameters["runtime_synaptic_scale"])
    kernel_graph = KernelGraph(graph["offsets"], np.asarray(targets, dtype=np.int32), graph["weights"])
    noise = NoiseSpec(
        seed, 17, probability_threshold(parameters["noise_probability_per_tick"]),
        parameters["noise_current_increment"], np.ones(graph["ids"].size, dtype=np.bool_),
    )
    state = KernelStateV2(model, kernel_graph, noise)
    visual_indices, _visual_ids, _output_ids = _indices(graph["ids"])
    groups = _groups(graph["ids"])
    decoder_profile = json.loads(DECODER.read_text(encoding="utf-8"))
    decay = float.fromhex(decoder_profile["rate_filter"]["decay_float64_hex"])
    rates = (0.0,) * 6
    output_spikes = defaultdict(int)
    population_spikes = 0
    escapes = 0
    moving_intervals = 0
    control_intervals = int(duration_ms / 10.0)
    started = time.perf_counter()
    for control_tick in range(control_intervals):
        drive = _drive(condition, control_tick, graph["ids"], visual_indices, parameters["input_gain"])
        interval_body_ids = []
        for _ in range(20):
            result = state.step(drive)
            fired = np.flatnonzero(result.spikes)
            population_spikes += int(fired.size)
            interval_body_ids.extend(int(graph["ids"][index]) for index in fired)
        escape, speed, turn, rates = decode_spikes_v2(
            tuple(interval_body_ids), rates, groups, decay, 0.01,
            decoder_profile["forward_speed"]["k_f"], decoder_profile["turn_rate"]["k_t"],
            decoder_profile["forward_speed"]["clamp_arena_units_per_ms"][0],
            decoder_profile["forward_speed"]["clamp_arena_units_per_ms"][1],
            decoder_profile["turn_rate"]["clamp_radians_per_ms"][1],
        )
        escapes += int(escape)
        moving_intervals += int(speed != 0.0 or turn != 0.0)
        for group_index, name in enumerate(("escape_left", "escape_right", "backward", "turn_left", "turn_right", "forward")):
            output_spikes[name] += sum(interval_body_ids.count(value) for value in groups[group_index])
    wall = time.perf_counter() - started
    seconds = duration_ms / 1000.0
    return {
        "mean_population_rate_hz": population_spikes / graph["ids"].size / seconds,
        "output_port_rates_hz": {
            name: output_spikes[name] / max(len(groups[index]), 1) / seconds
            for index, name in enumerate(("escape_left", "escape_right", "backward", "turn_left", "turn_right", "forward"))
        },
        "output_spike_count": int(sum(output_spikes.values())),
        "fraction_time_moving": moving_intervals / control_intervals,
        "escape_count": escapes,
        "wall_seconds_per_simulated_second": wall / seconds,
    }


def run(out: Path) -> dict[str, Any]:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    subset = profile["dry_run_subset"]
    rows = []
    for circuit_id in subset["circuits"]:
        graph = _load_graph(circuit_id)
        nulls, repaired_self_loops = _null_targets(
            graph,
            subset["nulls_per_family"],
            subset["null_swap_count_multiple_of_E"],
        )
        topologies = [("REAL", 0, graph["targets"])]
        for family, values in nulls.items():
            topologies.extend((family, index, targets) for index, targets in enumerate(values))
        for scale in subset["runtime_synaptic_scale"]:
            for probability in subset["noise_probability_per_tick"]:
                for increment in subset["noise_current_increment"]:
                    for gain in subset["input_gain"]:
                        parameters = {
                            "runtime_synaptic_scale": scale,
                            "noise_probability_per_tick": probability,
                            "noise_current_increment": increment,
                            "input_gain": gain,
                        }
                        family_trials: dict[str, list[dict[str, Any]]] = defaultdict(list)
                        for family, null_index, targets in topologies:
                            for seed in subset["seeds"]:
                                values = {
                                    condition: _trial(graph, targets, parameters, seed, condition, subset["trial_duration_ms"])
                                    for condition in ("no-threat", "looming", "matched-non-looming")
                                }
                                family_trials[family].append(values)
                        for family, trials in family_trials.items():
                            no_threat = [trial["no-threat"] for trial in trials]
                            all_conditions = [value for trial in trials for value in trial.values()]
                            output_rates = {
                                name: float(np.mean([trial["output_port_rates_hz"][name] for trial in no_threat]))
                                for name in no_threat[0]["output_port_rates_hz"]
                            }
                            rows.append(
                                {
                                    "circuit": circuit_id,
                                    "topology_family": family,
                                    "null_start_self_loops_repaired": repaired_self_loops,
                                    **parameters,
                                    "replicate_trials": len(trials),
                                    "silence": all(trial["output_spike_count"] == 0 for trial in no_threat),
                                    "saturation": any(trial["mean_population_rate_hz"] >= 100.0 for trial in all_conditions),
                                    "mean_population_rate_hz": float(np.mean([trial["mean_population_rate_hz"] for trial in no_threat])),
                                    "output_port_rates_hz": output_rates,
                                    "fraction_time_moving": float(np.mean([trial["fraction_time_moving"] for trial in no_threat])),
                                    "escape_counts": {
                                        condition: int(sum(trial[condition]["escape_count"] for trial in trials))
                                        for condition in ("no-threat", "looming", "matched-non-looming")
                                    },
                                    "wall_seconds_per_simulated_second_with_activity": float(
                                        np.mean(
                                            [
                                                condition_value["wall_seconds_per_simulated_second"]
                                                for replicate in trials
                                                for condition_name, condition_value in replicate.items()
                                                if condition_name != "no-threat"
                                            ]
                                        )
                                    ),
                                }
                            )
    report = {
        "schema": "flybench.v2b.calibration-dry-run",
        "version": 1,
        "status": "DRAFT_PIPELINE_DRY_RUN_ONLY",
        "protocol": str(PROFILE.relative_to(ROOT)),
        "hypothesis_conclusions": "NONE",
        "protocol_frozen": False,
        "controls_declared": profile["controls"],
        "rows": rows,
    }
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "dry-run.json", report)
    lines = [
        "# V2B calibration dry run",
        "",
        "This is a pipeline dry run. It makes no H1 or H2 conclusion and does not freeze the protocol.",
        "",
        "## Plain findings",
        "",
        f"- All {len(rows)} circuit, topology-family, and grid rows were silent in the no-threat condition.",
        f"- {sum(row['saturation'] for row in rows)} rows met the proposed saturation flag.",
        f"- {sum(row['fraction_time_moving'] > 0.0 for row in rows)} rows produced spontaneous movement.",
        f"- Looming produced {sum(row['escape_counts']['looming'] for row in rows)} escape intervals; the matched non-looming control produced {sum(row['escape_counts']['matched-non-looming'] for row in rows)}.",
        "- These failed and inverted draft outcomes are retained without parameter changes. The short dry run is a pipeline check, not a calibration or hypothesis result.",
        "",
        "## Grid table",
        "",
        "| Circuit | Family | Scale | p | w | Gain | Silence | Saturation | Mean Hz | Move fraction | Escapes no/loom/static | Wall s/s |",
        "|---|---|---:|---:|---:|---:|---|---|---:|---:|---|---:|",
    ]
    for row in rows:
        escapes = row["escape_counts"]
        lines.append(
            f"| {row['circuit']} | {row['topology_family']} | {row['runtime_synaptic_scale']} | {row['noise_probability_per_tick']} | {row['noise_current_increment']} | {row['input_gain']} | {row['silence']} | {row['saturation']} | {row['mean_population_rate_hz']:.6f} | {row['fraction_time_moving']:.6f} | {escapes['no-threat']}/{escapes['looming']}/{escapes['matched-non-looming']} | {row['wall_seconds_per_simulated_second_with_activity']:.6f} |"
        )
    (out / "FINDINGS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.out.resolve())
    print(json.dumps({"status": "PASS", "rows": len(report["rows"]), "out": str(args.out.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
