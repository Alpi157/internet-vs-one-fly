# V2E verification

Status: COMPLETE_FOR_REVIEW. V2E is not accepted. No scientific process remains
running. The original detached run completed in 35,991.309 seconds, retaining both
circuits. The freeze commit is `1a853f40007dcf10fb113c29a8400a7f99a3addb`, published
as prereg-v2 and prereg/v2. Main was not pushed and hosting remains unenabled.

T1b is the H1/H2 primary at s=0.01, kappa=0.05, nu0=5 Hz, gain=8. H0 retains its
preregistered T1a primary. H1/H2 primary tests are insufficient in every null
family because fewer than 149 nulls calibrated. Do not expand the grid or replace
nulls to change this result.

To verify the retained complete raw records and every frozen file:

```sh
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
uv run python tools/run_acceptance.py V2E --out evidence/V2E/acceptance
```

To regenerate figures and tables from those same raw records:

```sh
uv run python experiments/v2e_analyze.py --out evidence/V2E/results
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
```

For a separate reproduction, use the README's data acquisition, compilation and
runner commands in a separate checkout and output directory. Never edit a file
in profiles/freeze-v2.json. Preserve this submitted evidence and review archive.
Software licensing and any decision to enable public hosting remain with the owner.
