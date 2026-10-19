# V2J: walking design gate missed; layout and locale repair

No declared point passed all targets. No v2.8 point is selected or activated.
The shipped game remains v2.7. The new game-only current adapter is opt-in and
available for review. This is not an accepted stage or a claim about living flies.

The owner-authorized drive can be added without editing frozen files. Both freeze
manifests, the kernel, decoder, encoder, graphs, frozen parameters, registered
results, existing raw records and V2G anatomy remain unchanged. The lab continues
to use the original runner without walking current. Arena, takeoff and strike
mechanics remain v2.7. No push, tag, deployment or third-party request is authorized.

## Diagnosis before implementation

Initial diagnosis executed the unmodified base commit; the harness was then
committed and repeated without a drive. Twenty seeds (1 through 20), 30 seconds
each. One fly length is the existing display profile's two arena units.
The registered moving deadband includes turning in place; it is not a measure of
visible travel. Grounded translation above that speed deadband occurred in only
0.025% of intervals. Almost all baseline path length came from takeoffs.

| No-threat measure | Result |
|---|---:|
| Moving intervals | 38.628% |
| Completed movement bouts | 2927 |
| Median completed movement bout | 60 ms |
| Observed completed bout range | 10 to 490 ms |
| Mean path per 30 s | 0.342750 fly lengths |
| Mean net displacement per 30 s | 0.310861 fly lengths |
| Spontaneous takeoffs | 0.010/s |

| Decoder group | Mean spikes/s/neuron |
|---|---:|
| escape_left | 0.010000 |
| escape_right | 0.000000 |
| backward | 0.001250 |
| turn_left | 1.458333 |
| turn_right | 1.306667 |
| forward | 0.000000 |

Escape means a physical miss in the design gate. A neural escape request is reported separately. Each strike type has 200 attempts: 20 neural seeds, two independent five-strike rounds per seed. Neural state persists within each round. Before each strike, wait for 200 ms grounded below the registered movement deadband; aim exactly at the current position. Environment seeds are 1000 + neural seed + 100 * round. These are descriptive repeated-strike results, not 200 independent biological samples.

| Resting-fly strike | Neural onset before impact | Physical escape | Censored |
|---|---:|---:|---:|
| flick | 100.0% | 0.0% | 0 |
| slap | 94.0% | 0.0% | 0 |
| swat | 100.0% | 88.0% | 0 |

## Declared drive and grid

Protocol: [walking-grid-v1.json](../profiles/walking-grid-v1.json), frozen by commit
`88ab948`. The initial one-second pipeline dry run found that near-threshold
current did not activate the forward ports. Baseline membrane/current inspection
showed strong inhibition, motivating the disclosed pre-freeze amplitude revision.
This is pilot-informed game design. It is not confirmatory science.

Forward amplitudes: 1.5, 1.75, 2.0. Turn sigma: 0.5, 1.0. Mean walk: 1.0, 1.5 s.
Mean stop: 0.6, 1.0 s. All 24 combinations use seeds 101 through 104 for 30-second
no-threat rounds and the declared bots/resting-swat workload. A separate 20-seed
validation is conditional on selection; it was not run because no point passed.

The dedicated u32 stream 97 derives from the environment seed. Walk/stop dwell is
exponential, rounded up to integer 10 ms intervals. Turning is a 0.75 s OU process,
with deterministic Gaussian generation and pinned transition constants. Its
positive and negative parts drive the respective turn groups. Forward current is
present only in the walk state; backward current is zero. The drive object has no
hand, cursor, strike, body, callback or environment reference. Only the resulting
kernel spikes reach the unchanged decoder and BrainView.

A passing point must meet every declared bound. Distance is the sum of squared
normalized deviations from speed 2.25, walk bout 1.25 s, stop bout 0.9 s, walking
fraction 0.55, coverage 1.0, bot-1 catch 0.275 and bot-2 catch 0.45, with scales
0.75, 0.75, 0.6, 0.15, 0.5, 0.075 and 0.10. Ties favor lowest forward amplitude,
then lowest sigma, then grid order. No failed point is a fallback selection.

The observed bout metric uses grounded decoded forward speed above the registered
speed deadband. Round-edge censored segments are retained but excluded from bout
medians. Latent walk-state occupancy is recorded separately. Coverage counts
visited two-unit lattice cells whose centers lie in the circular arena (37 cells).
The declared coverage gate is at least half. Resting-swat censoring is a failure,
not an unobserved escape. Baseline for the four tuning seeds is 75% physical escape.
The raw per-seed segments, rates, bot impacts and censoring are all retained.

