# V2J: from a standing fly to owner-selected walking

Game profile **v2.8** activates **A: calm**, exactly as the owner played it in the a02 development preview. This is an owner-selected game setting, not a calibrated biological drive or a walking-superiority finding. The original a01 design gate remains **FAIL**; its grid, raw records and review ZIP, and all a02 records remain unchanged.

The wiring model does not walk on its own. The game adds a declared random drive to the walking neurons (game profile v2.8). Escape comes only from vision through the network. The walking setting was chosen by the author after playtesting four candidates that passed the same safety checks.

Movement comes from the neural decoder. The current enters only forward, backward and turning port neurons; backward current is zero. It never enters visual, escape or giant-fiber ports. The environment-seeded walk/stop and OU process cannot read the hand, cursor, aim, strike or body. BrainView activity still comes only from recorded spikes. Lab simulations have no walking drive.

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
no-threat rounds and the declared bots/resting-swat workload. The a01 protocol made a separate 20-seed validation conditional on selection;
it was not run in a01 because no point passed.

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
The complete a01 after-grid table by bot and strike type is in
`evidence/V2J/drive/selection.json` (`bot_rates` on every row); no selected-point
after rate existed in a01. The original ten-strategy bot set is retained unchanged in
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

## Reviewer correction after a01

The reviewer confirmed that stopping at the failed gate was correct. The requested 1.5-3 fly-length/s band selected sparse forward firing, so the 10 ms decoded bout metric measured short pushes rather than the motion a player sees. The point-0 review recording visibly crossed the arena. **The reviewer changed the next attempt's design criteria after seeing a01, and did not relabel its failed result.** [D-V2J-DESIGN-02](../decisions/D-V2J-DESIGN-02.json) records the instruction and cites the failed grid and recording. Game feel would be chosen by the owner playing; bot targets became descriptive.

## a02: four safety-gated previews

[The declared a02 profile](../profiles/owner-walking-a02.json) fixed A and B to a01 points 3 and 8. D chose the lowest amplitude among 1.6, 1.65, 1.7 with median visible bout at least 0.3 s on seeds 101-104. C chose the lowest takeoff speed among 0.027, 0.036, 0.045, 0.054 units/ms with unrestricted bot-4 flick catches at most 65% on those seeds. Every candidate and its metrics remain on record. D selected 1.6; C selected 0.045. Only C changes the disclosed takeoff-speed game parameter.

| Preset | Forward | Turn sigma | Mean input walk/stop (s) | Takeoff (units/ms) | Safety |
|---|---:|---:|---|---:|---|
| A: calm | 1.5 | 0.5 | 1.5/1.0 | 0.018 | PASS |
| B: busy | 1.75 | 0.5 | 1.0/0.6 | 0.018 | PASS |
| C: busy, quicker takeoff | 1.75 | 0.5 | 1.0/0.6 | 0.045 | PASS |
| D: middle | 1.6 | 0.5 | 1.0/0.6 | 0.018 | PASS |

The visible metric is the derivative of a trailing 200 ms boxcar average of body position: displacement over 200 ms divided by 0.2 s, in fly lengths/s. A visible bout stays above 0.5 fly lengths/s. The first incomplete window and windows containing airborne motion are ineligible. Bout and stop medians exclude round-edge and air-gap censored segments. Walking fraction uses all round intervals. Both visible and decoded metrics are retained; neither replaces the other. Coverage counts grounded visits to the same 37 one-fly-length grid cells.

The safety gates are spontaneous takeoffs at most 0.05/s, whole-circuit rate below 50 Hz, conservative resting-swat escape at least the matched v2.7 176/200, exact replay and bit-exact Python/TypeScript drive parity. Unresolved swat opportunities count as non-escapes. The final swat comparison restores the exact original two five-strike rounds per seed, as recorded in [D-V2J-PROTOCOL-04](../decisions/D-V2J-PROTOCOL-04.json). Earlier independent-round outputs and the corrected quiet-clock pilot are retained and clearly labeled in a02. [The unchanged a02 report](walking-v2j-a02.md) contains all metrics, bot tables, corrections and media references. Four presets passed these safety checks; a02's full software acceptance separately failed the 50 fps WebKit lab gate (46.642 fps). Production stayed v2.7 throughout a02.

## Owner choice on 2026-10-19

The owner played all four development previews and chose **A: calm as the most realistic**. [D-V2J-SELECT-01](../decisions/D-V2J-SELECT-01.json) cites the exact a02 profile and safety records. This choice authorizes production activation without retuning; it is not a controlled human-player study. A uses forward current 1.5, turn sigma 0.5, mean input walk 1.5 s and stop 1.0 s. Takeoff speed stays 0.018 units/ms. Every strike, arena and other body rule is unchanged from preview A and v2.7.

## a03 production verification

