# V2M a01: replay polish and takeoff playtest

Production stays **game v2.9**. T0, T1, T2 and T3 are development-only owner playtests; no preset has been selected for production. This report submits work for external review and does not mark the stage accepted. The owner reports the starting commit `2cb59c0d6dca6c341c03e83ee5352d8955223f29` as `v2l-accepted`, deployed. The prior ledger review status is retained because no external verdict text was supplied.

## Declaration and preserved identities

`profiles/owner-takeoff-v2m.json` and `D-V2M-PLAYTEST-01.json` were committed at `e71d37d` after the excluded seed-101 dry run and before the 20-seed diagnosis or preset measurements. All four fixed speeds are retained; there was no selection search or tuning. The parity harness corrected its neuron-count field lookup after its first execution failed before comparing frames. The protocol and executed model were unchanged.

The production profiles, game loops, walking drive A, kernel, graphs, frozen neural parameters, lab worker and lab profile, registered results, V2G anatomy assets, all prior V2J/V2K/V2L evidence and review ZIPs are checked against their pre-work hashes. The existing raw archive manifest is checked in full. New views consume the same recorded lab spikes; no new simulation or drive is introduced. `evidence/V2M/protected.json`, `prior-preservation.json` and `preservation-check.json` contain the receipts.

## Diagnosis

Every row is 20 seeds (1 through 20), six opportunities per seed, with no censored bot opportunities. Bots retain the V2J warmup (1.5 s), quiet gap (1 s), 30 s round, boundary projection and RNG stream 71. Bot 1 aims at the observed position; bot 2 leads using the observed held velocity and hand fall time. Bot 4 waits for 150 ms of observed grounded speed no greater than 0.5 fly lengths/s. Bot 5 uses that same rest observation and aims at the observed position. No stop is forced.

For bots 1, 2 and 4, human-like limits remain 200 ms reaction and independent uniform +/-0.3 unit aim noise per axis. Bot 5 uses the requested skilled limits: 120 ms and +/-0.15. The unrestricted condition removes delay and noise for every bot; consequently unrestricted bots 4 and 5 match exactly. The human-like schedules observe before their reaction interval; they do not reacquire the fly at release.

| Bot | Limits | v2.8 fast catches | v2.9 fast catches |
|---|---|---:|---:|
| 1 | none | 68/120 (56.67%) | 69/120 (57.50%) |
| 1 | human-like | 32/120 (26.67%) | 24/120 (20.00%) |
| 2 | none | 97/120 (80.83%) | 93/120 (77.50%) |
| 2 | human-like | 42/120 (35.00%) | 43/120 (35.83%) |
| 4 | none | 100/120 (83.33%) | 102/120 (85.00%) |
| 4 | human-like | 41/120 (34.17%) | 37/120 (30.83%) |
| 5 | none | 100/120 (83.33%) | 102/120 (85.00%) |
| 5 | skilled | 40/120 (33.33%) | 45/120 (37.50%) |

The stop-and-tap opportunity is real: unrestricted resting fast hands catch 85% in v2.9. Bot 5 with its specified reaction and aim error catches 37.5%, so this exact workload does not reproduce the owner's five catches in six hands. It does not estimate the owner's personal catch rate. The typical resting takeoff starts only 20 ms before impact. At the declared current speed, that permits only about 0.36 unit of nominal airborne travel before the hand arrives, while the fast-hand radius is 0.8. This is a geometric explanation inferred from the recorded onset leads and declared physics, not a neural retuning proposal.

Onset leads below use every resolved unrestricted bot-4 fast hand after the rest observation. Null means no recorded takeoff onset associated with that impact; nulls are excluded from quantiles and retained in raw records. Quantiles use the declared nearest-rank rule.

| Profile | Onsets / impacts | Min | p10 | p25 | Median | p75 | p90 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v28 | 115/120 | 10 ms | 10 ms | 20 ms | 20 ms | 20 ms | 20 ms | 60 ms |
| v29 | 118/120 | 10 ms | 10 ms | 20 ms | 20 ms | 20 ms | 20 ms | 40 ms |

