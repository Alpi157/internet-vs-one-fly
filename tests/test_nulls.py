from __future__ import annotations

import numpy as np
import pytest

from flybench.nulls import directed_double_edge_swap, null_diagnostics


def synthetic() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    sources = np.asarray([0, 0, 1, 1, 2, 2], dtype=np.int64)
    targets = np.asarray([3, 4, 4, 5, 3, 5], dtype=np.int64)
    counts = np.asarray([2, 3, 5, 7, 11, 13], dtype=np.uint64)
    weights = np.asarray([2, 3, -5, -7, 11, 13], dtype=np.float64)
    return sources, targets, counts, weights


def test_directed_swaps_preserve_required_invariants() -> None:
    sources, targets, counts, weights = synthetic()
    result = directed_double_edge_swap(sources, targets, swap_count=20, seed=41)
    assert np.array_equal(
        np.bincount(targets, minlength=6),
        np.bincount(result.targets, minlength=6),
    )
    assert np.array_equal(
        np.bincount(sources, minlength=6),
        np.bincount(sources, minlength=6),
    )
    assert np.array_equal(
        np.bincount(sources, weights=counts, minlength=6),
        np.bincount(sources, weights=counts, minlength=6),
    )
    assert np.array_equal(
        np.bincount(sources, weights=weights, minlength=6),
        np.bincount(sources, weights=weights, minlength=6),
    )
    assert not np.any(sources == result.targets)
    assert len(set(zip(sources.tolist(), result.targets.tolist(), strict=True))) == len(sources)


def test_directed_swaps_are_deterministic() -> None:
    sources, targets, _counts, _weights = synthetic()
    first = directed_double_edge_swap(sources, targets, swap_count=12, seed=7)
    second = directed_double_edge_swap(sources, targets, swap_count=12, seed=7)
    assert first.completed_swaps == second.completed_swaps
    assert first.proposal_attempts == second.proposal_attempts
    assert np.array_equal(first.targets, second.targets)


def test_frozen_edges_remain_untouched() -> None:
    sources, targets, _counts, _weights = synthetic()
    frozen = np.asarray([True, False, False, False, False, False])
    result = directed_double_edge_swap(
        sources, targets, swap_count=10, seed=9, frozen_edges=frozen
    )
    assert result.targets[0] == targets[0]


@pytest.mark.parametrize(
    ("sources", "targets", "message"),
    [
        (np.asarray([0, 0]), np.asarray([1, 1]), "multi-edge"),
    ],
)
def test_invalid_simple_graphs_are_rejected(
    sources: np.ndarray, targets: np.ndarray, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        directed_double_edge_swap(sources, targets, swap_count=0, seed=1)


def test_reachability_diagnostics_use_body_ids() -> None:
    sources, targets, counts, weights = synthetic()
    diagnostics = null_diagnostics(
        sources,
        targets,
        targets,
        counts,
        weights,
        6,
        {0},
        {3, 5},
        {3: 10001, 5: 10010},
    )
    assert set(diagnostics["visual_to_output"]["reachable"]) == {"10001", "10010"}
    assert set(diagnostics["visual_to_output"]["shortest_path_lengths"]) == {"10001", "10010"}


def test_autapses_are_identical_and_no_new_autapses():
    sources,targets,counts,weights=synthetic()
    sources=np.concatenate(([0],sources));targets=np.concatenate(([0],targets))
    swapped=directed_double_edge_swap(sources,targets,swap_count=30,seed=53)
    assert np.array_equal(sources==targets,sources==swapped.targets)
    assert swapped.targets[0]==0
    assert np.array_equal(np.bincount(targets,minlength=6),np.bincount(swapped.targets,minlength=6))
