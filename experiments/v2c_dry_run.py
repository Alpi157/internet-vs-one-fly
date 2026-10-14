"""V2C dry run 2: all rows, pipeline and sanity only. Never freezes protocol."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import itertools
import json
import subprocess
import time
from dataclasses import replace
import numpy as np
from flybench.graph import write_json
from flybench.model import load_candidate_model_spec
from flybench.kernel import KernelGraph
from flybench.kernel_v2 import KernelStateV2
from flybench.reference import ReferenceGraph
from flybench.reference_v2 import ReferenceStateV2, NoiseSpec
from flybench.kernel_v2 import interval_counts
from flybench.decoder_v2 import decode_spikes_v2
from flybench.encoding_v2 import HandStrikeV2
from flybench.runner_v2 import RunnerV2, GROUP_NAMES
from flybench.calibration_v2 import isolated_count

ROOT=Path(__file__).resolve().parents[1]


def load_graph(name):
    directory=ROOT/'data/compiled/v2'/name.lower()
    return {k:np.load(directory/f'{k}.npy',allow_pickle=False) for k in ('ids','offsets','targets','weights')}


def make_runner(graph,targets,params,seed,**kwargs):
    spec=load_candidate_model_spec(model_profile_path=ROOT/'profiles/model-v0.1.json',criteria_path=ROOT/'profiles/numerical-criteria-v0.1.json',neural_dt_ms=.5,runtime_synaptic_scale=params['s'],seed=seed)
    noise=NoiseSpec(seed,17,params['threshold_int'],params['w_noise'],np.ones(len(graph['ids']),dtype=np.bool_))
    state=KernelStateV2(spec,KernelGraph(graph['offsets'],targets,graph['weights']),noise)
    return RunnerV2(state,graph['ids'],params['gain'],body_enabled=False,**kwargs)


def trial(graph,targets,params,seed,condition,population=None,output_clamp=False,trace=False):
    runner=make_runner(graph,targets,params,seed,output_clamp=output_clamp)
    counts=np.zeros(len(graph['ids']),dtype=np.int64)
    group_counts=np.zeros(6,dtype=np.int64)
    onset_ticks=[]; moving=0; post_zero=True; hashes=[]
    if condition=='no-threat':
        speed,ax,ay=0.,0.,0.; intervals=2000; impact_tick=None
    else:
        speed,ax,ay=condition
        impact_tick=400+round(8/speed/.5)
        intervals=int((impact_tick*.5+200)/10)
    started=time.perf_counter()
    for ci in range(intervals):
        start_tick=ci*20
        active=impact_tick is not None and 400<=start_tick<=impact_tick
        strike=HandStrikeV2(active,ax,ay,max(0.,(start_tick-400)*.5),speed)
        value=runner.step(strike,population=population)
        counts+=value['counts'];group_counts+=value['group_counts']
        moving+=int(value['command'][1]!=0. or value['command'][2]!=0.)
        if value['onset']:onset_ticks.append(value['tick'])
        if impact_tick is not None and start_tick>impact_tick:post_zero &= value['drive_zero']
        if trace:hashes.append(hashlib.sha256(runner.neural_bytes()).hexdigest())
    wall=time.perf_counter()-started
    seconds=intervals*.01
    return dict(seed=seed,condition=condition,seconds=seconds,impact_tick=impact_tick,
        mean_rate_hz=float(counts.sum()/len(counts)/seconds),
        fraction_neurons_above_150_hz=float(np.mean(counts/seconds>150)),
        group_rates_hz={name:float(group_counts[i]/max(1,len(runner.groups[i]))/seconds) for i,name in enumerate(GROUP_NAMES)},
        escape_counts=len(onset_ticks),escape_onset_ticks=onset_ticks,
        escape_before_impact=impact_tick is not None and any(400<t<impact_tick for t in onset_ticks),
        moving_fraction=moving/intervals,post_impact_drive_zero=post_zero,
        wall_seconds=wall,wall_seconds_per_simulated_second=wall/seconds,
        **({'neural_interval_hashes':hashes} if trace else {}))


def criteria(no,standard):
    all_cal=[no,*standard]
    prob=sum(t['escape_before_impact'] for t in standard)/len(standard)
    values=dict(no_threat_mean_rate_hz=no['mean_rate_hz'],max_calibration_mean_rate_hz=max(t['mean_rate_hz'] for t in all_cal),
        max_fraction_neurons_above_150_hz=max(t['fraction_neurons_above_150_hz'] for t in all_cal),
        decoder_group_active=any(v>0 for v in no['group_rates_hz'].values()),
        moving_fraction=no['moving_fraction'],false_escape_onsets_per_second=no['escape_counts']/no['seconds'],standard_escape_fraction=prob)
    flags=dict(not_silent=values['no_threat_mean_rate_hz']>=.5 and values['decoder_group_active'],
        not_saturated=values['max_calibration_mean_rate_hz']<50 and values['max_fraction_neurons_above_150_hz']<.05,
        spontaneous_movement=.1<=values['moving_fraction']<=.9,
        false_escapes=values['false_escape_onsets_per_second']<=.05,
        escape_standard=.2<=prob<=.9)
    return dict(values=values,pass_flags=flags,passes_all=all(flags.values()))



def reference_checks(out):
    checks=[]
    for name,s in [('T1a',.01),('T1b',.039)]:
     graph=load_graph(name);p=dict(s=s,gain=8,threshold_int=881775520,w_noise=.3175750723556395)
     runner=make_runner(graph,graph['targets'],p,2026092802)
     state=runner.state
     reference=ReferenceStateV2(state.spec,ReferenceGraph(graph['offsets'],graph['targets'],graph['weights']),state.noise)
     drive=np.zeros(len(graph['ids']))
     spikes=0
     for ci in range(20):
      expected=np.zeros(len(graph['ids']),dtype=np.int64)
      for _ in range(20):expected+=reference.step(drive).spikes
      actual=interval_counts(state,drive);assert np.array_equal(actual,expected);spikes+=int(actual.sum())
      for field in ('voltage','synaptic_current','refractory_until_tick','pending_spikes','pending_inputs'):assert np.array_equal(getattr(reference,field),getattr(state,field))
     checks.append(dict(circuit=name,s=s,neural_ticks=400,spikes=spikes,all_interval_states_identical=True,scope='bounded 200 ms active no-threat reference-versus-batched kernel, not proof of all long-trial behavior'))
    rates=(0.,)*6;groups=((),(),(),(),(),(11177,))
    _,speed,_,rates=decode_spikes_v2((11177,),rates,groups,.8187307530779818,.01,.001,.00025,-.01,.02,.005)
    for _ in range(1999):_,speed,_,rates=decode_spikes_v2((),rates,groups,.8187307530779818,.01,.001,.00025,-.01,.02,.005)
    write_json(out/'bug-investigation.json',dict(reference_checks=checks,
     moving_fraction_surprise=dict(single_forward_spike_speed_after_20_s=speed,nonzero=speed!=0.,cause='The reviewer criterion uses exact nonzero commands. An exponential filter has no finite support, so one spike can make movement remain nonzero for the rest of a 20 s trial. This is a decoder/criterion design conflict, not a circuit finding. No deadband was added or outcome tuning performed.',bug_ruled_out='No implementation discrepancy in the bounded reference checks; finite-support absence follows directly from declared filter. Review required.'),
     recurrent_saturation=dict(cause='Strong signed recurrent network at reviewer scale. Bounded scalar reference and batched kernel agree, including noise and propagation. Unknown signs remain zero.',bug_ruled_out='No discrepancy in checked prefix; other long-run or design defects remain possible. Not a model finding.'),
     partial_visual_probe_failure=dict(cause='Some high-activity points have identical aggregate DNp01 counts under isolated visual input. Both populations change DNp01 at other predeclared points, satisfying the requested existential probe.',bug_ruled_out='Field-name mapping tests, reference checks and node runner parity pass. No parameters selected to change this observation.')))


def run(out):
    reference_checks(out)
    profile=json.loads((ROOT/'profiles/calibration-v2-draft.json').read_text())
    noise=json.loads((ROOT/'profiles/noise-table-v1.json').read_text())
    if not (ROOT/'data/compiled/v2/t1b/N-CONTEXT-19.npy').exists():
        subprocess.run([sys.executable,str(ROOT/'experiments/v2c_nulls.py'),'--out',str(out.parent/'p1')],check=True)
    rows=[]; sanity=[]
    subset=profile['dry_run_subset']
    for name in subset['circuits']:
        graph=load_graph(name)
        topologies=[('REAL',0,graph['targets'])]+[(family,ni,np.load(ROOT/'data/compiled/v2'/name.lower()/f'{family}-{ni}.npy',allow_pickle=False)) for family in ('N-FULL','N-CONTEXT') for ni in range(2)]
        for s,nu,gain in itertools.product(subset['runtime_synaptic_scale'],subset['nu0_hz'],subset['input_gain']):
            nr=next(r for r in noise['rows'] if r['kappa']==.05 and r['nu0_hz']==nu)
            params=dict(s=s,kappa=.05,nu0_hz=nu,gain=gain,threshold_int=nr['threshold_int'],w_noise=nr['w_noise'])
            for family,ni,targets in topologies:
                replicates=[]
                for seed in subset['seeds']:
                    no=trial(graph,targets,params,seed,'no-threat')
                    standard=[trial(graph,targets,params,seed+(i+1)*101,(.05,0.,0.)) for i in range(4)]
                    held_conditions=[(.025,0.,0.),(.1,0.,0.),(.05,0.,1.5),(.05,0.,-3.)]
                    held=[trial(graph,targets,params,seed+(i+5)*101,c) for i,c in enumerate(held_conditions)]
                    replicates.append(dict(seed=seed,no_threat=no,standard=standard,held_out_pipeline_only=held,criteria=criteria(no,standard)))
                aggregate_flags={key:all(rep['criteria']['pass_flags'][key] for rep in replicates) for key in replicates[0]['criteria']['pass_flags']}
                standard_fraction=sum(t['escape_before_impact'] for rep in replicates for t in rep['standard'])/8
                aggregate_flags['escape_standard']=.2<=standard_fraction<=.9
                row=dict(circuit=name,family=family,null_index=ni,parameters=params,replicates=replicates,
                    aggregate_pass_flags=aggregate_flags,standard_escape_fraction=standard_fraction,
                    passes_all=all(aggregate_flags.values()),
                    wall_seconds_per_simulated_second=sum(t['wall_seconds'] for rep in replicates for t in [rep['no_threat'],*rep['standard'],*rep['held_out_pipeline_only']])/sum(t['seconds'] for rep in replicates for t in [rep['no_threat'],*rep['standard'],*rep['held_out_pipeline_only']]))
                rows.append(row)
            # Real sanity probes at every declared grid point, no tuning.
            baseline=trial(graph,graph['targets'],params,subset['seeds'][0],(.05,0.,0.),population='NONE',trace=True)
            probes={pop:trial(graph,graph['targets'],params,subset['seeds'][0],(.05,0.,0.),population=pop) for pop in ('LC4','LPLC2')}
            normal=trial(graph,graph['targets'],params,subset['seeds'][0],(.05,0.,0.),trace=True)
            clamp=trial(graph,graph['targets'],params,subset['seeds'][0],(.05,0.,0.),output_clamp=True,trace=True)
            dnp=lambda t: [t['group_rates_hz'][n] for n in ('escape_left','escape_right')]
            sanity.append(dict(circuit=name,parameters=params,dnp01_no_visual=dnp(baseline),dnp01_lc4_only=dnp(probes['LC4']),dnp01_lplc2_only=dnp(probes['LPLC2']),lc4_changes_dnp01=dnp(baseline)!=dnp(probes['LC4']),lplc2_changes_dnp01=dnp(baseline)!=dnp(probes['LPLC2']),after_impact_visual_zero=normal['post_impact_drive_zero'],output_clamp_zero=clamp['escape_counts']==0,output_clamp_neural_hashes_identical=normal['neural_interval_hashes']==clamp['neural_interval_hashes'],normal_neural_interval_hashes=normal['neural_interval_hashes'],clamped_neural_interval_hashes=clamp['neural_interval_hashes']))
            write_json(out/'dry-run.partial.json',dict(rows=rows,sanity=sanity))
            print(name,params,'rows',len(rows),flush=True)
    isolated=[]
    for nr in noise['rows']:
        measured=isolated_count(nr['threshold_int'],nr['w_noise'],noise['seed'],400000)/200
        isolated.append(dict(kappa=nr['kappa'],nu0_hz=nr['nu0_hz'],measured_rate_hz=measured,within_10_percent=abs(measured-nr['nu0_hz'])<=.1*nr['nu0_hz']))
    result=dict(schema='flybench.v2c.dry-run-2',status='PIPELINE_AND_SANITY_ONLY',protocol_frozen=False,hypothesis_results='NONE',
        producer_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        profile_sha256=hashlib.sha256((ROOT/'profiles/calibration-v2-draft.json').read_bytes()).hexdigest(),
        trial_seed_rule='base seed for no-threat; base+(i+1)*101 for four standard; base+(i+5)*101 for four held-out; all use stream 17',
        identities={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [ROOT/'profiles/source-lock.json',ROOT/'profiles/noise-table-v1.json',ROOT/'profiles/ports-v2.json',ROOT/'profiles/turn-directions-v1.json',ROOT/'profiles/encoder-v2-draft.json',ROOT/'profiles/decoder-v2-draft.json',*[ROOT/'src/flybench'/f'{name}.py' for name in ('runner_v2','kernel_v2','reference_v2','encoding_v2','decoder_v2','detmath')]]},
        graph_digests={name:json.loads((ROOT/'data/compiled/v2'/name.lower()/'manifest.json').read_text())['semantic_digest']['value'] for name in subset['circuits']},
        rows=rows,sanity_probes=sanity,isolated_neuron_rates=isolated)
    write_json(out/'dry-run.json',result)
    (out/'dry-run.partial.json').unlink(missing_ok=True)
    lines=['# V2C dry run 2','','Pipeline and sanity only. No H1 or H2 analysis. Protocol remains DRAFT_REVIEW_REQUIRED.','','Every replicate and criterion value is in dry-run.json. Held-out trial observations only verify plumbing. They support no hypothesis claim.','','| Circuit | Family | Null | s | nu0 | gain | Mean Hz range | Move range | False escapes/s range | Standard fraction range | Pass | Wall s/s |','|---|---|---:|---:|---:|---:|---|---|---|---|---|---:|']
    for row in rows:
        p=row['parameters'];v=[rep['criteria']['values'] for rep in row['replicates']]
        extent=lambda key: f"{min(x[key] for x in v):.4g} to {max(x[key] for x in v):.4g}"
        lines.append(f"| {row['circuit']} | {row['family']} | {row['null_index']} | {p['s']} | {p['nu0_hz']} | {p['gain']} | {extent('no_threat_mean_rate_hz')} | {extent('moving_fraction')} | {extent('false_escape_onsets_per_second')} | {extent('standard_escape_fraction')} | {row['passes_all']} | {row['wall_seconds_per_simulated_second']:.5g} |")
    lines+=['',f"Passing subset points: {sum(r['passes_all'] for r in rows)} of {len(rows)}. This subset cannot establish full-grid calibratability.",'','Sanity probes, failures, and bug investigations are recorded in the JSON and the review. No parameter was changed to alter an outcome.']
    (out/'FINDINGS.md').write_text('\n'.join(lines)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);run(a.out)
