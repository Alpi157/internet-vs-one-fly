# Catch the Fly: preregistration v2

This protocol becomes public at the annotated Git tag **prereg-v2** and branch
**prereg/v2**. The freeze commit fixes the model, graph identities, trial seeds,
calibration, controls and analysis before confirmatory data. File hashes are in
[freeze-v2.json](../profiles/freeze-v2.json). Exact metric definitions, including
missing-data rules, are [preserved verbatim](v2e-metrics.md); the complete protocol
is [calibration-v2.md](calibration-v2.md).

**Question.** Under this simplified spiking model, does measured MaleCNS wiring
produce different stability, escape or spontaneous movement from shuffled wiring?
We compare real T1a and T1b circuits with N-FULL, N-CONTEXT and N-SIGN nulls. All
preserve directed degree and source edge attributes, with autapses frozen.
N-CONTEXT freezes direct visual-output edges. N-SIGN additionally preserves each
target's incoming degree by effective source sign. No biological coordinates,
IDs, neurotransmitter signs or turn directions are invented.

**H0, stability.** H0 was motivated by a V2D pilot with 2 nulls per family; those
nulls are excluded from this test. Fresh seeds produce 499 nulls per family on
T1a and 199 on T1b. At fixed kappa=0.05, nu0=2 Hz, each graph receives the same two
10 s noise trials at 11 couplings from 0.005 to 0.1. Outcomes are the first
coupling with mean rate >=50 Hz, censored above 0.1, and rate at s=0.039. T1a is
the nominal primary circuit. E/I shift correlations are descriptive.

**Calibration and H1/H2.** Every graph receives the same 180-point grid, seeds,
five criteria and budget. Selection minimizes no-threat whole-circuit rate among
passing points, with grid-order ties. T1a is primary if calibratable; otherwise
T1b is primary if calibratable. If neither passes, H1/H2 are not run. Every failed
point and uncalibratable null is reported. The other circuit is replication.

H1 uses 25 trials per held-out speed/offset/azimuth condition, 800 total. Metrics
are fast-minus-slow escape probability at offset zero, median first-onset lead
time with at least ten escapes, and lateral DNp01 spike asymmetry at offset three.
H2 uses four 120 s no-threat trials: uncensored mean bout duration, moving-pair
turn autocorrelation at 100 ms, and signed turn divided by absolute turn while
moving. Movement uses the reviewed E2 deadband. Calibration outcomes are not
reused as primary metrics.

**Inference and controls.** Two-sided permutation ranks use conservative inclusive
ties and plus-one p-values. Holm adjusts within each hypothesis and family at
alpha 0.05. Effects accompany null medians and 95% percentile bands. Censored
critical-coupling effects are not treated as point measurements. NA exclusions
are counted; fewer than 149 valid calibratable nulls means percentiles only.
Controls are descriptive: output clamp, LC4/LPLC2/turning lesions, independent
rate-matched decoder noise, a stochastic one-neuron LIF baseline with contact-derived
feature fractions, and a fixed 30 ms timer. Baseline fitting has a fixed bounded
search and a one-trial mismatch allowance. Fixed-parameter null comparisons and
replication receive no confirmatory Holm claim.

**Execution and reporting.** Real calibration precedes all confirmatory null data.
A measured projection above 16 hours defers the other circuit and executes the
selected primary, with scope recorded before null data. Per-graph outputs and
counter seeds permit worker-independent resume. Any defect after freeze stops
execution; frozen files cannot change. The game consumes exported profiles and
cannot alter scientific outcomes. Results, failures, exclusions, compute and
code will be published together, including negative findings. Claims concern
this model only, never a requirement for real flies or human usability.
