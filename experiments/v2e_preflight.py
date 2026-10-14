"""V2E pre-freeze probes. No H0 null observations are permitted here."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import hashlib
import json
import math
import time
import numpy as np
from experiments.v2d_dry_run import load_graph, make_runner, trial
from flybench.controls_v2 import direct_contact_fractions, fit_simple, simple_trial, lesion_graph, timer_trial
from flybench.encoding_v2 import HandStrikeV2
from flybench.graph import write_json
from flybench.kernel_v2 import interval_counts
from flybench.noise_v2 import measure_decoder_rates, decoder_noise_trial
from flybench.nulls import sign_stratified_swap, null_diagnostics
from flybench.runner_v2 import visual_indices, port_groups

ROOT=Path(__file__).resolve().parents[1]


def prepare_sign_nulls(out):
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for gi,name in enumerate(('T1a','T1b')):
        graph=load_graph(name)
        counts=np.load(ROOT/'data/compiled/v2'/name.lower()/'counts.npy',allow_pickle=False)
        sources=np.repeat(np.arange(len(graph['ids'])),np.diff(graph['offsets']))
        targets,strata=sign_stratified_swap(sources,graph['targets'],graph['weights'],seed=202610149000+gi*100)
        vis=set(np.concatenate(list(visual_indices(graph['ids']).values())).tolist())
        outs=set(np.flatnonzero(np.isin(graph['ids'],sum(port_groups(graph['ids']),()))).tolist())
        d=null_diagnostics(sources,graph['targets'],targets,counts,graph['weights'],len(graph['ids']),vis,outs,{i:int(graph['ids'][i]) for i in outs})
        assert d['in_degree_by_effective_sign_exact'] and d['self_loops_identical'] and all(d['degree_preservation'].values())
        targets=targets.astype(np.int32)
        np.save(out/f'{name}-N-SIGN.npy',targets,allow_pickle=False)
        rows.append(dict(circuit=name,seed=202610149000+gi*100,strata=strata,target_sha256=hashlib.sha256(targets.tobytes()).hexdigest(),**d))
    write_json(out/'diagnostics.json',dict(status='PASS',purpose='excluded pipeline nulls; never H0 tested',rows=rows))


def worker_check(task):
    name,kind,p=task
    g=load_graph(name)
    targets=g['targets'] if kind=='REAL' else np.load(ROOT/'evidence/V2E/dry-run-4/nulls'/f'{name}-N-SIGN.npy')
    return trial(g,targets,p,2027101499,(.05,0.,0.),trace=True)['neural_interval_hashes']


def run(out,dry):
    started=time.perf_counter()
    data=json.loads(dry.read_text())
    rows=[]; real_h0=[]; tasks=[]
    for name in ('T1a','T1b'):
        candidates=[r for r in data['rows'] if r['circuit']==name and r['family']=='REAL']
        # Provisional fallback only: maximize satisfied criteria, lowest quiet rate, grid order.
        row=min(candidates,key=lambda r:(-sum(r['aggregate_pass_flags'].values()),sum(t['no_threat']['mean_rate_hz'] for t in r['replicates'])))
        p=row['parameters'];g=load_graph(name)
        g['counts']=np.load(ROOT/'data/compiled/v2'/name.lower()/'counts.npy')
        runner=make_runner(g,g['targets'],p,2026092802)
        seeds=[t['seed'] for rep in row['replicates'] for t in rep['standard']]
        simple=fit_simple(runner.state.spec,p,direct_contact_fractions(g),seeds,row['standard_escape_fraction'])
        held=[simple_trial(runner.state.spec,p,simple['fractions'],simple['gain'],seed,c) for seed in seeds[:2] for c in ((.025,0.,0.),(.1,0.,0.),(.05,0.,1.5),(.05,0.,-3.))]
        rates=measure_decoder_rates(runner)
        dec=decoder_noise_trial(runner.groups,rates,2026092802,2000,runner.profile)
        counts=[sum(r['group_counts'][i] for r in dec['records']) for i in range(6)]
        measured=[n/max(1,len(group))/20 for n,group in zip(counts,runner.groups)]
        bounds=[max(.05*rate,3*math.sqrt(rate/(20*max(1,len(group))))) for rate,group in zip(rates,runner.groups)]
        lesions=[]
        for lesion in ('LC4','LPLC2','giant-fiber','turning-DN'):
            altered,indices=lesion_graph(g,lesion)
            r=make_runner(altered,altered['targets'],p,2026092802)
            mask=r.state.noise.population_mask.copy();mask[indices]=False
            r.state.noise=replace(r.state.noise,population_mask=mask)
            r.visual={k:np.setdiff1d(v,indices) for k,v in r.visual.items()}
            total=np.zeros(r.state.n,dtype=int)
            for ci in range(56):
                total+=r.step(HandStrikeV2(20<=ci<36,0,0,max(0,(ci-20)*10),.05))['counts']
            lesions.append(dict(name=lesion,neurons=len(indices),spikes_in_lesioned_neurons=int(total[indices].sum()),passes=bool(not total[indices].any())))
        normal=trial(g,g['targets'],p,2026092802,(.05,0.,0.),trace=True)
        clamp=trial(g,g['targets'],p,2026092802,(.05,0.,0.),output_clamp=True,trace=True)
        rows.append(dict(circuit=name,parameters=p,criteria=row['aggregate_pass_flags'],C_SIMPLE=simple,held_out_pipeline_only=held,
            C_TIMER=timer_trial(720),C_NOISE_DEC=dict(expected_rates=rates,observed_rates=measured,bounds=bounds,
            absolute_mismatch=[abs(a-b) for a,b in zip(rates,measured)],passes=all(abs(a-b)<=bnd for a,b,bnd in zip(rates,measured,bounds))),lesions=lesions,
            output_clamp=dict(passes=clamp['escape_counts']==0 and normal['neural_interval_hashes']==clamp['neural_interval_hashes'])))
        tasks.append((name,'REAL',p))
        noise=json.loads((ROOT/'profiles/noise-table-v2.json').read_text())
        nr=next(r for r in noise['rows'] if r['kappa']==.05 and r['nu0_hz']==2)
        # Real graphs only, full reviewer H0 sweep for timing, not inference.
        for scale in (.005,.0075,.01,.015,.02,.03,.039,.05,.06,.08,.1):
            for seed in (2027101401,2027101402):
                r=make_runner(g,g['targets'],dict(s=scale,gain=1,**nr),seed)
                begin=time.perf_counter()
                counts=interval_counts(r.state,np.zeros(r.state.n),20000)
                assert np.isfinite(r.state.voltage).all() and np.isfinite(r.state.synaptic_current).all()
                real_h0.append(dict(circuit=name,s=scale,seed=seed,seconds=10,rate_hz=float(counts.sum()/r.state.n/10),wall_seconds=time.perf_counter()-begin))
    tasks.append(('T1a','N-SIGN',rows[0]['parameters']))
    one=[worker_check(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=3) as pool:
        many=list(pool.map(worker_check,tasks))
    repeat=[worker_check(t) for t in tasks]
    report=dict(status='PIPELINE_ONLY',control_rows=rows,real_only_H0_timing=real_h0,
        deterministic_workers=dict(graphs=[t[:2] for t in tasks],one_vs_three=one==many,repeat=one==repeat,digests=one),
        wall_seconds=time.perf_counter()-started)
    write_json(out,report)
    print(json.dumps(dict(wall_seconds=report['wall_seconds'],simple=[{k:r['C_SIMPLE'][k] for k in ('target','achieved','absolute_mismatch','passes')} for r in rows])))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('evidence/V2E/control-feasibility.json'));parser.add_argument('--dry',type=Path,default=Path('evidence/V2E/dry-run-4/dry-run.json'))
    args=parser.parse_args();run(args.out,args.dry)
