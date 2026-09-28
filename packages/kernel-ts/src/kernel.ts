import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

export type WebGraph = {
  header: Record<string, any>;
  ids: BigUint64Array;
  offsets: BigInt64Array;
  targets: Int32Array;
  counts: BigUint64Array;
  weights: Float64Array;
};

export type Model = {
  runtime_synaptic_scale: number;
  current_decay: number;
  voltage_decay: number;
  held_drive_factor: number;
  current_coupling_factor: number;
  rest: number;
  reset: number;
  threshold: number;
  refractory_ticks: number;
  delay_ticks: number;
};

export type Noise = {
  seed: number;
  stream_id: number;
  threshold: number;
  current_increment: number;
};

function alignedPayloadOffset(headerLength: number): number {
  const prefix = 12 + headerLength;
  return prefix + ((8 - (prefix % 8)) % 8);
}

export function readGraph(path: string): WebGraph {
  const raw = readFileSync(path);
  if (raw.subarray(0, 8).toString("binary") !== "FLYWEB1\0") {
    throw new Error("invalid web graph magic");
  }
  const headerLength = raw.readUInt32LE(8);
  const header = JSON.parse(raw.subarray(12, 12 + headerLength).toString("utf8"));
  const payloadOffset = alignedPayloadOffset(headerLength);
  const section = (name: string) => header.sections[name];
  const start = (name: string) => raw.byteOffset + payloadOffset + section(name).byte_offset;
  return {
    header,
    ids: new BigUint64Array(raw.buffer, start("ids"), section("ids").length),
    offsets: new BigInt64Array(raw.buffer, start("offsets"), section("offsets").length),
    targets: new Int32Array(raw.buffer, start("targets"), section("targets").length),
    counts: new BigUint64Array(raw.buffer, start("counts"), section("counts").length),
    weights: new Float64Array(raw.buffer, start("weights"), section("weights").length),
  };
}

export function u32(seed: number, stream: number, tick: number, index: number): number {
  let value = (seed + 0x9e3779b9) >>> 0;
  value = (value ^ Math.imul(stream, 0x85ebca6b)) >>> 0;
  value = (value + Math.imul(tick, 0xc2b2ae35)) >>> 0;
  value = (value ^ Math.imul(index, 0x27d4eb2f)) >>> 0;
  value = (value ^ (value >>> 16)) >>> 0;
  value = Math.imul(value, 0x7feb352d) >>> 0;
  value = (value ^ (value >>> 15)) >>> 0;
  value = Math.imul(value, 0x846ca68b) >>> 0;
  return (value ^ (value >>> 16)) >>> 0;
}

export function atanApprox(input: number): number {
  if (!Number.isFinite(input) || input < -8 || input > 8) {
    throw new Error("atan approximation input outside domain");
  }
  const sign = input < 0 ? -1 : 1;
  const magnitude = input < 0 ? -input : input;
  const reduced = magnitude > 1 ? 1 / magnitude : magnitude;
  const core = reduced * (0.7853981633974483 + 0.273 * (1 - reduced));
  return sign * (magnitude > 1 ? 1.5707963267948966 - core : core);
}

export function rotateUnitStep(x: number, y: number, delta: number): [number, number] {
  const nextX = x - delta * y;
  const nextY = y + delta * x;
  const magnitude = Math.sqrt(nextX * nextX + nextY * nextY);
  return [nextX / magnitude, nextY / magnitude];
}

export class KernelState {
  readonly graph: WebGraph;
  readonly model: Model;
  readonly noise: Noise | null;
  readonly voltage: Float64Array;
  readonly synapticCurrent: Float64Array;
  readonly refractoryUntilTick: BigInt64Array;
  readonly pendingSpikeLists: number[][];
  readonly pendingSpikeSets: Set<number>[];
  readonly pendingInputs: Float64Array[];
  readonly arrivalIncrement: Float64Array;
  readonly spikes: Uint8Array;
  tick = 0;

