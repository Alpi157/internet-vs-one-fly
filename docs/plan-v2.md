# Catch the Fly v2: plan and scope contract

Status: authority for all work after M09. Supersedes sections 3, 4, 8, 9 and 15 of
`docs/architecture.md` (v1, kept unchanged as history) and milestones M10-M24 of the
v1 execution playbook. Everything in the v1 architecture that this file does not
change still applies.

## 1. Central question

Does the measured MaleCNS wiring change the fly's behavior compared with fake wiring
that has the same statistics? The game is both the product and the instrument that
collects the answer. Any outcome, including a negative one, is published.

Audiences: players (a fly that is hard to catch and feels alive), scientists
(pre-registered experiment with fair controls), recruiters and interviewers (live
link, video, bit-exact multi-runtime parity, measured numbers).

## 2. Known problems of v1 that v2 must fix

| Problem | Evidence | Fix |
|---|---|---|
| Wiring contributes almost nothing | Every LC4 gets one scalar, every LPLC2 another; populations spike in lockstep; synaptic scale 0.001; the intervention removes the only path to the output; static size drives more than looming | H1 with equally calibrated null graphs, side-split input, wider circuit |
| Game is close to deterministic | Same looming schedule for every strike, independent of aim; escape command about 30 ms before impact every time | Truth check against a fixed-latency controller, geometry-dependent stimulus, strike speed choice, neural walking |
| Process heavier than product | tools/ about 6.3k lines vs src/ about 8.8k; M09 at attempt 3 | Process v2 (section 8) |
| Full graph unused | 0.82-1.13 wall s per simulated s unoptimized; optimization pass unused; context likely silent at scale 0.001 | H3 offline first, then one optimization pass |
| Fresh clone cannot run | data/ is ignored; demo needs about 1 GB of sources | Small licensed circuit fixture in the repository |
| No capacity for traffic | 1-2 server workers | Deterministic kernel in the browser, server only verifies |

## 3. Hypotheses (protocol frozen by commit before any run)

| ID | Question | Primary metric | Comparison |
|---|---|---|---|
| H1 Escape | Does real wiring escape differently from fake wiring? | First escape command offset before impact; escape probability vs strike speed; looming vs non-looming difference | At least 20 degree- and sign-preserving null graphs |
| H2 Walking | Is spontaneous movement structured differently? | Speed, bout and pause duration distributions, turn autocorrelation, left/right asymmetry | Same noise fed straight to the decoder without the network; null graphs |
| H3 Context | Does the rest of the brain change the escape? | DNp01 first-spike tick and rate | Circuit vs full graph, same stimulus, offline |
| H4 Humans | Can players tell real from fake? | Real/Fake accuracy vs 50%; catch rate | Blind random assignment |

Controls for every profile: no threat; looming; non-looming with the same final size;
output clamp; LC4 lesion; LPLC2 lesion; turning-neuron lesion; noise straight to decoder.

Equal calibration rule: null flies are calibrated with the same grid, the same budget
and the same target criteria as the real fly. Matched calibration statistics are
published next to every comparison.

Statistics: H1-H3 use the percentile of the real graph within the null distribution
(permutation test). H4 uses a binomial test with a sample threshold or stop date
fixed in advance. No decisions are made while data is being collected.

Claims ladder:

| Outcome | Allowed claim | Not allowed |
|---|---|---|
| H1 positive | In this model, measured wiring produces different escape behavior than random graphs with the same statistics | That real flies work this way |
| H1 negative | Under these assumptions behavior is set by input and threshold, not by wiring details | That wiring does not matter |
| H4 above chance | Players told real from fake wiring in X% of N rounds | That humans recognize biology in general |
| H3 no effect | Full-brain context did not change the escape at these parameters | That context does not matter in flies |

Human data: anonymous game actions only, explicit consent before upload, no names or
extra headers.

## 4. Model v2

All fly movement, escape and walking, goes through spikes. Code only supplies noise,
body physics and rendering.

Circuit selection rule (parameters fixed before any behavior run):
1. Seeds: LC4 and LPLC2 split by `somaSide`; DNp01 left and right; walking descending
   neurons from the literature (MDN backward walking, Bidaye et al. 2014; P9, oDN1, BPN
   forward walking, Bidaye et al. 2020; DNa01 and DNa02 turning). A seed is used only
   after an exact canonical annotation match in MaleCNS v1.0 and reviewer receipt. Not
   found means excluded and recorded, never invented.
2. Expansion: neurons within one hop upstream of output DNs and one hop downstream of
   visual seeds with at least S synapses to or from a seed.
3. Tiers: T1 browser (size chosen by a phone performance budget), T2 server/offline
   (lower S or two hops), T3 full graph 166,700 neurons, offline only. Exact N, E and
   cut contact mass are published for each tier.

Spontaneity: background spikes with probability p per tick for a declared population,
from an integer counter-based RNG implemented identically in Python and TypeScript,
compared against an integer threshold (no exp, no log). p is a calibration parameter.
Seed and all deviations are recorded.

Synaptic scale is recalibrated together with p and input gain in a frozen grid. These
are new profiles; G-BIO, parity and replay evidence are rebuilt for v2.

Encoder v2: the strike descends at the aimed point with a player-chosen speed; angular
size and expansion come from the real hand-to-fly distance, so a far strike gives a
weak signal. Strike azimuth relative to the fly's heading splits drive between left
and right LC4/LPLC2 by a declared rule. Finer retinotopy only if measured spatial
coordinates exist in the data.

