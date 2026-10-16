# Under the microscope (V2H)

The approved reference is `docs/design/v4/DESIGN.md`. The operator supplied the
original design ZIP SHA-256
`fd8e7bd0a9c2bb8ae18b34438b8ce82d4968662a09712e637d260cfac39dd6f3`;
the extracted reference is committed. Its mockup sources are reference only and
were never executed. The design's illustrated brain is replaced with unchanged
V2G MaleCNS anatomy. Labs and secondary scientific pages remain for V2I.

Game v2.7 changes the square chamber to a circle of radius `12 / sqrt(pi)`.
Both have area 144 abstract arena units squared. Position reflects radially,
repeating for overshoot; heading and airborne direction reflect about the same
outward normal. UI aims clamp to the circle and authoritative inputs reject
out-of-circle aims. Strike timing, collision ordering, takeoff and decoder stay
unchanged. v2.6 is retained under `profiles/game-v2-history/`.
`experiments/v2e_game_export.py --game-only` refreshes product and replay hashes
without rebuilding neural data. The regression test compares every neural
runtime field and profile identity to the accepted base, checks both freeze
manifests, and proves frame equality without wall contact.

`apps/play/public/data/display-v1.json` declares the fly's display length as
2.0 arena units and the scale label as “1 fly length”. There is no conversion to
physical fly size. The static brightfield is cached, with an inner meniscus at
the actual arena boundary. The supplied fly SVG is assembled into one pose atlas and rasterized once per
device pixel ratio. The original leg paths swing from the recorded gait counter;
the original wing paths spread in the airborne pose. Body heading stays exact. Scale changes and airborne pose are presentation only. The hand's
core reaches the actual hit radius at impact, marked by a dashed circle. The
pill and rim clock use recorded ticks; game time pauses during recorded replay.

The looming meter receives a frozen copy of `RunnerV2.step().encoded` through
the worker snapshot. Those are the actual encoder size and expansion features,
not a second visual model. A test compares the display copy to `encodeHand` at
every interval. No kernel source changes are needed. The copy never feeds back
into the simulation or decoder.

BrainView lazy-loads after first paint and checks skeleton body-ID order against
the executed circuit. Phone LOD is selected for touch or widths below 900 CSS
pixels; otherwise desktop LOD is used. The Brain crop is the default; Whole CNS
uses the complete V2G composite. The scale bar is 100 µm in the asset coordinate
system. Giant-fiber labels anchor to a recorded soma, and LC4/LPLC2 labels to
the centroid of their displayed brain-panel skeleton vertices. Separate label
slots avoid text collisions; leader lines retain the measured anchor positions.
Missing soma coordinates remain missing.

Each observed spike lights its neuron at its recorded tick. Display alpha is
`exp(-(display_tick - spike_tick) * 0.5 / 60)`, with a 0.02 display cutoff.
This 60 ms decay is **display smoothing**, not membrane voltage, persistent
firing, or a model parameter. Future spikes never light early. The renderer
never interpolates missing neural observations or draws travelling pulses.
The timeline uses the recorded strike, combined LC4/LPLC2 population rate and
giant-fiber spike ticks over the 200 ms before impact.

The static neuropil and resting skeleton layer is cached per view. To meet
render budgets, active highlighted groups use skeleton lines while active
interior neurons use their measured somata; absent somata have no invented
positions. An activity texture carries the observed decay, and only active
highlighted ranges enter the per-frame line draw. Interior somata are batched.
Resting interior and highlighted layers are composited at 7% and 22% opacity,
avoiding accumulated opacity from overlapping segments. WebGL2 is preferred;
without it, the same assets supply canvas soma dots. This active interior LOD
is a deliberate display deviation from lighting every interior arbor.

Native modal sheets trap focus, support Escape and restore focus; the round
summary stays open until Play again or a lab is chosen. The arena supports
arrow-key aiming, Space hold/release and Enter. Reduced motion disables gait,
trail and shake; haptics also stop. Recorded replay remains available. Sound is
an independent toggle. Controls use a lighter border than the reference's
lowest-contrast token to meet the required 3:1 boundary contrast.

The share PNG uses the greatest observed giant-fiber lead among escaped hands.
If no escaped hand has a measured lead, it reports the actual catch score rather
than inventing a lead or a claim that the brain beat the hand. Doto decimals use
a custom dot in exported cards. Font subsets and their original OFL licenses
are local; the browser matrix rejects any third-party request.

Engineering evidence is under `evidence/V2H/`: paired bots, the complete
three-browser/two-viewport screenshot matrix, axe results for each screen state,
keyboard-only full rounds, replay re-execution checks and performance reports.
Measurements use the existing headless harness and are not physical-phone
measurements. FPS is rAF opportunity count during live worker execution or
continuously looping recorded replay. Initial download excludes graph and
anatomy and lists every included resource, both actual and calculated gzip
bytes. Anatomy timing includes fetch, decompression, decode and GPU preparation;
JS heap is reported only where the browser exposes it.

There is no change to the neural model, kernel, graphs, runtime neural parameters,
frozen records/results, or V2G anatomy. No push, tag or deployment is performed.
Stage acceptance remains with the external reviewer.

The existing review bundler needed a V2H-only 48 MiB bound: its dry run was
23,966,349 bytes before additional clip/fallback checks, above the legacy 15 MiB
bound. This keeps the entire mandated screenshot matrix and logs in one ZIP.
