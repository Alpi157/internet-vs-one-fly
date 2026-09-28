# Encoder card v2

Status: DRAFT_REVIEW_REQUIRED.

## Inputs and authority

The encoder receives the active strike, aimed arena point, player-chosen descent speed, elapsed strike time, and current fly pose. These values are sensory inputs to the network. They are not available to the decoder.

## Assumptions

- The hand is a disk with radius 0.75 arena units.
- The disk starts 8 arena units above the arena and descends vertically to the aimed point.
- Angular radius uses true three-dimensional hand-center distance and the declared deterministic atan approximation.
- LC4 drive is proportional to angular radius. LPLC2 drive is proportional to positive angular expansion.
- Left and right drive fractions use the signed planar cross product between fly heading and hand direction.
- A strike aimed far from the fly produces weak drive because its three-dimensional distance remains large.
- Radius, height, gain, population roles, and side formula are model assumptions, not measurements.

## Numerical limits

Runtime evaluation uses only addition, subtraction, multiplication, division, square root, comparisons, and the approximation in `profiles/detmath-v2.json`.

