import numpy as np
import pytest
from flybench.nulls import sign_stratified_swap, null_diagnostics
from flybench.controls_v2 import simple_trial, direct_contact_fractions
from flybench.model import load_candidate_model_spec
from pathlib import Path
import json


def test_sign_strata_preserve_degrees_and_edge_attributes():
    sources=np.repeat(np.arange(18),3)
    targets=np.array([(i+d)%18 for i in range(18) for d in (0,2,7)])
    counts=np.arange(1,55)
    weights=counts*np.repeat([-1,0,1],18)
    original=targets.copy()
    changed, diagnostics=sign_stratified_swap(sources,targets,weights,seed=20261015)
    repeat,_=sign_stratified_swap(sources,targets,weights,seed=20261015)
    assert np.array_equal(changed,repeat)
    assert np.array_equal(targets,original)
    assert all(v['completed_swaps']==18 for v in diagnostics.values())
    d=null_diagnostics(sources,targets,changed,counts,weights,18,set(),set())
    assert d['in_degree_by_effective_sign_exact']
    assert all(d['degree_preservation'].values())
    assert d['self_loops_identical'] and d['fraction_edges_changed']>0
    for sign in (-1,0,1):
        mask=np.sign(weights)==sign
        assert np.array_equal(np.bincount(targets[mask],minlength=18),np.bincount(changed[mask],minlength=18))
    assert len(set(zip(sources,changed)))==len(sources)


def test_sign_strata_reject_mixed_source_sign():
    with pytest.raises(ValueError,match='consistent'):
        sign_stratified_swap(np.array([0,0]),np.array([1,2]),np.array([1.,-1.]),seed=4)


def test_stochastic_simple_exact_reference_and_no_noise_manipulation():
    spec=load_candidate_model_spec(model_profile_path=Path('profiles/model-v0.1.json'),criteria_path=Path('profiles/numerical-criteria-v0.1.json'),neural_dt_ms=.5,runtime_synaptic_scale=.01,seed=41)
    noise=json.loads(Path('profiles/noise-table-v2.json').read_text())['rows'][5]
    args=(spec,noise,dict(a=.4,b=.6),2.,41)
    assert simple_trial(*args)==simple_trial(*args,reference=True)
    assert simple_trial(*args)['stream']==37


def test_hypothesis_metrics_censoring_lag_and_na():
    from flybench.analysis_v2 import h1_metrics,h2_metrics,holm,compare_family
    trials=[]
    for speed in (.025,.1):
        for i in range(100):
            trials.append(dict(condition=dict(speed=speed,offset=0,azimuth=0),impact_tick=800,strike_start_tick=400,
                records=[dict(tick=500,onset=speed==.1,side_drive=[0,0],window_counts=[0,0])]))
    metrics=h1_metrics(dict(trials=trials))
    assert metrics['H1a']==1 and metrics['H1b']==150 and metrics['H1c'] is None
    records=[dict(tick=(i+1)*20,applied=[False,0 if i in (0,99) else .003,.001 if i%2 else -.001]) for i in range(100)]
    # Explicit pauses must have turn below E2 too.
    for i in (0,99):records[i]['applied'][2]=0
    h2=h2_metrics(dict(trials=[dict(records=records)]))
    assert h2['H2a']==980 and h2['censored_bouts']==0
    assert h2['H2b']==pytest.approx(1) and h2['H2c']==0
    assert holm([.01,.04,None])==[.03,.08,None]
    assert compare_family(dict(x=None),[dict(x=1)],['x'])[0]['status']=='not computable'


def test_raw_trial_matches_calibration_boundary_and_spike_window():
    from flybench.experiment_v2 import raw_trial,parameters,runner
    from experiments.v2d_dry_run import trial
    path=Path('fixtures/escape-circuit-v1')
    graph={name:np.load(path/f'{name}.npy') for name in ('ids','offsets','targets','weights','counts')}
    p=parameters(.01,.05,.5,2)
    c=dict(speed=.05,offset=0,azimuth=0,x=0,y=0)
    raw=raw_trial(graph,p,2026092802,c)
    aggregate=trial(graph,graph['targets'],p,2026092802,(.05,0.,0.))
    assert raw['final_digest']==aggregate['final_digest']
    assert [r['tick'] for r in raw['records'] if r['onset']]==aggregate['escape_onset_ticks']
    assert all(r['window_counts']==[0,0] for r in raw['records'] if r['tick']<=400 or r['tick']>720)
