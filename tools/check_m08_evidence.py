#!/usr/bin/env python3
"""Validate M08 automated evidence and, in final mode, operator human receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from flybench.game import load_live_profile, sha256_file


ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDERS = ("OPERATOR_INPUT_REQUIRED", "TODO", "REPLACE_ME", "<fill")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"missing or invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def require_text(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"missing or invalid text {path}: {exc}") from exc
    if not value.strip():
        raise ValueError(f"evidence file is empty: {path}")
    return value


def ensure_nonplaceholder(value: object, label: str) -> None:
    if value is None or value == "" or any(marker in str(value) for marker in PLACEHOLDERS):
        raise ValueError(f"operator receipt field is incomplete: {label}")


def validate_automated(evidence: Path) -> dict[str, Any]:
    resolved = load_live_profile(ROOT / "profiles/live.json")
    if sha256_file(evidence / "live-profile.json") != resolved.sha256:
        raise ValueError("captured live-profile.json does not match profiles/live.json")
    if sha256_file(evidence / "game-spec.json") != resolved.game_spec_sha256:
        raise ValueError("captured game-spec.json does not match the committed GameSpec")
    for name in (
        "local-game-tests.json",
        "local-server-smoke.json",
        "headless-server-parity.json",
        "identity-check.json",
        "scientific-regression.json",
    ):
        if load_json(evidence / name).get("status") != "PASS":
            raise ValueError(f"M08 automated evidence does not pass: {name}")
    for name in ("frontend-tests.txt", "frontend-build.txt"):
        text = require_text(evidence / name)
        if "status: PASS" not in text or "exit_status: 0" not in text:
            raise ValueError(f"M08 command evidence does not pass: {name}")
    smoke = load_json(evidence / "local-server-smoke.json")
    if (
        smoke.get("bind_host") != "127.0.0.1"
        or smoke.get("server_terminated_cleanly") is not True
        or not all(smoke.get("checks", {}).values())
    ):
        raise ValueError("bounded local-server smoke is incomplete")
    identity = load_json(evidence / "identity-check.json")
    if (
        identity.get("live_profile_sha256") != resolved.sha256
        or identity.get("game_spec_sha256") != resolved.game_spec_sha256
        or not all(identity.get("checks", {}).values())
    ):
        raise ValueError("M08 identity evidence differs from the resolved live profile")
    return {
        "live_profile_sha256": resolved.sha256,
        "game_spec_sha256": resolved.game_spec_sha256,
    }


def validate_final(evidence: Path, identities: dict[str, Any]) -> None:
    manual = evidence / "manual"
    playtests_path = manual / "playtests.json"
    host_path = manual / "host-smoke.json"
    review_path = manual / "manual-game-review.txt"
    playtests = load_json(playtests_path)
    host = load_json(host_path)
    review = require_text(review_path)
    candidate = playtests.get("candidate_product_sha")
    if not isinstance(candidate, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise ValueError("playtests candidate_product_sha must be a full Git SHA")
    for name, receipt in (("playtests", playtests), ("host-smoke", host)):
        if receipt.get("status") != "COMPLETE_OPERATOR_SUPPLIED":
            raise ValueError(f"{name} is still a template or is not operator supplied")
        if receipt.get("candidate_product_sha") != candidate:
            raise ValueError(f"{name} is bound to a different candidate product SHA")
        if receipt.get("live_profile_sha256") != identities["live_profile_sha256"]:
            raise ValueError(f"{name} live-profile identity mismatch")
        if receipt.get("game_spec_sha256") != identities["game_spec_sha256"]:
            raise ValueError(f"{name} GameSpec identity mismatch")
        if any(marker in json.dumps(receipt, sort_keys=True) for marker in PLACEHOLDERS):
            raise ValueError(f"{name} still contains placeholder text")
    entries = playtests.get("playtests")
    if not isinstance(entries, list) or len(entries) < 3:
        raise ValueError("at least three unfamiliar-player entries are required")
    ids: set[str] = set()
    required_fields = (
        "unfamiliar_to_project",
        "browser_device_category",
        "discovered_attack_without_coaching",
        "completed_round",
        "observed_confusion",
        "approximate_attack_behavior_outcomes",
        "aiming_timing_assessment",
        "blocking_ui_problem",
    )
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError("each unfamiliar-player entry must be an object")
        player_id = entry.get("participant_id")
        if not isinstance(player_id, str) or not re.fullmatch(r"P[0-9]+", player_id):
            raise ValueError("playtests must use anonymous participant IDs such as P1")
        if player_id in ids:
            raise ValueError("playtest participant IDs must be distinct")
        ids.add(player_id)
        if any(key in entry for key in ("name", "email", "phone", "contact")):
            raise ValueError("playtest entries must not contain tester identity/contact fields")
        if entry.get("unfamiliar_to_project") is not True:
            raise ValueError("each required playtest must be from an unfamiliar person")
        for field in required_fields:
            ensure_nonplaceholder(entry.get(field), f"playtests[{index}].{field}")
    if host.get("unfinished_service_publicly_exposed") is not False:
        raise ValueError("host smoke must confirm no open public exposure")
    for field in (
        "coarse_hardware_facts",
        "browser_device_category",
        "restricted_access_method",
        "connection_result",
        "rendering_input_behavior",
        "visible_lag_or_failure",
    ):
        ensure_nonplaceholder(host.get(field), f"host-smoke.{field}")
    forbidden_host_keys = {"credentials", "token", "password", "private_key", "ip_address"}
    if forbidden_host_keys.intersection(host):
        raise ValueError("host smoke includes a forbidden secret or unnecessary address field")
    if len(review.strip()) < 80 or any(marker in review for marker in PLACEHOLDERS):
        raise ValueError("manual game-review receipt is absent or still a template")
    if candidate not in review:
        raise ValueError("manual game-review receipt is not bound to the candidate SHA")
    media = evidence / "media"
    screenshots = [
        path for path in media.glob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and path.stat().st_size
    ]
    clips = [
        path for path in media.glob("*") if path.suffix.lower() in {".mp4", ".webm", ".mov"} and path.stat().st_size
    ]
    if not screenshots or not clips:
        raise ValueError("at least one gameplay screenshot and one short gameplay clip are required")
    decision = load_json(evidence / "decision.json")
    if (
        decision.get("gate") != "G-GAME"
        or decision.get("proposed_outcome") != "PASS_CANDIDATE"
        or decision.get("external_milestone_acceptance") != "PENDING"
        or decision.get("candidate_product_sha") != candidate
        or decision.get("live_profile_sha256") != identities["live_profile_sha256"]
        or decision.get("game_spec_sha256") != identities["game_spec_sha256"]
    ):
        raise ValueError("M08 G-GAME candidate decision is incomplete or inconsistent")
    expected_hashes = {
        "manual/playtests.json": sha256_file(playtests_path),
        "manual/host-smoke.json": sha256_file(host_path),
        "manual/manual-game-review.txt": sha256_file(review_path),
    }
    if decision.get("operator_receipt_sha256") != expected_hashes:
        raise ValueError("decision receipt hashes do not match operator-supplied bytes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--phase", choices=("automated", "final"), default="final")
    args = parser.parse_args(argv)
    evidence = args.out if args.out.is_absolute() else ROOT / args.out
    try:
        identities = validate_automated(evidence)
        if args.phase == "final":
            validate_final(evidence, identities)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"M08 evidence check failed: {type(exc).__name__}: {exc}")
        return 1
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    print(
        json.dumps(
            {
                "status": "PASS",
                "phase": args.phase,
                "candidate_or_submission_head": head,
                **identities,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
