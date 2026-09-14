**Catch the Fly: architecture for a fast public release**

**Decision.** Keep Catch the Fly. Target a public v0.1 alpha in approximately fourteen calendar days of focused work, then deepen its performance and experimental capabilities through a v0.2 release over the following two to four weeks. These are planning targets, conditional on the neural-control and usability gates below, not delivery guarantees. Reduced working hours or a failed biological assumption extend the schedule.

This revision replaces the earlier twelve-week release sequence and reduces the launch architecture itself. It is not a proposal to fit the previous platform into two weeks. The attached discussion with GPT 5.6 Sol is the immediate input; the earlier biological and numerical caveats still apply. Naming is deferred until the release needs a package/repository identifier. No new naming exercise is on the critical path.

The public experience remains: aim, commit a strike, see the approaching threat, try to catch the fly, then watch the decisive moment in slow motion with recorded neural activity. The reusable engineering product begins with that exact experiment's runner and portable recording. Generalization follows working use cases.

**1. Assessment of Sol's proposal.** Sol is right to preserve the product, ship a complete narrow implementation, separate experimental model parameters from architecture, and move useful public milestones earlier. DesktopFly's similar sensory mechanism does not make an adversarial browser game redundant. Product identity can differ even when a biological pathway is shared.

I would correct five points. First, fourteen days is an alpha target, not evidence that the underlying simulation will work. Second, four response/ablation tests establish basic behavior and control dependence, not biological validation. Third, a telegraphed strike improves timing control but does not eliminate network/presentation latency. Fourth, the game needs meaningful choices and responsive feedback, not simply maximum difficulty. Fifth, per-player comparison against rewired graphs is additional scientific and operational scope; it must not block launch.

One factual correction to the discussion: DesktopFly's current README includes a MaleCNS locomotor component alongside its FlyWire escape circuit. Describe the product difference accurately rather than saying it has no MaleCNS runtime component. Its existence is implementation precedent, not independent validation of our model. Source: [DesktopFly README](https://github.com/DenisSergeevitch/desktop-fly).

The prior architecture put too many mature-platform capabilities near the first-release path: several recording formats, checkpoint/resume, generalized backend support, storage services and comprehensive topology comparisons. Those were defensible eventual features. They are not all needed to make the first release credible.

**2. Preserve depth in four pieces of engineering.** The project should contain difficult, inspectable work from the first public release: deterministic compilation of a large biological graph; an explicit neural model with a clear reference implementation; an authoritative environment loop with isolated session state; and a bounded recorder whose artifact can be re-executed.

These pieces reinforce one another. A large graph alone is not the portfolio story; a pretty game alone is not the portfolio story. The substantive result is a human interaction that produces an inspectable artifact, tied to an exact graph and model, with measured runtime behavior. Complexity should appear in the problem solved and evidence produced, not in a large number of services.

| Capability | Public v0.1 alpha | v0.2 and later |
|---|---|---|
| Catch the Fly | Polished short game, honest model scope | Better mechanics and scientifically grounded directional behavior |
| Neural execution | One fixed model and CPU implementation | Further optimization; another backend only when justified |
| Data | One pinned MaleCNS importer; selected circuit and full-graph audit | Additional datasets and richer annotations |
| Flight Recorder | One meaningful event view, slow playback, download | Richer comparison, selected-neuron queries and regeneration |
| Re-execution | From reset, one documented runtime envelope | Complete checkpoints and broader compatibility |
| Benchmarks | Scripted stimuli, authority controls, ordinary controller, performance report | Multiple topology nulls, uncertainty estimates and sensitivity studies |
| Public capacity | Fixed small worker pool and busy response | Queue, batching or more hosts only after measured demand |
| Persistence | Temporary local files and immediate download | Opt-in public sharing and object storage |
| Extensions | Plain Python modules and small contracts | Stable plugin interface after outside use |

**3. The product contract.** Use one arena, one short round format and one main result. An initial target is a 20–30 second round with bounded attacks and a visible cooldown. Keep aim-and-click/tap input; do not add a tutorial screen, account, multiplayer lobby or research dashboard before play.

