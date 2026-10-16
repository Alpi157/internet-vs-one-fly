# V2H — Under the microscope

V2H implements the approved game/replay UI from `docs/design/v4/DESIGN.md`.
The anatomy, neural model, frozen science and results remain unchanged. The
existing coupling and lesion labs remain reachable from Wiring lab; their
redesign belongs to V2I. See `docs/ui-v2h.md` for display rules and deviations.

The only mechanics change is the equal-area circular chamber in game v2.7.
The existing exporter has a product-only path:

```sh
uv run --offline python experiments/v2e_game_export.py --game-only
npm --prefix apps/play run build
npm --prefix apps/play test
node apps/play/test/e2e.mjs
uv run --offline python tools/run_acceptance.py V2H --out evidence/V2H/acceptance
uv run --offline python tools/review_bundle.py --milestone V2H --attempt 1 --base ae3e417ed6dd0882550b95b3ff29b56c751d60fa --out reviews/V2H-a01.zip
```

There are 16 registered acceptance commands, including full Python regression,
Node/browser parity, an offline fresh clone, production UI/network/accessibility
and performance tests, paired bots and frozen analysis verification. The
acceptance receipt and review manifest identify the final SHA, avoiding a
self-referential commit. Bots are descriptive, with no catch-rate target.
Evidence and review ZIPs are ignored generated outputs.

Do not mark the stage accepted. No push, tag or deployment is authorized.
