# V2E continuation

Status: RUN_IN_PROGRESS. V2E is not accepted. The science files are frozen at
`1a853f40007dcf10fb113c29a8400a7f99a3addb`, published as prereg-v2 and prereg/v2.
Main has not been pushed. T1b is the H1/H2 primary, selected at s=0.01,
kappa=0.05, nu0=5 Hz, gain=8. The pre-null projection retains both circuits.

The detached process ID is in evidence/V2E/run.pid. Do not launch a second copy
while it is alive. Monitor without interpreting partial hypothesis results:

```sh
ps -p "$(cat evidence/V2E/run.pid)" -o pid,ppid,stat,etime
tail -5 evidence/V2E/run.log
```

If the process has exited and results/STOP.json is absent, resume exactly:

```sh
setsid nohup .venv/bin/python experiments/v2e_run.py --workers 12 --resume --out evidence/V2E/results > evidence/V2E/run-resumed.log 2>&1 < /dev/null &
echo $! > evidence/V2E/run.pid
```

If STOP.json exists, preserve every output and report the defect. Do not edit any
file in profiles/freeze-v2.json. Do not delete STOP.json to bypass the stop.

After evidence/V2E/results/COMPLETE.json appears, run:

```sh
uv run python experiments/v2e_analyze.py --out evidence/V2E/results
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
```

Remaining science: finish H0, null calibration, eligible H1/H2, every-null
fixed-parameter comparisons and real-graph descriptive controls, then frozen S6
analysis, PNG figures and FINDINGS.md. Update README pending results from those
verified tables only. Add the analysis verification command to V2E acceptance
only once S6 has run. Keep existing submitted review evidence and archive intact.
The submitted ZIP is a snapshot of an active run, not a completed experiment.

All game functionality, bot checks and review packaging are independent of the
remaining scientific computation. Public Pages hosting remains unenabled.
