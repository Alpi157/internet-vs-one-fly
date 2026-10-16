"""Measured-coordinate panel layout and anatomical checks, with no simulation."""
import numpy as np
from .anatomy import project

LABEL = 'Composite layout: brain frontal view, VNC ventral view; not a single projection.'


def lookup(xyz, volume):
    scale = volume['scale']
    vox = np.floor(np.asarray(xyz)/(np.array(scale['resolution'])/1000)
                   - scale['voxel_offset']).astype(int)
    valid = np.all((vox >= 0) & (vox < volume['volume'].shape), axis=-1)
    labels = np.zeros(len(vox), dtype=np.uint8)
    labels[valid] = volume['volume'][tuple(vox[valid].T)]
    return labels


def panel_ids(xyz, frame, volumes=None):
    panels = (np.asarray(xyz)[..., frame['split']['axis']]
              >= frame['split']['boundary_um']).astype(np.uint8)
    if volumes is not None:
        brain, vnc = [lookup(xyz, v) != 0 for v in volumes]
        if np.any(brain & vnc):
            raise RuntimeError('STOP: conflicting brain and VNC ROI membership')
        panels[brain] = 0
        panels[vnc] = 1
    return panels


def make_layout(volumes, audit, gap):
    if audit['status'] != 'PASS':
        raise RuntimeError('STOP: anatomical axis gate failed')
    axes = {(r['panel'], r['anatomical_positive']): r for r in audit['axes']}
    lr = audit['left_right']; x = lr['axis']; xs = lr['sign']
    bv = axes['brain', 'ventral']; bp = axes['brain', 'posterior']
    vp = axes['VNC', 'posterior']; vv = axes['VNC', 'ventral']
    if bp['axis'] != vp['axis'] or bp['sign'] != vp['sign']:
        raise RuntimeError('STOP: cervical split axes differ between brain and VNC')
    ap = bp['axis']; sign = bp['sign']
    boundary_rows = []
    for v, name in zip(volumes, ('CV-anterior', 'CV-posterior')):
        label = next(k for k, n in v['names'].items() if n == name)
        points = np.argwhere(v['volume'] == label)
        xyz = (points + np.array(v['scale']['voxel_offset']) + .5)*np.array(v['scale']['resolution'])/1000
        boundary_rows.append((points, xyz))
    anterior, posterior = [r[1] for r in boundary_rows]
    a_exit = float(np.max(anterior[:, ap]*sign) + volumes[0]['scale']['resolution'][ap]/2000)
    p_entry = float(np.min(posterior[:, ap]*sign) - volumes[1]['scale']['resolution'][ap]/2000)
    boundary = (a_exit + p_entry)/2 * sign
    # In the frontal brain panel the connective exits at its ventral outline.
    brain_y = np.max(anterior[:, bv['axis']]*bv['sign'])
    aface = anterior[np.isclose(anterior[:, bv['axis']]*bv['sign'], brain_y)]
    vnc_y = np.min(posterior[:, ap]*sign)
    pface = posterior[np.isclose(posterior[:, ap]*sign, vnc_y)]
    shared = np.intersect1d(aface[:, x], pface[:, x])
    if not len(shared):
        raise RuntimeError('STOP: cervical outlines have no shared horizontal coordinate')
    target = (np.mean(aface[:, x])+np.mean(pface[:, x]))/2
    common_x = float(shared[np.argmin(np.abs(shared-target))])
    anchor_a = np.mean(aface[np.isclose(aface[:, x], common_x)], axis=0)
    anchor_p = np.mean(pface[np.isclose(pface[:, x], common_x)], axis=0)
    offset = float(brain_y + gap - vnc_y)
    frame = dict(schema='flybench.composite-layout.v1', units='micrometres', view=LABEL,
                 horizontal_axis=x, horizontal_sign=xs,
                 panels={'brain': dict(id=0, axes=[x, bv['axis']], signs=[xs, bv['sign']],
                                       projection_axis=bp['axis'], offset_um=[0, 0], view='frontal anterior; dorsal up'),
                         'VNC': dict(id=1, axes=[x, vp['axis']], signs=[xs, vp['sign']],
                                     projection_axis=vv['axis'], offset_um=[0, offset], view='ventral; T1 up')},
                 split=dict(axis=ap, boundary_um=boundary, posterior_sign=sign,
                            rule='Nonzero brain ROI membership assigns brain, including CV-anterior. Nonzero VNC ROI membership assigns VNC, including CV-posterior. Conflicting memberships stop. Unlabeled vertices use the midpoint between the posterior CV-anterior face and anterior CV-posterior face; equality assigns VNC.'),
                 neck=dict(gap_um=gap, vnc_vertical_translation_um=offset,
                           horizontal_translation_um=0, shared_source_x_um=common_x,
                           brain_exit_source_um=anchor_a.tolist(), vnc_entry_source_um=anchor_p.tolist(),
                           brain_cv_posterior_face_um=a_exit, vnc_cv_anterior_face_um=p_entry,
                           anchor_rule='Shared original x column nearest the two face means; brain CV-anterior ventral face and VNC CV-posterior anterior face. No panel horizontal shift.',
                           bridge_label='layout, not anatomy'))
    frame['neck']['brain_exit_display_um'] = project(anchor_a, frame, np.array(0)).tolist()
    frame['neck']['vnc_entry_display_um'] = project(anchor_p, frame, np.array(1)).tolist()
    return frame


