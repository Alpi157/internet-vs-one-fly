"""Export scripted v2 headless runner parity cases, including a clone fixture."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from dataclasses import asdict
import json
import hashlib
from flybench.web_export import export_web_graph
from flybench.graph import write_json
from flybench.runner_v2 import RunnerV2
from flybench.encoding_v2 import HandStrikeV2
from experiments.v2d_dry_run import load_graph, make_runner
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def export(name,directory,output,params):
    graph={k:np.load(directory/f'{k}.npy',allow_pickle=False) for k in ('ids','offsets','targets','weights')}
    runner=make_runner(graph,graph['targets'],params,2026092802)
    runner.body_enabled=True
    state=runner.state;spec=state.spec;p=runner.profile
    config=dict(model=dict(runtime_synaptic_scale=spec.runtime_synaptic_scale,current_decay=state._current_decay,voltage_decay=state._voltage_decay,held_drive_factor=state._held_drive_factor,current_coupling_factor=state._current_coupling_factor,rest=spec.rest,reset=spec.reset,threshold=spec.threshold,refractory_ticks=spec.refractory_ticks,delay_ticks=spec.delay_ticks),noise=dict(seed=state.noise.seed,stream_id=17,threshold=state.noise.threshold,current_increment=state.noise.current_increment,population_mask=state.noise.population_mask.tolist()),gain=params['gain'],groups=runner.groups,visual={k:v.tolist() for k,v in runner.visual.items()},body_enabled=True,decoder=dict(decay=float.fromhex(p['rate_filter']['decay_float64_hex']),forward_gain=p['forward_speed']['k_f'],turn_gain=p['turn_rate']['k_t'],minimum_speed=p['forward_speed']['clamp_arena_units_per_ms'][0],maximum_speed=p['forward_speed']['clamp_arena_units_per_ms'][1],maximum_turn_rate=p['turn_rate']['clamp_radians_per_ms'][1]))
    intervals=[]
    # Several scripted strikes, mirrored offsets, variable speeds and removal.
    for ci in range(200):
        start=ci*10
        if 200<=start<=360:
            strike=HandStrikeV2(True,0.,1.5,start-200,.05)
        elif 600<=start<=920:
            strike=HandStrikeV2(True,0.,-1.5,start-600,.025)
        elif 1200<=start<=1280:
            strike=HandStrikeV2(True,0.,0.,start-1200,.1)
        else:strike=HandStrikeV2(False)
        result=runner.step(strike)
        intervals.append(dict(strike=asdict(strike),expected_state_sha256=runner.digest(),expected_command=result['command'],expected_body=asdict(runner.body)))
    output.parent.mkdir(parents=True,exist_ok=True)
    if name!='fixture':export_web_graph(directory,output.with_suffix('.webbin'))
    write_json(output,dict(schema='flybench.v2c.runner-parity',graph=name,parameters=params,rng_algorithm='flybench.u32.v2',config=config,profile_identities={f:hashlib.sha256((ROOT/'profiles'/f).read_bytes()).hexdigest() for f in ('ports-v2.json','turn-directions-v1.json','encoder-v2-draft.json','decoder-v2-draft.json','noise-table-v2.json')},intervals=intervals))
    return dict(graph=name,intervals=200,last_digest=runner.digest())


def run(out):
    noise=json.loads((ROOT/'profiles/noise-table-v2.json').read_text())
    nr=next(r for r in noise['rows'] if r['kappa']==.05 and r['nu0_hz']==.5)
    params=dict(s=.01,gain=2,threshold_int=nr['threshold_int'],w_noise=nr['w_noise'])
    summaries=[export('fixture',ROOT/'fixtures/escape-circuit-v1',ROOT/'packages/kernel-ts/test/fixtures/v2d-runner.json',params)]
    for name in ('T1a','T1b'):
        summaries.append(export(name,ROOT/'data/compiled/v2'/name.lower(),ROOT/'data/compiled/v2'/f'{name.lower()}-v2d-runner.json',params))
    write_json(out/'python-parity.json',dict(status='EXPORTED',cases=summaries))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
