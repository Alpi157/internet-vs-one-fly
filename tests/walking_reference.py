"""Offline integration parity vectors for the new game adapter, not science records."""
import json
from pathlib import Path
import struct
import sys
from dataclasses import asdict
from flybench.walking_drive import WalkingDrive
from flybench.game_runner_v28 import GameRunnerV28
from flybench.encoding_v2 import HandStrikeV2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.v2d_dry_run import make_runner
import numpy as np

root=Path(__file__).resolve().parents[1]
p=json.loads((root/'profiles/game-v2.8.json').read_text())
point=p['walking_drive']['selected'] or dict(forward=1.5,turn_sigma=.5,walk_seconds=1.,stop_seconds=.6)
bits=lambda xs:struct.pack('<'+'d'*len(xs),*xs).hex()
drives=[]
for seed in [0,1,88,1001,4294967295]:
 d=WalkingDrive(seed,point)
 drives.append(dict(environment_seed=seed,point=point,intervals=[bits(d.next()+d.snapshot()) for _ in range(3000)]))
rt=json.loads((root/'apps/play/public/data/runtime.json').read_text())
raw=Path(sys.argv[2]).read_bytes();size=struct.unpack('<I',raw[8:12])[0];header=json.loads(raw[12:12+size]);offset=12+size;offset+=(-offset)%8
graph={name:np.frombuffer(raw,dtype=header['sections'][name]['dtype'],count=header['sections'][name]['length'],offset=offset+header['sections'][name]['byte_offset']).copy() for name in ['ids','offsets','targets','weights']}
base=make_runner(graph,graph['targets'],rt['parameters'],77)
r=GameRunnerV28(base.state,graph['ids'],rt['config']['gain'],88,point)
neural=[]
for i in range(400):
 # Includes within-interval visual removal and current persistence after impact.
 strike=HandStrikeV2(True,1.,-1.,(i-100)*10,.025) if 100<=i<150 else HandStrikeV2(False)
 value=r.step(strike,hand_radius=1.4)
 stimulus=asdict(strike);stimulus['hand_radius']=1.4
 neural.append(dict(strike=stimulus,digest=r.digest(),bits=bits(r.walking.snapshot()+[float(v) for v in value['command']]),counts=value['counts'].tolist()))
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True);(out/'reference.json').write_text(json.dumps(dict(point=point,drives=drives,neural=neural)))
