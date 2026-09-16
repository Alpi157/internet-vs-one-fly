"""Immutable numerical configuration for the FlyBench reference neural model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any


BASE_MODEL_PROFILE_SHA256 = "564c553f750ab9ef275014bbfc67d2b62ed5992fceb80185e09d7966d52b451a"
INTEGRATION_VERSION = "flybench.exact-linear-lif.v1"
EVENT_ORDER_VERSION = "flybench.neural-order.v1"
RNG_ALGORITHM = "PCG64"
STATE_DTYPE = "float64"
THRESHOLD_COMPARATOR = ">="
GRID_RATIO_ABS_TOL = 1e-12


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def duration_ticks(duration_ms: float, dt_ms: float, *, name: str) -> int:
    """Return an exact positive tick count or reject the unsupported grid."""

    if not math.isfinite(duration_ms) or duration_ms <= 0:
        raise ValueError(f"{name} must be a finite positive duration")
    if not math.isfinite(dt_ms) or dt_ms <= 0:
        raise ValueError("neural_dt_ms must be finite and positive")
    ratio = duration_ms / dt_ms
    nearest = round(ratio)
    if nearest <= 0 or not math.isclose(
        ratio, float(nearest), rel_tol=0.0, abs_tol=GRID_RATIO_ABS_TOL
    ):
        raise ValueError(
            f"{name}={duration_ms!r} ms is not an integer number of "
            f"neural_dt_ms={dt_ms!r} ticks (ratio={ratio!r})"
        )
    return int(nearest)


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Complete immutable identity of one reference numerical configuration."""

    base_model_profile_sha256: str
    numerical_criteria_sha256: str
    tau_m_ms: float
    tau_s_ms: float
    rest: float
    reset: float
    threshold: float
    refractory_ms: float
    delay_ms: float
    neural_dt_ms: float
    runtime_synaptic_scale: float
    seed: int
    integration_version: str = INTEGRATION_VERSION
    event_order_version: str = EVENT_ORDER_VERSION
    threshold_comparator: str = THRESHOLD_COMPARATOR
    state_dtype: str = STATE_DTYPE
    rng_algorithm: str = RNG_ALGORITHM

    def __post_init__(self) -> None:
        numeric = (
            self.tau_m_ms,
            self.tau_s_ms,
            self.refractory_ms,
            self.delay_ms,
            self.neural_dt_ms,
            self.runtime_synaptic_scale,
        )
        if not all(math.isfinite(value) and value > 0 for value in numeric):
            raise ValueError("time constants, durations, dt, and runtime scale must be positive")
        if not all(
            math.isfinite(value)
            for value in (self.rest, self.reset, self.threshold)
        ):
            raise ValueError("voltage parameters must be finite")
        if self.threshold <= self.reset:
            raise ValueError("threshold must be greater than reset")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if self.base_model_profile_sha256 != BASE_MODEL_PROFILE_SHA256:
            raise ValueError("base M04 model profile identity does not match the accepted profile")
        if len(self.numerical_criteria_sha256) != 64:
            raise ValueError("numerical criteria SHA-256 must contain 64 hexadecimal characters")
        int(self.numerical_criteria_sha256, 16)
        if self.integration_version != INTEGRATION_VERSION:
            raise ValueError("unsupported integration version")
        if self.event_order_version != EVENT_ORDER_VERSION:
            raise ValueError("unsupported event-order version")
        if self.threshold_comparator != THRESHOLD_COMPARATOR:
            raise ValueError("threshold comparator must be >=")
        if self.state_dtype != STATE_DTYPE:
            raise ValueError("reference state must use float64")
        if self.rng_algorithm != RNG_ALGORITHM:
            raise ValueError("reference RNG must use PCG64")
        duration_ticks(self.delay_ms, self.neural_dt_ms, name="delay_ms")
        duration_ticks(self.refractory_ms, self.neural_dt_ms, name="refractory_ms")

    @property
    def delay_ticks(self) -> int:
        return duration_ticks(self.delay_ms, self.neural_dt_ms, name="delay_ms")

    @property
    def refractory_ticks(self) -> int:
        return duration_ticks(
            self.refractory_ms, self.neural_dt_ms, name="refractory_ms"
        )

    def canonical_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = 1
        payload["delay_ticks"] = self.delay_ticks
        payload["refractory_ticks"] = self.refractory_ticks
        payload["rng_seed_rule"] = (
            "each ReferenceState owns a distinct numpy Generator initialized from seed; "
            "reset recreates that owner from the same explicit seed"
        )
        payload["runtime_synaptic_scale_classification"] = (
            "MODEL ASSUMPTION; M05 numerical-fixture value, not behavioral calibration"
        )
        return payload

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_payload())

    @property
    def semantic_sha256(self) -> str:
        return sha256_bytes(self.canonical_bytes())


def load_candidate_model_spec(
    *,
    neural_dt_ms: float,
    runtime_synaptic_scale: float,
    seed: int,
    model_profile_path: Path,
    criteria_path: Path,
) -> ModelSpec:
    """Load and identity-check the accepted M04 candidate without modifying it."""

    model_bytes = model_profile_path.read_bytes()
    if sha256_bytes(model_bytes) != BASE_MODEL_PROFILE_SHA256:
        raise ValueError("accepted M04 model profile SHA-256 mismatch")
    criteria_bytes = criteria_path.read_bytes()
    model = json.loads(model_bytes)
    neuron = model["neuron_model"]
    expected = {
        "tau_m_ms": 20.0,
        "tau_s_ms": 5.0,
        "rest": 0.0,
        "reset": 0.0,
        "threshold": 1.0,
        "refractory_ms": 2.0,
        "delay_ms": 1.0,
    }
    actual = {name: float(neuron[name]) for name in expected}
    if actual != expected:
        raise ValueError("accepted M04 normalized-LIF parameters changed")
    return ModelSpec(
        base_model_profile_sha256=BASE_MODEL_PROFILE_SHA256,
        numerical_criteria_sha256=sha256_bytes(criteria_bytes),
        neural_dt_ms=float(neural_dt_ms),
        runtime_synaptic_scale=float(runtime_synaptic_scale),
        seed=seed,
        **actual,
    )


def select_supported_timestep(
    criteria: dict[str, Any],
    comparisons: dict[str, dict[str, Any]],
    *,
    analytical_pass: bool,
    boundary_pass: bool,
) -> tuple[float | None, str]:
    """Apply the predeclared coarsest-passing policy without changing criteria."""

    if not analytical_pass or not boundary_pass:
        return None, "analytical or boundary semantics failed at the reference configuration"
    for candidate in criteria["candidate_dt_order_ms"]:
        result = comparisons.get(format(float(candidate), "g"))
        if result is None:
            raise ValueError(f"missing comparison for candidate dt {candidate}")
        if result.get("status") == "PASS":
            return float(candidate), "coarsest candidate satisfying every frozen criterion"
    reference = float(criteria["reference_dt_ms"])
    return reference, "no coarser candidate passed; finest studied reference timestep required"
