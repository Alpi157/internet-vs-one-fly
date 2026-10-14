"""Deterministic counter RNGs and restricted-operation approximations."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from flybench.graph import write_json


MASK32 = 0xFFFFFFFF
UINT32_SCALE = 1 << 32
PI_OVER_2 = 1.5707963267948966
PI_OVER_4 = 0.7853981633974483
ATAN_CURVATURE = 0.273


def _u32(value: int) -> int:
    return value & MASK32


def u32_v1(seed: int, stream: int, tick: int, index: int) -> int:
    """Return one counter-based unsigned 32-bit value without float arithmetic."""

    if any(type(value) is not int or not 0 <= value < UINT32_SCALE for value in (seed, stream, tick, index)):
        raise ValueError("u32 counters must be nonnegative integers")
    value = _u32(seed + 0x9E3779B9)
    value = _u32(value ^ _u32(stream * 0x85EBCA6B))
    value = _u32(value + _u32(tick * 0xC2B2AE35))
    value = _u32(value ^ _u32(index * 0x27D4EB2F))
    value = _u32(value ^ (value >> 16))
    value = _u32(value * 0x7FEB352D)
    value = _u32(value ^ (value >> 15))
    value = _u32(value * 0x846CA68B)
    return _u32(value ^ (value >> 16))



def fmix32(value: int) -> int:
    value &= MASK32
    value ^= value >> 16
    value = (value * 0x85EBCA6B) & MASK32
    value ^= value >> 13
    value = (value * 0xC2B2AE35) & MASK32
    return (value ^ (value >> 16)) & MASK32


def u32(seed: int, stream: int, tick: int, index: int) -> int:
    """flybench.u32.v2; every input is a u32 counter, no implicit wrapping."""
    if any(type(v) is not int or not 0 <= v < UINT32_SCALE for v in (seed, stream, tick, index)):
        raise ValueError("u32 counters must be integers in [0, 2**32)")
    h = fmix32(seed + 0x9E3779B9)
    h = fmix32(h ^ stream)
    h = fmix32(h + tick)
    return fmix32(h ^ index)

def probability_threshold(probability: float) -> int:
    """Build a profile threshold once using round-half-up semantics."""

    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be finite and within [0, 1]")
    return min(UINT32_SCALE, int(math.floor(probability * UINT32_SCALE + 0.5)))


def bernoulli(seed: int, stream: int, tick: int, index: int, threshold: int) -> bool:
    if type(threshold) is not int or not 0 <= threshold <= UINT32_SCALE:
        raise ValueError("threshold must be an integer within [0, 2**32]")
    return u32(seed, stream, tick, index) < threshold


def atan_approx(value: float) -> float:
    """Approximate atan on [-8, 8] using a declared reciprocal reduction."""

    if not math.isfinite(value) or value < -8.0 or value > 8.0:
        raise ValueError("atan approximation input must be within [-8, 8]")
    sign = -1.0 if value < 0.0 else 1.0
    magnitude = -value if value < 0.0 else value
    # Two half-angle reductions put |z| <= tan(pi/8) after reciprocal
    # reduction, then <= tan(pi/16). Alternating Taylor remainder <=
    # 4*z**19/19 < 1.0e-13 rad. Fixed order is shared with TypeScript.
    reduced = 1.0 / magnitude if magnitude > 1.0 else magnitude
    for _ in range(2):
        reduced = reduced / (1.0 + math.sqrt(1.0 + reduced * reduced))
    square = reduced * reduced
    term = reduced
    core = term
    for k in range(1, 9):
        term = -term * square
        core = core + term / (2 * k + 1)
    core = 4.0 * core
    result = PI_OVER_2 - core if magnitude > 1.0 else core
    return sign * result


def rotate_unit_step(
    heading_x: float, heading_y: float, delta_radians: float
) -> tuple[float, float]:
    """Rotate by a normalized tangent step using only restricted operations."""

    if not all(math.isfinite(value) for value in (heading_x, heading_y, delta_radians)):
        raise ValueError("rotation inputs must be finite")
    if delta_radians < -0.05 or delta_radians > 0.05:
        raise ValueError("rotation delta must be within [-0.05, 0.05]")
    next_x = heading_x - delta_radians * heading_y
    next_y = heading_y + delta_radians * heading_x
    magnitude = math.sqrt(next_x * next_x + next_y * next_y)
    if magnitude == 0.0:
        raise ValueError("heading must be nonzero")
    return next_x / magnitude, next_y / magnitude


def _hex(value: float) -> str:
    return float(value).hex()


def build_vectors() -> dict[str, Any]:
    rng = []
    legacy_rng = []
    for vector_index in range(1000):
        seed = 17 + vector_index * 104729
        stream = vector_index % 19
        tick = vector_index * 37
        index = (vector_index * 101) % 4096
        result = u32(seed, stream, tick, index)
        legacy_rng.append({"seed":seed,"stream":stream,"tick":tick,"index":index,"output_u32":u32_v1(seed,stream,tick,index)})
        rng.append(
            {
                "seed_hex": _hex(seed),
                "stream_hex": _hex(stream),
                "tick_hex": _hex(tick),
                "index_hex": _hex(index),
                "output_u32": result,
                "output_hex": _hex(result),
            }
        )
    atan_vectors = []
    for vector_index in range(1001):
        value = -8.0 + 16.0 * vector_index / 1000.0
        atan_vectors.append({"input_hex": _hex(value), "output_hex": _hex(atan_approx(value))})
    rotation_vectors = []
    for vector_index in range(1000):
        angle = 2.0 * math.pi * vector_index / 1000.0
        delta = -0.05 + 0.1 * ((vector_index * 37) % 1000) / 999.0
        heading_x = math.cos(angle)
        heading_y = math.sin(angle)
        output_x, output_y = rotate_unit_step(heading_x, heading_y, delta)
        rotation_vectors.append(
            {
                "heading_x_hex": _hex(heading_x),
                "heading_y_hex": _hex(heading_y),
                "delta_hex": _hex(delta),
                "output_x_hex": _hex(output_x),
                "output_y_hex": _hex(output_y),
            }
        )
    return {
        "schema": "flybench.detmath-vectors",
        "version": 2,
        "algorithm": "flybench.u32.v2",
        "rng": rng,
        "rng_v1_reproduction_only": legacy_rng,
        "approximations": {"atan": atan_vectors, "rotate_unit_step": rotation_vectors},
    }


def approximation_errors() -> dict[str, Any]:
    atan_inputs = np.linspace(-8.0, 8.0, 2_000_001, dtype=np.float64)
    atan_outputs = np.asarray([atan_approx(float(value)) for value in atan_inputs])
    atan_error = np.max(np.abs(atan_outputs - np.arctan(atan_inputs)))
    deltas = np.linspace(-0.05, 0.05, 1_000_001, dtype=np.float64)
    rotation_error = np.max(np.abs(np.arctan(deltas) - deltas))
    return {
        "atan": {
            "domain": [-8.0, 8.0],
            "measured_grid_points": int(atan_inputs.size),
            "maximum_absolute_error_radians": float(atan_error),
            "maximum_relative_error": float(max(abs(atan_approx(float(v))-math.atan(float(v)))/math.atan(float(v)) for v in np.geomspace(1e-4,8.0,100001))),
        },
        "rotate_unit_step": {
            "delta_domain_radians": [-0.05, 0.05],
            "measured_grid_points": int(deltas.size),
            "maximum_angular_error_radians": float(rotation_error),
        },
    }


def rng_sanity(sample_count: int = 1_000_000) -> dict[str, Any]:
    values = np.fromiter(
        (u32(20260928, 31, tick, 0) for tick in range(sample_count)),
        dtype=np.uint32,
        count=sample_count,
    )
    scaled = values.astype(np.float64) / UINT32_SCALE
    neighboring = np.fromiter(
        (u32(20260928, 31, tick, 1) for tick in range(sample_count)),
        dtype=np.uint32,
        count=sample_count,
    ).astype(np.float64) / UINT32_SCALE
    rates = []
    for probability in (0.001, 0.01, 0.1):
        threshold = probability_threshold(probability)
        events = values.astype(np.uint64) < threshold
        rates.append(
            {
                "p": probability,
                "threshold": threshold,
                "successes": int(np.count_nonzero(events)),
                "trials": sample_count,
                "empirical_rate": float(np.mean(events)),
            }
        )
    return {
        "schema": "flybench.v2c.basic-rng-sanity",
        "version": 2,
        "algorithm": "flybench.u32.v2",
        "sample_count": sample_count,
        "bernoulli": rates,
        "lag_1_autocorrelation_over_ticks": float(np.corrcoef(scaled[:-1], scaled[1:])[0, 1]),
        "cross_correlation_neighboring_indices": float(np.corrcoef(scaled, neighboring)[0, 1]),
        "approximation_error": approximation_errors(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m flybench.detmath")
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    write_json(args.vectors.resolve(), build_vectors())
    write_json(args.out.resolve() / "rng-sanity.json", rng_sanity())
    print(json.dumps({"status": "PASS", "vectors": str(args.vectors), "out": str(args.out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
