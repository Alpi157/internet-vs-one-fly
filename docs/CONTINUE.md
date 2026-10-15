# V2F continuation

Status: IN_PROGRESS. Do not mark accepted. No final review ZIP has been produced.
The detached scientific run is active. Preserve every raw result and every
profiles/freeze-v2.1.json member exactly. A scientific defect must stop the run.

Base: 6f5276d021086580b04a81bad3a16b1a840beac7.
Implementation: 363c662.
v2.1 freeze: 083bd2be2944c5dd773f670efc7b69445e207058.
Tag prereg-v2.1 and branch prereg/v2.1 pushed, verified 2026-10-15 06:15:07 UTC.
Receipt: docs/preregistration-receipt-v2.1.json. Main was not pushed.

Run PID is in evidence/V2F/run.pid; log is evidence/V2F/run.log.
Task progress: evidence/V2F/results/progress.jsonl.
A separate watcher (PID in evidence/V2F/analysis-after-run.pid) waits for clean
COMPLETE.json, then runs the frozen analysis and --verify. Its log is
evidence/V2F/analysis-after-run.log. Do not launch duplicate analysis while it is
active. Script copy: evidence/V2F/analysis-after-run.sh. It neither publishes
results nor commits changes and refuses a STOP or missing completion record.
The frozen plan uses one full-graph worker, four T2 workers, eight T1a workers,
and two mechanism workers. Pre-null projection was 33,651 seconds (9.35 hours).
Use the declared counts unchanged. Do not start a duplicate runner.

```sh
tail -5 evidence/V2F/run.log
cat evidence/V2F/results/STOP.json
cat evidence/V2F/results/COMPLETE.json
```

Missing STOP/COMPLETE is normal while running. If the process ended without a
scientific defect, inspect logs and resource evidence before using the frozen
runner's --resume. A STOP.json is a defect stop, not permission to patch or resume.

Completed: S0 external V2E verdict verbatim; S1 null implementation and pilots;
S2 gates; S3 isolated freeze and public push; S4 launched. H0-STR completed.
P1 licensing and citation; P2 lazy live T1a coupling lab; P3 recorded GIF, still
and clip; P4 cache optimization; P5 finding panel; P6 manual-only build; P7 initial
three-browser game/coupling matrix and production base path checks pass.
The final live-game pass in evidence/V2F/game-final is PASS: mobile WebKit 58.37 fps during active simulation; coupling about 62.22 fps. Desktop live WebKit 52.91 fps is disclosed. Ten bot strategies pass; evidence/V2F/bots-v6.json.

Product implementation and media are committed in 96a5337. The fresh-clone smoke
passed in evidence/V2F/fresh-clone-r2. Its earlier dependency-target failure is
retained in evidence/V2F/fresh-clone and fixed in the acceptance registration.
Do not rerun v2e_game_export.py, which rewrites older game exports/evidence.
The product-only exporter is experiments/v2f_game_export.py.

Remaining: await S4; run frozen analysis and verify;
publish docs/findings-v2f.md and docs/results-v2f.json; update public text with
all robustness outcomes; finalize README; move this continuation to docs/history
when no run remains; run acceptance, commit submission and build one review ZIP.
Do not run uv sync while the science process is active: it can remove the separate
SciPy dependency used by the frozen exploratory tasks. Acceptance should install
profiles/requirements-v2.1.txt after its required locked base sync.

```sh
uv run python experiments/v2f_analyze.py --out evidence/V2F/results
uv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify
uv run python tools/run_acceptance.py V2F --out evidence/V2F/acceptance
uv run python tools/review_bundle.py --milestone V2F --attempt 1 --base 6f5276d021086580b04a81bad3a16b1a840beac7 --out reviews/V2F-a01.zip
```

No deployment or main push is authorized. Every EXPLORATORY output stays labeled.
No em dashes in new prose. Final handoff must include the review ZIP, submitted
SHA, freeze/push receipt, tables, exploratory highlights, resource use, WebKit
before/after, coupling screenshot list, and open questions.

Checkpoint at 2026-10-15T06:52:30.149799+00:00: H0-FULL 25/199 tasks; H0-STR complete.
Both manifests verified unchanged. No STOP.json. Full worker observed peak RSS
5276708 KiB. Treat this as progress only; final resource totals are pending.
