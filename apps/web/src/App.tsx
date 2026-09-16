import { useCallback, useEffect, useRef, useState } from "react";

import { Arena } from "./Arena";
import type { GameState, Point, ServerMessage } from "./types";

type ConnectionState = "connecting" | "connected" | "disconnected" | "error";

export default function App() {
  const socket = useRef<WebSocket | null>(null);
  const sequence = useRef(0);
  const [game, setGame] = useState<GameState | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [failure, setFailure] = useState<string | null>(null);
  const [connectionKey, setConnectionKey] = useState(0);

  useEffect(() => {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const next = new WebSocket(`${scheme}://${window.location.host}/ws/demo`);
    socket.current = next;
    setConnection("connecting");
    setFailure(null);
    next.onopen = () => setConnection("connected");
    next.onmessage = (event) => {
      let message: ServerMessage;
      try {
        message = JSON.parse(String(event.data)) as ServerMessage;
      } catch {
        setConnection("error");
        setFailure("The server sent an unreadable message.");
        return;
      }
      if (message.type === "state") setGame(message);
      if (message.type === "error") {
        setFailure(message.message);
        if (message.code === "local_session_busy") setConnection("error");
      }
    };
    next.onerror = () => {
      setConnection("error");
      setFailure("Connection failed. The local FlyBench server may have stopped.");
    };
    next.onclose = () => {
      setConnection((current) => (current === "error" ? current : "disconnected"));
      setFailure((current) => current ?? "Disconnected from the authoritative game server.");
    };
    return () => {
      next.close();
      if (socket.current === next) socket.current = null;
    };
  }, [connectionKey]);

  const send = useCallback((type: "aim" | "attack", point: Point) => {
    const current = socket.current;
    if (!current || current.readyState !== WebSocket.OPEN) return;
    sequence.current += 1;
    current.send(
      JSON.stringify({ type, sequence: sequence.current, x: point.x, y: point.y }),
    );
  }, []);

  const canAttack =
    connection === "connected" &&
    game?.result == null &&
    game?.strike == null &&
    (game?.cooldown_remaining_ms ?? 0) === 0;
  const seconds = ((game?.round_remaining_ms ?? 20000) / 1000).toFixed(1);

  return (
    <main>
      <header className="masthead">
        <div>
          <p className="eyebrow">Internet vs One Fly</p>
          <h1>Catch the Fly</h1>
          <p className="instruction">Aim. Commit the strike. Catch the fly before it gets away.</p>
        </div>
        <div className={`connection ${connection}`} role="status">
          <span aria-hidden="true" />
          {connection === "connected" ? "Authoritative server connected" : connection}
        </div>
      </header>

      {failure && (
        <div className="failure" role="alert">
          {failure}
        </div>
      )}

      <section className="game-grid">
        <Arena
          game={game}
          disabled={!canAttack}
          onAim={(point) => send("aim", point)}
          onAttack={(point) => send("attack", point)}
        />
        <aside className="hud" aria-label="Round status">
          <div className="hud-card primary">
            <span>Time</span>
            <strong>{seconds}s</strong>
          </div>
          <div className="hud-card">
            <span>Attempts remaining</span>
            <strong>{game?.attempts_remaining ?? 6}</strong>
          </div>
          <div className="hud-card">
            <span>Strike</span>
            <strong className="phase">{game?.phase ?? "waiting"}</strong>
            {(game?.cooldown_remaining_ms ?? 0) > 0 && (
              <div className="cooldown" aria-label="Cooldown active">
                <i
                  style={{
                    width: `${Math.max(0, Math.min(100, (game!.cooldown_remaining_ms / 600) * 100))}%`,
                  }}
                />
              </div>
            )}
          </div>
          <div className="hud-card">
            <span>Fly motion</span>
            <strong>{game?.fly.takeoff_active ? "Takeoff" : "Walking"}</strong>
          </div>
          {game?.last_impact && (
            <div className={`impact ${game.last_impact.outcome}`}>
              Impact: {game.last_impact.outcome}
            </div>
          )}
        </aside>
      </section>

      {game?.result && (
        <section className={`result ${game.result}`} role="dialog" aria-label="Round result">
          <p>{game.result === "caught" ? "Caught." : "The fly survived."}</p>
          <button onClick={() => { setGame(null); setConnectionKey((value) => value + 1); }}>
            New round
          </button>
        </section>
      )}

      <section className="model-notice" aria-label="Model disclosure">
        <strong>Live model: 313-neuron MaleCNS-derived circuit.</strong>{" "}
        The neural model controls escape onset. Walking and takeoff mechanics are simplified.
        The stimulus is feature-level/scalar, not reconstructed raw vision. Strike direction is
        not reconstructed from fly vision.
      </section>
    </main>
  );
}
