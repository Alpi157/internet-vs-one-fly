from __future__ import annotations

import json
from pathlib import Path

import pytest

from flybench.detmath import atan_approx, rotate_unit_step, u32


ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "tests/vectors/detmath-v2.json"


def test_rng_vectors() -> None:
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))["rng"]
    assert len(vectors) >= 1000
    for vector in vectors:
        inputs = [int(float.fromhex(vector[name])) for name in ("seed_hex", "stream_hex", "tick_hex", "index_hex")]
        result = u32(*inputs)
        assert result == vector["output_u32"]
        assert float(result).hex() == vector["output_hex"]


def test_atan_vectors() -> None:
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))["approximations"]["atan"]
    assert len(vectors) >= 1000
    for vector in vectors:
        assert atan_approx(float.fromhex(vector["input_hex"])).hex() == vector["output_hex"]


def test_rotation_vectors() -> None:
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))["approximations"]["rotate_unit_step"]
    assert len(vectors) >= 1000
    for vector in vectors:
        output = rotate_unit_step(
            float.fromhex(vector["heading_x_hex"]),
            float.fromhex(vector["heading_y_hex"]),
            float.fromhex(vector["delta_hex"]),
        )
        assert output[0].hex() == vector["output_x_hex"]
        assert output[1].hex() == vector["output_y_hex"]


@pytest.mark.parametrize("value", [-8.01, 8.01])
def test_atan_domain_is_enforced(value: float) -> None:
    with pytest.raises(ValueError, match="within"):
        atan_approx(value)


@pytest.mark.parametrize("counter",[-1,2**32,True,1.5])
def test_rng_counter_bounds(counter):
    with pytest.raises(ValueError):u32(1,2,counter,3)


def test_atan_error_envelope():
    import math
    import numpy as np
    for x in np.concatenate((np.linspace(-8,8,20001),np.geomspace(1e-4,8,20001))):
        error=abs(atan_approx(float(x))-math.atan(float(x)))
        assert error<=1e-6
        if x>=1e-4:assert error/math.atan(float(x))<=1e-5


def test_legacy_rng_reproduction_vectors():
    from flybench.detmath import u32_v1
    for v in json.loads(VECTORS.read_text())['rng_v1_reproduction_only']:
        assert u32_v1(v['seed'],v['stream'],v['tick'],v['index'])==v['output_u32']
