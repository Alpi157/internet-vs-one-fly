# Catch the Fly: design v5, "make it understandable"

v5 is an update on top of `docs/design/v4/DESIGN.md`, which still defines the tokens, fonts, components and accessibility rules. The look stays the same. v5 changes what a first-time visitor understands, how the game gives feedback, and how the wiring lab and How it works explain the science.

The owner approved these mockups on 2026-10-19. One rule: the lab keeps the name **Wiring lab** everywhere.

Contents:
- `screens/` holds the approved renders: phone screens at 2x, desktop screens at 1x.
- `source/` holds the mockup sources. They are reference only: they run in a design tool, and their `/_blob/` image links point to that tool.
- `assets/` holds the four brain frames used in the mockups. They are real recorded BrainView frames, with their labels removed.

## 0. Goal

Within 10 seconds, a visitor should know three things:
1. This fly has a brain: a simulation of 5,555 neurons wired as in a real fruit fly.
2. You can try to swat it.
3. After each hand, you can look inside its head.

Use plain words first and technical names second, for example "Escape neuron (giant fiber)" and "Looming detectors (LC4, LPLC2)". Every number stays generated or live, as before.

## 1. First visit (`screens/V5-Intro-1.png`, `V5-Intro-2.png`, `V5-Intro-3.png`)

- **When it shows.** Show the three cards on the first visit. Store a "seen" flag in localStorage, wrapped in try/catch. If storage fails, show the cards once per page load.
- **Controls.** "Skip" goes straight to the game. The "?" button reopens the cards.
- **Desktop.** The same three cards appear in a centered modal (max-width 560 px) over the game.
- **Accessibility.** The modal is a real dialog: it traps focus, closes with Escape, and returns focus afterwards.
- **Copy, card 1.**
  - Title: "This fly has a brain".
  - Body: "5,555 neurons, connected as in a real fruit fly’s brain, run live in your browser." and "Its escapes are not scripted. They come from those neurons."
  - Caption under the image: "Real neuron shapes from the MaleCNS map of a male fruit fly."
  - Generate the count.
- **Copy, card 2.**
  - Title: "Try to swat it".
  - Tiles: "Tap / Fast hand / Small and quick. Hard for it to react in time." and "Hold / Big, slow hand / Easy to aim. But the fly has time to see it coming."
  - Body: "Six hands per round. The fly walks, stops and turns, so aim where it will be."
- **Copy, card 3.**
  - Title: "Then look inside its head".
  - Body: "After every hand, a replay shows the cells that saw your hand coming and the one that made it jump." and "Every flash is a spike that happened in the simulation."
  - Button: "Play". Note: "Reopen this anytime with the ? button."
- **Images.** Card 1 uses a recorded BrainView frame. Card 3 uses a recorded frame plus a small static three-track timeline. Use real recorded frames, never illustrations.

## 2. Header and footer

- **Header subtitle**, phone and desktop: "A fly brain simulated from its real wiring. Try to swat it."
- **Desktop nav:** "Play", "Wiring lab", "How it works", "Code ↗".
- **Footer** on every desktop page, and at the end of How it works on phone:
  - "Made by Alpar Arman · GitHub", where GitHub links to https://github.com/Alpi157;
  - "Wiring and neuron shapes: MaleCNS v1.0, Janelia FlyEM, CC BY 4.0 · Data: 10.5281/zenodo.23409752".
  - Only GitHub; no other personal links.

## 3. Two hands (game profile v2.9)

- **Mapping.**
  - A tap or click shorter than the hold threshold gives the **fast hand**: the current flick, speed 0.04, radius 0.8, unchanged.
  - Holding past the threshold gives the **big, slow hand**: the current swat, speed 0.025, radius 1.4, unchanged.
  - The middle slap tier is removed from input mapping.
  - Declare one threshold of 300 ms in the profile.
- **Legend.** It is always visible and large.
  - Phone: two tiles under the field, "Tap / Fast hand" and "Hold / Big, slow hand", each at least 60 px tall.
  - Desktop: two tiles under the field, "Click for a fast hand" and "Hold for a big, slow hand", plus a small line "Keyboard: arrow keys aim, Space works like the mouse button."
  - Remove the old one-line hint.
