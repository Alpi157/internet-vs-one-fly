# Calibration and confirmatory protocol v2

Status: frozen only by the annotated prereg-v2 commit, after the V2E gates pass.
The authoritative machine protocol is profiles/calibration-v2.json. The exact
reviewer metrics and C1-C9 clarifications are preserved in docs/v2e-metrics.md.
A completed public push is required before confirmatory execution.

## Model, data and clocks

MaleCNS v1.0 sources are pinned in profiles/source-lock.json. T1a and T1b identities
and array hashes are in profiles/circuits-v2.json. Contact counts remain separate
from signed executable weights. Unknown source signs are disabled. No biological
mapping is invented. Uniform float64 LIF constants, the encoder, spike-only decoder,
interior-only noise and E2 movement deadband retain the reviewed V2D semantics.
The 0.5 ms neural clock and 20-tick control intervals are integers. A previously
held decoded command drives the current interval. Reset is independent per trial;
state persists throughout a trial. Positive turn means left minus right decoded
turn-group activity, using the frozen direction assumptions.

## H0: pilot-motivated dynamic stability

H0 was motivated by a V2D pilot with 2 nulls per family; those nulls are excluded
from this test. T1a is primary and T1b secondary. Each N-FULL, N-CONTEXT and N-SIGN
family has 499 fresh T1a nulls and 199 fresh T1b nulls. All use identical trial
seeds. Sweep s over 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.039, 0.05, 0.06,
0.08 and 0.1 at kappa 0.05 and isolated nu0 2 Hz, two seeds each for 10 s without
threat. H0a is the smallest s whose seed-mean whole-circuit rate is at least
50 Hz. If no crossing occurs, report above 0.1 and rank tied at the top. The
0.11 computational sentinel is never a measurement. Effects with a censored
real or null median are not point identifiable. H0b is mean rate at s=0.039.

Null swaps retain each edge's source, contact count and signed weight. Autapses
are frozen and new self-loops and multiple edges are prohibited. N-CONTEXT also
freezes direct visual-to-output edges. N-SIGN swaps only edges with equal effective
presynaptic sign, including disabled zero as a separate stratum. It preserves
sign-split degree, but does not preserve target strength or E/I input strength.
Diagnostics report these shifts and completed swaps. One completed swap per
original edge is requested, per sign stratum in N-SIGN. Fresh seed formula and
all excluded pilot ranges are pinned in the machine protocol.

## Calibration

Grid, in tie order: s {0.005,0.01,0.02,0.039,0.06}, kappa {0.02,0.05,0.10},
nu0 {0.5,2,5} Hz, gain {1,2,4,8}. Failed isolated noise-table rows are excluded
without refitting. All nine reviewed noise rows currently pass. No-threat trials
are reused once per (s,kappa,nu0,seed), independent of gain. Two fixed calibration
seeds each receive 20 s no-threat and four independent standard strikes, with
trial seed base+(i+1)*101. The standard strike has a 200 ms baseline, height 8,
radius 0.75, speed 0.05 units/ms, fixed sensory pose, then 200 ms after impact.
Visual drive ends at impact. Calibration seeds are retained from the reviewed
draft; confirmatory H0, H1 and H2 seeds are separate and fixed in the protocol.

| Criterion | Pass |
|---|---|
| not_silent | No-threat whole-circuit rate >=0.5 Hz and one active decoder group |
| not_saturated | Every calibration trial rate <50 Hz and <5% of neurons above 150 Hz |
| spontaneous_movement | 10% to 90% moving intervals per no-threat seed |
| false_escapes | At most 0.05 rising-edge escape onsets/s per no-threat seed |
| escape_standard | 20% to 90% onsets before impact across all eight standard strikes |

Moving means abs(applied speed)>=0.002 units/ms or abs(applied turn)>=0.0005 rad/ms.
Select the passing point with lowest seed-mean whole-circuit no-threat rate,
then grid order. H1/H2 primary is T1a if any full-grid point passes, otherwise
T1b if any passes. If neither passes, H1/H2 are not run and the result is
"real graphs uncalibratable under these criteria". The other calibratable real
circuit is a descriptive replication. Every null receives the same grid, seeds,
criteria, budget and selection rule. Uncalibratable graphs remain in summaries.

