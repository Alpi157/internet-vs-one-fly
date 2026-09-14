# FlyBench repository instructions

The authority is `docs/architecture.md` (SHA-256 `bae80837d5d6d769ae5b728af3b80c1caa21b7f08efdd7f3eb458f7bb2eab9d1`) and the FlyBench execution playbook, version 0.1. Work only on the current ledger milestone. Architecture deviations require evidence and a recorded decision.

## Invariants

- **I1:** Pin biological sources and order IDs/edges deterministically. Original biological body IDs remain recoverable. Biological contact counts remain separate from executable weights.
- **I2:** Neural, sign, encoder, and decoder assumptions are explicit and versioned. Unknown or omitted biology remains explicit. Never invent mappings.
- **I3:** The motor decoder receives no threat geometry: no cursor coordinates, attack target, threat bearing, distance, future collision information, or away vector, including through closures, globals, callbacks, helper objects, environment references, or hidden shared state. Ambient locomotion is threat-independent. The environment never implements a hidden substitute escape controller.
- **I4:** CLI and web ultimately use the same Runner. Logical time uses integer clocks. The previously held command drives the current interval. A newly decoded escape command cannot apply retroactively to an earlier impact or collision.
- **I5:** Neural state persists within a normal round. Reset is explicit and complete. RNG streams and mutable session state are independent. Immutable graph topology may be shared; mutable scientific state may not.
- **I6:** Record authoritative applied input, resolved provenance, and bounded essential/optional traces. Trace gaps remain explicit. Exact re-execution claims require a declared supported envelope.
- **I7:** Playback means recorded data, not neural re-execution. Never invent or interpolate missing neural observations. Displayed graph/model counts match the executed scope.
- **I8:** Public alpha uses a fixed host/pool and one active session per worker. Messages, lifetimes, and disk are bounded. Overload never silently modifies the model.
- **I9:** Owner, Origin, and capability controls are required where applicable. Run archives are data-only. Gameplay telemetry is minimal. Secrets never enter public artifacts or review ZIPs.
- **I10:** Benchmarks use controlled scripted workloads and comparable interfaces. Failures and censoring remain explicit. Weak controls do not support biological-superiority claims.
- **I11:** The first-success and CI path is small and offline. No credentials, GPU, or full MaleCNS download is required. Only measured quantities may become quantified claims.
- **I12:** Architecture section 17 scope remains deferred. Deviations require explicit evidence and a recorded decision.

Codex narration is not evidence. “Tests pass” text alone is not acceptance. Codex may submit work but must not mark a milestone accepted. M01 acceptance is issued only by the external reviewer after inspecting the review ZIP.
