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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('profiles/noise-table-v1.json'))
    args = parser.parse_args()
    print(json.dumps(build_noise_table(args.out)))


if __name__ == '__main__':
    main()
