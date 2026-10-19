# V2J a02: owner walking presets

Four safety-passing presets are offered only by the Vite development server. Production remains **flybench.game.v2.7**. The owner has not yet chosen game feel, and this report does not mark the stage accepted. The original a01 grid, every raw result, its failed gate, and its ZIP remain unchanged; `a01-preservation.json` inventories their hashes.

The reviewer decision is recorded in `decisions/D-V2J-DESIGN-02.json`. Original freeze: `65c9862`; quiet-clock repair: `a026595`; disclosed baseline-gate correction: `85ecd17`; dev-preview implementation: `d636fb8`; exact original-schedule safety freeze: `f4f8989`. No neural model, kernel, graph, frozen parameter, registered result, V2G anatomy, strike type, arena, takeoff onset, duration, direction, or jitter rule changed. Preset C alone changes the explicitly authorized takeoff-speed game parameter.

## Declared selection

`profiles/owner-walking-a02.json` declared all presets, candidate values, metrics, seeds, bot rules and safety gates before execution. A is a01 point 3; B is point 8. D uses the first qualifying amplitude from the declared ascending list. C uses B’s current and the first qualifying takeoff speed. No bot catch target selects A/B/D or otherwise controls offering.

| D forward amplitude | Median visible bout, seeds 101–104 (s) | Qualifies ≥0.3 s |
|---|---:|---|
| 1.60 | 0.800 | yes |
| 1.65 | 0.805 | yes |
| 1.70 | 0.720 | yes |

D selects **1.6**. Each candidate used four 30 s no-threat rounds.

| C takeoff speed (units/ms) | Unrestricted bot 4 flick catches | Rate | Qualifies ≤65% |
|---|---:|---:|---|
| 0.027 | 17/24 | 70.83% | no |
| 0.036 | 18/24 | 75.00% | no |
| 0.045 | 2/24 | 8.33% | yes |
| 0.054 | 1/24 | 4.17% | yes |

C selects **0.045 units/ms**. These are four selection seeds × six flick opportunities; 0 censored. The independent 20-seed descriptive catch rates appear below. C retains B’s neural current and all other v2.7 body rules. This speed is abstract game physics, not a neural or biological parameter.

## Measurement

No-threat validation uses neural seeds 1–20, environment seeds 1001–1020, and 30 s each: 600 s per preset. Fly length is 2 arena units. Visible speed is the 10 ms derivative of a trailing 200 ms boxcar average of body position, equivalently the displacement over 200 ms divided by 0.2 s. A visible bout is a contiguous run above 0.5 fly lengths/s. The initial 200 ms and windows containing airborne motion are ineligible. Fractions use all 3,000 round intervals as denominator. Completed bout/stop medians exclude round edges and air-gap censoring; every observed segment remains in the raw records. Speed is the median of walking intervals pooled across rounds.

The a01 decoded definition is retained beside it: grounded absolute held forward speed ≥0.002 arena units/ms. Turning in place does not count as visible walking. Coverage uses the same 37 eligible one-fly-length cells as a01, counting grounded visits. Path length and net displacement are reported in fly lengths; path includes takeoff displacement, whereas walking metrics exclude it.

Bots use the authoritative `Game` loop, a 1.5 s warmup, 1 s quiet gaps, six opportunities per 30 s round, each of 20 neural seeds, and holds 80/300/600 ms for flick/slap/swat. Bot 1 observes current position. Bot 2 observes position and held velocity and leads by velocity × strike fall time. Bot 4 waits for 150 ms of grounded body speed ≤0.5 fly lengths/s, then observes and aims at that position; rotation alone is allowed and no stop is forced. Each is run both unrestricted and with 200 ms reaction delay plus independent uniform ±0.3 arena-unit aim noise per axis, using existing stream 71. Aims are projected inside the unchanged circular arena. There are 120 resolved strikes in every preset/bot/limits/type cell and zero censored bot opportunities.

## Offered presets

### A: calm

Offered: **yes**. Forward 1.5, turn sigma 0.5, mean input walk/stop 1.5/1 s, takeoff speed 0.018 units/ms.

