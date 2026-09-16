#!/usr/bin/env python3
"""Build reproducible M04 candidate-pathway and cut-context evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flybench.pathway import MappingError, build_m04_mapping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path("profiles/source-lock.json"))
    parser.add_argument("--full-graph", type=Path, default=Path("data/compiled/full"))
    parser.add_argument("--circuit-graph", type=Path)
    parser.add_argument("--circuit-profile", type=Path)
    parser.add_argument(
        "--model-profile", type=Path, default=Path("profiles/model-v0.1.json")
    )
    parser.add_argument(
        "--encoder-profile", type=Path, default=Path("profiles/encoder-v0.1.json")
    )
    parser.add_argument(
        "--decoder-profile", type=Path, default=Path("profiles/decoder-v0.1.json")
    )
    parser.add_argument(
        "--calibration-plan", type=Path, default=Path("profiles/calibration-plan.json")
    )
    parser.add_argument("--out", type=Path, default=Path("evidence/M04"))
    parser.add_argument("--require-manual-review", action="store_true")
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    try:
        result = build_m04_mapping(
            repository_root=root,
            lock_path=args.lock,
            full_graph_dir=args.full_graph,
            circuit_graph_dir=args.circuit_graph,
            output_dir=args.out,
            circuit_profile_path=args.circuit_profile,
            model_profile_path=args.model_profile,
            encoder_profile_path=args.encoder_profile,
            decoder_profile_path=args.decoder_profile,
            calibration_plan_path=args.calibration_plan,
            require_manual_review=args.require_manual_review,
        )
    except (MappingError, OSError, KeyError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 3 if str(exc) == "HUMAN M04 MAPPING REVIEW REQUIRED" else 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
