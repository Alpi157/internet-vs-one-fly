"""Thin loopback FastAPI transport for the M08 local demo."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from flybench.game import (
    ACCEPTED_CONTACTS,
    ACCEPTED_E,
    ACCEPTED_N,
    DemoProtocol,
    GameInputError,
    GameSession,
    ResolvedLiveProfile,
    build_live_session,
    load_live_profile,
)


def public_profile(resolved: ResolvedLiveProfile) -> dict[str, object]:
    value = resolved.value
    return {
        "profile_id": value["profile_id"],
        "live_profile_sha256": resolved.sha256,
        "game_spec_sha256": resolved.game_spec_sha256,
        "graph": {
            "N": ACCEPTED_N,
            "E": ACCEPTED_E,
            "represented_contacts": ACCEPTED_CONTACTS,
            "semantic_digest": value["graph"]["semantic_digest"],
        },
        "backend": value["backend"],
        "identities": {
            "m07_live_candidate_sha256": value["m07_live_candidate"]["sha256"],
            "runtime_model_spec_sha256": value["model"]["runtime_model_spec_sha256"],
            "controller_sha256": value["controller"]["sha256"],
            "encoder_sha256": value["encoder"]["sha256"],
            "decoder_sha256": value["decoder"]["sha256"],
            "environment_sha256": value["environment"]["sha256"],
        },
        "clock": value["clock"],
        "game": {
            "profile_id": resolved.game_spec.profile_id,
            "strike_radius": resolved.game_spec.strike_radius,
            "attack_wind_up_ms": resolved.game_spec.attack_wind_up_ms,
            "impact_offset_ms": resolved.game_spec.impact_offset_ms,
        },
        "claim_scope": value["claim_scope"],
        "model_notice": value["model_notice"],
        "limitations": value["limitations"],
    }


def create_app(
    profile_path: Path,
    frontend_directory: Path,
    *,
    tick_seconds: float = 0.01,
    session_factory: Callable[[], GameSession] | None = None,
) -> FastAPI:
    """Create the same-origin M08 app after checking all local-live identities."""

    resolved = load_live_profile(profile_path)
    frontend_directory = frontend_directory.resolve()
    if not (frontend_directory / "index.html").is_file():
        raise FileNotFoundError(
            f"built frontend is unavailable at {frontend_directory}; "
            "run: npm --prefix apps/web run build"
        )
    if not tick_seconds > 0.0:
        raise ValueError("tick_seconds must be positive")
    make_session = session_factory or (lambda: build_live_session(resolved))
    app = FastAPI(title="FlyBench M08 local demo", docs_url=None, redoc_url=None)
    app.state.resolved_live_profile = resolved
    app.state.active_websocket = False
    app.state.active_lock = asyncio.Lock()

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "scope": "M08 loopback local demo",
                "profile_id": resolved.value["profile_id"],
            }
        )

    @app.get("/api/demo/profile")
    async def demo_profile() -> JSONResponse:
        return JSONResponse(public_profile(resolved))

    @app.websocket("/ws/demo")
    async def demo_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        async with app.state.active_lock:
            if app.state.active_websocket:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "local_session_busy",
                        "message": "The local demo already has an active game.",
                    }
                )
                await websocket.close(code=1013)
                return
            app.state.active_websocket = True
        try:
            protocol = DemoProtocol(make_session())
            send_lock = asyncio.Lock()

            async def send(payload: dict[str, object]) -> None:
                async with send_lock:
                    await websocket.send_json(payload)

            await send(protocol.session.snapshot())

            async def receive_messages() -> None:
                while True:
                    try:
                        payload = await websocket.receive_json()
                        response = protocol.handle(payload)
                    except GameInputError as exc:
                        response = {
                            "type": "error",
                            "code": exc.code,
                            "message": str(exc),
                            "server_tick": protocol.session.control_tick,
                        }
                    except ValueError:
                        response = {
                            "type": "error",
                            "code": "malformed",
                            "message": "message must contain valid JSON",
                            "server_tick": protocol.session.control_tick,
                        }
                    await send(response)
                    if response.get("type") == "ack":
                        await send(protocol.session.snapshot())

            async def advance_clock() -> None:
                loop = asyncio.get_running_loop()
                deadline = loop.time() + tick_seconds
                while True:
                    await asyncio.sleep(max(deadline - loop.time(), 0.0))
                    deadline += tick_seconds
                    if protocol.session.result is not None:
                        continue
                    before_impact = protocol.session.last_impact
                    state = protocol.advance()
                    decisive = (
                        state["last_impact"] is not None
                        and state["last_impact"] is not before_impact
                    )
                    if (
                        decisive
                        or state["result"] is not None
                        or protocol.session.control_tick
                        % protocol.session.spec.presentation_intervals
                        == 0
                    ):
                        await send(state)

            receiver = asyncio.create_task(receive_messages())
            ticker = asyncio.create_task(advance_clock())
            try:
                await asyncio.gather(receiver, ticker)
            finally:
                receiver.cancel()
                ticker.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await receiver
                with suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await ticker
        except WebSocketDisconnect:
            pass
        finally:
            async with app.state.active_lock:
                app.state.active_websocket = False

    app.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")
    return app
