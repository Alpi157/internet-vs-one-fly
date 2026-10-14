"""Resumable V2E confirmatory run. Invoke only after public preregistration."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import os
import subprocess
import time
import traceback
import numpy as np
from flybench.experiment_v2 import ROOT,FAMILIES,read,save,verify_freeze,load_graph,null_graph,calibration,h0,h1,h2,runner,conditions
from flybench.controls_v2 import direct_contact_fractions,fit_simple,simple_trial,timer_trial
from flybench.noise_v2 import measure_decoder_rates,decoder_noise_trial


def controls(graph,p,profile,selected,fit_path):
    r=runner(graph,p,profile['calibration_seeds'][0])
    seeds=[seed+(i+1)*101 for seed in profile['calibration_seeds'] for i in range(profile['standard_strikes_per_seed'])]
    fit=fit_simple(r.state.spec,p,direct_contact_fractions(graph),seeds,selected['standard_escape_fraction'])
    save(fit_path,fit)
    if not fit['passes']:raise RuntimeError('C-SIMPLE selected-point mismatch exceeds frozen bound')
    simple=[dict(condition=c,**simple_trial(r.state.spec,p,fit['fractions'],fit['gain'],profile['H1_seed_base']+ci*100+rep,(c['speed'],c['x'],c['y']))) for ci,c in enumerate(conditions()) for rep in range(25)]
    rates=measure_decoder_rates(r)
    noise=[decoder_noise_trial(r.groups,rates,seed,12000,r.profile) for seed in profile['H2_seeds']]
    timer=[dict(condition=c,**timer_trial(400+round(8/c['speed']/.5))) for c in conditions()]
    return dict(C_SIMPLE=dict(fit=fit,trials=simple),C_TIMER=timer,C_NOISE_DEC=dict(trials=noise),
        interventions={name:dict(H1=h1(graph,p,profile,name),H2=h2(graph,p,profile,name)) for name in ('output-clamp','LC4','LPLC2','turning-DN')})


def task(args):
    stage,circuit,family,index,out,protocol_hash=args
    verify_freeze()
    profile=read(ROOT/'profiles/calibration-v2.json')
    key=f'{circuit}-{family}-{index:03d}'
    path=out/stage/f'{key}.json.gz'
    if path.exists():
        old=read(path)
        if old['protocol_sha256']!=protocol_hash:raise RuntimeError('resume identity mismatch')
        return dict(key=key,stage=stage,resumed=True,wall_seconds=old['wall_seconds'])
    begin=time.perf_counter()
    if family=='REAL':graph=load_graph(circuit);diagnostics=None
    else:
        cache=ROOT/'data/compiled/v2e'/f'{key}.npy';diag=out/'topology'/f'{key}.json'
        if cache.exists() and diag.exists():
            graph=load_graph(circuit);graph['targets']=np.load(cache,allow_pickle=False);diagnostics=read(diag)
            if hashlib.sha256(graph['targets'].tobytes()).hexdigest()!=diagnostics['target_sha256']:raise RuntimeError('cached null target identity mismatch')
        else:
            graph,diagnostics=null_graph(circuit,family,index,profile)
            cache.parent.mkdir(parents=True,exist_ok=True);np.save(cache,graph['targets'],allow_pickle=False);save(diag,diagnostics)
    if stage=='calibration':data=calibration(graph,profile)
    elif stage=='H0':data=h0(graph,profile)
    elif stage=='fixed':
        real=read(out/'calibration'/f'{circuit}-REAL-000.json.gz')['data']['selected']
        data=dict(H1=h1(graph,real['parameters'],profile),H2=h2(graph,real['parameters'],profile)) if real else dict(status='REAL_UNCALIBRATABLE')
    else:
        calibrated=read(out/'calibration'/f'{key}.json.gz')['data']
        if not calibrated['selected']:data=dict(status='UNCALIBRATABLE_NOT_RUN')
        else:
            p=calibrated['selected']['parameters']
            if stage=='H1':data=h1(graph,p,profile)
            elif stage=='H2':data=h2(graph,p,profile)
            elif stage=='controls':data=controls(graph,p,profile,calibrated['selected'],out/'control-fits'/f'{key}.json')
            else:raise ValueError(stage)
    verify_freeze()
    record=dict(protocol_sha256=protocol_hash,circuit=circuit,family=family,index=index,stage=stage,data=data,wall_seconds=time.perf_counter()-begin)
    save(path,record)
    return dict(key=key,stage=stage,resumed=False,wall_seconds=record['wall_seconds'])


def batch(tasks,workers,log):
    begin=time.perf_counter();done=0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(task,t) for t in tasks]
        try:
            for future in as_completed(futures):
                row=future.result();done+=1
                elapsed=time.perf_counter()-begin
                row.update(done=done,total=len(tasks),elapsed_seconds=elapsed,eta_seconds=elapsed/done*(len(tasks)-done))
                line=json.dumps(row,sort_keys=True)
                print(line,flush=True)
                with log.open('a') as stream:stream.write(line+'\n')
        except BaseException:
            for future in futures:future.cancel()
            for process in pool._processes.values():process.terminate()
            raise


def run(out,workers,resume):
    protocol_hash=verify_freeze();profile=read(ROOT/'profiles/calibration-v2.json')
    receipt=read(ROOT/'evidence/V2E/preregistration-receipt.json')
    if receipt['status']!='PUSHED' or receipt['protocol_sha256']!=protocol_hash:raise RuntimeError('public preregistration receipt required')
    out.mkdir(parents=True,exist_ok=True)
    if (out/'STOP.json').exists():raise RuntimeError('defect stop exists; preserve outputs and request review')
    if not resume and any(out.glob('*/*.json.gz')):raise RuntimeError('existing results require --resume')
    start=time.perf_counter();log=out/'progress.jsonl'
    try:
        real=[('calibration',c,'REAL',0,out,protocol_hash) for c in ('T1a','T1b')]
        batch(real,min(workers,2),log)
        calibrations={c:read(out/'calibration'/f'{c}-REAL-000.json.gz') for c in ('T1a','T1b')}
        primary=next((c for c in ('T1a','T1b') if calibrations[c]['data']['selected']),None)
        save(out/'selection.json',dict(primary_circuit=primary,rule=profile['primary_circuit_rule'],selected={c:r['data']['selected'] for c,r in calibrations.items()}))
        if primary:
            subprocess.run([sys.executable,'experiments/v2e_game_export.py','--selection',str(out/'selection.json')],cwd=ROOT,check=True)
        projection=out/'projection.json'
        if not projection.exists():
            pre=read(ROOT/'evidence/V2E/control-feasibility.json')
            # Conservative serial projection measured before any confirmatory null.
            timings={c:sum(r['wall_seconds'] for r in pre['real_only_H0_timing'] if r['circuit']==c) for c in ('T1a','T1b')}
            totals={c:(3*profile['nulls']['count_per_circuit'][c]+1)*(timings[c]+calibrations[c]['wall_seconds']+profile['projection_H1_H2_seconds_per_graph'][c]) for c in ('T1a','T1b')}
            projected=sum(totals.values())/max(1,workers)
            circuits=[primary or 'T1a'] if projected>16*3600 else ['T1a','T1b']
            save(projection,dict(projected_total_seconds=projected,workers=workers,measured_H0_per_circuit=timings,measured_calibration_seconds={c:r['wall_seconds'] for c,r in calibrations.items()},per_circuit_serial_seconds=totals,circuits=circuits,secondary_deferred=len(circuits)==1,basis='Real-only timing; H1/H2 measured short pilot scaled by simulated duration; estimate excludes possible null saturation cost and is not a runtime guarantee. Decision before confirmatory null data.'))
        circuits=read(projection)['circuits']
        graph_ids=[(c,'REAL',0) for c in circuits]+[(c,f,i) for c in circuits for f in FAMILIES for i in range(profile['nulls']['count_per_circuit'][c])]
        batch([('H0',*g,out,protocol_hash) for g in graph_ids],workers,log)
        batch([('calibration',*g,out,protocol_hash) for g in graph_ids if g[1]!='REAL'],workers,log)
        eligible=[g for g in graph_ids if read(out/'calibration'/f'{g[0]}-{g[1]}-{g[2]:03d}.json.gz')['data']['selected']]
        if primary:
            for stage in ('H1','H2','fixed'):
                batch([(stage,*g,out,protocol_hash) for g in (graph_ids if stage=='fixed' else eligible) if stage!='fixed' or g[1]!='REAL'],workers,log)
            batch([('controls',c,'REAL',0,out,protocol_hash) for c in circuits if calibrations[c]['data']['selected']],min(workers,2),log)
        save(out/'COMPLETE.json',dict(status='COMPLETE',protocol_sha256=protocol_hash,primary=primary,circuits=circuits,invocation_wall_seconds=time.perf_counter()-start))
    except BaseException as error:
        save(out/'STOP.json',dict(status='STOPPED',error=repr(error),traceback=traceback.format_exc(),protocol_sha256=protocol_hash))
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('evidence/V2E/results'));parser.add_argument('--workers',type=int,default=12);parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();run(args.out.resolve(),args.workers,args.resume)
