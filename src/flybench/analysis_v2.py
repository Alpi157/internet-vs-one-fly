"""Synthetic-tested analysis primitives. No real-graph H1/H2 analysis in V2C.

Durations use integer neural ticks (0.5 ms). Movement segmentation uses absolute
speed >= 0.002 units/ms OR absolute turn >= 0.0005 rad/ms, shared with calibration. Gaps split segments;
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
                  speed_threshold: float=.002, turn_threshold: float=.0005) -> dict:
    if interval_ticks<1 or speed_threshold<0 or turn_threshold<0:
        raise ValueError('invalid segmentation thresholds')
    segments=[]; current=None; previous=None; gaps=[]; after_gap=True
    for row in records:
        tick=row['tick']
        if type(tick) is not int or tick<interval_ticks or tick % interval_ticks or (previous is not None and tick<=previous):
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
            moving=abs(command[1])>=speed_threshold or abs(command[2])>=turn_threshold
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
    impact=trial.get('impact_tick'); onset_ticks=[]; prior=False if records and records[0]['tick']==interval_ticks else None; previous_tick=None
    speed_values=[]; turn_values=[]; group_counts=[0,0]; gaps=int(bool(records) and records[0]['tick']!=interval_ticks)
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
        moving=abs(command[1])>=.002 or abs(command[2])>=.0005
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
        expected_points=math.prod(len(grid_order[name]) for name in ('s','kappa','nu0','gain'))
        points={tuple(row['parameters'][name] for name in ('s','kappa','nu0','gain')) for row in candidates}
        complete=len(points)==expected_points and len(candidates)==expected_points
        selected=min(passing,key=key) if passing and complete else None
        output.append(dict(graph_id=graph_id,attempted_points=len(candidates),passing_points=len(passing),
            expected_points=expected_points,unique_points=len(points),grid_complete=complete,
            status=('CALIBRATED' if passing else 'UNCALIBRATABLE') if complete else 'INCOMPLETE_GRID' if candidates else 'NOT_RUN',selected=selected))
    return output


def h0_metrics(data: dict) -> dict:
    scales=sorted({r['s'] for r in data['rows']})
    means={s:float(np.mean([r['total_spikes']/r['neurons']/r['seconds'] for r in data['rows'] if r['s']==s])) for s in scales}
    critical=next((s for s in scales if means[s]>=50),None)
    # 0.11 is a ranking sentinel, never a measured critical coupling.
    return dict(H0a=.11 if critical is None else critical,H0b=means[.039],critical_coupling=critical,
        censor='above 0.1' if critical is None else None,curve=[dict(s=s,rate_hz=means[s]) for s in scales])


def h1_metrics(data: dict) -> dict:
    trials=data['trials'];leads=[];by_speed={.025:[],.1:[]};lateral=[];equal=0
    for trial in trials:
        c=trial['condition'];impact=trial['impact_tick'];start=trial['strike_start_tick']
        # Existing calibration onset convention: boundary must be after start.
        onsets=[r['tick'] for r in trial['records'] if r['onset'] and start<r['tick']<impact]
        if onsets:leads.append((impact-onsets[0])*.5)
        if c['offset']==0 and c['speed'] in by_speed:by_speed[c['speed']].append(bool(onsets))
        if c['offset']==3 and c['azimuth'] in (90,270):
            drive=np.sum([r['side_drive'] for r in trial['records']],axis=0)
            counts=np.sum([r['window_counts'] for r in trial['records']],axis=0)
            if drive[0]==drive[1]:equal+=1;continue
            side=0 if drive[0]>drive[1] else 1
            lateral.append(0. if counts.sum()==0 else float((counts[side]-counts[1-side])/counts.sum()))
    return dict(H1a=float(np.mean(by_speed[.1])-np.mean(by_speed[.025])) if all(by_speed.values()) else None,
        H1b=float(np.median(leads)) if len(leads)>=10 else None,H1c=float(np.mean(lateral)) if lateral else None,
        escape_count=len(leads),H1a_counts={str(s):dict(trials=len(v),escapes=sum(v)) for s,v in by_speed.items()},
        H1c_count=len(lateral),H1c_equal_drive_excluded=equal)


def h2_metrics(data: dict) -> dict:
    bouts=[];censored=0;left=[];right=[];turns=[];pauses=[]
    for trial in data['trials']:
        records=trial['records'];segments=segment_bouts(records)['segments']
        for seg in segments:
            if seg['moving']:
                if seg['left_censored'] or seg['right_censored']:censored+=1
                else:bouts.append(seg['duration_ms'])
            elif not seg['left_censored'] and not seg['right_censored']:pauses.append(seg['duration_ms'])
        commands=np.asarray([r['applied'] for r in records],dtype=float)
        moving=(np.abs(commands[:,1])>=.002)|(np.abs(commands[:,2])>=.0005)
        turns.extend(commands[moving,2].tolist())
        mask=moving[:-10]&moving[10:]
        left.extend(commands[:-10,2][mask].tolist());right.extend(commands[10:,2][mask].tolist())
    denominator=0. if len(left)<30 else float(np.sqrt(np.sum((np.array(left)-np.mean(left))**2)*np.sum((np.array(right)-np.mean(right))**2)))
    ac=None if not denominator else float(np.sum((np.array(left)-np.mean(left))*(np.array(right)-np.mean(right)))/denominator)
    absolute=float(np.mean(np.abs(turns))) if turns else 0.
    return dict(H2a=float(np.mean(bouts)) if bouts else None,H2b=ac,H2c=float(np.mean(turns)/absolute) if absolute else None,
        uncensored_bouts=len(bouts),censored_bouts=censored,autocorrelation_pairs=len(left),moving_intervals=len(turns),
        bout_durations_ms=bouts,pause_durations_ms=pauses)


def holm(pvalues: list[float | None]) -> list[float | None]:
    """Family size includes non-computable metrics, conservatively p=1."""
    order=sorted(range(len(pvalues)),key=lambda i:1 if pvalues[i] is None else pvalues[i])
    adjusted=[None]*len(pvalues);prior=0.
    for rank,i in enumerate(order):
        value=1. if pvalues[i] is None else pvalues[i]
        prior=max(prior,min(1.,(len(order)-rank)*value))
        if pvalues[i] is not None:adjusted[i]=prior
    return adjusted


def compare_family(real: dict, nulls: list[dict], keys: list[str],minimum: int=149) -> list[dict]:
    rows=[]
    for key in keys:
        values=[n[key] for n in nulls if n[key] is not None]
        row=dict(metric=key,real=real[key],n_null=len(values),NA_excluded=len(nulls)-len(values),p=None)
        if values:
            row.update(null_median=float(np.median(values)),null_band=np.percentile(values,[2.5,97.5]).tolist(),
                effect=None if real[key] is None else real[key]-float(np.median(values)))
        if real[key] is None:row['status']='not computable'
        elif len(values)<minimum:row['status']='insufficient calibratable nulls'
        else:
            rank=permutation_rank(real[key],values);row.update(status='COMPUTED',p=rank['two_sided_p'],percentile=rank['lower_percentile'])
        rows.append(row)
    for row,adjusted in zip(rows,holm([r['p'] for r in rows])):row['holm_p']=adjusted
    return rows
