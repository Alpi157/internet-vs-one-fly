# V2G anatomy repair a02

Status: COMPLETE_FOR_REVIEW, conditional on the final-commit acceptance receipt.
External stage acceptance remains pending. No push, tag, deployment or new
scientific trial is authorized or performed.

The original landmark gate stopped correctly. The external reviewer amended only
VNC dorsal/ventral strict checks after the stop: same-neuromere upper tectulum
versus leg neuropil, plus IntTct versus bilateral T2 mean. LTct is descriptive.
The amendment is verbatim in docs/anatomy-v2g-a02-axis-audit.md and ledger.yaml.
All 55 strict checks now pass. Original failed reports remain under docs/history/.

Composite layout: brain frontal view, VNC ventral view; not a single projection.
Brain uses (x,y), VNC (x,z) with a +33.504 µm vertical translation, sharing x.
ROI membership and the CV boundary at z=415.744 µm assign vertices. The neck
anchors share x=393.728 µm and have a 12 µm gap. Every crossing edge is flagged
layout, not anatomy. All four assets pass at the same a01 pruning thresholds.
Both giant-fiber annotated somata are dorsal to their fixed-rule branch points.
No long LA clipping edge is found at documented ROI volume/chunk boundaries;
both labels remain in the default silhouette, with evidence and scope explicit.

The full guide, sizes, cable retention and every centroid are committed under
docs/anatomy-v2g.md and docs/anatomy-v2g-a02-axis-audit.json. Frame evidence is in
apps/play/public/data/anatomy/frame.json. All previews and isolated browser
screenshots are regenerated. The brain-only preview has exactly 1 pixel per µm.

Exact verification commands:

```sh
uv run --offline python experiments/v2g_anatomy.py --audit-frame
uv run --offline python experiments/v2g_anatomy.py --verify-raw
npm --prefix apps/play run test:anatomy
npm --prefix apps/play run test:anatomy-browsers
uv run --offline python tools/recompute_v2e.py
uv run --offline python -m pytest -q
uv run --offline python tools/run_acceptance.py V2G --out evidence/V2G/acceptance
uv run --offline python tools/review_bundle.py --milestone V2G --attempt 2 --base f66b2100e43bb0a4683da7c5ffcfb0ef6124ad36 --out reviews/V2G-a02.zip
```

There are 15 registered acceptance commands. The command-results.json receipt
must PASS and name the exact submitted SHA with a clean tree. Final SHA is in
that receipt and the review manifest, avoiding a self-referential commit.
Raw verification needs ignored pinned anatomy downloads; fresh-clone smoke is
offline and uses committed assets/fixtures. No frozen file, raw scientific record,
source lock, model, mechanics, runtime profile or current game UI is changed.

The bounded review ZIP includes phone transports, manifests, all previews and
browser screenshots, compact per-neuron retention, logs and original gate history.
Desktop transports and full source-row inventories remain in the committed
checkout and are listed by hash and size in large-files.json.
