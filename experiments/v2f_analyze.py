"""Frozen v2.1 analysis. Verify recomputes all tables and source identities."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import numpy as np
from scipy.stats import spearmanr
from flybench.experiment_v2 import ROOT,read,save
from flybench.experiment_v21 import verify_freeze
from flybench.analysis_v2 import h0_metrics,compare_family,holm
from experiments.v2f_run import tasks


def summarize(out):
    identity=verify_freeze();p=read(ROOT/'profiles/protocol-v2.1.json');complete=read(out/'COMPLETE.json')
    if complete['protocol_sha256']!=identity:raise RuntimeError('completion identity mismatch')
    records={};hashes={};metrics={};tables=[];exploratory=[]
    for block in complete['blocks']:
        for task in tasks(p,block):
            _,c,f,i=task;path=out/block/f'{c}-{f}-{i:03d}.json.gz';r=read(path)
            if r['task']!=list(task) or r['protocol_sha256']!=identity:raise RuntimeError('raw record identity mismatch')
            hashes[str(path.relative_to(out))]=hashlib.sha256(path.read_bytes()).hexdigest();records[task]=r
            if block!='E1':metrics[task]=h0_metrics(r['data'])
    for b in p['confirmatory']:
        block,c=b['test'],b['circuit'];real=metrics[(block,c,'REAL',0)]
        for f in b['families']:
            nulls=[metrics[(block,c,f,i)] for i in range(b['nulls'])]
            for row in compare_family(real,nulls,['H0b'] if c=='FULL' else ['H0a','H0b'],minimum=b['nulls']):
                row.update(test=block,circuit=c,family=f,classification='CONFIRMATORY')
                if row['metric']=='H0a':
                    row['real_censored']=row['real']==.11;row['null_median_censored']=row['null_median']==.11
                    row['null_band_censored']=[v==.11 for v in row['null_band']]
                    if row['real_censored'] or row['null_median_censored']:row['effect']=None
                if c=='FULL':row['metric']='H0b-FULL'
                tables.append(row)
        if c=='FULL':
            rows=[r for r in tables if r['test']==block]
            for row,adjusted in zip(rows,holm([r['p'] for r in rows])):row['holm_p']=adjusted
    for block in ('E2a','E3-low','E3-high'):
        if block not in complete['blocks']:
            exploratory.append(dict(classification='EXPLORATORY',test=block,status='NOT_RUN_RESOURCE_RULE'));continue
        real=metrics[(block,'T1a','REAL',0)]
        nulls=[metrics[(block,'T1a','N-SIGN',i)] for i in range(99)]
        for key in ('H0a','H0b'):
            values=[n[key] for n in nulls]
            exploratory.append(dict(classification='EXPLORATORY',test=block,metric=key,real=real[key],null_median=float(np.median(values)),null_band=np.percentile(values,[2.5,97.5]).tolist(),percentile=float((sum(v<real[key] for v in values)+.5*sum(v==real[key] for v in values))/len(values))))
    exploratory.append(dict(classification='EXPLORATORY',test='E2b',**p['exploratory']['E2b']))
    descriptors={};correlations=[]
    for task,r in records.items():
        if task[0]!='E1':continue
        _,c,f,i=task
        values={k:(v['value'] if isinstance(v,dict) else v) for k,v in r['data'].items() if k!='classification'}
        if c=='T1a' and f in ('REAL','N-FULL','N-CONTEXT','N-SIGN'):
            old=ROOT/'evidence/V2E/results/H0'/f'{c}-{f}-{i:03d}.json.gz'
            hashes['V2E/H0/'+old.name]=hashlib.sha256(old.read_bytes()).hexdigest();h=h0_metrics(read(old)['data'])
        else:h=metrics[('H0-STR' if c=='T1a' else 'H0-T2',c,f,i)]
        descriptors[f'{c}:{f}:{i}']=dict(classification='EXPLORATORY',**values,H0a=h['H0a'],H0b=h['H0b'],numerical_status={k:v['status'] for k,v in r['data'].items() if isinstance(v,dict)})
    for c in ('T1a','T2'):
        rk=f'{c}:REAL:0'
        if rk not in descriptors:continue
        real=descriptors[rk]
        for f in ('N-FULL','N-CONTEXT','N-SIGN','N-STRENGTH'):
            rows=[v for k,v in descriptors.items() if k.startswith(f'{c}:{f}:')]
            if not rows:continue
            for key in ('leading_signed_eigenvalue','excitatory_spectral_radius','excitatory_reciprocity','largest_excitatory_scc','contact_weighted_2_cycles','contact_weighted_3_cycles','in_strength_gini'):
                valid=[v for v in rows if v[key] is not None];values=[v[key] for v in valid]
                summary=dict(classification='EXPLORATORY',test='E1',circuit=c,family=f,metric=key,real=real[key],valid=len(valid),missing=len(rows)-len(valid),null_median=float(np.median(values)) if values else None,null_band=np.percentile(values,[2.5,97.5]).tolist() if values else None,
                    percentile=float((sum(v<real[key] for v in values)+.5*sum(v==real[key] for v in values))/len(values)) if values and real[key] is not None else None)
                exploratory.append(summary)
                for outcome in ('H0a','H0b'):
                    rho=None if len(set(values))<2 or len({v[outcome] for v in valid})<2 else float(spearmanr(values,[v[outcome] for v in valid]).statistic)
                    correlations.append(dict(classification='EXPLORATORY',circuit=c,family=f,metric=key,outcome=outcome,pairs=len(valid),rho=rho))
    return dict(schema='flybench.results.v2.1',protocol_sha256=identity,tables=tables,exploratory=exploratory,correlations=correlations,descriptors=descriptors,
        metrics={':'.join(map(str,k)):v for k,v in metrics.items()},raw_input_sha256=hashes,
        summed_task_wall_seconds=sum(r['wall_seconds'] for r in records.values()),peak_task_rss_kib=max(r['peak_rss_kib'] for r in records.values()),completion=complete,resource_plan=p['resource_plan'])


def narrative(r):
    lines=['# Robustness findings','','Confirmatory model comparisons. H0a >0.1 is censored; 0.11 is a rank sentinel only.','','| Test | Family | Metric | Real | Null median | 95% null band | p | Holm p |','|---|---|---|---:|---:|---|---:|---:|']
    for v in r['tables']:
        real='>0.1' if v.get('real_censored') else f"{v['real']:.6g}"
        lines.append(f"| {v['test']} | {v['family']} | {v['metric']} | {real} | {v['null_median']:.6g} | {v['null_band']} | {v['p']:.6g} | {v['holm_p']:.6g} |")
    lines+=['','## Family conclusions','']
    for test in ('H0-STR','H0-FULL','H0-T2'):
        for family in sorted({v['family'] for v in r['tables'] if v['test']==test}):
            rows=[v for v in r['tables'] if v['test']==test and v['family']==family]
            positive=all(v['holm_p']<.05 and (v['real']>v['null_median'] if v['metric']=='H0a' else v['real']<v['null_median']) for v in rows)
            lines.append(f'- {test}, {family}: '+('The model stability difference holds for this family.' if positive else 'The registered stability result did not replicate for this family. Inspect metric directions and adjusted p-values above.'))
    lines+=['','## EXPLORATORY mechanism and assumptions','','Descriptive percentiles and Spearman correlations only. No confirmatory or multiplicity-adjusted claim. All values, missing eigenvalues, skipped checks and correlations are in results-v2f.json.','']
    for v in r['exploratory']:
        if 'status' in v:lines.append(f"- EXPLORATORY {v['test']}: {v['status']}. {v.get('reason','')}")
    lines+=['','## Limits and compute','','Uniform LIF neurons, assumed transmitter signs and port mappings, and interior-only noise limit these results to this model. H1 and H2 retain insufficient calibratable nulls.',f"Summed task time: {r['summed_task_wall_seconds']:.3f} seconds. Elapsed invocation: {r['completion']['invocation_wall_seconds']:.3f} seconds. Peak task RSS: {r['peak_task_rss_kib']} KiB.",'','```sh','uv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify','```']
    return '\n'.join(lines)+'\n'


def figures(out,r):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    dest=out/'figures';dest.mkdir(exist_ok=True)
    for row in r['tables']:
        c,f,t=row['circuit'],row['family'],row['test'];metric='H0b' if c=='FULL' else row['metric']
        values=[v[metric] for k,v in r['metrics'].items() if k.startswith(f'{t}:{c}:{f}:')]
        fig,ax=plt.subplots(figsize=(7,4));ax.hist(values,bins=25,color='#0072b2',label=f'{f}, n={len(values)}');ax.axvline(row['real'],color='#d55e00',label='Measured');ax.set(xlabel=metric+(' (.11 = censored >.1)' if metric=='H0a' else ' (Hz)'),ylabel='Null graphs');ax.legend();fig.tight_layout();fig.savefig(dest/f'{t}-{f}-{metric}.png',dpi=120);plt.close(fig)
    for t,c in (('H0-STR','T1a'),('H0-T2','T2'),('H0-FULL','FULL')):
        real=r['metrics'][f'{t}:{c}:REAL:0']['curve']
        for f in sorted({v['family'] for v in r['tables'] if v['test']==t}):
            curves=[v['curve'] for k,v in r['metrics'].items() if k.startswith(f'{t}:{c}:{f}:')]
            # Bands only where every null was evaluated. Never impute stopped tails.
            x=sorted(set.intersection(*[{v['s'] for v in curve} for curve in curves]))
            values=[[next(v['rate_hz'] for v in curve if v['s']==s) for s in x] for curve in curves]
            band=np.percentile(values,[2.5,97.5],axis=0)
            fig,ax=plt.subplots(figsize=(7,4));ax.fill_between(x,*band,alpha=.25,color='#0072b2',label=f'{f} complete observed band');ax.errorbar(x,np.median(values,axis=0),yerr=[np.median(values,axis=0)-band[0],band[1]-np.median(values,axis=0)],fmt='.',color='#0072b2');ax.plot([v['s'] for v in real],[v['rate_hz'] for v in real],color='#d55e00',label='Measured');ax.axhline(50,color='gray',ls=':');ax.set(xlabel='Coupling s',ylabel='Whole-graph rate (Hz)',title=c+'; stopped tails remain missing');ax.legend();fig.tight_layout();fig.savefig(dest/f'{c}-{f}-curve.png',dpi=120);plt.close(fig)
    for row in r['correlations']:
        values=[v for k,v in r['descriptors'].items() if k.startswith(f"{row['circuit']}:{row['family']}:") and v[row['metric']] is not None]
        fig,ax=plt.subplots(figsize=(5,4));ax.scatter([v[row['metric']] for v in values],[v[row['outcome']] for v in values],s=9,alpha=.5);ax.set(xlabel=row['metric'],ylabel=row['outcome'],title='EXPLORATORY '+row['circuit']+' '+row['family']);fig.tight_layout();fig.savefig(dest/f"E1-{row['circuit']}-{row['family']}-{row['metric']}-{row['outcome']}.png",dpi=100);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('evidence/V2F/results'));p.add_argument('--verify',action='store_true');a=p.parse_args();r=summarize(a.out)
    if a.verify:
        assert r==read(a.out/'tables.json'),'tables differ'
        assert narrative(r)==(a.out/'FINDINGS.md').read_text(),'findings differ'
        print('PASS: v2 and v2.1 manifests and every table recomputed from raw records')
    else:
        save(a.out/'tables.json',r);(a.out/'FINDINGS.md').write_text(narrative(r));figures(a.out,r)
