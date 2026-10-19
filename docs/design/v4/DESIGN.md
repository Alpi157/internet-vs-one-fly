# Catch the Fly: "Under the microscope" design reference (v4)

This folder is the approved visual reference for the redesign. Screens are in `screens/`, the mockup sources in `source/` (reference only: they were built in a design tool whose runtime is not included, so read them for exact values, do not run them), and reusable art in `assets/`.

The mockups use placeholder data in three places. The implementation must replace each with real data:
1. The brain image in the mockups is an illustration. The game draws the real V2G anatomy assets (composite: brain frontal view, nerve cord ventral view).
2. Lab chart curves are illustrative except at s = 0.039. The game reads every curve, band and number from the generated results.
3. "What it sees" (the hexagon inset on the phone game) is not supported by the model, which uses feature-level vision. See "Looming input" below.

## 1. Tokens

Colors (dark UI, light specimen):
- page background `#000000`; raised surface (sheets, panels) `#0A0C0A`; hairline `#1F2420` / `#262B27`; control border `#3A413B`
- text primary `#E9EDE6`, secondary `#C9D0C8`, tertiary `#9BA59C` (the lowest allowed for text on black)
- spike green `#63F29A`: used only for neural activity, the word "Escaped", escape pips and data bands. Never decorative.
- link `#7FEFAA`, hover `#B8F7CF`; focus ring `2px solid #7FEFAA`, offset 3px
- neuropil magenta `#C24FB8` (confocal-style tissue)
- specimen field: radial gradient `#F2F2EC` → `#E6E7E0` → `#CFD2CA` → `#9DA39B` at the rim, plus an inner rim shadow; field ink `#1E231F`
- status pill: `rgba(11,13,11,0.82)` background, `#F2F4F0` text, green dot

Type:
- Display and numbers: **Doto** weight 900. Text and UI: **Atkinson Hyperlegible Next** 400/600/700.
- Self-host both (OFL) as subset WOFF2 files. No requests to Google Fonts: the game promises no tracking.
- Doto's period renders as a plus sign. For decimals in Doto, render a custom dot: inline-block, 0.16em square, border-radius 35%, currentColor, margins 0.08em/0.1em. Keep the real number in visually hidden text for screen readers.
- Line-height at least 1.05 for Doto and 1.3 for text. Never let lines overlap.
- Scale (phone): screen title 29 to 34, outcome word 40, score 72, stat number 32 to 34, body 15 to 16, caption 12 to 13. Desktop: page title 52, panel title 40.

Shape and spacing:
- Phone side gutter 16px. Desktop page padding 40px, max content width 1360px.
- Primary and secondary buttons: height 52 (phone) or 48 (desktop), fully rounded. Icon buttons 44×44. Every hit target at least 44px.
- Bottom sheet: top radius 22, grabber 40×5. Panels: radius 16 to 20. Brain image: radius 12.
- Icons: 16px inline stroke SVG, 1.8px stroke, round caps. No emoji.

## 2. Components

### MicroscopeField
- The field is a circle with a light brightfield look: the gradient above, a rim shadow, faint dust specks and a couple of lint fibres. See `screens/Field.png` and `assets/field-reference.svg`.
- **The arena is a circle** (game profile v2.7). The playable arena circle must be fully visible. The visual field circle is larger than the arena by a margin ring that shows the chamber edge: a subtle darker meniscus where the fly bounces.
  - Phone: field 430px, centred and allowed to bleed past the screen edges. The arena circle is at most 374px across, fully on screen.
  - Desktop: field 680px, arena about 640px.
- **The fly** uses `assets/fly.svg`, a male D. melanogaster in dorsal view: greyish tan, black abdominal tip, brick-red eyes, clear wings longer than the abdomen. Its display length is a declared constant, L = 2.0 arena units, stored in a UI display profile.
  - Rotate it to the body heading.
  - Gait: subtle leg swing from the frame's gait counter. Off under reduced motion.
  - In the air: wings spread, a slightly larger scale, the shadow offset, and a faint path trail. Off under reduced motion.
