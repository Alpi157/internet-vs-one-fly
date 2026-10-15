# V2E findings

Only model-level claims are permitted. H0 was pilot-motivated; all confirmatory null seeds are fresh.

| Circuit | Family | Metric | Real | Null median | 95% null band | Effect | p | Holm p | Status |
|---|---|---|---:|---:|---|---:|---:|---:|---|
| T1a | N-FULL | H0a | 0.11 | 0.03 | [0.03, 0.039] | None | 0.004 | 0.008 | COMPUTED |
| T1a | N-FULL | H0b | 2.650681560015146 | 113.67434683831881 | [79.56061719045816, 134.73644358197652] | -111.02366527830367 | 0.004 | 0.008 | COMPUTED |
| T1a | N-CONTEXT | H0a | 0.11 | 0.03 | [0.03, 0.039] | None | 0.004 | 0.008 | COMPUTED |
| T1a | N-CONTEXT | H0b | 2.650681560015146 | 110.73218477849301 | [80.90180045437334, 137.7639984854222] | -108.08150321847786 | 0.004 | 0.008 | COMPUTED |
| T1a | N-SIGN | H0a | 0.11 | 0.03 | [0.03, 0.03] | None | 0.004 | 0.008 | COMPUTED |
| T1a | N-SIGN | H0b | 2.650681560015146 | 119.77872018174934 | [101.71613498674745, 135.69438091631957] | -117.12803862173419 | 0.004 | 0.008 | COMPUTED |
| T1b | N-FULL | H0a | 0.11 | 0.03 | [0.02, 0.03] | None | 0.01 | 0.02 | COMPUTED |
| T1b | N-FULL | H0b | 18.00393339333933 | 143.6046804680468 | [120.48601710171017, 163.66219351935192] | -125.60074707470747 | 0.01 | 0.02 | COMPUTED |
| T1b | N-FULL | H1a | -1.0 | -1.0 | [-1.0, -0.49499999999999994] | 0.0 | None | None | insufficient calibratable nulls |
| T1b | N-FULL | H1b | 40.0 | 30.0 | [10.0, 40.0] | 10.0 | None | None | insufficient calibratable nulls |
| T1b | N-FULL | H1c | 0.5936507936507935 | 0.12666666666666668 | [0.016666666666666666, 0.35333333333333333] | 0.46698412698412683 | None | None | insufficient calibratable nulls |
| T1b | N-FULL | H2a | 80.88998763906056 | 77.20756595321055 | [62.294658399850135, 162.64148632979305] | 3.6824216858500165 | None | None | insufficient calibratable nulls |
| T1b | N-FULL | H2b | 0.23137300319297513 | 0.1349007842902623 | [0.04079716781702376, 0.23993394444802246] | 0.09647221890271282 | None | None | insufficient calibratable nulls |
| T1b | N-FULL | H2c | 0.06835726702785772 | -0.45275318790238617 | [-1.0, 0.8581437612228262] | 0.5211104549302439 | None | None | insufficient calibratable nulls |
| T1b | N-CONTEXT | H0a | 0.11 | 0.03 | [0.02, 0.03] | None | 0.01 | 0.02 | COMPUTED |
| T1b | N-CONTEXT | H0b | 18.00393339333933 | 140.55851485148514 | [109.93273987398739, 161.65485103510352] | -122.5545814581458 | 0.01 | 0.02 | COMPUTED |
| T1b | N-CONTEXT | H1a | -1.0 | NA | NA | NA | None | None | insufficient calibratable nulls |
| T1b | N-CONTEXT | H1b | 40.0 | NA | NA | NA | None | None | insufficient calibratable nulls |
| T1b | N-CONTEXT | H1c | 0.5936507936507935 | NA | NA | NA | None | None | insufficient calibratable nulls |
| T1b | N-CONTEXT | H2a | 80.88998763906056 | NA | NA | NA | None | None | insufficient calibratable nulls |
| T1b | N-CONTEXT | H2b | 0.23137300319297513 | NA | NA | NA | None | None | insufficient calibratable nulls |
| T1b | N-CONTEXT | H2c | 0.06835726702785772 | NA | NA | NA | None | None | insufficient calibratable nulls |
| T1b | N-SIGN | H0a | 0.11 | 0.03 | [0.02, 0.03] | None | 0.01 | 0.02 | COMPUTED |
| T1b | N-SIGN | H0b | 18.00393339333933 | 127.52824482448246 | [112.65584518451845, 140.44748379837984] | -109.52431143114313 | 0.01 | 0.02 | COMPUTED |
| T1b | N-SIGN | H1a | -1.0 | -1.0 | [-1.0, -0.8569999999999987] | 0.0 | None | None | insufficient calibratable nulls |
| T1b | N-SIGN | H1b | 40.0 | 30.0 | [20.0, 59.00000000000027] | 10.0 | None | None | insufficient calibratable nulls |
| T1b | N-SIGN | H1c | 0.5936507936507935 | 0.19333333333333333 | [-0.007333333333333334, 0.38666666666666666] | 0.4003174603174602 | None | None | insufficient calibratable nulls |
| T1b | N-SIGN | H2a | 80.88998763906056 | 72.92028985507247 | [56.94195658785009, 130.74042551211315] | 7.969697783988096 | None | None | insufficient calibratable nulls |
| T1b | N-SIGN | H2b | 0.23137300319297513 | 0.09629789881735923 | [0.011276218548394903, 0.23759973541541454] | 0.1350751043756159 | None | None | insufficient calibratable nulls |
| T1b | N-SIGN | H2c | 0.06835726702785772 | 0.34230670495754684 | [-1.0, 1.0] | -0.2739494379296891 | None | None | insufficient calibratable nulls |

