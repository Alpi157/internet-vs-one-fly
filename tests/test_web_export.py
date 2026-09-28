from __future__ import annotations

import json
from pathlib import Path
import struct

from flybench.web_export import MAGIC, export_web_graph


ROOT = Path(__file__).resolve().parents[1]


def test_fixture_web_export_is_little_endian_and_digest_labeled(tmp_path: Path) -> None:
    output = tmp_path / "fixture.webbin"
    report = export_web_graph(ROOT / "fixtures/escape-circuit-v1", output)
    raw = output.read_bytes()
    assert raw[:8] == MAGIC
    header_length = struct.unpack("<I", raw[8:12])[0]
    header = json.loads(raw[12 : 12 + header_length])
    assert header["byte_order"] == "little-endian"
    assert header["N"] == 313 and header["E"] == 20607
    assert header["semantic_graph_digest"] == "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5"
    assert header["sections"]["counts"]["dtype"] == "<u8"
    assert header["sections"]["weights"]["dtype"] == "<f8"
    assert report["bytes"] == output.stat().st_size