For limited bot 5, median onset lead is 40 ms in both versions; the ranges are 10 to 70 ms, with 13/120 null onsets in v2.8 and 15/120 in v2.9. Full distributions, every impact, observed pose and censoring field are retained in `evidence/V2M/diagnosis.json`. Bots 1, 2 and 4 reproduce V2L baseline records exactly.

## Fixed preset measurements

Takeoff speed is abstract body physics, not a neural or biological parameter. Duration is `round((6 / speed) / 10) * 10` ms to respect the existing 10 ms movement clock. Every flight uses its preset speed throughout. Reflections preserve the existing rule, so net displacement can be less than integrated path length. Direction, jitter, onset, hands, walking and neurons are unchanged.

| Preset | Speed (units/ms) | Duration | Nominal path | Spontaneous takeoffs | Circuit mean | Resting swat escapes | Censored swats | Safety |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| T0 | 0.018 | 330 ms | 5.94 units | 0.010/s | 4.275 Hz | 179/200 (89.5%) | 2 | PASS |
| T1 | 0.036 | 170 ms | 6.12 units | 0.010/s | 4.275 Hz | 193/200 (96.5%) | 1 | PASS |
| T2 | 0.040 | 150 ms | 6.00 units | 0.010/s | 4.275 Hz | 191/200 (95.5%) | 1 | PASS |
| T3 | 0.045 | 130 ms | 5.85 units | 0.010/s | 4.275 Hz | 189/200 (94.5%) | 3 | PASS |

All presets have six spontaneous takeoffs in 600 no-threat seconds, below 0.05/s. Every per-seed circuit rate is below 50 Hz. Resting swat uses the exact V2J two five-strike rounds per seed, 200 ms below decoded movement deadbands and environment seed `1000 + seed + 100 * round`; unresolved opportunities count as nonescapes. All exceed the original matched V2J 176/200 (88%) safety threshold. Python/TypeScript body, held commands, spikes, reflection and 3,000-interval walking-drive/reset parity pass for every preset; exact profile-bound replay passes.

Each cell below is **fast / slow catch percentage**, with 120 resolved hands per number and zero censored bot opportunities. Slow means the existing 600 ms hold swat; fast uses an 80 ms hold.

| Bot | Limits | T0 | T1 | T2 | T3 |
|---|---|---:|---:|---:|---:|
| 1 | none | 57.50% / 7.50% | 46.67% / 1.67% | 17.50% / 0.83% | 7.50% / 1.67% |
| 1 | human-like | 20.00% / 4.17% | 7.50% / 1.67% | 5.00% / 1.67% | 4.17% / 4.17% |
| 2 | none | 77.50% / 20.83% | 63.33% / 6.67% | 60.00% / 5.83% | 29.17% / 3.33% |
| 2 | human-like | 35.83% / 16.67% | 12.50% / 3.33% | 11.67% / 0.83% | 8.33% / 2.50% |
| 4 | none | 85.00% / 12.50% | 70.83% / 2.50% | 21.67% / 0.00% | 17.50% / 4.17% |
| 4 | human-like | 30.83% / 5.00% | 9.17% / 5.00% | 10.83% / 1.67% | 10.00% / 4.17% |
| 5 | none | 85.00% / 12.50% | 70.83% / 2.50% | 21.67% / 0.00% | 17.50% / 4.17% |
| 5 | skilled | 37.50% / 4.17% | 10.83% / 5.83% | 11.67% / 7.50% | 8.33% / 2.50% |

Full per-opportunity records and quiet traces are under `evidence/V2M/presets/`. `profiles/owner-takeoff-v2m-selected.json` offers exactly the safety-passing fixed presets; the production bundle removes the preview module, data and activation path.

## UI changes and evidence

