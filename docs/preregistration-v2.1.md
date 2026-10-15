# Catch the Fly: preregistration v2.1

This protocol extends the publicly frozen [prereg-v2](preregistration-v2.md).
Its separate annotated tag is **prereg-v2.1**, with branch **prereg/v2.1**.
The machine specification is [protocol-v2.1.json](../profiles/protocol-v2.1.json).
The freeze manifest is profiles/freeze-v2.1.json. No member may change after
freeze. A defect stops the run and is reported. Public push must precede null
simulation. The original protocol and its manifest remain unchanged.

The question concerns stability under a simplified LIF model, motivated by the
prior registered T1a result. It does not concern what real flies require.
All scientific tasks retain failures, censoring and missing observations.

## Confirmatory tests

| Test | Graph | Null families | Fresh nulls per family | Outcomes |
|---|---|---|---:|---|
| H0-STR | T1a, 2,641 neurons | N-STRENGTH | 499 | H0a, H0b |
| H0-FULL | MaleCNS, 166,700 neurons | N-SIGN, N-STRENGTH | 99 | H0b-FULL |
| H0-T2 | T2, 43,894 neurons | N-FULL, N-SIGN, N-STRENGTH | 199 | H0a, H0b |

H0a is the first grid coupling with seed-mean whole-graph rate at least 50 Hz.
If no crossing occurs, it is censored above 0.1. The value 0.11 is a rank sentinel,
never a measured coupling. H0b is rate at 0.039. The grid is
0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.039, 0.05, 0.06, 0.08, 0.1.
Kappa is 0.05 and nu0 is 2 Hz. The trial seeds remain 2027101401 and 2027101402.
T1a and T2 use two independent 10 s trials per coupling. H0b-FULL uses two
independent 5 s trials at 0.039. The real full graph also gets the full grid,
using 5 s per seed, for a descriptive curve.

Noise uses the existing interior mask, stream 17 and noise-table-v2.json.
Every visual and decoder port is excluded, including DNb02. Body IDs are exactly
those in profiles/ports-v2.json, whose profile identifies ports-v2.1.
The no-threat sweeps use zero visual drive and independent reset per trial.

Null sweeps run in ascending order and stop after a coupling whose seed-mean
rate is at least 50 Hz, once 0.039 has been evaluated. The first crossing remains
the H0a value even if a later rate falls. Both metrics are therefore unchanged.
The rule was checked against five complete archived T1a N-SIGN sweeps without
running any new null simulation. Real graphs always receive full sweeps.
Stopped curve tails remain missing and are never extrapolated.

Two-sided permutation ranks use inclusive ties and plus-one p-values from
analysis_v2.permutation_rank. Alpha is 0.05. Holm applies across H0a and H0b
within each family for H0-STR and H0-T2, and across the two family p-values for
H0b-FULL. Report real values, null medians, 2.5% to 97.5% bands, effects, p and
adjusted p. Effects involving a censored critical-coupling median are not point
identifiable. All declared nulls must be present; no replacement or reduced count.

## Null generation and seeds

N-STRENGTH performs directed double-edge swaps within equal presynaptic effective
sign and equal contact bin: 1, 2, 3 to 4, 5 to 8, 9 to 16, 17 to 32, 33 to 64,
65 to 128, and 129 or more. Each edge retains its source, contact count and signed
weight. Autapses are frozen. A global edge-pair index rejects duplicate edges
across bins as well as within bins. No new self-loop is allowed. Incoming degree
within each sign/bin is exact; exact incoming numerical strength is not claimed.

N-SIGN uses equal source sign strata, and N-FULL uses one stratum. Each stratum
requests its original edge count in swaps, including frozen autapses in the
budget, with at most 100 proposals per requested swap. Immobile and incomplete
strata remain explicit. No adaptive reseeding is allowed. Diagnostics retain
completed swaps, proposals, changed fraction per stratum, incoming-strength KS
by sign, and E/I ratio shifts. The pilot gate requires at least 50% of all edges
changed in T1a and T2.

