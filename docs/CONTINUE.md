# V2F review handoff

Status: COMPLETE_FOR_REVIEW. External acceptance pending. No run is active.
Do not rerun, resume or extend the scientific experiment. Do not edit any member
of either freeze manifest or any raw task record. No main/tag push or deployment
was performed in this finishing session.

Base: 6f5276d021086580b04a81bad3a16b1a840beac7 (v2e-accepted).
v2.1 freeze: 083bd2be2944c5dd773f670efc7b69445e207058.
Tag prereg-v2.1 and branch prereg/v2.1 were published before execution; receipt:
docs/preregistration-receipt-v2.1.json. Final submitted SHA is recorded in the
review ZIP's REVIEW.md and review-manifest.json, avoiding a self-referential hash.
Archive: reviews/V2F-a01.zip.

The queued script did run: evidence/V2F/analysis-after-run.log records successful
analysis and verification on 2026-10-15 at 13:23 UTC. It wrote outputs under
results/ but did not publish them into committed docs. This session independently
reran both exact frozen commands successfully. No frozen code was patched.

Integrity: both manifests PASS; 3,655 expected and found records. No STOP.json.
H0-STR 500; H0-FULL 199; H0-T2 598; E1 2,058; E2a, E3-low and E3-high 100 each.
All raw records remain unchanged locally and have SHA-256/size inventories.

Outcome: N-STRENGTH did not replicate on T1a, T2 or the full graph. T2 N-STRENGTH
has a significant rate difference in the opposite direction. T2 N-FULL and
N-SIGN, and full-graph N-SIGN, support the registered model stability direction.
Every family is reported in docs/findings-v2f.md, docs/results-v2f.json and public
copy. EXPLORATORY E1 retains two unconverged spectra as missing. E2b is
preregistered SKIPPED, not a deviation, for unestablished confidence semantics.

Exact frozen verification commands, both passed:

```sh
uv run python experiments/v2f_analyze.py --out evidence/V2F/results
uv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify
```

Public-copy generation/check, without simulation:

```sh
uv run python experiments/v2f_publish.py
uv run python experiments/v2f_publish.py --check
```

README, public findings and browser results JSON are generated from committed
tables and declared metadata. Tests reject inconsistent public copy. Browser
checks verify displayed results against that JSON.

Full standalone Python suite: 290 passed. Full registered V2F acceptance: PASS,
16 checks including browser matrix, fresh clone, bots and frozen verification.
Acceptance ran against 059428a1a55107aa52f8e806fef05149c58fee46. The final commit
adds review status, publication dates from receipts and acceptance measurements;
publication consistency and freeze checks were rerun after those documentation
updates. Scientific code and game execution code are unchanged from acceptance.

```sh
uv run python tools/run_acceptance.py V2F --out evidence/V2F/acceptance
uv run python tools/review_bundle.py --milestone V2F --attempt 1 --base 6f5276d021086580b04a81bad3a16b1a840beac7 --out reviews/V2F-a01.zip
```

Logs and complete figures are under evidence/V2F/. The archive excludes raw task
records and graph arrays to fit the existing size limit; their hashes and sizes
are retained. Redundant media is indexed in recording-inventory.json. No new
review tooling was introduced. The next action is external review, not deployment.
