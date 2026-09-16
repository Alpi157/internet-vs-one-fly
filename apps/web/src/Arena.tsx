import { useEffect, useRef, useState, type PointerEvent } from "react";

import type { GameState, Point } from "./types";

const WIDTH = 900;
const HEIGHT = 580;
const ARENA_MIN = -10;
const ARENA_MAX = 10;

function screenPoint(point: Point): Point {
  return {
    x: ((point.x - ARENA_MIN) / (ARENA_MAX - ARENA_MIN)) * WIDTH,
    y: HEIGHT - ((point.y - ARENA_MIN) / (ARENA_MAX - ARENA_MIN)) * HEIGHT,
  };
}

function arenaPoint(event: PointerEvent<HTMLCanvasElement>): Point {
  const rect = event.currentTarget.getBoundingClientRect();
  const width = rect.width || WIDTH;
  const height = rect.height || HEIGHT;
  const px = Math.min(Math.max(event.clientX - rect.left, 0), width);
  const py = Math.min(Math.max(event.clientY - rect.top, 0), height);
  return {
    x: ARENA_MIN + (px / width) * (ARENA_MAX - ARENA_MIN),
    y: ARENA_MAX - (py / height) * (ARENA_MAX - ARENA_MIN),
  };
}

type ArenaProps = {
  game: GameState | null;
  disabled: boolean;
  onAim: (point: Point) => void;
  onAttack: (point: Point) => void;
};

export function Arena({ game, disabled, onAim, onAttack }: ArenaProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [aim, setAim] = useState<Point>({ x: 0, y: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    context.clearRect(0, 0, WIDTH, HEIGHT);
    const background = context.createLinearGradient(0, 0, WIDTH, HEIGHT);
    background.addColorStop(0, "#d9efbd");
    background.addColorStop(1, "#a8ce7f");
    context.fillStyle = background;
    context.fillRect(0, 0, WIDTH, HEIGHT);

    context.strokeStyle = "rgba(24, 53, 28, 0.12)";
    context.lineWidth = 1;
    for (let x = 0; x <= WIDTH; x += 45) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, HEIGHT);
      context.stroke();
    }
    for (let y = 0; y <= HEIGHT; y += 45) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(WIDTH, y);
      context.stroke();
    }

    const aimScreen = screenPoint(aim);
    context.strokeStyle = "rgba(255, 255, 255, 0.86)";
    context.lineWidth = 2;
    context.beginPath();
    context.arc(aimScreen.x, aimScreen.y, 14, 0, Math.PI * 2);
    context.moveTo(aimScreen.x - 22, aimScreen.y);
    context.lineTo(aimScreen.x + 22, aimScreen.y);
    context.moveTo(aimScreen.x, aimScreen.y - 22);
    context.lineTo(aimScreen.x, aimScreen.y + 22);
    context.stroke();

    if (game?.strike) {
      const locked = screenPoint(game.strike.locked_target);
      const collisionRadiusX =
        game.strike.strike_radius * (WIDTH / (ARENA_MAX - ARENA_MIN));
      const collisionRadiusY =
        game.strike.strike_radius * (HEIGHT / (ARENA_MAX - ARENA_MIN));
      const shadowScale = 1.15 + game.strike.progress * 3.2;
      context.fillStyle = `rgba(111, 26, 17, ${0.1 + game.strike.progress * 0.22})`;
      context.beginPath();
      context.ellipse(
        locked.x,
        locked.y,
        collisionRadiusX * shadowScale,
        collisionRadiusY * shadowScale,
        0,
        0,
        Math.PI * 2,
      );
      context.fill();
      context.strokeStyle = "#7f2117";
      context.lineWidth = 4;
      context.beginPath();
      context.ellipse(
        locked.x,
        locked.y,
        collisionRadiusX,
        collisionRadiusY,
        0,
        0,
        Math.PI * 2,
      );
      context.stroke();
      context.fillStyle = "#7f2117";
      context.font = "700 15px system-ui";
      context.textAlign = "center";
      context.fillText("LOCKED", locked.x, locked.y - 58);
    }

    if (game?.last_impact && !game.strike) {
      const impact = screenPoint(game.last_impact.locked_target);
      const impactRadiusX =
        game.last_impact.strike_radius * (WIDTH / (ARENA_MAX - ARENA_MIN));
      const impactRadiusY =
        game.last_impact.strike_radius * (HEIGHT / (ARENA_MAX - ARENA_MIN));
      context.strokeStyle = game.last_impact.outcome === "caught" ? "#184f2c" : "#952c1f";
      context.lineWidth = 5;
      context.beginPath();
      context.ellipse(
        impact.x,
        impact.y,
        impactRadiusX,
        impactRadiusY,
        0,
        0,
        Math.PI * 2,
      );
      context.stroke();
    }

    const fly = screenPoint({ x: game?.fly.x ?? 0, y: game?.fly.y ?? 0 });
    const heading = game?.fly.heading_rad ?? 0;
    context.save();
    context.translate(fly.x, fly.y);
    context.rotate(-heading);
    if (game?.fly.takeoff_active) {
      context.strokeStyle = "rgba(255, 249, 213, 0.85)";
      context.lineWidth = 7;
      context.beginPath();
      context.moveTo(-55, 0);
      context.lineTo(-18, 0);
      context.stroke();
    }
    context.fillStyle = "rgba(230, 244, 222, 0.78)";
    context.beginPath();
    context.ellipse(-2, -12, 20, 9, -0.4, 0, Math.PI * 2);
    context.ellipse(-2, 12, 20, 9, 0.4, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#171b16";
    context.beginPath();
    context.ellipse(0, 0, 21, 10, 0, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#8e2e1e";
    context.beginPath();
    context.arc(17, 0, 7, 0, Math.PI * 2);
    context.fill();
    context.restore();
  }, [aim, game]);

  function move(event: PointerEvent<HTMLCanvasElement>) {
    const point = arenaPoint(event);
    setAim(point);
    onAim(point);
  }

  function attack(event: PointerEvent<HTMLCanvasElement>) {
    if (disabled) return;
    const point = arenaPoint(event);
    setAim(point);
    onAttack(point);
  }

  return (
    <div className="arena-shell">
      <canvas
        aria-label="Catch the Fly arena. Move to aim and press or tap to commit a strike."
        data-testid="arena"
        ref={canvasRef}
        width={WIDTH}
        height={HEIGHT}
        onPointerMove={move}
        onPointerDown={attack}
      />
      <span className="aim-readout" data-testid="aim-readout">
        Aim {aim.x.toFixed(2)}, {aim.y.toFixed(2)}
      </span>
      <span className="locked-readout" data-testid="locked-readout">
        {game?.strike
          ? `Locked strike ${game.strike.locked_target.x.toFixed(2)}, ${game.strike.locked_target.y.toFixed(2)} · radius ${game.strike.strike_radius.toFixed(2)}`
          : "No strike locked"}
      </span>
    </div>
  );
}
