# V2C parameter units

Rest is 0 and firing threshold is 1. Executable edge weights are biological contact
count times source sign, normalization none. Unknown signs remain disabled with
contact mass reported. Synaptic scale s is the current jump per contact.

The exact discrete update gives a unit impulse response
v[n] = (b^n - a^n)/3, where b is the voltage decay and a is the current decay.
The implementation evaluates the same recurrence as ReferenceStateV2 until the
unique peak, without a threshold crossing. PSP_UNIT is 0.15744308780006205 at
end tick 18 (9 ms). A contact at scale s has peak PSP s*PSP_UNIT.

The opened MIT-licensed [Shiu model repository](https://github.com/philshiu/Drosophila_brain_model)
was checked at commit 91bdd1e7dcf193f3e7ca5a8933497fcef63b7960. Relevant parameter
lines in [model.py](https://github.com/philshiu/Drosophila_brain_model/blob/91bdd1e7dcf193f3e7ca5a8933497fcef63b7960/model.py):

```python
'v_0' : -52 * mV,
'v_th' : -45 * mV,
'w_syn' : .275 * mV,
```

The anchor is verified: 0.275/7 = 0.039285714285714285. The reviewer grid uses
0.039 as a rounded anchor. This is a current-jump comparison, not a claim of
identical whole-model physiology. Shiu's refractory, delay, reset and integration
implementation differ from this model. Nothing was tuned to circuit output.

Grid s: {0.005, 0.01, 0.02, 0.039, 0.06}. For noise, kappa is the peak fraction
of threshold per event, w_noise = kappa/PSP_UNIT. nu0 is the firing rate of a
noise-only isolated neuron. The nine-row table records deterministic integer
threshold bisection over 200 simulated seconds, seed 2026101401, stream 17,
flybench.u32.v2. Refractory, current decay and event order match ReferenceStateV2.
Finite reset-neuron rates need not be strictly monotone in threshold; the declared
search keeps the closest evaluated rate and records residual errors.

Input gain {1, 2, 4, 8} multiplies normalized geometry features. The decoder gains
and speed bounds are declared in its profile before the circuit dry run.

V2D amendment: profiles/noise-v2.json excludes visual ports and every declared
output port including DNb02. profiles/noise-table-v2.json supersedes the 200 s
fit for V2D only. Four fixed seeds each run 1000 s per bisection evaluation; two
new seeds each run 2000 s for validation. The pooled validation tolerance is
max(0.05*nu0, 3*sqrt(nu0/4000)) Hz. All evaluated thresholds and counts are retained.
No validation failure is refitted. Movement classification uses inclusive
0.002 units/ms and 0.0005 rad/ms thresholds on the applied command.
