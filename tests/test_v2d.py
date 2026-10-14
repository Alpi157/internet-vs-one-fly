import json
import math
from pathlib import Path
import numpy as np
from flybench.noise_v2 import interior_mask, decoder_noise_trial
from flybench.decoder_v2 import decode_spikes_v2
from flybench.analysis_v2 import segment_bouts
from flybench.reference_v2 import NoiseSpec, ReferenceStateV2
from flybench.reference import ReferenceGraph
from flybench.kernel_v2 import KernelStateV2
from flybench.kernel import KernelGraph
from flybench.model import load_candidate_model_spec

ROOT = Path(__file__).resolve().parents[1]


def test_no_noise_on_any_ports_including_unknown_and_reference_parity():
    ports=json.loads((ROOT/'profiles/ports-v2.json').read_text())['groups']
    output=[int(e['body_id']) for g in ports.values() for e in g]
    visual=json.loads((ROOT/'profiles/visual-ports-sides-v1.json').read_text())['populations']
    visual_ids=[int(v) for pop in visual.values() for side in ('left','right') for v in pop[f'{side}_body_ids_decimal']]
    # Real port IDs plus a fixture interior sentinel, not a biological mapping.
    ids=np.array(sorted(set(output+visual_ids))+[2**63],dtype=np.uint64)
    mask=interior_mask(ids)
    assert not mask[:-1].any() and mask[-1]
    n=len(ids);offsets=np.zeros(n+1,dtype=np.int64);targets=np.array([],dtype=np.int32);weights=np.array([],dtype=np.float64)
    spec=load_candidate_model_spec(model_profile_path=ROOT/'profiles/model-v0.1.json',criteria_path=ROOT/'profiles/numerical-criteria-v0.1.json',neural_dt_ms=.5,runtime_synaptic_scale=.01,seed=1)
    noise=NoiseSpec(1,17,2**32,1.,mask)
    ref=ReferenceStateV2(spec,ReferenceGraph(offsets,targets,weights),noise)
    kernel=KernelStateV2(spec,KernelGraph(offsets,targets,weights),noise)
    for _ in range(100):
        a=ref.step(0);b=kernel.step(0)
        assert np.array_equal(a.spikes,b.spikes)
        assert np.array_equal(ref.voltage,kernel.voltage)
        assert np.array_equal(ref.synaptic_current,kernel.synaptic_current)
        assert not ref.synaptic_current[:-1].any()
    assert ref.synaptic_current[-1]>0


def test_single_spike_movement_has_analytical_bound():
    p=json.loads((ROOT/'profiles/decoder-v2-draft.json').read_text())
    d=float.fromhex(p['rate_filter']['decay_float64_hex'])
    # Worst case: one neuron group, forward gain .001. At j silent intervals
    # speed <= .001*(1-d)/.01*d**j, hence at most floor(log(T/A)/log(d))+1 moving intervals.
    amplitude=.001*(1-d)/.01
    bound=math.floor(math.log(.002/amplitude)/math.log(d))+1
    groups=((),(),(),(),(),(1,));rates=(0.,)*6;moving=0
    for ci in range(bound+20):
        _,speed,turn,rates=decode_spikes_v2((1,) if ci==0 else (),rates,groups,d,.01,.001,.00025,-.01,.02,.005)
        moving+=abs(speed)>=.002 or abs(turn)>=.0005
    assert moving==bound
    assert bound*10==120
    segments=segment_bouts([dict(tick=20,applied=[False,.002,0]),dict(tick=40,applied=[False,0,-.0005]),dict(tick=60,applied=[False,.001999,.000499])])['segments']
    assert [(s['moving'],s['duration_ms']) for s in segments]==[(True,20),(False,10)]


def test_decoder_control_repeats_and_zero_rates_are_silent():
    p=json.loads((ROOT/'profiles/decoder-v2-draft.json').read_text())
    groups=((1,),(2,),(3,),(4,),(5,),(6,))
    a=decoder_noise_trial(groups,[10.]*6,41,100,p)
    assert a==decoder_noise_trial(groups,[10.]*6,41,100,p)
    silent=decoder_noise_trial(groups,[0.]*6,41,100,p)
    assert all(not any(r['applied']) for r in silent['records'])
    assert a['stream']==29
