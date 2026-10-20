"""V2L game-loop vectors, outside every frozen executable."""
import hashlib,json,struct,sys,gzip
from pathlib import Path
import numpy as np
from flybench.game_runner_v28 import GameRunnerV28,WalkingGame
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.v2d_dry_run import make_runner
root=Path(__file__).resolve().parents[1]
p=json.loads((Path(sys.argv[3]) if len(sys.argv)>3 else root/'profiles/game-v2.9.json').read_text());rt=json.loads((root/'apps/play/public/data/runtime.json').read_text())
raw=Path(sys.argv[1]).read_bytes();size=struct.unpack('<I',raw[8:12])[0];header=json.loads(raw[12:12+size]);offset=12+size;offset+=(-offset)%8
graph={name:np.frombuffer(raw,dtype=header['sections'][name]['dtype'],count=header['sections'][name]['length'],offset=offset+header['sections'][name]['byte_offset']).copy() for name in ['ids','offsets','targets','weights']}
bits=lambda xs:struct.pack('<'+'d'*len(xs),*xs).hex()
rows=[]
for seed in [1,7]:
 base=make_runner(graph,graph['targets'],rt['parameters'],seed)
 runner=GameRunnerV28(base.state,graph['ids'],rt['config']['gain'],1000+seed,p['walking_drive']['selected'])
 game=WalkingGame(runner,p,1000+seed);intervals=[]
 for i in range(1000):
  if i in [150,500,800]:
   b=runner.body;game.apply(game.tick,b.x,b.y,[600,299.999,300][[150,500,800].index(i)])
  f=game.step();b=runner.body
  intervals.append(dict(tick=game.tick,bits=bits([b.x,b.y,b.heading_x,b.heading_y,*map(float,f['applied']),*map(float,runner.held),*runner.walking.snapshot(),*game.air_direction,game.air_until]),air=f['air'],onset=f['onset'],counts_sha256=hashlib.sha256(np.array(f['counts'],dtype='<u4').tobytes()).hexdigest(),impact=f['impact']))
 rows.append(dict(seed=seed,intervals=intervals))
Path(sys.argv[2]).write_bytes(gzip.compress(json.dumps(rows,separators=(',',':')).encode(),mtime=0))
