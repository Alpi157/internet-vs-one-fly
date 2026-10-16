"""Data-only anatomy transforms and FLYARB02/03 transport, independent of simulation."""
from pathlib import Path
import struct
import numpy as np

MAGIC = b'FLYARB02'
HEADER = struct.Struct('<8s4I4d')
NEURON = np.dtype([('body', '<u8'), ('first', '<u4'), ('count', '<u4'),
                   ('soma', '<u2', (2,)), ('flags', '<u4')])


def roi_centroids(volume, scale, names):
    """Voxel-centre centroids in original 3D source micrometres.

    Accumulate one X slice at a time, independently of any display projection.
    Offset and resolution are the official precomputed scale metadata.
    """
    counts = np.zeros(256, dtype=np.int64)
    moments = np.zeros((256, 3), dtype=np.float64)
    yy = np.repeat(np.arange(volume.shape[1]) + .5, volume.shape[2])
    zz = np.tile(np.arange(volume.shape[2]) + .5, volume.shape[1])
    for x in range(volume.shape[0]):
        labels = volume[x].ravel()
        c = np.bincount(labels, minlength=256)
        counts += c
        moments[:, 0] += c * (x + .5)
        moments[:, 1] += np.bincount(labels, weights=yy, minlength=256)
        moments[:, 2] += np.bincount(labels, weights=zz, minlength=256)
    rows = []
    for label in np.flatnonzero(counts[1:]) + 1:
        if label not in names:
            raise ValueError(f'Unnamed ROI label: {label}')
        xyz = ((moments[label] / counts[label] + scale['voxel_offset'])
               * np.asarray(scale['resolution']) / 1000)
        rows.append(dict(label=int(label), name=names[label],
                         voxels=int(counts[label]), centroid_um=xyz.tolist()))
    return rows


def anatomical_axis_audit(centroids, left_right_axis=0, left_right_sign=1):
    """Infer axes from the requested landmark sets, then check every ordering.

    Signs come only from set contrasts. No relation is discarded or averaged
    away after assignment. A contradictory individual ordering fails the gate.
    The existing annotated-soma rule supplies the horizontal axis and sign.
    """
    def select(panel, cores):
        rows = [r for r in centroids[panel] if r['name'].split('(')[0] in cores]
        if {r['name'].split('(')[0] for r in rows} != set(cores):
            raise ValueError('Missing required anatomical landmark: ' + panel)
        return rows

    axes = []; relations = []
    def infer(panel, meaning, low, high, available, strict=True):
        contrast = (np.mean([r['centroid_um'] for r in high], axis=0)
                    - np.mean([r['centroid_um'] for r in low], axis=0))
        axis = max(available, key=lambda a: abs(contrast[a]))
        if contrast[axis] == 0:
            raise ValueError('Zero landmark contrast: ' + meaning)
        sign = 1 if contrast[axis] > 0 else -1
        axes.append(dict(panel=panel, anatomical_positive=meaning,
                         source_axis='xyz'[axis], axis=axis, sign=sign,
                         contrast_xyz_um=contrast.tolist(),
                         low_landmarks=[r['name'] for r in low],
                         high_landmarks=[r['name'] for r in high]))
        for a in low if strict else []:
            for b in high:
                delta = sign * (b['centroid_um'][axis] - a['centroid_um'][axis])
                relations.append(dict(panel=panel, anatomical_positive=meaning,
                                      low=a['name'], high=b['name'],
                                      signed_separation_um=float(delta), passes=bool(delta > 0)))
        return axis, sign

    available = [a for a in range(3) if a != left_right_axis]
    ba, _ = infer('brain', 'posterior',
                   select('brain', ('AL', 'aL', 'bL', 'gL', 'EB')),
                   select('brain', ('CA', 'PB')), available)
    bd, bs = infer('brain', 'ventral',
                    select('brain', ('SMP', 'CA', 'PB')),
                    select('brain', ('GNG', 'AL')), [a for a in available if a != ba])
    for a in select('brain', ('aL',)):
        side = a['name'][a['name'].index('('):]
        b = next(r for r in select('brain', ('bL',)) if r['name'] == 'bL' + side)
        delta = bs * (b['centroid_um'][bd] - a['centroid_um'][bd])
        relations.append(dict(panel='brain', anatomical_positive='ventral',
                              low=a['name'], high=b['name'],
                              signed_separation_um=float(delta), passes=bool(delta > 0)))
    legs = select('VNC', ('LegNp',))
    va, _ = infer('VNC', 'posterior', [r for r in legs if '(T1)' in r['name']],
                   [r for r in legs if '(T3)' in r['name']], available)
    vd, vs = infer('VNC', 'ventral', select('VNC', ('NTct', 'WTct', 'HTct', 'IntTct', 'LTct')),
          select('VNC', ('LegNp', 'mVAC')), [a for a in available if a != va], strict=False)
    vnc = {r['name']: r for r in centroids['VNC']}
    for tectulum, segment in (('NTct', 'T1'), ('WTct', 'T2'), ('HTct', 'T3')):
        for side in ('L', 'R'):
            a = vnc[f'{tectulum}(UTct-{segment})({side})']
            b = vnc[f'LegNp({segment})({side})']
            delta = vs * (b['centroid_um'][vd] - a['centroid_um'][vd])
            relations.append(dict(panel='VNC', anatomical_positive='ventral',
                                  low=a['name'], high=b['name'],
                                  signed_separation_um=float(delta), passes=bool(delta > 0)))
    delta = vs * (np.mean([vnc[f'LegNp(T2)({s})']['centroid_um'][vd] for s in ('L', 'R')])
                  - vnc['IntTct']['centroid_um'][vd])
    relations.append(dict(panel='VNC', anatomical_positive='ventral', low='IntTct',
                          high='mean LegNp(T2)(L), LegNp(T2)(R)',
                          signed_separation_um=float(delta), passes=bool(delta > 0)))
    failures = [r for r in relations if not r['passes']]
    return dict(status='STOP' if failures else 'PASS',
                rule='Brain rules unchanged. VNC strict dorsal checks are within-neuromere NTct/T1, WTct/T2 and HTct/T3 by side, plus IntTct against mean bilateral LegNp(T2). LTct is descriptive, intermediate, with no strict rule. Overall tectulum-versus-ventral contrast retained.',
                left_right=dict(source_axis='xyz'[left_right_axis], axis=left_right_axis,
                                sign=left_right_sign, anatomical_positive='fly left; viewer right'),
                axes=axes, relations=relations, contradictions=failures,
                descriptive_LTct=dict(centroid_um=vnc['LTct']['centroid_um'],
                                      interpretation='Lower tectulum; intermediate; no strict ordering gate'))


