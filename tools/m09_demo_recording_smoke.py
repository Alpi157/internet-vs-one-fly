#!/usr/bin/env python3
"""Bounded real-server smoke for the M09 demo recording integration."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

from websockets.asyncio.client import connect

from flybench.recording import (
    FLYRUN_FORMAT_ID,
    STATE_DIGEST_INTERVALS,
    canonical_applied_input_sha256,
    load_flyrun,
)


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    (10.0, 10.0),
    (-10.0, 10.0),
    (10.0, -10.0),
    (-10.0, -10.0),
    (10.0, 10.0),
    (-10.0, 10.0),
)
PROCESS_STATUS = {
    "decision": "D-M08-HUMAN-GATE-DEFER-01",
    "m09_execution": "AT_RISK",
    "m08_g_game": "PENDING_UNMEASURED",
    "m09_is_m08_usability_evidence": False,
    "public_release_blocked": True,
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def get_json(url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


async def receive_matching(
    client: Any,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout: float,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for the bounded demo state")
        message = json.loads(await asyncio.wait_for(client.recv(), timeout=remaining))
        if predicate(message):
            return message


async def disconnect_before_completion(port: int) -> None:
    uri = f"ws://127.0.0.1:{port}/ws/demo"
    async with connect(uri, open_timeout=5, close_timeout=2, max_size=128 * 1024) as client:
        initial = json.loads(await asyncio.wait_for(client.recv(), timeout=3))
        if initial.get("type") != "state" or initial.get("result") is not None:
            raise RuntimeError("demo did not begin with an incomplete authoritative round")


async def complete_demo_round(port: int) -> dict[str, Any]:
    uri = f"ws://127.0.0.1:{port}/ws/demo"
    sequence = 0
    attacks: list[dict[str, Any]] = []
    async with connect(uri, open_timeout=5, close_timeout=2, max_size=128 * 1024) as client:
        initial = json.loads(await asyncio.wait_for(client.recv(), timeout=3))
        if initial.get("type") != "state" or initial.get("phase") != "ready":
            raise RuntimeError("demo did not begin in ready state")
        for index, (x, y) in enumerate(TARGETS, start=1):
            sequence += 1
            await client.send(
                json.dumps(
                    {"type": "aim", "sequence": sequence, "x": x, "y": y}
                )
            )
            aim_ack = await receive_matching(
                client,
                lambda item: item.get("type") == "ack"
                and item.get("kind") == "aim"
                and item.get("sequence") == sequence,
                timeout=3,
            )
            sequence += 1
            await client.send(
                json.dumps(
                    {"type": "attack", "sequence": sequence, "x": x, "y": y}
                )
            )
            attack_ack = await receive_matching(
                client,
                lambda item: item.get("type") == "ack"
                and item.get("kind") == "attack"
                and item.get("sequence") == sequence,
                timeout=3,
            )
            attack_id = attack_ack["attack_id"]
            impact_state = await receive_matching(
                client,
                lambda item: item.get("type") == "state"
                and (item.get("last_impact") or {}).get("attack_id") == attack_id,
                timeout=3,
            )
            attacks.append(
                {
                    "index": index,
                    "aim_ack": aim_ack,
                    "attack_ack": attack_ack,
                    "impact": impact_state["last_impact"],
                }
            )
            if impact_state.get("result") is not None:
                return {
                    "initial": initial,
                    "attacks": attacks,
                    "final": impact_state,
                }
            await receive_matching(
                client,
                lambda item: item.get("type") == "state"
                and item.get("phase") == "ready"
                and item.get("server_tick", -1) > impact_state["server_tick"],
                timeout=3,
            )
    raise RuntimeError("six explicit missed attacks did not complete the demo round")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--startup-timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    output = args.out if args.out.is_absolute() else ROOT / args.out
    profile = args.profile if args.profile.is_absolute() else ROOT / args.profile
    port = args.port or free_loopback_port()
    flybench = Path(sys.executable).parent / "flybench"
    started = time.monotonic()
    report: dict[str, Any] = {
        "schema_version": 2,
        "status": "FAIL",
        "scope": "bounded automated loopback demo recording smoke; not the required real operator demo round and not M08 usability evidence",
        "started_at_utc": utc_now(),
        "bind_host": "127.0.0.1",
        "port": port,
        "process_status": PROCESS_STATUS,
    }
    process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="flybench-m09-demo-smoke-") as directory:
            record_directory = Path(directory) / "runs"
            command = [
                str(flybench),
                "demo",
                "--profile",
                str(profile),
                "--port",
                str(port),
                "--no-browser",
                "--record-dir",
                str(record_directory),
            ]
            report["command"] = command
            environment = dict(os.environ)
            environment.update({"NUMBA_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + args.startup_timeout
            health = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"demo exited during startup with status {process.returncode}"
                    )
                try:
                    health = get_json(f"http://127.0.0.1:{port}/healthz")
                    break
                except (URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
                    time.sleep(0.05)
            if health is None:
                raise TimeoutError("demo health endpoint exceeded the startup timeout")
            profile_value = get_json(f"http://127.0.0.1:{port}/api/demo/profile")
            asyncio.run(disconnect_before_completion(port))
            incomplete_deadline = time.monotonic() + 5
            while time.monotonic() < incomplete_deadline and not list(
                record_directory.glob("*.incomplete.json")
            ):
                time.sleep(0.02)
            incomplete_paths = sorted(record_directory.glob("*.incomplete.json"))
            if len(incomplete_paths) != 1:
                raise RuntimeError("early disconnect did not create exactly one receipt")
            incomplete = json.loads(incomplete_paths[0].read_text(encoding="utf-8"))
            execution = asyncio.run(complete_demo_round(port))
            artifact_deadline = time.monotonic() + 5
            while time.monotonic() < artifact_deadline and not list(
                record_directory.glob("*.flyrun")
            ):
                time.sleep(0.02)
            flyruns = sorted(record_directory.glob("*.flyrun"))
            if len(flyruns) != 1:
                raise RuntimeError("completed round did not create exactly one flyrun")
            loaded = load_flyrun(flyruns[0])
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            state_events = [
                event for event in loaded.events if event["type"] == "state_digest"
            ]
            expected_ticks = [0]
            expected_ticks.extend(
                range(
                    STATE_DIGEST_INTERVALS,
                    loaded.summary["final_control_tick"],
                    STATE_DIGEST_INTERVALS,
                )
            )
            if loaded.summary["final_control_tick"] not in expected_ticks:
                expected_ticks.append(loaded.summary["final_control_tick"])
            checks = {
                "health_ok": health.get("status") == "ok",
                "game_spec_v03": profile_value.get("game", {}).get("profile_id")
                == "flybench.catch-game.v0.3",
                "early_disconnect_receipt_honest": incomplete.get("status")
                == "INCOMPLETE"
                and incomplete.get("completed_flyrun") is False,
                "exactly_one_completed_round_archive": len(flyruns) == 1,
                "format_v02": loaded.manifest.get("format_id") == FLYRUN_FORMAT_ID
                and loaded.manifest.get("schema_version") == 2,
                "actual_demo_path": loaded.manifest.get("run", {}).get(
                    "execution_kind"
                )
                == "game-session",
                "candidate_code_identity": loaded.manifest.get("provenance", {}).get(
                    "code_git_sha"
                )
                == head,
                "completed_round": loaded.summary.get("authoritative_result")
                == "fly-survived"
                and loaded.summary.get("attacks_committed") == 6,
                "applied_hash_valid": loaded.summary.get("applied_input_sha256")
                == canonical_applied_input_sha256(loaded.events),
                "state_digest_cadence": [
                    event["control_tick"] for event in state_events
                ]
                == expected_ticks,
                "final_state_digest_present": loaded.summary.get(
                    "final_whole_state_sha256"
                )
                == state_events[-1].get("whole_state_sha256"),
                "reexecution_not_verified": loaded.summary.get("reexecution", {}).get(
                    "verified"
                )
                is False,
            }
            if not all(checks.values()):
                raise RuntimeError(f"demo recording smoke assertion failed: {checks}")
            archive_bytes = flyruns[0].read_bytes()
            report.update(
                {
                    "status": "PASS",
                    "health": health,
                    "profile": profile_value,
                    "execution": execution,
                    "incomplete_receipt": incomplete,
                    "automated_fixture": {
                        "ephemeral_path": str(flyruns[0]),
                        "bytes": len(archive_bytes),
                        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
                        "content_digest": loaded.content_digest,
                        "applied_input_sha256": loaded.summary[
                            "applied_input_sha256"
                        ],
                        "final_whole_state_sha256": loaded.summary[
                            "final_whole_state_sha256"
                        ],
                    },
                    "checks": checks,
                }
            )
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
                terminated_cleanly = True
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
                terminated_cleanly = False
            report["server_exit_status"] = process.returncode
            report["server_terminated_cleanly"] = terminated_cleanly
            report["server_stdout"] = stdout
            report["server_stderr"] = stderr
        report["duration_seconds"] = round(time.monotonic() - started, 6)
        report["ended_at_utc"] = utc_now()
        write_json(output, report)
    print(json.dumps({"status": report["status"], "out": str(output)}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