Critical coupling 0.11 in the machine tables is a rank sentinel meaning censored above 0.1, not a measured value. Secondary circuits and fixed-parameter comparisons are descriptive.

## Calibration

- T1a N-FULL: 145/499 calibratable; real passing points 0; selected None. Matched calibration statistics are in tables.json.
- T1a N-CONTEXT: 0/499 calibratable; real passing points 0; selected None. Matched calibration statistics are in tables.json.
- T1a N-SIGN: 90/499 calibratable; real passing points 0; selected None. Matched calibration statistics are in tables.json.
- T1b N-FULL: 21/199 calibratable; real passing points 4; selected {'gain': 8, 'kappa': 0.05, 'nu0_hz': 5, 's': 0.01, 'threshold_int': 1111880680, 'w_noise': 0.3175750723556395}. Matched calibration statistics are in tables.json.
- T1b N-CONTEXT: 0/199 calibratable; real passing points 4; selected {'gain': 8, 'kappa': 0.05, 'nu0_hz': 5, 's': 0.01, 'threshold_int': 1111880680, 'w_noise': 0.3175750723556395}. Matched calibration statistics are in tables.json.
- T1b N-SIGN: 37/199 calibratable; real passing points 4; selected {'gain': 8, 'kappa': 0.05, 'nu0_hz': 5, 's': 0.01, 'threshold_int': 1111880680, 'w_noise': 0.3175750723556395}. Matched calibration statistics are in tables.json.

## Conclusions

- T1a H0: Model-level differences from the listed shuffles were detected. See metric directions and effects; this does not establish a requirement in real flies.
- T1a H1: Not run; no calibratable real graph in the executed scope.
- T1a H2: Not run; no calibratable real graph in the executed scope.
- T1b H0: Model-level differences from the listed shuffles were detected. See metric directions and effects; this does not establish a requirement in real flies.
- T1b H1: No computable confirmatory comparison; inspect missing values and calibratable-null counts.
- T1b H2: No computable confirmatory comparison; inspect missing values and calibratable-null counts.

## Secondary analyses and controls

Full descriptive fixed-parameter results, Spearman correlations, lesion results, stochastic control fit and mismatches, and timer results are in tables.json. No secondary superiority claim is made.

## Compute and verification

Summed task wall time: 427071.621 s. Tasks overlap across workers; this is not elapsed wall time. Hardware: {'platform': 'Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.39', 'hardware_threads': 24}.

```sh
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
```

This recomputes tables from raw per-trial records and checks every frozen file.
