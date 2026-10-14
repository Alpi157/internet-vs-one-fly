"""V2E descriptive controls. Independent stream 37 for stochastic C-SIMPLE."""
from dataclasses import replace
import math
import numpy as np
from flybench.encoding_v2 import HandStrikeV2, encode_hand_v2
from flybench.kernel import KernelGraph
from flybench.kernel_v2 import KernelStateV2, interval_counts
from flybench.reference_v2 import NoiseSpec
from flybench.runner_v2 import visual_indices, port_groups

SIMPLE_STREAM = 37


def direct_contact_fractions(graph):
    """Fraction of all LC4 plus LPLC2 direct DNp01 contacts, pooled sides."""
    sources = np.repeat(np.arange(len(graph['ids'])), np.diff(graph['offsets']))
    visual = visual_indices(graph['ids'])
    outputs = set(port_groups(graph['ids'])[0] + port_groups(graph['ids'])[1])
    mask = np.isin(graph['ids'][graph['targets']], list(outputs))
    counts = {}
    for pop in ('LC4', 'LPLC2'):
        indices = np.concatenate([visual[pop+'_left'], visual[pop+'_right']])
        counts[pop] = int(graph['counts'][mask & np.isin(sources, indices)].sum())
    total = sum(counts.values())
    if not total:
        raise ValueError('no measured direct LC4/LPLC2 contacts onto DNp01')
    return dict(contacts=counts, denominator=total, a=counts['LC4']/total, b=counts['LPLC2']/total)


def simple_trial(spec, noise_row, fractions, gain, seed, condition=(.05, 0., 0.), *, reference=False):
    """Same 10 ms held encoder, LIF order, reset and onset as the graph runner."""
    if not math.isfinite(gain) or gain < 0:
        raise ValueError('gain must be finite and nonnegative')
    noise = NoiseSpec(seed, SIMPLE_STREAM, noise_row['threshold_int'], noise_row['w_noise'], np.ones(1,dtype=bool))
    graph = KernelGraph(np.array([0,0],dtype=np.int64),np.array([],dtype=np.int32),np.array([],dtype=np.float64))
    state = KernelStateV2(spec, graph, noise)
    if reference:
        from flybench.reference import ReferenceGraph
        from flybench.reference_v2 import ReferenceStateV2
        state = ReferenceStateV2(spec, ReferenceGraph(graph.offsets,graph.targets,graph.weights), noise)
    speed, x, y = condition
    impact = 400 + round(8/speed/.5)
    prior = False
    onsets, spikes = [], []
    for start in range(0, impact+400, 20):
        active = 400 <= start < impact
        encoded = encode_hand_v2(HandStrikeV2(active,x,y,max(0.,(start-400)*.5),speed),fly_x=0,fly_y=0,heading_x=1,heading_y=0,hand_radius=.75,initial_height=8,dt_ms=.5,input_gain=1)
        feature = fractions['a']*encoded.expansion_feature + fractions['b']*(encoded.size_feature if encoded.angular_expansion_per_ms>0 else 0)
        count = 0
        for tick in range(start,start+20):
            drive = gain*feature if tick<impact else 0.
            result = state.step(drive)
            if result.spikes[0]:
                count += 1
                spikes.append(state.tick)
        escape = count>0
        if escape and not prior:
            onsets.append(state.tick)
        prior = escape
    return dict(seed=seed,stream=SIMPLE_STREAM,gain=gain,impact_tick=impact,escape_onset_ticks=onsets,spike_ticks=spikes,
        escape_before_impact=any(400<t<impact for t in onsets))


def fit_simple(spec, noise_row, fractions, seeds, target):
    """Declared bounded search: endpoints 0/64 then 32 bisections, closest result.

    Finite LIF sample response is not assumed globally monotone. Retain every
    evaluation and report mismatch; never change noise or seeds to improve fit.
    """
    evaluated = {}
    def evaluate(g):
        rows = [simple_trial(spec,noise_row,fractions,g,seed) for seed in seeds]
        evaluated[g] = rows
        return sum(r['escape_before_impact'] for r in rows)/len(rows)
    low, high = 0., 64.
    evaluate(low); evaluate(high)
    for _ in range(32):
        mid = (low+high)/2
        if evaluate(mid)<target: low=mid
        else: high=mid
    selected = min(evaluated,key=lambda g:(abs(sum(r['escape_before_impact'] for r in evaluated[g])/len(seeds)-target),g))
    achieved = sum(r['escape_before_impact'] for r in evaluated[selected])/len(seeds)
    return dict(gain=selected,target=target,achieved=achieved,absolute_mismatch=abs(achieved-target),
        bound=1/len(seeds),passes=abs(achieved-target)<=1/len(seeds),fractions=fractions,
        evaluations=[dict(gain=g,fraction=sum(r['escape_before_impact'] for r in rows)/len(seeds),trials=rows) for g,rows in evaluated.items()])


def lesion_graph(graph, name):
    """Silence the named neurons by removing their input, output and noise.

    Returned arrays are copies. Caller also masks direct drive for visual lesions.
    """
    visual = visual_indices(graph['ids']); groups = port_groups(graph['ids'])
    if name in ('LC4','LPLC2'):
        indices = np.concatenate([visual[name+'_left'],visual[name+'_right']])
    else:
        bodies = sum(groups[:2] if name=='giant-fiber' else groups[3:5], ())
        indices = np.flatnonzero(np.isin(graph['ids'],bodies))
    sources = np.repeat(np.arange(len(graph['ids'])),np.diff(graph['offsets']))
    result = dict(graph)
    result['weights'] = graph['weights'].copy()
    result['weights'][np.isin(sources,indices)|np.isin(graph['targets'],indices)] = 0
    return result, indices


def timer_trial(impact_tick, lead_ms=30):
    return dict(impact_tick=impact_tick,onset_tick=impact_tick-round(lead_ms*2),lead_ms=lead_ms,
                target='fixed 30 ms before impact; no escape-fraction matching claimed')
