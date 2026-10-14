from pathlib import Path
from dataclasses import replace
import json
import numpy as np
import pytest
from flybench.kernel import KernelGraph
from flybench.kernel_v2 import KernelStateV2,interval_counts
from flybench.reference import ReferenceGraph
from flybench.reference_v2 import NoiseSpec,ReferenceStateV2
from flybench.model import load_candidate_model_spec
from flybench.runner_v2 import RunnerV2
from flybench.encoding_v2 import HandStrikeV2
from flybench.calibration_v2 import unit_psp,isolated_count

ROOT=Path(__file__).resolve().parents[1]


def spec():
    return load_candidate_model_spec(model_profile_path=ROOT/'profiles/model-v0.1.json',criteria_path=ROOT/'profiles/numerical-criteria-v0.1.json',neural_dt_ms=.5,runtime_synaptic_scale=.039,seed=1)


def test_unit_psp_matches_discrete_reference_and_noise_table():
    graph=ReferenceGraph(np.array([0,0],dtype=np.int64),np.array([],dtype=np.int32),np.array([],dtype=np.float64))
    state=ReferenceStateV2(spec(),graph,NoiseSpec(1,17,0,0.,np.ones(1,dtype=np.bool_)))
    state.pending_inputs[0,0]=1.
    trace=[]
    for _ in range(200):state.step(0.);trace.append(state.voltage[0])
    assert (max(trace),int(np.argmax(trace))+1)==unit_psp()
    table=json.loads((ROOT/'profiles/noise-table-v1.json').read_text())
    for row in table['rows']:
        assert row['w_noise']*table['psp_unit']==pytest.approx(row['kappa'],rel=2e-16)
        assert row['relative_error']<=.1


def test_interval_batch_matches_active_reference_and_reset():
    directory=ROOT/'fixtures/escape-circuit-v1'
    arrays={k:np.load(directory/f'{k}.npy',allow_pickle=False) for k in ('offsets','targets','weights')}
    n=arrays['offsets'].size-1
    noise=NoiseSpec(119,17,1113223450,.3175750723556395,np.ones(n,dtype=np.bool_))
    reference=ReferenceStateV2(spec(),ReferenceGraph(**arrays),noise)
    kernel=KernelStateV2(spec(),KernelGraph(**arrays),noise)
    for j in range(10):
        drive=np.zeros(n);drive[:15]=8. if j<5 else 0.
        expected=np.zeros(n,dtype=np.int64)
        for _ in range(20):expected+=reference.step(drive).spikes
        actual=interval_counts(kernel,drive)
        assert np.array_equal(expected,actual)
        for field in ('voltage','synaptic_current','refractory_until_tick','pending_spikes','pending_inputs'):
            assert np.array_equal(getattr(reference,field),getattr(kernel,field))
    runner=RunnerV2(kernel,np.load(directory/'ids.npy',allow_pickle=False),2.)
    digest=runner.digest();runner.step(HandStrikeV2(False));runner.reset()
    assert runner.digest()==digest


def test_previous_held_command_and_clamp():
    # Use real annotated output IDs on a synthetic disconnected two-neuron graph.
    ids=np.array([10001,11177],dtype=np.uint64)
    graph=KernelGraph(np.array([0,0,0],dtype=np.int64),np.array([],dtype=np.int32),np.array([],dtype=np.float64))
    noise=NoiseSpec(1,17,0,0.,np.ones(2,dtype=np.bool_))
    runner=RunnerV2(KernelStateV2(spec(),graph,noise),ids,2.)
    runner.state.pending_inputs[0,:]=100.
    result=runner.step(HandStrikeV2(False))
    assert result['applied']==(False,0.,0.)
    assert runner.body.x==0.
    assert result['command'][0] and result['command'][1]>0.
    runner.step(HandStrikeV2(False))
    assert runner.body.x>0.


def test_hand_removed_on_neural_boundary_inside_control_interval():
    from flybench.encoding_v2 import encode_hand_v2
    directory=ROOT/'fixtures/escape-circuit-v1'
    arrays={k:np.load(directory/f'{k}.npy',allow_pickle=False) for k in ('offsets','targets','weights')}
    ids=np.load(directory/'ids.npy',allow_pickle=False);n=len(ids)
    noise=NoiseSpec(1,17,0,0.,np.ones(n,dtype=np.bool_))
    runner=RunnerV2(KernelStateV2(spec(),KernelGraph(**arrays),noise),ids,8.,body_enabled=False)
    reference=ReferenceStateV2(spec(),ReferenceGraph(**arrays),noise)
    strike=HandStrikeV2(True,0.,1.5,153.,.05)
    encoded=encode_hand_v2(strike,fly_x=0.,fly_y=0.,heading_x=1.,heading_y=0.,hand_radius=.75,initial_height=8.,dt_ms=.5,input_gain=8.)
    drive=np.zeros(n)
    for key,indices in runner.visual.items():drive[indices]=getattr(encoded,key.lower()+'_drive')
    for step in range(20):reference.step(drive if step<14 else np.zeros(n))
    runner.step(strike)
    assert np.array_equal(runner.state.voltage,reference.voltage)
    assert np.array_equal(runner.state.synaptic_current,reference.synaptic_current)
