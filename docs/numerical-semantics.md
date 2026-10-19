# M05 reference numerical semantics

This document defines the readable float64 oracle for the normalized LIF candidate. All neural parameters are **MODEL ASSUMPTIONS, not MaleCNS measurements**. The integration and event-order rules are project numerical conventions, not physiology validation.

## Equations and state

Time is measured in milliseconds. Voltage and synaptic current use normalized model units. For held external drive `u` between boundaries:

```text
tau_m * dv/dt = -v + I + u
tau_s * dI/dt = -I
```

The accepted parameters are `tau_m=20 ms`, `tau_s=5 ms`, rest/reset `0`, threshold `1`, refractory `2 ms`, and delay `1 ms`. State consists of float64 voltage and synaptic current, exact integer refractory-until ticks, fixed-delay pending source-spike/direct-input rings, logical tick, and one state-owned NumPy `Generator(PCG64(seed))`.

For one interval of length `dt`, define `em=exp(-dt/tau_m)` and `es=exp(-dt/tau_s)`. Then:

```text
I1 = I0 * es
v1 = rest + (v0-rest)*em + u*(1-em)
     + I0*tau_s/(tau_s-tau_m)*(es-em)
```

When the time constants are equal, the coupled term is the exact limit `I0*(dt/tau_m)*em`. Explicit Euler is not the oracle.

## `flybench.neural-order.v1`

At boundary `t_k`, the reference accumulates every due signed synaptic-current jump in deterministic source-major order. It then establishes the explicit drive held over `[t_k,t_{k+1}]`, evolves current, and evolves voltage only for neurons eligible at `t_k`. A refractory neuron's voltage remains exactly at reset for the entire interval; its current still receives arrivals and decays.

At `t_{k+1}`, eligible neurons spike when `v >= threshold`; equality spikes. Spiking voltage resets immediately, refractory begins at that boundary, and outgoing source spikes are queued for exactly `t_spike + 1 ms`. No spike can affect a preceding interval. Release occurs when the interval start tick equals `refractory_until_tick`.

The graph convention remains `A[source,target]`. Active source rows are traversed directly, which is equivalent to `A.T @ spike_vector`; no dense circuit matrix is used.

## Input, scaling, and RNG

External drive is explicit and held for one neural interval. Compiled base weights remain raw contact count times accepted effective sign. `runtime_synaptic_scale` is a separate ModelSpec field; M05 uses `1.0` only as a numerical-fixture value, not a calibrated release value.

Every state owns a distinct PCG64 generator created from an explicit seed. Zero/rest initialization and the v0.1 deterministic equations consume zero random draws. Reset reconstructs all mutable arrays, rings, tick, refractory state, and RNG owner from the seed. Global NumPy RNG state cannot affect reference evolution.

## Frozen numerical decision

`profiles/numerical-criteria-v0.1.json` was committed before measurement. The 0.1 ms run is the comparison reference. Candidates are tested in order 0.5 then 0.25 ms, and the coarsest candidate satisfying every frozen criterion is selected. Delay/refractory durations must be exact positive integer tick counts; unsupported grids are rejected rather than rounded.

The panel contains analytical subthreshold evolution, a constant-drive spiking neuron, and a signed delayed network. Stimulus changes occur only at integer-millisecond boundaries. A passing numerical result does not establish physiology, behavioral calibration, whole-CNS equivalence, performance, or closed-loop correctness.
