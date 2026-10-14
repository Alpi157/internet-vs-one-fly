# Decoder card v2

Status: DRAFT_REVIEW_REQUIRED. Inputs are spike body IDs and prior rates only.
The dependency audit excludes geometry, closures and reachable environment state.
Filtered group rates are mean spikes per neuron per second, with a 50 ms filter.
Escape requests occur on any DNp01 spike; onsets count rising request edges.

Constants are declared before the dry run and are not calibrated. A 20 Hz
forward-minus-MDN difference reaches maximum speed 0.02 units/ms. Backward speed
is allowed to -0.01 units/ms. A 20 Hz left-minus-right difference reaches maximum
turn 0.005 rad/ms. Empty groups have rate zero.

Turn directions are model assumptions in turn-directions-v1.json. DNa01 and DNa02
use ipsilateral interpretation from the opened Rayshubskiy 2020 primary preprint;
DNg13 uses soma-relative ipsiversive interpretation from the opened Yang 2023
primary preprint. DNb02 is UNKNOWN and excluded from decoding while retained in
the circuit. The annotation audit does not establish projection side or crossing.
Yang reports type-level DNg13 crossing and DNa02 noncrossing; transferring the
type-level direction to these somaSide groups remains an assumption.

Body translation and takeoff follow current heading. Commands decoded at an
interval end drive the next interval; they cannot change an earlier collision.
