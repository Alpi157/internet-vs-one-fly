"""a02 game-current vectors; no frozen model or registered record is changed."""
import gzip
import json
from pathlib import Path
import struct
import sys
from flybench.walking_drive import WalkingDrive

profiles=json.loads(Path(sys.argv[1]).read_text())
rows=[]
for label,profile in profiles.items():
    point=profile['walking_drive']['selected']
    for seed in [0,1,88,1001,4294967295]:
        drive=WalkingDrive(seed,point)
        rows.append(dict(preset=label,point=point,seed=seed,intervals=[struct.pack('<10d',*(drive.next()+drive.snapshot())).hex() for _ in range(3000)]))
Path(sys.argv[2]).write_bytes(gzip.compress(json.dumps(rows,separators=(',',':')).encode(),mtime=0))
