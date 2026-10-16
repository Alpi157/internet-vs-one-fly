"""Export selected runtime and measured soma positions for local play."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import json
import shutil
import gzip
import struct
import numpy as np
import pyarrow.feather as feather
from experiments.v2d_parity import export
from flybench.graph import write_json
from flybench.web_export import export_web_graph

ROOT=Path(__file__).resolve().parents[1]


def update_anatomy_units(report_path):
    """Metadata-only update, without rerunning calibration, graph export or simulation."""
    report=json.loads(report_path.read_text())
    if report['status']!='CONFIRMED' or report['unit_nm']!=8:
        raise ValueError('Soma units are not confirmed by anatomy comparison')
    for directory in (ROOT/'apps/play/public/data',ROOT/'apps/play/public/data/coupling'):
        path=directory/'brain.json';brain=json.loads(path.read_text())
        original_nodes=brain['nodes']
        brain['units']='Original somaLocation values use 8 nm voxel units, confirmed against official SWC soma/root coordinates; displayed positions remain normalized relative x/z coordinates. Anatomical camera orientation of this legacy map remains unverified. Evidence: docs/anatomy-soma-units.json.'
        if directory.name=='coupling':
            from flybench.experiment_v2 import save as save_compact
            save_compact(path,brain)
        else:write_json(path,brain)
        assert json.loads(path.read_text())['nodes']==original_nodes
        hashes=json.loads((directory/'HASHES.json').read_text())
        hashes['brain.json']=dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        write_json(directory/'HASHES.json',hashes)

def pack_graph(path):
    raw=path.read_bytes();size=struct.unpack('<I',raw[8:12])[0];header=json.loads(raw[12:12+size]);payload=12+size;payload+=(-payload)%8
    def array(name):
        section=header['sections'][name]
        return np.frombuffer(raw,dtype=section['dtype'],count=section['length'],offset=payload+section['byte_offset'])
    ids,offsets,targets,counts,weights=[array(name) for name in ('ids','offsets','targets','counts','weights')]
    packed=bytearray(b'FLYPACK1'+raw[8:12]+raw[12:12+size]);packed.extend(ids.tobytes())
    def varint(n):
        n=int(n)
        if n<0:raise ValueError('negative delta')
        while n>=128:packed.append((n&127)|128);n>>=7
        packed.append(n)
    for degree in np.diff(offsets):varint(degree)
    for source in range(len(ids)):
        prior=0
        for target in targets[offsets[source]:offsets[source+1]]:varint(target-prior);prior=int(target)
    for count in counts:varint(count)
    for source in range(len(ids)):
        a,b=offsets[source:source+2];sign=int(np.sign(weights[a])) if b>a else 0
        if not np.array_equal(weights[a:b],counts[a:b].astype(float)*sign):raise ValueError('weights are not exact source-sign times contacts')
        packed.append(sign+1)
    output=path.with_name('circuit.flygraph.gz');output.write_bytes(gzip.compress(bytes(packed),mtime=0))
    return dict(packed_bytes=output.stat().st_size,unpacked_sha256=hashlib.sha256(raw).hexdigest(),packed_sha256=hashlib.sha256(output.read_bytes()).hexdigest())

def run(fixture=False,selection=None):
    out=ROOT/'apps/play/public/data';out.mkdir(parents=True,exist_ok=True)
    choice=json.loads(selection.read_text()) if selection else None
    if choice and choice['primary_circuit']:
        name=choice['primary_circuit'];params=choice['selected'][name]['parameters'];status='CALIBRATED MODEL / prereg-v2'
    else:
        dry=json.loads((ROOT/'evidence/V2E/dry-run-4/dry-run.json').read_text()) if not fixture else None
        candidates=[] if dry is None else [r for r in dry['rows'] if r['family']=='REAL']
        best=min(candidates,key=lambda r:(-sum(r['aggregate_pass_flags'].values()),sum(v['no_threat']['mean_rate_hz'] for v in r['replicates']))) if candidates else None
        name=best['circuit'] if best else 'fixture';params=best['parameters'] if best else None;status='PROVISIONAL MODEL / no frozen calibration selection'
    directory=ROOT/('fixtures/escape-circuit-v1' if fixture else 'data/compiled/v2/'+name.lower())
    noise=json.loads((ROOT/'profiles/noise-table-v2.json').read_text())
    nr=next(r for r in noise['rows'] if r['kappa']==.05 and r['nu0_hz']==.5)
    params=params or dict(s=.01,kappa=.05,nu0_hz=.5,gain=2,threshold_int=nr['threshold_int'],w_noise=nr['w_noise'])
    export(name,directory,out/'runtime.json',params)
    export_web_graph(directory,out/'circuit.webbin')
    for redundant in ('runtime.webbin','runtime.webbin.json'):(out/redundant).unlink(missing_ok=True)
    runtime=json.loads((out/'runtime.json').read_text());runtime.pop('intervals');runtime['config']['body_enabled']=False
    runtime['status']=status
    runtime['circuit']=name
    runtime['parameters']=params
    runtime['protocol_tag']='prereg-v2' if choice else None
    runtime['selection_rule']='Lowest no-threat mean rate among full-grid passing points, grid-order ties' if choice else 'Most dry-run criteria passed, lowest no-threat rate, grid order; provisional only'
    m=json.loads((directory/'manifest.json').read_text());runtime['graph_identity']=m['semantic_digest']['value'];runtime['counts']=m['graph']
    runtime['profile_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'profiles'/n for n in ('game-v2.json','noise-v2.json','noise-table-v2.json','model-v2d-provisional.json','encoder-v2-draft.json','decoder-v2-draft.json','ports-v2.json','turn-directions-v1.json')]}
    for code in [*sorted((ROOT/'packages/kernel-ts/src').glob('*.ts')),ROOT/'apps/play/src/game.ts']:
        runtime['profile_hashes'][str(code.relative_to(ROOT))]=hashlib.sha256(code.read_bytes()).hexdigest()
    ids=np.load(directory/'ids.npy');coords={}
    if not fixture:
        table=feather.read_table(ROOT/'data/raw/body-annotations-male-cns-v1.0-minconf-0.5.feather',columns=['bodyId','somaLocation'])
        coords={int(r['bodyId']):r['somaLocation'] for r in table.to_pylist()}
    positions=[coords.get(int(body)) for body in ids];valid=[p for p in positions if p is not None]
    # Display x/z projection. Coordinates remain relative, no unverified soma units.
    low=np.min(np.array(valid)[:,[0,2]],axis=0) if valid else np.array([0,0]);high=np.max(np.array(valid)[:,[0,2]],axis=0) if valid else np.array([1,1]);span=max(high-low)
    groups={}
    for key,indices in runtime['config']['visual'].items():
        for i in indices:groups[i]=key.split('_')[0]
    for i,body in enumerate(ids):
        if int(body) in sum(runtime['config']['groups'][:2],[]):groups[i]='giant fiber'
        elif int(body) in sum(runtime['config']['groups'][2:],[]):groups[i]='walking DNs'
    nodes=[dict(index=i,body_id=str(int(body)),group=groups.get(i,'interior'),somaLocation=positions[i],position=None if positions[i] is None else [float((positions[i][0]-low[0])/span),float((positions[i][2]-low[1])/span)]) for i,body in enumerate(ids)]
    brain=dict(nodes=nodes,missing=sum(p is None for p in positions),projection='x horizontal, z vertical; front display convention, anatomical camera orientation unverified',units='Relative positions only. Official page specifies 8 nm for synapse coordinates and SWC skeletons, but does not explicitly specify somaLocation units.',source='https://male-cns.janelia.org/download/',source_sha256='2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2')
    from flybench.nulls import directed_double_edge_swap
    sources=np.repeat(np.arange(len(ids)),np.diff(np.load(directory/'offsets.npy')))
    targets=np.load(directory/'targets.npy')
    scramble=directed_double_edge_swap(sources,targets,swap_count=len(targets),seed=202710159999,maximum_attempt_multiple=100)
    (out/'lab-targets.json.gz').write_bytes(gzip.compress(json.dumps(scramble.targets.tolist(),separators=(',',':')).encode(),mtime=0))
    runtime['lab_identity']=hashlib.sha256(scramble.targets.astype('<i4').tobytes()).hexdigest()
    runtime['lab_seed']=202710159999
    runtime['transport']=pack_graph(out/'circuit.webbin')
    runtime['graph_url']='data/circuit.flygraph.gz'
    (out/'circuit.webbin').unlink()
    (out/'circuit.webbin.json').unlink()
    write_json(out/'runtime.json',runtime);write_json(out/'brain.json',brain)
    (out/'LICENSE-DATA.md').write_text('# MaleCNS data attribution\n\nDerived from MaleCNS v1.0, Janelia FlyEM, CC-BY. Source: https://male-cns.janelia.org/download/ . Original IDs and biological contact counts are preserved. Source and graph hashes appear in runtime.json and HASHES.json. Relative soma x/z positions have unverified units and anatomical orientation.\n')
    shutil.copyfile(ROOT/'profiles/game-v2.json',out/'game.json')
    (ROOT/'apps/play/public/model.html').write_text(f'<!doctype html><meta name="viewport" content="width=device-width"><title>What is real here?</title><h1>What is real here?</h1><p>MaleCNS v1.0 measured wiring, CC-BY. This export executes {runtime["counts"]["N"]} neurons and {runtime["counts"]["source_accepted_E"]} directed connections representing {runtime["counts"]["represented_source_contacts"]} contacts. Uniform LIF neurons, feature-level vision, assumed signs and turn directions, abstract heading-based takeoff. Model status: {status}. No biological superiority claim.</p><p>Unknown signs are disabled. Missing soma positions appear in a labeled group band. Soma units and anatomical camera orientation are unverified; only relative x/z positions are shown.</p><a href="https://male-cns.janelia.org/download/">MaleCNS source and attribution</a>')
    result_copy='H0 shows a model stability difference. H1 and H2 have insufficient calibratable nulls. See the repository README for results and limitations.' if (ROOT/'evidence/V2E/results/FINDINGS.md').exists() else 'Hypothesis results are pending. See the frozen protocol and limitations.'
    (ROOT/'apps/play/public/preregistration.html').write_text('<!doctype html><meta name="viewport" content="width=device-width"><title>Protocol status</title><h1>'+status+'</h1><p>'+result_copy+'</p><a href="https://github.com/Alpi157/internet-vs-one-fly/tree/prereg-v2">Pre-registration</a>')
    hashes={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir() if p.name!='HASHES.json'}
    write_json(out/'HASHES.json',hashes)
    write_json(ROOT/'evidence/V2E/game/export.json',dict(fixture=fixture,parameters=params,graph=runtime['graph_identity'],counts=runtime['counts'],brain_missing=brain['missing'],coordinate_provenance={k:v for k,v in brain.items() if k!='nodes'},files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir()}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fixture',action='store_true');p.add_argument('--selection',type=Path);p.add_argument('--anatomy-units-from',type=Path);a=p.parse_args()
    if a.anatomy_units_from:update_anatomy_units(a.anatomy_units_from)
    else:run(a.fixture,a.selection)
