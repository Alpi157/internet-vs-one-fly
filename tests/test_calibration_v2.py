from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_calibration_protocol_remains_draft_and_complete() -> None:
    profile = json.loads((ROOT / "profiles/calibration-v2-draft.json").read_text(encoding="utf-8"))
    assert profile["status"] == "DRAFT_REVIEW_REQUIRED"
    assert profile["protocol_frozen"] is False
    assert set(profile["nulls"]["families"]) == {"N-FULL", "N-CONTEXT"}
    assert profile["nulls"]["count_per_family"] == 20
    assert {"H1", "H2"} == set(profile["hypotheses"])
    assert {
        "output clamp",
        "LC4 lesion",
        "LPLC2 lesion",
        "turning-neuron lesion",
        "noise straight to decoder",
        "C-SIMPLE single threshold on angular size fitted with the same calibration budget",
        "C-TIMER fixed 30 ms latency from V2A",
    } <= set(profile["controls"])
