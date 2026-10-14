import numpy as np
import pytest
from flybench.analysis_v2 import permutation_rank, segment_bouts, turn_autocorrelation, trial_metrics, matched_calibration_summary


def test_exchangeable_ranks_are_exactly_uniform():
    # Every possible assignment of the real label to an exchangeable sample.
    values=np.random.default_rng(841).normal(size=101).tolist()
    percentiles=[permutation_rank(v,values[:i]+values[i+1:])['lower_percentile'] for i,v in enumerate(values)]
    assert np.sort(percentiles)==pytest.approx((np.arange(101)+.5)/101)


def test_known_shift_and_ties():
    null=np.linspace(-1,1,99).tolist()
    assert permutation_rank(4.,null)['two_sided_p']==pytest.approx(.02)
    ties=permutation_rank(0.,[0.]*20)
    assert ties['exact_rank']==11 and ties['lower_percentile']==.5
    assert ties['two_sided_p']==1


def rows(speeds):
    return [dict(tick=(i+1)*20,applied=[False,speed,0.]) for i,speed in enumerate(speeds)]


def test_segmentation_known_durations_and_gap_censoring():
    data=rows([0,0,.01,.01,.01,0,0,.01])
    result=segment_bouts(data)
    assert [s['duration_ms'] for s in result['segments']]==[20,30,20,10]
    assert trial_metrics({'records':data})['bout_durations_ms']==[30]
    assert trial_metrics({'records':data})['pause_durations_ms']==[20]
    data[4]['tick']+=20
    with pytest.raises(ValueError):segment_bouts(data)
    del data[4]
    result=segment_bouts(data)
    assert result['gaps']
    assert result['segments'][1]['right_censored']


def test_escape_and_autocorrelation():
    data=rows([0]*5)
    data[2]['applied'][0]=True
    data[3]['applied'][0]=True
    m=trial_metrics({'records':data,'impact_tick':100})
    assert m['first_escape_offset_before_impact_ms']==30
    assert m['escape_onset_ticks']==[40]
    result=turn_autocorrelation([1.,-1.,1.,-1.],2)
    assert [v['correlation'] for v in result]==pytest.approx([1,-1,1])
    assert turn_autocorrelation([0.,0.],1)[1]['correlation'] is None


def test_matched_summary_keeps_uncalibratable_and_budget():
    grid={'s':[.01,.039],'kappa':[.05],'nu0':[.5,5],'gain':[2,8]}
    a=dict(graph_id='real',passes_all=True,no_threat_mean_rate_hz=2,parameters=dict(s=.01,kappa=.05,nu0=.5,gain=2))
    b=dict(a,graph_id='null',passes_all=False)
    result=matched_calibration_summary([a,b],['real','null','missing'],grid)
    assert [x['status'] for x in result]==['CALIBRATED','UNCALIBRATABLE','NOT_RUN']


def test_missing_command_censors_both_sides_of_gap():
    data=rows([.01,.01,.01,0.])
    data[1]['applied']=None
    segments=segment_bouts(data)['segments']
    assert segments[0]['right_censored']
    assert segments[1]['left_censored']
