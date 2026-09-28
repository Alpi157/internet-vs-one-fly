"""Deterministic 32-bit random values and restricted-runtime approximations.

The u32 mixer is evaluated in this exact order, with every arithmetic result
reduced modulo 2**32:

1. x = seed + 0x9E3779B9
2. x = x xor (stream * 0x85EBCA6B)
3. x = x + (tick * 0xC2B2AE35)
4. x = x xor (index * 0x27D4EB2F)
5. x = x xor (x unsigned-shift-right 16)
6. x = x * 0x7FEB352D
7. x = x xor (x unsigned-shift-right 15)
8. x = x * 0x846CA68B
9. x = x xor (x unsigned-shift-right 16)

TypeScript uses Math.imul for multiplication and >>> 0 for reduction. Random
events compare the resulting integer to a threshold stored in the profile.
"""

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


def u32(seed: int, stream: int, tick: int, index: int) -> int:
    """Return one counter-based unsigned 32-bit value without float arithmetic."""

    if any(type(value) is not int or value < 0 for value in (seed, stream, tick, index)):
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
    reduced = 1.0 / magnitude if magnitude > 1.0 else magnitude
    core = reduced * (PI_OVER_4 + ATAN_CURVATURE * (1.0 - reduced))
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
    for vector_index in range(1000):
        seed = 17 + vector_index * 104729
        stream = vector_index % 19
        tick = vector_index * 37
        index = (vector_index * 101) % 4096
        result = u32(seed, stream, tick, index)
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
        "version": 1,
        "algorithm": "flybench.u32.v1",
        "rng": rng,
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
        "schema": "flybench.v2b.rng-sanity",
        "version": 1,
        "algorithm": "flybench.u32.v1",
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
