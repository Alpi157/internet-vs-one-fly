# MaleCNS source data and attribution

FlyBench M02 consumes three files from **MaleCNS v1.0**, published by the Janelia FlyEM project through the [official MaleCNS download page](https://male-cns.janelia.org/download/):

- `body-annotations-male-cns-v1.0-minconf-0.5.feather`
- `body-neurotransmitters-male-cns-v1.0.feather`
- `connectome-weights-male-cns-v1.0-minconf-0.5.feather`

The official site states that the Male CNS dataset is licensed under CC-BY. Users of the source data and derived artifacts must preserve the applicable attribution.

MaleCNS source bytes remain data published by their original authors; FlyBench does not claim ownership of them. FlyBench-derived locks, reports, compiled artifacts, and software are distinct from the underlying biological source dataset. The exact locally observed identities and official URLs are recorded in `profiles/source-lock.json`. Locally computed SHA-256 values are byte-identity records, not upstream-published checksums or claims of biological correctness.

The anatomy assets additionally use these sources from the same official page,
under CC-BY-4.0:

- SWC skeletons: `gs://flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc/<bodyId>.swc`, Male CNS EM coordinates in 8 nm units.
- Brain neuropil segmentation: `gs://flyem-male-cns/rois/fullbrain-roi-v4`.
- VNC neuropil segmentation: `gs://flyem-male-cns/rois/malecns-vnc-neuropil-roi-v0`.
- Each volume's own `segment_properties/info` supplies the ROI names verbatim.
- The already pinned body annotations supply soma side, somaLocation and instance names.

Acquisition uses anonymous HTTPS at `storage.googleapis.com`, at most eight
requests, retries and resumed partial files. Raw responses remain under ignored
`data/anatomy/raw/`. The separate [anatomy lock](../profiles/anatomy-lock-v1.json)
pins every input without changing the frozen source lock. The [anatomy guide](anatomy-v2g.md)
documents transforms and transport. Missing skeletons and unlabeled anatomy are
never replaced by an illustration.
