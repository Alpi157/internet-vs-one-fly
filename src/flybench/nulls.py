"""Directed degree-preserving null graphs and V2A diagnostics."""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from numba import njit
import numpy as np

from flybench.graph import write_json


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "profiles/nulls-v1.json"
PORTS = ROOT / "profiles/escape-circuit.json"
CANDIDATES = ROOT / "profiles/walking-dn-candidates-v1.json"


@dataclass(frozen=True, slots=True)
class SwapResult:
    targets: np.ndarray
    completed_swaps: int
    proposal_attempts: int


def sign_stratified_swap(sources, targets, weights, *, seed, multiple=1):
    """N-SIGN: independent swaps within negative, disabled and positive sources.

    A source's sign is its effective executable sign, including zero for unknown.
    Request multiple times the number of edges in each stratum, loops included
    in that budget but frozen. Counts and weights are never permuted.
    """
    sources = np.asarray(sources, dtype=np.int64)
    targets = np.asarray(targets, dtype=np.int64)
    weights = np.asarray(weights, dtype=np.float64)
    if weights.shape != sources.shape or not np.all(np.isfinite(weights)):
        raise ValueError('finite edge weights required')
    if type(multiple) is not int or multiple < 0:
        raise ValueError('nonnegative integer swap multiple required')
    validate_simple_directed_graph(sources, targets)
    signs = np.sign(weights).astype(np.int8)
    width = int(sources.max(initial=0)) + 1
    low, high = np.full(width, 2), np.full(width, -2)
    np.minimum.at(low, sources, signs)
    np.maximum.at(high, sources, signs)
    if np.any((low <= 1) & (low != high)):
        raise ValueError('presynaptic effective sign must be consistent')
    rewired = targets.copy()
    strata = {}
    for sign in (-1, 0, 1):
        mask = signs == sign
        requested = int(mask.sum()) * multiple
        if not requested:
            strata[str(sign)] = dict(completed_swaps=0, proposal_attempts=0)
            continue
        result = directed_double_edge_swap(sources[mask], targets[mask],
            swap_count=requested, seed=seed + sign + 1, maximum_attempt_multiple=100)
        rewired[mask] = result.targets
        strata[str(sign)] = dict(completed_swaps=result.completed_swaps,
            proposal_attempts=result.proposal_attempts,
            fraction_changed=float(np.mean(result.targets != targets[mask])))
    validate_simple_directed_graph(sources, rewired)
    return rewired, strata


def validate_simple_directed_graph(sources: np.ndarray, targets: np.ndarray) -> None:
    if sources.shape != targets.shape or sources.ndim != 1:
        raise ValueError("sources and targets must be matching one-dimensional arrays")
    pairs = {(int(source), int(target)) for source, target in zip(sources, targets, strict=True)}
    if len(pairs) != sources.size:
        raise ValueError("input graph contains a multi-edge")


def directed_double_edge_swap(
    sources: np.ndarray,
    targets: np.ndarray,
    *,
    swap_count: int,
    seed: int,
    frozen_edges: np.ndarray | None = None,
    maximum_attempt_multiple: int = 20,
) -> SwapResult:
    sources = np.asarray(sources, dtype=np.int64)
    original_targets = np.asarray(targets, dtype=np.int64)
    validate_simple_directed_graph(sources, original_targets)
    if type(swap_count) is not int or swap_count < 0:
        raise ValueError("swap_count must be a nonnegative integer")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if type(maximum_attempt_multiple) is not int or maximum_attempt_multiple < 1:
        raise ValueError("maximum_attempt_multiple must be a positive integer")
    if frozen_edges is None:
        frozen = np.zeros(sources.size, dtype=np.bool_)
    else:
        frozen = np.asarray(frozen_edges, dtype=np.bool_)
        if frozen.shape != sources.shape:
            raise ValueError("frozen edge mask must match the edge arrays")
    # Autapses retain their original edge, contact count and sign in every null.
    frozen = frozen | (sources == original_targets)
    eligible = np.flatnonzero(~frozen)
    if swap_count and eligible.size < 2:
        raise ValueError("at least two eligible edges are required")
    rng = np.random.Generator(np.random.PCG64(seed))
    rewired = original_targets.copy()
    completed = 0
    attempts = 0
    maximum_attempts = max(swap_count * maximum_attempt_multiple, 1)
    # Batch independent uniform edge proposals, then process in exact order.
    # Equal edge proposals are rejected, giving the same uniform distinct pair
    # law as sampling without replacement, with a new declared seed sequence.
    width = int(max(sources.max(initial=0), original_targets.max(initial=0))) + 1
    encoded_pairs = {int(source) * width + int(target) for source, target in zip(sources, rewired, strict=True)}
    while completed < swap_count and attempts < maximum_attempts:
        size = min(max(4096, (swap_count - completed) * 2), 1_000_000, maximum_attempts-attempts)
        proposals = eligible[rng.integers(0, eligible.size, size=(size, 2))]
        done, used = _swap_proposals(sources, rewired, proposals, encoded_pairs, width, swap_count-completed)
        completed += done
        attempts += used
    if completed != swap_count:
        raise RuntimeError(
            f"completed {completed} of {swap_count} swaps after {attempts} proposals"
        )
    if np.any(rewired[frozen] != original_targets[frozen]):
        raise RuntimeError("a frozen edge changed")
    if not np.array_equal(sources == rewired, sources == original_targets):
        raise RuntimeError("self-loop set changed")
    validate_simple_directed_graph(sources, rewired)
    return SwapResult(rewired, completed, attempts)



