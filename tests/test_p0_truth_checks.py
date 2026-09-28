from __future__ import annotations

import math

import pytest

from experiments import p0_truth_checks as P0


ROOT = P0.ROOT


def test_seed_rule_is_deterministic_and_distinct() -> None:
    profile = {"seed_rule": {"base_seed": 100}}
    first = [P0.round_seed(profile, 2, index) for index in range(5)]
    second = [P0.round_seed(profile, 2, index) for index in range(5)]
    assert first == second
    assert len(set(first)) == len(first)
    assert set(first).isdisjoint(
        {P0.round_seed(profile, 3, index) for index in range(5)}
    )


@pytest.mark.parametrize(
    ("successes", "total", "expected"),
    [
        (0, 10, (0.0, 0.2775327998628892)),
        (5, 10, (0.236593090512564, 0.7634069094874361)),
        (10, 10, (0.7224672001371107, 1.0)),
    ],
)
def test_wilson_interval_arithmetic(
    successes: int, total: int, expected: tuple[float, float]
) -> None:
    actual = P0.wilson_interval(successes, total)
    assert math.isclose(actual[0], expected[0], rel_tol=0.0, abs_tol=1e-15)
    assert math.isclose(actual[1], expected[1], rel_tol=0.0, abs_tol=1e-15)


def test_fixed_latency_control_is_not_reachable_from_product_paths() -> None:
    for relative in (
        "src/flybench/game.py",
        "src/flybench/server.py",
        "src/flybench/runner.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "FixedLatencyController" not in source
        assert "p0_truth_checks" not in source
