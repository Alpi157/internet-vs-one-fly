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
    session = build_live_session(resolved)
    state = session.snapshot()
    effective_environment = session.runner.environment.config
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
        "game_spec_v03": resolved.game_spec.profile_id
        == "flybench.catch-game.v0.3",
        "strike_radius_point_55": resolved.game_spec.strike_radius == 0.55,
        "effective_ambient_speed_point_03": effective_environment.ambient_speed_per_interval
        == 0.03,
        "effective_heading_jitter_minus_point_09_to_point_09": (
            effective_environment.heading_jitter_min_rad,
            effective_environment.heading_jitter_max_rad,
        )
        == (-0.09, 0.09),
        "game_mechanics_classified_non_physiological": resolved.value.get(
            "game_mechanics", {}
        ).get("biological_estimate")
        is False,
        "historical_game_spec_preserved": sha256_file(
            resolved.root / "profiles/game-v0.1.json"
        )
        == "521dc8f33457155b0f5c5438f11da2c6b489d9a5667b7d63421ed863fbb62cd7",
        "historical_v02_game_spec_preserved": sha256_file(
            resolved.root / "profiles/game-v0.2.json"
        )
        == "4d28775a7c69f063d7aab0cee44d6f8b1c4eaa72687644f96a59c65ae7220a25",
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
        "effective_game_environment": {
            "ambient_speed_per_control_interval": effective_environment.ambient_speed_per_interval,
            "heading_jitter_uniform_rad": [
                effective_environment.heading_jitter_min_rad,
                effective_environment.heading_jitter_max_rad,
            ],
            "rng_algorithm": session.runner.environment.rng.bit_generator.__class__.__name__,
            "environment_seed": session.runner.environment.seed,
        },
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
