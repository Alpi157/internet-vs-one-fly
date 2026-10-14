"""V2C autapse-preserving null diagnostics; graph arrays stay under data/."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import json
import numpy as np
from flybench.nulls import directed_double_edge_swap, null_diagnostics
from flybench.graph import write_json
from experiments.v2b_dry_run import _indices, _load_graph, _sources

ROOT = Path(__file__).resolve().parents[1]


def generate(out: Path):
    results = []
    for gi, name in enumerate(('T1a', 'T1b')):
        graph = _load_graph(name)
        graph['counts'] = np.load(graph['directory']/'counts.npy',allow_pickle=False)
        sources = _sources(graph['offsets'])
        _, visual, output = _indices(graph['ids'])
        by_id = {int(v): i for i,v in enumerate(graph['ids'])}
        vis = {by_id[v] for v in visual if v in by_id}
        outs = {by_id[v] for v in output if v in by_id}
        direct = np.isin(sources,list(vis)) & np.isin(graph['targets'],list(outs))
        loops = sources == graph['targets']
        for fi, family in enumerate(('N-FULL','N-CONTEXT')):
            frozen = loops | (direct if fi else False)
            for ni in range(20):
                seed = 202610140000 + gi*100000 + fi*10000 + ni
                swapped = directed_double_edge_swap(sources,graph['targets'],swap_count=sources.size,seed=seed,frozen_edges=frozen,maximum_attempt_multiple=30)
                d = null_diagnostics(sources,graph['targets'],swapped.targets,graph['counts'],graph['weights'],graph['ids'].size,vis,outs,{i:int(graph['ids'][i]) for i in outs})
                assert d['self_loops_identical'] and d['no_new_self_loops']
                assert all(d['degree_preservation'].values())
                assert np.array_equal(swapped.targets[frozen], graph['targets'][frozen])
                digest = hashlib.sha256(np.asarray(swapped.targets,dtype='<i4').tobytes()).hexdigest()
                results.append(dict(circuit=name,family=family,index=ni,seed=seed,requested_swaps=int(sources.size),completed_swaps=swapped.completed_swaps,proposal_attempts=swapped.proposal_attempts,frozen_edges=int(frozen.sum()),self_loops=int(loops.sum()),target_sha256=digest,**d))
                # C7 uses these exact first two nulls per family. Keep all arrays ignored.
                path=ROOT/'data/compiled/v2'/name.lower()/f'{family}-{ni}.npy'
                np.save(path,np.asarray(swapped.targets,dtype='<i4'),allow_pickle=False)
            print(name,family,'20 diagnostics complete',flush=True)
    report=dict(schema='flybench.v2c.null-diagnostics',status='PASS',nulls_per_family_graph=20,swap_multiple_of_E=1,proposal_rng='PCG64 batched independent uniform edge pairs; reject equal pairs',self_loop_rule='frozen in place',graphs=results)
    write_json(out/'null-diagnostics.json',report)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);generate(p.parse_args().out)