Fresh seed = 202910150000 + block_index * 100000 + family_index * 10000 + index * 32.
Block indices are H0-STR=0, H0-FULL=1, H0-T2=2, E2a=3, E3-low=4, E3-high=5.
Family indices are N-FULL=0, N-SIGN=1, N-STRENGTH=2. Internal strata add 0 to 26.
These seed ranges exclude every earlier null seed, including the topology-only
pilots beginning 202810150000. The first null index is zero. Archived null seeds
are used only for EXPLORATORY E1 regeneration and the product demonstration.

## EXPLORATORY E1: mechanism

Analyze real T1a and all 499 T1a nulls in each of N-FULL, N-CONTEXT, N-SIGN and
N-STRENGTH. Regenerate the first three families with the frozen V2E generator and
check the recorded target hashes. Also analyze real T2 and the first 20 nulls
per T2 family, subject to the resource rule below.

The signed effective matrix is s * PSP_UNIT * W, with s=0.039 and
PSP_UNIT=calibration_v2.unit_psp()[0]. W uses A[source,target]; transposition does
not change eigenvalues. Report the eigenvalue with largest real part, excitatory
spectral radius, excitatory reciprocity, largest excitatory strongly connected
component, contact-weighted excitatory 2-cycles and 3-cycles, and incoming-strength
Gini. Precise conventions and numerical solver bounds are in the machine profile.
Cycles have distinct vertices and product contact weights, counted once modulo
rotation. Autapses are excluded from cycles and reciprocity, retained in spectra.
Gini includes all neurons and uses absolute signed incoming strength.

ARPACK uses a deterministic all-ones start, tolerance 1e-7 and 5,000 iterations.
Nonconvergence is reported as missing, with no replacement spectrum. Report
family-wise descriptive percentiles and Spearman correlations with s* and rate
at 0.039. Censored s* values share the top rank. Constant variables yield missing
correlations. No p-values or Holm claims appear in EXPLORATORY outputs.

## EXPLORATORY E2 and E3: assumptions

E2a treats consensus glutamate sources as excitatory, retaining all other signs.
It uses real T1a plus 99 fresh N-SIGN nulls under those effective signs. E2b is
skipped: predicted_nt_confidence is copied into compiled arrays, but confidence
semantics relative to the consensus sign have not been established. The skip is
reported rather than inventing a confidence interpretation.

E3 separately uses nu0=0.5 and 5 Hz, each with real T1a and 99 fresh N-SIGN nulls.
All these checks use the H0 grid, kappa, two trial seeds, 10 s duration, metrics
and early-stop rule. They remain EXPLORATORY, with descriptive percentiles only.

## Resource rule and execution

The committed resource plan records measured real-graph timing, topology-generator
RSS and an explicit margin. Summed full-worker memory must stay within 70% of
available RAM. If the projection exceeds 24 hours, drop E2/E3 first, then E1 for
T2. Never reduce a confirmatory null count. A confirmatory test that cannot fit
is not started and is reported as not run. The plan is fixed before null data;
real-only projections are not runtime guarantees for saturated null graphs.

Order: H0-STR, H0-FULL, H0-T2, EXPLORATORY E1, EXPLORATORY E2a, EXPLORATORY E3.
Every graph/task writes an atomic independent record. Resume validates protocol
and task identity. Seeds and numerical outputs do not depend on worker count.
Progress logs include completion counts, elapsed time and ETA. Raw records,
compute, resource use, failed checks and verification accompany the findings.

## Claims ladder additions

A positive H0-STR permits: "In this model, measured wiring stays stable at
couplings where shuffles that also preserve each neuron's binned excitatory and
inhibitory connection strength saturate."

A positive H0-T2 or H0-FULL permits: "The stability difference also holds in the
43,894-neuron circuit" or "in the full 166,700-neuron MaleCNS graph", under this
model and for the families that reached significance. Directions must agree with
the registered stability claim. Every non-significant or not-run test is stated
plainly, family by family, wherever H0 is mentioned. EXPLORATORY checks never
support confirmatory claims. No claim says that real flies need this wiring.
