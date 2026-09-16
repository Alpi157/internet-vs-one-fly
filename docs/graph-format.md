# FlyBench M03 compiled graph format

This document describes graph compiler version `flybench.graph-compiler.v1`. It is
an immutable data representation, not a simulator or a biological pathway map.

## Accepted population and indices

The accepted-node profile is `profiles/accepted-neurons.json`. A row in the pinned
curated annotation table is accepted when its `superclass` value is non-null. The
exact positive integer `bodyId` remains the biological identity. Duplicate accepted
annotation IDs are deduplicated and counted. Connection endpoints never create
nodes.

Accepted IDs are sorted numerically without conversion through floating point and
written as `uint64`. Dense runtime index `i` identifies `ids[i]`. The target-index
representation is rejected unless `N <= 2^31 - 1`.

## Source-major arrays

All graph arrays are NumPy `.npy` files and can be opened with
`numpy.load(path, mmap_mode="r", allow_pickle=False)`. Numeric payloads use canonical
little-endian byte order.

| File | Canonical dtype | Shape | Meaning |
| --- | --- | --- | --- |
| `ids.npy` | `uint64` | `(N,)` | Ordered original biological body IDs |
| `offsets.npy` | `int64` | `(N + 1,)` | Source-row boundaries |
| `targets.npy` | `int32` | `(source_accepted_E,)` | Dense postsynaptic indices |
| `counts.npy` | `uint64` | `(source_accepted_E,)` | Aggregated source contact counts |
| `weights.npy` | `float32` | `(source_accepted_E,)` | Provisional executable weights |

The orientation is `A[source, target]`: row `i` is presynaptic. Reference incoming
propagation is `A.T @ spike_vector`. Targets are strictly increasing within each
source row. Repeated source rows for one biological source-target pair are summed
deterministically before output.

Raw contacts are never renamed or stored only as executable weights. The initial
weight is `float32(count * presynaptic_effective_sign * 1.0)`. Unit gain, transmitter
signs, and normalization `none` are MODEL ASSUMPTIONS in
`profiles/compile-transform-v1.json`, not MaleCNS measurements. Zero-sign source
edges remain in `targets.npy` and `counts.npy`; audits separately report source E,
nonzero executable E, and disabled contact mass.

Node-aligned auxiliary arrays preserve whether a transmitter record exists,
predicted and consensus label codes, ground-truth label codes, prediction count,
the original float64 prediction confidence, and the separately derived int8
effective sign. The generated manifest carries the exact codebook.

## Semantic graph digest

The SHA-256 semantic digest starts with the domain bytes
`FlyBench semantic sparse graph v1\0`. It then hashes canonical JSON describing:

- semantic array order `ids`, `offsets`, `targets`, `counts`, `weights`;
- canonical dtypes and little-endian byte order;
- source-major orientation;
- the accepted-node selection-rule semantic SHA-256; and
- the compile-transform profile SHA-256.

For each semantic array it hashes canonical JSON containing the array name, NumPy
dtype string, and shape, followed by the contiguous canonical array payload bytes.
It does not hash `.npy` headers, paths, timestamps, temporary filenames, memory
addresses, or build-resource measurements. Ordinary SHA-256 hashes of every full
`.npy` file are recorded separately in `manifest.json` and the audit.

The accepted-node selection also has an ordinary profile-file SHA-256. Its semantic
identity canonicalizes the JSON selection rule while excluding only the embedded
source-lock byte digest. This permits equivalent source tables in another row order
to compile to the same graph identity while preserving their distinct byte
provenance in the manifest.

## Source counting boundary

The pinned MaleCNS connection table has exactly `body_pre`, `body_post`, and
`weight`; it has no ROI partition column. Each retained row is therefore treated as
one released segment-pair contact total. Any repeated exact pair is summed once.
Unexpected additional connection columns stop compilation because their partition
semantics would be ambiguous.

Rows with either endpoint outside the accepted annotation population are excluded
from adjacency. Row counts and contact mass are reported for source-only,
target-only, and both-endpoint exclusions, so no discarded mass is silent.
