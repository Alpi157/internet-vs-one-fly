"""Frozen raw-record analysis and figures; --verify recomputes all tables."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import json
import platform
import os
import numpy as np
from flybench.experiment_v2 import ROOT,FAMILIES,read,save,verify_freeze
from flybench.analysis_v2 import h0_metrics,h1_metrics,h2_metrics,compare_family


def ranks(values):
    values=np.asarray(values);return np.array([np.count_nonzero(values<v)+(np.count_nonzero(values==v)+1)/2 for v in values])


def summarize(out):
    identity=verify_freeze()
    complete=read(out/'COMPLETE.json')
    if complete['protocol_sha256']!=identity:raise RuntimeError('completion identity mismatch')
    profile=read(ROOT/'profiles/calibration-v2.json');projection=read(out/'projection.json')
    circuits=complete['circuits'];tables=[];cal=[];secondary=[];controls=[];metrics={};wall=0.;inputs={}
    for stage,fn in (('H0',h0_metrics),('H1',h1_metrics),('H2',h2_metrics)):
        for path in sorted((out/stage).glob('*.json.gz')):
            record=read(path)
            if record['protocol_sha256']!=identity:raise RuntimeError('result identity mismatch')
            if 'trials' not in record['data'] and 'rows' not in record['data']:continue
            metrics[(stage,record['circuit'],record['family'],record['index'])]=fn(record['data'])
            wall+=record['wall_seconds'];inputs[str(path.relative_to(out))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for circuit in circuits:
        real=read(out/'calibration'/f'{circuit}-REAL-000.json.gz')['data']
        for family in FAMILIES:
            null_cal=[]
            for i in range(profile['nulls']['count_per_circuit'][circuit]):
                path=out/'calibration'/f'{circuit}-{family}-{i:03d}.json.gz';record=read(path);null_cal.append(record['data']);wall+=record['wall_seconds'];inputs[str(path.relative_to(out))]=hashlib.sha256(path.read_bytes()).hexdigest()
            selected=[v['selected'] for v in null_cal if v['selected']]
            matched={}
            for key in ('no_threat_mean_rate_hz','standard_escape_fraction'):
                values=[v[key] for v in selected]
                matched[key]=dict(real=None if not real['selected'] else real['selected'][key],null_median=float(np.median(values)) if values else None,null_band=np.percentile(values,[2.5,97.5]).tolist() if values else None)
            cal.append(dict(circuit=circuit,family=family,total=len(null_cal),calibratable=len(selected),fraction=len(selected)/len(null_cal),passing_points=[v['passing_points'] for v in null_cal],real_passing_points=real['passing_points'],real_selected=None if not real['selected'] else real['selected']['parameters'],matched=matched))
            for stage in ('H0','H1','H2'):
                rk=(stage,circuit,'REAL',0)
                if rk not in metrics:continue
                ns=[v for (s,c,f,i),v in metrics.items() if (s,c,f)==(stage,circuit,family)]
                keys=[stage+x for x in ('ab' if stage=='H0' else 'abc')]
                if stage=='H0' and len(ns)!=profile['nulls']['count_per_circuit'][circuit]:raise RuntimeError('incomplete H0 family')
                for row in compare_family(metrics[rk],ns,keys,minimum=1 if stage=='H0' else 149):
                    if row['metric']=='H0a':
                        row['real_censored']=row['real']==.11
                        row['null_median_censored']=row.get('null_median')==.11
                        row['null_band_censored']=[v==.11 for v in row.get('null_band',[])]
                        if row['real_censored'] or row['null_median_censored']:
                            row['effect']=None
                            row['effect_note']='not point identifiable: critical coupling censored above 0.1; 0.11 is rank-only sentinel'
                    row.update(hypothesis=stage,circuit=circuit,family=family,classification='primary' if circuit==('T1a' if stage=='H0' else complete['primary']) else 'secondary descriptive')
                    tables.append(row)
            pairs=[]
            for i in range(profile['nulls']['count_per_circuit'][circuit]):
                key=('H0',circuit,family,i)
                if key not in metrics:continue
                d=read(out/'topology'/f'{circuit}-{family}-{i:03d}.json')
                shift=d['excitatory_inhibitory_input_ratio_shift']['mean_absolute']
                if shift is not None:pairs.append((metrics[key]['H0a'],shift))
            corr=None
            if pairs:
                x,y=np.array(pairs).T
                if len(np.unique(x))>1 and len(np.unique(y))>1:corr=float(np.corrcoef(ranks(x),ranks(y))[0,1])
            secondary.append(dict(circuit=circuit,family=family,analysis='Spearman critical coupling versus mean absolute E/I input-ratio shift',pairs=len(pairs),rho=corr,censored_critical_values='tied top rank'))
            fixed=[]
            for path in sorted((out/'fixed').glob(f'{circuit}-{family}-*.json.gz')):
                record=read(path);data=record['data']
                inputs[str(path.relative_to(out))]=hashlib.sha256(path.read_bytes()).hexdigest();wall+=record['wall_seconds']
                if 'H1' in data:fixed.append(dict(**h1_metrics(data['H1']),**h2_metrics(data['H2'])))
            for stage in ('H1','H2'):
                key=(stage,circuit,'REAL',0)
                if key in metrics and fixed:
                    rows=compare_family(metrics[key],fixed,[stage+x for x in 'abc'],minimum=1)
                    for row in rows:row.pop('holm_p')
                    secondary.append(dict(circuit=circuit,family=family,analysis='fixed real parameters; descriptive, all nulls, no Holm claim',hypothesis=stage,rows=rows))
        cp=out/'controls'/f'{circuit}-REAL-000.json.gz'
        if cp.exists():
            record=read(cp);d=record['data'];wall+=record['wall_seconds'];inputs[str(cp.relative_to(out))]=hashlib.sha256(cp.read_bytes()).hexdigest()
            if 'C_SIMPLE' in d:
                trials=d['C_SIMPLE']['trials'];by_speed={s:[t for t in trials if t['condition']['offset']==0 and t['condition']['speed']==s] for s in (.025,.1)}
                leads=[(t['impact_tick']-next(x for x in t['escape_onset_ticks'] if 400<x<t['impact_tick']))*.5 for t in trials if t['escape_before_impact']]
                controls.append(dict(circuit=circuit,C_SIMPLE=dict(fit={k:v for k,v in d['C_SIMPLE']['fit'].items() if k!='evaluations'},H1a=float(np.mean([t['escape_before_impact'] for t in by_speed[.1]])-np.mean([t['escape_before_impact'] for t in by_speed[.025]])),H1b=float(np.median(leads)) if len(leads)>=10 else None,escape_count=len(leads),H1c=None,H1c_reason='single unit has no left/right identity'),C_TIMER=dict(H1a=0,H1b=30,H1c=None),C_NOISE_DEC=h2_metrics(d['C_NOISE_DEC']),interventions={name:dict(H1=h1_metrics(value['H1']),H2=h2_metrics(value['H2'])) for name,value in d['interventions'].items()}))
    result=dict(protocol_sha256=identity,primary_circuit=complete['primary'],circuits=circuits,projection=projection,tables=tables,calibration=cal,secondary=secondary,controls=controls,raw_input_sha256=inputs,summed_task_wall_seconds=wall,hardware=dict(platform=platform.platform(),hardware_threads=os.cpu_count()),metrics={':'.join(map(str,k)):v for k,v in metrics.items()})
    return result


def figures(out,result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    dest=out/'figures';dest.mkdir(exist_ok=True)
    for row in result['tables']:
        metric=row['metric'];stage=row['hypothesis'];c=row['circuit'];family=row['family']
        values=[v[metric] for key,v in result['metrics'].items() if key.startswith(f'{stage}:{c}:{family}:') and v[metric] is not None]
        if not values:continue
        fig,ax=plt.subplots(figsize=(7,4));ax.hist(values,bins=25,color='#0072b2',alpha=.8,label=f'{family} n={len(values)}')
        if row['real'] is not None:ax.axvline(row['real'],color='#d55e00',lw=2,label='Measured wiring')
        ax.set(xlabel=metric+(' (0.11 denotes censored above 0.1)' if metric=='H0a' else ''),ylabel='Null graphs',title=f'{c}: {metric} versus {family}');ax.legend();fig.tight_layout();fig.savefig(dest/f'{c}-{family}-{metric}.png',dpi=140);plt.close(fig)
    for c in result['circuits']:
        for family in FAMILIES:
            real=result['metrics'][f'H0:{c}:REAL:0']['curve'];curves=[v['curve'] for k,v in result['metrics'].items() if k.startswith(f'H0:{c}:{family}:')]
            x=[r['s'] for r in real];values=np.array([[r['rate_hz'] for r in curve] for curve in curves]);band=np.percentile(values,[2.5,97.5],axis=0)
            fig,ax=plt.subplots(figsize=(7,4));ax.fill_between(x,*band,color='#0072b2',alpha=.25,label=f'{family} 95% null band');ax.plot(x,[r['rate_hz'] for r in real],color='#d55e00',marker='o',label='Measured wiring');ax.axhline(50,color='gray',ls=':');ax.set(xlabel='Coupling s',ylabel='Whole-circuit rate (Hz)',title=c);ax.legend();fig.tight_layout();fig.savefig(dest/f'{c}-{family}-H0-curve.png',dpi=140);plt.close(fig)


def narrative(result):
    lines=['# V2E findings','','Only model-level claims are permitted. H0 was pilot-motivated; all confirmatory null seeds are fresh.','','| Circuit | Family | Metric | Real | Null median | 95% null band | Effect | p | Holm p | Status |','|---|---|---|---:|---:|---|---:|---:|---:|---|']
    for r in result['tables']:
        lines.append('| '+' | '.join(str(r.get(k,'NA')) for k in ('circuit','family','metric','real','null_median','null_band','effect','p','holm_p','status'))+' |')
    lines+=['','Critical coupling 0.11 in the machine tables is a rank sentinel meaning censored above 0.1, not a measured value. Secondary circuits and fixed-parameter comparisons are descriptive.','','## Calibration','']
    for c in result['calibration']:lines.append(f"- {c['circuit']} {c['family']}: {c['calibratable']}/{c['total']} calibratable; real passing points {c['real_passing_points']}; selected {c['real_selected']}. Matched calibration statistics are in tables.json.")
    lines+=['','## Conclusions','']
    for circuit in result['circuits']:
        for hypothesis in ('H0','H1','H2'):
            rows=[r for r in result['tables'] if r['circuit']==circuit and r['hypothesis']==hypothesis]
            sig=[r for r in rows if r.get('holm_p') is not None and r['holm_p']<.05]
            if not rows:message='Not run; no calibratable real graph in the executed scope.'
            elif all(r['p'] is None for r in rows):message='No computable confirmatory comparison; inspect missing values and calibratable-null counts.'
            elif sig:message='Model-level differences from the listed shuffles were detected. See metric directions and effects; this does not establish a requirement in real flies.'
            else:message='No Holm-significant difference was detected under these assumptions; this is not proof that wiring does not matter.'
            lines.append(f'- {circuit} {hypothesis}: {message}')
    lines+=['','## Secondary analyses and controls','','Full descriptive fixed-parameter results, Spearman correlations, lesion results, stochastic control fit and mismatches, and timer results are in tables.json. No secondary superiority claim is made.','','## Compute and verification','',f"Summed task wall time: {result['summed_task_wall_seconds']:.3f} s. Tasks overlap across workers; this is not elapsed wall time. Hardware: {result['hardware']}.",'','```sh','uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify','```','','This recomputes tables from raw per-trial records and checks every frozen file.']
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('evidence/V2E/results'));p.add_argument('--verify',action='store_true');a=p.parse_args()
    result=summarize(a.out)
    if a.verify:
        assert result==read(a.out/'tables.json'),'recomputed tables differ'
        assert narrative(result)==(a.out/'FINDINGS.md').read_text(),'findings differ'
        print('PASS: frozen identities and every table recomputed from raw records')
    else:
        save(a.out/'tables.json',result);figures(a.out,result);(a.out/'FINDINGS.md').write_text(narrative(result))
