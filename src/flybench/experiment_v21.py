"""New v2.1 execution helpers, leaving every prereg-v2 file untouched."""
import hashlib
import time
import numpy as np
from flybench.experiment_v2 import ROOT, read, runner, parameters
from flybench.kernel_v2 import interval_counts
from flybench.graph import semantic_graph_digest

IDENTITIES = {
    'T1a': ('data/compiled/v2/t1a', 'c157802c70bfeb71548b71159ff297525136d3d58f31d91e91937fddc738e3d2', 2641, 275162),
    'T2': ('data/compiled/v2/t2', '41aeec554aa4296bc0e8bea7803958a40d8f9c7e69feff80aceed61f0019b0df', 43894, 7321740),
    'FULL': ('data/compiled/full', '429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0', 166700, 25582938),
}


def load_graph(circuit):
    path, expected, n, e = IDENTITIES[circuit]
    directory = ROOT/path
    manifest = read(directory/'manifest.json')
    for entry in manifest['arrays'].values():
        with (directory/entry['filename']).open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != entry['sha256']:
            raise RuntimeError('graph array identity mismatch: '+entry['filename'])
    digest = semantic_graph_digest(directory, manifest['selection_profile']['semantic_sha256'], manifest['compile_transform_profile']['sha256'])
    if digest != expected or manifest['semantic_digest']['value'] != expected:
        raise RuntimeError('graph semantic identity mismatch')
    graph = {k: np.load(directory/f'{k}.npy', allow_pickle=False) for k in ('ids','offsets','targets','counts','weights')}
    if len(graph['ids']) != n or len(graph['targets']) != e:
        raise RuntimeError('graph cardinality mismatch')
    return graph


def rate_trial(graph, scale, seed, seconds, nu0=2):
    start = time.perf_counter()
    r = runner(graph, parameters(scale, .05, nu0, 1), seed)
    counts = interval_counts(r.state, np.zeros(r.state.n), int(seconds*2000))
    if not np.isfinite(r.state.voltage).all() or not np.isfinite(r.state.synaptic_current).all():
        raise RuntimeError('nonfinite H0 state')
    return dict(s=scale, seed=seed, seconds=seconds, total_spikes=int(counts.sum()),
        neurons=r.state.n, rate_hz=float(counts.sum()/r.state.n/seconds),
        final_digest=r.digest(), wall_seconds=time.perf_counter()-start)


def early_stop(rows, scale):
    current = [r for r in rows if r['s'] == scale]
    return scale >= .039 and any(r['s'] == .039 for r in rows) and np.mean(
        [r['total_spikes']/r['neurons']/r['seconds'] for r in current]) >= 50


def sweep(graph, hp, *, early=False, nu0=2):
    rows = []
    for scale in hp['s']:
        for seed in hp['seeds']:
            rows.append(rate_trial(graph, scale, seed, hp['seconds_per_seed'], nu0))
        if early and early_stop(rows, scale):
            break
    return dict(rows=rows, stopped_early=len(rows)<len(hp['s'])*len(hp['seeds']))


def verify_freeze():
    from flybench.experiment_v2 import verify_freeze as verify_v2
    verify_v2()
    manifest=read(ROOT/'profiles/freeze-v2.1.json')
    for name,digest in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('FROZEN v2.1 FILE CHANGED: '+name)
    return hashlib.sha256((ROOT/'profiles/protocol-v2.1.json').read_bytes()).hexdigest()


def null_graph(circuit, family, index, block_index, *, variant=None):
    from flybench.nulls_v21 import strength_swap, diagnostics
    graph=load_graph(circuit)
    sources=np.repeat(np.arange(len(graph['ids'])),np.diff(graph['offsets']))
    if variant=='glutamate':
        codes=np.load(ROOT/IDENTITIES[circuit][0]/'consensus-nt-codes.npy')
        graph['weights']=graph['weights'].copy()
        mask=codes[sources]==3
        graph['weights'][mask]=graph['counts'][mask].astype(np.float32)
    family_index={'N-FULL':0,'N-SIGN':1,'N-STRENGTH':2}[family]
    seed=202910150000+block_index*100000+family_index*10000+index*32
    targets,strata=strength_swap(sources,graph['targets'],graph['counts'],graph['weights'],seed=seed,family=family)
    report=dict(seed=seed,strata=strata,target_sha256=hashlib.sha256(targets.tobytes()).hexdigest(),
        **diagnostics(sources,graph['targets'],targets,graph['counts'],graph['weights'],len(graph['ids'])))
    graph['targets']=targets
    return graph,report
