"""Presentation only: generate public copy from frozen analysis outputs, never simulate.

The frozen analysis remains authoritative. This module formats its values and
protocol-authorized claims, and checks that public artifacts have not drifted.
"""
from pathlib import Path
import argparse
import hashlib
import html
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text())


def num(value, metric=''):
    if value is None:
        return 'missing'
    if metric == 'H0a' and value == .11:
        return '>0.1 (censored)'
    return f'{value:.6g}'


def verdict(row):
    if row['holm_p'] >= .05:
        return 'Not significant; does not establish the stability difference'
    direction = row['real'] > row['null_median'] if row['metric'] == 'H0a' else row['real'] < row['null_median']
    return 'Supports the registered stability direction' if direction else 'Opposite direction: measured rate is higher'


def table(rows):
    lines = ['| Test | Circuit | Family | Metric | Real | Null median | 95% null band | p | Holm p | Verdict |',
             '|---|---|---|---|---:|---:|---|---:|---:|---|']
    for r in rows:
        m = r['metric']
        band = ', '.join(num(v, m) for v in r['null_band'])
        lines.append(f"| {r['test']} | {r['circuit']} | {r['family']} | {m} | {num(r['real'],m)} | {num(r['null_median'],m)} | [{band}] | {num(r['p'])} | {num(r['holm_p'])} | {verdict(r)} |")
    return '\n'.join(lines)


def lab_chart():
    """Presentation projection, preserving stopped tails instead of imputing them."""
    import numpy as np
    original = read('docs/results-v2e-lab-curves.json')
    assert original['source_sha256'] == read('docs/results-v2e.json')['source_tables_sha256']
    full = ROOT / original['source']
    if full.exists():
        assert hashlib.sha256(full.read_bytes()).hexdigest() == original['source_sha256']
        metrics = json.loads(full.read_text())['metrics']
        assert all(metrics[k]['curve'] == v for k, v in original['metrics'].items())
    robustness = read('docs/results-v2f.json')['metrics']
    families = []
    for family, curves in [('N-SIGN', [v for k,v in original['metrics'].items() if ':N-SIGN:' in k]), ('N-STRENGTH', [v['curve'] for k,v in robustness.items() if k.startswith('H0-STR:T1a:N-STRENGTH:')])]:
        grid = sorted(set.union(*[set(p['s'] for p in c) for c in curves]))
        points = []
        missing = []
        for scale in grid:
            values = [p['rate_hz'] for c in curves for p in c if p['s'] == scale]
            if len(values) != len(curves):
                missing.append(dict(s=scale, observed=len(values), missing=len(curves)-len(values)))
                continue
            points.append(dict(s=scale, band=np.percentile(values,[2.5,97.5]).tolist()))
        families.append(dict(family=family,n=len(curves),grid=grid,points=points,missing=missing))
    measured = original['metrics']['H0:T1a:REAL:0']
    assert measured == robustness['H0-STR:T1a:REAL:0']['curve']
    grid_text = ', '.join(str(x) for x in families[0]['grid'])
    same = families[0]['grid'] == families[1]['grid']
    caption = ('Both families used the same registered grid: '+grid_text+'. ' if same else 'Families used different grids; each is drawn on its own grid. ')
    for f in families:
        for m in f['missing']:
            caption += f"{f['family']} at {m['s']}: {m['missing']} stopped tails are missing; the complete-family band ends before that point. "
    caption += 'Bands show the middle 95% of shuffles, not confidence intervals. Lines join observed grid points; no missing observations are filled.'
    protocol = read('profiles/protocol-v2.1.json')
    return dict(measured=measured,families=families,reference_hz=float(re.search(r'>=([0-9.]+) Hz',protocol['H0']['H0a'])[1]),caption=caption,sources={'N-SIGN':original['source'],'N-STRENGTH':'docs/results-v2f.json: metrics H0-STR:T1a:N-STRENGTH:*'},source_sha256=original['source_sha256'])


