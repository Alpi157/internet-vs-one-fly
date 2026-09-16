#!/usr/bin/env python3
"""Create unfilled operator templates and instructions for the mandatory M08 human gate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from flybench.game import load_live_profile


ROOT = Path(__file__).resolve().parents[1]


def write_new(path: Path, value: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing human-review artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def json_text(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="evidence/M08", type=Path)
    parser.add_argument("--candidate-sha")
    args = parser.parse_args(argv)
    output = args.out if args.out.is_absolute() else ROOT / args.out
    candidate = args.candidate_sha or subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise ValueError("candidate SHA must be a full 40-character Git SHA")
    resolved = load_live_profile(ROOT / "profiles/live.json")
    common = {
        "candidate_product_sha": candidate,
        "live_profile_sha256": resolved.sha256,
        "game_spec_sha256": resolved.game_spec_sha256,
    }
    playtests = {
        "schema_version": 1,
        "status": "OPERATOR_INPUT_REQUIRED",
        **common,
        "instructions": "Do not coach the first attempt. Do not record names or contact details. Replace every placeholder from direct observation.",
        "playtests": [
            {
                "participant_id": player,
                "unfamiliar_to_project": None,
                "browser_device_category": "OPERATOR_INPUT_REQUIRED",
                "discovered_attack_without_coaching": None,
                "completed_round": None,
                "observed_confusion": "OPERATOR_INPUT_REQUIRED",
                "approximate_attack_behavior_outcomes": "OPERATOR_INPUT_REQUIRED",
                "aiming_timing_assessment": "OPERATOR_INPUT_REQUIRED",
                "blocking_ui_problem": "OPERATOR_INPUT_REQUIRED"
            }
            for player in ("P1", "P2", "P3")
        ],
    }
    host = {
        "schema_version": 1,
        "status": "OPERATOR_INPUT_REQUIRED",
        **common,
        "coarse_hardware_facts": "OPERATOR_INPUT_REQUIRED",
        "browser_device_category": "OPERATOR_INPUT_REQUIRED",
        "restricted_access_method": "OPERATOR_INPUT_REQUIRED (for example SSH tunnel/private network; do not include addresses or secrets)",
        "connection_result": "OPERATOR_INPUT_REQUIRED",
        "rendering_input_behavior": "OPERATOR_INPUT_REQUIRED",
        "visible_lag_or_failure": "OPERATOR_INPUT_REQUIRED",
        "unfinished_service_publicly_exposed": None,
    }
    receipt = f"""M08 MANUAL GAME REVIEW — OPERATOR INPUT REQUIRED

Candidate product SHA: {candidate}
Live profile SHA-256: {resolved.sha256}
GameSpec SHA-256: {resolved.game_spec_sha256}

Replace this template with the operator's own concise receipt after the local browser check,
three unfamiliar playtests, restricted external-host smoke, screenshot, and gameplay clip.
Record observed failures honestly. Do not write ACCEPTED; external review remains pending.
"""
    instructions = f"""# M08 human review package

This package is bound to candidate product SHA `{candidate}`.

- Live profile SHA-256: `{resolved.sha256}`
- GameSpec SHA-256: `{resolved.game_spec_sha256}`

Do not modify product, GameSpec, frontend, game/server, or scientific files during this evaluation. Any such change invalidates affected human evidence.

## A. Local operator browser check

Run from the repository root:

```bash
npm --prefix apps/web ci
npm --prefix apps/web run build
uv run flybench demo --profile profiles/live.json
```

Open the printed loopback URL. Verify the game renders; mouse works; touch works where available; the locked strike is obvious; impact is understandable; takeoff never appears before the authoritative command can apply; cooldown and result are clear; stopping the server produces a visible connection failure; the UI says the live circuit has 313 neurons; and it does not imply whole-fly locomotion or biological validation.

## B. Three unfamiliar playtests

Use at least three unfamiliar people and do not coach their first attempt. Record no names or contact details—use `P1`, `P2`, `P3`. Complete every field in `../manual/playtests.json`, including attack discovery, round completion, confusion, approximate behavior/outcome, whether aiming/timing felt meaningful, and blocking UI problems. This is usability evidence, not a retention study.

## C. Restricted external-host smoke

Run this exact candidate on a representative remote CPU host. Keep the service bound to `127.0.0.1` and reach it with an SSH tunnel or private restricted mechanism. Complete `../manual/host-smoke.json` with coarse hardware, browser/device, access method, connection, rendering/input, lag/failure, and confirmation that the unfinished service was not exposed as an open public endpoint. Include no credentials, tokens, private keys, unnecessary addresses, or SSH secrets.

## D. Actual media

Put at least one clear gameplay screenshot and one short clip in `../media/`. The clip must show actual aim → locked strike → approach → impact/result from this candidate, not a mockup.

## E. Operator receipt and reviewer handoff

Replace `../manual/manual-game-review.txt` with your own receipt, keeping the candidate/live/GameSpec identities. Change JSON status values to `COMPLETE_OPERATOR_SUPPLIED` only after completing the work. Do not write an M08 decision yourself yet. Bring these artifacts to the external GPT reviewer for suggested final receipt text. M08 remains `IN_PROGRESS`; do not begin M09.
"""
    write_new(output / "manual" / "playtests.json", json_text(playtests))
    write_new(output / "manual" / "host-smoke.json", json_text(host))
    write_new(output / "manual" / "manual-game-review.txt", receipt)
    write_new(output / "human-review-package" / "README.md", instructions)
    write_new(
        output / "media" / "README.txt",
        "OPERATOR INPUT REQUIRED: add one actual gameplay screenshot and one short actual gameplay clip here.\n",
    )
    write_new(output / "candidate.json", json_text({"schema_version": 1, **common}))
    print(json.dumps({"status": "TEMPLATES_CREATED_NOT_FILLED", **common}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
