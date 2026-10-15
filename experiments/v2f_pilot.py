"""Real-graph pilots and topology diagnostics only, before v2.1 freeze."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import resource
import time
import numpy as np
from flybench.experiment_v2 import read, save, ROOT, verify_freeze
from flybench.experiment_v21 import load_graph, rate_trial, early_stop, IDENTITIES
from flybench.nulls_v21 import strength_swap, diagnostics
from flybench.analysis_v2 import h0_metrics

p=argparse.ArgumentParser();p.add_argument('--circuit', choices=list(IDENTITIES));p.add_argument('--scale',type=float,default=.039);p.add_argument('--repeat',type=int,default=0);p.add_argument('--diagnostics',action='store_true');p.add_argument('--early-proof',action='store_true');a=p.parse_args()
out=ROOT/'evidence/V2F/pilots';out.mkdir(parents=True,exist_ok=True)
verify_freeze()
if a.early_proof:
    proofs=[]
    for path in sorted((ROOT/'evidence/V2E/results/H0').glob('T1a-N-SIGN-*.json.gz'))[:5]:
        raw=read(path)['data']; prefix=[]
        for scale in sorted({r['s'] for r in raw['rows']}):
            prefix.extend(r for r in raw['rows'] if r['s']==scale)
            if early_stop(prefix,scale):break
        full=h0_metrics(raw);early=h0_metrics(dict(rows=prefix));keys=('H0a','H0b','censor')
        assert all(full[k]==early[k] for k in keys)
        proofs.append(dict(source=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),full={k:full[k] for k in keys},early={k:early[k] for k in keys},evaluated_couplings=len(prefix)//2))
    assert len(proofs)==5
    save(out/'early-stop-proof.json',dict(status='PASS',method='Replay stopping predicate over all raw V2E sweep rows; no new null simulation',rows=proofs))
else:
    start=time.perf_counter();g=load_graph(a.circuit)
    if a.diagnostics:
        sources=np.repeat(np.arange(len(g['ids'])),np.diff(g['offsets']))
        seed=202810150000+list(IDENTITIES).index(a.circuit)*100
        targets,strata=strength_swap(sources,g['targets'],g['counts'],g['weights'],seed=seed)
        result=dict(seed=seed,strata=strata,**diagnostics(sources,g['targets'],targets,g['counts'],g['weights'],len(g['ids'])))
        name=f'{a.circuit}-strength-diagnostics'
    else:
        result=rate_trial(g,a.scale,2027101401,5 if a.circuit=='FULL' else 10)
        name=f'{a.circuit}-{a.scale}-{a.repeat}'
    result.update(circuit=a.circuit,graph_digest=IDENTITIES[a.circuit][1],task_wall_seconds=time.perf_counter()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(out/f'{name}.json',result);print(result if not a.diagnostics else {k:v for k,v in result.items() if k!='strata'},flush=True)