- Desktop continuation is a 56 px primary field button after the stamp, with the Space hint and paused explanation. The panel action remains. Hand 6 says “See your round”. Phone actions stack full width without wrapping. Space and Enter advance from the field/replay surface; text, range, select and explicit playback controls keep their own keyboard actions.
- The replay playhead selects recorded frames only. Arrows move one frame, PageUp/PageDown ten, Home/End to the ends. Scrubbing pauses and clears the transient impact stamp so the field, timeline and BrainView agree. The timeline includes the entire recorded replay and labels time relative to impact. Display decay is recomputed from recorded spikes through that frame; scrubbing and normal playback are compared for exact frame, activity array and rendered image equality.
- Whole nervous system is fitted without inner scrolling. Landscape boxes transform the existing brain and cord panels side by side; portrait boxes retain the stack. Labels use 14 CSS px, stacking their header positions in narrow boxes. The scale bar keeps anatomical units. The native full-screen dialog restores focus on Escape. Assets and coordinates on disk are unchanged.
- Try it yourself is full-width with two stacked blocks. Connection strength stays open. Its two live BrainViews display the same recorded worker stream as the story; only visible views repaint. When both sections show the same view, they share the rasterized recorded activity through a shared canvas image and draw their fixed-size labels independently; this avoids four simultaneous geometry passes on wide screens. Lab activity canvases use 360 px backing widths; labels keep their independent 14 CSS px rendering. All recorded spikes and original anatomy assets are retained. Dense spike-history and draw-index loops use typed buffers; an independent sparse oracle checks exact activity at every frame. Four direct geometry views and the intermediate copy paths missed the WebKit gate; their failed receipts are retained. Chromium and Firefox copy the recorded canvas synchronously; WebKit uses a local canvas stream to avoid its slower GPU readback. Stream delivery is checked using presented-frame callbacks, with direct rendering as a stalled-stream fallback. Time spent off screen does not count as a stall; acceptance also measures returning to the story after using Try it yourself. The intermediate Firefox manual-capture failure and Chromium stream FPS failure are also retained. The chart is open on desktop and can collapse on phone. Four lesion cards form a desktop row.
- Intro focus starts on the card title; the next Tab reaches Next in DOM order.

The matrix covers Chromium, Firefox and WebKit at 390x844, 1440x900, 1920x1080 and 2560x1440, in en-US and ru-RU. Every captured state checks overlap, axe WCAG A/AA, bounds, locale formatting and same-origin requests. The portrait anatomy fixture uses a 210x340 display box within the expansion dialog to exercise the container contract at every viewport. Long lab content scrolls as designed; each control is individually scrolled fully into view and checked. The arena and modal controls must fit simultaneously. Browser receipts and screenshots are under `evidence/V2M/browser/`; preflight failures are retained separately.

## Hero encoding

The exact 153 retained V2L PNG frames, order and 50 ms duration are unchanged. The 112-color palette weights semantic green and tan body shades; no simulation or scene was re-recorded. The new GIF is 7,653,523 bytes. Stamp sample at frame 65, (171,156): source RGB (99,242,154), GIF (99,238,152). Panel title at frame 110, (475,104): source (101,242,152), GIF (99,238,152). Fly body at frame 20, (343,286): source (137,108,79), GIF (135,110,80). Source frame hashes and historical capture identities are recorded in the media provenance; the original V2L provenance is retained unchanged. All 153 source PNGs are included under `evidence/V2M/hero-source-frames`; `.venv/bin/python apps/play/test/media-gifs.py --v2m` reproduces the encoding. Existing alt descriptions still describe those same frames.

## Interpretation and final acceptance

Duration rounding is the only interpretation needed for the requested six-unit path; nominal paths range from 5.85 to 6.12 units. Mobile replay replaces the old explanatory paragraph with the requested controls; cell names, recorded-spike display, settings link and full explanatory pages remain. Keyboard shortcuts preserve explicit button actions rather than stealing Space/Enter from playback buttons. No other requested behavior is omitted.

The acceptance registry contains 29 commands for V2M. Final-SHA receipts are written under `evidence/V2M/acceptance/`; the final preservation check requires diagnosis, all four presets and parity to match the final commit. The external acceptance decision and production preset selection remain pending. Nothing is pushed, tagged or deployed.

## Owner playtest in WSL

```bash
cd ~/Projects/FlyBench
npm --prefix apps/play run dev -- --port 5173 --strictPort
```

Open these in the Windows browser while the WSL command runs:

- http://localhost:5173/internet-vs-one-fly/?preview=T0
- http://localhost:5173/internet-vs-one-fly/?preview=T1
- http://localhost:5173/internet-vs-one-fly/?preview=T2
- http://localhost:5173/internet-vs-one-fly/?preview=T3

The badge identifies the active preset. Without `preview`, the development server also runs ordinary v2.9. Stop it with Ctrl+C. These preview URLs do not activate in production.
