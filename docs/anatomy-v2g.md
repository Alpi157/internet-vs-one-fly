# Real anatomy assets

**Composite layout: brain frontal view, VNC ventral view; not a single projection.**

Assets are prepared for external review. The a01 view was mislabeled: it projected
the whole CNS along y with the body's anterior-posterior axis vertical. This
repair uses independent 3D anatomical landmarks. It changes display assets and
their isolated decoder only. Model, executed circuits, runtime, mechanics,
scientific results and current game UI are unchanged.

## Sources and anatomy

The [official MaleCNS download page](https://male-cns.janelia.org/download/)
documents the original unmirrored 8 nm SWCs, brain fullbrain-roi-v4 and VNC
malecns-vnc-neuropil-roi-v0 volumes. Each volume supplies its own official label
names in segment_properties/info. The pinned Feather annotations supply somata,
soma side and instance names. All 6,538 union skeletons were found; all 90 brain
and 24 VNC labels have names. T1a is not a subset of T1b.

[anatomy-lock-v1.json](../profiles/anatomy-lock-v1.json) is unchanged: URL, byte
size, SHA-256 and retrieval date for every input. Anonymous original acquisition
used storage.googleapis.com, at most eight requests, retries and Range resume.
Raw downloads remain ignored under data/. The 353 brain and 1,916 VNC absent
chunks retain the documented precomputed background interpretation and receipts.
The scientific source lock and both frozen scientific manifests are unchanged.

## Anatomical axes and the amended gate

Centroids are computed from occupied voxel centres in original 3D source space,
using official offsets and resolution. They are not averages of contour vertices.
The [complete axis audit](anatomy-v2g-a02-axis-audit.md) records all centroids,
signs, strict comparisons, the original stopped gate and the external reviewer's
verbatim amendment. Lower tectulum remains descriptive and intermediate. The
overall tectulum-versus-ventral contrast remains unchanged.

| Panel | Source axis | Positive anatomical direction | Evidence |
|---|---|---|---|
| Both | +x | Fly left, viewer right | Annotated R/L soma majority rule |
| Brain | +z | Posterior | AL/aL/bL/gL/EB anterior to CA/PB |
| Brain | +y | Ventral | GNG/AL ventral to SMP/CA/PB; aL dorsal to bL |
| VNC | +z | Posterior | LegNp(T1) anterior to LegNp(T3) |
| VNC | +y | Ventral | Seven amended within-neuromere and IntTct checks |

All 55 strict checks pass. The existing soma-side evidence remains 97.19568567026194%
of 3,245 R somata and 99.51969260326609% of 3,123 L somata on their expected sides.
Exceptions remain in place. No point is moved to satisfy a landmark rule.

## Composite split and neck alignment

Brain ROI membership assigns the brain panel, including CV-anterior. VNC ROI
membership assigns the VNC panel, including CV-posterior. Conflicting membership
stops export. Unlabeled skeleton vertices use the midpoint between the posterior
CV-anterior boundary face and anterior CV-posterior boundary face. These are both
at source z = 415.744 µm, so the split is z < 415.744 for brain and z >= 415.744
for VNC. ROI membership is authoritative. In this dataset it agrees with the
boundary fallback for every source skeleton vertex.

The brain panel uses (x,y), dorsal up, projecting along z. The VNC panel uses
(x,z), T1 up, projecting along y. Both retain the same original x without a
horizontal translation. All ROI labels belong to exactly one panel, by source
volume. The cervical anchors use one shared original x column on the brain
CV-anterior ventral outline and VNC CV-posterior anterior outline.

The shared x is 393.728000000000 µm. The brain exit is at display
[393.728, 437.76000000000016] µm and VNC entry at [393.7279999999996, 449.75999999999976] µm.
VNC vertical translation is 33.504000000000 µm; the anchor gap
is 12 µm. Horizontal translation is zero. These are documented layout
choices and measured ROI anchors, not a continuous anatomical projection.

Every crossing edge preserves both original endpoints. It is drawn straight,
amber and dashed, and is flagged **layout, not anatomy**. No transition is hidden
inside a simplified path. Other displayed vertices select original SWC vertices,
subject only to the documented quantization. Soma coordinates come from the
annotated soma, with missing values explicit. Unlabeled panel assignment is a
display convention, not an inferred anatomical compartment label.

Source-vertex panel accounting:

| Assignment | Vertices |
|---|---:|
| VNC_roi | 4973626 |
| brain_roi | 23718522 |
| roi_override_plane | 0 |
| unlabeled_VNC | 445237 |
| unlabeled_brain | 2090338 |

## Giant-fiber anatomical sanity check

The display profile recorded the branch-point selection rule before inspecting
candidate heights. On the raw tree, start at the vertex nearest the annotated
soma, follow the shortest cable route to VNC ROI membership, and choose the
brain-ROI trunk vertex with greatest off-trunk brain cable. Ties use the lowest
original row. Neither axes nor this rule were tuned to the outcome. This is an
operational main dendritic branch point, not a new synaptic annotation.

| Body | Annotated soma height µm | Main branch height µm | Soma dorsal separation µm | Nearest-soma vertex disagreement µm | Soma dorsal |
|---|---:|---:|---:|---:|---|
| 10001 | 178.064000000000 | 211.968000000000 | 33.904000000000 | 1.234412961695 | True |
| 10010 | 177.872000000000 | 210.473600000000 | 32.601600000000 | 1.046616797113 | True |

Both satisfy the reviewer-required dorsal-soma relation. Source XYZ, original
rows, scores and measured disagreement remain in frame.json. Failure stops export.

## Lamina inspection and ROI silhouettes

Each label has a maximum occupancy projection in its own panel at 1.024 µm
voxel size. Marching squares traces the 0.5 boundary; Douglas-Peucker tolerance
is 1 µm. Overlapping ROIs remain separate. Coarse groups retain the documented
name-based mapping: optic lobe, central brain, mushroom body, central complex,
antennal lobe, SEZ, VNC leg neuropil and other. No ROI name is invented.

The LA(L)/LA(R) frontal rasters are inspected against the actual volume limits
and 64-voxel chunk planes. The report lists all coincident boundary runs; a
contiguous run of 20 µm or longer flags clipping. Neither label touches an outer
volume face. No long chunk-aligned clipping edge is detected. This is a check of
documented bounds, not proof that all tissue inside the imaged specimen is intact.

| Lamina | Longest chunk/volume-aligned boundary run µm | Truncation flag | Default silhouette |
|---|---:|---|---|
| LA(L) | 7.168 | None | True |
| LA(R) | 3.072 | None | True |

Both are retained in the data and default silhouette. The code retains any
flagged ROI and its contour while excluding it from the default union. A fixture
checks this behavior. The union is of named neuropils, not invented unsegmented
tissue. The [lamina raster inspection](media/anatomy/lamina-inspection.png)
shows the source pixels and chunk grid. The numerical evidence is in frame.json.

## Display simplification and sizes

The accepted a01 pruning thresholds and budgets are unchanged. Iteratively
remove whole terminal twigs shorter than the threshold using 3D cable path
length. Preserve roots, explicit SWC somata and their ancestor paths. Simplify
unbranched segments with original vertices only. Preserve the two endpoints of
every panel-crossing edge so the bridge flag is exact. This is display
simplification only; raw skeletons stay pinned. No smoothing or resampling occurs.

| Circuit | LOD | Gzip bytes | Budget bytes | Highlighted twig µm | Interior twig µm | DP µm | Layout bridges |
|---|---|---:|---:|---:|---:|---:|---:|
| T1a | phone | 1167797 | 1500000 | 6 | 20 | 1.5 | 291 |
| T1a | desktop | 2766617 | 3000000 | 3 | 15 | 0.5 | 291 |
| T1b | phone | 2062331 | 2500000 | 6 | 25 | 1.5 | 807 |
| T1b | desktop | 4769548 | 5000000 | 3 | 20 | 0.5 | 807 |

All pass at the same accepted thresholds; no size-driven increase was made in
this repair. Per-neuron original, pruned and kept 3D cable lengths and tip counts,
original source rows and hashes are in the retention files. Kept cable measures
simplified 3D chords before projection, excluding the invented layout distance.
Every exported vertex is independently checked against its original row. Fine
cable can be substantially reduced; these are display assets, not full morphology
for scientific measurement. Missing anatomy is never invented to replace pruning.

| Circuit | LOD | Group | Neurons | Median kept cable fraction | Minimum kept cable fraction |
|---|---|---|---:|---:|---:|
| T1a | phone | LC4 | 126 | 0.573458 | 0.324262 |
| T1a | phone | LPLC2 | 185 | 0.625928 | 0.365803 |
| T1a | phone | giant fiber | 2 | 0.607436 | 0.585025 |
| T1a | phone | interior | 2312 | 0.365541 | 0.059166 |
| T1a | phone | named ports | 4 | 0.765160 | 0.748801 |
| T1a | phone | walking DNs | 12 | 0.741342 | 0.610922 |
| T1a | desktop | LC4 | 126 | 0.840418 | 0.501853 |
| T1a | desktop | LPLC2 | 185 | 0.860987 | 0.572809 |
| T1a | desktop | giant fiber | 2 | 0.908810 | 0.899651 |
| T1a | desktop | interior | 2312 | 0.460241 | 0.085390 |
| T1a | desktop | named ports | 4 | 0.906148 | 0.899814 |
| T1a | desktop | walking DNs | 12 | 0.894052 | 0.860594 |
| T1b | phone | LC4 | 126 | 0.573458 | 0.324262 |
| T1b | phone | LPLC2 | 185 | 0.625928 | 0.365803 |
| T1b | phone | giant fiber | 2 | 0.607436 | 0.585025 |
| T1b | phone | interior | 5226 | 0.306164 | 0.028143 |
| T1b | phone | named ports | 4 | 0.765160 | 0.748801 |
| T1b | phone | walking DNs | 12 | 0.741342 | 0.610922 |
| T1b | desktop | LC4 | 126 | 0.840418 | 0.501853 |
| T1b | desktop | LPLC2 | 185 | 0.860987 | 0.572809 |
| T1b | desktop | giant fiber | 2 | 0.908810 | 0.899651 |
| T1b | desktop | interior | 5226 | 0.371921 | 0.051103 |
| T1b | desktop | named ports | 4 | 0.906148 | 0.899814 |
| T1b | desktop | walking DNs | 12 | 0.894052 | 0.860594 |

## Binary transport and decoder

FLYARB03 extends the accepted FLYARB02 tree transport. All fields are little-endian.
The zero-timestamp gzip contains a 56-byte header: magic FLYARB03, uint32 neuron
count N, uint32 S, uint32 P, uint32 zero, then four float64 bounding coordinates
[xmin,ymin,xmax,ymax] in composite display µm. S equals P.

The N 24-byte neuron rows contain uint64 body ID, uint32 first/count, uint16 soma
x/y and uint32 flags: bit 0 missing skeleton, bit 1 missing soma, bit 2 VNC soma.
Next are uint32[P] parent deltas (zero means root), uint16[P] parent-relative x
and uint16[P] parent-relative y modulo 65536. Finally uint8[P] layout flags:
bit 0 is VNC panel; bit 1 marks a parent edge crossing panels, layout, not anatomy.
All other flag bits are zero. Parents precede children within the same neuron.
The decoder rejects an incorrect bridge flag or a parent outside its neuron.

Each coordinate's quantization step is its bounding span / 65535; rounding error
is at most half a step. Python and TypeScript agree on both legacy and composite
fixtures, including invalid bridge flags. Neuron order matches compiled IDs, and
missing lists are exact. The decoder is isolated from the current game UI.

## Previews and verification

Every preview is labeled with the composite-view caveat and has a real 100 µm
scale bar. Raw-versus-pruned examples keep the lowest body ID selection rule.

- [Neuropil outlines](media/anatomy/neuropils.png).
- [T1b highlighted arbors](media/anatomy/T1b-arbors.png).
- [T1b brain alone, 1 pixel per µm and equal axes](media/anatomy/T1b-brain-1to1.png).
- [Giant fibers with measured soma and branch points](media/anatomy/giant-fiber.png).
- [T1a coupling circuit](media/anatomy/T1a-arbors.png).
- [Giant fiber raw/pruned](media/anatomy/giant-fiber-raw-versus-pruned.png).
- [LC4 raw/pruned](media/anatomy/LC4-raw-versus-pruned.png).
- [LPLC2 raw/pruned](media/anatomy/LPLC2-raw-versus-pruned.png).

Chromium, Firefox and WebKit decode and draw both phone assets at 390x844 and
1440x900. Reports include five decode timings, exact transport/allocated-array
storage, optional heap readings, flags and screenshots. Unavailable memory APIs
remain null; total process/GPU memory is not measured.

```sh
uv run --offline python experiments/v2g_anatomy.py --audit-frame
uv run --offline python experiments/v2g_anatomy.py --build
uv run --offline python experiments/v2g_anatomy.py --verify-raw
npm --prefix apps/play run test:anatomy
npm --prefix apps/play run test:anatomy-browsers
uv run --offline python tools/recompute_v2e.py
uv run --offline python tools/run_acceptance.py V2G --out evidence/V2G/acceptance
```

## Preserved accepted work

The N-STRENGTH demo stays at index 43, seed 202910171376, with the recorded
target hash ab33b3baef17f67f5e65ad00382fb9a8825447626947c3c6d13812d422177488.
Both demo shuffles still execute through the existing coupling worker in tests;
the new demo is not wired into the UI. The portable V2E recompute still compares
all raw fields and the exact compact public tables, ignoring only hardware. No
frozen verifier, raw scientific record, result or published finding is changed.

The [soma units report](anatomy-soma-units.json) is unchanged: 8 nm absolute-coordinate
fit, Pearson r 0.9217653808001026 over 6,443 bodies, maximum soma/root disagreement
842.84911910021 µm. Roots need not be somata. Quantization is not used to explain
those residuals. Missing annotations stay explicit. Attribution remains CC-BY-4.0.
No claim about living flies follows from these display assets.
