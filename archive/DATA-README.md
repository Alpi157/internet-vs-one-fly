# Catch the Fly raw simulation records

Existing raw simulation records and analysis inputs for the preregistered FlyBench stability study, including V2E and V2F. This is a simplified MaleCNS neural model study; it makes no claims about living flies or biological necessity. The N-STRENGTH stability result did not replicate on T1a, T2 or the full graph; measured T2 wiring had a higher rate than N-STRENGTH. EXPLORATORY analyses remain descriptive.

Reserved dataset DOI: 10.5281/zenodo.23409752. This deposition is a DRAFT. The DOI and public file URL resolve after the owner publishes it. No publication was requested by the agent.

## Identities

- Repository: https://github.com/Alpi157/internet-vs-one-fly
- prereg-v2 freeze: 1a853f40007dcf10fb113c29a8400a7f99a3addb
- prereg-v2 protocol SHA-256: f684489801ec3d5d9af4c9fd845019c79f4daef97cb3533d023b6baf4fce4c8a
- prereg-v2.1 freeze: 083bd2be2944c5dd773f670efc7b69445e207058
- prereg-v2.1 protocol SHA-256: c4ed65c481373d1a3a4a29637878acae93c0a085fdff50914bb9d0f95d6b217d
- Archive SHA-256: 7b808bdef63450414e10afa8dde96233a2c4b218240bfdc3688e67c69a4e19f2

## Restore and verify

Use the repository repair a02 checkout containing tools/restore_evidence.py and archive/raw-records-manifest.json. Install its locked Python environment and the pinned sparse-analysis dependency, then use the downloaded archive offline:

```sh
uv sync --extra dev --locked
uv pip install --no-deps -r profiles/requirements-v2.1.txt
uv run python tools/restore_evidence.py --archive /path/to/flybench-raw-records-v2e-v2f.tar.gz
uv run python experiments/v2e_analyze.py --out evidence/V2E/results --verify
uv run python experiments/v2f_analyze.py --out evidence/V2F/results --verify
```

After publication, tools/restore_evidence.py --download retrieves the same archive from the public Zenodo URL. Restoration verifies the archive hash before extracting, refuses conflicting existing files, and verifies every restored member. No graph arrays or new simulation are needed for these analysis commands. The frozen v2 verifier also compares recorded host metadata (platform and hardware-thread count), so its exact equality check requires the recorded host envelope documented in the repository results. No metadata substitution is performed.

The archive has 12,633 sorted regular-file entries with fixed mtime, uid/gid zero and a gzip header without a timestamp. SHA256SUMS includes the archive and every member. Included inputs are raw task records, topology diagnostics, COMPLETE and progress files, projection, frozen tables and findings. Source graphs, compiled arrays, credentials and caches are excluded.

## Attribution and license

MaleCNS v1.0, Male CNS Connectome project, including FlyEM at HHMI Janelia, Cambridge, MRC LMB and Google Research. Dataset release: https://male-cns.janelia.org/ ; source download and license: https://male-cns.janelia.org/download/ . Study: https://www.cell.com/cell/fulltext/S0092-8674%2826%2900942-6 . Source identities are pinned in the repository source-lock.json.

The records in this deposition are licensed under Creative Commons Attribution 4.0 International (CC-BY-4.0): https://creativecommons.org/licenses/by/4.0/ . Underlying and derived MaleCNS data remains CC-BY; repository code is MIT. Cite both this dataset DOI and the MaleCNS release.
