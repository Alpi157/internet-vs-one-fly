"""Outcome-independent C-SIMPLE feasibility check, no neural model or data fit."""
import json
from pathlib import Path
from flybench.encoding_v2 import HandStrikeV2, encode_hand_v2
from flybench.graph import write_json

def run(out):
    trajectories=[]
    for _ in range(8):
        trajectories.append([encode_hand_v2(HandStrikeV2(True,0,0,t,.05),fly_x=0,fly_y=0,heading_x=1,heading_y=0,hand_radius=.75,initial_height=8,dt_ms=.5,input_gain=1).size_feature for t in range(0,160,10)])
    assert all(row==trajectories[0] for row in trajectories)
    thresholds=[0,.1,.25,.5,.75,1,2]
    observations=[dict(threshold=t,fraction=sum(any(v>=t for v in row) for row in trajectories)/8) for t in thresholds]
    assert all(r['fraction'] in (0,1) for r in observations)
    write_json(out,dict(status='DESIGN_CONFLICT',identical_trials=8,observations=observations,proof='For deterministic feature sequence f(t) identical on every standard trial, indicator(max(f)>=threshold) is identical on every trial for any real threshold. Its sample mean is 0 or 1. No threshold can match a passing real fraction in [0.2,0.9].',proposed_change='NONE; reviewer decision required'))

if __name__=='__main__':run(Path('evidence/V2D/control-feasibility.json'))
