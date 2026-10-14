"""Extended RNG sanity report. No circuit or behavior simulation."""
from pathlib import Path
import argparse
import json
import math
from numba import njit
import numpy as np
from flybench.detmath import build_vectors, approximation_errors, probability_threshold
from flybench.kernel_v2 import _counter_u32, _counter_u32_v1, _fmix32
from flybench.graph import write_json


@njit(cache=True)
def values(version, seed, stream, dt, di, count):
    out = np.empty(count,dtype=np.uint32)
    for tick in range(count):
        if version == 1:
            out[tick] = _counter_u32_v1(seed,stream,tick+dt,di)
        else:
            out[tick] = _counter_u32(seed,stream,tick+dt,di)
    return out


@njit(cache=True)
def collision_pairs(version, seed, stream, ticks, n, histogram):
    pairs = 0
    repeated = 0
    maximum = 0
    for tick in range(ticks):
        for index in range(n):
            # Finalizers are permutations, so count before the finalizer.
            if version == 1:
                x = np.uint32(seed) + np.uint32(0x9E3779B9)
                x = np.uint32(x ^ np.uint32(np.uint32(stream)*np.uint32(0x85EBCA6B)))
                x = np.uint32(x + np.uint32(np.uint32(tick)*np.uint32(0xC2B2AE35)))
                x = np.uint32(x ^ np.uint32(np.uint32(index)*np.uint32(0x27D4EB2F)))
            else:
                x = _fmix32(np.uint32(seed)+np.uint32(0x9E3779B9))
                x = _fmix32(np.uint32(x ^ np.uint32(stream)))
                x = _fmix32(np.uint32(x + np.uint32(tick)))
                x = np.uint32(x ^ np.uint32(index))
            old = int(histogram[x])
            if old == 65535:
                raise RuntimeError('histogram overflow')
            pairs += old
            repeated += int(old > 0)
            histogram[x] = old+1
            maximum = max(maximum,old+1)
    return pairs,repeated,maximum


def run(out: Path, n: int):
    reports=[]
    count=1_000_000
    seed,stream=2026101401,17
    limit=4/math.sqrt(count)
    for version in (1,2):
        base=values(version,seed,stream,0,0,count)
        events=base < probability_threshold(.01)
        correlations=[]
        for dt in (0,1,2,3,4,8,16,32,64):
            for di in (0,1,2,3,4,8,16,32,64,128):
                if dt==di==0:continue
                other=values(version,seed,stream,dt,di,count) < probability_threshold(.01)
                r=float(np.corrcoef(events,other)[0,1])
                correlations.append(dict(dt=dt,di=di,pairs=count,r=r,flagged=abs(r)>limit))
        print('v',version,'offsets complete',flush=True)
        # One bounded histogram, freed before the next algorithm. 8 GiB RAM.
        hist=np.zeros(2**32,dtype=np.uint16)
        pair_count,repeated,maximum=collision_pairs(version,seed,stream,40000,n,hist)
        del hist
        total=40000*n
        reports.append(dict(algorithm=f'flybench.u32.v{version}',
            bernoulli=[dict(p=p,threshold=probability_threshold(p),trials=count,successes=int(np.count_nonzero(base<probability_threshold(p))),empirical_rate=float(np.mean(base<probability_threshold(p)))) for p in (.001,.01,.1)],
            offset_correlations=correlations,flag_threshold=limit,
            collisions=dict(ticks=40000,N=n,outputs=total,identical_output_pairs=pair_count,repeated_outputs=repeated,maximum_multiplicity=maximum,birthday_expected_pairs=total*(total-1)/(2*2**32),method='Exact uint16 histogram before bijective finalizer, checked for overflow')))
        write_json(out/'rng-sanity.json',dict(schema='flybench.v2c.rng-sanity',seed=seed,stream=stream,reports=reports,approximation_error=approximation_errors()))
        print('v',version,'round collisions complete',flush=True)
    write_json(Path('tests/vectors/detmath-v2.json'),build_vectors())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--n',type=int,default=43894);a=p.parse_args();run(a.out,a.n)
