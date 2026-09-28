# Calibration protocol v2 draft

Status: DRAFT_REVIEW_REQUIRED. This protocol is not frozen and the V2B run is only a pipeline dry run.

## Grid and targets

The proposed grid jointly varies runtime synaptic scale, background spike probability, background current increment, and sensory input gain. Exact proposed values and the two-value dry-run subset are in `profiles/calibration-v2-draft.json`.

The proposed pass criteria require output activity without a threat, reject whole-population mean rates at or above 100 Hz, require spontaneous movement during 5 to 80 percent of no-threat intervals, require looming escape probability from 0.1 to 0.9, and require looming escape probability to exceed the matched non-looming control by at least 0.10. These ranges are proposals for reviewer evaluation, not measured facts.

If several settings pass, select the setting with the lowest no-threat whole-population mean rate. Break ties lexicographically by synaptic scale, noise probability, noise increment, then input gain. This rule is declared before a full run.

## Controls

Every profile includes no threat, looming, matched non-looming at the same final angular size, output clamp, LC4 lesion, LPLC2 lesion, turning-neuron lesion, and the same noise sent straight to the decoder. C-SIMPLE is a single angular-size threshold fitted with the same grid budget. C-TIMER is the fixed 30 ms controller measured in V2A. Control fitting does not receive extra trials or parameter combinations.

## Null calibration

N-FULL makes every circuit edge eligible for directed double-edge swaps. N-CONTEXT freezes direct visual-port to output-port edges and makes every other edge eligible. The full protocol uses 20 nulls per family. Each null receives the same grid, seed budget, controls, criteria, and selection rule as the real graph. Matched calibration statistics must be published with comparisons.

## H1 and H2

H1 records first escape-command offset before impact, escape probability against strike speed, and the looming versus matched non-looming difference. H2 records speed, bout and pause duration distributions, turn autocorrelation, and left/right asymmetry. H2 also compares against the same noise sent directly to the decoder. For both hypotheses, the real graph is placed within the null distribution and evaluated with a permutation test. No decisions are made during data collection.

## V2B dry run

The dry run uses two values per parameter, T1a and T1b, the real graph, two N-FULL nulls, two N-CONTEXT nulls, two seeds, and short trials. It reports pipeline measurements for every grid point. It cannot support H1 or H2 conclusions and cannot freeze this protocol.

