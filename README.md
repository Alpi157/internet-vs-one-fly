# Catch the Fly

Six strikes against a simulated fly driven by measured neural wiring.

![A recorded takeoff and brain-cam replay](docs/media/catch-the-fly-v2e.png)

## What it is

Catch the Fly is a browser game whose walking, turning and takeoff requests come
from a spiking neural simulation. It executes a 5,555-neuron MaleCNS circuit locally
and replays recorded spikes after each strike. The accompanying experiment tests
measured wiring against equally calibrated shuffled graphs.

## What is real and what is simplified

The T1b graph contains 759,305 measured directed connections representing 7,397,244
biological contacts. Original body IDs and contact counts survive compilation and
lossless browser transport. The model uses uniform LIF neurons, predicted source
signs, feature-level vision, assumed turn directions and abstract takeoff physics.
Unknown signs remain disabled; missing soma coordinates remain explicitly missing.
The brain map uses relative x/z positions with unverified physical units and
anatomical orientation. It shows recorded spikes, including fading afterglow,
without inventing neural observations.

## Results and status

V2E is submitted for review with the confirmatory run in progress. Hosting has not
been enabled. The [public preregistration tag](https://github.com/Alpi157/internet-vs-one-fly/tree/prereg-v2)
fixes the protocol at `1a853f40007dcf10fb113c29a8400a7f99a3addb` before confirmatory
execution. [The protocol](docs/preregistration-v2.md), [freeze manifest](profiles/freeze-v2.json)
and [push receipt](docs/preregistration-receipt-v2.json) are committed.

| Outcome | Status |
|---|---|
| H0: dynamic stability | Pending; disclosed as pilot-motivated, fresh confirmatory nulls |
| H1: held-out escape | Pending |
| H2: spontaneous movement | Pending |
| Full-grid real calibration | T1a uncalibratable; T1b selected by the frozen fallback rule |

T1b uses s=0.01, kappa=0.05, isolated nu0=5 Hz and visual gain=8. Calibration is
not evidence of a wiring advantage. Failed points and uncalibratable nulls remain
in the experiment. See [CONTINUE.md](CONTINUE.md) for the running job and remaining
analysis. No claim about a requirement in real flies follows from this model.

## Engineering

- Bit-exact state-digest checks cover the readable Python reference, Numba,
  TypeScript and Chromium, Firefox and WebKit within the declared float64 and
  integer-clock envelope. Browser parity uses 200 intervals per fixture/circuit.
- Counter-based RNG streams, explicit resets, immutable topology and atomic
  per-graph/stage outputs make scientific tasks resumable and independent of
  worker count and scheduling order. Preflight compares one and three workers.
- The decoder receives spikes and prior rates only. It receives no hand position,
  bearing, distance or future collision information. Previously held commands
  drive the current interval, before any newly decoded escape request.
- A profiler-driven TypeScript pass retained exact digests. Selected T1b median
  wall seconds per simulated second were 0.130 Chromium, 0.302 Firefox and 0.156
  WebKit, versus 0.500, 1.665 and 0.599 before the pass on this development host.
- The measured non-lab build is 1,329,773 compressed bytes. The separately loaded
  lab adds 1,483,138 bytes. Committed game data is 4,021,214 bytes, below 8 MB.
- Game version 6 meets the 10% to 70% target for all ten development bots, with
  60 strikes per strategy. Versions 2 to 5 failures are retained in review evidence.
  These reused scripted seeds do not establish human usability.

Exact measurements, scope and uncertainty are in
[measurements-v2e.json](docs/measurements-v2e.json). Browser numbers come from
headless desktop engines under concurrent scientific load, not phone hardware.

## Play locally

Python 3.12, uv and Node 24 are used by the locked development setup. Committed
browser data means local play needs no MaleCNS download, credentials or GPU.

```sh
uv sync --extra dev --locked
npm --prefix apps/play ci
npm --prefix apps/play run dev
```

Open `http://127.0.0.1:5173/internet-vs-one-fly/`. Tap for a flick, hold for a slap,
or hold longer for a swat. The visible descending hand and growing shadow depict
the looming stimulus. After each strike, replay the recorded brain at 0.25x.
The lab explicitly resets the simulation for lesions or the predeclared scramble.
Export a 1200x630 result card or a 720x1280 replay clip where MediaRecorder is
supported. Chromium and Firefox WebM exports were verified; this WebKit environment
does not provide the clip export. Sound and reduced-motion settings are local.

## Reproduce

The small test path uses committed fixtures and game data:

```sh
npm --prefix packages/kernel-ts ci
uv run python -m pytest -q tests/test_v2e.py tests/test_v2e_freeze.py
npm --prefix packages/kernel-ts run test:fixture
npm --prefix apps/play test
npm --prefix apps/play run build
```

After dependencies are cached, these checks need no network or full connectome.
The complete scientific run requires the pinned raw data and compiled graphs:

```sh
uv run flybench data fetch --lock profiles/source-lock.json --out data/raw --report evidence/V2E/sources.json
uv run flybench data compile --lock profiles/source-lock.json --selection profiles/accepted-neurons.json --out data/compiled/full
uv run python -m flybench.circuit build-v2 --out evidence/V2E/circuit-build
uv run python -m pytest -q tests/test_v2e_freeze.py
uv run python experiments/v2e_dry_run.py --out evidence/V2E/dry-run-4
uv run python experiments/v2e_preflight.py
cp docs/preregistration-receipt-v2.json evidence/V2E/preregistration-receipt.json
uv run python experiments/v2e_run.py --workers 12 --resume --out evidence/V2E/results
uv run python experiments/v2e_analyze.py --out evidence/V2E/results
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
```

The original real calibrations took 28.23 s for T1a and 71.88 s for T1b. The
pre-null projection for the full run was 4.85 hours on 12 workers. That is an
estimate from measured pilot timings, not a measured completion time. Data
acquisition and graph compilation are additional. A frozen-file mismatch or
recorded defect stops execution; never patch frozen code to continue this attempt.

Stage acceptance, including three-browser tests and fresh-clone smoke:

```sh
uv run python tools/run_acceptance.py V2E --out evidence/V2E/acceptance
```

The Pages workflow is manual-only and has not been triggered. Its configured URL
is `https://alpi157.github.io/internet-vs-one-fly/`; this is not a live-hosting claim.

## Limitations

This is a selected circuit, not the full fly brain. Neurotransmitter signs,
feature-level sensing, decoder directions and body physics are modeling assumptions.
No learning, plasticity, realistic biomechanics, human-player experiment, public
verification server or shared score is included. The scramble in the lab uses real
selected parameters and is explicitly not calibrated. Replay displays recorded data;
it does not infer observations across gaps. Hypothesis results remain pending.

## Data attribution and citation

MaleCNS v1.0 is published by the Male CNS Connectome project, a collaboration
including FlyEM at HHMI Janelia, Cambridge, MRC LMB and Google Research. The
[official download page](https://male-cns.janelia.org/download/) identifies the
CC-BY license. Cite the [MaleCNS study linked by the project, Cell (2026)](https://www.cell.com/cell/fulltext/S0092-8674%2826%2900942-6)
and [dataset release](https://male-cns.janelia.org/). Source URLs and observed
SHA-256 values are in [source-lock.json](profiles/source-lock.json); browser-derived
data attribution and hashes are in [LICENSE-DATA.md](apps/play/public/data/LICENSE-DATA.md)
and [HASHES.json](apps/play/public/data/HASHES.json).

## License

Underlying MaleCNS data is CC-BY. A software license has not yet been declared by
the repository owner; the data license does not grant a license to FlyBench code.