def giant_fiber_sanity(body, xyz, parent, soma, volumes, frame):
    """Fixed raw-tree rule recorded in the display profile before inspection."""
    soma = np.asarray(soma)*.008
    nearest = int(np.argmin(np.linalg.norm(xyz-soma, axis=1)))
    neighbors = [[] for _ in parent]
    for i, p in enumerate(parent):
        if p >= 0:
            neighbors[i].append(int(p)); neighbors[p].append(i)
    order = [nearest]; prev = np.full(len(parent), -2, dtype=int); prev[nearest] = -1
    distance = np.zeros(len(parent))
    for i in order:
        for j in neighbors[i]:
            if prev[j] == -2:
                prev[j] = i; distance[j] = distance[i]+np.linalg.norm(xyz[j]-xyz[i]); order.append(j)
    brain = lookup(xyz, volumes[0]) != 0; vnc = (lookup(xyz, volumes[1]) != 0) & (prev != -2)
    if not vnc.any():
        raise RuntimeError(f'STOP: giant fiber {body} soma component does not reach VNC')
    candidates = np.flatnonzero(vnc); endpoint = int(candidates[np.argmin(distance[candidates])])
    trunk = []; i = endpoint
    while i >= 0:
        trunk.append(i); i = int(prev[i])
    trunk = set(trunk); cable = np.zeros(len(parent))
    for i in reversed(order):
        p = prev[i]
        if p >= 0:
            cable[p] += cable[i] + (np.linalg.norm(xyz[i]-xyz[p]) if brain[i] and brain[p] else 0)
    scores = []
    for i in sorted(trunk):
        if not brain[i]: continue
        off = [j for j in neighbors[i] if prev[j] == i and j not in trunk]
        if off:
            score = sum(cable[j]+(np.linalg.norm(xyz[j]-xyz[i]) if brain[j] else 0) for j in off)
            scores.append((float(score), i))
    if not scores: raise RuntimeError(f'STOP: no main dendritic branch candidate for {body}')
    score, branch = max(scores, key=lambda r: (r[0], -r[1]))
    soma_display = project(soma, frame, np.array(0))
    branch_display = project(xyz[branch], frame, np.array(0))
    return dict(body_id=str(body), annotated_soma_source_um=soma.tolist(),
                annotated_soma_display_um=soma_display.tolist(),
                nearest_soma_row=nearest, soma_to_nearest_swc_um=float(np.linalg.norm(xyz[nearest]-soma)),
                branch_row=branch, branch_source_um=xyz[branch].tolist(),
                branch_display_um=branch_display.tolist(), off_trunk_brain_cable_um=score,
                soma_dorsal=bool(soma_display[1] < branch_display[1]),
                dorsal_separation_um=float(branch_display[1]-soma_display[1]),
                rule='Nearest annotated-soma vertex to nearest VNC vertex by cable distance; largest off-trunk brain cable at a brain-ROI trunk branch point. Ties use lowest original row. No sign tuning.')


def lamina_check(volume, frame):
    """Check frontal raster boundaries against official volume/chunk planes."""
    panel = frame['panels']['brain']; axes = panel['axes']; scale = volume['scale']
    rows = []
    for name in ('LA(L)', 'LA(R)'):
        label = next(k for k, n in volume['names'].items() if n == name)
        mask = np.any(volume['volume'] == label, axis=panel['projection_axis'])
        remaining = [a for a in range(3) if a != panel['projection_axis']]
        if remaining != axes: mask = mask.T
        evidence = []
        for dim, axis in enumerate(axes):
            chunk = scale['chunk_sizes'][0][axis]
            for plane in sorted({0, mask.shape[dim], *range(chunk, mask.shape[dim], chunk)}):
                for at, adjacent in ((plane, plane-1), (plane-1, plane)):
                    if not 0 <= at < mask.shape[dim]: continue
                    edge = np.take(mask, at, axis=dim).copy()
                    if 0 <= adjacent < mask.shape[dim]: edge &= ~np.take(mask, adjacent, axis=dim)
                    padded = np.pad(edge.astype(int), 1)
                    starts = np.flatnonzero(np.diff(padded) == 1); ends = np.flatnonzero(np.diff(padded) == -1)
                    run = int(np.max(ends-starts)) if len(starts) else 0
                    if run:
                        evidence.append(dict(axis='xyz'[axis], plane_voxel=int(plane),
                                             type='volume' if plane in (0, mask.shape[dim]) else 'chunk',
                                             longest_run_voxels=run,
                                             longest_run_um=run*scale['resolution'][axes[1-dim]]/1000))
        maximum = max((e['longest_run_um'] for e in evidence), default=0)
        truncated = maximum >= 20
        vox = np.argwhere(volume['volume'] == label)
        rows.append(dict(name=name, label=label, source_voxel_min=vox.min(axis=0).tolist(),
                         source_voxel_max=vox.max(axis=0).tolist(), boundary_runs=evidence,
                         longest_aligned_run_um=maximum, truncated=truncated,
                         flag='truncated at the imaged volume' if truncated else None,
                         default_silhouette=not truncated))
    return dict(rule='In frontal occupancy projection, inspect volume and 64-voxel source chunk boundary planes. Flag a contiguous boundary run of at least 20 micrometres; retain source ROI and contour. Also retain raster inspection preview. This detects aligned clipping, not arbitrary tissue loss inside acquired bounds.',
                rows=rows)
