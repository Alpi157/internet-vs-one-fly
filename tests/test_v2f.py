import numpy as np
import pytest
from flybench.nulls_v21 import strength_swap, BIN_UPPER
from flybench.experiment_v21 import early_stop
from flybench.analysis_v2 import h0_metrics


def test_strength_invariants_and_repeat():
    rng = np.random.default_rng(12)
    n = 80
    sources = np.repeat(np.arange(n), 12)
    targets = np.concatenate([rng.choice(n, 12, replace=False) for _ in range(n)])
    counts = rng.choice([1, 2, 3, 4, 5, 8, 16, 32, 64, 128, 129], len(sources))
    weights = counts * np.repeat(np.tile([-1, 0, 1, 1], 20), 12)
    before = [a.copy() for a in (sources, targets, counts, weights)]
    result, strata = strength_swap(sources, targets, counts, weights, seed=18)
    again, diag = strength_swap(sources, targets, counts, weights, seed=18)
    assert np.array_equal(result, again) and diag == strata
    assert len(set(zip(sources, result))) == len(sources)
    assert np.array_equal(sources == targets, sources == result)
    bins = np.searchsorted(BIN_UPPER, counts)
    for sign in (-1, 0, 1):
        for b in range(9):
            mask = (np.sign(weights) == sign) & (bins == b)
            assert np.array_equal(np.bincount(targets[mask], minlength=n), np.bincount(result[mask], minlength=n))
    for a, b in zip(before, (sources, targets, counts, weights)):
        assert np.array_equal(a, b)
    assert np.mean(result != targets) > .5


def test_strength_frozen_and_immobile_strata():
    s = np.array([0, 0, 1, 1]); t = np.array([0, 1, 0, 1]); c = np.array([1, 2, 2, 1])
    result, d = strength_swap(s, t, c, c, seed=4)
    assert np.array_equal(t, result)
    assert sum(v['completed_swaps'] for v in d.values()) == 0
    with pytest.raises(ValueError):
        strength_swap(s, t, c, np.array([1, -2, 2, 1]), seed=4)


def test_bin_edges():
    assert np.searchsorted(BIN_UPPER, [1,2,3,4,5,8,9,16,17,32,33,64,65,128,129,1000]).tolist() == [0,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8]


def test_early_stop_keeps_both_metrics_even_with_nonmonotone_rates():
    for rates in ([1,60,2,55,90], [1,60,2,3,4], [1,2,3,4,5]):
        rows = [dict(s=s, total_spikes=rate, neurons=1, seconds=1, seed=seed) for s,rate in zip([.005,.03,.039,.06,.1],rates) for seed in (1,2)]
        prefix=[]
        for s in [.005,.03,.039,.06,.1]:
            prefix.extend(r for r in rows if r['s']==s)
            if early_stop(prefix,s): break
        a,b=h0_metrics(dict(rows=rows)),h0_metrics(dict(rows=prefix))
        assert (a['H0a'],a['H0b'],a['censor']) == (b['H0a'],b['H0b'],b['censor'])


def test_mechanism_distinct_weighted_cycles():
    from flybench.mechanism_v21 import mechanism
    # 0->1->2->0, weights 2,3,5 plus 1->0 weight 7 and autapse 11.
    g=dict(ids=np.arange(3),offsets=np.array([0,2,4,5]),targets=np.array([0,1,0,2,0]),weights=np.array([11.,2.,7.,3.,5.]))
    m=mechanism(g)
    assert m['classification']=='EXPLORATORY'
    assert m['contact_weighted_2_cycles']==14
    assert m['contact_weighted_3_cycles']==30
    assert m['excitatory_reciprocity']==.5
    assert m['largest_excitatory_scc']==3


def test_frozen_analysis_family_sizes_and_censoring(tmp_path, monkeypatch):
    from experiments import v2f_analyze as analysis
    from flybench.experiment_v2 import save, read
    blocks=[dict(test='H0-STR',circuit='T1a',families=['N-STRENGTH'],nulls=2),dict(test='H0-FULL',circuit='FULL',families=['N-SIGN','N-STRENGTH'],nulls=2),dict(test='H0-T2',circuit='T2',families=['N-FULL','N-SIGN','N-STRENGTH'],nulls=2)]
    p=dict(confirmatory=blocks,resource_plan={},exploratory={'E2b':dict(status='SKIPPED',reason='test')})
    monkeypatch.setattr(analysis,'verify_freeze',lambda:'test')
    monkeypatch.setattr(analysis,'read',lambda path:p if str(path).endswith('protocol-v2.1.json') else read(path))
    save(tmp_path/'COMPLETE.json',dict(protocol_sha256='test',blocks=[b['test'] for b in blocks],invocation_wall_seconds=1))
    for b in blocks:
        for t in analysis.tasks(p,b['test']):
            block,c,f,i=t
            rows=[dict(s=s,seed=seed,seconds=10,neurons=1,total_spikes=10 if f=='REAL' else 1000) for s in [.005,.039,.1] for seed in (1,2)]
            save(tmp_path/block/f'{c}-{f}-{i:03d}.json.gz',dict(task=list(t),protocol_sha256='test',data=dict(rows=rows),wall_seconds=1,peak_rss_kib=1))
    result=analysis.summarize(tmp_path)
    assert len(result['tables'])==10
    assert all(v['n_null']==2 for v in result['tables'])
    assert all(v['effect'] is None and v['real_censored'] for v in result['tables'] if v['metric']=='H0a')
    assert all('p' not in v and 'holm_p' not in v for v in result['exploratory'])
    victim=tmp_path/'H0-FULL/FULL-N-SIGN-001.json.gz';victim.unlink()
    with pytest.raises(FileNotFoundError):analysis.summarize(tmp_path)
