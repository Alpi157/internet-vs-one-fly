"""Frozen V2E trial definitions, calibration and task identities.

This module executes science at fixed pose for calibration/H1 and free body for
H2. No game code is imported. Large raw records are gzip JSON, data only.
"""
from pathlib import Path
from dataclasses import replace
import gzip
import hashlib
import itertools
import json
import os
import time
import numpy as np
from flybench.encoding_v2 import HandStrikeV2
from flybench.kernel_v2 import interval_counts
from flybench.controls_v2 import lesion_graph

ROOT=Path(__file__).resolve().parents[2]
FAMILIES=('N-FULL','N-CONTEXT','N-SIGN')


def read(path):
    path=Path(path)
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_text())


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if path.suffix=='.gz': raw=gzip.compress(raw,mtime=0)
    temp=path.with_name(path.name+f'.{os.getpid()}.tmp');temp.write_bytes(raw);temp.replace(path)


def verify_freeze():
    manifest=read(ROOT/'profiles/freeze-v2.json')
    for name,digest in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('FROZEN FILE CHANGED: '+name)
    return hashlib.sha256((ROOT/'profiles/calibration-v2.json').read_bytes()).hexdigest()


def load_graph(circuit):
    directory=ROOT/'data/compiled/v2'/circuit.lower()
    manifest=read(directory/'manifest.json')
    for entry in manifest['arrays'].values():
        if hashlib.sha256((directory/entry['filename']).read_bytes()).hexdigest()!=entry['sha256']:
            raise RuntimeError('graph identity mismatch')
    return {k:np.load(directory/f'{k}.npy',allow_pickle=False) for k in ('ids','offsets','targets','weights','counts')}


def parameters(s,kappa,nu0,gain):
    row=next(r for r in read(ROOT/'profiles/noise-table-v2.json')['rows'] if r['kappa']==kappa and r['nu0_hz']==nu0)
    if not row['passes']:raise ValueError('failed noise row excluded')
    return dict(s=s,kappa=kappa,nu0_hz=nu0,gain=gain,threshold_int=row['threshold_int'],w_noise=row['w_noise'])


def runner(graph,p,seed,*,body=False,control=None):
    from experiments.v2d_dry_run import make_runner
    indices=[]
    if control in ('LC4','LPLC2','giant-fiber','turning-DN'):
        graph,indices=lesion_graph(graph,control)
    result=make_runner(graph,graph['targets'],p,seed,output_clamp=control=='output-clamp')
    result.body_enabled=body
    if len(indices):
        mask=result.state.noise.population_mask.copy();mask[indices]=False
        result.state.noise=replace(result.state.noise,population_mask=mask)
        result.visual={k:np.setdiff1d(v,indices) for k,v in result.visual.items()}
    return result


def calibration(graph,profile):
    from experiments.v2d_dry_run import trial,criteria
    rows=[];cache={};grid=profile['grid'];seeds=profile['calibration_seeds']
    for s,kappa,nu,gain in itertools.product(grid['runtime_synaptic_scale'],grid['kappa'],grid['nu0_hz'],grid['input_gain']):
        try:p=parameters(s,kappa,nu,gain)
        except ValueError:continue
        reps=[]
        for seed in seeds:
            key=(s,kappa,nu,seed)
            if key not in cache:cache[key]=trial(graph,graph['targets'],p,seed,'no-threat')
            no=cache[key]
            standard=[trial(graph,graph['targets'],p,seed+(i+1)*101,(.05,0.,0.)) for i in range(profile['standard_strikes_per_seed'])]
            reps.append(dict(seed=seed,no_threat=no,standard=standard,criteria=criteria(no,standard)))
        flags={key:all(r['criteria']['pass_flags'][key] for r in reps) for key in reps[0]['criteria']['pass_flags']}
        fraction=sum(t['escape_before_impact'] for r in reps for t in r['standard'])/(len(seeds)*profile['standard_strikes_per_seed'])
        flags['escape_standard']=.2<=fraction<=.9
        rows.append(dict(parameters=p,replicates=reps,aggregate_pass_flags=flags,passes_all=all(flags.values()),standard_escape_fraction=fraction,no_threat_mean_rate_hz=float(np.mean([r['no_threat']['mean_rate_hz'] for r in reps]))))
    passing=[r for r in rows if r['passes_all']]
    selected=min(passing,key=lambda r:r['no_threat_mean_rate_hz']) if passing else None
    return dict(status='CALIBRATED' if selected else 'UNCALIBRATABLE',passing_points=len(passing),attempted_points=len(rows),selected=selected,rows=rows)


