# V2G real anatomy assets

Status: COMPLETE_FOR_REVIEW, conditional on PASS from the final-commit acceptance
receipt. No acceptance or publication is performed by the implementing agent.
Base: f66b2100e43bb0a4683da7c5ffcfb0ef6124ad36, tag v2f-accepted.
No push, tag, deployment or new scientific trial was performed.

The owner replaced the initial all-branch-point rule with iterative terminal-twig
pruning. The active display rule is profiles/anatomy-display-v1.json. Highlighted
neurons remain at 3 µm desktop and 6 µm phone. Only interior thresholds increase,
in 5 µm steps, and every failed and passing size attempt is recorded.

## Completed assets

- T1a phone: 1,163,036 gzip bytes; highlighted twig 6 µm, interior twig 20 µm, DP 1.5 µm.
- T1a desktop: 2,753,201 gzip bytes; highlighted twig 3 µm, interior twig 15 µm, DP 0.5 µm.
- T1b phone: 2,051,910 gzip bytes; highlighted twig 6 µm, interior twig 25 µm, DP 1.5 µm.
- T1b desktop: 4,750,204 gzip bytes; highlighted twig 3 µm, interior twig 20 µm, DP 0.5 µm.

All 6,538 union skeletons were found. The 90 brain and 24 VNC labels have official
names. The frame is +x horizontal, +z downward, projecting away y. Annotated
R/L soma majorities and all six descending-neuron brain-above-VNC checks pass.
Soma annotation units are 8 nm by absolute-coordinate comparison; correlations
and the large root/soma disagreement remain explicit in docs/anatomy-soma-units.json.
Roots need not be somata. No coordinates were invented or moved to match labels.

Every neuron has retained cable and tip counts in its provenance file. Every
exported vertex selects an original SWC row. The raw verifier checks raw hashes,
selection rows, ancestor paths and quantization. Raw-versus-pruned previews use
the lowest body ID in each requested T1b group.

The N-STRENGTH demo uses recorded index 43, seed 202910171376. Its regenerated
target hash matches the stored V2F record. The original worker executes both
shuffles in tests. The UI still selects N-SIGN; no mechanics or runtime profile
changed. Legacy brain.json metadata was updated through the existing exporter.

The portable V2E recomputation checks all raw fields except hardware, then checks
the exact existing compact publication view. It restores nothing and does not
simulate. The original frozen verifiers and raw records remain unchanged.

## Commands

```sh
uv sync --extra dev --locked
uv pip install --no-deps -r profiles/requirements-v2.1.txt
uv run python experiments/v2g_anatomy.py --fetch
uv run python experiments/v2g_anatomy.py --build
uv run python experiments/v2g_anatomy.py --verify-raw
npm --prefix apps/play run test:anatomy
npm --prefix apps/play run test:anatomy-browsers
uv run python tools/recompute_v2e.py
uv run python -m pytest -q
uv run python tools/run_acceptance.py V2G --out evidence/V2G/acceptance
uv run python tools/review_bundle.py --milestone V2G --attempt 1 --base f66b2100e43bb0a4683da7c5ffcfb0ef6124ad36 --out reviews/V2G-a01.zip
```

There are 15 registered acceptance commands. The acceptance receipt's
submitted_code_sha must equal git rev-parse HEAD, with a clean tree. Do not change
a tracked file after final acceptance; a fix requires a new commit and full
acceptance against it. Raw verification requires cached official downloads.
Fresh-clone smoke uses committed assets and fixtures, offline.

Raw downloads and parsed/volume caches stay ignored under data/. The anatomy lock
preserves its original retrieval identities on reacquisition and rejects changes.
All browser assets and provenance are committed. The bounded review ZIP includes
phone transports, every preview, manifests, per-neuron retention measurements,
decode screenshots and logs. Desktop transports and detailed source-row lists
remain in the submitted checkout and are enumerated with hashes in large-files.json.

The final SHA is recorded by acceptance and review manifests to avoid a
self-referential commit. External review remains pending. All 122 scientific
frozen hashes match. See docs/anatomy-v2g.md and evidence/V2G/REVIEW.md for details.
