"""Regenerate one stored null for a future product demo; never simulate."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gzip
import hashlib
import json
import numpy as np
from flybench.analysis_v2 import h0_metrics
from flybench.experiment_v21 import verify_freeze,null_graph

ROOT=Path(__file__).resolve().parents[1]
# Fixed before reading any candidate. No simulation or additional selection.
SELECTION_RULE='the T1a H0-STR N-STRENGTH null whose H0b equals the family median of the 499 values; ties go to the lowest index.'


def run():
    identity=verify_freeze()
    paths=sorted((ROOT/'evidence/V2F/results/H0-STR').glob('T1a-N-STRENGTH-*.json.gz'))
    assert len(paths)==499, 'Expected exactly 499 recorded candidates'
    candidates=[]
    for path in paths:
        record=json.loads(gzip.decompress(path.read_bytes()))
        assert record['protocol_sha256']==identity
        candidates.append((h0_metrics(record['data'])['H0b'],record['task'][3],path,record))
    median=float(np.median([v[0] for v in candidates]))
    rate,index,path,record=min((v for v in candidates if v[0]==median),key=lambda v:v[1])
    graph,diagnostic=null_graph('T1a','N-STRENGTH',index,0)
    assert diagnostic['seed']==record['diagnostics']['seed']
    assert diagnostic['target_sha256']==record['diagnostics']['target_sha256']
    targets=graph['targets'].astype('<i4')
    assert hashlib.sha256(targets.tobytes()).hexdigest()==record['diagnostics']['target_sha256']
    packed=gzip.compress(json.dumps(targets.tolist(),separators=(',',':')).encode(),mtime=0)
    out=ROOT/'apps/play/public/data/coupling';(out/'strength-targets.json.gz').write_bytes(packed)
    metadata=dict(schema='flybench.coupling-strength-demo.v1',selection_rule=SELECTION_RULE,
        family='N-STRENGTH',circuit='T1a',index=index,seed=diagnostic['seed'],H0b=rate,family_median_H0b=median,
        source_record=str(path.relative_to(ROOT)),source_record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        protocol_sha256=identity,target_sha256=diagnostic['target_sha256'],target_hash_check='PASS',
        asset=dict(file='strength-targets.json.gz',bytes=len(packed),sha256=hashlib.sha256(packed).hexdigest()),
        scope='Data-only export of an existing null. UI is unchanged; no new scientific trial.')
    (out/'strength-demo.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+'\n')
    hashes=json.loads((out/'HASHES.json').read_text())
    for name in ('strength-targets.json.gz','strength-demo.json'):
        path=out/name;hashes[name]=dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (out/'HASHES.json').write_text(json.dumps(hashes,indent=2,sort_keys=True)+'\n')
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':run()