@njit(cache=True)
def _swap_proposals(sources, targets, proposals, pairs, width, requested):
    completed = 0
    used = 0
    for row in proposals:
        used += 1
        first, second = row[0], row[1]
        a, b = sources[first], sources[second]
        x, y = targets[first], targets[second]
        if a == b or x == y or a == y or b == x:
            continue
        new1, new2 = a*width+y, b*width+x
        if new1 in pairs or new2 in pairs:
            continue
        pairs.remove(a*width+x)
        pairs.remove(b*width+y)
        pairs.add(new1)
        pairs.add(new2)
        targets[first], targets[second] = y, x
        completed += 1
        if completed == requested:
            break
    return completed, used

def _edge_sources(offsets: np.ndarray) -> np.ndarray:
    return np.repeat(
        np.arange(offsets.size - 1, dtype=np.int64), np.diff(offsets).astype(np.int64)
    )


def _ks_statistic(left: np.ndarray, right: np.ndarray) -> float:
    left_sorted = np.sort(np.asarray(left, dtype=np.float64))
    right_sorted = np.sort(np.asarray(right, dtype=np.float64))
    values = np.sort(np.unique(np.concatenate((left_sorted, right_sorted))))
    left_cdf = np.searchsorted(left_sorted, values, side="right") / left_sorted.size
    right_cdf = np.searchsorted(right_sorted, values, side="right") / right_sorted.size
    return float(np.max(np.abs(left_cdf - right_cdf))) if values.size else 0.0


def _input_strength(targets: np.ndarray, values: np.ndarray, node_count: int) -> np.ndarray:
    return np.bincount(targets, weights=values, minlength=node_count).astype(np.float64)


def _input_ratio(targets: np.ndarray, weights: np.ndarray, node_count: int) -> np.ndarray:
    excitatory = _input_strength(targets, np.maximum(weights, 0.0), node_count)
    inhibitory = _input_strength(targets, np.maximum(-weights, 0.0), node_count)
    total = excitatory + inhibitory
    ratio = np.full(node_count, np.nan, dtype=np.float64)
    active = total > 0.0
    ratio[active] = excitatory[active] / total[active]
    return ratio


def _shortest_paths(
    sources: np.ndarray,
    targets: np.ndarray,
    node_count: int,
    visual_indices: set[int],
    output_indices: set[int],
    body_id_by_index: dict[int, int],
) -> dict[str, int | None]:
    adjacency: list[list[int]] = [[] for _ in range(node_count)]
    for source, target in zip(sources, targets, strict=True):
        adjacency[int(source)].append(int(target))
    distance = np.full(node_count, -1, dtype=np.int64)
    queue: deque[int] = deque()
    for source in sorted(visual_indices):
        distance[source] = 0
        queue.append(source)
    while queue:
        source = queue.popleft()
        for target in adjacency[source]:
            if distance[target] != -1:
                continue
            distance[target] = distance[source] + 1
            queue.append(target)
    return {
        str(body_id_by_index[index]): None if distance[index] < 0 else int(distance[index])
        for index in sorted(output_indices)
    }