- **While holding** (`screens/V5-Charge.png`).
  - A ring grows around the aim point.
  - Before the threshold, the label reads "Fast hand".
  - After the threshold, a pill above the ring reads "Big, slow hand" with a smaller second line, "Release to swat". The Hold tile fills (#E9EDE6 background, dark text). The dashed circle shows the exact swat radius.
  - Announce "Big, slow hand ready" once through aria-live.

## 4. Outcome feedback (`screens/V5-Caught.png`, `V5-Escaped.png`)

- **Stamp.** At impact, show a stamp at the top of the field.
  - Style: a dark plate, rgba(8,10,8,0.88), radius 22, about 78% of the field width.
  - Word: Doto 900, "Caught" in #F2F4F0 or "Escaped" in #63F29A. Size is 0.115 × field diameter, capped at 64 px.
  - Below the word: one plain line, 14 to 19 px.
  - The stamp stays for 1.6 s, then fades. Under reduced motion there is no animation, but the same duration.
  - Announce the word and the line through aria-live.
- **After the stamp.** On phone, the buttons become "See inside its head" (primary) and "Next hand". The replay sheet opens automatically when the stamp ends. On desktop, the right panel switches to the replay as now.
- **Line by outcome**, generated from the impact record and the V2K outcome branches:
  - takeoff escape: "It saw your hand coming and jumped {takeoff lead} ms before it landed."
  - walk-out, escape neuron silent: "It walked out from under your hand."
  - walk-out, escape neuron fired but no takeoff before impact: "It walked out from under your hand. Its escape neuron fired too late to jump."
  - caught, escape neuron fired: "Too quick for it. It saw your hand only {escape neuron lead} ms before it landed."
  - caught, escape neuron silent: "It never saw it coming."
  The replay sheet and desktop panel use the same main line. Where it exists, add a detail line: "Escape neuron (giant fiber) fired {lead} ms before impact."
- **Caught visual.**
  - The hand stays pressed on the fly for 500 ms: a less blurred hand, a dark core exactly the hit radius, and the fly dimmed underneath.
  - The field shakes 6 px for 150 ms, except under reduced motion.
  - Haptics stay as now.

## 5. Takeoff, out of focus (`screens/V5-Flight.png`)

- **Visual.**
  - A flying fly leaves the focal plane: it scales up to about 1.55×, blurs to about 2.4 px (in units of a 358 px field), spreads its wings and tucks its legs.
  - Its shadow stays on the glass, smaller and fainter, with the offset growing with height.
  - A faint dotted trail runs from the takeoff point.
  - On landing it returns to focus, and a faint ring fades out over 400 ms.
  - Under reduced motion, keep a static airborne pose (scale and shadow offset, no blur animation, no trail).
- **Mechanics, game profile v2.9.**
  - The first 120 ms of takeoff stay identical to v2.8: same speed, direction and jitter rules. This keeps outcomes for impacts inside that window unchanged.
  - After that, the fly keeps flying until its total displacement is about 3 fly lengths (6 arena units), then lands.
  - Declare the speed and duration in the profile. Wall reflection is unchanged.
  - Report how many bot outcomes change compared with v2.8, and why.

## 6. Plain words in BrainView and the replay (`screens/V5-Replay.png`)

- **BrainView labels:** "Escape neuron" (at the giant fiber), "LC4", "LPLC2".
- **Line under the brain:** "LC4 and LPLC2 are looming detectors: eye cells that fire when something grows fast. The escape neuron (giant fiber) triggers the jump."
- **Timeline track names:** "Your hand", "Looming detectors", "Escape neuron".
- **Desktop toggle:** "Brain | Whole nervous system". On phone it may stay "Brain | Whole CNS".

## 7. Desktop uses the full width (`screens/V5-Desktop-Game.png`)

- **No container.** Drop the 1360 px max-width container. Pages fill the window with 56 px side padding.
- **Field.** The field fits the available height: between 420 and 760 px across, and the whole arena is always visible.
- **Right panel.** It takes the remaining width.
  - Top row: Doto outcome word and line on the left, "Next hand" and "Save clip" on the right.
  - Then a large BrainView at the full panel width.
  - Then the timeline on the left and the explanation plus "Is it the wiring? Open the wiring lab →" on the right.
- **Checks.** Keep every existing bounds check. Add 1920×1080 and 2560×1440 with the arena fully visible.

## 8. Wiring lab as a three-step story (`screens/V5-Lab-1.png`, `V5-Lab-2.png`, `V5-Lab-3.png`, `V5-Desktop-Lab*.png`)

- **Name.** Keep the name "Wiring lab".
- **Steps.**
  - Phone: three screens with a step bar labelled "Wiring lab · Step N of 3".
  - Desktop: a stepper on the left; only the current step is expanded and has a "Next" button. The right side changes with the step.
- **Step 1.**
  - Title: "Is it the wiring?"
  - Body: "Take the real brain and make a fake copy. Every neuron keeps the same number of connections, but who connects to whom is shuffled at random. Then run both."
  - Brains: real wiring next to the N-SIGN demo.
  - Verdict: "The shuffled brain explodes into activity. The real one stays calm. So the wiring matters?"
  - Button: "Next: not so fast".
- **Step 2.**
  - Title: "Not so fast"
  - Body: "Shuffling changed something else too: some neurons ended up with far more input than before, others with less. So, before running it, I registered a stricter test: shuffle again, but every neuron keeps its total input."
  - Brains: real wiring next to the N-STRENGTH demo.
  - Verdict: "Most of the storm is gone. The exact partners matter much less than it first looked."
- **Step 3.**
  - Title: "What I learned"
  - Body: "In this model, the brain stays calm mostly because of how unevenly input is spread across neurons, not because of exactly who connects to whom." and "My stricter test overturned part of my first result. That is why you register a test before you run it."
  - Bars: three horizontal bars of the registered medians (real, shuffled, shuffled with the same input).
  - Caveat: "A simplified model of one 2,641-neuron circuit. In other circuits the results were mixed. Nothing here is a claim about living flies."
  - Links: "See all registered results" and "Read the preregistration".
- **Numbers.**
  - The big numbers are the registered T1a medians at the registered test strength (currently 2.65, 119.78 and 4.40 Hz), generated from the results. Show them as 2.7, 120 and 4.4, with the caption "Median spikes a second per neuron in the registered test, 499 shuffled copies."
  - Under each brain, a small live line: "live now: X spikes a second". Never mix live and registered numbers in one label.
  - Brains run live at the registered test strength, as now.
- **"Try it yourself"**, below the story on both phone and desktop:
  - **Connection strength:** the existing slider with its "Game setting" and "Registered test" ticks, the live brains, and the existing registered chart. On phone the chart may sit in a collapsed "Show the registered curves".
  - **"Switch off a cell type, then play":** four buttons, "LC4 off", "LPLC2 off", "Escape neuron off", "Steering off". These are the existing lesions, each starting a fresh round with the visible badge. Add the explanation line from the mockup.
  - **More:** the uncalibrated full shuffle stays inside a collapsed "More".

## 9. How it works (`screens/V5-How.png`)

- **Layout.**
  - Text column 740 px, wide sections 1120 px.
  - Body 18 to 19 px with line-height 1.65 to 1.7. Section spacing about 104 px.
  - h1 Doto 72, h2 Doto 40. On phone: h1 40, h2 30, body 17, section spacing 64.
- **Sections, in order.**
  1. Title and lead: "A fly brain, simulated from the real wiring diagram of a fruit fly. Here is what is real, what is simplified, and what I found."
  2. "From your hand to its jump": five boxes, "Your hand → Its eyes → 5,555 simulated neurons → Escape neuron → Jump". Use separate HTML elements, not one image, and stack them vertically on phone. Then the paragraph from the mockup, including the walking-drive sentence.
  3. "What is real, what is simplified": two cards with the mockup's lists.
  4. "The experiment in one minute": two paragraphs and three generated numbers, linking to the Wiring lab.
  5. "You can check all of it": preregistration dates with links, the DOI, cross-engine bit-exact parity ("In our tests…"), one-command acceptance.
  6. "Words used here": a glossary (Connectome, Spike, Looming detectors, Escape neuron, Preregistration).
  7. "For scientists: methods, statistics and limits": collapsed `<details>` holding today's generated tables, findings, model limits and walking disclosure, unchanged in substance.
  8. Footer.
- **Other pages.** model.html and preregistration.html follow the same type scale and spacing.

## 10. Unchanged

- Tokens, fonts, the microscope field look and the fly art all stay as in v4.
- The no-tracking and zero-third-party-requests rules stay.
- Activity is drawn only from recorded spikes.
- The round summary and share card stay, except for the wording rules in section 4.
