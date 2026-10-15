"""Resumable v2.1 tasks. Requires a verified public freeze receipt."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import os
import resource
import time
import traceback
import numpy as np
from flybench.experiment_v2 import ROOT, read, save
from flybench.experiment_v21 import verify_freeze, load_graph, null_graph, sweep, IDENTITIES
from flybench.mechanism_v21 import mechanism


def tasks(profile, block):
    if block.startswith('H0-'):
        b=next(v for v in profile['confirmatory'] if v['test']==block)
        return [(block,b['circuit'],'REAL',0)]+[(block,b['circuit'],f,i) for f in b['families'] for i in range(b['nulls'])]
    if block=='E1':
        circuits=['T1a']+(['T2'] if profile['resource_plan']['E1_T2'] else [])
        return [(block,c,'REAL',0) for c in circuits]+[(block,c,f,i) for c in circuits for f in (['N-FULL','N-CONTEXT','N-SIGN','N-STRENGTH'] if c=='T1a' else ['N-FULL','N-SIGN','N-STRENGTH']) for i in range(499 if c=='T1a' else 20)]
    return [(block,'T1a','REAL',0)]+[(block,'T1a','N-SIGN',i) for i in range(99)]


def task(args):
    (block,circuit,family,index),out,identity=args
    verify_freeze();p=read(ROOT/'profiles/protocol-v2.1.json')
    key=f'{circuit}-{family}-{index:03d}';path=out/block/f'{key}.json.gz'
    if path.exists():
        old=read(path)
        if old['protocol_sha256']!=identity or old['task']!=[block,circuit,family,index]:raise RuntimeError('resume identity mismatch')
        return dict(task=old['task'],resumed=True,wall_seconds=old['wall_seconds'])
    start=time.perf_counter();diagnostic=None
    if block=='E1' and circuit=='T1a' and family in ('N-FULL','N-CONTEXT','N-SIGN'):
        from flybench.experiment_v2 import null_graph as old_null
        graph,diagnostic=old_null(circuit,family,index,read(ROOT/'profiles/calibration-v2.json'))
        expected=read(ROOT/'evidence/V2E/results/topology'/f'{key}.json')
        if expected['target_sha256']!=diagnostic['target_sha256']:raise RuntimeError('V2E regeneration mismatch')
    elif family=='REAL':
        graph=load_graph(circuit)
        if block=='E2a':
            codes=np.load(ROOT/IDENTITIES[circuit][0]/'consensus-nt-codes.npy')
            sources=np.repeat(np.arange(len(graph['ids'])),np.diff(graph['offsets']))
            mask=codes[sources]==3;graph['weights'][mask]=graph['counts'][mask].astype(np.float32)
    else:
        bi={'H0-STR':0,'H0-FULL':1,'H0-T2':2,'E2a':3,'E3-low':4,'E3-high':5}.get(block,0 if circuit=='T1a' else 2)
        graph,diagnostic=null_graph(circuit,family,index,bi,variant='glutamate' if block=='E2a' else None)
    if block=='E1':data=mechanism(graph)
    else:
        hp=dict(p['H0']);hp['seconds_per_seed']=5 if circuit=='FULL' else 10
        if circuit=='FULL' and family!='REAL':hp['s']=[.039]
        data=sweep(graph,hp,early=family!='REAL' and circuit!='FULL',nu0=.5 if block=='E3-low' else 5 if block=='E3-high' else 2)
    verify_freeze()
    record=dict(task=[block,circuit,family,index],protocol_sha256=identity,data=data,diagnostics=diagnostic,
        classification='EXPLORATORY' if block.startswith('E') else 'CONFIRMATORY',
        wall_seconds=time.perf_counter()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(path,record)
    return {k:record[k] for k in ('task','wall_seconds','peak_rss_kib')}


def run(out,resume):
    identity=verify_freeze();profile=read(ROOT/'profiles/protocol-v2.1.json')
    receipt=read(ROOT/'docs/preregistration-receipt-v2.1.json')
    if receipt['status']!='PUSHED' or receipt['protocol_sha256']!=identity:raise RuntimeError('public preregistration receipt required')
    out.mkdir(parents=True,exist_ok=True)
    if (out/'STOP.json').exists():raise RuntimeError('defect stop exists')
    if not resume and any(out.glob('*/*.json.gz')):raise RuntimeError('existing records require --resume')
    started=time.perf_counter();plan=profile['resource_plan']
    blocks=['H0-STR','H0-FULL','H0-T2','E1']+(['E2a','E3-low','E3-high'] if plan['E2_E3'] else [])
    try:
        for block in blocks:
            jobs=tasks(profile,block)
            workers=plan['full_workers'] if block=='H0-FULL' else plan['T2_workers'] if block=='H0-T2' else plan['small_workers']
            if block=='E1':workers=plan['mechanism_workers']
            begin=time.perf_counter()
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures=[pool.submit(task,(t,out,identity)) for t in jobs]
                try:
                    for done,future in enumerate(as_completed(futures),1):
                        row=future.result();elapsed=time.perf_counter()-begin
                        row.update(block=block,done=done,total=len(jobs),elapsed_seconds=elapsed,eta_seconds=elapsed/done*(len(jobs)-done))
                        with (out/'progress.jsonl').open('a') as stream:
                            import json
                            line=json.dumps(row,sort_keys=True);stream.write(line+'\n');print(line,flush=True)
                except BaseException:
                    for f in futures:f.cancel()
                    for process in pool._processes.values():process.terminate()
                    raise
        save(out/'COMPLETE.json',dict(status='COMPLETE',protocol_sha256=identity,blocks=blocks,invocation_wall_seconds=time.perf_counter()-started,hardware_threads=os.cpu_count()))
    except BaseException as e:
        save(out/'STOP.json',dict(status='STOPPED',error=repr(e),traceback=traceback.format_exc(),protocol_sha256=identity))
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('evidence/V2F/results'));p.add_argument('--resume',action='store_true');a=p.parse_args();run(a.out.resolve(),a.resume)
