"""Product-only export. Selection rule is fixed before reading candidate outcomes."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gzip,hashlib,json
import numpy as np
from flybench.experiment_v2 import ROOT,read,save,null_graph,parameters,runner
from flybench.analysis_v2 import h0_metrics
from flybench.experiment_v21 import verify_freeze,load_graph
from flybench.encoding_v2 import HandStrikeV2
from experiments.v2d_parity import export
from experiments.v2e_game_export import pack_graph
from flybench.web_export import export_web_graph

SELECTION_RULE='First V2E T1a N-SIGN null in ascending seed order whose s* equals the family median; no other outcome enters selection.'


def run():
    verify_freeze();p=read(ROOT/'profiles/calibration-v2.json')
    candidates=[]
    for path in sorted((ROOT/'evidence/V2E/results/H0').glob('T1a-N-SIGN-*.json.gz')):
        r=read(path);i=r['index'];diag=read(ROOT/'evidence/V2E/results/topology'/f'T1a-N-SIGN-{i:03d}.json')
        candidates.append((diag['seed'],i,h0_metrics(r['data'])['H0a'],path))
    assert len(candidates)==499
    median=float(np.median([v[2] for v in candidates]))
    seed,index,critical,source=next(v for v in sorted(candidates) if v[2]==median)
    g,diag=null_graph('T1a','N-SIGN',index,p)
    expected=read(ROOT/'evidence/V2E/results/topology'/f'T1a-N-SIGN-{index:03d}.json')
    assert diag['seed']==seed and diag['target_sha256']==expected['target_sha256']
    out=ROOT/'apps/play/public/data/coupling';out.mkdir(parents=True,exist_ok=True)
    directory=ROOT/'data/compiled/v2/t1a';params=parameters(.01,.05,2,1)
    export('T1a',directory,out/'runtime.json',params)
    export_web_graph(directory,out/'circuit.webbin')
    transport=pack_graph(out/'circuit.webbin')
    for name in ('runtime.webbin','runtime.webbin.json','circuit.webbin','circuit.webbin.json'):(out/name).unlink(missing_ok=True)
    runtime=read(out/'runtime.json');runtime.pop('intervals');runtime['config']['body_enabled']=False
    runtime.update(graph_identity='c157802c70bfeb71548b71159ff297525136d3d58f31d91e91937fddc738e3d2',transport=transport,
        grid=p['hypotheses']['H0']['s'],null_selection=dict(rule=SELECTION_RULE,seed=seed,index=index,critical_coupling=critical,family_median=median,target_sha256=diag['target_sha256'],source_record=str(source.relative_to(ROOT)),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()),
        protocol_tag='prereg-v2',status='H0 model settings; no threat until Drop the hand',lab_identity=diag['target_sha256'])
    save(out/'runtime.json',runtime)
    (out/'targets.json.gz').write_bytes(gzip.compress(json.dumps(g['targets'].tolist(),separators=(',',':')).encode(),mtime=0))
    import pyarrow.feather as feather
    original=read(ROOT/'apps/play/public/data/brain.json')
    table=feather.read_table(ROOT/'data/raw/body-annotations-male-cns-v1.0-minconf-0.5.feather',columns=['bodyId','somaLocation'])
    coordinates={int(v['bodyId']):v['somaLocation'] for v in table.to_pylist()}
    positions=[coordinates.get(int(body)) for body in g['ids']]
    valid=np.array([v for v in positions if v is not None])[:,[0,2]]
    low=valid.min(axis=0);span=max(valid.max(axis=0)-low)
    groups={}
    for key,indices in runtime['config']['visual'].items():
        for i in indices:groups[i]=key.split('_')[0]
    nodes=[]
    for i,body in enumerate(g['ids']):
        group=groups.get(i,'interior')
        if int(body) in sum(runtime['config']['groups'][:2],[]):group='giant fiber'
        elif int(body) in sum(runtime['config']['groups'][2:],[]):group='walking DNs'
        pos=positions[i]
        nodes.append(dict(index=i,body_id=str(int(body)),group=group,somaLocation=pos,position=None if pos is None else [float((pos[0]-low[0])/span),float((pos[2]-low[1])/span)]))
    save(out/'brain.json',dict(nodes=nodes,missing=sum(n['position'] is None for n in nodes),projection=original['projection'],units=original['units'],source=original['source'],source_sha256=original['source_sha256']))
    cases=[]
    real=load_graph('T1a')
    for scale in (.01,.03,.06):
        for family,graph in [('REAL',real),('N-SIGN',g)]:
            r=runner(graph,parameters(scale,.05,2,1),2027101401)
            total=0
            for _ in range(100):total+=int(r.step(HandStrikeV2(False))['counts'].sum())
            cases.append(dict(family=family,s=scale,intervals=100,total_spikes=total,final_digest=r.digest()))
    save(out/'parity.json',dict(classification='Product parity at H0 settings, not new confirmatory evidence',cases=cases))
    (out/'LICENSE-DATA.md').write_bytes((ROOT/'apps/play/public/data/LICENSE-DATA.md').read_bytes())
    save(out/'HASHES.json',{f.name:dict(bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in out.iterdir() if f.name!='HASHES.json'})
    save(ROOT/'evidence/V2F/game-export.json',dict(selection=runtime['null_selection'],transport=transport,files=read(out/'HASHES.json')))
    print(runtime['null_selection'])

def media(source):
    from PIL import Image
    paths=sorted((source/'hero-frames').glob('*.png'))
    if len(paths)!=60:raise ValueError('Expected 60 actual Playwright recordings')
    frames=[]
    for path in paths:
        frame=Image.open(path).convert('RGB')
        frame=frame.resize((480,round(frame.height*480/frame.width)),Image.Resampling.LANCZOS)
        frames.append(frame.quantize(colors=128))
    output=ROOT/'docs/media/coupling-hero.gif'
    frames[0].save(output,save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=True)
    if output.stat().st_size>5_000_000:raise RuntimeError('Hero exceeds 5 MB')
    (ROOT/'docs/media/coupling-still.png').write_bytes((source/'chromium-1440x900-coupling-0.06.png').read_bytes())
    save(ROOT/'evidence/V2F/media-provenance.json',dict(classification='Recorded browser simulation; no generated neural frames',
        source_directory=str(source),frames=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths],
        output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),width=480,playback_seconds=6,
        timing='60 observed screenshots played at 100 ms each. Browser capture time may exceed playback time; no interpolation.'))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--media-from',type=Path);args=parser.parse_args()
    if args.media_from:media(args.media_from)
    else:run()
