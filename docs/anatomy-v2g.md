# Real anatomy asset preparation

> Repair a02 is stopped at an anatomical landmark conflict. The a01
> whole-CNS view below was mislabeled as frontal and is superseded. The requested
> composite layout has not been exported. See the [3D axis audit](anatomy-v2g-a02-axis-audit.md)
> and [handoff](CONTINUE.md). Sources, pruning and transport results below remain
> the a01 record, not validation of its anatomical view.

Status: assets prepared for external review. Final-commit verification and acceptance are recorded separately under evidence/V2G/acceptance/.

These are display assets derived from measured anatomy. There is no change to
the model, graph, mechanics, runtime settings, scientific results or game UI.
No claim about living flies follows from a display asset.

## Sources and identities

The [official MaleCNS download page](https://male-cns.janelia.org/download/)
documents the original, unmirrored Male CNS EM-space SWC skeletons in 8 nm units,
the brain `fullbrain-roi-v4` segmentation, and the VNC
`malecns-vnc-neuropil-roi-v0` segmentation. Both volumes are uint64 at their base
256 nm resolution. Their own `segment_properties/info` files supply names.
The original pinned Feather body annotations supply soma side and instance names.

[anatomy-lock-v1.json](../profiles/anatomy-lock-v1.json) records each URL, size,
SHA-256 and retrieval date. Raw responses are under ignored `data/anatomy/raw/`.
There are 6,538 distinct bodies across the two circuits, with no missing SWCs.
T1a is not a subset of T1b. Every source and graph identity is kept separate.
The original scientific source lock and both freeze manifests are unchanged.

Acquisition uses anonymous HTTPS to `storage.googleapis.com`, eight requests at
most, four attempts with exponential backoff, and Range-based partial-file
resume. Missing inputs remain explicit. Sparse precomputed volume chunks are
absent background, as handled by the official
[Neuroglancer volume reader](https://github.com/google/neuroglancer/blob/master/src/datasource/precomputed/backend.ts).
There are 353 absent brain chunks and 1,916 absent VNC chunks at the selected
scale. These HTTP 404 responses are recorded, not replaced with named anatomy.
Other source failures stop acquisition. A nonzero ROI label lacking an official
name stops export.

## Frontal display frame

Coordinates are micrometres. Source x is horizontal, increasing to the viewer's
right; source z is vertical, increasing downward; source y is projected away.
This is a frontal anterior view: the fly's right is on the viewer's left.

The horizontal axis is chosen by the largest standardized separation of
annotated R/L soma coordinates. The median-based dividing coordinate is
386.88 µm. Among the 3,245 annotated R somata, 97.19568567026194% appear left of
the dividing coordinate; among the 3,123 L somata, 99.51969260326609% appear right.
Exceptions remain in place. No neuron is moved to make its side annotation agree.

Among the remaining axes, z gives the largest brain/VNC centroid separation.
The brain centroid is at z = 231.94749413479045 µm and the VNC centroid at
z = 758.5664791040778 µm. The six required descending neurons are checked
individually against the ROI volumes: giant fibers 10001 and 10010, and MDNs
10763, 11288, 11332 and 12348. Their brain-ROI skeleton-node median display
heights all precede their VNC-ROI medians. SWC type codes are not interpreted as
axon/dendrite labels. This check establishes compartment placement, not a new
biological annotation.

`apps/play/public/data/anatomy/frame.json` retains the individual annotated
somata, anchor coordinates, compartment node counts and majority-rule evidence.
Tests recompute the side majority and the brain-above-VNC rule from those data.

## somaLocation units

[The comparison report](anatomy-soma-units.json) compares 6,443 bodies with an
annotated soma against SWC soma nodes where present, otherwise the nearest SWC
root. The absolute-coordinate fit supports 8 nm annotation units: fitted scale
0.007875238373573436 µm per annotation unit. Pearson correlation across all
coordinate components is 0.9217653808001026; correlations by x, y and z are
0.9111452215838445, 0.8220875162360781 and 0.9333701881003481.

The maximum soma/root disagreement is 842.84911910021 µm. A root need not be the
soma, so this is not a coordinate-accuracy bound. The RMS disagreement at the
8 nm hypothesis is 64.132947292898 µm, versus 300.14005584808706 µm at 1 nm and
42318.140546764094 µm at 1 µm. Correlation alone cannot establish units; the
absolute-coordinate hypotheses are compared as well. Individual comparisons and
missing soma annotations remain explicit.

The existing exporter has a metadata-only `--anatomy-units-from` mode, so unit
notes can be updated without regenerating runtime profiles or executing trials.
The legacy normalized soma map retains its existing display convention.

## ROI outlines

The selected scale is 1.024 µm isotropic. Each nonzero ROI label is projected
separately with a maximum occupancy operation along source y, so overlapping
ROIs remain separate. Marching squares traces the 0.5 boundary of the binary
occupancy mask; Douglas-Peucker tolerance is 1.0 µm. Voxel centres, offsets,
resolution and the display signs determine physical coordinates.

There are 90 observed brain labels and 24 observed VNC labels, with no missing
names. Names are copied verbatim from each volume's label metadata; the volume
name namespaces its numeric labels. The union silhouette is the union of these
projected neuropils, not an invented outline of unsegmented cortex or tissue.

Coarse groups are a documented display mapping of those labels: ME, AME, LA, LO
and LOP are optic lobe; CA, PED and the named mushroom-body lobes are mushroom
body; EB, FB, NO and PB are central complex; AL is antennal lobe; GNG, PRW and SAD
are SEZ; LegNp is VNC leg neuropil. Remaining brain neuropils are central brain,
except CV-anterior and CRN, which are other. Remaining VNC labels are other.
No new ROI name or finer anatomical annotation is inferred.

## Display simplification and asset sizes

The owner replaced the original every-branch-point rule with display-resolution
pruning. This is a display simplification only. The pinned raw skeletons, model,
executed circuits and scientific results are unchanged.

Whole terminal twigs shorter than T are removed iteratively until no more qualify,
using 3D cable length along each path. This follows the non-exact recursive
[navis prune_twigs semantics](https://navis-org.github.io/navis/stable/api/).
Every original root and any explicitly labeled SWC soma is protected, including
its ancestral path. Remaining branch points and tips are retained. Degree-2
chains form unbranched paths; Douglas-Peucker removes redundant original vertices
inside those paths, with 0.5 µm desktop and 1.5 µm phone tolerance. No smoothing,
resampling, invented soma or reconnection is performed.

Highlighted groups use fixed twig thresholds of 3 µm desktop and 6 µm phone.
This includes LC4, LPLC2, giant fiber, walking DNs and every named port in the
frozen `profiles/ports-v2.json`. Four named ports classified as interior in the
legacy brain map are protected and reported separately. Interior thresholds start
at 10 µm desktop and 20 µm phone; only they rise, in 5 µm steps, until the first
passing budget. No highlighted threshold was raised. The display profile and
all attempts are committed in the manifests and retention reports.

| Circuit | LOD | Gzip bytes | Budget bytes | Highlighted twig T (µm) | Interior twig T (µm) | DP tolerance (µm) |
|---|---|---:|---:|---:|---:|---:|
| T1a | phone | 1,163,036 | 1,500,000 | 6 | 20 | 1.5 |
| T1a | desktop | 2,753,201 | 3,000,000 | 3 | 15 | 0.5 |
| T1b | phone | 2,051,910 | 2,500,000 | 6 | 25 | 1.5 |
| T1b | desktop | 4,750,204 | 5,000,000 | 3 | 20 | 0.5 |

Every threshold attempt, including failures:

| Circuit | LOD | Interior twig T (µm) | Gzip bytes | Budget passes |
|---|---|---:|---:|---|
| T1a | phone | 20 | 1,163,036 | True |
| T1a | desktop | 10 | 3,571,604 | False |
| T1a | desktop | 15 | 2,753,201 | True |
| T1b | phone | 20 | 2,514,448 | False |
| T1b | phone | 25 | 2,051,910 | True |
| T1b | desktop | 10 | 7,752,866 | False |
| T1b | desktop | 15 | 5,889,948 | False |
| T1b | desktop | 20 | 4,750,204 | True |

Each neuron's `.retention.json.gz` entry records original, pruned and final cable
length, original and kept tip counts, pruning rounds, and original SWC vertex
rows. Cable lengths are 3D micrometres; pruned length follows all remaining raw
edges, while final kept length follows simplified 3D chords. Quantization is a
separate bounded transport approximation. Tip counts exclude isolated roots.
Every exported vertex is checked against its original SWC row before encoding,
and the raw verifier independently checks the rows, topology and coordinate error.

Per-group retained cable fractions, including the minimum:

| Circuit | LOD | Group | Neurons | Median kept fraction | Minimum kept fraction |
|---|---|---|---:|---:|---:|
| T1a | phone | LC4 | 126 | 0.573458 | 0.324262 |
| T1a | phone | LPLC2 | 185 | 0.625928 | 0.365803 |
| T1a | phone | giant fiber | 2 | 0.607455 | 0.585021 |
| T1a | phone | interior | 2312 | 0.365541 | 0.059166 |
| T1a | phone | named ports | 4 | 0.765172 | 0.748777 |
| T1a | phone | walking DNs | 12 | 0.741314 | 0.610907 |
| T1a | desktop | LC4 | 126 | 0.840418 | 0.501853 |
| T1a | desktop | LPLC2 | 185 | 0.860987 | 0.572809 |
| T1a | desktop | giant fiber | 2 | 0.908810 | 0.899651 |
| T1a | desktop | interior | 2312 | 0.460241 | 0.085390 |
| T1a | desktop | named ports | 4 | 0.906233 | 0.899850 |
| T1a | desktop | walking DNs | 12 | 0.894032 | 0.860594 |
| T1b | phone | LC4 | 126 | 0.573458 | 0.324262 |
| T1b | phone | LPLC2 | 185 | 0.625928 | 0.365803 |
| T1b | phone | giant fiber | 2 | 0.607455 | 0.585021 |
| T1b | phone | interior | 5226 | 0.306149 | 0.028143 |
| T1b | phone | named ports | 4 | 0.765172 | 0.748777 |
| T1b | phone | walking DNs | 12 | 0.741314 | 0.610907 |
| T1b | desktop | LC4 | 126 | 0.840418 | 0.501853 |
| T1b | desktop | LPLC2 | 185 | 0.860987 | 0.572809 |
| T1b | desktop | giant fiber | 2 | 0.908810 | 0.899651 |
| T1b | desktop | interior | 5226 | 0.371921 | 0.051103 |
| T1b | desktop | named ports | 4 | 0.906233 | 0.899850 |
| T1b | desktop | walking DNs | 12 | 0.894032 | 0.860594 |

Pruning can discard substantial fine cable. These are coarse display assets,
not complete morphology for scientific measurement. Missing anatomy is not
invented to replace removed twigs. The earlier all-endpoint encoding exceeded
its superseded budgets; that audit and the owner's revised rule remain recorded
in the review evidence.

Static previews use the same frontal frame and a real 100 µm scale bar:

- [Neuropil outlines](media/anatomy/neuropils.png).
- [T1b, with declared groups highlighted](media/anatomy/T1b-arbors.png).
- [Giant fibers](media/anatomy/giant-fiber.png).
- [T1a coupling circuit](media/anatomy/T1a-arbors.png).
- [Giant fiber, raw versus pruned](media/anatomy/giant-fiber-raw-versus-pruned.png).
- [LC4, raw versus pruned](media/anatomy/LC4-raw-versus-pruned.png).
- [LPLC2, raw versus pruned](media/anatomy/LPLC2-raw-versus-pruned.png).

Raw-versus-pruned examples use the lowest body ID in each T1b group. No example
is selected for visual agreement. Per-example identities are recorded beside the
images. The browser harness decodes the phone assets, checks their hashes and
neuron counts, draws real coordinates, and screenshots both circuits in Chromium,
Firefox and WebKit. It records five decode timings and exact binary/typed-array
storage, plus browser heap readings when available. Total process and GPU memory
are not measured; unavailable heap APIs remain null.

### FLYARB02 binary layout

All fields are little-endian. The gzip wrapper has a zero timestamp. The
56-byte header is `8s, uint32 N, uint32 S, uint32 P, uint32 reserved, float64[4]
bbox`. Magic is `FLYARB02`; reserved is zero; S equals P. Bounding coordinates
are `[xmin, ymin, xmax, ymax]` in µm. Quantization steps are the two bounding
spans divided by 65,535; rounding error is at most half a step per coordinate.

Each of the N 24-byte neuron records contains `uint64 bodyId, uint32 first,
uint32 count, uint16 somaX, uint16 somaY, uint32 flags`. Records follow the exact
compiled graph order, including empty slots. Flag bit 0 means missing skeleton;
bit 1 means missing annotated soma. A missing soma's coordinate fields are
ignored. Soma coordinates are absolute quantized coordinates in the same frame.

After the records come `uint32[P] parentDelta`, `uint16[P] xDelta`, and
`uint16[P] yDelta`. Vertices follow deterministic parent-before-child order within
each neuron. A zero parentDelta denotes a root; otherwise the parent is
`vertexIndex - parentDelta`, within that same neuron. Each vertex defines its
parent-to-child segment; a root is a degenerate segment at the root position.
For a root the coordinate deltas contain absolute quantized coordinates. Other
deltas are `(childQuantized - parentQuantized) modulo 65,536`. Decoding adds the
parent coordinate modulo 65,536. This transform is lossless for quantized values.

The Python encoder and TypeScript decoder agree on a committed synthetic fixture.
The decoder is data-only and is not imported into the current game UI.

## Strength-preserving demo

The fixed rule, recorded before candidate inspection, is: "the T1a H0-STR
N-STRENGTH null whose H0b equals the family median of the 499 values; ties go to
the lowest index."

It selects index 43, seed 202910171376. The regenerated target SHA-256 is
`ab33b3baef17f67f5e65ad00382fb9a8825447626947c3c6d13812d422177488`, matching the
stored raw record. Targets and selection provenance are exported beside N-SIGN.
The existing coupling worker loads and executes both demo shuffles in a Node
test. The UI still selects its original N-SIGN demo. This export adds no trial
and changes no scientific result.

## Portable results check

`uv run python tools/recompute_v2e.py` restores nothing and is independent of the
frozen CLI verifier. It calls the same frozen analysis functions, compares all
recomputed fields against the full stored tables while ignoring only hardware,
then checks the existing compact publication view against
`docs/results-v2e.json`. Full metrics, raw-input hashes and duration arrays are
checked before the compact view is formed. The public view's source-table hash
and completion record are also checked. No host metadata is substituted and no
frozen file is changed.

All underlying and derived anatomy remains CC-BY-4.0. Cite the Male CNS
Connectome project and the references in [CITATION.cff](../CITATION.cff).

## Reproduce and verify anatomy

```sh
uv run python experiments/v2g_anatomy.py --fetch
uv run python experiments/v2g_anatomy.py --build
uv run python experiments/v2g_anatomy.py --verify-raw
npm --prefix apps/play run test:anatomy
npm --prefix apps/play run test:anatomy-browsers
uv run python tools/recompute_v2e.py
```

Acquisition preserves the committed lock when restoring its exact input identities.
An upstream byte or layout change stops the operation. Raw verification requires
the pinned local downloads; the default tests and browser decoder use committed
derived assets and offline fixtures. Raw responses and parsed caches are excluded
from Git and the review ZIP.
