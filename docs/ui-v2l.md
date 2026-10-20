# V2L: make it understandable

The approved v5 reference was committed unchanged first, at
`b34c30ec396152e7cb4e75e6ae1c1b19d61f4fbb`. The supplied ZIP identity is
`7946ce58de65596873d10fcbfa3681f3b085fa76a15b01889976e97ec099bc9b`.
The extracted files are hash-inventoried in `evidence/V2L/reference.json` and
compared to that commit. The source ZIP was not present locally, so its supplied
hash is attributed to the owner. Mockup sources were read, never executed.
V4 remains the basis for fonts, tokens, fly art and accessibility.

Game v2.9 makes exactly the two owner-authorized mechanics changes recorded in
[D-V2L-GAME-01](../decisions/D-V2L-GAME-01.json): a press below 300 ms selects the
existing flick, while 300 ms or longer selects the existing swat. The slap has no
input tier. Flight uses the same speed, heading, jitter and reflection for its
first 120 ms, then continues at 0.018 arena units/ms until 330 ms: a nominal
5.94-unit path, about three displayed fly lengths. Reflection can reduce endpoint
displacement, so the declared distance describes the flight path. Replay pauses
and round termination can interrupt observation before landing; the clock and
round-ending rules are unchanged.

The selected A walking current, its RNG stream and neural routing stay unchanged.
The Python game adapter and TypeScript implement the same mapping and duration.
V2J's fixed binary64 length arithmetic remains in the game; the Python v2.9 loop
uses the same order. Legacy Python profiles retain their previous arithmetic.
Parity checks cover body bits, commands, walking state, reflected air direction,
spike counts, impact ordering, the 300 ms boundary and the first 120 ms. New game
logs use schema v4. Earlier schemas reject clearly when paired with v2.9, rather
than silently changing their dynamics. Kernel, graph, frozen neural parameters,
registered results, raw records, anatomy transports and earlier evidence are
hash-checked against the accepted base.

The Wiring lab worker stays byte-identical. It explicitly loads the unchanged
v2.8 profile, then disables the walking drive exactly as before. This preserves
its existing drop-hand mapping and both live simulations. Registered story
numbers come from the original T1a N-SIGN and stricter N-STRENGTH result tables,
through the existing publisher: 2.7, 120 and 4.4. The sample count, circuit sizes,
curves and medians are generated. Separate small live lines report observed
spikes over the existing bounded window; they never replace registered values.
The stricter control's approximate strength preservation and the full statistical
results remain available in the generated methods and model limits.

First-visit cards use actual recorded BrainView and timeline snapshots from the
hero recording. Their neuron count comes from the runtime. A native dialog traps
focus, supports Escape and restores the opener. Storage access is guarded; if it
fails, the introduction appears once per page load. The question-mark button
reopens it. Header, footer, legends, hold-ready announcement, replay track names,
BrainView labels, lesion labels and README use the approved plain-language copy.
How it works has the seven requested sections, generated numbers and preserved
methods in a collapsed detail. Model and preregistration pages share its type
scale. Every resource is local; outbound attribution links make no requests until
followed.

The outcome sentence is derived only from impact metadata. Takeoff requires a
strictly positive recorded onset lead; a walk-out remains a walking explanation.
The same main line appears in the field, replay and summary, with the separate
measured giant-fiber detail in replay. The stamp uses a 1.6 s presentation clock.
Caught feedback holds the recorded impact pose under the exact hit-radius hand
for 500 ms without changing the continuing runner trace. Airborne scale, tucked
legs, shadow, blur, trail and landing ring are display effects. Cached SVG blur
poses make defocus work in WebKit as well as Chromium and Firefox; the unmodified
fly SVG remains the source. Reduced motion uses a static airborne pose and omits
blur animation, trail, ring animation, shake and haptics. Activity still comes only
from recorded spikes, with the unchanged 60 simulated ms display fade.

The validation protocol, [ui-v2l.json](../profiles/ui-v2l.json), was frozen at
`78b554e` after the excluded seed-101 pipeline dry run. It fixes seeds 1-20, the
original V2J bot and repeated resting-swat schedules, the two hands, both limit
conditions and the unchanged safety bounds. No parameter is tuned. The final
acceptance runs both v2.8 and v2.9 on the submitted SHA, retains every opportunity
and censored outcome, and requires the v2.8 results to reproduce V2J exactly.
Fixed old inputs are also replayed under v2.9 until the first body divergence.
Per-round audits distinguish an impact after the old flight window from a changed
pose or resting eligibility carried into a later hand. Complete rates, changed
outcomes, causes, no-threat counts, circuit rates and resting-swat records are in
`evidence/V2L/validation.json`; the review narrative summarizes them.

The hero rule remains the first ascending seed whose current-position 600 ms swat
at 1.5 s escapes with a pre-impact neural takeoff. Every selection trial and all
separate diagnostic fixture probes are retained in provenance. The lead-in runs
at real speed, strike intervals at the inherited fivefold slowdown, and the final
three seconds use ordinary quarter-speed recorded replay. An unsolicited takeoff
in the selected seed's quiet lead-in is retained rather than edited or used to
change the selection. The lab GIF runs story step 1 then step 2 at the registered
test strength. The OG image and intro use the hero replay frame with the greatest
observed spike count. A ten-second review video contains an actual caught hand
and the selected escaped hand. Media hashes, dimensions, timing, inputs and source
identities are in [media provenance](media/media-provenance.json).

Interpretations and deviations from the renders:

- BrainView height is constrained on short desktop screens and capped on very
  large screens so its controls and the complete arena fit. The panel still uses
  the remaining window width; the field stays between 420 and 760 CSS pixels.
  Phone replay uses a compact brain crop to keep all modal controls in view.
- Story anatomy-mode switches and source/seed details are available with the live
  brains in Try it yourself. Keeping them out of the initial story leaves room for
  the three-step explanation and separates registered numbers from live rates.
- Long story and scientific pages scroll, as in the phone step-3 reference. Bounds
  checks require all game/modal controls and the arena to fit simultaneously.
  Flow-page controls are checked horizontally, then individually scrolled fully
  into the same viewport and checked in both axes. Each screenshot also gets the
  generic text/control overlap detector, axe and network checks.
- The existing higher-contrast control borders, active-interior soma LOD and
  measured label anchors are retained from V2H/V2I. No anatomical positions or
  missing observations are invented. Original source art stays unchanged.

The matrix includes all 18 requested states plus two reduced-motion states at
all six sizes, in Chromium, Firefox and WebKit, for en-US, ru-RU and de-DE. Intro
focus restoration and blocked storage are exercised in browsers. Frame rates are
headless rAF measurements while the real worker and recorded-spike renderer
advance, not physical-phone measurements. Both live lab families are measured.
The existing review bundler permits 512 MiB for V2L because 360 dry-run PNGs
already occupy 129 MB and the required final matrix contains 1,080 screenshots.
Every final screenshot is included; earlier scientific bulk remains hash-listed.
Final-SHA suite and acceptance receipts live under `evidence/V2L/acceptance`.
Software checks do not constitute external stage acceptance. No push, tag or
deployment is performed.

Reproduce the registered acceptance and package:

```sh
uv run --offline python tools/run_acceptance.py V2L --out evidence/V2L/acceptance
uv run --offline python tools/review_bundle.py --milestone V2L --attempt 1 --base f30ae501a21c71e714084bd378ae59d6e2144a9e --out reviews/V2L-a01.zip
```