def read_swc(path):
    data = np.loadtxt(path, comments='#', ndmin=2)
    if data.shape[1] != 7 or not len(data) or not np.isfinite(data).all():
        raise ValueError(f'Invalid SWC: {path}')
    ids, parents = data[:, 0].astype(np.int64), data[:, 6].astype(np.int64)
    if len(set(ids)) != len(ids) or np.any(ids != data[:, 0]) or np.any(parents != data[:, 6]):
        raise ValueError('Nonunique or noninteger SWC identity')
    index = {int(n): i for i, n in enumerate(ids)}
    parent = np.array([-1 if p == -1 else index[int(p)] for p in parents])
    # Every parent chain must terminate; input order is not assumed topological.
    visited = np.zeros(len(ids), np.uint8)
    for start in range(len(ids)):
        chain = []; i = start
        while i != -1 and visited[i] == 0:
            visited[i] = 1; chain.append(i); i = parent[i]
        if i != -1 and visited[i] == 1:
            raise ValueError('SWC parent cycle')
        visited[chain] = 2
    return data[:, 2:5] * .008, parent, data[:, 1].astype(int)


def unbranched_paths(parent):
    children = [[] for _ in parent]
    for i, p in enumerate(parent):
        if p >= 0: children[p].append(i)
    paths = []
    for i, p in enumerate(parent):
        if p >= 0 and len(children[i]) == 1: continue
        if p == -1 and not children[i]: paths.append(np.array([i]))
        for child in children[i]:
            path = [i, child]
            while len(children[path[-1]]) == 1: path.append(children[path[-1]][0])
            paths.append(np.array(path))
    return paths


