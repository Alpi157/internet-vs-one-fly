# V2D science gate report

S0 through S3 complete. G1 through G3 pass. G4 fails before any protocol freeze.
S5, S6 and S7 are skipped under the user's stop rule. V2D is not accepted.

The five calibration criteria require standard-strike escape probability between
0.2 and 0.9. The pre-registration also requires C-SIMPLE, a deterministic threshold
on size, to match that fraction. Fixed pose, geometry and reset make the sensory
trajectory identical across every standard strike. For any threshold, the response
indicator is identical across trials. Its empirical mean is either 0 or 1. Neither
can equal the response fraction of any passing calibration point.

This is a control-design conflict, independent of graph outcome. Random thresholds,
randomized sensory input, probabilistic triggering, or accepting a nearest attainable
fraction would each change the requested control. None was substituted. The reviewer
must specify the resolution before a later protocol version is frozen.

Dry run 3 retained all 80 rows. One point passes on real T1b; none passes on T1a in
the subset. This is not full-grid calibration and cannot establish uncalibratability.
Both visual-only drives change DNp01 somewhere in the declared subset. Every checked
post-impact visual input is zero; output clamp leaves fixed-pose neural digests
unchanged; repeated runs agree. Bounded 200 ms active reference checks agree with
the Numba kernel on T1a and T1b. No NaN or ring collision occurred. Recurrent
saturation and high false-escape rates remain explicit failures, without tuning.

All nine E3 rows pass pooled independent validation. The same inclusive movement
deadband now governs applied-command calibration and analysis segmentation. Direct
noise is excluded from all visual and output ports, including UNKNOWN DNb02.

| Hypothesis | Metrics | Result |
|---|---|---|
| H1 | speed tuning, escape lead time, lateral asymmetry | NOT RUN: S4 G4 stop |
| H2 | bout duration, turn autocorrelation, turn asymmetry | NOT RUN: S4 G4 stop |

No freeze commit, preregistration tag/branch, push, full-grid selection, null-family
calibratable fractions, permutation p-values, figures or biological claims exist.
The provisional game is an engineering artifact at the first dry-run grid point.
