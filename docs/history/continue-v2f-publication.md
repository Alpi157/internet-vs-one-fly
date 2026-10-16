# V2F publication repair a02

Status: COMPLETE_FOR_REVIEW, subject to the final-SHA acceptance receipt included
in the review ZIP. The external a01 verdict accepts the science and requests
publication repair; decisions/D-V2F-REVIEW-01.json and ledger.yaml preserve it
verbatim. External acceptance of the publication repair remains pending.

Repair base: 04f1f302c844653421a116c583a99da841a876ae.
Blocked-gate checkpoint: ffcf0b115a6379e9a28338f725638f06758fd3a4.
v2.1 freeze: 083bd2be2944c5dd773f670efc7b69445e207058.
Both freeze manifests and all raw records remain unchanged. No experiment,
resume, added null, git push, tag or deployment is authorized or performed.
The requested regression/browser/bot acceptance workloads validate existing code.

## Public raw evidence

The owner authorized separate evidence storage after the size gate failed.
Archive: ~/flybench-archive/flybench-raw-records-v2e-v2f.tar.gz.
Size: 2,201,225,419 bytes; SHA-256:
7b808bdef63450414e10afa8dde96233a2c4b218240bfdc3688e67c69a4e19f2.
Its 12,633 members are the audited inputs to both frozen verifiers, plus the
requested progress logs. The archive bytes match the earlier measured stream.
Manifest: archive/raw-records-manifest.json. Dataset guide: archive/DATA-README.md.

Zenodo DRAFT: https://zenodo.org/deposit/23409752.
Reserved DOI: 10.5281/zenodo.23409752, resolving only after owner publication.
The archive, SHA256SUMS and DATA-README.md uploaded through streaming bucket PUT;
all three local/remote MD5 comparisons pass. Full metadata and receipts are in
evidence/V2F/zenodo-draft.json and zenodo-upload-checks.json. The owner alone may
publish. Never invoke a publication endpoint or include credentials in artifacts.

## Restore and verify

```sh
uv run python tools/restore_evidence.py --archive /path/to/flybench-raw-records-v2e-v2f.tar.gz
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
uv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify
uv run python experiments/v2f_publish.py --check
```

Use the locked environment and profiles/requirements-v2.1.txt. After owner
publication, restore_evidence.py --download fetches the pinned public file URL.
Restoration checks the full archive hash before extraction, refuses differing
existing files, rejects unsafe paths and verifies every member. The older frozen
verifier also compares recorded host metadata; exact equality requires its
recorded platform and hardware-thread-count envelope. No metadata is substituted.

## Publication repair

README leads with the combined result: earlier controls have a large rate gap,
while N-STRENGTH removes most of it. All public numbers are generated from
committed tables. T2 explicitly says measured wiring is faster than N-STRENGTH.
The input-strength Gini explanation stays EXPLORATORY and is not presented as a
preregistered mechanism test. Input-strength preservation is approximate through
sign/contact bins, not exact numerical sums. Every family conclusion includes
measured values versus null medians.

The coupling heading is neutral. Its generated strength caveat is directly below
the caption and burned into exported clips. Existing hero media was cropped from
the same recorded pixels to remove the partners-only heading and stale footer;
no new scientific recording or neural interpolation was generated.

## Acceptance and review

The a01 registry contained 15 commands; the prior statement of 16 was incorrect.
The a02 registry has 16 commands after adding the dedicated offline evidence
restore check. Acceptance must run on the final committed SHA itself. The report
is evidence/V2F/acceptance/command-results.json; its submitted_code_sha must equal
git rev-parse HEAD. No tracked file may change after that run. If a fix requires
a new commit, rerun the full acceptance against that new SHA before bundling.

```sh
uv run python -m pytest -q
uv run python tools/run_acceptance.py V2F --out evidence/V2F/acceptance
uv run python tools/review_bundle.py --milestone V2F --attempt 2 --base 6f5276d021086580b04a81bad3a16b1a840beac7 --out reviews/V2F-a02.zip
```

The bundle retains the original accepted base for a complete stage diff and the
review narrative identifies the repair base separately. Include the archive
manifest, draft metadata, upload checks, restore/verify logs, DATA-README.md,
updated screenshots/clip and token-scan result. The large archive stays outside
the repository and ZIP. Final ZIP path: reviews/V2F-a02.zip. Final submitted SHA
is in the review-manifest.json and REVIEW.md to avoid a self-referential commit.

The token remains in ~/.config/flybench/zenodo_token and is read only at runtime.
Before delivery scan the working tree, new logs and final ZIP for its exact bytes,
reporting only PASS or FAIL. Do not publish the Zenodo draft, push Git or deploy.
