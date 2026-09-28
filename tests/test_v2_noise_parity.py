from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from flybench.game import build_live_session, load_live_profile
from flybench.kernel import KernelGraph
from flybench.kernel_v2 import KernelStateV2, _counter_u32
from flybench.reference import ReferenceGraph
from flybench.reference_v2 import NoiseSpec, ReferenceStateV2
from flybench.detmath import u32


ROOT = Path(__file__).resolve().parents[1]


def _digest(state: object) -> str:
    digest = hashlib.sha256()
    digest.update(int(state.tick).to_bytes(8, "little"))
    for value in (
        state.voltage,
        state.synaptic_current,
        state.refractory_until_tick,
        state.pending_spikes,
        state.pending_inputs,
    ):
        digest.update(np.ascontiguousarray(value).tobytes())
    return digest.hexdigest()


@pytest.mark.parametrize("index", range(25))
def test_numba_rng_matches_python(index: int) -> None:
    expected = u32(2026092802, 17, index * 37, index * 11)
    assert int(_counter_u32(2026092802, 17, index * 37, index * 11)) == expected


def _parity(directory: Path, ticks: int) -> None:
    arrays = {
        name: np.load(directory / f"{name}.npy", allow_pickle=False)
        for name in ("offsets", "targets", "weights")
    }
    spec = build_live_session(load_live_profile(ROOT / "profiles/live.json")).runner.model_spec
    reference_graph = ReferenceGraph(**arrays)
    kernel_graph = KernelGraph(**arrays)
    noise = NoiseSpec(2026092802, 17, 42949673, 0.05, np.ones(reference_graph.n, dtype=np.bool_))
    reference = ReferenceStateV2(spec, reference_graph, noise)
    kernel = KernelStateV2(spec, kernel_graph, noise)
    drive = np.zeros(reference_graph.n, dtype=np.float64)
    for _ in range(ticks):
        reference_result = reference.step(drive)
        kernel_result = kernel.step(drive)
        assert np.array_equal(reference_result.spikes, kernel_result.spikes)
        assert _digest(reference) == _digest(kernel)


def test_fixture_noise_parity_for_one_second() -> None:
    _parity(ROOT / "fixtures/escape-circuit-v1", 2000)


def test_t1a_noise_parity_for_one_second_when_available() -> None:
    directory = ROOT / "data/compiled/v2/t1a"
    if not directory.is_dir():
        pytest.skip("T1a is an ignored local scientific-data bundle")
    _parity(directory, 2000)
