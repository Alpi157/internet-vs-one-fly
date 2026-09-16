import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const gradient = { addColorStop: vi.fn() } as unknown as CanvasGradient;
const context = {
  clearRect: vi.fn(),
  createLinearGradient: vi.fn(() => gradient),
  fillRect: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  fillText: vi.fn(),
  ellipse: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  translate: vi.fn(),
  rotate: vi.fn(),
  set fillStyle(_value: string | CanvasGradient | CanvasPattern) {},
  set strokeStyle(_value: string | CanvasGradient | CanvasPattern) {},
  set lineWidth(_value: number) {},
  set font(_value: string) {},
  set textAlign(_value: CanvasTextAlign) {},
} as unknown as CanvasRenderingContext2D;

Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  configurable: true,
  value: vi.fn(() => context),
});

Object.defineProperty(HTMLCanvasElement.prototype, "getBoundingClientRect", {
  configurable: true,
  value: () => ({
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    right: 900,
    bottom: 580,
    width: 900,
    height: 580,
    toJSON: () => ({}),
  }),
});