- **The hand**: a defocused hand shadow approaching the aim point. Its darkest core equals the hit zone at impact, and it grows and sharpens with strike progress. Draw the hit zone as a thin dashed ring at the exact strike radius. Fingers are visibly lighter than the core and never suggest a larger hit area.
- **Status pill**, top centre, during a strike: "Hand lands in N ms", counting down from the real impact tick.
- **Scale bar** at the bottom centre: length L, label "1 fly length". The arena has no physical units, so never show millimetres.
- **Outcome stamp** at impact (replaces "GOTCHA" and "NICE TRY"): "Caught" or "Escaped", with Escaped in spike green. Text is 15 to 16px bold, inside a dark pill.

### BrainView (WebGL2, canvas fallback)
- **Source**: V2G assets. Composite layout, brain frontal view on top and nerve cord ventral view below, with the fly's right on the viewer's left. Layout bridges are drawn as faint lines in the neuron colour, never amber dashes. A caption must always be reachable: "Brain: front view. Nerve cord: underside view. Real MaleCNS neuron skeletons, simplified for display."
- **Look**: black background.
  - Neuropils: filled magenta at low alpha, with a fine grain (noise texture) and a soft glow, giving a confocal look. Internal ROI boundaries are faint darker seams.
  - Neurons, at rest: interior about 6 to 8% alpha, highlighted groups (LC4, LPLC2, giant fiber, walking DNs, named ports) about 18 to 25%.
  - Neurons, active: lit in spike green with an additive glow.
- **Activity only from recorded spikes** in frames.
  - A neuron lights the moment it spikes and fades with a display decay of tau = 60 ms of simulated time. Document this decay as display smoothing.
  - The whole neuron lights at once. Never animate travelling pulses: the model has point neurons.
- **Modes**:
  - "Brain": a crop of the brain panel, landscape, about 1.7:1. Default.
  - "Whole CNS": the full composite, portrait.
  - Phone replay sheet: Brain mode, with a small segmented control "Brain | Whole CNS"; Whole CNS scrolls within the sheet.
  - Desktop: Brain mode in the side panel, same control.
- **Labels**, tertiary text with a dark halo, collision-free: "Giant fiber" at the soma, "LC4" and "LPLC2" at their glomeruli, plus a real "100 µm" scale bar. Label only groups that exist in the circuit.
- **Performance**:
  - A static layer of neuropils and resting neurons is rendered once to a texture.
  - Each frame draws only neurons whose activity exceeds a threshold: per-neuron index ranges, or an activity texture sampled in the vertex shader.
  - Phone LOD on touch or narrow screens, desktop LOD otherwise. Lazy-load after first paint.
  - Fallback without WebGL2: canvas soma dots in the same colours.

### Timeline (replay)
- Three tracks: "Hand height", "Looming cells" (LC4 plus LPLC2 population rate) and "Giant fiber" (spike ticks).
- Show the impact line, a playhead in link green, and the axis ends "−200 ms" and "hand lands".
- Track labels are 12px tertiary. The SVG or canvas scales to its container width.

### Pips and stats
- Six pips, 14px:
  - caught: filled `#E9EDE6`;
  - escaped: green ring, 2px;
  - current: white ring with a 4px dot;
  - remaining: 1.5px `#3A413B` ring.
- The stat number sits above its label, never on the same baseline.

### Segmented control
- A pill container with an inset 1px border. Options are 40px tall, and the selected option is filled `#E9EDE6` with dark text.
- Implement it with real radio semantics (radiogroup and radio, arrow keys).

### Looming input (replaces "What it sees")
- A small meter beside the hint row showing the encoder's actual looming inputs (size and expansion) during a strike, taken from the same function the encoder uses. Label it "Looming input".
- If those values cannot be exposed without changing kernel code, omit the meter.

## 3. Screens

### Phone game (`screens/Main.png`)
- Header: Doto title "Catch the fly"; subtitle "5,555 neurons, wired as mapped in a real male fruit fly."; a 44px "?" button that opens How it works.
- Stats row directly above the field: "N caught" on the left; six pips plus "Hand X of 6" on the right.
- The field, with the hint row below it: "Tap the fly to slap. Hold for a bigger, slower hand."
- Bottom row: "Replay last hand" and "Wiring lab", both outline buttons, since the field itself is the primary action.
- Vertical space is distributed evenly; there is no large empty band.

