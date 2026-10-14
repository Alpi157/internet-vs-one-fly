"""Descriptive C-NOISE-DEC plumbing evidence at the provisional point, not H2."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
from experiments.v2d_dry_run import load_graph,make_runner
from flybench.noise_v2 import measure_decoder_rates,decoder_noise_trial
from flybench.graph import write_json

def run():
    noise=json.loads(Path('profiles/noise-table-v2.json').read_text())
    nr=next(r for r in noise['rows'] if r['kappa']==.05 and r['nu0_hz']==.5)
    p=dict(s=.01,gain=2,kappa=.05,nu0_hz=.5,threshold_int=nr['threshold_int'],w_noise=nr['w_noise'])
    graph=load_graph('T1a');runner=make_runner(graph,graph['targets'],p,2026092802)
    rates=measure_decoder_rates(runner)
    trial=decoder_noise_trial(runner.groups,rates,2026092802,2000,runner.profile)
    counts=[sum(r['group_counts'][i] for r in trial['records']) for i in range(6)]
    observed=[n/max(1,len(g))/20 for n,g in zip(counts,runner.groups,strict=True)]
    write_json(Path('evidence/V2D/noise-control.json'),dict(status='PIPELINE_ONLY_NOT_H2',parameters=p,network_stream=17,control_stream=29,seconds=20,network_group_rates_hz=rates,control_group_rates_hz=observed,expected_control_group_rates_hz=rates,counts=counts,seed=2026092802,rule='Independent Bernoulli spikes per output neuron per 0.5 ms tick. Finite sample rates need not equal expected rates exactly. No network in the control.'))

if __name__=='__main__':run()