[The a03 protocol](../profiles/walking-a03.json) was dry-run before commit `8fa7d5c` froze it. The final acceptance reruns neural seeds 1-20, environment seeds 1001-1020, for 30 s each, and the full a02 bot and original resting-swat workloads on the submitted SHA. `evidence/V2J/a03/A.json` contains the code/profile hashes, every aggregate, all bot/swat records, and explicit equality checks against a02. All reported physical and neural measurements below reproduce a02 A exactly; only production profile/log identity changes. Final-SHA receipts remain external evidence rather than changing this committed report after testing.

| No-threat measure | Visible path | Decoded output |
|---|---:|---:|
| Median walking speed (fly lengths/s) | 2.257209 | 3.034966 |
| Median completed bout (s) | 0.760 | 0.130 |
| Median completed stop (s) | 0.240 | 0.060 |
| Walking fraction | 60.310% | 42.463% |

Mean path **44.938526 fly lengths/30 s**, net displacement **2.055683**, coverage **77.702703%**. Spontaneous takeoffs **6/600 s = 0.010/s**; whole-circuit mean **4.275010 Hz**. Resting-swat conservative escape **185/200 = 92.5%**, versus **176/200 = 88%** in v2.7; 199 resolved, one censored as a non-escape. These are repeated scripted strikes, not independent biological trials.

Bots run the authoritative game loop, six opportunities per seed and type, 1.5 s warmup and 1 s gaps. Bot 1 aims at observed position. Bot 2 leads by held velocity times strike fall time. Bot 4 waits for 150 ms grounded body speed at or below 0.5 fly lengths/s before aiming; it never forces a stop. Human-like limits add 200 ms delay and independent uniform +/-0.3 arena units per aim axis using existing stream 71. Holds are 80/300/600 ms. Every row/type below has 120 resolved impacts and zero censored opportunities.

| Bot | Limits | Flick catches | Slap catches | Swat catches |
|---|---|---:|---:|---:|
| 1 | none | 68/120 (56.67%) | 77/120 (64.17%) | 7/120 (5.83%) |
| 1 | human-like | 32/120 (26.67%) | 42/120 (35.00%) | 10/120 (8.33%) |
| 2 | none | 97/120 (80.83%) | 112/120 (93.33%) | 35/120 (29.17%) |
| 2 | human-like | 42/120 (35.00%) | 61/120 (50.83%) | 20/120 (16.67%) |
| 4 | none | 100/120 (83.33%) | 109/120 (90.83%) | 8/120 (6.67%) |
| 4 | human-like | 41/120 (34.17%) | 78/120 (65.00%) | 11/120 (9.17%) |

The lab rendering optimization scales only its two activity canvases from 720 to 480 pixels wide, keeps text overlays at 720, and removes the additional soma-glow draw pass. It changes no simulation, source anatomy or recorded spike. The pre-final WebKit check measured N-SIGN **56.1 fps at 1440x900**, versus a02 **46.6**; all four sizes exceeded the unchanged **50 fps** threshold. Final acceptance repeats the full matrix. Game FPS must remain at least 55. Browser results are headless desktop engine measurements, not physical-device benchmarks.

The six-size matrix covers game, replay, round summary, lab Shuffle, lab Silence and How it works in Chromium, Firefox and WebKit, plus ru-RU and de-DE runs. Every captured state has generic visible text/control overlap, axe and external-network checks; a deliberate collision tests the detector. English number formatting covers DOM, canvas, alt and ARIA text. The corrected hint explains flick on quick click/tap, slap on a short hold (the fastest hand), and slow swat on a longer hold. The charge ring and mechanics are unchanged.

v2.8 logs use replay schema v3 and the effective profile identity. Old v2 logs are clearly rejected with the wrong-schema error; they are not silently replayed with new dynamics. The A/B/C/D preview module remains behind `import.meta.env.DEV`; a production-bundle scan and query test prove it is excluded.

## Hero and preserved lab media

The hero rule was written into the committed protocol and provenance before capture: 1.5 s walking at real speed, then one 300 ms slap at the fly's current position at tick 3000; choose the first escaping neural seed in ascending order with environment seed fixed at 8128. **Seed 1 escaped, one seed tried.** The 960 px-wide hero shows the walk, strike and takeoff at a disclosed 5x slowdown, the Escaped stamp, and three seconds of ordinary quarter-speed recorded replay. The OG brain frame uses the same maximum-observed-spike-count hero replay rule as before. [Media provenance](media/media-provenance.json) records the log, trials, timing, source identities, sizes and frame hash. The lab GIF and still remain byte-identical to a02; the lab has no walking drive.

Frozen science, kernel, graph, neural parameters, raw/registered results and V2G anatomy stay byte-identical. The a03 prior-preservation inventory also pins all a01/a02 evidence and ZIPs. Full suite and acceptance receipts are under `evidence/V2J/a03/acceptance`; the review bundle is `reviews/V2J-a03.zip`. The agent submits for external review and does not mark the stage accepted. No push, tag or deployment is performed.
