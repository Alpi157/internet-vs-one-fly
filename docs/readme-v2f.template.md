# Catch the Fly

A simulated fly driven by measured neural wiring. Try to swat it, then compare measured and shuffled wiring under the same model.

![Recorded comparison of measured and shuffled wiring as coupling increases](docs/media/coupling-hero.gif)

**[Play Catch the Fly](https://alpi157.github.io/internet-vs-one-fly/)** · Live after deployment.
Tap for a flick or hold for a slower, wider strike. Open the coupling lab to compare measured and scrambled wiring side by side.

## The finding

{{original}}

{{summary}}

{{limits}}

The [original pre-registration](docs/preregistration-v2.md) was publicly timestamped on **{{original_date}}**, before execution. The [robustness protocol](docs/preregistration-v2.1.md) was published on **{{robustness_date}}**, before its run; [the receipt records the exact UTC publication time and commit](docs/preregistration-receipt-v2.1.json).

![Measured circuit rate and N-SIGN null band across coupling](docs/media/T1a-N-SIGN-H0-curve.png)

The clip demonstrates the original N-SIGN comparison, not the strength-preserving control. The lab scramble is the first seed at the family's median critical coupling, selected by a fixed rule. Heat and meters use recorded simulation spikes; the speed factor reports simulated time per wall second. The strength-preserving comparisons above limit the broader interpretation.

## How it works

```mermaid
flowchart LR
    A[MaleCNS measured wiring] --> B[Deterministic compiler]
    B --> C[Selected circuit or full graph]
    C --> D[LIF model: Python and Numba]
    C --> E[Equivalent TypeScript model]
    D --> F[Resumable experiment runner]
    E --> G[Browser game and coupling lab]
```

Visual features enter neural input ports. Spikes reach a motor decoder that receives no hand position, distance or future collision information. The previous command drives the current interval, so a new escape cannot alter an earlier hit.

## Engineering highlights

- Bit-exact state-digest checks cover Python, Numba, TypeScript, Chromium, Firefox and WebKit within the declared execution envelope.
- Publicly timestamped protocols and freeze manifests pin code, graph identities, assumptions, seeds and analysis before confirmatory execution.
- Atomic per-task results and deterministic seeds support resume independently of worker scheduling. The robustness run took **{{hours}} hours** on a **{{threads}}-thread** host, with peak process RSS **{{peak}} GiB**.
- Cached canvas rendering raised mobile-viewport WebKit frame opportunities from **{{before}} to {{after}} fps** in the comparable measurement window. Active mobile gameplay measured **{{live}} fps**; the coupling lab measured **{{labfps}} fps**. These are headless desktop engines, not physical iPhone measurements.
- The recorded initial compressed build scope is **{{initial}} MB**, with the **{{coupling}} MB** coupling lab and **{{lesion}} MB** lesion lab loaded separately. Missing neural observations remain missing.
- Offline fixtures, cross-runtime parity, scripted bots, browser screenshots, production base-path checks and fresh-clone acceptance make the implementation inspectable. [Measurement details](docs/measurements-v2f.json) state each scope.

## Run locally

Use the locked Python and Node development setup. Committed browser data means local play needs no credentials, GPU or connectome download.

```sh
uv sync --extra dev --locked
npm --prefix apps/play ci
npm --prefix apps/play run dev
```

Open the localhost URL printed by Vite with the `/internet-vs-one-fly/` base path. The Pages workflow is manual-only. Deployment remains an operator action.

## For scientists

The game executes a calibrated **{{game_n}}-neuron** circuit. The coupling lab executes **{{lab_n}} neurons** in each simulation. The full accepted graph contains **{{full_n}} neurons**. Original body IDs and contact counts remain separate from executable weights. Unknown signs remain disabled. Soma maps use relative coordinates with unverified physical units and anatomical orientation.

The model uses uniform current-based LIF neurons, assumed source signs, feature-level vision, declared turn-direction assumptions and abstract takeoff physics. Noise excludes visual and decoder ports. Moving the coupling slider explicitly resets both simulations with the same seed; normal game rounds retain neural state. Dropping the hand adds visual input to both neural simulations.

**Escape and walking comparisons remain insufficient.** The selected real circuit calibrated, but only {{calibration}} nulls did. The preregistered threshold was not reached. There are no confirmatory escape or walking superiority claims.

### CONFIRMATORY robustness

{{table}}

Critical coupling above the tested grid is censored. A non-significant result does not establish equivalence. A significant opposite-direction rate does not support the registered stability claim. Full [findings](docs/findings-v2f.md) include figures, null bands, censoring and exact [result tables](docs/results-v2f.json).

### EXPLORATORY checks

{{exploratory}}

[Original findings](docs/findings-v2e.md) · [Original tables](docs/results-v2e.json) · [Robustness freeze manifest](profiles/freeze-v2.1.json).

Verify the existing raw records without simulating new trials:

```sh
uv pip install --no-deps -r profiles/requirements-v2.1.txt
uv run python experiments/v2f_analyze.py --out evidence/V2F/results
uv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify
uv run python experiments/v2f_publish.py --check
```

Analysis takes seconds on this host after the records are available. Reproducing the registered experiment from scratch requires the pinned sources and graphs in the [data guide](docs/data-attribution.md), plus the exact commands and worker plan in the [protocol](docs/preregistration-v2.1.md). The completed run's elapsed time above is a measurement, not a runtime guarantee. Do not patch a frozen executable to continue an attempt.

## Limitations

The strength-preserving comparisons did not replicate the registered stability result. There is no learning, plasticity, realistic biomechanics, human-player study, public verification service or shared score. Scripted bot results are engineering evidence, not human usability evidence. EXPLORATORY analyses cannot support confirmatory claims. A difference from a shuffle does not establish biological necessity or identify a unique mechanism.

## Data attribution, citation and license

MaleCNS is published by the Male CNS Connectome project, including FlyEM at HHMI Janelia, Cambridge, MRC LMB and Google Research. The [official download page](https://male-cns.janelia.org/download/) identifies the CC-BY license. Cite the [MaleCNS study](https://www.cell.com/cell/fulltext/S0092-8674%2826%2900942-6) and [dataset release](https://male-cns.janelia.org/).

Source URLs and observed hashes are in [source-lock.json](profiles/source-lock.json). Browser asset attribution and hashes accompany the committed data. See [CITATION.cff](CITATION.cff) for software and dataset citation metadata. Code is [MIT licensed](LICENSE); underlying and derived MaleCNS data remains [CC-BY](LICENSE-DATA.md).
