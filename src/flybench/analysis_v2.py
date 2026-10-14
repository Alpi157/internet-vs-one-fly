"""Synthetic-tested analysis primitives. No real-graph H1/H2 analysis in V2C.

Durations use integer neural ticks (0.5 ms). Movement segmentation uses absolute
speed > 0.001 units/ms OR absolute turn > 0.0001 rad/ms. These analysis thresholds
are distinct from the exact-nonzero calibration criterion. Gaps split segments;
edge and gap-touching segments are explicitly censored. No missing values are
interpolated. Rank percentiles use midranks; tail p-values include ties.
"""
from __future__ import annotations
from typing import Any
import math
import numpy as np


def permutation_rank(real: float, null: list[float]) -> dict[str, Any]:
    values=np.asarray(null,dtype=np.float64)
    if values.ndim!=1 or not values.size or not np.all(np.isfinite(values)) or not math.isfinite(real):
        raise ValueError('real and nonempty null sample must be finite')
    less=int(np.count_nonzero(values<real)); equal=int(np.count_nonzero(values==real))
    greater=int(values.size-less-equal); denominator=int(values.size+1)
    rank=1+less+equal/2
    lower_p=(1+less+equal)/denominator
    upper_p=(1+greater+equal)/denominator
    return dict(n_null=int(values.size),less=less,equal=equal,greater=greater,
        exact_rank=rank,rank_denominator=denominator,
        lower_percentile=(rank-.5)/denominator,
        upper_percentile=1-(rank-.5)/denominator,
        two_sided_percentile=2*min((rank-.5)/denominator,1-(rank-.5)/denominator),
        lower_tail_p=lower_p,upper_tail_p=upper_p,two_sided_p=min(1.,2*min(lower_p,upper_p)),
        ties_rule='midrank including real; conservative inclusive ties for tail p-values; plus-one real observation')


def segment_bouts(records: list[dict], *, interval_ticks: int=20,
                  speed_threshold: float=.001, turn_threshold: float=.0001) -> dict:
    if interval_ticks<1 or speed_threshold<0 or turn_threshold<0:
        raise ValueError('invalid segmentation thresholds')
    segments=[]; current=None; previous=None; gaps=[]; after_gap=True
    for row in records:
        tick=row['tick']
        if type(tick) is not int or tick<interval_ticks or (previous is not None and tick<=previous):
            raise ValueError('ticks must be increasing integer interval ends')
        command=row.get('applied')
        valid=command is not None and len(command)==3 and all(math.isfinite(v) for v in command)
        contiguous=previous is None or tick==previous+interval_ticks
        if not contiguous or not valid:
            if current:
                current['right_censored']=True;segments.append(current);current=None
            gaps.append(dict(after_tick=previous,before_tick=tick,reason='missing command' if not valid else 'trace gap'))
            after_gap=True
        if valid:
            moving=abs(command[1])>speed_threshold or abs(command[2])>turn_threshold
            if current is not None and moving!=current['moving']:
                segments.append(current);current=None
            if current is None:
                current=dict(moving=moving,start_tick=tick-interval_ticks,end_tick=tick,
                    left_censored=after_gap,right_censored=False)
            else:current['end_tick']=tick
            after_gap=False
        previous=tick
    if current:
        current['right_censored']=True;segments.append(current)
    for segment in segments:segment['duration_ms']=(segment['end_tick']-segment['start_tick'])*.5
    return dict(segments=segments,gaps=gaps,interval_ticks=interval_ticks,speed_threshold=speed_threshold,turn_threshold=turn_threshold)


