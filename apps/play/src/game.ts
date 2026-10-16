import { RunnerV2 } from '../../../packages/kernel-ts/src/runner.ts';
import { readGraph, u32, sha256 } from '../../../packages/kernel-ts/src/kernel.ts';
import { advanceBody } from '../../../packages/kernel-ts/src/body.ts';
import type { Body } from '../../../packages/kernel-ts/src/body.ts';
export type Input = {
    tick: number;
    x: number;
    y: number;
    hold_ms: number;
};
export type Frame = {
    tick: number;
    body: Body;
    air: boolean;
    applied: [boolean,number,number];
    gait: number;
    activity_hz: number;
    strike: any;
    impact: any;
    onset: boolean;
    spikes: {
        tick: number;
        indices: number[];
    }[];
};
export type RoundLog = {
    schema: string;
    neural_seed: number;
    environment_seed: number;
    profile_hashes: Record<string, string>;
    graph_identity: string;
    inputs: Input[];
    end_tick: number;
    digest: string;
    gaps: any[];
};
// No geometry is reachable from this pure takeoff function.
export function takeoff(heading_x: number, heading_y: number, seed: number, tick: number, jitter: number): [
    number,
    number
] {
    const delta = (u32(seed, 43, tick, 0) / 2 ** 32 * 2 - 1) * jitter;
    const x = heading_x - delta * heading_y, y = heading_y + delta * heading_x;
    const norm = Math.sqrt(x * x + y * y);
    return [x / norm, y / norm];
}
export class Game {
    runner: RunnerV2;
    profile: any;
    runtime: any;
    environmentSeed: number;
    neuralSeed: number;
    // Read-only display copy of the encoder output; never fed back into simulation.
    looming: Readonly<Record<string, number>> = Object.freeze({});
    inputs: Input[] = [];
    frames: Frame[] = [];
    impacts: any[] = [];
    strike: any = null;
    airUntil = 0;
    airDirection: [
        number,
        number
    ] = [1, 0];
    gait = 0;
    strikes = 0;
    catches = 0;
    done = false;
    lastImpact: any = null;
    constructor(buffer: ArrayBuffer, runtime: any, profile: any, neuralSeed: number, environmentSeed: number) {
        if (profile.arena_shape === 'circle' && (!Number.isFinite(profile.arena_radius) || profile.arena_radius <= 0))
            throw new Error('Invalid circle radius');
        for (const strike of profile.strikes) {
            const ticks = 8 / strike.speed / .5;
            if (!Number.isFinite(ticks) || Math.abs(ticks - Math.round(ticks / 20) * 20) > 1e-8)
                throw new Error('Strike impact must align with a 10 ms control boundary');
        }
        this.runtime = structuredClone(runtime);
        this.profile = structuredClone(profile);
        this.neuralSeed = neuralSeed;
        this.environmentSeed = environmentSeed;
        const config = structuredClone(runtime.config);
        config.noise.seed = neuralSeed;
        config.body_enabled = false;
        this.runner = new RunnerV2(readGraph(buffer), config);
    }
    get tick() { return this.runner.state.tick; }
    apply(input: Input) {
        if (this.done || this.strike || this.strikes >= this.profile.max_strikes)
            return false;
        if (input.tick !== this.tick || input.tick % 20 || ![input.x, input.y, input.hold_ms].every(Number.isFinite) || input.hold_ms < 0 || (this.profile.arena_shape === 'circle' ? Math.hypot(input.x, input.y) > this.profile.arena_radius : Math.abs(input.x) > this.profile.arena_half_size || Math.abs(input.y) > this.profile.arena_half_size))
            throw new Error('Invalid authoritative input');
        const type = input.hold_ms < this.profile.hold_thresholds_ms[0] ? 0 : input.hold_ms < this.profile.hold_thresholds_ms[1] ? 1 : 2;
        const spec = this.profile.strikes[type];
        this.inputs.push({ ...input });
        this.strikes++;
        this.strike = { ...spec, aim_x: input.x, aim_y: input.y, start_tick: this.tick, impact_tick: this.tick + Math.round(8 / spec.speed / .5), number: this.strikes };
        return true;
    }
    step(): Frame {
        if (this.done)
            throw new Error('Round complete');
        const start = this.tick, s = this.strike;
        const stimulus = s ? { active: start < s.impact_tick, aim_x: s.aim_x, aim_y: s.aim_y, elapsed_ms: (start - s.start_tick) * .5, downward_speed_per_ms: s.speed, hand_radius: s.radius } : { active: false, aim_x: 0, aim_y: 0, elapsed_ms: 0, downward_speed_per_ms: 0 };
        const value = this.runner.step(stimulus);
        this.looming = Object.freeze({ ...value.encoded });
        // Integrate held movement, then collision, then newly decoded onset. Every
        // supported strike impact is aligned to a 10 ms control boundary.
        let body = this.runner.body;
        if (start < this.airUntil) {
            body = { ...body, x: body.x + this.airDirection[0] * this.profile.takeoff_speed * 10, y: body.y + this.airDirection[1] * this.profile.takeoff_speed * 10 };
        }
        else
            body = advanceBody(body, value.applied[1], value.applied[2]);
        if (this.profile.arena_shape === 'circle') {
            const radius = this.profile.arena_radius;
            let distance = Math.hypot(body.x, body.y);
            while (distance > radius) {
                const nx = body.x / distance, ny = body.y / distance;
                const factor = 2 * radius / distance - 1;
                body.x *= factor; body.y *= factor;
                const headingDot = body.heading_x * nx + body.heading_y * ny;
                body.heading_x -= 2 * headingDot * nx;
                body.heading_y -= 2 * headingDot * ny;
                const airDot = this.airDirection[0] * nx + this.airDirection[1] * ny;
                this.airDirection = [this.airDirection[0] - 2 * airDot * nx, this.airDirection[1] - 2 * airDot * ny];
                distance = Math.hypot(body.x, body.y);
            }
        } else {
        const bound = this.profile.arena_half_size;
        for (const axis of ['x', 'y'] as const) {
            const heading = axis === 'x' ? 'heading_x' : 'heading_y';
            const index = axis === 'x' ? 0 : 1;
            while (body[axis] > bound || body[axis] < -bound) {
                body[axis] = body[axis] > bound ? 2 * bound - body[axis] : -2 * bound - body[axis];
                body[heading] = -body[heading];
                this.airDirection[index] = -this.airDirection[index];
            }
        }
        }
        this.runner.body = body;
        let impact = null;
        if (s && this.tick === s.impact_tick) {
            const dx = body.x - s.aim_x, dy = body.y - s.aim_y;
            const caught = dx * dx + dy * dy <= s.radius * s.radius;
            const priorOnsets = this.frames.filter(f => f.onset && f.tick > s.start_tick && f.tick < s.impact_tick);
            const gf = new Set(this.runner.config.groups.slice(0, 2).flat());
            const events = [...this.frames.flatMap(f => f.spikes), ...value.recordedSpikes];
            const firstGf = events.find(e => e.tick > s.start_tick && e.tick < s.impact_tick && e.indices.some(i => gf.has(Number(this.runner.state.graph.ids[i]))));
            impact = { tick: this.tick, caught, position: { x: body.x, y: body.y }, aim: { x: s.aim_x, y: s.aim_y }, radius: s.radius, type: s.name, lead_ms: firstGf ? (s.impact_tick - firstGf.tick) * .5 : null, escape_onset_lead_ms: priorOnsets.length ? (s.impact_tick - priorOnsets[0].tick) * .5 : null };
            this.lastImpact = impact;
            this.impacts.push(impact);
            if (caught)
                this.catches++;
        }
        if (value.onset && this.tick >= this.airUntil) {
            this.airDirection = takeoff(body.heading_x, body.heading_y, this.environmentSeed, this.tick, this.profile.takeoff_jitter_tangent);
            this.airUntil = this.tick + this.profile.takeoff_duration_ms * 2;
        }
        this.gait += Math.abs(value.applied[1])*10 + Math.abs(value.applied[2])*10;
        const frame = { applied: value.applied, gait: this.gait, activity_hz: value.recordedSpikes.reduce((n,e)=>n+e.indices.length,0)/this.runner.state.graph.header.N/.01, tick: this.tick, body: { ...body }, air: this.tick < this.airUntil, strike: s ? { ...s } : null, impact, onset: value.onset, spikes: value.recordedSpikes };
        this.frames.push(frame);
        if (this.frames.length > this.profile.recording_max_intervals)
            throw new Error('Declared recording bound exceeded');
        if (s && this.tick >= s.impact_tick + this.profile.replay_post_ms * 2) {
            this.strike = null;
            if (this.strikes >= this.profile.max_strikes)
                this.done = true;
        }
        if (this.tick >= this.profile.round_ms * 2)
            this.done = true;
        return frame;
    }
    replayFrames() { const input = this.inputs.at(-1); return input ? this.frames.filter(f => f.tick >= input.tick - this.profile.replay_pre_ms * 2) : []; }
    async digest() {
        const neural = await this.runner.digest();
        const payload = { neural, tick: this.tick, airUntil: this.airUntil, airDirection: this.airDirection, strike: this.strike, strikes: this.strikes, catches: this.catches, done: this.done, inputs: this.inputs, impacts: this.impacts, neural_seed: this.neuralSeed, environment_seed: this.environmentSeed, profile: this.profile, profile_hashes: this.runtime.profile_hashes, graph_identity: this.runtime.graph_identity };
        return sha256(new TextEncoder().encode(JSON.stringify(payload)));
    }
    async log(): Promise<RoundLog> { return { schema: 'flybench.game-round.v2', neural_seed: this.neuralSeed, environment_seed: this.environmentSeed, profile_hashes: this.runtime.profile_hashes, graph_identity: this.runtime.graph_identity, inputs: this.inputs.map(v => ({ ...v })), end_tick: this.tick, digest: await this.digest(), gaps: [] }; }
}
export async function replayLog(buffer: ArrayBuffer, runtime: any, profile: any, log: RoundLog) {
    if (JSON.stringify(runtime.profile_hashes) !== JSON.stringify(log.profile_hashes) || runtime.graph_identity !== log.graph_identity)
        throw new Error('Replay identity mismatch');
    const game = new Game(buffer, runtime, profile, log.neural_seed, log.environment_seed);
    let next = 0;
    while (game.tick < log.end_tick) {
        if (log.inputs[next]?.tick === game.tick) {
            if (!game.apply(log.inputs[next++]))
                throw new Error('Rejected recorded input');
        }
        game.step();
    }
    if (next !== log.inputs.length)
        throw new Error('Unconsumed input');
    return { digest: await game.digest(), matches: await game.digest() === log.digest, catches: game.catches };
}
