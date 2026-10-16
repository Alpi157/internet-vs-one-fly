"""Real-anatomy transport and topology checks; fixtures need no downloads."""
import gzip
import json
from pathlib import Path
import numpy as np
import pytest
from flybench.anatomy import decode_arbors,encode_arbors,unbranched_paths,simplify,read_swc,decode_segmentation,project,simplified_tree,prune_terminal_twigs,cable_and_tips
from tools.recompute_v2e import compare

ROOT=Path(__file__).resolve().parents[1]


def test_topology_and_simplification(tmp_path):
    swc=tmp_path/'tree.swc'
    swc.write_text('1 0 0 0 0 1 -1\n2 0 64 0 0 1 1\n3 0 128 0 0 1 2\n4 0 128 64 0 1 3\n5 0 128 -64 0 1 3\n6 0 500 0 0 1 -1\n')
    xyz,parent,_=read_swc(swc);paths=unbranched_paths(parent)
    assert [p.tolist() for p in paths]==[[0,1,2],[2,3],[2,4],[5]]
    edges=[(int(a),int(b)) for p in paths for a,b in zip(p,p[1:])]
    assert sorted(edges)==sorted((int(p),i) for i,p in enumerate(parent) if p>=0)
    for path in paths:
        reduced=simplify(xyz[path],1000)
        assert np.array_equal(reduced[[0,-1]],xyz[path[[0,-1]]])
    points,parents=simplified_tree(xyz,parent,1000,dict(axes=[0,2],signs=[1,1]))
    assert len(points)==5 and parents.tolist()==[-1,0,1,1,-1]


def test_codec_fixture():
    f=json.loads((ROOT/'fixtures/anatomy-v1.json').read_text())
    raw=bytes.fromhex(f['hex']);d=decode_arbors(raw)
    assert d['neurons']['body'].tolist()==f['ids']
    assert d['neurons']['flags'].tolist()==[0,3,2]
    assert np.all(np.abs(d['points']-f['points'])<=d['step']*.50001)
    encoded=encode_arbors(f['ids'],[(f['tree_points'],f['parents']),(np.empty((0,2)),[]),(f['isolated'],[-1])],[[.25,1.25],None,None],[False,True,False],f['bbox'])
    assert encoded==raw
    assert d['parents'].tolist()==[-1,0,1,-1]
    with pytest.raises(ValueError):decode_arbors(raw[:-1])


def test_recursive_twig_pruning_strict_length_and_soma():
    xyz=np.array([[0,0,0],[0,0,2],[0,0,4],[1,0,4],[-1,0,4],[0,0,12]],float)
    parent=np.array([-1,0,1,2,2,1])
    unchanged,_=prune_terminal_twigs(xyz,parent,1)
    assert unchanged.all()  # Exactly threshold is retained; criterion is shorter.
    active,rounds=prune_terminal_twigs(xyz,parent,3)
    assert np.flatnonzero(active).tolist()==[0,1,5] and rounds==2
    assert cable_and_tips(xyz,parent,active)==(12.,1)
    protected,_=prune_terminal_twigs(xyz,parent,100,[3])
    assert np.flatnonzero(protected).tolist()==[0,1,2,3]
    frame=dict(axes=[0,2],signs=[1,1])
    points,links,rows=simplified_tree(xyz,parent,1000,frame,protected,True,[3])
    assert 0 in rows and 3 in rows
    assert np.array_equal(points,project(xyz[rows],frame))
    assert set(rows)<=set(np.flatnonzero(protected))


def test_twig_threshold_uses_cable_not_tip_distance():
    xyz=np.array([[0,0,0],[10,0,0],[10,10,0],[0,10,0],[0,0,1]],float)
    parent=np.array([-1,0,1,2,3])
    assert np.linalg.norm(xyz[-1]-xyz[0])==1
    active,_=prune_terminal_twigs(xyz,parent,20)
    assert active.all()  # Long folded path, despite adjacent root and tip.


def test_every_kept_vertex_is_an_original_vertex_and_parent_is_ancestor():
    rng=np.random.default_rng(782)
    parent=np.array([-1,*[int(rng.integers(i)) for i in range(1,150)]])
    xyz=rng.normal(size=(150,3))*20
    active,_=prune_terminal_twigs(xyz,parent,35,[20])
    frame=dict(axes=[0,2],signs=[1,1])
    points,links,rows=simplified_tree(xyz,parent,.5,frame,active,True,[20])
    assert np.array_equal(points,project(xyz[rows],frame))
    assert len(set(rows))==len(rows) and active[rows].all()
    assert 0 in rows and 20 in rows
    for i,p in enumerate(links):
        source_parent=int(parent[rows[i]])
        if p<0:assert source_parent==-1;continue
        while source_parent!=rows[p]:
            assert source_parent>=0 and active[source_parent]
            source_parent=int(parent[source_parent])


