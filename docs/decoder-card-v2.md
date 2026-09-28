# Decoder card v2

Status: DRAFT_REVIEW_REQUIRED.

## Authority boundary

The decoder receives spike body IDs and its prior filtered rates only. It receives no cursor, strike, threat, aim, bearing, distance, collision, future outcome, environment, or position data.

## Assumptions

- Any escape-group spike requests escape for the next control interval.
- Filtered group rates use the precomputed decay in `profiles/decoder-v2-draft.json`.
- Forward speed is proportional to forward rate minus backward rate and is clamped.
- Turn rate is proportional to left-group rate minus right-group rate and is clamped.
- An empty group has rate zero.
- Assigning a body-side group to the same named turn direction is a model assumption, not a measured fact.
- Takeoff follows current heading. This direction rule is a simplification.
- Gain values, filter duration, and clamps are proposed model assumptions for calibration review.

