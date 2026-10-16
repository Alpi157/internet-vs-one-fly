# V2F publication repair a02

Status: BLOCKED_RAW_ARCHIVE_SIZE. The external a01 verdict accepts the science
and requires publication repairs. It is recorded verbatim in
decisions/D-V2F-REVIEW-01.json and ledger.yaml. Stage acceptance is not claimed.

Repair base: 04f1f302c844653421a116c583a99da841a876ae.
Both frozen manifests remain unchanged; 122 distinct frozen files verified.
No simulation, resume, raw-record edit, push, tag or deployment occurred.

The operator's explicit size gate says to stop if the required evidence archive
exceeds 50 MB. It fails:

- Required files: 12,633, from actual reads of both frozen --verify
  paths, plus the two explicitly requested progress logs.
- Stored input file bytes: 2,229,611,176.
- Deterministic tar.gz bytes: 2,201,225,419.
- Limit: 50,000,000 bytes.
- Compressed stream SHA-256:
  7b808bdef63450414e10afa8dde96233a2c4b218240bfdc3688e67c69a4e19f2.

The size/hash were measured by streaming sorted USTAR entries through gzip,
without writing or committing an archive. Entries use fixed mtime 0, uid/gid 0,
mode 0644 and empty owner names; gzip level 9 uses an empty filename and mtime 0.
The exact archive candidate file set equals the audited verification read set.

V2E inputs dominate: fixed-parameter records alone are 1,339,891,438 stored bytes;
calibration 350,042,061; H2 341,240,288; H1 168,697,380. These are read by the
unchanged verifier and cannot be replaced with summaries under this instruction.
No raw files were rewritten or stripped.

Both existing frozen verification commands passed during the read audit:

```sh
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
uv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify
```

Exact per-file read list: evidence/V2F/a02/verification-read-set.json.
Per-file SHA-256 and size report: evidence/V2F/a02/archive-size-report.json.
Logs: evidence/V2F/a02/inventory-and-verify.log and archive-size.log.

Publication repair stopped at this gate. No restore tool, new acceptance check,
README/lab/media repair, final-SHA acceptance, or V2F-a02 review ZIP was produced.
The existing a01 acceptance registry has 15 commands, not 16; its previous count
claim was incorrect. The only persisted changes are the external verdict and this
blocked handoff. The next action requires an operator decision about the size cap
or a separate public storage mechanism. Do not rerun or extend the science.
