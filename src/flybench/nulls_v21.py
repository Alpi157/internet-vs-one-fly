"""v2.1 nulls. Source attributes stay attached to their original edge slots."""
import numpy as np
from numba import njit
from flybench.nulls import _ks_statistic, _input_ratio
from numba.typed import Dict
from numba import types

BIN_UPPER = np.array([1, 2, 4, 8, 16, 32, 64, 128], dtype=np.uint64)


@njit(cache=True)
def pair_set(sources, targets, width):
    pairs = Dict.empty(key_type=types.int64, value_type=types.boolean)
    for i in range(len(sources)):
        key = sources[i] * width + targets[i]
        if key in pairs:
            raise ValueError('multi-edge in input')
        pairs[key] = True
    return pairs


@njit(cache=True)
def swap_proposals(sources, targets, proposals, pairs, width, requested):
    completed = used = 0
    for row in proposals:
        used += 1
        first, second = row[0], row[1]
        a, b = sources[first], sources[second]
        x, y = targets[first], targets[second]
        if a == b or x == y or a == y or b == x:
            continue
        new1, new2 = a*width+y, b*width+x
        if new1 in pairs or new2 in pairs:
            continue
        del pairs[a*width+x]
        del pairs[b*width+y]
        pairs[new1] = True
        pairs[new2] = True
        targets[first], targets[second] = y, x
        completed += 1
        if completed == requested:
            break
    return completed, used


def strength_swap(sources, targets, counts, weights, *, seed, multiple=1,
                  maximum_attempt_multiple=100, family="N-STRENGTH"):
    """Request E_stratum swaps, bounded at 100 proposals per requested swap.

    A global pair set prevents duplicate edges across contact bins. Small or
    immobile strata remain explicit, with their incomplete swap budgets reported.
    Autapses count toward the budget but cannot participate in a proposal.
    """
    sources = np.asarray(sources, dtype=np.int64)
    original = np.asarray(targets, dtype=np.int64)
    counts = np.asarray(counts)
    weights = np.asarray(weights)
    if (sources.ndim != 1 or any(v.shape != sources.shape for v in (original, counts, weights))
            or np.any(sources < 0) or np.any(original < 0) or np.any(counts < 1)
            or not np.issubdtype(counts.dtype, np.integer) or not np.all(np.isfinite(weights))):
        raise ValueError('invalid edge arrays')
    if type(seed) is not int or seed < 0 or type(multiple) is not int or multiple < 0:
        raise ValueError('invalid seed or swap budget')
    if type(maximum_attempt_multiple) is not int or maximum_attempt_multiple < 1:
        raise ValueError('invalid proposal bound')
    n = int(max(sources.max(initial=0), original.max(initial=0))) + 1
    signs = np.sign(weights).astype(np.int8)
    low, high = np.full(n, 2), np.full(n, -2)
    np.minimum.at(low, sources, signs); np.maximum.at(high, sources, signs)
    if np.any((low <= 1) & (low != high)):
        raise ValueError('inconsistent presynaptic effective sign')
    bins = np.searchsorted(BIN_UPPER, counts, side='left')
    if family not in ("N-STRENGTH", "N-SIGN", "N-FULL"):
        raise ValueError("unknown null family")
    if family != "N-STRENGTH": bins = np.zeros(len(sources), dtype=np.int8)
    if family == "N-FULL": signs = np.zeros(len(sources), dtype=np.int8)
    rewired = original.copy()
    pairs = pair_set(sources, rewired, n)
    strata = {}
    for sign in (-1, 0, 1):
        for bin_index in range(9):
            mask = (signs == sign) & (bins == bin_index)
            eligible = np.flatnonzero(mask & (sources != original))
            requested = int(mask.sum()) * multiple
            rng = np.random.Generator(np.random.PCG64(seed + (sign+1)*9 + bin_index))
            done = attempts = 0
            limit = requested * maximum_attempt_multiple
            while done < requested and attempts < limit and len(eligible) >= 2:
                size = min(max(4096, (requested-done)*3), 1_000_000, limit-attempts)
                proposals = eligible[rng.integers(0, len(eligible), size=(size, 2))]
                completed, used = swap_proposals(sources, rewired, proposals, pairs, n, requested-done)
                done += completed; attempts += used
            strata[f'{sign}:{bin_index}'] = dict(edges=int(mask.sum()), eligible_edges=len(eligible),
                requested_swaps=requested, completed_swaps=done, proposal_attempts=attempts,
                fraction_changed=float(np.mean(rewired[mask] != original[mask])) if mask.any() else 0.)
            if not np.array_equal(np.bincount(original[mask], minlength=n), np.bincount(rewired[mask], minlength=n)):
                raise RuntimeError('sign/bin incoming degree changed')
    if not np.array_equal(sources == original, sources == rewired):
        raise RuntimeError('autapses changed')
    return rewired.astype(np.int32), strata


def diagnostics(sources, original, targets, counts, weights, n):
    signs = np.sign(weights)
    ks = {}
    for sign in (-1, 0, 1):
        mask = signs == sign
        a = np.bincount(original[mask], weights=counts[mask], minlength=n)
        b = np.bincount(targets[mask], weights=counts[mask], minlength=n)
        ks[str(sign)] = _ks_statistic(a, b)
    a, b = _input_ratio(original, weights, n), _input_ratio(targets, weights, n)
    valid = np.isfinite(a) & np.isfinite(b)
    delta = np.abs(a[valid]-b[valid])
    return dict(fraction_edges_changed=float(np.mean(original != targets)),
        in_strength_ks_by_effective_sign=ks,
        excitatory_inhibitory_input_ratio_shift=dict(comparable_neurons=int(valid.sum()),
            mean_absolute=float(delta.mean()) if len(delta) else None,
            maximum_absolute=float(delta.max()) if len(delta) else None,
            ks=_ks_statistic(a[valid], b[valid]) if len(delta) else None))