The fly can walk using a simple, seeded, threat-independent movement rule. The neural model controls the escape trigger. The body turns that command into a fixed, disclosed takeoff primitive relative to the fly's current heading. Arena boundary handling belongs to ordinary mechanics. No movement rule may secretly use the threat to select an evasive direction.

This is a deliberate first-release claim: “The neural model controls escape decisions. Walking and movement mechanics are simplified.” It is not a claim that the connectome generates all locomotion. Ambient movement makes aiming meaningful without requiring a walking-controller research project. If a credible neural locomotion mapping already works during the initial experiment, it can replace the ambient rule under a separately identified profile; it is not a launch prerequisite.

After the player commits, lock the strike position and make the approaching threat visible. Resolve impact on the authoritative simulation clock. On escape, render the takeoff clearly. On failure, make contact visually legible. After the round, open a slow-motion replay with strike, sensory input, neural output and escape command aligned in time.

The first playtest must ask whether accurately aimed attacks have a meaningful range of outcomes under the declared model. A stationary fly, identical initial state and identical strike stimulus can yield the same result every time. That is a product failure even when the neural code is correct. Test mechanics by day 3 or 4, using a clearly labeled ordinary controller until the neural controller is available; never silently ship the ordinary controller as connectome-driven.

Keep neural parameters fixed while tuning game parameters such as strike footprint, approach timing, cooldown and ambient speed. Version those game settings too. If the game remains trivial or frustrating, alter the mechanic and record the change. Do not invent physiological parameters to manufacture a desired win rate or add adaptive hidden handicaps.

The neural state continues through a normal round, including walking and cooldown. There is no implicit reset or frozen brain between attacks. Round reset is an explicit experimental reset. This prevents an optimization from silently changing adaptation and history.

Public copy: “Try to catch a digital fly whose escape decisions are controlled by a neural model built from measured fruit-fly wiring.” Display the actual executed graph size. “166,000 neurons” is allowed only if that profile actually executes at that scale; allocated but disabled nodes do not justify an inflated functional claim.

**4. Keep scientific assumptions inspectable, but stop expanding the model.** MaleCNS supplies reconstructed connectivity and biological annotations, not a complete executable nervous system. The initial candidate remains a small, declared current-based LIF model. Its parameters belong to a versioned experiment profile, never to the framework's permanent architecture.