def turn_autocorrelation(turns: list[float | None], max_lag: int) -> list[dict]:
    if max_lag<0:raise ValueError('max_lag must be nonnegative')
    values=np.array([np.nan if v is None else v for v in turns],dtype=np.float64)
    output=[]
    for lag in range(max_lag+1):
        left=values[:len(values)-lag] if lag else values
        right=values[lag:]
        if lag>=len(values):left=right=np.array([])
        mask=np.isfinite(left)&np.isfinite(right)
        x,y=left[mask],right[mask]
        pairs=int(x.size)
        denominator=0. if pairs<2 else float(np.sqrt(np.sum((x-x.mean())**2)*np.sum((y-y.mean())**2)))
        corr=None if denominator==0. else float(np.sum((x-x.mean())*(y-y.mean()))/denominator)
        output.append(dict(lag_intervals=lag,pairs=pairs,correlation=corr))
    return output


def trial_metrics(trial: dict, *, interval_ticks: int=20) -> dict:
    records=trial['records']; segmentation=segment_bouts(records,interval_ticks=interval_ticks)
    impact=trial.get('impact_tick'); onset_ticks=[]; prior=False; previous_tick=None
    speed_values=[]; turn_values=[]; group_counts=[0,0]; gaps=0
    for row in records:
        command=row.get('applied')
        if command is None:
            prior=None;previous_tick=row['tick'];turn_values.append(None);gaps+=1;continue
        if previous_tick is not None and row['tick']!=previous_tick+interval_ticks:
            prior=None;turn_values.extend([None]*((row['tick']-previous_tick)//interval_ticks-1));gaps+=1
        escape=bool(command[0])
        # Cannot invent an onset on the far side of a trace gap.
        if escape and prior is False:onset_ticks.append(row['tick']-interval_ticks)
        prior=escape; previous_tick=row['tick']
        moving=abs(command[1])>.001 or abs(command[2])>.0001
        if moving:speed_values.append(abs(command[1]))
        turn_values.append(command[2])
        counts=row.get('group_counts')
        if counts is not None:
            group_counts[0]+=counts[0];group_counts[1]+=counts[1]
    before=[] if impact is None else [t for t in onset_ticks if t<impact]
    total=sum(group_counts)
    turns=np.array([v for v in turn_values if v is not None])
    return dict(escape_probability_observation=None if impact is None or gaps else int(bool(before)),
        escape_onset_ticks=onset_ticks,first_escape_offset_before_impact_ms=None if not before else (impact-before[0])*.5,
        escape_group_left_right_asymmetry=None if total==0 else (group_counts[0]-group_counts[1])/total,
        segmentation=segmentation,
        bout_durations_ms=[s['duration_ms'] for s in segmentation['segments'] if s['moving'] and not s['left_censored'] and not s['right_censored']],
        pause_durations_ms=[s['duration_ms'] for s in segmentation['segments'] if not s['moving'] and not s['left_censored'] and not s['right_censored']],
        speed_distribution_while_moving=speed_values,turn_autocorrelation=turn_autocorrelation(turn_values,10),
        left_right_turn_asymmetry=None if not len(turns) or np.count_nonzero(turns)==0 else float((np.count_nonzero(turns>0)-np.count_nonzero(turns<0))/np.count_nonzero(turns)),
        missing_or_gapped_intervals=gaps)


def matched_calibration_summary(graph_rows: list[dict], expected_graph_ids: list[str],
                                grid_order: dict[str,list]) -> list[dict]:
    """Retain every graph, including failures; no silent dropping or imputation."""
    output=[]
    for graph_id in expected_graph_ids:
        candidates=[r for r in graph_rows if r['graph_id']==graph_id]
        passing=[r for r in candidates if r['passes_all']]
        def key(row):
            return (row['no_threat_mean_rate_hz'],*(grid_order[name].index(row['parameters'][name]) for name in ('s','kappa','nu0','gain')))
        selected=min(passing,key=key) if passing else None
        output.append(dict(graph_id=graph_id,attempted_points=len(candidates),passing_points=len(passing),
            status='CALIBRATED' if passing else 'UNCALIBRATABLE' if candidates else 'NOT_RUN',selected=selected))
    return output