## Held-out trials and controls

H1 and H2 definitions and reviewer clarifications are verbatim in
[the metric specification](v2e-metrics.md). No calibration quantity is a primary
outcome. H1 uses 800 independently reset trials per graph at fixed pose. Onsets
retain the existing control-boundary convention: strictly after strike start
and strictly before impact. H1c excludes neural spikes at impact. H2 uses four
120 s free-body trials. Bouts and turns use the previously decoded command
actually applied during the interval. Pairs never cross seed/trial boundaries.

C-SIMPLE is one LIF unit with the same constants, selected kappa and p, independent
stream 37. Drive is g*(a*LC4 feature+b*LPLC2 feature). Fractions a,b use measured
LC4/LPLC2 direct contacts onto DNp01 divided by their combined contact count,
pooled sides. Features are unsplit expansion and expansion-gated size. Evaluate
g=0 and 64, then 32 bisections using identical standard seeds. Select the closest
evaluated fraction, lowest g on ties. Report every evaluation and mismatch.
The allowed absolute mismatch is one standard trial divided by trial count.
Exceeding that bound at a selected point stops the run without changing the fit.

C-TIMER retains exactly 30 ms lead; it has no fractional matching target and is
only a descriptive, geometry-informed control. C-NOISE-DEC receives independent
stream-29 Bernoulli spikes at measured per-neuron output-group rates. Expected
rates match exactly; finite observations report max(5% of target, three Poisson
standard errors) bounds without refit. Output clamp must zero commands while
preserving fixed-pose neural trajectories. LC4, LPLC2 and turning-neuron lesions
zero the named neurons' drive, noise, incoming and outgoing edges. The feasibility
probe also tests the giant-fiber lesion used in the game. Lesions have no behavioral
matching target. All descriptive controls use the same held-out trial seeds.

## Statistics, missingness and claims

Use analysis_v2.permutation_rank two-sided inclusive-tie plus-one p-values, Holm
across H0a/H0b or the three H1/H2 metrics within each family, alpha 0.05. Family
size includes NA as p=1 for adjustment. Effects are real minus null median with
the null 2.5 to 97.5 percentile band. Metric-level NA nulls are excluded and
counted. Fewer than 149 valid calibratable nulls means insufficient calibratable
nulls, with percentiles only. Real NA means not computable and no p-value.
Secondary replication, every null at the real selected parameters, and Spearman
across nulls of critical coupling versus mean absolute per-target E/I input-ratio
shift are descriptive. Censored critical values tie at the top for Spearman.

Claims follow plan-v2 section 3. The additional permitted positive H0 wording is:
"In this model, measured wiring stays stable at couplings where degree- and
sign-matched shuffles saturate". Its direction and relevant family must be
supported by the data. Never infer that real flies need this wiring. Null,
negative, noncomputable and insufficient-sample results are retained.

## Execution and freeze

Run real calibrations first, then export the selected primary point for the game.
Before confirmatory null data, project total compute from measured timings. Above
16 hours, execute only the selected primary circuit (T1a if neither calibrates)
and defer the other circuit. This budget rule may defer the nominal H0 T1a primary
if H1/H2 select T1b; that scope is explicitly reported before null data. Then run
H0, null calibration, H1/H2, fixed-parameter comparisons, and controls. Atomic
per-graph/stage files support --resume; seeds never depend on worker count or order.
Progress logs include ETA. A frozen identity mismatch or defect stops execution;
all existing output remains, and STOP.json blocks automatic continuation.

The freeze manifest hashes scientific executables, dependencies, model and protocol,
ports, signs, directions, encoder, decoder, noise table and source/circuit identities.
Browser rendering and game exports consume these profiles and do not edit them.
The browser implementation may receive the authorized parity-preserving performance
pass. It is validated separately and does not produce confirmatory science data.

```sh
uv run python experiments/v2e_run.py --workers 12 --resume --out evidence/V2E/results
uv run python experiments/v2e_analyze.py --out evidence/V2E/results
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
```
