# Catch the Fly

Try to swat a simulated fly driven by measured fruit-fly wiring, then replay the spikes behind its escape.

**[Play Catch the Fly](https://alpi157.github.io/internet-vs-one-fly/)**

![A played hand followed by its recorded BrainView replay](docs/media/game-hero.gif)

- **Science:** [preregistered comparisons](docs/preregistration-v2.1.md), a stricter input-strength control that overturned part of the headline, and [raw records with a DOI](https://doi.org/{{dataset_doi}}).
- **Engineering:** [bit-exact parity across Python, Numba, TypeScript and three browsers](packages/kernel-ts/test/browser-parity.mjs), WebGL rendering of [real neuron skeletons](docs/ui-v2h.md), and [reproducible acceptance](tools/acceptance.json).
- **Game:** aim, hold and drop your hand; replay recorded spikes, shuffle partners or silence a circuit in the wiring lab. No account or tracking.

## The finding

{{original}}

{{combined}}

Rates at coupling {{coupling}} in the registered comparisons:

{{comparison_table}}

{{mechanism}}

{{bin_note}} {{limits}}

The [original pre-registration](docs/preregistration-v2.md) was publicly timestamped on **{{original_date}}** and the [robustness protocol](docs/preregistration-v2.1.md) on **{{robustness_date}}**, before their runs. [Full family results and limits](docs/findings-v2f.md).

![Measured rate versus the earlier N-SIGN shuffles; the stricter control removes most of this gap](docs/media/T1a-N-SIGN-H0-curve.png)

![Recorded lab switching from partner shuffle to input-strength control at the game-calibrated coupling](docs/media/coupling-hero.gif)

The lab recording switches between the existing fixed-rule N-SIGN and median-rate N-STRENGTH demos. Live numbers are separate from registered results. [Media provenance](docs/media/media-provenance.json) records seeds, identities and capture details.

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

The game executes a calibrated **{{game_n}}-neuron** circuit. The coupling lab executes **{{lab_n}} neurons** in each simulation. The full accepted graph contains **{{full_n}} neurons**. Original body IDs and contact counts remain separate from executable weights. Unknown signs remain disabled. BrainView uses pinned MaleCNS skeletons in a composite of the brain frontal view and nerve cord underside view, simplified for display.

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
uv run python tools/restore_evidence.py --archive /path/to/flybench-raw-records-v2e-v2f.tar.gz
uv pip install --no-deps -r profiles/requirements-v2.1.txt
uv run python tools/recompute_v2e.py
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
uv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify
uv run python experiments/v2f_publish.py --check
```

The raw-record dataset DOI is [{{dataset_doi}}](https://doi.org/{{dataset_doi}}). `uv run python tools/restore_evidence.py --download` retrieves the checksum-pinned archive. Both frozen verifiers run offline after restoration; the older verifier also compares recorded host metadata, so its exact equality check requires the recorded platform and thread-count envelope. `tools/recompute_v2e.py` is independent of that frozen CLI verifier: it uses the same frozen analysis functions and compares every result field against the committed tables, ignoring only `hardware`. It restores nothing and works outside the recorded host envelope. Verification processes the raw records without running a simulation. Reproducing the registered experiment from scratch requires the pinned sources and graphs in the [data guide](docs/data-attribution.md), plus the exact commands and worker plan in the [protocol](docs/preregistration-v2.1.md). The completed run's elapsed time above is a measurement, not a runtime guarantee. Do not patch a frozen executable to continue an attempt.

## Limitations

The strength-preserving comparisons did not replicate the registered stability result. There is no learning, plasticity, realistic biomechanics, human-player study, public verification service or shared score. Scripted bot results are engineering evidence, not human usability evidence. EXPLORATORY analyses cannot support confirmatory claims. A difference from a shuffle does not establish biological necessity or identify a unique mechanism.

## Data attribution, citation and license

MaleCNS is published by the Male CNS Connectome project, including FlyEM at HHMI Janelia, Cambridge, MRC LMB and Google Research. The [official download page](https://male-cns.janelia.org/download/) identifies the CC-BY license. Cite the [MaleCNS study](https://www.cell.com/cell/fulltext/S0092-8674%2826%2900942-6) and [dataset release](https://male-cns.janelia.org/).

Source URLs and observed hashes are in [source-lock.json](profiles/source-lock.json). Browser asset attribution and hashes accompany the committed data. See [CITATION.cff](CITATION.cff) for software and dataset citation metadata. Code is [MIT licensed](LICENSE); underlying and derived MaleCNS data remains [CC-BY](LICENSE-DATA.md).