def simplify_indices(points, tolerance):
    """Iterative Douglas-Peucker; endpoints are immutable, including closed paths."""
    points = np.asarray(points)
    if tolerance < 0: raise ValueError('Negative tolerance')
    keep = {0, len(points)-1}; stack = [(0, len(points)-1)]
    while stack:
        a, b = stack.pop()
        if b <= a+1: continue
        delta = points[b]-points[a]; norm = float(delta @ delta)
        t = np.clip((points[a+1:b]-points[a]) @ delta / norm, 0, 1) if norm else np.zeros(b-a-1)
        distances = np.linalg.norm(points[a+1:b]-(points[a]+t[:, None]*delta), axis=1)
        k = int(np.argmax(distances))
        if distances[k] > tolerance:
            mid = a+1+k; keep.add(mid); stack.extend([(a, mid), (mid, b)])
    return np.array(sorted(keep), dtype=int)


def simplify(points, tolerance):
    return np.asarray(points)[simplify_indices(points,tolerance)]


def prune_terminal_twigs(xyz, parent, threshold, soma_nodes=()):
    """Iteratively remove whole terminal paths shorter than threshold (3D µm).

    Equivalent path-length rule to navis prune_twigs(exact=False, recursive=True),
    with the user-required protection of every root and any explicit SWC soma.
    Returns an ancestor-closed subset of the original vertex rows. No new points.
    """
    if not np.isfinite(threshold) or threshold<0:raise ValueError('Invalid twig threshold')
    n=len(parent);active=np.ones(n,bool);nonroot=parent>=0
    degree=np.bincount(parent[nonroot],minlength=n)
    edge=np.zeros(n);edge[nonroot]=np.linalg.norm(xyz[nonroot]-xyz[parent[nonroot]],axis=1)
    protected=~nonroot
    for soma in soma_nodes:
        i=int(soma)
        while i>=0 and not protected[i]:protected[i]=True;i=int(parent[i])
    rounds=0
    while True:
        remove=[]
        for tip in np.flatnonzero(active & (degree==0) & ~protected):
            chain=[];length=0.;i=int(tip)
            while not protected[i]:
                chain.append(i);length+=edge[i];p=int(parent[i])
                if p<0 or protected[p] or degree[p]!=1:break
                i=p
            if length<threshold:remove.extend(chain)
        if not remove:break
        removed=np.array(remove,dtype=int)
        assert len(np.unique(removed))==len(removed)
        active[removed]=False
        degree-=np.bincount(parent[removed],minlength=n)
        rounds+=1
    assert np.all(active[parent[np.flatnonzero(active & nonroot)]])
    return active,rounds


def cable_and_tips(xyz,parent,active=None):
    active=np.ones(len(parent),bool) if active is None else active
    nonroot=(parent>=0)&active;indices=np.flatnonzero(nonroot)
    if not np.all(active[parent[indices]]):raise ValueError('Missing ancestral path')
    length=float(np.linalg.norm(xyz[indices]-xyz[parent[indices]],axis=1).sum())
    degree=np.bincount(parent[indices],minlength=len(parent))
    return length,int(np.count_nonzero(active & (degree==0) & (parent>=0)))


def simplified_tree(xyz, parent, tolerance, frame, active=None, return_rows=False, preserve_nodes=()):
    active=np.ones(len(parent),bool) if active is None else np.asarray(active,dtype=bool)
    selected_active=np.flatnonzero(active)
    remap=np.full(len(parent),-1,np.int32);remap[selected_active]=np.arange(len(selected_active))
    if np.any((parent[selected_active]>=0)&(remap[parent[selected_active]]<0)):raise ValueError('Pruned tree lacks ancestral path')
    compact_parent=np.array([-1 if parent[i]<0 else remap[parent[i]] for i in selected_active],np.int32)
    compact_xyz=xyz[selected_active]
    if len(selected_active)!=len(parent):
        preserved=[int(remap[i]) for i in preserve_nodes if active[i]]
        points,parents,rows=simplified_tree(compact_xyz,compact_parent,tolerance,frame,return_rows=True,preserve_nodes=preserved)
        result=(points,parents,selected_active[rows])
        return result if return_rows else result[:2]
    children=[[] for _ in parent]
    for i,p in enumerate(parent):
        if p>=0:children[p].append(i)
    keep=np.zeros(len(parent),bool)
    for path in unbranched_paths(parent):
        cuts=sorted({0,len(path)-1,*np.flatnonzero(np.isin(path,preserve_nodes)).tolist()})
        if len(cuts)==1:keep[path[0]]=True
        for a,b in zip(cuts,cuts[1:]):
            indices=np.array([a,b]) if np.isinf(tolerance) else a+simplify_indices(xyz[path[a:b+1]],tolerance)
            keep[path[indices]]=True
    selected=[];parents=[]
    stack=[(int(i),-1) for i in np.flatnonzero(parent==-1)[::-1]]
    while stack:
        i,ancestor=stack.pop()
        if keep[i]:
            selected.append(i);parents.append(ancestor);ancestor=len(selected)-1
        stack.extend((child,ancestor) for child in reversed(children[i]))
    assert len(selected)==int(keep.sum())
    result=(project(xyz[selected],frame),np.array(parents,dtype=np.int32),np.array(selected,dtype=np.int32))
    return result if return_rows else result[:2]