def test_compressed_segmentation_fixture():
    # One channel, two blocks, one 1-bit codebook including a >32-bit label.
    words=np.array([1, (1<<24)|6, 4, 10, 0, 0b10101010, 0, 7,0,9,1, 13,0],'<u4')
    decoded=decode_segmentation(words.tobytes(),(4,2,1),(2,2,1))
    assert decoded.shape==(4,2,1)
    assert decoded[:2,:,0].tolist()==[[7,7],[4294967305,4294967305]]
    assert np.all(decoded[2:]==13)


def test_recompute_ignores_only_hardware():
    a={'hardware':{'platform':'A','hardware_threads':24},'tables':[{'real':2.65}],'raw_input_sha256':{'x':'abc'}}
    b={**a,'hardware':{'platform':'B','hardware_threads':2}}
    compare(a,b)
    with pytest.raises(ValueError):compare(a,{**b,'tables':[{'real':3}]})
    with pytest.raises(ValueError):compare(a,{**b,'raw_input_sha256':{}})


def test_committed_assets_order_quantization_missing_and_orientation():
    manifest=json.loads((ROOT/'apps/play/public/data/anatomy/manifest.json').read_text())
    sources=json.loads((ROOT/'profiles/anatomy-lock-v1.json').read_text())['inputs']
    missing={r['url'].rsplit('/',1)[-1].removesuffix('.swc') for r in sources if r['url'].endswith('.swc') and r.get('http_status')==404}
    for asset in manifest['assets']:
        d=decode_arbors(gzip.decompress((ROOT/'apps/play/public/data/anatomy'/asset['file']).read_bytes()))
        brain=json.loads((ROOT/'apps/play/public/data'/('coupling/brain.json' if asset['circuit']=='T1a' else 'brain.json')).read_text())
        ids=[int(n['body_id']) for n in brain['nodes']]
        assert d['neurons']['body'].tolist()==ids
        absent=[str(int(r['body'])) for r in d['neurons'] if r['flags']&1]
        assert set(absent)==set(map(str,ids))&missing==set(asset['missing_skeletons'])
        assert asset['bytes']<=asset['budget_bytes']
        assert asset['highlighted_twig_um']==(6 if asset['lod']=='phone' else 3)
        retention=json.loads(gzip.decompress((ROOT/'apps/play/public/data/anatomy'/asset['retention']['file']).read_bytes()))
        assert len(retention['neurons'])==len(ids)
        assert all(r['kept_cable_um']<=r['original_cable_um']+1e-6 for r in retention['neurons'] if not r['missing'])
        assert asset['maximum_quantization_error_um']<=max(asset['quantization_step_um'])/2+1e-7
        assert np.array_equal(np.rint((d['points']-np.array(d['bbox'][:2]))/d['step']).astype(np.uint16),d['quantized'])
    frame=json.loads((ROOT/'apps/play/public/data/anatomy/frame.json').read_text())
    assert all(v['fraction']>.5 for v in frame['evidence']['soma_side_majority'].values())
    for side in ('R','L'):
        points=np.array([r['xyz_um'] for r in frame['evidence']['annotated_somata'] if r['somaSide']==side])
        x=project(points,frame['frame'])[:,0];mid=frame['evidence']['soma_side_midline_um']
        fraction=float(np.mean(x<mid if side=='R' else x>mid))
        assert fraction>.5 and fraction==frame['evidence']['soma_side_majority'][side]['fraction']
    assert frame['evidence']['axis_audit']['audit']['status']=='PASS'
    assert all(r['soma_dorsal'] for r in frame['evidence']['giant_fiber_sanity']['neurons'])
    neck=frame['frame']['neck'];a=neck['brain_exit_display_um'];b=neck['vnc_entry_display_um']
    assert abs(a[0]-b[0])<1e-9 and abs(b[1]-a[1]-12)<1e-9
    rois=json.loads((ROOT/'apps/play/public/data/anatomy/neuropils.json').read_text())
    assert 1<=rois['voxel_size_um']<=2 and rois['simplification_tolerance_um']<=1.5
    assert not rois['missing_roi_names'] and all(r['name'] for r in rois['rois'])
