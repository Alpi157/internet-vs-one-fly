# V2A Phase 0 findings

These are measurements of the unchanged accepted v1 model and game. They do not validate natural fly behavior.

## Catch rates

| Strategy | Controller | Caught / rounds | Catch rate | 95% Wilson interval |
|---|---|---:|---:|---:|
| current-position | accepted-neural | 14 / 500 | 0.028000 | [0.016751, 0.046446] |
| current-position | fixed-latency-control | 14 / 500 | 0.028000 | [0.016751, 0.046446] |
| current-position | no-escape | 239 / 500 | 0.478000 | [0.434551, 0.521785] |
| lead-0.5 | accepted-neural | 17 / 500 | 0.034000 | [0.021335, 0.053771] |
| lead-0.5 | fixed-latency-control | 17 / 500 | 0.034000 | [0.021335, 0.053771] |
| lead-0.5 | no-escape | 149 / 500 | 0.298000 | [0.259573, 0.339507] |
| lead-1.0 | accepted-neural | 11 / 500 | 0.022000 | [0.012328, 0.038961] |
| lead-1.0 | fixed-latency-control | 11 / 500 | 0.022000 | [0.012328, 0.038961] |
| lead-1.0 | no-escape | 20 / 500 | 0.040000 | [0.026041, 0.060974] |
| lead-2.0 | accepted-neural | 494 / 500 | 0.988000 | [0.974070, 0.994489] |
| lead-2.0 | fixed-latency-control | 494 / 500 | 0.988000 | [0.974070, 0.994489] |
| lead-2.0 | no-escape | 348 / 500 | 0.696000 | [0.654313, 0.734698] |
| far-corner | accepted-neural | 0 / 500 | 0.000000 | [0.000000, 0.007624] |
| far-corner | fixed-latency-control | 0 / 500 | 0.000000 | [0.000000, 0.007624] |
| far-corner | no-escape | 1 / 500 | 0.002000 | [0.000353, 0.011241] |

## Plain conclusions

- The fixed-latency control used 30.0 ms before impact, derived from the accepted-neural runs.
- current-position: neural offset variance was 0.0 ms^2 and accepted-neural versus fixed-latency outcomes matched on 1.0 of paired attacks.
- lead-0.5: neural offset variance was 0.0 ms^2 and accepted-neural versus fixed-latency outcomes matched on 1.0 of paired attacks.
- lead-1.0: neural offset variance was 0.0 ms^2 and accepted-neural versus fixed-latency outcomes matched on 1.0 of paired attacks.
- lead-2.0: neural offset variance was 0.0 ms^2 and accepted-neural versus fixed-latency outcomes matched on 1.0 of paired attacks.
- far-corner: neural offset variance was 0.0 ms^2 and accepted-neural versus fixed-latency outcomes matched on 1.0 of paired attacks.
- Contrary to the plan-v2 nondegeneracy goal, far-corner had a neural catch rate of 0%.

## Context check

- accepted_circuit: DNp01 R first tick 1135, spikes 3, L first tick 1130, spikes 3; outside-circuit spiking neurons 0.
- full_graph: DNp01 R first tick 1136, spikes 3, L first tick 1131, spikes 3; outside-circuit spiking neurons 11.

Raw per-attack offset values and all context counts are in `findings.json`.

## Reviewer corrections

- Far-corner is a control strategy, not a nondegeneracy failure. The degenerate result is lead-2.0: with the accepted neural escape the catch rate is 0.988 versus 0.696 with no escape, so escaping makes the fly easier to catch and one trivial strategy dominates.
- The accepted neural controller is behaviorally identical to a fixed 30 ms timer in the current game: the escape-command offset variance is zero and paired outcomes match 100 percent. Public claims must not imply that the v1 connectome changes game behavior.
