# Calibration protocol v2 draft

Status: DRAFT_REVIEW_REQUIRED. Not frozen. V2C executes pipeline and sanity only.

| Criterion | Condition | Pass |
|---|---|---|
| not_silent | 20 s no-threat | whole-circuit mean rate >= 0.5 Hz and at least one decoder group rate > 0 |
| not_saturated | all calibration trials | whole-circuit mean rate < 50 Hz and fewer than 5% of neurons above 150 Hz |
| spontaneous_movement | 20 s no-threat | speed or turn nonzero in 10% to 90% of control intervals |
| false_escapes | 20 s no-threat | at most 0.05 escape onsets per second |
| escape_standard | aimed at the fly, standard speed | escape onset before impact in 20% to 90% of strikes |

Grid: s {0.005, 0.01, 0.02, 0.039, 0.06}; kappa {0.02, 0.05, 0.10}; nu0 {0.5, 2, 5} Hz; input gain {1, 2, 4, 8}. Weights are contact count times sign, normalization none. Noise uses all neurons, stream 17, flybench.u32.v2. The isolated table uses 200 s per evaluation and no circuit output.

lowest no-threat whole-circuit rate; ties broken by s, kappa, nu0, gain in grid order.

A quantity used as a calibration criterion cannot be a primary H1 or H2 outcome. Primary outcomes are measured on held-out conditions.

H1 primary outcomes: escape probability and onset time before impact across speeds {0.025, 0.05, 0.1} units/ms, offsets {0, 1.5, 3} units, azimuths {0, 90, 180, 270} degrees; exclude the standard aimed condition. Record left/right escape-group asymmetry for lateral strikes. H2 primary outcomes: walking bout and pause duration distributions, speed distribution while moving, turn autocorrelation and left/right turn asymmetry. Moving fraction is not primary. No real-graph hypothesis analysis occurs in V2C.

Controls: output clamp; LC4 lesion; LPLC2 lesion; turning-neuron lesion; noise straight to decoder; C-SIMPLE single threshold on angular size fitted with the same calibration budget; C-TIMER fixed 30 ms latency from V2A. Static control is an encoder sanity test only.

Nulls: N-FULL and N-CONTEXT, 20 each. Autapses frozen in both; direct visual-to-output edges also frozen in N-CONTEXT. Identical grid, seeds, criteria and selection rule. A real or null graph with no passing point is uncalibratable and never silently dropped.

Strike timeline: 200 ms baseline, approach from height 8, impact, then zero visual drive for 200 ms. Standard speed 0.05 units/ms. Each trial resets explicitly; state persists during a trial. Escape onset counts rising edges of commands, not consecutive escape intervals. The previously held command drives the current interval.

Draft dry run: T1a and T1b, real plus two nulls per family, s {0.01, 0.039}, kappa 0.05, nu0 {0.5, 5}, gain {2, 8}, two seeds. Each seed receives 20 s no-threat and four standard plus four held-out strikes. Standard fraction pools eight strikes; no-threat criteria must pass each seed and saturation each calibration trial. Held-out trials are reported as pipeline observations only and never enter pass criteria. Sensory pose is fixed to keep aimed conditions controlled; commanded motion is recorded. C9 separately exercises the coupled body runner.

No full calibration, protocol freeze or H1/H2 conclusion is authorized in this stage.