  constructor(graph: WebGraph, model: Model, noise: Noise | null) {
    this.graph = graph;
    this.model = model;
    this.noise = noise;
    this.voltage = new Float64Array(graph.header.N);
    this.synapticCurrent = new Float64Array(graph.header.N);
    this.refractoryUntilTick = new BigInt64Array(graph.header.N);
    const ringSize = model.delay_ticks + 1;
    this.pendingSpikeLists = Array.from({ length: ringSize }, () => []);
    this.pendingSpikeSets = Array.from({ length: ringSize }, () => new Set<number>());
    this.pendingInputs = Array.from({ length: ringSize }, () => new Float64Array(graph.header.N));
    this.arrivalIncrement = new Float64Array(graph.header.N);
    this.spikes = new Uint8Array(graph.header.N);
  }

  step(drive: Float64Array): Uint8Array {
    const count = this.graph.header.N as number;
    if (drive.length !== count) throw new Error("drive size mismatch");
    const ringSize = this.pendingSpikeLists.length;
    const slot = this.tick % ringSize;
    const inputs = this.pendingInputs[slot];
    this.arrivalIncrement.set(inputs);
    inputs.fill(0);
    this.spikes.fill(0);
    for (const source of this.pendingSpikeLists[slot]) {
      const start = Number(this.graph.offsets[source]);
      const stop = Number(this.graph.offsets[source + 1]);
      for (let edge = start; edge < stop; edge += 1) {
        this.arrivalIncrement[this.graph.targets[edge]] +=
          this.graph.weights[edge] * this.model.runtime_synaptic_scale;
      }
    }
    this.pendingSpikeLists[slot] = [];
    this.pendingSpikeSets[slot].clear();
    const endTick = this.tick + 1;
    const arrivalSlot = (endTick + this.model.delay_ticks) % ringSize;
    for (let neuron = 0; neuron < count; neuron += 1) {
      if (this.noise !== null && u32(this.noise.seed, this.noise.stream_id, this.tick, neuron) < this.noise.threshold) {
        this.arrivalIncrement[neuron] += this.noise.current_increment;
      }
      const currentAtBoundary = this.synapticCurrent[neuron] + this.arrivalIncrement[neuron];
      this.synapticCurrent[neuron] = currentAtBoundary * this.model.current_decay;
      if (this.tick >= Number(this.refractoryUntilTick[neuron])) {
        const evolvedVoltage =
          this.model.rest
          + (this.voltage[neuron] - this.model.rest) * this.model.voltage_decay
          + drive[neuron] * this.model.held_drive_factor
          + currentAtBoundary * this.model.current_coupling_factor;
        this.voltage[neuron] = evolvedVoltage;
        if (evolvedVoltage >= this.model.threshold) {
          this.spikes[neuron] = 1;
          this.voltage[neuron] = this.model.reset;
          this.refractoryUntilTick[neuron] = BigInt(endTick + this.model.refractory_ticks);
          if (this.pendingSpikeSets[arrivalSlot].has(neuron)) {
            throw new Error("fixed-delay ring collision");
          }
          this.pendingSpikeLists[arrivalSlot].push(neuron);
          this.pendingSpikeSets[arrivalSlot].add(neuron);
        }
      } else {
        this.voltage[neuron] = this.model.reset;
      }
    }
    this.tick = endTick;
    return this.spikes;
  }

  digest(domain: string): string {
    const hash = createHash("sha256");
    hash.update(Buffer.from(domain + "\0", "utf8"));
    const tick = Buffer.alloc(8);
    tick.writeBigUInt64LE(BigInt(this.tick));
    hash.update(tick);
    hash.update(Buffer.from(this.voltage.buffer, this.voltage.byteOffset, this.voltage.byteLength));
    hash.update(Buffer.from(this.synapticCurrent.buffer, this.synapticCurrent.byteOffset, this.synapticCurrent.byteLength));
    hash.update(Buffer.from(this.refractoryUntilTick.buffer, this.refractoryUntilTick.byteOffset, this.refractoryUntilTick.byteLength));
    const pending = new Uint8Array(this.graph.header.N * this.pendingSpikeLists.length);
    for (let slot = 0; slot < this.pendingSpikeLists.length; slot += 1) {
      for (const neuron of this.pendingSpikeLists[slot]) pending[slot * this.graph.header.N + neuron] = 1;
    }
    hash.update(Buffer.from(pending.buffer));
    for (const values of this.pendingInputs) {
      hash.update(Buffer.from(values.buffer, values.byteOffset, values.byteLength));
    }
    return hash.digest("hex");
  }
}