Decoder v2 receives spikes only (I3). Escape: a left or right DNp01 spike starts
takeoff. Walking: forward speed from forward-walking DN rate minus MDN rate; turn rate
from left minus right DNa01/DNa02 rate; declared filter and disclosed speed limits.
Stops, bursts and freezing must come from the network, not from a separate rule.

## 5. Game v2

Player decisions: where, when and how fast to strike (fast strike: less warning,
smaller footprint; slow strike: bigger footprint, longer warning), and approach side.

Modes: Classic (6 strikes, 20 s round); Real or Fake (guess the wiring after the
round, feeds H4); Lesion Lab (disable a neuron group and play again); Daily Fly (same
seed for everyone that day, spoiler-free share card).

Brain-cam replay at 0.25x: arena plus spike raster and the neurons that fired before
the jump, drawn at real positions only if the data has them, otherwise by circuit
layer, always labeled. Client-side clip export. Global "Internet vs the fly" score
from verified runs only.

Honesty rules: game settings change only through versioned game profiles and never
touch neural parameters; no hidden difficulty; the null fly in Real or Fake is
calibrated like the real one.

Usability evidence: no human playtest panel is available. Degenerate mechanics are
caught with scripted bot players with human-like limits (reaction delay, aim noise,
lead strategies): catch rate must not be 0% or 100% for reasonable bots, and no single
trivial strategy may dominate. The soft launch is the first human usability evidence.
No usability claim is made before public data exists.

## 6. Architecture v2

The game runs entirely in the player's browser. A small server re-executes uploaded
runs and accepts into the score and H4 data only runs that match bit for bit.

| Component | Where | Responsibility | Based on |
|---|---|---|---|
| TypeScript kernel | Browser, Web Worker | Port of `_serial_step` with the same event order; spike ID lists instead of scanning all N | kernel.py, M07 parity |
| Runner and game | Browser | Same integer ticks, previous-held command, no retroactive escape | runner.py, game.py |
| Recorder | Browser | Applied inputs, seeds, digests; .flyrun simplified to what is needed | recording.py |
| Upload API | One small host | Consent only, size and rate limits, no accounts | v1 section 11 limits |
| Verifier | Same host, queue | Re-execute a round from its input log; mismatch means excluded | planned v1 verify |
| Offline research | Local or rented CPU | Null graphs, T2 and T3, H1-H3 | bench.py, performance_probe.py |

Bit-exact parity: JavaScript numbers are IEEE-754 float64 like the model state. Add,
multiply and compare are identical everywhere for the same operation order. exp and
randomness are removed from the kernel path: decay constants ship precomputed in the
profile bundle and the noise RNG is integer. Gate: identical per-interval state
digests for fixtures and random input logs in Chrome, Firefox and Safari.

Removed from the main path: server game workers, WebSocket play, slot admission (v1
M12-M13). They remain a fallback if browser parity fails.

## 7. Invariants

I1-I7, I9-I11 from v1 remain. Changes:
- I3 extended: walking is neural now; the decoder still receives no threat geometry.
  Threat can influence movement only through the network.
- I8 replaced: gameplay executes client-side; only server-verified runs enter shared
  data; overload delays verification and never changes a model.
- I12 replaced: the deferred list is section 10 of this file.

## 8. Process v2

Kept: hashes of scientific identities (source lock, graphs, model profiles, calibration
protocols); protocols frozen by commit before the run; claims only from the ladder;
agents never mark work accepted.

Changed:
1. One external review per stage (a stage may contain several phases).
2. Dry run before freezing any protocol.
3. Wording and metadata fixes do not require a new attempt; they become review
   conditions checked next time. A new attempt is needed only if results or executed
   code change.
4. Decision records only for scientific changes (model, graph, protocol, calibration,
   claims). Mechanical fixes need only a commit message.
5. No new review tooling unless existing tooling blocks work; tools/ should not grow
   faster than src/.
6. Short ledger: current state, identities, gate decisions. v1 history lives in
   docs/history/.
7. The implementing agent may be Codex or Claude Code; the same rules apply.

## 9. Phases and gates

| Phase | Content | Gate |
|---|---|---|
| 0 Truth | Close M09; bot-player comparison with a fixed-latency controller; circuit vs full graph DNp01 at accepted parameters; process v2 migration | G0: findings recorded |
| 1 Data and circuit | Walking DN and side mapping; circuit rule T1/T2 with cut-mass audit; null graph generator with diagnostics; small fixture in repo | G1: IDs reviewed, audits and null diagnostics accepted |
| 2 Model and calibration | Noise, encoder/decoder v2, dry run then frozen protocol; equal calibration of real and null flies; H1 and H2 with all controls | G-WIRING: outcome recorded, claims chosen |
| 3 Browser and game | TypeScript kernel with 3-browser parity; four modes; brain-cam and clips; bot-player checks | G3: bit-exact parity, bot metrics in range |
| 4 Launch | Static hosting, upload API, verifier, README, video, model card, limitations; soft launch then public | G4: claim audit, clean install, limits under load |
| 5 Science after launch | One full-graph optimization pass; H3; H4 analysis by the fixed plan; write-up with negative results; independent reproduction | none |

## 10. Deferred

GPU runtime, plasticity, learned decoders, accounts, global leaderboards with
identities, chat, persistent shared simulation state, realistic biomechanics,
multiple production models, arbitrary public experiment submission.
