from __future__ import annotations

import numpy as np
import pytest

from flybench.nulls import directed_double_edge_swap


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
        (np.asarray([0]), np.asarray([0]), "self-loop"),
        (np.asarray([0, 0]), np.asarray([1, 1]), "multi-edge"),
    ],
)
def test_invalid_simple_graphs_are_rejected(
    sources: np.ndarray, targets: np.ndarray, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        directed_double_edge_swap(sources, targets, swap_count=0, seed=1)