| No-threat measure | Visible path | Decoded output |
|---|---:|---:|
| Median walking speed (fly lengths/s) | 2.257 | 3.035 |
| Median completed bout (s) | 0.760 | 0.130 |
| Median completed stop (s) | 0.240 | 0.060 |
| Walking fraction | 60.31% | 42.46% |

Coverage **77.70%**; mean path/net **44.939/2.056 fly lengths**; spontaneous takeoffs **0.01000/s**; circuit rate **4.275 Hz**; resting-swat conservative escape **185/200 (92.5%)**, 199 resolved and 1 censored. Censored opportunities count as non-escapes.

| Bot | Limits | Flick catch | Slap catch | Swat catch |
|---|---|---:|---:|---:|
| 1 | none | 68/120 (56.67%) | 77/120 (64.17%) | 7/120 (5.83%) |
| 1 | 200 ms, ±0.3 | 32/120 (26.67%) | 42/120 (35.00%) | 10/120 (8.33%) |
| 2 | none | 97/120 (80.83%) | 112/120 (93.33%) | 35/120 (29.17%) |
| 2 | 200 ms, ±0.3 | 42/120 (35.00%) | 61/120 (50.83%) | 20/120 (16.67%) |
| 4 | none | 100/120 (83.33%) | 109/120 (90.83%) | 8/120 (6.67%) |
| 4 | 200 ms, ±0.3 | 41/120 (34.17%) | 78/120 (65.00%) | 11/120 (9.17%) |

All safety gates pass. Exact replay and bit-exact Python/TypeScript drive/reset parity are recorded under `evidence/V2J/a02`; group currents remain independent of the hand. The full effective profile hash is `6471c26c4caa6c2f394e2927783d4ec3a62bf670e6d056bba31b95aca519bf39`.

### B: busy

Offered: **yes**. Forward 1.75, turn sigma 0.5, mean input walk/stop 1/0.6 s, takeoff speed 0.018 units/ms.

| No-threat measure | Visible path | Decoded output |
|---|---:|---:|
| Median walking speed (fly lengths/s) | 5.404 | 5.998 |
| Median completed bout (s) | 0.855 | 0.680 |
| Median completed stop (s) | 0.330 | 0.380 |
| Walking fraction | 69.33% | 62.85% |

Coverage **94.19%**; mean path/net **114.698/1.959 fly lengths**; spontaneous takeoffs **0.01333/s**; circuit rate **4.281 Hz**; resting-swat conservative escape **180/200 (90.0%)**, 196 resolved and 4 censored. Censored opportunities count as non-escapes.

| Bot | Limits | Flick catch | Slap catch | Swat catch |
|---|---|---:|---:|---:|
| 1 | none | 49/120 (40.83%) | 57/120 (47.50%) | 4/120 (3.33%) |
| 1 | 200 ms, ±0.3 | 16/120 (13.33%) | 32/120 (26.67%) | 2/120 (1.67%) |
| 2 | none | 76/120 (63.33%) | 96/120 (80.00%) | 32/120 (26.67%) |
| 2 | 200 ms, ±0.3 | 26/120 (21.67%) | 41/120 (34.17%) | 20/120 (16.67%) |
| 4 | none | 99/120 (82.50%) | 103/120 (85.83%) | 9/120 (7.50%) |
| 4 | 200 ms, ±0.3 | 30/120 (25.00%) | 60/120 (50.00%) | 8/120 (6.67%) |

All safety gates pass. Exact replay and bit-exact Python/TypeScript drive/reset parity are recorded under `evidence/V2J/a02`; group currents remain independent of the hand. The full effective profile hash is `d147bfa0d1fbe25fa71d0ba366b354f83512b0655218baa242c292d4dcfc2014`.

### C: busy, quicker takeoff

Offered: **yes**. Forward 1.75, turn sigma 0.5, mean input walk/stop 1/0.6 s, takeoff speed 0.045 units/ms.

