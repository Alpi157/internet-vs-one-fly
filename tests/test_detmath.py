from __future__ import annotations

import json
from pathlib import Path

import pytest

from flybench.detmath import atan_approx, rotate_unit_step, u32


ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "tests/vectors/detmath-v1.json"


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
