# V2E reviewer metric definitions

Exact V2D definitions (preserve verbatim at freeze):

- H1 trials (at each graph's selected point, fixed pose, independent resets):
  speeds {0.025, 0.05, 0.1} units/ms, lateral offsets {0, 1.5, 3} units, azimuths
  {0, 90, 180, 270} degrees; exclude speed 0.05 with offset 0; at offset 0 azimuth
  has no effect and those trials are replicates; 25 trials per condition.
- H1 primary metrics:
  H1a speed tuning = P(escape before impact | speed 0.1) minus
      P(escape before impact | speed 0.025), offset 0.
  H1b median escape lead time before impact (ms) over all held-out escapes; NA
      with fewer than 10 escapes (report the count).
  H1c lateral asymmetry at offset 3, azimuths 90 and 270: mean over trials of
      (DNp01 spikes on the strike side minus the other side) / total (0 if none);
      the strike side is the side whose visual ports receive more drive.
- H2 trials: 4 seeds x 120 s, no threat, body free to move.
- H2 primary metrics (E2 deadband): H2a mean bout duration; H2b turn-rate
  autocorrelation at 100 ms lag while moving; H2c turn asymmetry = mean signed
  turn while moving / mean absolute turn while moving.

Reviewer clarifications (also freeze these; they resolve details the V2D text left open):

C1 "Escape before impact": an escape onset (existing rising-edge rule, existing
   onset timestamp at the control-interval boundary) strictly before the impact
   tick of that strike. Only the first onset per strike counts.
C2 H1a: pool all offset-0 trials across the four azimuths (replicates), so each
   speed has 100 trials.
C3 H1b: "held-out escapes" = first onsets before impact in every included H1
   condition (all speeds, offsets and azimuths except speed 0.05 with offset 0).
   Lead time = impact time minus onset time, in ms.
C4 H1c: count DNp01 spikes per side from strike start to impact. The strike side
   is the side whose visual ports (LC4 plus LPLC2 of that side) receive the larger
   summed encoder drive over the same window; exclude a trial only if the two
   sides are exactly equal and report how many were excluded. Trials with zero
   total spikes contribute 0 and are counted.
C5 H2a: a bout is a maximal run of moving control intervals (E2 deadband). Bouts
   touching the start or end of a trial are censored and excluded from the mean;
   report the censored count. NA if there are no uncensored bouts.
C6 H2b: Pearson autocorrelation of the decoded turn rate at a lag of 10 control
   intervals, using only pairs where both intervals are moving, pooled over the 4
   seeds. NA if fewer than 30 such pairs (report the count).
C7 H2c: decoder sign convention as implemented (state it in the protocol), pooled
   over all moving intervals of the 4 seeds. NA if the mean absolute turn is 0.
C8 NA handling: a graph with NA for a metric is excluded from that metric's
   permutation test and the count is reported per family. If the real graph is NA,
   that metric is reported as "not computable" and no p-value is given.
C9 All H1 and H2 metrics are computed from raw per-trial records by the frozen
   analysis code, and the verification command recomputes them.