def null_diagnostics(
    sources: np.ndarray,
    original_targets: np.ndarray,
    rewired_targets: np.ndarray,
    counts: np.ndarray,
    weights: np.ndarray,
    node_count: int,
    visual_indices: set[int],
    output_indices: set[int],
    body_id_by_index: dict[int, int] | None = None,
) -> dict[str, Any]:
    original_indegree = np.bincount(original_targets, minlength=node_count)
    rewired_indegree = np.bincount(rewired_targets, minlength=node_count)
    original_outdegree = np.bincount(sources, minlength=node_count)
    rewired_outdegree = np.bincount(sources, minlength=node_count)
    original_source_strength = np.bincount(sources, weights=counts, minlength=node_count)
    rewired_source_strength = np.bincount(sources, weights=counts, minlength=node_count)
    original_source_signed = np.bincount(sources, weights=weights, minlength=node_count)
    rewired_source_signed = np.bincount(sources, weights=weights, minlength=node_count)
    original_in_strength = _input_strength(original_targets, counts, node_count)
    rewired_in_strength = _input_strength(rewired_targets, counts, node_count)
    original_ratio = _input_ratio(original_targets, weights, node_count)
    rewired_ratio = _input_ratio(rewired_targets, weights, node_count)
    finite_ratio = np.isfinite(original_ratio) & np.isfinite(rewired_ratio)
    ratio_shift = np.abs(original_ratio[finite_ratio] - rewired_ratio[finite_ratio])
    body_ids = body_id_by_index or {index: index for index in output_indices}
    shortest = _shortest_paths(
        sources,
        rewired_targets,
        node_count,
        visual_indices,
        output_indices,
        body_ids,
    )
    return {
        "self_loops_identical": bool(np.array_equal(sources == original_targets, sources == rewired_targets)),
        "no_new_self_loops": bool(not np.any((sources == rewired_targets) & (sources != original_targets))),
        "in_degree_by_effective_sign_exact": all(
                np.array_equal(np.bincount(original_targets[np.sign(weights) == sign], minlength=node_count),
                               np.bincount(rewired_targets[np.sign(weights) == sign], minlength=node_count))
                for sign in (-1, 0, 1)),
        "degree_preservation": {
            "out_degree_exact": bool(np.array_equal(original_outdegree, rewired_outdegree)),
            "in_degree_exact": bool(np.array_equal(original_indegree, rewired_indegree)),
            "per_source_out_strength_exact": bool(
                np.array_equal(original_source_strength, rewired_source_strength)
            ),
            "per_source_signed_weight_exact": bool(
                np.array_equal(original_source_signed, rewired_source_signed)
            ),
        },
        "fraction_edges_changed": float(np.mean(original_targets != rewired_targets)),
        "in_strength_distribution_shift_ks": _ks_statistic(
            original_in_strength, rewired_in_strength
        ),
        "excitatory_inhibitory_input_ratio_shift": {
            "comparable_neurons": int(np.count_nonzero(finite_ratio)),
            "mean_absolute": float(np.mean(ratio_shift)) if ratio_shift.size else None,
            "maximum_absolute": float(np.max(ratio_shift)) if ratio_shift.size else None,
            "ks": (
                _ks_statistic(original_ratio[finite_ratio], rewired_ratio[finite_ratio])
                if np.any(finite_ratio)
                else None
            ),
        },
        "visual_to_output": {
            "reachable": {
                output: distance is not None for output, distance in shortest.items()
            },
            "shortest_path_lengths": shortest,
        },
    }


def _output_body_ids() -> set[int]:
    ports = json.loads(PORTS.read_text(encoding="utf-8"))["populations"]
    outputs = {int(value) for value in ports["DNp01"]["body_ids_decimal"]}
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    for name in ("MDN", "P9", "oDN1", "BPN", "DNa01", "DNa02"):
        outputs.update(
            int(match["body_id"])
            for match in candidates["names"][name]
            if match["match_kind"] == "exact type"
        )
    return outputs


