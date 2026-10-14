# Catch the Fly v2 local slice

V2D is submitted for review. The game uses a provisional T1a point because S4 G4
stopped the science track. There is no frozen protocol or H1/H2 result.

Run locally from the repository root:

```sh
uv sync --extra dev --locked
uv run python experiments/v2d_game_export.py
npm --prefix apps/play ci
npm --prefix apps/play run dev
```

The full T1a export needs the pinned local data. For a small offline first success,
use `uv run python experiments/v2d_game_export.py --fixture` instead. That mode
executes the licensed 313-neuron fixture and displays its actual counts. It is
not the T1a game performance or bot evidence. Restore T1a with the first command.
No server, account, telemetry or public hosting is used.

The worker and Node bots import the same Game and packages/kernel-ts RunnerV2.
Every 10 ms interval uses the previously held movement command. Collision at the
interval end precedes takeoff from a newly decoded onset at that boundary.
Takeoff accepts only heading, environment seed, onset tick and game jitter. No
hand or threat geometry enters the decoder or takeoff function. Flight reflects
at arena boundaries and lands after its declared duration. Neural state continues
through all six strikes. Replay pauses logical time and displays recorded frames
and recorded spikes only; it performs no neural simulation or interpolation.
A round ends after six strikes or 30 seconds of logical simulation.

The round JSON stores applied coordinates, hold time and integer application tick,
independent neural/environment seeds, profile hashes, graph identity, final tick,
state digest and explicit trace gaps. This supported re-execution envelope is
float64 on the tested Node/Chromium/Firefox/WebKit versions, fixed graph edge order,
0.5 ms neural ticks, 20 ticks per control interval, matching profiles and code.
MediaRecorder exports WebM or MP4 where the browser supports it. PNG result cards
and JSON round logs are also local downloads.

Soma positions come directly from pinned MaleCNS v1.0 annotations. The display uses
an x/z projection normalized with a single scale. This is a front display convention;
anatomical camera orientation is unverified. The official download page explicitly
specifies 8 nm units for synapse coordinates and SWC skeletons, but not somaLocation.
Only relative soma positions are used. Missing coordinates occupy a side band by
group and are not assigned anatomical locations.
Source and CC-BY attribution: https://male-cns.janelia.org/download/

Game version history:

| Version | Flick radius | Other game parameters | Bot target |
|---|---:|---|---|
| v2.1 | 0.45 | Initial declared game profile | Missed: flick lead 1.5 caught 5/60, 8.3% |
| v2.2 | 0.55 | Identical to v2.1 | All ten strategy point estimates 10% to 43.3% |

Version 1 is preserved in profiles/game-v2-history/v1.json. No neural, encoder or
decoder parameter changed for difficulty. Bots observe position and heading, wait
180 ms, then apply independent uniform aim error of +/-0.8 units per axis. Lead
strategies use 0, 0.5 or 1.5 units, for every strike type; a tenth uses random strike
types. Each strategy runs ten independent seeded rounds, six strikes each. Reported
95% intervals bootstrap whole rounds to retain within-round dependence. Point
estimates are a development target, not evidence of human usability. The same seeds
were reused across game versions and no holdout difficulty claim is made.
