from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_round_two_candidates_preserve_exact_annotation_matches() -> None:
    profile = json.loads((ROOT / "profiles/walking-dn-candidates-v2.json").read_text(encoding="utf-8"))
    exact = {
        name: {int(value["body_id"]) for value in matches if value["match_kind"] == "exact type"}
        for name, matches in profile["names"].items()
    }
    assert exact == {
        "DNp09": {10783, 11177},
        "DNg13": {11074, 512006},
        "DNb02": {10805, 12767, 13922, 529488},
        "oDN1": set(),
    }
    assert "higher brain interneurons" in profile["exclusions"]["BPN"]


def test_ports_v2_final_receipt_and_provisional_separation() -> None:
    profile = json.loads((ROOT / "profiles/ports-v2.json").read_text(encoding="utf-8"))
    final_ids = {
        int(entry["body_id"])
        for entries in profile["groups"].values()
        for entry in entries
        if entry["status"] == "FINAL"
    }
    provisional_ids = {
        int(entry["body_id"])
        for entries in profile["groups"].values()
        for entry in entries
        if entry["status"] == "PROVISIONAL"
    }
    assert final_ids == {10001, 10010, 10763, 11332, 11288, 12348, 10360, 523769}
    assert provisional_ids == {10783, 11177, 11074, 512006, 10805, 12767, 13922, 529488}
    assert final_ids.isdisjoint(provisional_ids)
    assert "model assumption" in profile["turn_direction_assumption"]


def test_v2_circuit_report_is_provisional_and_audited() -> None:
    report = json.loads((ROOT / "evidence/V2B/p1/circuits.json").read_text(encoding="utf-8"))
    assert [value["candidate"] for value in report["circuits"]] == ["T1a", "T1b", "T2"]
    assert all(value["seed_status"] == "PROVISIONAL_SEEDS" for value in report["circuits"])
    assert all(value["audit_status"] == "PASS" for value in report["circuits"])
