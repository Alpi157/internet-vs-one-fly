#!/usr/bin/env python3
"""Resolve and capture M08 live/GameSpec identity evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil

from flybench.game import build_live_session, load_live_profile, sha256_file


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    profile_path = args.profile if args.profile.is_absolute() else ROOT / args.profile
    output = args.out if args.out.is_absolute() else ROOT / args.out
    output.mkdir(parents=True, exist_ok=True)
    resolved = load_live_profile(profile_path)
    state = build_live_session(resolved).snapshot()
    game_path = resolved.root / resolved.value["game"]["path"]
    shutil.copyfile(profile_path, output / "live-profile.json")
    shutil.copyfile(game_path, output / "game-spec.json")
    checks = {
        "profile_resolved": True,
        "live_profile_copy_exact": sha256_file(output / "live-profile.json") == resolved.sha256,
        "game_spec_copy_exact": sha256_file(output / "game-spec.json")
        == resolved.game_spec_sha256,
        "actual_graph_counts": state["model"]
        == {"N": 313, "E": 20607, "represented_contacts": 79112},
        "actual_backend_kernel": state["backend"] == "kernel",
        "game_spec_v02": resolved.game_spec.profile_id
        == "flybench.catch-game.v0.2",
        "strike_radius_point_55": resolved.game_spec.strike_radius == 0.55,
        "historical_game_spec_preserved": sha256_file(
            resolved.root / "profiles/game-v0.1.json"
        )
        == "521dc8f33457155b0f5c5438f11da2c6b489d9a5667b7d63421ed863fbb62cd7",
    }
    report = {
        "schema_version": 1,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "live_profile_path": str(profile_path.relative_to(ROOT)),
        "live_profile_sha256": resolved.sha256,
        "game_spec_path": resolved.value["game"]["path"],
        "game_spec_sha256": resolved.game_spec_sha256,
        "graph": resolved.value["graph"],
        "backend": resolved.value["backend"],
        "identities": {
            "m07_live_candidate_sha256": resolved.value["m07_live_candidate"]["sha256"],
            "runtime_model_spec_sha256": resolved.value["model"]["runtime_model_spec_sha256"],
            "controller_sha256": resolved.value["controller"]["sha256"],
            "encoder_sha256": resolved.value["encoder"]["sha256"],
            "decoder_sha256": resolved.value["decoder"]["sha256"],
            "environment_sha256": resolved.value["environment"]["sha256"],
        },
        "checks": checks,
    }
    write_json(output / "identity-check.json", report)
    print(json.dumps({"status": report["status"], "out": str(output)}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