Use LC4/LPLC2 and a giant-fiber/DNp01 output as candidate ports, resolving their exact identities and sides against the pinned MaleCNS release. Their role in looming responses is supported by prior work, but transfer of labels and function to an executable MaleCNS profile still requires checking. Source: [Ache et al., looming size and velocity encoding](https://www.janelia.org/publication/neural-basis-for-looming-size-and-velocity-encoding-in-the-drosophila-giant-fiber-escape).

Start with feature-level stimulation: convert threat geometry into explicit angular size, expansion and spatial drive. State that this bypasses early visual computation. Do not claim that a generic whole-neuron LIF model reconstructs visual processing from pixels. Read out an abstract descending escape command; do not claim that chemical connectivity reproduces the complete electrical-synapse/muscle/wing chain.

The encoder receives observations. The decoder receives declared neural outputs, its own previous state and parameters. It cannot receive cursor position, threat distance, bearing, future impact information or an “away” vector. The environment implements movement, collision and visual presentation.

Keep the earlier normalized LIF candidate as a starting experiment, avoiding a new model-design detour: tau_m=20 ms, tau_s=5 ms, threshold=1, rest/reset=0, refractory=2 ms and delay=1 ms. These are model choices, not MaleCNS measurements. Between arrivals, use tau_m dv/dt = -v + I + u and tau_s dI/dt = -I, with weighted current jumps at synaptic arrivals. Specify integration, threshold/reset and refractory semantics. The current continues evolving while voltage is held in refractory state in this candidate.

Similarly, the baseline sign mapping is an explicit effective-current assumption: ACh positive; GABA/histamine negative; glutamate negative in this particular candidate; unknown, unsupported and modulatory classes omitted from fast current. Preserve probabilities/confidence, report affected edge/contact mass, and allow only documented overrides. If behavior depends on an unsupported or uncertain mapping, narrow the claim or revise the profile. Do not silently resolve it.

Freeze a small declared calibration panel and a limited gain/input-amplitude search during the first experiment. Publish the attempted settings, not only the attractive result. Include no-threat, looming and matched non-looming controls, and at least a small neighborhood around the selected parameters. No twenty-dimensional optimization campaign is on the launch path.

The day-2 scientific gate is: exact mapped ports and connectivity are recorded; stimulus changes relevant output; output clamping from reset removes the escape command; a declared pathway intervention changes the modeled response; and there is no runaway or permanently saturated operating regime. These are functional engineering checks. They do not establish reproduction of natural fly behavior or superiority of biological wiring.

If that gate fails, first narrow to a documented circuit/context extract and timing-only escape. If it still fails, keep the repository and clearly labeled prototype available, but do not announce a functioning connectome-controlled public game. A deadline cannot authorize a false controller claim.

**5. Compile once, run many times.** Use the official v1.0 bulk files, not live scientific API queries during gameplay. The downloadable weights table covers segments beyond the selected neuron population; the compiler must define accepted nodes before building the execution graph. Python access is supported. Source: [MaleCNS downloads](https://male-cns.janelia.org/download/).

Implement one importer, not an ingestion framework. Its output is a small graph bundle: source metadata/hashes, ordered biological IDs, source-major offsets, target indices, raw counts and compiled weights. Map biological IDs to contiguous runtime indices deterministically. Keep source counts separate from weights and preserve node selection, confidence filters, normalization and omitted signaling as explicit transformations.

Sort source and target indices. Use read-only NPY arrays: int64 offsets, int32 target indices within checked bounds, float32 weights and uint64 biological IDs. In a source-major matrix A[source,target], the reference input propagation is A.T multiplied by the spike vector. Do not get orientation wrong while optimizing.

A selected circuit and the full accepted graph are two artifacts from the same importer. Report N, E, represented contacts, isolated nodes, unknown labels, filtered mass and input/output port mappings. For the circuit, report cut incoming and outgoing contact mass. Full-context behavioral comparison is a v0.2 priority; explicitly mark it pending at alpha if not completed.

Using N=166,700 and E=26 million solely as a rounded sizing example, targets plus float32 weights take about 208 MB; offsets add about 1.33 MB. One float32 state value per neuron takes about 0.667 MB. These are payload estimates, not imported counts, actual RSS or throughput measurements. A full graph can fit in memory while remaining too expensive to update in real time.

Keep source license and attribution with each distributed derived fixture. Do not put bulk arrays in ordinary Git history. Ship one small, licensed circuit fixture for onboarding and separate synthetic fixtures for correctness tests. Full-data download is explicit.

**6. One model, one optimized implementation, one reference.** Retain a clear NumPy/SciPy reference and one restricted Numba implementation of the same candidate model. Use serial deterministic accumulation within a session, no unsafe fast-math changes, and source-major traversal of active spikers. Fixed-delay queues hold spike IDs rather than individual edge-delivery objects. No plasticity or mutable per-contact state.

Do not build a backend registry, equation DSL or multiple production simulator integrations. A small boundary between ModelSpec, GraphBundle and Runner is enough. Existing research implementations can supply reference equations and reusable properly licensed components, but their biological validation does not transfer automatically. The original Shiu repository is useful reference material and is MIT-licensed. Source: [Shiu model repository](https://github.com/philshiu/Drosophila_brain_model).

The optimized kernel must agree with analytical fixtures and the clear reference before serving public play. Brian2 cross-checks on small circuits remain desirable, but a full third packaged backend is deferred. If an optimization is the thing breaking the deadline, serve the verified reference on the small circuit at measured capacity and mark the optimized path experimental. Do not require original kernel authorship merely for resume decoration.

At 0.5 ms, the rounded full graph entails about 333 million neuron updates per simulated second even before connection propagation. Time-stepped activity-sparse propagation is not a fully event-driven simulator. Actual cost depends on the outgoing degrees of firing neurons, their rates and bursts, memory access and recording.

Run the first full-graph performance probe with a wall-time limit. Measure loading, graph memory, initialization, one control interval and a bounded simulated duration. Quiet, nominal and sustained approved inputs are separate cases. An upper bound or timeout is an honest result; it is not evidence of interactive feasibility.

Give full-graph live execution one initial profiling pass and at most one clearly targeted optimization pass during alpha development. If it misses the selected host's deadline, use the disclosed circuit profile for launch. Do not move to GPUs, browser execution or coarse unvalidated timesteps to save the headline. Publish the full-graph audit and the actual completed timing measurements separately.

**7. The complete runtime loop.** One runner owns all logical time. Both CLI and server invoke it. Start with a 0.5 ms neural step and 10 ms control interval, then check neural steps of 0.25 and 0.1 ms on relevant fixtures and stimuli. Use the coarse candidate only if its declared response errors are acceptable; do not tune the tolerance after examining results. The browser draws at display refresh independently.

At time t, apply accepted player inputs, form the observation and encode it. Advance neural state over [t,t+h] under the declared input-hold rule. Advance the environment over the same interval using the previously held command c(t), resolving scheduled impacts. Decode the new command c(t+h) for the next interval. Newly computed escape must never be applied retroactively to an earlier collision.

The essential functions are load_graph, reset_run, advance_control_interval, finish_run and verify_run. State objects cover neural arrays, pending spikes, RNG state, encoder history, decoder filters, held command, environment state, tick and recording counters. They remain explicit even though general checkpoint/resume is deferred.

Keep one frozen model profile per deployed release. Starting another session, changing the recorder view, or slowing a browser must not change a session's modeled trajectory. If a server cannot keep pace, stop new admission and end substantially lagged games as infrastructure-invalid. Offline execution can be slower than real time.

A provisional goal is p99 control completion around 7 ms for a 10 ms control interval, including scheduled work, at admitted capacity. This is a proposed headroom target, not a measured result or an absolute tail-latency guarantee. Record real misses and their causes.

**8. Public serving: one host and one worker per game slot.** Build the browser UI with TypeScript, Vite, a conventional component framework and Canvas 2D for the arena. Use the same built assets for a loopback local demo and production. No 3D engine is necessary for the first presentation. Use a single FastAPI application serving the built frontend and API on one origin, behind a standard TLS reverse proxy.

The application owns a fixed set of warm simulation worker processes, initially one or two. Each worker maps the graph read-only and owns at most one active game. This removes multiplexing, batching and scheduler complexity. The gateway owns only admission, authentication, networking and artifact delivery. Limit numerical-library threads to prevent oversubscription.

Workers receive bounded control messages over local IPC and publish bounded state updates. Every message carries a session ID plus a generation counter; the gateway discards late output belonging to a previous occupant of a worker. Do not reload the graph or compile the kernel for every round. Reset private state completely at session start.

Admission reserves a worker, reset/warm-up occurs, the server sends ready, and scored time begins after client acknowledgement. Expire a reservation that never becomes ready. The lifecycle is idle, reserved, ready, running, finalizing, idle; crashes take the worker out of admission until restarted and warmed.

The browser sends bounded coordinates, attack intents and monotonically increasing sequence numbers. The runner records the accepted, quantized values and their applied logical ticks. Coalesce pointer updates by a fixed latest-value rule; give committed attacks stable identifiers and ordering. Validate finite values, bounds, frame size and input rate.

The alpha needs just admission, active WebSocket, owner-authorized artifact download, model information and health endpoints. The browser renders authoritative state with interpolation and predicts only its own aim indicator. It does not invent escape motion to hide lag. A telegraph helps, but does not eliminate Internet latency or make global human scores scientifically comparable.

No waiting-room subsystem: return a clear busy response with retry guidance and offer a curated recorded run. Do not claim a queue position unless a queue exists. Do not say “one fly is fighting four humans” when four independent simulation states are actually running. Say “All live game slots are busy.”

During a brief five-second reconnect window, the authoritative world continues with the last accepted aim state and no new attack commitments; already scheduled impacts still occur. On expiry, terminate as disconnected and release the slot. Freeze-on-disconnect would enable a free-pause exploit.

A single Docker image for app/worker code plus the reverse proxy configuration is enough. Mount the compiled graph read-only and a bounded local artifact directory read-write. No Kubernetes, message broker, database, distributed scheduler or cloud worker fleet.

**9. Recorder v0.1: one small format.** The first .flyrun is a standard ZIP containing manifest.json, events.jsonl and summary.json. Use one schema version and a few event types. This replaces the original launch plan's multiple Parquet tables, preview derivative and checkpoint files. JSONL is appropriate for the bounded alpha trace; typed columnar exports can be added without changing the logical event contract.

The manifest records dataset/graph hashes, exact model/encoder/decoder/environment configuration, executed node/edge counts, code version, dependency lock, tested runtime envelope, initial conditions, RNG algorithm/seeds, clock semantics, selected probes, validity and payload hashes. All defaults must be resolved. An opaque config ID and a seed are insufficient.

Events include accepted inputs, attack commits/impacts, selected sensory samples, selected neural summaries, relevant output-spike timestamps, motor commands, environment frames, lifecycle changes and recorder gaps. Every record has a type, integer tick and documented phase; wall time is separate operational metadata. Preserve decisive neural output events at neural-tick resolution even if the plots are sampled at 20–50 Hz.

The browser consumes the same event schema as the archive. The live stream may omit optional visualization frames under backpressure; completed replay loads the finalized event data rather than pretending the partial live stream is complete. Sparse visualization frames may be interpolated; the UI must not invent missing neural measurements. No second browser neural simulator is needed.

Set an initial hard uncompressed trace budget of 4 MB per 30-second round and measure typical size. Preallocate/bound essential input and outcome capture separately from optional probes. Do not allocate a Python object for every neuron update; collect selected values in the kernel and serialize small batches at control boundaries. When optional data is lost, record a gap. If essential input evidence is lost, mark the run incomplete and do not certify re-execution.

Exact whole-state digests can be sampled periodically, starting around once per simulated second and at completion, subject to measured overhead. Hash canonical meaningful scientific state, including valid delayed events, RNG state and held commands. Exclude uninitialized buffer capacity, addresses and wall time.

Use three identifiers: a unique run ID from admission; a profile/recipe hash; and a finalized content digest. A human input schedule is not known at admission, so the completed manifest references its actual input payload hash. The manifest hashes payloads only, never itself; the external content digest authenticates the canonical finalized manifest. Do not create a circular checksum inventory.

Playback reads recorded frames/events. Re-execution resets the original model and applies the original accepted inputs. They are separate operations with separate results. For alpha, support only re-execution from reset on a documented pinned CPU environment. Preserve independent per-session RNG streams and stable draw order. No general mid-run resume is promised.

The verify command first checks integrity, schemas and dependencies. With re-execution requested, compare scientific-state/action digests and report pass, mismatch or unsupported environment. A mismatch is not “close enough” for an exact badge. Where only periodic original digests exist, report the first mismatching interval. Finding the first divergent tick requires rerunning both implementations in compatible environments.

A graph may be referenced rather than included in the archive. Clearly distinguish a lightweight replay from a self-contained scientific bundle. Ship the small demonstration graph and its hash with the release so the advertised quickstart can actually reproduce it. Keep bulky full-graph assets outside each downloaded game.

**10. The first recorder screen is a product feature.** Show the arena replay beside one synchronized timeline with stimulus, selected neural output, escape command and impact. Select a decisive attack automatically and allow 0.25× playback. Annotate “escape command occurred X ms before modeled impact” only from recorded logical events, not fabricated narrative. Separate command timing from actual body clearance.

Make the result screen useful without reading a paper: caught/missed, attempts, a short replay and “Inspect the escape.” Offer a model card and download. Do not show 166,000 nodes, a generic graph editor, arbitrary neural queries or a dashboard full of unexplained units.

Avoid unearned causality. “This recorded activity preceded the escape command” is safe when supported. A separate model intervention can establish dependence inside the modeled system. Neither is a statement about what caused behavior in a living animal.

The first comparison can be a checked-in or precomputed controlled example, using the same runner: normal model, output clamped, and a conventional looming controller. Label it as a recorded example. Re-running each visitor's entire game against a rewired graph would add compute and scientific scope; defer it.

**11. Local artifacts and budget caps.** No SQLite or object storage is required for this alpha. Write a completed artifact atomically to a bounded local directory, return an owner-authorized download capability, and expire it after 24 hours. Set a hard directory limit, initially 1 GB, and clean expired entries periodically. If there is no room for a promised artifact, reject new recorded sessions before allocation rather than falsely promising a download.

In-memory admission metadata is sufficient; a gateway restart ends live sessions. This is acceptable for a short game. A finalizing worker remains occupied until its bounded completion handoff has succeeded or failed explicitly. Do not mark a half-written artifact as complete. Artifact delivery failures should produce an honest unavailable status, while any already received browser data can still support immediate playback.

Public arbitrary share links, accounts and durable histories are deferred. Curated sample runs can be static release assets. An optional CDN can cache frontend assets; it is not another application service that must be built. The single-host design remains usable without it.

Select one affordable fixed CPU host only after measuring the approved live profile. An initial planning envelope is approximately US$50–100/month if acceptable, not a provider quote or a guaranteed total. Prefer fewer sessions over an unbounded scaling policy. Account for transfer allowances and cap metered delivery exposure; fixed compute does not cap every possible bill.

Enforce worker count, maximum round length, reservation timeout, reconnect grace, admission/input rates, message bytes, trace bytes, local spool and artifact-read limits. A provider billing alert is additional monitoring, not enforcement. Keep a switch to stop live admission while static examples remain available.

Use short-lived session capabilities, ownership checks and WebSocket Origin checks. Accept only allowlisted release profiles. Reject nonfinite and oversized input before expensive allocation. Run unprivileged workers with read-only graph access and no credentials they do not need.

Do not collect free-text names, general webpage mouse movement or raw operational headers in scientific recordings. Retain only game actions and coordinates required by the model. Downloads are data-only; shared/local archive readers reject traversal paths, oversized expanded data and unsupported schemas. Never deserialize pickle or execute content from a replay.

**12. Testing and evidence that cannot be cut.** Keep tests that protect the scientific claim and public resource boundary. Defer a comprehensive simulator conformance suite, broad platform matrix and full checkpoint tests until their features exist.

| Required alpha check | Why it remains on the critical path |
|---|---|
| Graph identity, ordering, direction and endpoint bounds | Prevents accidentally simulating the wrong wiring |
| Analytical decay and small sign/delay/reset fixtures | Establishes basic numerical correctness |
| Reference-versus-compiled comparison | Detects optimization errors |
| Output clamp and declared pathway intervention | Tests actual neural control |
| Recorded-input re-execution from reset | Makes the central artifact promise real |
| Recorder enabled/disabled scientific-state agreement | Prevents observation from changing the model |
| Session churn and stale-message rejection | Protects isolation and worker reuse |
| Flood, slow client, disconnect, full spool and worker crash | Establishes bounded public operation |
| Clean installation and local replay | Makes the repository usable outside the author’s machine |

Measure real graph counts, load/build time, actual memory, per-control-interval latency, wall seconds per simulated second, active-neuron/event work, recording overhead, bytes/run and concurrent capacity. Report graph/model/timestep, hardware, versions, recording level and actual workload. Distinguish kernel timing from end-to-end serving.

On pull requests, run the small offline test suite, frontend build and packaged quickstart smoke test. Run full-data benchmarks manually for alpha/release with resource bounds; ordinary public CI should not download the full graph on every change. Use independent repeated timing samples on the chosen host, not a single attractive measurement.

Before launch, test one and two active sessions with nominal and sustained approved stimuli, a slow client and input flooding. Run a bounded soak long enough to reveal growth and lag. Freeze admission at a passing capacity with headroom. Report measured limits honestly if the result is one live slot.

**13. Minimum benchmark and v0.2 scientific work.** Ship one scripted stimulus family and one headless game/threat policy. Record all per-trial outputs and include the no-output control and a conventional threshold controller with the same declared sensory information and actuator limits. This is already useful for regression testing.

For alpha, report response latency, false escapes, capture probability at the chosen horizon, horizon-capped survival, instability and infrastructure-invalid counts. Separate game time, neural time and network delay. A round that reaches its horizon is not a death at the horizon.

Do not claim that output clamping proves the biological topology matters. Do not claim that the biological model beats artificial intelligence. Do not treat human sessions as a controlled benchmark: humans adapt to a changed trajectory, and replaying their original cursor path creates a fixed input-schedule experiment.

In v0.2, add multiple directed degree-preserving null graphs with explicit sign/weight handling, diagnostics for incoming strength and reachability, paired scenario seeds, held-out calibration, uncertainty estimates and negative results. If a null becomes silent or saturated, report it and distinguish a fixed-parameter comparison from an equally calibrated-controller comparison.

The later “Try your attack against another wiring configuration” feature must consume capped counterfactual compute or run locally. It is a new run, not a reconstruction of the original adaptive-human encounter. Blinded human comparisons and persistent collective play remain later product experiments.

**14. Repository and developer experience.** Use one package and one web application, with modules rather than separately published packages.

| Path | Purpose |
|---|---|
| src/flybench/data.py | One pinned importer, compiler and audit |
| src/flybench/model.py | Candidate profile and model definitions |
| src/flybench/reference.py | Clear numerical implementation |
| src/flybench/kernel.py | Restricted optimized implementation |
| src/flybench/runner.py | Logical time and complete round state |
| src/flybench/encoding.py | Sensory and motor mappings |
| src/flybench/catch.py | Headless environment, mechanics and scripted threat driver |
| src/flybench/recording.py | Bounded event schema, export and verification |
| src/flybench/cli.py | Demo, benchmark, inspect and verify commands |
| apps/server/ | Admission, WebSocket, worker IPC and temporary files |
| apps/web/ | Game, result screen and focused recorder |
| profiles/ and fixtures/ | Versioned assumptions, small data and reference runs |
| tests/ and experiments/ | Required checks and reproducible measurements |

The working package name is temporary. Split a module only when it grows enough to justify it. ModelSpec and GraphBundle can be simple typed data structures. Avoid abstract factories, plugin managers and configuration inheritance frameworks.

A developer should install the package, run the small local demo, complete a round, inspect/download it and re-execute it without credentials or GPU access. The local server serves prebuilt frontend assets; users do not need Node just to inspect a recording. Contributors use Vite for frontend development. A full-data command performs the larger download explicitly.

The proposed CLI shape is demo, bench, inspect, verify and data fetch/compile. Command names and artifact schema are small contracts worth documenting. Everything else remains an internal implementation until actual outside use establishes a need for stability. This is a specification, not a claim that these commands are already implemented or published.

**15. Revised implementation sequence.** Work in small end-to-end increments. Bring deployment and playtesting forward instead of leaving them until the last two days.

| Target window | Deliverable and decision |
|---|---|
| Days 1–2 | Pin data; compile circuit/full audit; define model; obtain stimulus-to-output trace; run authority tests and bounded full-graph timing |
| Days 3–4 | Playable local loop; early external-host smoke test; first unfamiliar-player feedback; choose live graph profile |
| Days 5–6 | Canonical accepted-input recording, reset re-execution, immediate slow replay and event timeline |
| Days 7–8 | One/two worker admission, timeouts, resource caps, temporary downloads, conventional baseline and benchmark output |
| Days 9–10 | Fix usability/numerical issues; profile one real bottleneck; measure recording overhead and capacity; clean-install test |
| Days 11–12 | Capped hosted beta, broader feedback, overload tests, README/video and source/model notices |
| Days 13–14 | Fix launch blockers, reproduce release artifacts, tag public v0.1 alpha and publish measured limitations |
| Following 2–4 weeks | v0.2: context sensitivity, stronger topology study, deeper optimization and external reproduction |

This schedule assumes the early functional model works. Days 1–2 timebox investigation; they do not demand a successful scientific conclusion on command. If mapping or neural control is unresolved, communicate the blocker and revise the claim. Do not keep polishing a website while assuming the core will eventually work.

The public repository can become visible with the first reproducible example, and a short local video can appear before broad launch. Label synthetic-controller previews and incomplete capabilities clearly. Job applications can use actual completed milestones while deeper work continues.

A public alpha is complete when a visitor can play, inspect a recorded moment, download the run, and follow documented instructions to re-execute the supported profile; the server has measured limits and no hidden evasion policy. A topology paper, a universal framework and a high-concurrency fleet are not part of that definition.

**16. Codex implementation workflow.** Use this document as the current scope contract. Coding assistance reduces the cost of scaffolding, UI implementation, tests and mechanical changes. It does not remove the need to inspect biological mappings, validate equations, choose honest comparison rules or measure performance.

Start with a runnable fixture and a single complete experiment. Keep changes small enough that one result can be reviewed: one command, one artifact and a short account of what passed or remains uncertain. A feature is not complete because its files exist; it is complete when its acceptance behavior runs. Do not ask for the entire platform in one implementation task.

For each task, supply the objective, allowed files/boundaries, invariants, acceptance command and what is explicitly deferred. Keep the scientific invariants and release scope in the repository's AGENTS.md or equivalent contributor instructions. New functionality must not silently change the frozen model; a changed model or game rule gets a new profile/version.

Suggested implementation task sequence:
1. Compile and audit the pinned dataset; create small fixtures and biological-ID mappings.
2. Implement and test the chosen candidate model and transparent sensory/output mapping.
3. Run the headless looming scenario with required controls and write the first complete artifact.
4. Wire the same runner into the local game and test whether aiming/escape is meaningful.
5. Implement replay and exact-from-reset verification before broader UI.
6. Add the fixed-slot server, bounded inputs and temporary artifact downloads.
7. Measure, fix the demonstrated bottleneck, verify public failure behavior and prepare release evidence.

A suitable first Codex brief is:

“Implement the first headless Catch the Fly experiment from the current architecture. Begin with a pinned MaleCNS graph compiler, a clearly labeled small fixture, a transparent reference model and stimulus-to-output trace. Preserve source contact counts separately from weights. The decoder must receive no threat geometry. Include no-threat, looming, output-clamped and pathway-intervention checks. Produce the exact graph/profile identities and a runnable acceptance command. Perform a bounded full-graph timing probe if the data is available. Do not add cloud deployment, GPUs, plugin discovery, learned controllers or undocumented neural tuning. If the biological mapping is unresolved, report that gap instead of inventing it.”

Review the scientific mappings, numerical semantics and control dependencies yourself before accepting their implementation. Ask Codex to show a profiler result before accepting a performance rewrite. Make the code and experiment history readable enough that you can defend the decisions without relying on generated explanations.

**17. What is explicitly deferred.** No GPU/browser runtime, session batching, persistent Internet-vs-Fly state, checkpoint/resume, public share service, database, object store, real waiting room, arbitrary public experiment submission, learned decoder, plasticity, multiple production models, detailed morphology, realistic biomechanics, global leaderboard, accounts or chat in the alpha.

An immutable graph format, explicit state and versioned events preserve future options without implementing them now. Add object storage when public links need durable retention. Add a queue when short waits demonstrably improve conversion. Add another backend when it resolves an observed limitation. Add checkpoints when restart-from-reset is too expensive. Add Parquet/Zarr when the actual record volume or analysis workflow warrants them.

**18. Resume and launch standard.** For a recruiter, the first explanation is short: “I built an interactive fly-connectome experiment with recorded neural activity and downloadable, reproducible runs.” For a technical interviewer, the evidence is concrete: sparse representation and compiler audits, differential numerical tests, explicit time/order semantics, independent session state, resource caps and a measured recorder.

A strong alpha resume bullet should use only achieved scope: “Built a connectome-derived escape experiment with replay-verifiable human interaction, a shared sparse graph runtime and bounded public sessions; published numerical checks and performance measurements.” Insert actual counts, latency and memory only after measurement. If the live graph is small and the full-graph work is offline, keep those results separate.

The v0.2 goal is a measurable performance result plus a controlled scientific comparison that someone else reproduces. That is where the broader ML/research-engineering story becomes especially strong. No number of technologies compensates for missing evidence; a compact system with a defensible optimization and independently rerunnable result can be impressive.

The release strategy is therefore: ship the smallest complete version of the product quickly, retain four technically demanding foundations, and make every subsequent release add evidence rather than speculative architecture.
