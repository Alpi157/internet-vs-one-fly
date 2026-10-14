"""Threshold-relative units and isolated-neuron noise calibration.

No circuit or behavioral output enters the noise-table calculation.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json

from numba import njit
import numpy as np

from flybench.kernel_v2 import _counter_u32
from flybench.graph import write_json

V_DECAY = float.fromhex('0x1.f35bd21f40adcp-1')
I_DECAY = float.fromhex('0x1.cf46d99d52b3ap-1')
COUPLING = 5.0 / (5.0 - 20.0) * (I_DECAY - V_DECAY)
NOISE_STREAM = 17
ISOLATED_SEED = 2026101401


def unit_psp() -> tuple[float, int]:
    """Exact discrete recurrence from ReferenceStateV2, unit arrival at tick 0.

    v[n]=(b**n-a**n)/3, where a=current decay and b=voltage decay.
    Evaluate the recurrence until its first decrease; there is one maximum.
    """
    voltage, current, peak, peak_tick = 0.0, 1.0, 0.0, 0
    for end_tick in range(1, 10000):
        voltage = voltage * V_DECAY + current * COUPLING
        current = current * I_DECAY
        if voltage < peak:
            return peak, peak_tick
        peak, peak_tick = voltage, end_tick
    raise RuntimeError('unit PSP did not peak')


@njit(cache=True)
def isolated_count(threshold: int, increment: float, seed: int, ticks: int) -> int:
    voltage = 0.0
    current = 0.0
    until = 0
    count = 0
    for tick in range(ticks):
        if np.uint64(_counter_u32(seed, NOISE_STREAM, tick, 0)) < np.uint64(threshold):
            current += increment
        boundary = current
        current = boundary * I_DECAY
        if tick >= until:
            voltage = voltage * V_DECAY + boundary * COUPLING
            if voltage >= 1.0:
                count += 1
                voltage = 0.0
                until = tick + 1 + 4
        else:
            voltage = 0.0
    return count


def build_noise_table(output: Path) -> dict:
    peak, peak_tick = unit_psp()
    seconds = 200.0
    ticks = int(seconds * 2000)
    rows = []
    for kappa in (0.02, 0.05, 0.10):
        increment = kappa / peak
        for target in (0.5, 2.0, 5.0):
            low, high = 0, 2**32
            evaluated = {}
            # The finite, reset neuron need not be strictly monotone in a
            # Bernoulli threshold. Deterministic bracket search is declared;
            # retain closest evaluated count and publish any residual error.
            for _ in range(32):
                mid = (low + high) // 2
                rate = isolated_count(mid, increment, ISOLATED_SEED, ticks) / seconds
                evaluated[mid] = rate
                if rate < target:
                    low = mid + 1
                else:
                    high = mid
            threshold = min(evaluated, key=lambda t: (abs(evaluated[t]-target),t))
            rows.append(dict(kappa=kappa, nu0_hz=target, w_noise=increment,
                p_per_tick=threshold/2**32, threshold_int=threshold,
                measured_isolated_rate_hz=evaluated[threshold],
                relative_error=abs(evaluated[threshold]-target)/target))
    result = dict(schema='flybench.noise-table.v1', profile_id='flybench.noise-table.v1',
        rng='flybench.u32.v2', seed=ISOLATED_SEED, stream=NOISE_STREAM,
        population='all circuit neurons', seconds=seconds, ticks=ticks,
        rest=0, threshold=1, psp_unit=peak, peak_end_tick=peak_tick,
        method='32 integer-threshold bisections from [0,2**32]; closest measured rate, threshold ascending tie break; no circuit output',
        rows=rows)
    write_json(output, result)
    return result


FIT_SEEDS = (2026101401, 2026101402, 2026101403, 2026101404)
VALIDATION_SEEDS = (2026101411, 2026101412)


def build_noise_table_v2(output: Path) -> dict:
    """E3: common random numbers, pooled fit, independent pooled validation."""
    import math
    import time
    started = time.perf_counter()
    peak, peak_tick = unit_psp()
    rows = []
    for kappa in (.02, .05, .10):
        increment = kappa / peak
        for target in (.5, 2., 5.):
            low, high = 0, 2**32
            evaluated = {}
            for _ in range(32):
                mid = (low + high) // 2
                counts = [int(isolated_count(mid, increment, seed, 2_000_000)) for seed in FIT_SEEDS]
                rate = sum(counts) / 4000
                evaluated[mid] = counts
                if rate < target:
                    low = mid + 1
                else:
                    high = mid
            threshold = min(evaluated, key=lambda t: (abs(sum(evaluated[t])/4000-target), t))
            counts = [int(isolated_count(threshold, increment, seed, 4_000_000)) for seed in VALIDATION_SEEDS]
            rate = sum(counts) / 4000
            tolerance = max(.05*target, 3*math.sqrt(target/4000))
            passed = abs(rate-target) <= tolerance
            row = dict(kappa=kappa, nu0_hz=target, w_noise=increment,
                threshold_int=threshold, p_per_tick=threshold/2**32,
                fit_counts=evaluated[threshold], fit_rate_hz=sum(evaluated[threshold])/4000,
                validation_counts=counts, validation_rate_hz=rate,
                tolerance_hz=tolerance, passes=passed,
                evaluations=[dict(threshold_int=t, counts=c) for t,c in evaluated.items()])
            rows.append(row)
            print(kappa, target, rate, passed, flush=True)
    result = dict(schema='flybench.noise-table.v2', profile_id='flybench.noise-table.v2',
        rng='flybench.u32.v2', stream=17, noise_profile='profiles/noise-v2.json',
        fit_seeds=FIT_SEEDS, fit_seconds_per_seed=1000, validation_seeds=VALIDATION_SEEDS,
        validation_seconds_per_seed=2000, psp_unit=peak, peak_end_tick=peak_tick,
        tolerance='pooled validation rate within max(0.05*nu0, 3*sqrt(nu0/4000)) Hz',
        method='32 integer bisections; closest pooled fit count; ascending threshold ties; common random numbers; no refit after validation',
        rows=rows)
    write_json(output, result)
    print('wall_seconds', time.perf_counter()-started, flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path)
    parser.add_argument('--v2', action='store_true')
    args = parser.parse_args()
    output=args.out or Path('profiles/noise-table-v2.json' if args.v2 else 'profiles/noise-table-v1.json')
    print(json.dumps((build_noise_table_v2 if args.v2 else build_noise_table)(output)))


if __name__ == '__main__':
    main()
