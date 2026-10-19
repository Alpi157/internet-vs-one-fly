# Wiring lab and launch readiness (V2I)

Presentation only. The model, kernel, game mechanics, runtime neural parameters,
graphs, raw records, scientific results, freeze manifests and V2G anatomy assets
retain their accepted bytes. `tests/test_v2i.py` compares protected files to the
operator-specified starting commit. Stage acceptance belongs to the reviewer.

## Registered results and live observations

The publisher `experiments/v2f_publish.py` generates the public chart, finding
copy, graph table, scientific pages and README. It never runs a simulation.
The N-SIGN curve input is `docs/results-v2e-lab-curves.json`, a lossless curve-only
projection from `evidence/V2E/results/tables.json`. Its full source hash must match
`docs/results-v2e.json:source_tables_sha256`; when the full table is present the
publisher also compares every projected curve. N-STRENGTH comes directly from
`docs/results-v2f.json:metrics`, the H0-STR T1a family. The measured T1a curves
from the two studies are checked for exact equality. Bands use NumPy's same
linear percentile convention as the frozen figure code, separately per family.

Both families used the same registered grid: 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.039, 0.05, 0.06, 0.08, 0.1. N-STRENGTH at 0.1: 94 stopped tails are missing; the complete-family band ends before that point. Bands show the middle 95% of shuffles, not confidence intervals. Lines join observed grid points; no missing observations are filled.

Each panel's live rate is its recorded spike count divided by neuron count and
observed duration, up to the existing 250 simulated ms window. The worker sends
all recorded frames from each publication interval. The display retains a bounded
history and uses the same BrainView renderer and display smoothing as the game.
The chart never incorporates live rates. Switching family or grid point creates
both games afresh with the same existing seeds; the regression test verifies
identical reset frames and equality of displayed event counts with rate counts.
The hand button sends the existing drop command to both games.

N-SIGN: seed 202710160000, index 0.
Selection: First V2E T1a N-SIGN null in ascending seed order whose s* equals the family median; no other outcome enters selection.

N-STRENGTH: seed 202910171376, index 43.
Selection: the T1a H0-STR N-STRENGTH null whose H0b equals the family median of the 499 values; ties go to the lowest index.
Target SHA-256: `ab33b3baef17f67f5e65ad00382fb9a8825447626947c3c6d13812d422177488`.

## Design interpretation

- The a02 reviewer correction distinguishes the selected game setting from the
  registered H0b test strength. The lab defaults to the latter, including family
  switches. Both slider ticks and the logarithmic chart guides are generated
  from runtime calibration metadata and the frozen protocol's H0b definition.
  The game runtime remains unchanged. Phone plots have a readable independent
  viewBox and a plot area above the requested minimum height.
- The desktop field scales with viewport height. The compact lesion badge occupies
  the subtitle slot, so changing circuits adds no layout height. Restore retains
  a full touch target. Bounds checks use the renderer's actual arena radius.
- The real panel identifies its simulation noise seed, not a shuffle seed:
  it has no shuffled graph. The shuffled panel shows its actual shuffle seed,
  family and fixed selection rule in an expandable information detail.
- Brain is the default crop, as required by the shared BrainView contract.
  Whole CNS is independently selectable in each panel. The design illustration
  is replaced by the unchanged real skeletons. The inherited active-interior
  soma LOD and measured group-label anchors are described in `ui-v2h.md`.
- Anatomy captions and selection details expand in place to keep the phone
  layout compact. The full lab scrolls on phones; extra chart screenshots make
  the registered data reviewable. The desktop columns flow independently.
- The explanatory desktop paragraph qualifies the mechanism as exploratory,
  matching the generated README. Input-strength preservation is approximate,
  as the generated model-limits disclosure explains.
- Higher-contrast control borders retain the V2H accessibility adjustment.
  Round summaries use side-by-side score and share card on desktop. Every
  summary control is asserted inside all requested viewport sizes.

## Launch and evidence

The manual-only Pages workflow builds the ordinary Vite production site at its
configured repository base path. The generated scientific pages and 404 page use
local fonts, icons and CSS, with black theme metadata and social tags. A nested
missing URL uses the same base-path assets. The browser harness blocks and records
third-party requests. Outbound attribution/data links fetch nothing until followed.
No push, tag or deployment is performed.

`apps/play/test/v2i-e2e.mjs` captures all requested states in Chromium, Firefox and
WebKit at every requested viewport, checks axe, both radio groups, resets, restore,
rate arithmetic, summaries and missing-page routing. FPS is rAF opportunities
while both worker simulations advance and both BrainViews render recorded events.
This is headless host-engine evidence, not a physical-phone measurement. The full
game harness additionally exercises keyboard rounds, authority, replay and sharing.

`apps/play/test/media.mjs` records a real keyboard-played hand, its replay, both
lab families and a site social card using a recorded escape BrainView frame. Icons remain derived from the supplied fly SVG.
`docs/media/media-provenance.json` records source-file hashes, applied game inputs,
seeds, graph/profile identities, capture dimensions and output hashes. The hero
live phase advances recorded simulation intervals deterministically for capture;
the replay uses the ordinary quarter-speed UI, explicitly looped for the capture. The declaration is written before seed selection; the first ascending seed yielding an escape is chosen. Input, outcome, tried count, recorded replay ticks and the declaration hash are retained in provenance. `apps/play/test/media-gifs.py` performs GIF palette conversion; it changes
only presentation. Identical captured frames may merge with their duration retained. Source frames are temporary, not new scientific records.

The frozen punctuation inventory is `frozen-punctuation-v2i.json`. Non-frozen
public prose uses plain punctuation. Frozen source text and immutable v1 history
are retained verbatim, including their existing punctuation.

The existing acceptance registry and review bundler are extended for V2I. The
bundle includes all stage screenshot evidence and current media; unchanged bulk
science/anatomy is hash-inventoried and recoverable from the submitted checkout.
Acceptance receipts identify the final SHA without a self-referential commit.

The V2I dry review ZIP measured 54,971,103 bytes, above the inherited 48 MiB
bound. The existing bundler permits 64 MiB for V2I only, retaining both complete
browser matrices and current media. This is packaging, not a scientific change.

## Repair acceptance (a02)

The a02 matrix adds the requested intermediate desktop viewport and checks normal
and silenced arena bounds, every visible game button, every summary button, and
pairwise slider-label intersections. Every lab performance measurement reports
both rAF frequency and simulated time advanced per wall second at the registered
test strength. The full game regression matrix uses the same four viewports.
The verification command block is an explicitly named region, resolving the
unsupported ARIA name on a generic preformatted element. Axe asserts the specific
incomplete result is absent as well as requiring no violations.

Evidence is isolated under `evidence/V2I/a02`, including acceptance receipts for
the final submitted SHA. Reproduce with:

```sh
uv run --offline python tools/run_acceptance.py V2I --out evidence/V2I/a02/acceptance
uv run --offline python tools/review_bundle.py --milestone V2I --attempt 2 --base 05784243254e3b299cfc0ad8b377495df9e4578f --out reviews/V2I-a02.zip
```

The GIF inclusion bound follows the requested GitHub media limit; unchanged bulk
assets remain hash-inventoried. No scientific identity or game mechanic changes.

The a02 ZIP bound is 96 MiB to retain the fourth viewport in both complete
browser matrices and the longer, higher-frame-rate media. Its actual byte count
is reported after packaging; each GIF remains below the requested media limit.