def outputs():
    r = read('docs/results-v2f.json')
    old = read('docs/results-v2e.json')
    p = read('profiles/protocol-v2.1.json')
    freeze = read('profiles/freeze-v2.1.json')
    measurement = read('docs/measurements-v2f.json')
    runtime = read('apps/play/public/data/runtime.json')
    lab = read('apps/play/public/data/coupling/runtime.json')
    def row(test, family, metric):
        return next(v for v in r['tables'] if (v['test'],v['family'],v['metric']) == (test,family,metric))
    strength = row('H0-STR','N-STRENGTH','H0b')
    fullsign = row('H0-FULL','N-SIGN','H0b-FULL')
    fullstr = row('H0-FULL','N-STRENGTH','H0b-FULL')
    t2str = row('H0-T2','N-STRENGTH','H0b')
    t2a = row('H0-T2','N-STRENGTH','H0a')
    # Every public family conclusion is derived from every registered row.
    family_lines = []
    for block in p['confirmatory']:
        for family in block['families']:
            rr = [v for v in r['tables'] if v['test']==block['test'] and v['family']==family]
            positive = all(verdict(v).startswith('Supports') for v in rr)
            detail = '; '.join(f"{v['metric']}: measured {num(v['real'],v['metric'])} versus null median {num(v['null_median'],v['metric'])}, Holm p {num(v['holm_p'])}, {verdict(v).lower()}" for v in rr)
            family_lines.append(f"{block['test']} ({block['circuit']}), {family}: "+('the stability difference holds under this model. ' if positive else 'the registered stability result did not replicate. ')+detail+'.')
    # These explanations apply to the completed tables, with explicit guardrails
    # against reusing a positive or negative sentence for different future results.
    assert strength['holm_p'] >= .05 and fullsign['holm_p'] < .05 and fullstr['holm_p'] >= .05
    assert t2str['real'] > t2str['null_median'] and t2str['holm_p'] < .05 and t2a['holm_p'] >= .05
    n = {c: f"{g['graph']['N']:,}" for c,g in freeze['graphs'].items()}
    oldrows = [v for v in old['tables'] if v['hypothesis']=='H0' and v['circuit']=='T1a' and v['metric']=='H0b']
    original = "In this model, measured wiring stays calm at couplings where shuffles that keep each neuron's partner counts and signs saturate."
    combined = "A stricter preregistered control that also approximately keeps each neuron's total input strength removes most of that gap."
    limits = 'These results apply only to this simplified model, with no claims about living flies. A non-significant result does not establish equivalence. Escape and walking comparisons remain insufficient.'
    def rate_pair(v):
        return f"{v['family']} {v['null_median']:.2f} Hz (Holm p {num(v['holm_p'])})"
    comparison_rows = [
        dict(graph='T1a',real=strength['real'],earlier=oldrows,strength=strength,verdict='The stricter control removes most of the rate gap; its comparison is not significant.'),
        dict(graph='Full MaleCNS',real=fullsign['real'],earlier=[fullsign],strength=fullstr,verdict='No significant rate difference from the stricter control.'),
        dict(graph='T2',real=t2str['real'],earlier=[row('H0-T2',f,'H0b') for f in ('N-FULL','N-SIGN')],strength=t2str,verdict='Measured wiring is faster than N-STRENGTH, the opposite direction.')
    ]
    comparison_table = '\n'.join(['| Graph | Measured rate | Earlier shuffle medians and Holm p | N-STRENGTH median and Holm p | Verdict |','|---|---:|---|---|---|'] + [f"| {v['graph']} | {v['real']:.2f} Hz | {'; '.join(rate_pair(x) for x in v['earlier'])} | {rate_pair(v['strength'])} | {v['verdict']} |" for v in comparison_rows])
    summary = [f"{v['graph']}: measured {v['real']:.2f} Hz; earlier shuffles: {'; '.join(rate_pair(x) for x in v['earlier'])}; stricter control: {rate_pair(v['strength'])}. {v['verdict']}" for v in comparison_rows]
    gini = {v['family']:v for v in r['exploratory'] if v['test']=='E1' and v['circuit']=='T1a' and v['metric']=='in_strength_gini'}
    mechanism = (f"EXPLORATORY: the earlier shuffles flattened the input-strength distribution in T1a (Gini about {gini['N-SIGN']['null_median']:.2f}, versus {gini['N-SIGN']['real']:.2f} measured), while N-STRENGTH kept it close (about {gini['N-STRENGTH']['null_median']:.2f}). This suggests that, in this model, stability mainly reflects how unevenly input strength is spread across neurons rather than which partners connect. This explanation was not a preregistered mechanism test; the E1 descriptors were preregistered as exploratory.")
    bin_note = 'N-STRENGTH preserves incoming partner counts within sign and contact-count bins; its preservation of total input strength is approximate.'
    sign = next(v for v in oldrows if v['family']=='N-SIGN')
    coupling = next(v['s'] for v in r['metrics']['H0-STR:T1a:REAL:0']['curve'] if v['s']==p['H0']['s'][6])
    lab_caveat = (f"This shuffle keeps each neuron's excitatory and inhibitory partner counts and signs, but not its total input strength. Shuffles that also approximately keep input strength stay almost as calm as measured wiring: in the registered T1a comparison at coupling {coupling}, measured wiring averaged {strength['real']:.2f} Hz, N-SIGN {sign['null_median']:.2f} Hz and N-STRENGTH {strength['null_median']:.2f} Hz (N-STRENGTH Holm p {num(strength['holm_p'])}).")
    lab_heading = 'Measured vs shuffled wiring'
    exp = []
    e1 = [v for v in r['exploratory'] if v['test']=='E1']
    missing = sum(v['missing'] for v in e1)
    leading = [v for v in e1 if v['metric']=='leading_signed_eigenvalue']
    exp.append(f"EXPLORATORY E1: measured leading signed eigenvalues are {num(leading[0]['real'])} for T1a and {num(next(v['real'] for v in leading if v['circuit']=='T2'))} for T2, above every family median; {missing} null eigenvalues did not converge and remain missing. Structure and Spearman associations are descriptive, not a causal mechanism test.")
    for test,label in [('E2a','glutamate treated as excitatory'),('E3-low','lower noise'),('E3-high','higher noise')]:
        a = next(v for v in r['exploratory'] if v['test']==test and v['metric']=='H0a')
        b = next(v for v in r['exploratory'] if v['test']==test and v['metric']=='H0b')
        exp.append(f"EXPLORATORY {test} ({label}): measured rate {num(b['real'])} Hz versus null median {num(b['null_median'])} Hz; measured critical coupling {num(a['real'],'H0a')} versus null median {num(a['null_median'],'H0a')}. Measured rate percentile {num(b['percentile']*100)}%; critical-coupling percentile {num(a['percentile']*100)}%." + (' Both measured and shuffled wiring saturate under this sign assumption.' if test=='E2a' else ''))
    skipped = next(v for v in r['exploratory'] if v['test']=='E2b')
    exp.append('EXPLORATORY E2b: preregistered '+skipped['status']+'. '+skipped['reason'])
    public = dict(dataset_doi=read('archive/raw-records-manifest.json')['reserved_doi'],chart=lab_chart(),calibrated_coupling=runtime['parameters']['s'],lab_seeds={'neural':p['H0']['seeds'][0],'environment':8128},schema='flybench.public-results.v2f',source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['docs/results-v2e.json','docs/results-v2f.json','profiles/protocol-v2.1.json']},original=original,combined=combined,summary=summary,comparison_rows=comparison_rows,comparison_table=comparison_table,mechanism=mechanism,bin_note=bin_note,lab_heading=lab_heading,lab_caveat=lab_caveat,families=family_lines,limitations=limits,exploratory=exp,tables=r['tables'])
    full_table = table(r['tables'])
    paragraphs = original+'\n\n'+combined+'\n\n'+'\n\n'.join(summary)+'\n\n'+bin_note
    figures = '\n'.join(f"![{block['test']} {family} observed rate curve](media/v2f/{block['circuit']}-{family}-curve.png)" for block in p['confirmatory'] for family in block['families'])
    findings = f'''# Robustness findings

Generated from [results-v2f.json](results-v2f.json), the unchanged frozen analysis tables.

## CONFIRMATORY

{paragraphs}

{full_table}

H0a is critical coupling; >0.1 means censored above the tested grid. The stored 0.11 is a rank sentinel, never a measured coupling. H0b and H0b-FULL are whole-graph rates in Hz at coupling 0.039. Bands are descriptive null percentiles, not confidence intervals on an effect. Non-significant outcomes do not establish equivalence. A significant opposite-direction rate does not support the registered stability claim.

''' + '\n'.join('- '+x for x in family_lines) + '\n\n' + figures + '\n\n## EXPLORATORY\n\nDescriptive percentiles and Spearman coefficients only.\n\n' + mechanism+'\n\n'+'\n\n'.join(exp)
    findings += '\n\n### EXPLORATORY assumption tables\n\n| Check | Metric | Real | Null median | 95% null band | Measured percentile |\n|---|---|---:|---:|---|---:|\n'
    for v in r['exploratory']:
        if v['test'] in ('E2a','E3-low','E3-high'):
            m=v['metric']; findings+=f"| EXPLORATORY {v['test']} | {m} | {num(v['real'],m)} | {num(v['null_median'],m)} | {', '.join(num(x,m) for x in v['null_band'])} | {num(v['percentile']*100)}% |\n"
    findings+='\n### EXPLORATORY structure tables\n\n| Circuit | Family | Descriptor | Real | Null median | 95% null band | Percentile | Valid | Missing |\n|---|---|---|---:|---:|---|---:|---:|---:|\n'
    for v in e1:
        findings+=f"| {v['circuit']} | {v['family']} | {v['metric']} | {num(v['real'])} | {num(v['null_median'])} | {', '.join(num(x) for x in v['null_band'])} | {num(v['percentile']*100) if v['percentile'] is not None else 'missing'}% | {v['valid']} | {v['missing']} |\n"
    findings+='\n### EXPLORATORY correlations\n\n| Circuit | Family | Descriptor | Outcome | Pairs | Spearman rho |\n|---|---|---|---|---:|---:|\n'
    for v in r['correlations']:
        findings+=f"| {v['circuit']} | {v['family']} | {v['metric']} | {v['outcome']} | {v['pairs']} | {num(v['rho'])} |\n"
    findings+='\nAll null-distribution and EXPLORATORY scatter figures are in the review archive under evidence/results/figures/. Censored critical couplings share the top rank; constant quantities have missing correlations. No stopped curve tails or failed spectra were filled.\n'
    findings+=f"\n## Compute and limits\n\nElapsed invocation: {r['completion']['invocation_wall_seconds']:.3f} seconds ({r['completion']['invocation_wall_seconds']/3600:.3f} hours). Summed task time: {r['summed_task_wall_seconds']:.3f} seconds. Peak process high-water RSS: {r['peak_task_rss_kib']:,} KiB. Hardware threads: {r['completion']['hardware_threads']}. Worker counts were full graph {p['resource_plan']['full_workers']}, T2 {p['resource_plan']['T2_workers']}, small circuits {p['resource_plan']['small_workers']}, mechanism {p['resource_plan']['mechanism_workers']}. RSS is a process high-water mark, not an isolated incremental allocation for each task.\n\n{limits}\n\nNo scientific protocol deviation or replacement was made. The EXPLORATORY E2b skip and numerical nonconvergence handling were preregistered. Data hashes, task identity checks, synthetic null invariants, censoring and analysis checks passed; no frozen code was patched to obtain these conclusions. The opposite-direction T2 N-STRENGTH outcome is retained.\n\n```sh\nuv run python experiments/v2f_analyze.py --out evidence/V2F/results\nuv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify\nuv run python experiments/v2f_publish.py --check\n```\n"
    def wk(key):return next(x for x in measurement[key] if x['browser']=='webkit')['runs'][0]
    calibration = ', '.join(f"{v['calibratable']}/{v['total']} {v['family']}" for v in old['calibration'] if v['circuit']=='T1b')
    values = dict(original_date=read('docs/preregistration-receipt-v2.json')['push_verified_utc'][:10],robustness_date=read('docs/preregistration-receipt-v2.1.json')['push_observed_utc'][:10],original=original,combined=combined,comparison_table=comparison_table,mechanism=mechanism,bin_note=bin_note,summary=paragraphs,limits=limits,table=full_table,exploratory='\n\n'.join(exp),
        hours=f"{r['completion']['invocation_wall_seconds']/3600:.2f}",threads=str(r['completion']['hardware_threads']),peak=f"{r['peak_task_rss_kib']/1024**2:.2f}",
        before=f"{wk('game_before')['frame_rate_fps']:.1f}",after=f"{wk('game_after')['frame_rate_fps']:.1f}",live=f"{measurement['live_mobile_webkit_fps']:.1f}",labfps=f"{wk('game_final')['coupling'][0]['fps']:.1f}",
        initial=f"{measurement['initial_gzip_bytes']/1e6:.2f}",coupling=f"{measurement['coupling_lazy_gzip_bytes']/1e6:.2f}",lesion=f"{measurement['lesion_lazy_gzip_bytes']/1e6:.2f}",
        game_n=f"{runtime['counts']['N']:,}",lab_n=n['T1a'],full_n=n['FULL'],calibration=calibration)
    manifest=read('archive/raw-records-manifest.json')
    values['dataset_doi']=manifest['reserved_doi']
    values['coupling']=str(coupling)
    template=(ROOT/'docs/readme-v2f.template.md').read_text()
    for key,value in values.items():template=template.replace('{{'+key+'}}',value)
    assert '{{' not in template
    counts=runtime['counts']
    def paragraphs(items):
        return ''.join('<p>'+html.escape(x)+'</p>' for x in items)
    def html_table(markdown):
        rows=[line.strip('|').split('|') for line in markdown.splitlines()]
        return '<div class="table-scroll" role="region" aria-label="Registered graph comparison" tabindex="0"><table><thead><tr>'+''.join('<th scope="col">'+html.escape(v.strip())+'</th>' for v in rows[0])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(v.strip())+'</td>' for v in row)+'</tr>' for row in rows[2:])+'</tbody></table></div>'
    repo='https://github.com/Alpi157/internet-vs-one-fly'
    body=f"""<h1>How it works</h1><p class="lede">Measured wiring. A simplified model. Results you can check.</p>
<section id="real"><h2>What is real here?</h2><p>The connections come from MaleCNS. The game executes {counts['N']:,} neurons and {counts['source_accepted_E']:,} directed connections representing {counts['represented_source_contacts']:,} biological contacts. Original body IDs are recoverable; contacts remain separate from executable weights.</p><p>Every flash comes from a recorded spike. Replay displays recorded observations. It does not invent activity between frames.</p></section>
<section id="model"><h2>The model</h2><p>The model passed the calibration registered in {runtime['protocol_tag']}. Its selected connection strength is {runtime['parameters']['s']}, from the frozen calibration grid. The selection rule is: {html.escape(runtime['selection_rule'])}.</p><p>Uniform current-based LIF neurons use assumed source transmitter signs. Unknown signs are disabled. Feature-level vision supplies size and expansion. A motor decoder receives only neural activity, with no hand coordinates, distance or future collision information. Walking and escape are neural; body physics and takeoff are simplified. The previous motor command drives the current interval.</p><p>Normal rounds preserve neural state. Changing a lab control explicitly resets both simulations with the same noise seed. Display fading smooths recorded spikes only.</p></section>
<section id="finding"><h2>The finding</h2>{paragraphs([original,combined])}<p>Rates at registered connection strength {coupling}, in spikes a second per neuron:</p>{html_table(comparison_table)}{paragraphs([mechanism,bin_note,limits])}<a href="{repo}/blob/main/docs/findings-v2f.md">Full family results and limitations</a></section>
<section id="preregistrations"><h2>Registered before the runs</h2><p>The original protocol was publicly timestamped on {values['original_date']}, tag <a href="{repo}/tree/prereg-v2">prereg-v2</a>. The robustness protocol was publicly timestamped on {values['robustness_date']}, tag <a href="{repo}/tree/prereg-v2.1">prereg-v2.1</a>. Frozen manifests pin code, graph identities, seeds, assumptions and analysis.</p></section>
<section id="verify"><h2>Data and verification</h2><p>The raw-record dataset is <a href="https://doi.org/{values['dataset_doi']}">{values['dataset_doi']}</a>. Download the checksum-pinned archive, then recompute the published tables without simulating new trials.</p><pre tabindex="0" aria-label="Verification commands"><code>uv run python tools/restore_evidence.py --archive /path/to/flybench-raw-records-v2e-v2f.tar.gz
uv run python tools/recompute_v2e.py
uv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify
uv run python experiments/v2f_publish.py --check</code></pre><p>The portable original-results check ignores only recorded hardware metadata. <a href="{repo}/blob/main/README.md">See the README</a> for locked dependencies and the frozen verifier's supported host envelope.</p></section>
<section id="anatomy"><h2>Real anatomy, credited</h2><p>Brain: front view. Nerve cord: underside view. Real MaleCNS neuron skeletons, simplified for display. The fly's right appears on the viewer's left. Display layout bridges are not continuous anatomical projections. Missing coordinates stay missing.</p><p>MaleCNS is published by the Male CNS Connectome project, including FlyEM at HHMI Janelia, Cambridge, MRC LMB and Google Research. Underlying and derived anatomy is <a href="{repo}/blob/main/LICENSE-DATA.md">CC-BY</a>; code is MIT. <a href="https://male-cns.janelia.org/download/">MaleCNS source</a>. <a href="{repo}/blob/main/profiles/anatomy-lock-v1.json">Pinned anatomy sources and hashes</a>.</p></section>
<section id="limitations"><h2>Limitations</h2>{paragraphs([limits])}<p>The strength-preserving comparisons did not replicate the registered stability result. There is no learning, plasticity, realistic biomechanics, human-player study, public verification service or shared score. Scripted bots are engineering evidence, not human usability evidence. Exploratory associations do not establish a mechanism or biological necessity.</p></section>"""
    site='https://alpi157.github.io/internet-vs-one-fly/'
    def page(name,title,content):
        return f'''<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#000000"><title>{title} | Catch the fly</title><meta name="description" content="Measured MaleCNS wiring, a simplified neural model, and registered results you can verify."><meta property="og:title" content="{title} | Catch the fly"><meta property="og:type" content="website"><meta property="og:description" content="Measured wiring. Recorded spikes. Registered comparisons and their limitations."><meta property="og:url" content="{site}{name}"><meta property="og:image" content="{site}og-image.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image"><link rel="icon" href="./favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="./icon-180.png"><link rel="stylesheet" href="./site.css"></head><body><main class="science-page"><header><a class="wordmark" href="./">Catch the fly</a><nav aria-label="Main"><a href="./">Play</a><a href="./?lab=1">Wiring lab</a><a href="./how-it-works.html" aria-current="page">How it works</a><a href="{repo}">Code and data ↗</a></nav></header><a href="./">‹ Back to the game</a><article>{content}</article></main></body></html>\n'''.replace('href="./','href="/internet-vs-one-fly/')
    css=(ROOT/'apps/play/src/style.css').read_text().replace('../public/fonts/','./fonts/')
    css += '\n.science-page article{max-width:1000px;margin:32px auto}.science-page h1{font-size:52px;white-space:normal}.science-page h2{font-size:32px;margin-top:40px}.science-page .lede{font-size:22px}.science-page p{line-height:1.65}.science-page p a{display:inline;min-height:0}.science-page .wordmark{font:900 28px Doto;color:#e9ede6;text-decoration:none}.table-scroll{overflow:auto;border:1px solid #687369;border-radius:14px;margin:24px 0}table{border-collapse:collapse;min-width:800px;font-size:14px}th,td{padding:14px;text-align:left;border-bottom:1px solid #262b27}th{background:#0a0c0a}pre{overflow:auto;padding:20px;border:1px solid #687369;border-radius:14px;font-size:13px}section{scroll-margin-top:20px}@media(max-width:899px){.science-page h1{font-size:34px}.science-page h2{font-size:28px}.science-page article{margin-top:24px}.science-page header{margin-bottom:8px}}\n'
    pages={name:page(name,title,body) for name,title in [('how-it-works.html','How it works'),('model.html','Model and findings'),('preregistration.html','Protocols and findings')]}
    pages['404.html']=page('404.html','Page not found','<h1>Page not found</h1><p>Return to the game or read about the model and its registered results.</p><a href="'+site+'">Play Catch the fly</a>')
    return {'README.md':template,'docs/findings-v2f.md':findings,'apps/play/public/results-v2f.json':json.dumps(public,indent=2,sort_keys=True)+'\n','apps/play/public/site.css':css,**{'apps/play/public/'+name:content for name,content in pages.items()}}



def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for name,text in outputs().items():
        path=ROOT/name
        if args.check:
            if not path.exists() or path.read_text()!=text:raise SystemExit('Public results drift: '+name)
        else:path.write_text(text)
    if args.check:print('PASS: README, findings and game results derive exactly from committed tables and declared metadata')


if __name__=='__main__':main()
