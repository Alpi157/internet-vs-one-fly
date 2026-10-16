"""3D centroid recomputation and explicit contradictory-landmark stop gate."""
import json
from pathlib import Path
import numpy as np
from flybench.anatomy import roi_centroids, anatomical_axis_audit


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


def test_real_landmark_axes_recompute_and_do_not_hide_the_contradiction():
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root/'docs/anatomy-v2g-a02-axis-audit.json').read_text())
    r = report['audit']['left_right']
    recomputed = anatomical_axis_audit(report['centroids'], r['axis'], r['sign'])
    assert recomputed == report['audit']
    assert [(a['panel'], a['anatomical_positive'], a['source_axis'], a['sign'])
            for a in recomputed['axes']] == [
                ('brain', 'posterior', 'z', 1), ('brain', 'ventral', 'y', 1),
                ('VNC', 'posterior', 'z', 1), ('VNC', 'ventral', 'y', 1)]
    assert recomputed['status'] == 'STOP'
    assert [(r['low'], r['high']) for r in recomputed['contradictions']] == [
        ('LTct', 'LegNp(T3)(R)')]
    assert recomputed['contradictions'][0]['signed_separation_um'] < 0