| Point | Forward | Sigma | Mean walk/stop s | Median speed FL/s | Median decoded bout/stop s | Walking % | Coverage % | False takeoffs/s | Circuit Hz | Bot 1/2 catches % | Pass |
|---|---:|---:|---|---:|---|---:|---:|---:|---:|---|---|
| 0 | 1.5 | 0.5 | 1/0.6 | 2.876 | 0.090/0.070 | 36.47 | 70.95 | 0.01667 | 4.280 | 37.50/62.50 | No |
| 1 | 1.5 | 0.5 | 1/1 | 3.038 | 0.120/0.070 | 30.97 | 58.11 | 0.00000 | 4.280 | 50.00/61.11 | No |
| 2 | 1.5 | 0.5 | 1.5/0.6 | 3.038 | 0.140/0.070 | 44.84 | 81.08 | 0.00000 | 4.284 | 30.56/61.11 | No |
| 3 | 1.5 | 0.5 | 1.5/1 | 2.958 | 0.140/0.050 | 46.75 | 79.05 | 0.00000 | 4.282 | 33.33/55.56 | No |
| 4 | 1.5 | 1 | 1/0.6 | 2.858 | 0.090/0.080 | 36.84 | 64.19 | 0.00000 | 4.288 | 41.67/55.56 | No |
| 5 | 1.5 | 1 | 1/1 | 3.038 | 0.130/0.070 | 31.39 | 56.08 | 0.01667 | 4.278 | 50.00/66.67 | No |
| 6 | 1.5 | 1 | 1.5/0.6 | 2.972 | 0.090/0.060 | 44.58 | 69.59 | 0.00833 | 4.288 | 40.28/52.78 | No |
| 7 | 1.5 | 1 | 1.5/1 | 2.979 | 0.140/0.060 | 45.77 | 76.35 | 0.00000 | 4.282 | 43.06/55.56 | No |
| 8 | 1.75 | 0.5 | 1/0.6 | 5.883 | 0.490/0.375 | 58.00 | 95.27 | 0.00833 | 4.285 | 27.78/48.61 | No |
| 9 | 1.75 | 0.5 | 1/1 | 5.893 | 0.670/0.680 | 47.95 | 84.46 | 0.00000 | 4.281 | 45.83/51.39 | No |
| 10 | 1.75 | 0.5 | 1.5/0.6 | 5.998 | 1.000/0.360 | 67.74 | 97.30 | 0.00000 | 4.284 | 19.44/52.78 | No |
| 11 | 1.75 | 0.5 | 1.5/1 | 6.093 | 1.035/0.755 | 67.49 | 93.24 | 0.00000 | 4.287 | 30.56/58.33 | No |
| 12 | 1.75 | 1 | 1/0.6 | 5.845 | 0.530/0.360 | 58.38 | 96.62 | 0.00000 | 4.290 | 29.17/56.94 | No |
| 13 | 1.75 | 1 | 1/1 | 5.930 | 0.735/0.700 | 47.98 | 91.89 | 0.00000 | 4.292 | 45.83/54.17 | No |
| 14 | 1.75 | 1 | 1.5/0.6 | 6.013 | 0.950/0.325 | 68.08 | 96.62 | 0.00000 | 4.293 | 19.44/34.72 | No |
| 15 | 1.75 | 1 | 1.5/1 | 6.144 | 0.850/0.635 | 67.30 | 97.30 | 0.00000 | 4.296 | 27.78/51.39 | No |
| 16 | 2 | 0.5 | 1/0.6 | 10.000 | 0.570/0.435 | 61.18 | 100.00 | 0.00000 | 4.294 | 25.00/55.56 | No |
| 17 | 2 | 0.5 | 1/1 | 10.000 | 0.780/0.900 | 49.93 | 97.30 | 0.00000 | 4.289 | 41.67/61.11 | No |
| 18 | 2 | 0.5 | 1.5/0.6 | 10.000 | 1.175/0.350 | 70.71 | 97.30 | 0.00833 | 4.296 | 12.50/55.56 | No |
| 19 | 2 | 0.5 | 1.5/1 | 10.000 | 1.010/0.940 | 68.89 | 97.97 | 0.00000 | 4.298 | 27.78/63.89 | No |
| 20 | 2 | 1 | 1/0.6 | 10.000 | 0.555/0.420 | 61.44 | 97.97 | 0.00000 | 4.303 | 23.61/47.22 | No |
| 21 | 2 | 1 | 1/1 | 10.000 | 0.805/0.890 | 50.05 | 95.27 | 0.00833 | 4.293 | 45.83/54.17 | No |
| 22 | 2 | 1 | 1.5/0.6 | 10.000 | 1.110/0.320 | 70.83 | 100.00 | 0.00000 | 4.302 | 16.67/38.89 | No |
| 23 | 2 | 1 | 1.5/1 | 10.000 | 1.140/0.925 | 68.89 | 100.00 | 0.00000 | 4.305 | 26.39/50.00 | No |

