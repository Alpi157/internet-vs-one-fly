import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { Game, replayLog, takeoff } from '../src/game.ts';
const root = new URL('../../../', import.meta.url);
const raw = readFileSync(new URL('packages/kernel-ts/test/fixtures/escape.webbin', root));
const buffer = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
const runtime = JSON.parse(readFileSync(new URL('packages/kernel-ts/test/fixtures/v2d-runner.json', root), 'utf8'));
runtime.profile_hashes = { fixture: 'offline' };
runtime.graph_identity = 'fixture';
const profile = JSON.parse(readFileSync(new URL('profiles/game-v2.json', root), 'utf8'));
const game = new Game(buffer, runtime, profile, 1, 2);
assert.deepEqual(takeoff(1, 0, 2, 20, 1), takeoff(1, 0, 2, 20, 1));
assert.throws(() => game.apply({ tick: 1, x: 0, y: 0, hold_ms: 0 }));
for (let i = 0; i < 6; i++) {
    assert(game.apply({ tick: game.tick, x: i % 2 ? 5 : 0, y: 0, hold_ms: [0, 250, 600][i % 3] }));
    const state = game.runner.state;
    while (game.strike)
        game.step();
    assert.equal(game.runner.state, state, 'neural state persists through each strike');
}
assert.equal(game.done, true);
assert.equal(game.strikes, 6);
const log = await game.log();
assert((await replayLog(buffer, runtime, profile, log)).matches);
await assert.rejects(() => replayLog(buffer, { ...runtime, graph_identity: 'different' }, profile, log));
// Impact must use the old held movement and precede a same-boundary onset.
const boundary = new Game(buffer, runtime, profile, 1, 2);
boundary.apply({ tick: 0, x: 0, y: 0, hold_ms: 0 });
while (boundary.tick < 140)
    boundary.step();
boundary.runner.step = () => { boundary.runner.state.tick += 20; return { applied: [false, 0, 0], command: [true, 0, 0], onset: true, encoded: {}, recordedSpikes: [] }; };
const impact = boundary.step();
assert.equal(impact.impact.caught, true);
assert.equal(impact.body.x, 0);
assert(boundary.airUntil > boundary.tick);
console.log('PASS input authority, persistent state, replay digest, identity rejection, collision before onset');
