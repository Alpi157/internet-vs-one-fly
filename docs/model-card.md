# Candidate model card v0.1

This card freezes an M04 candidate for later numerical implementation. No simulator, timestep result, calibration outcome, or behavioral claim is part of M04.

## Scientific status

Every parameter in this card is a **MODEL ASSUMPTION, not a MaleCNS measurement**. The candidate is a normalized leaky integrate-and-fire model with `tau_m = 20 ms`, `tau_s = 5 ms`, rest `0`, reset `0`, threshold `1`, refractory period `2 ms`, and delay `1 ms`.

M05 must study timesteps `0.5 ms`, `0.25 ms`, and `0.1 ms` and determine which, if any, meets the later numerical criteria. M04 makes no numerical-acceptance claim.

## Weight convention

The immutable compiled base weight remains `raw_contact_count * accepted_effective_sign * 1.0`, with no compile-time normalization. A separate later `ModelSpec` parameter named `runtime_synaptic_scale` applies runtime scale and must participate in model identity. It may not be hidden in the environment or decoder.

The bounded candidate values are frozen in `profiles/calibration-plan.json`. M04 does not run them.

## Scope and limitations

The candidate uses the ports-only induced circuit in `profiles/escape-circuit.json`. Omitted context is a deliberate intervention quantified in M04 cut-context evidence. Natural neural dynamics, cellular diversity, compartmental structure, electrical coupling, plasticity, neuromodulation, and body mechanics are not represented by this candidate.