Point 15 initially encountered a projected aim a rounding error outside the arena.
Commit `6ff39ca` adds a repeated inward shrink only when the prior projection would
be rejected. Its failed log is retained. Completed points had valid aims and are
unaffected; point 15 and the remaining points ran with that mechanical correction.
The protocol, game and targets did not change.

Low-drive points produced median decoded bouts of 90 to 140 ms. Higher drive made
bouts longer but raised median speed to 5.85 to 10 fly lengths/s. This grid does
not establish that every possible current design is infeasible. It establishes
that the declared design grid has no passing selection. No decoder gain, deadband,
result, target or hidden movement controller was changed to force a pass.

## Bot evidence

Bots 1 and 2 use current position and current held velocity times the fall time,
respectively, after 1.5 s warmup and one-second quiet gaps. They use no aim noise
or reaction delay. The baseline below uses 20 seeds, six strikes per seed/type.
The complete after-grid table by bot and strike type is in
`evidence/V2J/drive/selection.json` (`bot_rates` on every row); no selected-point
after rate exists. The original ten-strategy bot set is retained unchanged in
`evidence/V2J/baseline/bots-v7.json`. A separately labeled point-0 review run of
that same bot set is under `evidence/V2J/bots/review-point0/`; it is not validation.

| Bot | Strike | Baseline catch rate | Strikes |
|---|---|---:|---:|
| 1 | flick | 99.167% | 120 |
| 1 | slap | 100.000% | 120 |
| 1 | swat | 11.667% | 120 |
| 2 | flick | 99.167% | 120 |
| 2 | slap | 100.000% | 120 |
| 2 | swat | 10.833% | 120 |

## Software, UI and media

Python/TypeScript checks compare 15,000 complete drive intervals across five seeds,
including reset, and 400 T1b intervals of neural state, commands and recorded spike
counts. They include sensory removal while walking current persists. Additional
checks cover hand-independent drive sequences, unchanged lab frames, output-clamp
causality, same-boundary impact before takeoff, and clear replay-schema rejection.
The bit-exact claim covers these drive/neural fixtures, not arbitrary full-game
floating-point body trajectories across runtimes.

Desktop tabs now occupy a normal layout row, so both lab panels begin below them.
The generic overlap check compares visible text rectangles and control boxes,
excluding owned contents, clipped screen-reader text and modal-occluded content.
Canvas graphics are checked separately by arena bounds, not treated as text boxes.
It runs on every captured state in all three browser harnesses, and a deliberate
collision checks that the detector detects an actual overlap. Font line-box
collisions in the game counter and phone summary were also repaired.

All browser-dependent number-format calls explicitly use en-US. Other numeric
copy uses locale-independent String/toFixed or explicit Python formatting. The
new matrix captures game, replay, summary, Shuffle, Silence and How it works at
390x844, 1280x720, 1366x768, 1440x900, 1920x1080 and 2560x1440 in Chromium,
Firefox and WebKit, plus ru-RU and de-DE Chromium runs. It checks DOM, alt/ARIA and
canvas text, axe, external requests and live game FPS. Final results and SHA are
in `evidence/V2J/acceptance/command-results.json` and the browser reports.

The exact requested walking disclosure is stored in profile metadata and is
rendered in the game, generated README and model pages when a point is active.
It is deliberately not displayed as an achieved production behavior while
`selected` is null. The generated lab limits state: "Lab simulations have no
walking drive." Share cards identify the actual game profile. v2.8 re-execution
logs use schema v3; attempting to load a v2 log with v2.8 clearly rejects it.

`evidence/V2J/media/walking-10s.webm` is a review-only recording of the first grid
point with seed 1, not a selected or passing point. It uses 200 real recorded
frames at 20 fps, no threat, and ordinary recorded-spike BrainView rendering.
The old README hero remains a declared historical v2.7 capture, with provenance
validated against the exact accepted base commit. A v2.8 README hero is not
re-recorded because the drive selection gate failed. No first-success hero seed
is claimed. The requested v2.8 hero and selected-point validation remain pending.

Full software acceptance is run on the final local commit. The walking-design
acceptance gate must remain FAIL for this submission. External acceptance is
pending. Review archive: `reviews/V2J-a01.zip`.
