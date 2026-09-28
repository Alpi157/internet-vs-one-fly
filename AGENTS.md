# FlyBench repository instructions

Authority order for work after M09 is `docs/plan-v2.md`, then the unchanged v1 history in `docs/architecture.md`. Where they disagree, plan v2 wins. Work only on the current stage in `ledger.yaml`. Scientific deviations require evidence and a recorded decision.

## Invariants

- **I1:** Pin biological sources and order IDs and edges deterministically. Original biological body IDs remain recoverable. Biological contact counts remain separate from executable weights.
- **I2:** Neural, sign, encoder, and decoder assumptions are explicit and versioned. Unknown or omitted biology remains explicit. Never invent mappings.
- **I3:** All walking, movement, and escape are neural. The motor decoder receives no threat geometry: no cursor coordinates, attack target, threat bearing, distance, future collision information, or away vector, including through closures, globals, callbacks, helper objects, environment references, or hidden shared state. Threat can influence movement only through the network. The environment never implements a hidden substitute escape controller.
- **I4:** CLI and web ultimately use the same Runner. Logical time uses integer clocks. The previously held command drives the current interval. A newly decoded command cannot apply retroactively to an earlier impact or collision.
- **I5:** Neural state persists within a normal round. Reset is explicit and complete. RNG streams and mutable session state are independent. Immutable graph topology may be shared; mutable scientific state may not.
- **I6:** Record authoritative applied input, resolved provenance, and bounded essential and optional traces. Trace gaps remain explicit. Exact re-execution claims require a declared supported envelope.
- **I7:** Playback means recorded data, not neural re-execution. Never invent or interpolate missing neural observations. Displayed graph and model counts match the executed scope.
- **I8:** Gameplay executes client-side. Only server-verified runs enter shared data. Overload delays verification and never changes a model.
- **I9:** Owner, Origin, and capability controls are required where applicable. Run archives are data-only. Gameplay telemetry is minimal. Secrets never enter public artifacts or review ZIPs.
- **I10:** Benchmarks use controlled scripted workloads and comparable interfaces. Failures and censoring remain explicit. Weak controls do not support biological-superiority claims.
- **I11:** The first-success and CI path is small and offline. No credentials, GPU, or full MaleCNS download is required. Only measured quantities may become quantified claims.
- **I12:** The deferred list is section 10 of `docs/plan-v2.md`. Deviations require explicit evidence and a recorded decision.

## Process

- Keep hashes of scientific identities, including the source lock, graphs, model profiles, and calibration protocols.
- Freeze protocols by commit before running them.
- Make claims only from the claims ladder in plan v2.
- Agents never mark work accepted.
- Use one external review per stage. A stage may contain several phases.
- Perform a dry run before freezing any protocol.
- Wording and metadata fixes do not require a new attempt. Check them as review conditions next time. A new attempt is required only if results or executed code change.
- Create decision records only for scientific changes to the model, graph, protocol, calibration, or claims. Mechanical fixes need only a commit message.
- Add no new review tooling unless existing tooling blocks work. The `tools/` tree should not grow faster than `src/`.
- Keep the ledger short: current state, identities, and gate decisions. Keep v1 history under `docs/history/`.
- The implementing agent may be Codex or Claude Code. The same rules apply.
