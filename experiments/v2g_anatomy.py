"""Acquire and export real anatomy only. No simulation and no UI changes."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import json
import gzip
import time
import numpy as np
from flybench.anatomy_sources import SWC, ROIS, fetch_many, chunk_paths
from flybench.anatomy import read_swc, unbranched_paths, simplify, simplified_tree, project, decode_segmentation, encode_arbors, decode_arbors, prune_terminal_twigs, cable_and_tips, roi_centroids, anatomical_axis_audit

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'apps/play/public/data/anatomy'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def circuits():
    result = {}
    for name in ('T1a','T1b'):
        directory=ROOT/'data/compiled/v2'/name.lower()
        manifest=json.loads((directory/'manifest.json').read_text())
        ids_file=directory/'ids.npy'
        assert hashlib.sha256(ids_file.read_bytes()).hexdigest()==manifest['arrays']['ids']['sha256']
        ids = np.load(ids_file)
        brain = json.loads((ROOT/'apps/play/public/data'/('coupling/brain.json' if name=='T1a' else 'brain.json')).read_text())
        assert ids.tolist() == [int(n['body_id']) for n in brain['nodes']]
        runtime=json.loads((ROOT/'apps/play/public/data'/('coupling/runtime.json' if name=='T1a' else 'runtime.json')).read_text())
        assert runtime['graph_identity']==manifest['semantic_digest']['value']
        result[name] = (ids, brain)
    return result


def acquire():
    # Metadata must exist, and names must be supplied by its own label property.
    metadata = fetch_many(ROOT, [roi+'/'+n for roi in ROIS for n in ('info','segment_properties/info')])
    if any(r.get('http_status') for r in metadata): raise RuntimeError('STOP: documented ROI metadata unavailable')
    existing=ROOT/'profiles/anatomy-lock-v1.json'
    pinned=json.loads(existing.read_text()) if existing.exists() else None
    def check_pinned(rows):
        if pinned is None:return
        expected={r['url']:r for r in pinned['inputs']}
        for row in rows:
            prior=expected[row['url']]
            if any(row.get(k)!=prior.get(k) for k in ('bytes','sha256','http_status')):
                raise RuntimeError('STOP: anatomy source changed from pinned identity: '+row['url'])
    check_pinned(metadata)
    for roi in ROIS:
        p=json.loads((ROOT/'data/anatomy/raw'/roi/'segment_properties/info').read_text())
        label=next(v for v in p['inline']['properties'] if v['type']=='label')
        if len(label['values']) != len(p['inline']['ids']) or not all(label['values']):
            raise RuntimeError('STOP: missing official ROI label names')
    ids=sorted(set(int(n) for ids,_ in circuits().values() for n in ids))
    names=[SWC+str(body)+'.swc' for body in ids]
    names += [name for roi in ROIS for name,*_ in chunk_paths(ROOT,roi)]
    rows=fetch_many(ROOT,names)
    annotation=json.loads((ROOT/'profiles/source-lock.json').read_text())['files'][0]
    path=ROOT/'data/raw'/annotation['filename']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==annotation['observed_sha256']
    rows.append(dict(url=annotation['official_url'],bytes=annotation['observed_bytes'],sha256=annotation['observed_sha256'],retrieved_utc=annotation['acquired_at_utc'],cache_path=str(path.relative_to(ROOT))))
    check_pinned(rows)
    if pinned is not None:
        assert {r['url'] for r in rows+metadata}=={r['url'] for r in pinned['inputs']}
        save(ROOT/'evidence/V2G/sources/reacquisition.json',dict(status='PASS',inputs=rows+metadata))
        print('PASS: pinned identities reacquired; committed lock and retrieval dates preserved',flush=True)
        return
    save(ROOT/'profiles/anatomy-lock-v1.json',dict(schema='flybench.anatomy-sources.v1',
        documentation='https://male-cns.janelia.org/download/',license='CC-BY-4.0',
        swc_units_nm=8,roi_scale_nm=1024,maximum_concurrency=8,
        absent_roi_chunks='HTTP 404 is recorded explicitly. Neuroglancer precomputed absent volume chunks contain background; no named ROI is added there.',
        inputs=sorted(rows+metadata,key=lambda r:r['url'])))
    print('PASS: source acquisition and identities recorded',flush=True)


def volumes():
    result=[]
    lock=json.loads((ROOT/'profiles/anatomy-lock-v1.json').read_text())
    inputs={r['url']:r for r in lock['inputs']}
    from flybench.anatomy_sources import BASE
    for roi in ROIS:
        chunks=list(chunk_paths(ROOT,roi)); scale=chunks[0][3]
        metadata=json.loads((ROOT/'data/anatomy/raw'/roi/'segment_properties/info').read_text())['inline']
        names=dict(zip(map(int,metadata['ids']),next(p['values'] for p in metadata['properties'] if p['type']=='label')))
        cache=ROOT/'data/anatomy'/Path(roi).name
        dest=cache.with_suffix('.npy')
        volume=np.lib.format.open_memmap(dest,mode='w+',dtype=np.uint8,shape=tuple(scale['size']))
        volume[:]=0; missing=0; observed=set()
        for index,(name,begin,end,_) in enumerate(chunks):
            row=inputs[BASE+name]
            if row.get('http_status')==404:
                missing+=1; continue
            path=ROOT/row['cache_path']; data=path.read_bytes()
            assert hashlib.sha256(data).hexdigest()==row['sha256']
            decoded=decode_segmentation(data,np.array(end)-begin,scale['compressed_segmentation_block_size'])
            labels=set(map(int,np.unique(decoded)))-{0}; observed.update(labels)
            if labels-set(names): raise RuntimeError('STOP: ROI labels without official names: '+str(labels-set(names)))
            volume[tuple(slice(a,b) for a,b in zip(begin,end))]=decoded.astype(np.uint8)
        volume.flush()
        weights=(volume!=0).sum(axis=(0,1)); total=int(weights.sum())
        centroid=[]
        for axis in range(3):
            mass=(volume!=0).sum(axis=tuple(a for a in range(3) if a!=axis))
            coords=(np.arange(volume.shape[axis])+scale['voxel_offset'][axis]+.5)*scale['resolution'][axis]/1000
            centroid.append(float(mass@coords/total))
        result.append(dict(roi=roi,scale=scale,names=names,volume=volume,centroid=centroid,
                           observed=sorted(observed),absent_background_chunks=missing,total_chunks=len(chunks)))
        print('Decoded',roi,'labels',len(observed),'absent background chunks',missing,flush=True)
    return result


def annotations():
    import pyarrow.feather as feather
    path=ROOT/'data/raw/body-annotations-male-cns-v1.0-minconf-0.5.feather'
    return {int(r['bodyId']):r for r in feather.read_table(path,columns=['bodyId','somaLocation','somaSide','instance']).to_pylist()}


def audit_frame():
    """Outcome-neutral landmark gate. It never re-exports any display asset."""
    verify_pinned_inputs()
    centroids = {}
    for panel, v in zip(('brain', 'VNC'), volumes()):
        centroids[panel] = roi_centroids(v['volume'], v['scale'], v['names'])
    prior = json.loads((OUT/'frame.json').read_text())
    frame = prior['frame']
    audit = anatomical_axis_audit(centroids, frame['axes'][0], frame['signs'][0])
    report = dict(schema='flybench.anatomical-axis-audit.v1',
                  source_lock_sha256=hashlib.sha256((ROOT/'profiles/anatomy-lock-v1.json').read_bytes()).hexdigest(),
                  scale_um=1.024, coordinate_definition='Original source XYZ in micrometres, using occupied voxel centres; not display coordinates.',
                  centroids=centroids, audit=audit,
                  existing_soma_side_evidence=prior['evidence']['soma_side_majority'])
    path = ROOT/'evidence/V2G/a02/axis-audit.json'
    save(path, report)
    for row in audit['axes']:
        print(row['panel'],row['anatomical_positive'],row['source_axis'],row['sign'],flush=True)
    if audit['contradictions']:
        for failure in audit['contradictions']:
            print('CONTRADICTION', json.dumps(failure,sort_keys=True),flush=True)
        raise RuntimeError('STOP: contradictory anatomical landmark ordering; see evidence/V2G/a02/axis-audit.json. No assets re-exported.')
    print('PASS: anatomical landmark axis gate',flush=True)
    return report


def verify_pinned_inputs():
    inputs=json.loads((ROOT/'profiles/anatomy-lock-v1.json').read_text())['inputs']
    for row in inputs:
        if row.get('http_status')==404:continue
        path=ROOT/row['cache_path']
        assert path.stat().st_size==row['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],row['url']
    return inputs


def display_frame(volumes, annotation, skeletons):
    sides={side:np.array([r['somaLocation'] for body,r in annotation.items() if body in skeletons and r['somaSide']==side and r['somaLocation'] is not None])*.008 for side in ('R','L')}
    right,left=sides['R'],sides['L']; effect=(left.mean(axis=0)-right.mean(axis=0))/np.maximum(np.std(np.concatenate([right,left]),axis=0),1e-12)
    lr=int(np.argmax(np.abs(effect))); lr_sign=1 if effect[lr]>0 else -1
    separation=np.array(volumes[1]['centroid'])-volumes[0]['centroid']
    dv=max((a for a in range(3) if a!=lr),key=lambda a:abs(separation[a]))
    dv_sign=1 if separation[dv]>0 else -1
    frame=dict(axes=[lr,dv],signs=[lr_sign,dv_sign],projection_axis=next(a for a in range(3) if a not in (lr,dv)),
               units='micrometres',y_direction='down; brain above VNC',view='frontal anterior; fly right on viewer left')
    mid=float((np.median(right[:,lr])+np.median(left[:,lr]))/2)*lr_sign
    majority={side:dict(n=len(values),fraction=float(np.mean(values[:,lr]*lr_sign<mid if side=='R' else values[:,lr]*lr_sign>mid))) for side,values in sides.items()}
    assert all(v['fraction']>.5 for v in majority.values()),'Soma-side majority fails'
    anchors=[]
    for body in (10001,10010,10763,11288,11332,12348):
        xyz,parent,_=skeletons[body]; medians=[]; counts=[];xyz_medians=[]
        for volume in volumes:
            scale=volume['scale']; vox=np.floor(xyz/(np.array(scale['resolution'])/1000)-scale['voxel_offset']).astype(int)
            valid=np.all((vox>=0)&(vox<volume['volume'].shape),axis=1)
            selected=np.zeros(len(xyz),bool)
            selected[valid]=volume['volume'][tuple(vox[valid].T)]!=0
            assert selected.any(),f'Anchor {body} misses '+volume['roi']
            medians.append(float(np.median(project(xyz[selected],frame)[:,1]))); counts.append(int(selected.sum()))
            xyz_medians.append(np.median(xyz[selected],axis=0).tolist())
        assert medians[0]<medians[1],f'Brain-above-VNC fails for {body}'
        anchors.append(dict(body_id=str(body),instance=annotation[body]['instance'],brain_median_y_um=medians[0],vnc_median_y_um=medians[1],brain_median_xyz_um=xyz_medians[0],vnc_median_xyz_um=xyz_medians[1],brain_nodes=counts[0],vnc_nodes=counts[1]))
    return frame,dict(soma_side_majority=majority,soma_side_midline_um=mid,soma_axis_effect=effect.tolist(),
                      annotated_somata=[dict(body_id=str(body),somaSide=r['somaSide'],xyz_um=(np.array(r['somaLocation'])*.008).tolist()) for body,r in annotation.items() if body in skeletons and r['somaSide'] in ('R','L') and r['somaLocation'] is not None],
                      roi_centroids_um={v['roi']:v['centroid'] for v in volumes},anchors=anchors)


def soma_units(annotation,skeletons):
    rows=[]
    for body,(xyz,parent,types) in skeletons.items():
        soma=annotation.get(body,{}).get('somaLocation')
        if soma is None:continue
        candidates=np.flatnonzero(types==1)
        method='SWC type 1 soma'
        if not len(candidates):candidates=np.flatnonzero(parent==-1);method='SWC root (not necessarily soma)'
        # All root candidates are retained; nearest root is an explicit comparison.
        raw=np.array(soma,float);i=candidates[np.argmin(np.linalg.norm(xyz[candidates]-raw*.008,axis=1))]
        rows.append(dict(body_id=str(body),somaLocation=raw.tolist(),swc_um=xyz[i].tolist(),method=method,deviation_um=float(np.linalg.norm(xyz[i]-raw*.008))))
    a=np.array([r['somaLocation'] for r in rows]);b=np.array([r['swc_um'] for r in rows])
    correlation=[float(np.corrcoef(a[:,i],b[:,i])[0,1]) for i in range(3)]
    slope=float((a*b).sum()/(a*a).sum())
    errors={str(unit):float(np.sqrt(np.mean((a*unit/1000-b)**2))) for unit in (1,8,1000)}
    confirmed=min(errors,key=errors.get)=='8' and abs(slope/.008-1)<.1
    return dict(status='CONFIRMED' if confirmed else 'UNCONFIRMED',unit_nm=8 if confirmed else None,
                compared_bodies=len(rows),correlation_xyz=correlation,pearson_all_coordinates=float(np.corrcoef(a.ravel(),b.ravel())[0,1]),
                fitted_um_per_annotation_unit=slope,rms_deviation_um_by_unit_nm=errors,
                maximum_root_or_soma_deviation_um=max(r['deviation_um'] for r in rows),
                caveat='SWC roots need not be somata; deviations are measured disagreement, not quantization error. Correlation alone cannot identify units; unit hypotheses also compare absolute coordinate magnitudes.',comparisons=rows)


def contours(mask, scale, frame, tolerance=1.0):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    if not mask.any():return []
    axes=frame['axes']; resolution=np.array(scale['resolution'])/1000;offset=scale['voxel_offset']
    x=(np.arange(mask.shape[0]+2)+offset[axes[0]]-.5)*resolution[axes[0]]
    y=(np.arange(mask.shape[1]+2)+offset[axes[1]]-.5)*resolution[axes[1]]
    fig,ax=plt.subplots(); cs=ax.contour(x,y,np.pad(mask,1).T.astype(float),levels=[.5]);paths=[]
    for vertices,codes in zip(cs.allsegs[0],cs.allkinds[0]):
        if codes is None:pieces=[vertices]
        else:
            indices=list(np.flatnonzero(codes==1))+[len(codes)]
            pieces=[vertices[a:b] for a,b in zip(indices,indices[1:])]
        for piece in pieces:
            if len(piece)>=3:paths.append(simplify(piece*frame['signs'],tolerance).tolist())
    plt.close(fig);return paths


def roi_group(name, volume):
    core=name.split('(')[0]
    if volume=='VNC':return 'VNC leg neuropil' if core=='LegNp' else 'other'
    if core in ('ME','AME','LA','LO','LOP'):return 'optic lobe'
    if core in ('CA','PED',"a'L",'aL',"b'L",'bL','gL'):return 'mushroom body'
    if core in ('EB','FB','NO','PB'):return 'central complex'
    if core=='AL':return 'antennal lobe'
    if core in ('GNG','PRW','SAD'):return 'SEZ'
    return 'central brain' if core not in ('CV-anterior','CRN') else 'other'


def export_rois(volumes,frame):
    rois=[]; shape=np.max([v['scale']['size'] for v in volumes],axis=0)
    union=np.zeros(tuple(shape[frame['axes']]),bool)
    for v in volumes:
        name='brain' if v is volumes[0] else 'VNC'; volume=v['volume']; scale=v['scale']
        for label in v['observed']:
            mask=np.any(volume==label,axis=frame['projection_axis'])
            # np.any retains original axis order; the display axes can differ.
            remaining=[a for a in range(3) if a!=frame['projection_axis']]
            if remaining!=frame['axes']:mask=mask.T
            union[tuple(slice(0,n) for n in mask.shape)] |= mask
            rois.append(dict(volume=name,label=label,name=v['names'][label],group=roi_group(v['names'][label],name),contours_um=contours(mask,scale,frame)))
        print('Projected',name,flush=True)
    result=dict(schema='flybench.neuropil-outlines.v1',frame=frame,voxel_size_um=1.024,simplification_tolerance_um=1.0,
                projection='Frontal maximum occupancy projection of each label separately; overlaps retained',rois=rois,
                missing_roi_names=[],union_silhouette_um=contours(union,volumes[0]['scale'],frame),
                sparse_chunks=[dict(source=v['roi'],absent_background_chunks=v['absent_background_chunks'],total_chunks=v['total_chunks']) for v in volumes])
    save(OUT/'neuropils.json',result);return result


def named_port_ids():
    profile=json.loads((ROOT/'profiles/anatomy-display-v1.json').read_text())
    return {int(row['body_id']) for name in profile['named_ports_sources'] for rows in json.loads((ROOT/name).read_text())['groups'].values() for row in rows}


def display_group(node,ports):
    return 'named ports' if node['group']=='interior' and int(node['body_id']) in ports else node['group']


def retention_summary(rows):
    result={}
    for group in sorted({r['group'] for r in rows}):
        selected=[r for r in rows if r['group']==group]
        values=[r['kept_cable_fraction'] for r in selected if r['kept_cable_fraction'] is not None]
        result[group]=dict(neurons=len(selected),defined_cable_fractions=len(values),
                           median_kept_cable_fraction=float(np.median(values)) if values else None,
                           minimum_kept_cable_fraction=min(values) if values else None)
    return result


def export_arbors(circuit, ids, brain, skeletons, frame, bbox, lod):
    profile=json.loads((ROOT/'profiles/anatomy-display-v1.json').read_text());settings=profile[lod]
    tolerance=settings['douglas_peucker_um'];highlighted=settings['highlighted_twig_um'];interior=settings['interior_twig_um']
    budget=settings[circuit+'_budget_bytes'];ports=named_port_ids();attempts=[]
    started=time.perf_counter()
    while True:
        trees=[];somata=[];missing=[];records=[];interior_max_cable=0.
        for node,body in zip(brain['nodes'],ids):
            body=int(body);is_missing=body not in skeletons;missing.append(is_missing)
            soma=node['somaLocation'];somata.append(None if soma is None else project(np.array(soma)*.008,frame))
            group=display_group(node,ports);threshold=interior if group=='interior' else highlighted
            if is_missing:
                trees.append((np.empty((0,2)),np.empty(0,np.int32)))
                records.append(dict(body_id=str(body),group=group,missing=True,source_rows=[],original_cable_um=None,kept_cable_um=None,kept_cable_fraction=None,original_tips=None,kept_tips=None))
                continue
            xyz,parent,types=skeletons[body];soma_nodes=np.flatnonzero(types==1)
            active,rounds=prune_terminal_twigs(xyz,parent,threshold,soma_nodes)
            positions,links,rows=simplified_tree(xyz,parent,tolerance,frame,active,return_rows=True,preserve_nodes=soma_nodes)
            # Every transport vertex is selected directly from the original SWC.
            assert np.array_equal(positions,project(xyz[rows],frame))
            assert active[rows].all() and np.all(np.isin(np.flatnonzero(parent==-1),rows))
            assert np.all(np.isin(soma_nodes,rows))
            original_length,original_tips=cable_and_tips(xyz,parent)
            pruned_length,pruned_tips=cable_and_tips(xyz,parent,active)
            kept_length,kept_tips=cable_and_tips(xyz[rows],links)
            assert kept_tips==pruned_tips and kept_length<=pruned_length+1e-6
            if group=='interior':interior_max_cable=max(interior_max_cable,original_length)
            trees.append((positions,links))
            records.append(dict(body_id=str(body),group=group,missing=False,twig_threshold_um=threshold,prune_rounds=rounds,
                original_vertices=len(xyz),pruned_vertices=int(active.sum()),kept_vertices=len(rows),
                original_cable_um=original_length,pruned_cable_um=pruned_length,kept_cable_um=kept_length,
                kept_cable_fraction=kept_length/original_length if original_length else None,
                original_tips=original_tips,pruned_tips=pruned_tips,kept_tips=kept_tips,
                source_rows=rows.tolist(),selected_original_vertices_sha256=hashlib.sha256(xyz[rows].astype('<f8').tobytes()).hexdigest()))
        raw=encode_arbors(ids,trees,somata,missing,bbox);packed=gzip.compress(raw,mtime=0)
        attempt=dict(highlighted_twig_um=highlighted,interior_twig_um=interior,douglas_peucker_um=tolerance,bytes=len(packed),budget_bytes=budget,passes=len(packed)<=budget)
        attempts.append(attempt);print(circuit,lod,json.dumps(attempt),flush=True)
        if len(packed)<=budget:break
        if interior>interior_max_cable:
            save(ROOT/'evidence/V2G/SIZE-STOP.json',dict(circuit=circuit,lod=lod,attempts=attempts,reason='Budgets still fail after every removable interior twig is gone. Highlighted thresholds unchanged.'))
            raise RuntimeError('STOP: display assets cannot fit without exceeding protected-group limits')
        interior+=profile['interior_threshold_step_um']
    name=f'{circuit.lower()}-{lod}.arbors.gz';(OUT/name).write_bytes(packed)
    decoded=decode_arbors(raw);assert decoded['neurons']['body'].tolist()==ids.tolist()
    original=np.concatenate([tree[0] for tree in trees])
    assert np.all(np.abs(decoded['points']-original)<=decoded['step']*.50001)
    maximum=float(np.max(np.abs(decoded['points']-original)))
    retention=dict(schema='flybench.anatomy-retention.v1',circuit=circuit,lod=lod,attempts=attempts,
                   cable_definition='3D micrometres. Pruned cable follows original edges; kept cable is the final simplified 3D tree. Tip counts exclude isolated roots. Quantization is separate.',
                   groups=retention_summary(records),neurons=records,original_vertex_membership_check='PASS for every exported vertex')
    retention_name=f'{circuit.lower()}-{lod}.retention.json.gz'
    retention_bytes=gzip.compress((json.dumps(retention,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0)
    (OUT/retention_name).write_bytes(retention_bytes)
    return dict(file=name,circuit=circuit,lod=lod,bytes=len(packed),uncompressed_bytes=len(raw),budget_bytes=budget,
                sha256=hashlib.sha256(packed).hexdigest(),uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
                tolerance_um=tolerance,highlighted_twig_um=highlighted,interior_twig_um=interior,attempts=attempts,
                neurons=len(ids),segments=len(decoded['points']),points=len(decoded['points']),
                graph_identity=json.loads((ROOT/'apps/play/public/data'/('coupling/runtime.json' if circuit=='T1a' else 'runtime.json')).read_text())['graph_identity'],
                ordered_body_ids_sha256=hashlib.sha256(ids.astype('<u8').tobytes()).hexdigest(),
                missing_skeletons=[str(int(body)) for body,flag in zip(ids,missing) if flag],
                missing_somata=[node['body_id'] for node in brain['nodes'] if node['somaLocation'] is None],
                quantization_step_um=decoded['step'].tolist(),maximum_quantization_error_um=maximum,
                retention=dict(file=retention_name,bytes=len(retention_bytes),sha256=hashlib.sha256(retention_bytes).hexdigest(),groups=retention['groups']),
                export_wall_seconds=time.perf_counter()-started)


def build(arbors_only=False):
    # Never regenerate the mislabeled a01 frame while the anatomical gate fails.
    audit_frame()
    inputs=verify_pinned_inputs()
    OUT.mkdir(parents=True,exist_ok=True);v=None if arbors_only else volumes(); annotation=annotations();c=circuits();skeletons={}
    for row in inputs:
        if not row['url'].endswith('.swc') or row.get('http_status')==404:continue
        path=ROOT/row['cache_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        body=int(path.stem);cache=ROOT/'data/anatomy/parsed'/f'{body}.npz'
        if cache.exists():
            with np.load(cache,allow_pickle=False) as parsed:
                assert str(parsed['source_sha256'])==row['sha256']
                skeletons[body]=(parsed['xyz'],parsed['parent'],parsed['types'])
        else:
            skeletons[body]=read_swc(path);cache.parent.mkdir(parents=True,exist_ok=True)
            xyz,parent,types=skeletons[body]
            np.savez(cache,xyz=xyz,parent=parent,types=types,source_sha256=row['sha256'])
    if arbors_only:
        saved=json.loads((OUT/'frame.json').read_text());frame,orientation=saved['frame'],saved['evidence']
    else:frame,orientation=display_frame(v,annotation,skeletons)
    units=soma_units(annotation,skeletons);save(ROOT/'docs/anatomy-soma-units.json',units)
    save(OUT/'frame.json',dict(frame=frame,evidence=orientation))
    roi=json.loads((OUT/'neuropils.json').read_text()) if arbors_only else export_rois(v,frame)
    all_ids={int(body) for ids,_ in c.values() for body in ids}
    points=np.concatenate([project(xyz,frame) for xyz,_,_ in skeletons.values()]+[project(np.array(r['somaLocation'])*.008,frame)[None,:] for body,r in annotation.items() if body in all_ids and r['somaLocation'] is not None])
    bbox=np.concatenate([points.min(axis=0),points.max(axis=0)]).tolist()
    assets=[]
    for circuit,(ids,brain) in c.items():
        for lod in ('phone','desktop'):
            asset=export_arbors(circuit,ids,brain,skeletons,frame,bbox,lod)
            assets.append(asset)
    manifest=dict(schema='flybench.anatomy-assets.v1',frame=frame,bounding_box_um=bbox,
                  source_lock_sha256=hashlib.sha256((ROOT/'profiles/anatomy-lock-v1.json').read_bytes()).hexdigest(),display_profile_sha256=hashlib.sha256((ROOT/'profiles/anatomy-display-v1.json').read_bytes()).hexdigest(),assets=assets,
                  roi_count=len(roi['rois']),missing_roi_names=[],soma_units_report='docs/anatomy-soma-units.json')
    save(OUT/'manifest.json',manifest)
    preview(manifest,roi,c)
    pruning_previews(manifest,c,skeletons)
    save(OUT/'HASHES.json',{p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in OUT.iterdir() if p.is_file() and p.name!='HASHES.json'})


def preview(manifest,roi,circuits):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    dest=ROOT/'docs/media/anatomy';dest.mkdir(parents=True,exist_ok=True)
    colors={'LC4':'#0072b2','LPLC2':'#e69f00','giant fiber':'#cc79a7','walking DNs':'#009e73','interior':'#596474'}
    for name,circuit in [('neuropils',None),('T1b-arbors','T1b'),('giant-fiber','T1b'),('T1a-arbors','T1a')]:
        fig,ax=plt.subplots(figsize=(8,10),facecolor='black');ax.set_facecolor('black')
        paths=[p for r in roi['rois'] for p in r['contours_um']]
        ax.add_collection(LineCollection(paths,colors='#cc28ad',linewidths=.4,alpha=.65))
        if circuit:
            asset=next(a for a in manifest['assets'] if a['circuit']==circuit and a['lod']=='desktop')
            d=decode_arbors(gzip.decompress((OUT/asset['file']).read_bytes()));brain=circuits[circuit][1]
            for group in ['interior',*[g for g in colors if g!='interior']]:
                paths=[]
                for i,node in enumerate(brain['nodes']):
                    if node['group']!=group or (name=='giant-fiber' and group!='giant fiber'):continue
                    row=d['neurons'][i]
                    for j in range(row['first'],row['first']+row['count']):
                        parent=int(d['parents'][j]);paths.append(d['points'][[j,parent if parent>=0 else j]])
                ax.add_collection(LineCollection(paths,colors=colors[group],linewidths=.25 if group=='interior' else .8,alpha=.06 if group=='interior' else .8,label=group))
            ax.legend(loc='upper right',facecolor='black',labelcolor='white',fontsize=8)
        bbox=manifest['bounding_box_um'];ax.set_xlim(bbox[0]-10,bbox[2]+10);ax.set_ylim(bbox[3]+10,bbox[1]-10)
        if name=='giant-fiber':
            selected=[]
            for i,node in enumerate(brain['nodes']):
                if node['group']=='giant fiber':
                    row=d['neurons'][i];a=int(row['first']);b=a+int(row['count']);selected.append(d['points'][a:b])
            p=np.concatenate(selected);low=p.min(axis=0)-15;high=p.max(axis=0)+15;ax.set_xlim(low[0],high[0]);ax.set_ylim(high[1],low[1])
        x0,x1=ax.get_xlim();bottom,top=ax.get_ylim();sx=x0+10;sy=bottom-20
        ax.plot([sx,sx+100],[sy,sy],color='white',lw=2);ax.text(sx,sy-8,'100 µm',color='white',fontsize=9)
        ax.set_aspect('equal');ax.tick_params(colors='white');ax.set_xlabel('Frontal horizontal (µm)',color='white');ax.set_ylabel('Dorsal to ventral (µm)',color='white');ax.set_title(name+' · measured MaleCNS anatomy',color='white');fig.tight_layout();fig.savefig(dest/(name+'.png'),dpi=140);plt.close(fig)


def pruning_previews(manifest,circuits,skeletons):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    directory=ROOT/'docs/media/anatomy';selection=[]
    brain=circuits['T1b'][1]
    for group in ('giant fiber','LC4','LPLC2'):
        node=min((n for n in brain['nodes'] if n['group']==group),key=lambda n:int(n['body_id']))
        body=int(node['body_id']);xyz,parent,_=skeletons[body];raw=project(xyz,manifest['frame'])
        low=raw.min(axis=0)-15;high=raw.max(axis=0)+15
        if high[0]-low[0]<140:
            mid=(low[0]+high[0])/2;low[0]=mid-70;high[0]=mid+70
        height=min(12,max(3,4*(high[1]-low[1])/(high[0]-low[0])+1))
        fig,axes=plt.subplots(1,3,figsize=(12,height),facecolor='black')
        for ax,label in zip(axes,('raw','desktop','phone')):
            if label=='raw':points,links=raw,parent;subtitle='raw SWC'
            else:
                asset=next(a for a in manifest['assets'] if a['circuit']=='T1b' and a['lod']==label)
                d=decode_arbors(gzip.decompress((OUT/asset['file']).read_bytes()));index=next(i for i,n in enumerate(brain['nodes']) if n['body_id']==str(body))
                row=d['neurons'][index];first=int(row['first']);end=first+int(row['count'])
                points=d['points'][first:end];links=d['parents'][first:end].copy();links[links>=0]-=first
                subtitle=f"{label}: twig < {asset['highlighted_twig_um']} µm; DP {asset['tolerance_um']} µm"
            indices=np.flatnonzero(links>=0)
            lines=np.stack([points[indices],points[links[indices]]],axis=1)
            ax.set_facecolor('black');ax.add_collection(LineCollection(lines,colors='#cc79a7',linewidths=.45))
            ax.scatter(points[links<0,0],points[links<0,1],s=2,c='white')
            ax.set_xlim(low[0],high[0]);ax.set_ylim(high[1],low[1]);ax.set_aspect('equal');ax.tick_params(colors='white')
            x,y=low[0]+10,high[1]-15;ax.plot([x,x+100],[y,y],c='white',lw=2);ax.text(x,y-6,'100 µm',c='white',fontsize=8)
            ax.set_title(subtitle,color='white',fontsize=9)
        fig.suptitle(f'{group}, body {body} · original versus display simplification',color='white');fig.tight_layout()
        name=group.replace(' ','-')+'-raw-versus-pruned.png';fig.savefig(directory/name,dpi=140);plt.close(fig)
        selection.append(dict(group=group,body_id=str(body),rule='Lowest body ID in this T1b brain.json group',file=name))
    save(directory/'pruning-previews.json',dict(frame=manifest['frame'],selection=selection))


def verify_assets(raw=False):
    manifest=json.loads((OUT/'manifest.json').read_text());profile=json.loads((ROOT/'profiles/anatomy-display-v1.json').read_text())
    assert manifest['source_lock_sha256']==hashlib.sha256((ROOT/'profiles/anatomy-lock-v1.json').read_bytes()).hexdigest()
    assert manifest['display_profile_sha256']==hashlib.sha256((ROOT/'profiles/anatomy-display-v1.json').read_bytes()).hexdigest()
    inputs=verify_pinned_inputs() if raw else json.loads((ROOT/'profiles/anatomy-lock-v1.json').read_text())['inputs']
    sources={r['url'].rsplit('/',1)[-1][:-4]:r for r in inputs if r['url'].endswith('.swc')}
    skeleton_cache={};total=0
    for asset in manifest['assets']:
        packed=(OUT/asset['file']).read_bytes();assert hashlib.sha256(packed).hexdigest()==asset['sha256']
        assert len(packed)==asset['bytes']<=profile[asset['lod']][asset['circuit']+'_budget_bytes']
        assert asset['highlighted_twig_um']==profile[asset['lod']]['highlighted_twig_um']<=8
        d=decode_arbors(gzip.decompress(packed))
        brain=json.loads((ROOT/'apps/play/public/data'/('coupling/brain.json' if asset['circuit']=='T1a' else 'brain.json')).read_text())
        assert d['neurons']['body'].tolist()==[int(n['body_id']) for n in brain['nodes']]
        retention_data=(OUT/asset['retention']['file']).read_bytes()
        assert hashlib.sha256(retention_data).hexdigest()==asset['retention']['sha256']
        retention=json.loads(gzip.decompress(retention_data))
        assert retention_summary(retention['neurons'])==asset['retention']['groups']
        assert len(retention['neurons'])==asset['neurons']
        for i,r in enumerate(retention['neurons']):
            row=d['neurons'][i];assert r['body_id']==str(int(row['body']))
            if r['missing']:assert int(row['flags'])&1;continue
            assert r['kept_tips']==r['pruned_tips']<=r['original_tips']
            assert r['kept_cable_um']<=r['pruned_cable_um']+1e-6<=r['original_cable_um']+1e-6
            assert len(r['source_rows'])==row['count']
            if not raw:continue
            if r['body_id'] not in skeleton_cache:
                source=sources[r['body_id']];path=ROOT/source['cache_path']
                assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']
                skeleton_cache[r['body_id']]=read_swc(path)
            xyz,parent,types=skeleton_cache[r['body_id']];indices=np.array(r['source_rows'],int)
            assert np.all((indices>=0)&(indices<len(xyz))) and len(np.unique(indices))==len(indices)
            assert hashlib.sha256(xyz[indices].astype('<f8').tobytes()).hexdigest()==r['selected_original_vertices_sha256']
            threshold=r['twig_threshold_um'];active,_=prune_terminal_twigs(xyz,parent,threshold,np.flatnonzero(types==1))
            points,parents,selected=simplified_tree(xyz,parent,asset['tolerance_um'],manifest['frame'],active,True,np.flatnonzero(types==1))
            assert np.array_equal(selected,indices)
            first=int(row['first']);end=first+int(row['count']);actual=d['parents'][first:end].copy();actual[actual>=0]-=first
            assert np.array_equal(actual,parents)
            assert np.all(np.abs(d['points'][first:end]-points)<=d['step']*.50001)
            total+=len(indices)
    print('PASS: anatomy assets, budgets, groups, retention, original vertex rows and graph order; '+(str(total)+' exported vertices independently checked against pinned SWCs' if raw else 'raw vertex check available with --verify-raw'),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--fetch',action='store_true');parser.add_argument('--build',action='store_true');parser.add_argument('--arbors-only',action='store_true');parser.add_argument('--verify',action='store_true');parser.add_argument('--verify-raw',action='store_true');parser.add_argument('--previews',action='store_true');parser.add_argument('--audit-frame',action='store_true');args=parser.parse_args()
    if args.audit_frame:audit_frame()
    if args.fetch:acquire()
    if args.build:build(args.arbors_only)
    if args.verify or args.verify_raw:verify_assets(args.verify_raw)
    if args.previews:
        audit_frame()
        manifest=json.loads((OUT/'manifest.json').read_text());c=circuits();roi=json.loads((OUT/'neuropils.json').read_text())
        preview(manifest,roi,c)
        selected={int(min((n for n in c['T1b'][1]['nodes'] if n['group']==g),key=lambda n:int(n['body_id']))['body_id']) for g in ('giant fiber','LC4','LPLC2')}
        skeletons={body:read_swc(ROOT/'data/anatomy/raw'/SWC/(str(body)+'.swc')) for body in selected}
        pruning_previews(manifest,c,skeletons)
