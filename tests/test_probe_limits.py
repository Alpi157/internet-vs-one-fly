from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "flybench_m07_performance_probe", ROOT / "experiments/performance_probe.py"
)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)
error_worker = PROBE.error_worker
finite_delay_worker = PROBE.finite_delay_worker
run_worker_with_timeout = PROBE.run_worker_with_timeout


def test_forced_worker_timeout_is_reaped_and_partial_is_not_complete(tmp_path: Path) -> None:
    result = run_worker_with_timeout(
        finite_delay_worker,
        (0.2, 2),
        timeout_seconds=0.03,
        interval_capacity=3,
        temporary_parent=tmp_path,
    )
    assert result["status"] == "TIMEOUT"
    assert result["completed_intervals"] == 2
    assert result["raw_interval_timings_ns"] == [1, 2]
    assert result["worker_alive_after_join"] is False
    assert result["temporary_worker_state_released"] is True
    assert list(tmp_path.iterdir()) == []


def test_complete_result_schema(tmp_path: Path) -> None:
    result = run_worker_with_timeout(
        finite_delay_worker,
        (0.0, 3),
        timeout_seconds=1.0,
        interval_capacity=3,
        temporary_parent=tmp_path,
    )
    assert result["status"] == "COMPLETE"
    assert result["completed_intervals"] == 3
    assert result["worker_alive_after_join"] is False
    assert result["temporary_worker_state_released"] is True


def test_error_result_schema_and_cleanup(tmp_path: Path) -> None:
    result = run_worker_with_timeout(
        error_worker,
        (),
        timeout_seconds=1.0,
        interval_capacity=0,
        temporary_parent=tmp_path,
    )
    assert result["status"] == "ERROR"
    assert result["error_type"] == "RuntimeError"
    assert "deliberate bounded worker error" in result["error"]
    assert result["worker_alive_after_join"] is False
    assert result["temporary_worker_state_released"] is True
    assert list(tmp_path.iterdir()) == []


def test_status_values_are_distinct() -> None:
    assert {"TIMEOUT", "COMPLETE", "ERROR"} == set(
        ["TIMEOUT", "COMPLETE", "ERROR"]
    )