| No-threat measure | Visible path | Decoded output |
|---|---:|---:|
| Median walking speed (fly lengths/s) | 5.390 | 5.998 |
| Median completed bout (s) | 0.890 | 0.680 |
| Median completed stop (s) | 0.315 | 0.380 |
| Walking fraction | 69.32% | 62.85% |

Coverage **93.51%**; mean path/net **115.319/1.910 fly lengths**; spontaneous takeoffs **0.01333/s**; circuit rate **4.281 Hz**; resting-swat conservative escape **194/200 (97.0%)**, 198 resolved and 2 censored. Censored opportunities count as non-escapes.

| Bot | Limits | Flick catch | Slap catch | Swat catch |
|---|---|---:|---:|---:|
| 1 | none | 13/120 (10.83%) | 51/120 (42.50%) | 2/120 (1.67%) |
| 1 | 200 ms, ±0.3 | 6/120 (5.00%) | 12/120 (10.00%) | 2/120 (1.67%) |
| 2 | none | 31/120 (25.83%) | 78/120 (65.00%) | 7/120 (5.83%) |
| 2 | 200 ms, ±0.3 | 10/120 (8.33%) | 13/120 (10.83%) | 8/120 (6.67%) |
| 4 | none | 20/120 (16.67%) | 95/120 (79.17%) | 5/120 (4.17%) |
| 4 | 200 ms, ±0.3 | 6/120 (5.00%) | 22/120 (18.33%) | 1/120 (0.83%) |

All safety gates pass. Exact replay and bit-exact Python/TypeScript drive/reset parity are recorded under `evidence/V2J/a02`; group currents remain independent of the hand. The full effective profile hash is `2e41ccce640448a387ea9d4b9e6d764203f2b3c0efac6643781e86912501a65e`.

### D: middle

Offered: **yes**. Forward 1.6, turn sigma 0.5, mean input walk/stop 1/0.6 s, takeoff speed 0.018 units/ms.

| No-threat measure | Visible path | Decoded output |
|---|---:|---:|
| Median walking speed (fly lengths/s) | 3.348 | 3.792 |
| Median completed bout (s) | 0.805 | 0.250 |
| Median completed stop (s) | 0.380 | 0.050 |
| Walking fraction | 66.40% | 55.91% |

Coverage **87.70%**; mean path/net **70.462/2.126 fly lengths**; spontaneous takeoffs **0.01500/s**; circuit rate **4.279 Hz**; resting-swat conservative escape **184/200 (92.0%)**, 199 resolved and 1 censored. Censored opportunities count as non-escapes.

| Bot | Limits | Flick catch | Slap catch | Swat catch |
|---|---|---:|---:|---:|
| 1 | none | 56/120 (46.67%) | 66/120 (55.00%) | 9/120 (7.50%) |
| 1 | 200 ms, ±0.3 | 26/120 (21.67%) | 36/120 (30.00%) | 8/120 (6.67%) |
| 2 | none | 79/120 (65.83%) | 102/120 (85.00%) | 34/120 (28.33%) |
| 2 | 200 ms, ±0.3 | 28/120 (23.33%) | 49/120 (40.83%) | 20/120 (16.67%) |
| 4 | none | 99/120 (82.50%) | 111/120 (92.50%) | 11/120 (9.17%) |
| 4 | 200 ms, ±0.3 | 38/120 (31.67%) | 65/120 (54.17%) | 2/120 (1.67%) |

All safety gates pass. Exact replay and bit-exact Python/TypeScript drive/reset parity are recorded under `evidence/V2J/a02`; group currents remain independent of the hand. The full effective profile hash is `963a0bd6796eaf68c6808ad7ab1644dc39baf3c41602a40e5f7dc14b8c0123a0`.

## Corrections retained for review

The first a02 quiet harness used `seconds * 200` ticks rather than `seconds * 2000`, so its purported 30 s records contain 3 s. Those quiet records and D selection were invalidated, copied under `invalid-clock/`, and rerun after a committed fix and one-second dry run. Current records assert 60,000 neural ticks and 3,000 control intervals for a 30 s round; a .2 s integration regression checks 400 ticks and 20 intervals. Bot, resting-swat and replay loops already used integer ticks correctly and their raw outputs were retained. Corrected D selection still chooses 1.6.

