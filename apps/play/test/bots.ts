import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
import {gunzipSync} from 'node:zlib';
import { Game } from '../src/game.ts';
import { u32 } from '../../../packages/kernel-ts/src/kernel.ts';
const root = resolve(import.meta.dirname, '../../..'), data = resolve(root, 'apps/play/public/data');
const runtime = JSON.parse(readFileSync(resolve(data, 'runtime.json'), 'utf8')), profile = JSON.parse(readFileSync(resolve(root, 'profiles/game-v2.json'), 'utf8'));
const raw = readFileSync(resolve(data, 'circuit.flygraph.gz'));
const packed = gunzipSync(raw);
const buffer = unpackGraph(packed.buffer.slice(packed.byteOffset, packed.byteOffset + packed.byteLength));
const out = resolve(root, 'evidence/V2E/game');
mkdirSync(out, { recursive: true });
const rounds = Number(process.env.FLYBENCH_BOT_ROUNDS ?? 10), strategies: any[] = [];
for (const type of [0, 1, 2])
    for (const lead of [0, .5, 1.5])
        strategies.push({ name: `${profile.strikes[type].name}-lead-${lead}`, type, lead });
strategies.push({ name: 'random-strike-current', type: -1, lead: 0 });
function cluster95(records: any[]) {
    const totals = Array.from({ length: rounds }, (_, r) => records.filter(x => x.seed === 2026400000 + r).filter(x => x.caught).length);
    const draws = [];
    for (let b = 0; b < 10000; b++) {
        let sum = 0;
        for (let r = 0; r < rounds; r++)
            sum += totals[u32(2026600001, 79, b, r) % rounds];
        draws.push(sum / (rounds * 6));
    }
    draws.sort((a, b) => a - b);
    return [draws[249], draws[9749]];
}
function wilson(k: number, n: number) { const z = 1.959963984540054, p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d; return [c - h, c + h]; }
const started = performance.now(), results = [];
for (const strategy of strategies) {
    let catches = 0, strikes = 0;
    const records = [];
    for (let r = 0; r < rounds; r++) {
        const seed = 2026400000 + r, game = new Game(buffer, runtime, profile, seed, 2026500000 + r);
        for (let n = 0; n < 6; n++) {
            // Observe, then wait 180 ms before committing a noisy aim. Holding time is
            // a chosen strike type, not additional access to future state.
            const observed = { ...game.runner.body };
            for (let t = 0; t < 18; t++)
                game.step();
            const type = strategy.type < 0 ? u32(seed, 71, n, 2) % 3 : strategy.type;
            const noiseX = (u32(seed, 71, n, 0) / 2 ** 32 * 2 - 1) * .8, noiseY = (u32(seed, 71, n, 1) / 2 ** 32 * 2 - 1) * .8;
            const bound = profile.arena_half_size;
            const x = Math.max(-bound, Math.min(bound, observed.x + strategy.lead * observed.heading_x + noiseX)), y = Math.max(-bound, Math.min(bound, observed.y + strategy.lead * observed.heading_y + noiseY));
            game.apply({ tick: game.tick, x, y, hold_ms: [80, 300, 600][type] });
            while (game.strike)
                game.step();
            records.push({ seed, environment_seed: 2026500000 + r, strike: n, ...game.lastImpact });
        }
        if(game.impacts.length!==6)throw new Error('Every scripted strike must resolve an impact');
        catches += game.catches;
        strikes += game.strikes;
    }
    const row = { ...strategy, catches, strikes, catch_rate: catches / strikes, wilson95_nominal_independent_strikes: wilson(catches, strikes), cluster_bootstrap95: cluster95(records), target_pass: catches / strikes >= .1 && catches / strikes <= .7, records };
    results.push(row);
    console.log(JSON.stringify({ ...row, records: undefined }));
}
const report = { profile_id: profile.profile_id, profile, rounds_per_strategy: rounds, reaction_delay_ms: 180, interval_method: '95% percentile bootstrap of independent six-strike rounds, 10000 resamples, stream 79 seed 2026600001; descriptive only, ten rounds per strategy', aim_noise: 'independent uniform +/-0.8 arena units on each axis, RNG stream 71, fixed across game versions', neural_profile: runtime.status, parameters: runtime.parameters, status: results.every(r => r.target_pass) ? 'PASS' : 'TARGET_MISSED', wall_seconds: (performance.now() - started) / 1000, results };
writeFileSync(resolve(out, `bots-v${profile.version}.json`), JSON.stringify(report, null, 2) + '\n');

if(report.status!=='PASS')process.exitCode=1;