def project(xyz_um, frame, panels=None):
    xyz_um = np.asarray(xyz_um)
    if 'panels' in frame:
        if panels is None:
            panels = xyz_um[..., frame['split']['axis']] >= frame['split']['boundary_um']
        points = np.empty((*xyz_um.shape[:-1], 2), dtype=float)
        for name in ('brain', 'VNC'):
            panel = frame['panels'][name]
            values = xyz_um[..., panel['axes']] * panel['signs'] + panel['offset_um']
            points = np.where((np.asarray(panels) == panel['id'])[..., None], values, points)
        return points
    return xyz_um[..., frame['axes']] * frame['signs']


def decode_segmentation(data, shape, block=(8, 8, 8)):
    """Neuroglancer uint64 compressed_segmentation, one channel, XYZ order.

    Specification: google/neuroglancer/src/sliceview/compressed_segmentation/README.md.
    No third-party codec, resampling or interpretation of labels.
    """
    words = np.frombuffer(data, '<u4')
    if len(words) < 3 or words[0] != 1: raise ValueError('Invalid one-channel segmentation')
    words = words[1:]; shape = np.array(shape); block = np.array(block)
    grid = (shape+block-1)//block; out = np.empty(tuple(shape), np.uint64)
    linear = np.arange(int(np.prod(block)), dtype=np.uint64)
    for z in range(grid[2]):
        for y in range(grid[1]):
            for x in range(grid[0]):
                i = 2*(x+grid[0]*(y+grid[1]*z))
                header, encoded = int(words[i]), int(words[i+1])
                table, bits = header & 0xffffff, header >> 24
                if bits not in (0, 1, 2, 4, 8, 16, 32): raise ValueError('Invalid bits per voxel')
                start = np.array([x,y,z])*block; end = np.minimum(start+block, shape); extent = end-start
                region = tuple(slice(a,b) for a,b in zip(start,end))
                if bits == 0:
                    out[region] = np.uint64(words[table]) | (np.uint64(words[table+1]) << np.uint64(32))
                    continue
                if bits:
                    bit = linear * bits
                    indices = (words[encoded+(bit//32).astype(int)].astype(np.uint64) >> (bit % 32)) & ((1 << bits)-1)
                else: indices = np.zeros(len(linear), dtype=int)
                locations = table+2*indices.astype(int)
                values = words[locations].astype(np.uint64) | (words[locations+1].astype(np.uint64) << 32)
                values = values.reshape(tuple(block), order='F')
                out[region] = values[tuple(slice(0,n) for n in extent)]
    return out


def encode_arbors(ids, trees, somata, missing, bbox, panels=None, soma_panels=None):
    bbox=np.asarray(bbox,dtype=float);low,high=bbox[:2],bbox[2:];step=(high-low)/65535
    if np.any(step<=0):raise ValueError('Degenerate bounding box')
    def quantize(points):
        values=(np.asarray(points)-low)/step
        if np.any(values<-.001) or np.any(values>65535.001):raise ValueError('Coordinate outside bounds')
        return np.rint(values).astype('<u2')
    records=np.zeros(len(ids),NEURON);parents=[];coordinates=[];layout=[];total=0
    for i,body in enumerate(ids):
        points,local_parent=trees[i];local_parent=np.asarray(local_parent,dtype=np.int64)
        if len(points)!=len(local_parent):raise ValueError('Tree length differs')
        indices=np.arange(len(points))
        if np.any((local_parent>=indices)|(local_parent < -1)):raise ValueError('Tree must be topological')
        if missing[i] and len(points):raise ValueError('Missing skeleton has geometry')
        soma=somata[i];flag=int(missing[i])|(2 if soma is None else 0)
        if panels is not None:
            flag |= 4 if soma is not None and soma_panels[i] else 0
            pp=np.asarray(panels[i],dtype=np.uint8)
            if len(pp)!=len(points) or np.any(pp>1):raise ValueError('Invalid panel assignment')
            flags=pp.copy();children=np.flatnonzero(local_parent>=0)
            flags[children] |= (pp[children]!=pp[local_parent[children]]).astype(np.uint8)*2
            layout.append(flags)
        records[i]=(body,total,len(points),[0,0] if soma is None else quantize(soma),flag)
        q=quantize(points) if len(points) else np.empty((0,2),'<u2')
        delta=q.astype(np.int32)
        has_parent=local_parent>=0
        delta[has_parent]-=q[local_parent[has_parent]].astype(np.int32)
        coordinates.append((delta % 65536).astype('<u2'))
        parents.append(np.where(has_parent,indices-local_parent,0).astype('<u4'))
        total+=len(points)
    deltas=np.concatenate(coordinates) if total else np.empty((0,2),'<u2')
    links=np.concatenate(parents) if total else np.empty(0,'<u4')
    return (HEADER.pack(b'FLYARB03' if panels is not None else MAGIC,len(ids),total,total,0,*bbox)+records.tobytes()+links.tobytes()
            +deltas[:,0].astype('<u2').tobytes()+deltas[:,1].astype('<u2').tobytes()
            +(np.concatenate(layout).tobytes() if panels is not None and total else b''))


def decode_arbors(data):
    magic,n,s,p,reserved,*bbox=HEADER.unpack_from(data)
    composite=magic==b'FLYARB03'
    if magic not in (MAGIC,b'FLYARB03') or reserved or s!=p or len(data)!=HEADER.size+n*24+p*(9 if composite else 8):
        raise ValueError('Invalid FLYARB length/header')
    rows=np.frombuffer(data,NEURON,n,HEADER.size)
    links=np.frombuffer(data,'<u4',p,HEADER.size+n*24)
    dx=np.frombuffer(data,'<u2',p,HEADER.size+n*24+p*4)
    dy=np.frombuffer(data,'<u2',p,HEADER.size+n*24+p*6)
    q=np.empty((p,2),np.uint16);parents=np.empty(p,np.int32);expected=0
    for row in rows:
        first,count=int(row['first']),int(row['count'])
        if first!=expected or int(row['flags'])&~(7 if composite else 3) or first+count>p:raise ValueError('Invalid neuron index')
        if int(row['flags'])&1 and count:raise ValueError('Missing skeleton has geometry')
        for i in range(first,first+count):
            link=int(links[i]);parent=i-link if link else -1
            if parent!=-1 and not first<=parent<i:raise ValueError('Parent outside neuron or not topological')
            parents[i]=parent
            q[i,0]=(int(dx[i])+(int(q[parent,0]) if parent>=0 else 0))%65536
            q[i,1]=(int(dy[i])+(int(q[parent,1]) if parent>=0 else 0))%65536
        expected+=count
    if expected!=p:raise ValueError('Neuron index does not cover transport')
    layout=np.frombuffer(data,np.uint8,p,HEADER.size+n*24+p*8) if composite else np.zeros(p,np.uint8)
    if np.any(layout & ~np.uint8(3)):raise ValueError('Invalid layout flags')
    panels=layout&1;bridges=(layout&2)!=0
    children=np.flatnonzero(parents>=0);expected_bridges=np.zeros(p,bool)
    expected_bridges[children]=panels[children]!=panels[parents[children]]
    if not np.array_equal(bridges,expected_bridges):raise ValueError('Bridge flag disagrees with panels')
    low=np.array(bbox[:2]);step=(np.array(bbox[2:])-low)/65535
    if not np.isfinite(bbox).all() or np.any(step<=0):raise ValueError('Invalid bounding box')
    return dict(neurons=rows,parents=parents,quantized=q,points=q*step+low,
                somata=rows['soma']*step+low,bbox=bbox,step=step,panels=panels,bridges=bridges,
                soma_panels=((rows['flags']&4)!=0).astype(np.uint8),format=magic.decode())