The implementing agent also initially added an unrequested extra gate against a new independent-round v2.7 control (200/200 escapes). The owner’s specified baseline is the original a01 repeated-strike v2.7 rate, 176/200 = 88%. `D-V2J-PROTOCOL-03` records the post-measurement correction to that original threshold. The new control remains descriptive, and interim failed flags remain under `invalid-clock/`. This correction is disclosed and does not change the original 88% safety requirement, raw outcomes, preset parameters, or a01 FAIL.

The provisional independent-round workload used 200 independent opportunities per preset (20 neural seeds × 10 environment streams), observing the first 200 ms grounded rest below the a01 forward/turn deadbands, aiming perfectly, and using a swat. Neural state persists inside each round. An unresolved opportunity would count as a non-escape in the conservative rate. All 200 resolved for each preset in that provisional workload. These independent-round numbers cannot establish the requested safety comparison. They remain descriptive only and do not determine offering.

The final audit restored the exact original a01 schedule under `D-V2J-PROTOCOL-04`, frozen after a five-opportunity dry run at `f4f8989`: 20 neural seeds × two independent five-strike rounds, environment seed 1000 + seed + 100 × round, original 200 ms rest deadbands, original 30 s round limit, and persistent neural state between strikes. The v2.7 rerun reproduces **176/200 (88%) with 0 censored** exactly. Preset A escapes 185/200 (1 censored), B 180/200 (4 censored), C 194/200 (2 censored), D 184/200 (1 censored). These conservative rates treat every censored opportunity as a non-escape and all exceed 88%. The final offer uses this matched workload, not the provisional independent-round results. Both earlier protocol corrections, provisional offers, failed interim flags and raw records are retained. No preset, bot or neural parameter changed during these corrections.

## Preview and media

The `import.meta.env.DEV` guard dynamically loads a module and preset data that Vite removes from the production graph. A compact visible badge identifies the preset. How it works discloses the declared current and takeoff speed; C labels its speed as body physics. Replay logs bind the effective profile hash. BrainView and replay sentences use the ordinary recorded spike history. The coupling lab retains its original runner and no walking drive.

Vite’s static `.gz` handling originally caused browsers to decompress graph/anatomy containers before the existing readers. A serve-only middleware suppresses the HTTP `Content-Encoding` header for those explicit data containers. Their bytes and the frozen readers are unchanged. The failed first dev smoke test is retained under `preview-initial-failed/`.

Each offered preset has a 10 s no-threat seed-1 recording and a 10 s unrestricted bot-4 flick clip, both environment seed 1001, under `evidence/V2J/a02/media/`. The clips capture 200 actual render states at 20 fps, with ordinary recorded spikes. Authoritative Node execution, Chromium logs and replay digests must match. Initial clips with the larger badge remain under `media-initial/`; current clips use the compact badge. No a02 clip becomes a README hero; production and historical media stay v2.7.

In WSL, run:

```bash
cd /home/alpi/Projects/FlyBench
npm --prefix apps/play run dev -- --port 5173 --strictPort
```

Open these URLs in the Windows browser:

- `http://localhost:5173/internet-vs-one-fly/?preview=A`
- `http://localhost:5173/internet-vs-one-fly/?preview=B`
- `http://localhost:5173/internet-vs-one-fly/?preview=C`
- `http://localhost:5173/internet-vs-one-fly/?preview=D`

## Validation status

Full final-SHA acceptance is registered as `V2J-a02` and its receipt is `evidence/V2J/a02/acceptance/command-results.json`. It includes the full Python/Node suites, fresh-clone offline smoke, frozen-science verification and independent recomputation, three-browser production/lab checks, the 120-state production overlap/locale matrix, owner current parity and safety checks, production preview exclusion, and the dev preview matrix. The a01 gate is not rerun or relabeled. External owner playtest and acceptance remain pending.

No third-party requests, push, tag or deployment are authorized or performed.
