# V2G repair attempt a02

Status: STOP_ANATOMICAL_LANDMARK_GATE. Existing a01 anatomy assets are unchanged
and do not implement the requested composite layout. The previously claimed
frontal whole-CNS frame is invalid. External stage acceptance is not asserted.

Base: df787fa8c05591a39f4466b3c71872d902ecb6bc.
The source, pruning, budget, demo, portable recompute and a01 acceptance portions
were accepted by external review. The frame requires repair.

The pinned 3D volumes yield brain +z posterior, +y ventral and +x fly left.
The VNC set contrasts also yield +z posterior and +y ventral. One required
individual dorsal/ventral ordering conflicts: LTct y=438.7949197017007 µm is
more ventral than LegNp(T3)(R) y=429.72174902137596 µm by
9.073170680324722 µm. Other tectulum comparisons support the opposite ordering.
No sign or landmark was changed to conceal it.

See docs/anatomy-v2g-a02-axis-audit.md and its JSON companion for all 114 original
3D ROI centroids and 144 comparisons. The new non-frozen --audit-frame mode
recomputes the centroids from the pinned ROI chunks, stops with exit 1 and leaves
display assets untouched. Build and preview modes run this gate first.

Exact command:

```sh
uv run --offline python experiments/v2g_anatomy.py --audit-frame
```

Captured output and traceback:

```text
Decoded rois/fullbrain-roi-v4 labels 90 absent background chunks 353
Decoded rois/malecns-vnc-neuropil-roi-v0 labels 24 absent background chunks 1916
brain posterior z 1
brain ventral y 1
VNC posterior z 1
VNC ventral y 1
CONTRADICTION {"anatomical_positive": "ventral", "high": "LegNp(T3)(R)", "low": "LTct", "panel": "VNC", "passes": false, "signed_separation_um": -9.073170680324722}
Traceback (most recent call last):
  File "/home/alpi/Projects/FlyBench/experiments/v2g_anatomy.py", line 500, in <module>
    if args.audit_frame:audit_frame()
                        ^^^^^^^^^^^^^
  File "/home/alpi/Projects/FlyBench/experiments/v2g_anatomy.py", line 143, in audit_frame
    raise RuntimeError('STOP: contradictory anatomical landmark ordering; see evidence/V2G/a02/axis-audit.json. No assets re-exported.')
RuntimeError: STOP: contradictory anatomical landmark ordering; see evidence/V2G/a02/axis-audit.json. No assets re-exported.
```

The composite split, neck offsets, giant-fiber soma check, lamina check,
re-export, new previews, browser matrix and final acceptance are not run after
the failed gate. No reviews/V2G-a02.zip has been built. Do not treat the previous
a01 acceptance receipt as acceptance of this repair. No frozen file, scientific
raw record, UI, mechanics, model, runtime profile or source lock is changed.
No push, tag or deployment is authorized or performed.

New tests check the 3D centroid algorithm against direct voxel enumeration and
recompute the axis assignments and explicit stop from the full centroid report.
The owner's anatomical direction is required before continuing past this gate.
