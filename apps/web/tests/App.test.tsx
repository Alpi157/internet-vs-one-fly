import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import App from "../src/App";
import type { GameState } from "../src/types";

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  message(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent);
  }

  send(value: string) {
    this.sent.push(value);
  }

  close() {
    this.readyState = 3;
  }

  disconnect() {
    this.readyState = 3;
    this.onclose?.();
  }
}

const state = (locked: { x: number; y: number } | null = null): GameState => ({
  type: "state",
  server_tick: 4,
  logical_time_ms: 40,
  round_remaining_ms: 19960,
  phase: locked ? "wind-up" : "ready",
  aim: null,
  strike: locked
    ? {
        attack_id: "attack-1",
        locked_target: locked,
        commit_tick: 4,
        stimulus_tick: 24,
        impact_tick: 64,
        phase: "wind-up",
        progress: 0,
        strike_radius: 0.55,
      }
    : null,
  cooldown_remaining_ms: 0,
  attacks_used: locked ? 1 : 0,
  attempts_remaining: locked ? 5 : 6,
  fly: {
    x: 0,
    y: 0,
    heading_rad: 0,
    takeoff_started: false,
    takeoff_active: false,
  },
  last_impact: null,
  result: null,
  result_reason: null,
  backend: "kernel",
  model: { N: 313, E: 20607, represented_contacts: 79112 },
});

function connectedApp() {
  render(<App />);
  const socket = FakeWebSocket.instances.at(-1)!;
  act(() => socket.open());
  act(() => socket.message(state()));
  return socket;
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  Object.defineProperty(globalThis, "WebSocket", {
    configurable: true,
    value: FakeWebSocket,
  });
});

describe("M08 local game input and disclosure", () => {
  it("sends mouse/pointer aim and attack commit coordinates", () => {
    const socket = connectedApp();
    const arena = screen.getByTestId("arena");
    fireEvent.pointerMove(arena, { clientX: 675, clientY: 145, pointerType: "mouse" });
    fireEvent.pointerDown(arena, { clientX: 675, clientY: 145, pointerType: "mouse" });
    const payloads = socket.sent.map((item) => JSON.parse(item));
    expect(payloads[0]).toMatchObject({ type: "aim", x: 5, y: 5, sequence: 1 });
    expect(payloads[1]).toMatchObject({ type: "attack", x: 5, y: 5, sequence: 2 });
  });

  it("uses unified pointer input for touch attack commit", () => {
    const socket = connectedApp();
    fireEvent.pointerDown(screen.getByTestId("arena"), {
      clientX: 225,
      clientY: 435,
      pointerType: "touch",
      pointerId: 8,
    });
    expect(JSON.parse(socket.sent.at(-1)!)).toMatchObject({
      type: "attack",
      x: -5,
      y: -5,
    });
  });

  it("keeps the server-acknowledged strike locked after later aim movement", () => {
    const socket = connectedApp();
    act(() => socket.message(state({ x: 2, y: -3 })));
    expect(screen.getByTestId("locked-readout").textContent).toContain("2.00, -3.00");
    fireEvent.pointerMove(screen.getByTestId("arena"), {
      clientX: 855,
      clientY: 29,
      pointerType: "mouse",
    });
    expect(screen.getByTestId("aim-readout").textContent).toContain("9.00, 9.00");
    expect(screen.getByTestId("locked-readout").textContent).toContain("2.00, -3.00");
  });

  it("shows a visible disconnected state", () => {
    const socket = connectedApp();
    act(() => socket.disconnect());
    expect(screen.getByRole("alert").textContent).toContain("Disconnected");
    expect(screen.getByRole("status").textContent).toContain("disconnected");
  });

  it("renders mutually coherent state through disconnect and reconnect", () => {
    const first = connectedApp();
    expect(screen.getByText("Authoritative server connected")).not.toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();

    act(() => first.disconnect());
    expect(screen.queryByText("Authoritative server connected")).toBeNull();
    expect(screen.getByRole("alert").textContent).toContain("Disconnected");

    fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));
    const second = FakeWebSocket.instances.at(-1)!;
    expect(second).not.toBe(first);
    act(() => second.open());
    act(() => first.disconnect());
    expect(screen.getByText("Authoritative server connected")).not.toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText("Disconnected from the authoritative game server.")).toBeNull();
  });

  it("discloses the server-configured locked collision radius", () => {
    const socket = connectedApp();
    act(() => socket.message(state({ x: 2, y: -3 })));
    expect(screen.getByTestId("locked-readout").textContent).toContain("radius 0.55");
  });

  it("discloses the actual live model without a full-graph live claim", () => {
    connectedApp();
    const notice = screen.getByLabelText("Model disclosure");
    expect(notice.textContent).toContain("313-neuron");
    expect(notice.textContent).toContain("feature-level/scalar");
    expect(notice.textContent).not.toContain("166,700");
  });
});
