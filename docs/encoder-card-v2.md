# Encoder card v2

Status: DRAFT_REVIEW_REQUIRED. Model assumptions, not measured physiology.
The disk radius is 0.75 units, start height 8 units, standard speed 0.05 units/ms.
Angular radius is atan_approx(r / max(distance, r/8)). Expansion is the positive
backward finite difference over 0.5 ms, holding current fly pose fixed.

Both features are clamped to [0,1] before input gain. THETA_PEAK = atan_approx(8).
EXPANSION_PEAK = r*v_standard / ((r/8)^2+r^2), the maximum derivative on the
standard centered trajectory over height [r/8,H]. This geometry-derived bound
also bounds the finite difference. Peaks are independent of neural output.

LC4 receives expansion_feature. LPLC2 receives size_feature only while expansion
is strictly positive. A static object gives zero drive to both. Looming selectivity
is assumed at the encoder level and is not produced by the circuit, following the
reviewer reading of Klapoetke et al. Nature 2017 (doi:10.1038/nature24626) and Ache
et al. Current Biology 2019 (doi:10.1016/j.cub.2019.01.079). See D-V2C-ENCODER-01.
The looming versus static difference is not an H1 metric.

Cross product of heading and planar aim direction splits left=(1+cross)/2,
right=1-left, using somaSide groups. No retinotopy is inferred. Baseline is zero;
approach ends at impact; the hand is removed at impact, so drive is zero.
No strike also means zero drive. The decoder receives spikes only.