def h0(graph,profile):
    hp=profile['hypotheses']['H0'];rows=[]
    for scale,seed in itertools.product(hp['s'],hp['seeds']):
        p=parameters(scale,hp['kappa'],hp['nu0_hz'],1)
        r=runner(graph,p,seed);start=time.perf_counter()
        counts=interval_counts(r.state,np.zeros(r.state.n),hp['seconds_per_seed']*2000)
        if not np.isfinite(r.state.voltage).all() or not np.isfinite(r.state.synaptic_current).all():raise RuntimeError('nonfinite H0 state')
        rows.append(dict(s=scale,seed=seed,seconds=hp['seconds_per_seed'],total_spikes=int(counts.sum()),neurons=r.state.n,rate_hz=float(counts.sum()/r.state.n/hp['seconds_per_seed']),final_digest=r.digest(),wall_seconds=time.perf_counter()-start))
    return dict(rows=rows)


def conditions():
    # Exact cardinal vectors avoid floating trigonometric pseudo-offsets at 180.
    for speed,offset,(az,(x,y)) in itertools.product((.025,.05,.1),(0.,1.5,3.),((0,(1,0)),(90,(0,1)),(180,(-1,0)),(270,(0,-1)))):
        if speed==.05 and offset==0:continue
        yield dict(speed=speed,offset=offset,azimuth=az,x=x*offset,y=y*offset)


def raw_trial(graph,p,seed,condition=None,*,control=None,seconds=120):
    r=runner(graph,p,seed,body=condition is None,control=control)
    impact=None if condition is None else 400+round(8/condition['speed']/.5)
    end=seconds*2000 if impact is None else impact+400
    records=[]
    for start in range(0,end,20):
        active=impact is not None and 400<=start<impact
        strike=HandStrikeV2(active,0 if condition is None else condition['x'],0 if condition is None else condition['y'],max(0,(start-400)*.5),0 if condition is None else condition['speed'])
        value=r.step(strike)
        if not np.isfinite(r.state.voltage).all() or not np.isfinite(r.state.synaptic_current).all():raise RuntimeError('nonfinite trial state')
        window_counts=[0,0];side_drive=[0.,0.]
        if active:
            # Counts at the exact impact tick are outside [strike start,impact).
            before=value['counts'].copy()
            if r.state.tick==impact:before-=r.state._spikes.astype(np.int64)
            window_counts=[int(before[i].sum()) for i in r.group_indices[:2]]
            side_drive=[sum(value['encoded'][f'{pop.lower()}_{side}_drive']*len(r.visual[f'{pop}_{side}']) for pop in ('LC4','LPLC2'))*min(20,impact-start) for side in ('left','right')]
        records.append(dict(tick=value['tick'],applied=value['applied'],command=value['command'],onset=value['onset'],group_counts=value['group_counts'],window_counts=window_counts,side_drive=side_drive))
    return dict(seed=seed,condition=condition,impact_tick=impact,strike_start_tick=None if impact is None else 400,records=records,final_digest=r.digest())


def h1(graph,p,profile,control=None):
    return dict(trials=[raw_trial(graph,p,profile['H1_seed_base']+ci*100+rep,c,control=control) for ci,c in enumerate(conditions()) for rep in range(25)])


def h2(graph,p,profile,control=None):
    return dict(trials=[raw_trial(graph,p,seed,control=control) for seed in profile['H2_seeds']])


def null_graph(circuit,family,index,profile):
    from flybench.nulls import directed_double_edge_swap,sign_stratified_swap,null_diagnostics
    from flybench.runner_v2 import visual_indices,port_groups
    g=load_graph(circuit);sources=np.repeat(np.arange(len(g['ids'])),np.diff(g['offsets']))
    seed=202710140000+('T1a','T1b').index(circuit)*100000+FAMILIES.index(family)*10000+index
    vis=set(np.concatenate(list(visual_indices(g['ids']).values())).tolist())
    all_outputs={int(e['body_id']) for group in read(ROOT/'profiles/ports-v2.json')['groups'].values() for e in group}
    outs=set(np.flatnonzero(np.isin(g['ids'],list(all_outputs))).tolist())
    if family=='N-SIGN':targets,strata=sign_stratified_swap(sources,g['targets'],g['weights'],seed=seed)
    else:
        frozen=(sources==g['targets'])
        if family=='N-CONTEXT':frozen |= np.isin(sources,list(vis))&np.isin(g['targets'],list(outs))
        swap=directed_double_edge_swap(sources,g['targets'],swap_count=len(sources),seed=seed,frozen_edges=frozen,maximum_attempt_multiple=100)
        targets=swap.targets;strata=dict(completed_swaps=swap.completed_swaps,proposal_attempts=swap.proposal_attempts)
    targets=targets.astype(np.int32)
    d=null_diagnostics(sources,g['targets'],targets,g['counts'],g['weights'],len(g['ids']),vis,outs,{i:int(g['ids'][i]) for i in outs})
    if not d['self_loops_identical'] or not all(d['degree_preservation'].values()):raise RuntimeError('null invariant failed')
    if family=='N-SIGN' and not d['in_degree_by_effective_sign_exact']:raise RuntimeError('sign degree invariant failed')
    g['targets']=targets
    return g,dict(seed=seed,strata=strata,target_sha256=hashlib.sha256(targets.tobytes()).hexdigest(),**d)