def _graph_inputs(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    ids = np.load(directory / "ids.npy", mmap_mode="r", allow_pickle=False)
    offsets = np.load(directory / "offsets.npy", mmap_mode="r", allow_pickle=False)
    targets = np.load(directory / "targets.npy", mmap_mode="r", allow_pickle=False)
    counts = np.load(directory / "counts.npy", mmap_mode="r", allow_pickle=False)
    weights = np.load(directory / "weights.npy", mmap_mode="r", allow_pickle=False)
    sources = _edge_sources(offsets)
    index_by_id = {int(value): index for index, value in enumerate(ids)}
    ports = json.loads(PORTS.read_text(encoding="utf-8"))["populations"]
    visual_body_ids = {
        int(value)
        for name in ("LC4", "LPLC2")
        for value in ports[name]["body_ids_decimal"]
    }
    output_body_ids = _output_body_ids()
    visual_indices = {index_by_id[value] for value in visual_body_ids if value in index_by_id}
    output_indices = {index_by_id[value] for value in output_body_ids if value in index_by_id}
    return {
        "ids": ids,
        "sources": sources,
        "targets": np.asarray(targets),
        "counts": np.asarray(counts),
        "weights": np.asarray(weights, dtype=np.float64),
        "visual_indices": visual_indices,
        "output_indices": output_indices,
        "body_id_by_index": {
            index: int(ids[index]) for index in output_indices
        },
        "semantic_graph_digest": manifest["semantic_digest"]["value"],
    }


def generate(out: Path) -> dict[str, Any]:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    results = []
    for graph_index, graph_entry in enumerate(profile["graphs"]):
        directory = ROOT / graph_entry["path"]
        graph = _graph_inputs(directory)
        sources = graph["sources"]
        targets = graph["targets"]
        direct_visual_output = np.fromiter(
            (
                int(source) in graph["visual_indices"]
                and int(target) in graph["output_indices"]
                for source, target in zip(sources, targets, strict=True)
            ),
            dtype=np.bool_,
            count=sources.size,
        )
        families = []
        for family_index, family in enumerate(("N-FULL", "N-CONTEXT")):
            frozen = (
                np.zeros(sources.size, dtype=np.bool_)
                if family == "N-FULL"
                else direct_visual_output
            )
            nulls = []
            swap_count = int(round(float(profile["swap_count_multiple_of_E"]) * sources.size))
            for null_index in range(int(profile["nulls_per_family_graph"])):
                seed = (
                    int(profile["seed_rule"]["base_seed"])
                    + graph_index * 100_000
                    + family_index * 10_000
                    + null_index
                )
                swapped = directed_double_edge_swap(
                    sources,
                    targets,
                    swap_count=swap_count,
                    seed=seed,
                    frozen_edges=frozen,
                    maximum_attempt_multiple=int(
                        profile["maximum_proposal_attempt_multiple"]
                    ),
                )
                diagnostics = null_diagnostics(
                    sources,
                    targets,
                    swapped.targets,
                    graph["counts"],
                    graph["weights"],
                    graph["ids"].size,
                    graph["visual_indices"],
                    graph["output_indices"],
                    graph["body_id_by_index"],
                )
                diagnostics.update(
                    {
                        "index": null_index,
                        "seed": seed,
                        "requested_swaps": swap_count,
                        "completed_swaps": swapped.completed_swaps,
                        "proposal_attempts": swapped.proposal_attempts,
                        "frozen_edges": int(np.count_nonzero(frozen)),
                        "frozen_edges_unchanged": bool(
                            np.array_equal(swapped.targets[frozen], targets[frozen])
                        ),
                        "self_loops": int(np.count_nonzero(sources == swapped.targets)),
                        "multi_edges": sources.size
                        - len(
                            {
                                (int(source), int(target))
                                for source, target in zip(
                                    sources, swapped.targets, strict=True
                                )
                            }
                        ),
                    }
                )
                nulls.append(diagnostics)
            families.append(
                {
                    "family": family,
                    "eligible_edges": int(np.count_nonzero(~frozen)),
                    "frozen_edges": int(np.count_nonzero(frozen)),
                    "nulls": nulls,
                }
            )
        results.append(
            {
                "graph_id": graph_entry["id"],
                "graph_path": graph_entry["path"],
                "semantic_graph_digest": graph["semantic_graph_digest"],
                "N": int(graph["ids"].size),
                "E": int(sources.size),
                "families": families,
            }
        )
    report = {
        "schema": "flybench.v2a.null-diagnostics",
        "version": 1,
        "status": "SUBMITTED",
        "profile": str(PROFILE.relative_to(ROOT)),
        "graphs": results,
    }
    write_json(out / "null-diagnostics.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m flybench.nulls")
    commands = parser.add_subparsers(dest="command", required=True)
    generate_parser = commands.add_parser("generate")
    generate_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        report = generate(args.out.resolve())
        print(
            json.dumps(
                {"status": "PASS", "graphs": len(report["graphs"]), "out": str(args.out.resolve())},
                sort_keys=True,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
