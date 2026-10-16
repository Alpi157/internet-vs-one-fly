"""3D centroid recomputation and explicit contradictory-landmark stop gate."""
import json
from pathlib import Path
import numpy as np
from flybench.anatomy import roi_centroids, anatomical_axis_audit
from flybench.anatomy import decode_arbors,encode_arbors,project
from flybench.anatomy_layout import lamina_check,panel_ids


def test_composite_fixture_bridge_flags_and_quantization():
    root=Path(__file__).resolve().parents[1]
    f=json.loads((root/'fixtures/anatomy-composite-v1.json').read_text())
    raw=bytes.fromhex(f['hex']);d=decode_arbors(raw)
    assert d['format']=='FLYARB03' and d['panels'].tolist()==f['panels'] and d['bridges'].tolist()==f['bridges']
    assert np.all(np.abs(d['points']-f['points'])<=d['step']*.50001)
    assert encode_arbors(f['ids'],[(np.array(f['points']),[-1,0,1]),(np.empty((0,2)),[])],[[1.,1.],None],[False,True],[0.,0.,10.,30.],[np.array(f['panels']),np.empty(0,np.uint8)],[0,0])==raw


def test_composite_projection_keeps_shared_x_and_uses_two_distinct_axes():
    frame=dict(split=dict(axis=2,boundary_um=10),panels={
        'brain':dict(id=0,axes=[0,1],signs=[1,1],offset_um=[0,0]),
        'VNC':dict(id=1,axes=[0,2],signs=[1,1],offset_um=[0,25])})
    xyz=np.array([[2.,3.,4.],[2.,7.,12.]])
    assert panel_ids(xyz,frame).tolist()==[0,1]
    assert project(xyz,frame).tolist()==[[2,3],[2,37]]


def test_lamina_clipping_detection_flags_only_long_aligned_runs():
    a=np.zeros((40,50,3),np.uint8);a[:3,5:40,:]=37;a[10:13,10:15,:]=38
    v=dict(volume=a,names={37:'LA(L)',38:'LA(R)'},scale=dict(resolution=[1024]*3,chunk_sizes=[[16]*3]))
    report=lamina_check(v,dict(panels={'brain':dict(axes=[0,1],projection_axis=2)}))
    left,right=report['rows'];assert left['truncated'] and not left['default_silhouette']
    assert left['flag']=='truncated at the imaged volume'
    assert not right['truncated'] and right['default_silhouette']


def test_roi_centroids_use_3d_voxel_centres_and_official_offset_resolution():
    volume = np.zeros((5, 6, 7), dtype=np.uint8)
    volume[0:3, 1:5, 2:7] = 4
    volume[4, 5, 0:2] = 9
    scale = dict(resolution=[1024, 1536, 2048], voxel_offset=[10, -2, 5])
    rows = roi_centroids(volume, scale, {4: 'synthetic A', 9: 'synthetic B'})
    for row in rows:
        voxels = np.argwhere(volume == row['label'])
        expected = ((voxels + .5 + scale['voxel_offset'])
                    * np.array(scale['resolution']) / 1000).mean(axis=0)
        assert row['voxels'] == len(voxels)
        assert np.allclose(row['centroid_um'], expected, rtol=0, atol=1e-12)


def test_real_landmark_axes_recompute_under_the_reviewers_amended_rule():
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root/'docs/anatomy-v2g-a02-axis-audit.json').read_text())
    r = report['audit']['left_right']
    recomputed = anatomical_axis_audit(report['centroids'], r['axis'], r['sign'])
    assert recomputed == report['audit']
    assert [(a['panel'], a['anatomical_positive'], a['source_axis'], a['sign'])
            for a in recomputed['axes']] == [
                ('brain', 'posterior', 'z', 1), ('brain', 'ventral', 'y', 1),
                ('VNC', 'posterior', 'z', 1), ('VNC', 'ventral', 'y', 1)]
    assert recomputed['status'] == 'PASS' and not recomputed['contradictions']
    strict=[r for r in recomputed['relations'] if r['panel']=='VNC' and r['anatomical_positive']=='ventral']
    assert len(strict)==7 and all(r['passes'] for r in strict)
    assert not any(r['low']=='LTct' for r in strict)
    assert recomputed['descriptive_LTct']['centroid_um']==next(r['centroid_um'] for r in report['centroids']['VNC'] if r['name']=='LTct')
    # Synthetic negative control: reversing one same-neuromere ordering stops.
    altered=json.loads(json.dumps(report['centroids']))
    ntct=next(r for r in altered['VNC'] if r['name']=='NTct(UTct-T1)(L)')
    ntct['centroid_um'][1]=1000
    assert anatomical_axis_audit(altered)['status']=='STOP'


def test_composite_panel_metadata_silhouettes_and_one_to_one_preview():
    from PIL import Image
    import yaml
    root=Path(__file__).resolve().parents[1];directory=root/'apps/play/public/data/anatomy'
    saved=json.loads((directory/'frame.json').read_text());frame=saved['frame']
    assert frame['panels']['brain']['axes']==[0,1] and frame['panels']['brain']['projection_axis']==2
    assert frame['panels']['VNC']['axes']==[0,2] and frame['panels']['VNC']['projection_axis']==1
    assert all(p['offset_um'][0]==0 and p['signs'][0]==1 for p in frame['panels'].values())
    rois=json.loads((directory/'neuropils.json').read_text())
    assert all(r['panel']==(0 if r['volume']=='brain' else 1) for r in rois['rois'])
    flags={r['name']:r for r in saved['evidence']['lamina']['rows']}
    assert all(r['default_silhouette']==flags[r['name']]['default_silhouette'] for r in rois['rois'] if r['name'] in flags)
    preview=next(p for p in json.loads((root/'docs/media/anatomy/previews.json').read_text()) if p['file']=='T1b-brain-1to1.png')
    assert preview['pixels_per_um']==1 and preview['scale_bar_um']==100
    x0,y0,x1,y1=preview['bounds_um'];image=Image.open(root/'docs/media/anatomy'/preview['file'])
    assert image.size==(int(x1-x0+200),int(y1-y0+200))
    amendment=yaml.safe_load((root/'ledger.yaml').read_text())['v2g_current']['reviewer_amendment_verbatim'].rstrip('\n')
    assert '```text\n'+amendment+'\n```' in (root/'docs/anatomy-v2g-a02-axis-audit.md').read_text()
