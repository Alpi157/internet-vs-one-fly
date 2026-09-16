#!/usr/bin/env python3
"""Bounded loopback launch/health/frontend/WebSocket smoke for M08."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from websockets.asyncio.client import connect


ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def get_json(url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


async def receive_until(socket_client: Any, kind: str, *, timeout: float = 3.0) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for WebSocket message {kind!r}")
        message = json.loads(await asyncio.wait_for(socket_client.recv(), timeout=remaining))
        if message.get("type") == kind:
            return message


async def websocket_smoke(port: int) -> dict[str, Any]:
    uri = f"ws://127.0.0.1:{port}/ws/demo"
    async with connect(uri, open_timeout=5, close_timeout=2, max_size=128 * 1024) as client:
        initial = json.loads(await asyncio.wait_for(client.recv(), timeout=3))
        await client.send(json.dumps({"type": "aim", "sequence": 1, "x": 10.0, "y": 10.0}))
        aim_ack = await receive_until(client, "ack")
        await client.send(json.dumps({"type": "attack", "sequence": 2, "x": 10.0, "y": 10.0}))
        attack_ack = await receive_until(client, "ack")
        await client.send(json.dumps({"type": "aim", "sequence": 3, "x": -10.0, "y": -10.0}))
        later_aim_ack = await receive_until(client, "ack")
        locked_state: dict[str, Any] | None = None
        impact_state: dict[str, Any] | None = None
        deadline = asyncio.get_running_loop().time() + 4.0
        while asyncio.get_running_loop().time() < deadline:
            message = json.loads(
                await asyncio.wait_for(
                    client.recv(), timeout=deadline - asyncio.get_running_loop().time()
                )
            )
            if message.get("type") != "state":
                continue
            if message.get("strike") is not None:
                locked_state = message
            if message.get("last_impact") is not None:
                impact_state = message
                break
        if impact_state is None or locked_state is None:
            raise RuntimeError("WebSocket sequence did not reach locked strike and impact")
        return {
            "initial_server_tick": initial["server_tick"],
            "initial_backend": initial["backend"],
            "initial_model": initial["model"],
            "aim_ack": aim_ack,
            "attack_ack": attack_ack,
            "later_aim_ack": later_aim_ack,
            "locked_target_after_later_aim": locked_state["strike"]["locked_target"],
            "locked_strike_radius": locked_state["strike"]["strike_radius"],
            "impact": impact_state["last_impact"],
            "authoritative_final_tick": impact_state["server_tick"],
        }


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
    command = [
        str(flybench),
        "demo",
        "--profile",
        str(profile),
        "--port",
        str(port),
        "--no-browser",
    ]
    env = dict(os.environ)
    env.update({"NUMBA_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
    started_at = utc_now()
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "FAIL",
        "scope": "bounded M08 loopback smoke; not a public-host test",
        "started_at_utc": started_at,
        "command": command,
        "bind_host": "127.0.0.1",
        "port": port,
        "hard_timeouts": {
            "startup_seconds": args.startup_timeout,
            "http_request_seconds": 2.0,
            "websocket_sequence_seconds": 4.0,
            "shutdown_seconds": 10.0,
        },
    }
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + args.startup_timeout
        health: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"demo exited during startup with status {process.returncode}")
            try:
                health = get_json(f"http://127.0.0.1:{port}/healthz")
                break
            except (URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
                time.sleep(0.05)
        if health is None:
            raise TimeoutError("health endpoint did not become ready before the hard timeout")
        with urlopen(f"http://127.0.0.1:{port}/", timeout=2.0) as response:
            frontend = response.read()
        profile_value = get_json(f"http://127.0.0.1:{port}/api/demo/profile")
        websocket = asyncio.run(websocket_smoke(port))
        checks = {
            "health_ok": health.get("status") == "ok",
            "built_frontend_reachable": b"Internet vs One Fly" in frontend,
            "live_count_313": profile_value.get("graph", {}).get("N") == 313,
            "live_E_20607": profile_value.get("graph", {}).get("E") == 20607,
            "live_contacts_79112": profile_value.get("graph", {}).get("represented_contacts") == 79112,
            "kernel_backend": profile_value.get("backend", {}).get("name") == "kernel",
            "game_spec_v02": profile_value.get("game", {}).get("profile_id")
            == "flybench.catch-game.v0.2",
            "profile_strike_radius_point_55": profile_value.get("game", {}).get(
                "strike_radius"
            )
            == 0.55,
            "locked_target_immutable": websocket["locked_target_after_later_aim"]
            == {"x": 10.0, "y": 10.0},
            "locked_strike_radius_point_55": websocket["locked_strike_radius"]
            == 0.55,
            "impact_strike_radius_point_55": websocket["impact"].get(
                "strike_radius"
            )
            == 0.55,
            "impact_reached": websocket["impact"].get("outcome") in {"caught", "missed"},
        }
        if not all(checks.values()):
            raise RuntimeError(f"smoke assertion failed: {checks}")
        report.update(
            {
                "status": "PASS",
                "health": health,
                "frontend_bytes": len(frontend),
                "profile": profile_value,
                "websocket": websocket,
                "checks": checks,
            }
        )
    except Exception as exc:  # bounded evidence must retain exact failure class/message
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
                terminated_cleanly = process.returncode is not None
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