### Phone replay sheet (`screens/Replay.png`)
- A bottom sheet over the dimmed game: caption "Hand X of 6", Doto outcome word ("Escaped" in green, "Caught" in white), and a sentence built from impact data:
  - escaped: "Its giant fiber fired N ms before your hand landed." Add "Takeoff began M ms before impact." when that value exists;
  - caught before any giant-fiber spike: "Its giant fiber did not fire before your hand landed."
- Then BrainView, the timeline, and a pause control with "Quarter speed. Every flash is a recorded spike."
- Buttons: "Next hand" (primary) and "Save clip". A close button (44px) and Escape both close the sheet. Focus is trapped while it is open and returns afterwards.

### Phone round summary (`screens/Round.png`)
- "Round over"; scoreboard "The fly" N (green) against "You" N.
- Six hand cells with pips and the legend.
- Share card: BrainView still of the best escape, Doto "N ms", "A simulated fruit fly brain beat my hand by N ms.", and the site URL.
- Buttons: "Share" (Web Share API with a PNG card, falling back to download) and "Play again" (primary). Below them, a link row: "Is it the wiring, or just speed?" / "Scramble its connections and find out".

### Phone lab (`screens/Lab.png`, `screens/Lab-strength.png`)
- Back link, Doto title "Scramble the wiring", "Same neurons and partner counts. Only who connects to whom is shuffled."
- Segmented control: "Shuffle partners" (N-SIGN demo) or "Keep input strength" (N-STRENGTH demo), with a one-line note under it:
  - "Each neuron's total input strength changes.";
  - or "Total input strength kept. The gap mostly closes."
- Two BrainViews: "Real wiring", and "Shuffled partners" or "Shuffled, strength kept". Under each, Doto rate + "spikes a second".
- Connection-strength slider, with "Game setting" and "Registered test" ticks computed from the real grid and metadata. The a02 reviewer correction distinguishes the game calibration from the H0b test strength.
- Chart: the selected family's band filled, the other family's band as a dashed outline, the measured line, a 50 Hz reference and the marker.
- Link: "Both tests were registered before they ran. Read the results". Primary button "Drop the hand on both".

### Desktop game (`screens/Desktop-Game.png`)
- Header: Doto wordmark plus subtitle; nav "Play", "Wiring lab", "How it works", "Code and data ↗".
- Left: stats, the 680px field, and the hint "Click the fly to slap. Hold the button for a bigger, slower hand. Space works too."
- Right panel: live brain during play (dim), switching to the last-hand replay after each strike: outcome, sentence, BrainView, timeline, and the buttons "Save clip" and "Is it the wiring? Scramble it".

### Desktop lab (`screens/Desktop-Lab.png`, `screens/Desktop-Lab-strength.png`)
- Left column: title, explanatory paragraph, a card with the shuffle-type control, note and slider, the results link, and the primary button.
- Right: two large BrainViews with Doto rates, and the chart below.
- Paragraph text: "Same neurons, each with the same number of excitatory and inhibitory partners. Only who connects to whom is shuffled, and the shuffled brains run hot. Then also keep each neuron's total input strength: most of the gap closes. In this model, how unevenly input strength is spread matters more than which partners connect." Every number is generated.

## 4. Interaction and accessibility
- Pointer: press to aim, hold to charge, release to strike. Show the charge as a ring at the aim point with the strike name ("Flick", "Slap", "Swat").
- Keyboard: the field is focusable. Arrow keys move a visible aim reticle; holding Space charges and releasing strikes. Enter strikes at the reticle.
- Screen readers: an aria-live region announces outcomes and the hand count.
- Reduced motion: no shake, no flash, no gait swing and no trails, with replay still available. A sound toggle and haptics are kept, and haptics respect reduced motion.
- Contrast: at least 4.5:1 for all text, 3:1 for large numerals and UI boundaries. Real buttons, links and inputs, each with a label.
- No fake status bars, no emoji, no gradients as decoration on UI chrome.
