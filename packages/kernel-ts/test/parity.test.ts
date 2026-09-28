import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { atanApprox, KernelState, readGraph, rotateUnitStep, u32 } from "../src/kernel.ts";

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

function floatFromHex(value: string): number {
  const match = /^(-?)0x([0-9a-f]+)(?:\.([0-9a-f]+))?p([+-]?\d+)$/i.exec(value);
  if (match === null) throw new Error(`invalid float hex ${value}`);
  const sign = match[1] === "-" ? -1 : 1;
  const fraction = match[3] ?? "";
  const mantissa = Number.parseInt(match[2], 16) + (fraction ? Number.parseInt(fraction, 16) / 16 ** fraction.length : 0);
  return sign * mantissa * 2 ** Number.parseInt(match[4], 10);
}

function checkVectors(root: string): void {
  const vectors = JSON.parse(readFileSync(resolve(root, "tests/vectors/detmath-v1.json"), "utf8"));
  for (const vector of vectors.rng) {
    const inputs = ["seed_hex", "stream_hex", "tick_hex", "index_hex"].map((name) => Math.trunc(floatFromHex(vector[name])));
    assert(u32(inputs[0], inputs[1], inputs[2], inputs[3]) === vector.output_u32, "RNG vector mismatch");
  }
  for (const vector of vectors.approximations.atan) {
    assert(Object.is(atanApprox(floatFromHex(vector.input_hex)), floatFromHex(vector.output_hex)), "atan vector mismatch");
  }
  for (const vector of vectors.approximations.rotate_unit_step) {
    const output = rotateUnitStep(floatFromHex(vector.heading_x_hex), floatFromHex(vector.heading_y_hex), floatFromHex(vector.delta_hex));
    assert(Object.is(output[0], floatFromHex(vector.output_x_hex)), "rotation x vector mismatch");
    assert(Object.is(output[1], floatFromHex(vector.output_y_hex)), "rotation y vector mismatch");
  }
}

function fixtureParity(packageRoot: string): Record<string, unknown> {
  const graph = readGraph(resolve(packageRoot, "test/fixtures/escape.webbin"));
  const log = JSON.parse(readFileSync(resolve(packageRoot, "test/fixtures/v2a-bot-input-log.json"), "utf8"));
  const state = new KernelState(graph, log.model, null);
  const indexById = new Map<string, number>();
  graph.ids.forEach((value, index) => indexById.set(value.toString(), index));
  const lc4 = log.input_populations.LC4.map((value: string) => indexById.get(value));
  const lplc2 = log.input_populations.LPLC2.map((value: string) => indexById.get(value));
  const drive = new Float64Array(graph.header.N);
  const started = performance.now();
  for (let intervalIndex = 0; intervalIndex < log.intervals.length; intervalIndex += 1) {
    const interval = log.intervals[intervalIndex];
    drive.fill(0);
    for (const index of lc4) drive[index] = interval.held_lc4;
    for (const index of lplc2) drive[index] = interval.held_lplc2;
    for (let step = 0; step < 20; step += 1) state.step(drive);
    const digest = state.digest(log.digest_domain_utf8_nul);
    if (digest !== interval.expected_state_sha256) {
      throw new Error(`fixture parity mismatch at control interval ${intervalIndex + 1}, neural tick ${state.tick}`);
    }
  }
  const wallSeconds = (performance.now() - started) / 1000;
  return {
    status: "PASS",
    intervals: log.intervals.length,
    simulated_seconds: log.intervals.length * 0.01,
    wall_seconds: wallSeconds,
    wall_seconds_per_simulated_second: wallSeconds / (log.intervals.length * 0.01),
  };
}

function t1aParity(root: string): Record<string, unknown> {
  const graphPath = resolve(root, "data/compiled/v2/t1a.webbin");
  const parityPath = resolve(root, "data/compiled/v2/t1a-parity.json");
  if (!existsSync(graphPath) || !existsSync(parityPath)) return { status: "SKIP", reason: "local T1a export absent" };
  const graph = readGraph(graphPath);
  const parity = JSON.parse(readFileSync(parityPath, "utf8"));
  const state = new KernelState(graph, parity.model, parity.noise);
  const drive = new Float64Array(graph.header.N);
  const started = performance.now();
  for (const interval of parity.intervals) {
    for (let step = 0; step < 20; step += 1) state.step(drive);
    const digest = state.digest(parity.digest_domain_utf8_nul);
    if (digest !== interval.expected_state_sha256) {
      throw new Error(`T1a parity mismatch at control interval ${interval.control_interval}, neural tick ${state.tick}`);
    }
  }
  const wallSeconds = (performance.now() - started) / 1000;
  return {
    status: "PASS",
    intervals: parity.intervals.length,
    simulated_seconds: 1,
    wall_seconds: wallSeconds,
    wall_seconds_per_simulated_second: wallSeconds,
  };
}

const packageRoot = resolve(import.meta.dirname, "..");
const root = resolve(packageRoot, "../..");
checkVectors(root);
const fixture = fixtureParity(packageRoot);
const fixtureOnly = process.argv.includes("--fixture-only");
const t1a = fixtureOnly ? { status: "NOT_RUN_FIXTURE_ONLY" } : t1aParity(root);
const report = {
  schema: "flybench.v2b.kernel-ts-parity",
  version: 1,
  status: fixture.status === "PASS" && (t1a.status === "PASS" || fixtureOnly) ? "PASS" : "INCOMPLETE",
  detmath_vectors: "PASS",
  fixture_v1_v2a_bot_log: fixture,
  t1a_noise_one_second: t1a,
};
if (!fixtureOnly) {
  const output = resolve(root, "evidence/V2B/p3/kernel-ts-parity.json");
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
}
console.log(JSON.stringify(report));
