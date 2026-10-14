"""V2D interior-only background population and rate-matched decoder control."""
from pathlib import Path
import json
import math
import numpy as np
from flybench.detmath import bernoulli, probability_threshold
from flybench.decoder_v2 import decode_spikes_v2

ROOT = Path(__file__).resolve().parents[2]
DECODER_NOISE_STREAM = 29


def interior_mask(ids: np.ndarray) -> np.ndarray:
    """Exclude every declared output, even UNKNOWN direction DNb02."""
    ports = json.loads((ROOT / 'profiles/ports-v2.json').read_text())['groups']
    visual = json.loads((ROOT / 'profiles/visual-ports-sides-v1.json').read_text())['populations']
    excluded = {int(e['body_id']) for group in ports.values() for e in group}
    for pop in ('LC4', 'LPLC2'):
        for side in ('left', 'right'):
            excluded.update(int(v) for v in visual[pop][f'{side}_body_ids_decimal'])
    return np.array([int(v) not in excluded for v in ids], dtype=np.bool_)


def decoder_noise_trial(groups, mean_rates_hz, seed, intervals, profile):
    """Independent per-output Bernoulli events, no network or threat input.

    Input rates must be measured on the same graph and calibration point. One
    unique counter index per output neuron; stream 29 is separate from network 17.
    """
    if len(mean_rates_hz) != 6 or any(not math.isfinite(v) or v < 0 or v > 2000 for v in mean_rates_hz):
        raise ValueError('six finite output rates in [0,2000] Hz required')
    ids = sorted(set(v for group in groups for v in group))
    thresholds = {}
    for group, rate in zip(groups, mean_rates_hz, strict=True):
        for body in group:
            if body in thresholds:
                raise ValueError('overlapping decoder groups')
            thresholds[body] = probability_threshold(rate / 2000)
    rates = (0.,) * 6
    held = (False, 0., 0.)
    records = []
    for ci in range(intervals):
        spikes = [body for tick in range(ci*20, (ci+1)*20) for index, body in enumerate(ids)
                  if bernoulli(seed, DECODER_NOISE_STREAM, tick, index, thresholds[body])]
        escape, speed, turn, rates = decode_spikes_v2(spikes, rates, groups,
            float.fromhex(profile['rate_filter']['decay_float64_hex']), .01,
            profile['forward_speed']['k_f'], profile['turn_rate']['k_t'],
            *profile['forward_speed']['clamp_arena_units_per_ms'], profile['turn_rate']['clamp_radians_per_ms'][1])
        records.append(dict(tick=(ci+1)*20, applied=held,
            group_counts=[sum(body in group for body in spikes) for group in groups]))
        held = (escape, speed, turn)
    return dict(records=records, seed=seed, stream=DECODER_NOISE_STREAM, measured_group_rates_hz=mean_rates_hz)


def measure_decoder_rates(runner, intervals=2000):
    """Measure rates from the supplied graph/point from an independent reset."""
    from flybench.encoding_v2 import HandStrikeV2
    runner.reset()
    counts=np.zeros(6,dtype=np.int64)
    for _ in range(intervals):
        counts+=runner.step(HandStrikeV2(False))['group_counts']
    return [int(count)/max(1,len(group))/(intervals*.01)
            for count,group in zip(counts,runner.groups,strict=True)]
