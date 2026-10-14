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

export function readGraph(raw: ArrayBuffer): WebGraph {
  const bytes = new Uint8Array(raw);
  if (new TextDecoder().decode(bytes.subarray(0, 8)) !== "FLYWEB1\0") throw new Error("invalid web graph magic");
  const headerLength = new DataView(raw).getUint32(8, true);
  const header = JSON.parse(new TextDecoder().decode(bytes.subarray(12,12+headerLength)));
  const payloadOffset = alignedPayloadOffset(headerLength);
  const section = (name: string) => header.sections[name];
  const start = (name: string) => payloadOffset + section(name).byte_offset;
  return { header,
    ids: new BigUint64Array(raw,start("ids"),section("ids").length),
    offsets: new BigInt64Array(raw,start("offsets"),section("offsets").length),
    targets: new Int32Array(raw,start("targets"),section("targets").length),
    counts: new BigUint64Array(raw,start("counts"),section("counts").length),
    weights: new Float64Array(raw,start("weights"),section("weights").length) };
}

export function u32V1(seed: number, stream: number, tick: number, index: number): number {
  for (const v of [seed,stream,tick,index]) if (!Number.isInteger(v) || v<0 || v>=2**32) throw new Error("u32 counters outside domain");
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

export function fmix32(input: number): number {
  let x = input >>> 0;
  x = (x ^ (x >>> 16)) >>> 0;
  x = Math.imul(x,0x85ebca6b) >>> 0;
  x = (x ^ (x >>> 13)) >>> 0;
  x = Math.imul(x,0xc2b2ae35) >>> 0;
  return (x ^ (x >>> 16)) >>> 0;
}
export function u32(seed: number, stream: number, tick: number, index: number): number {
  for (const v of [seed,stream,tick,index]) if (!Number.isInteger(v) || v < 0 || v >= 2**32) throw new Error("u32 counters outside domain");
  let h = fmix32(seed+0x9e3779b9);
  h = fmix32(h ^ stream);
  h = fmix32(h+tick);
  return fmix32(h ^ index);
}

export function atanApprox(input: number): number {
  if (!Number.isFinite(input) || input < -8 || input > 8) {
    throw new Error("atan approximation input outside domain");
  }
  const sign = input < 0 ? -1 : 1;
  const magnitude = input < 0 ? -input : input;
  let reduced = magnitude > 1 ? 1/magnitude : magnitude;
  for (let k=0;k<2;k++) reduced = reduced/(1+Math.sqrt(1+reduced*reduced));
  const square = reduced*reduced;
  let term = reduced;
  let core = term;
  for (let k=1;k<9;k++) { term = -term*square; core = core + term/(2*k+1); }
  core = 4*core;
  return sign*(magnitude>1 ? 1.5707963267948966-core : core);
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
    if (noise) {
      u32(noise.seed,noise.stream_id,0,0);
      if (!Number.isInteger(noise.threshold) || noise.threshold<0 || noise.threshold>2**32 || !Number.isFinite(noise.current_increment) || noise.current_increment<0) throw new Error("invalid noise");
    }
    this.voltage = new Float64Array(graph.header.N);
    this.voltage.fill(model.rest);
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
    if (this.tick>=2**32-1) throw new Error("u32 clock exhausted");
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

  neuralBytes(): Uint8Array {
    const tick = new Uint8Array(8);
    new DataView(tick.buffer).setBigUint64(0,BigInt(this.tick),true);
    const pending = new Uint8Array(this.graph.header.N*this.pendingSpikeLists.length);
    for (let slot=0;slot<this.pendingSpikeLists.length;slot++) for (const neuron of this.pendingSpikeLists[slot]) pending[slot*this.graph.header.N+neuron]=1;
    return concatBytes([tick,new Uint8Array(this.voltage.buffer),new Uint8Array(this.synapticCurrent.buffer),
      new Uint8Array(this.refractoryUntilTick.buffer),pending,...this.pendingInputs.map(v=>new Uint8Array(v.buffer))]);
  }
  async digest(domain: string): Promise<string> {
    return sha256(concatBytes([new TextEncoder().encode(domain+"\0"),this.neuralBytes()]));
  }
}

export function concatBytes(parts: Uint8Array[]): Uint8Array {
  const out=new Uint8Array(parts.reduce((n,p)=>n+p.byteLength,0));
  let offset=0;for (const part of parts) {out.set(part,offset);offset+=part.byteLength;}return out;
}
export async function sha256(bytes: Uint8Array): Promise<string> {
  const result=await crypto.subtle.digest("SHA-256",bytes);
  return Array.from(new Uint8Array(result),v=>v.toString(16).padStart(2,"0")).join("");
}
