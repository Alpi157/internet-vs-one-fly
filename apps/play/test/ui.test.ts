import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { Game } from '../src/game.ts';
import { encodeHand } from '../../../packages/kernel-ts/src/encoding.ts';
import { spikeAlpha } from '../src/brain-view.ts';
const root = new URL('../../../', import.meta.url), read = (p: string) => readFileSync(new URL(p, root)), json = (p: string) => JSON.parse(read(p).toString());
const old = json('profiles/game-v2-history/game-v2.6.json'), profile = json('profiles/game-v2.7.json'), runtime = json('packages/kernel-ts/test/fixtures/v2d-runner.json'), raw = read('packages/kernel-ts/test/fixtures/escape.webbin'), buffer = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
assert(Math.abs(Math.PI * profile.arena_radius ** 2 - (old.arena_half_size * 2) ** 2) < 1e-12);
for (const k of Object.keys(old))
    if (!['version', 'profile_id', 'change_reason'].includes(k))
        assert.deepEqual(profile[k], old[k], k);
assert.deepEqual(profile, json('profiles/game-v2.json'));
assert.deepEqual(profile, json('apps/play/public/data/game.json'));
const square = new Game(buffer, runtime, old, 1, 2), circle = new Game(buffer, runtime, profile, 1, 2);
square.apply({ tick: 0, x: 0, y: 0, hold_ms: 300 });
circle.apply({ tick: 0, x: 0, y: 0, hold_ms: 300 });
for (let i = 0; i < 70; i++) {
    const a = square.step(), b = circle.step();
    assert(Math.hypot(a.body.x, a.body.y) < old.arena_half_size, 'no wall contact envelope');
    assert.deepEqual(a, b, 'frames exactly equal without wall contact');
}
const bounce = new Game(buffer, runtime, profile, 1, 2), R = profile.arena_radius;
bounce.runner.body = { x: R + 1, y: 0, heading_x: 1, heading_y: 0 };
bounce.airDirection = [1, 0];
bounce.runner.step = () => { bounce.runner.state.tick += 20; return { applied: [false, 0, 0], command: [false, 0, 0], onset: false, encoded: {}, recordedSpikes: [] }; };
bounce.step();
assert(Math.abs(bounce.runner.body.x - (R - 1)) < 1e-12);
assert.equal(bounce.runner.body.heading_x, -1);
assert.equal(bounce.airDirection[0], -1);
bounce.runner.body = { x: R * 10 + .1, y: 0, heading_x: 1, heading_y: 0 };
bounce.step();
assert(Math.hypot(bounce.runner.body.x, bounce.runner.body.y) <= R);
assert.throws(() => new Game(buffer, runtime, profile, 1, 2).apply({ tick: 0, x: R, y: R, hold_ms: 0 }), /Invalid/);
const features = new Game(buffer, runtime, profile, 1, 2);
features.apply({ tick: 0, x: 1, y: 1, hold_ms: 300 });
for (let i = 0; i < 16; i++) {
    const s = features.strike, b = features.runner.body;
    const expected = encodeHand({ active: features.tick < s.impact_tick, aim_x: s.aim_x, aim_y: s.aim_y, elapsed_ms: (features.tick - s.start_tick) * .5, downward_speed_per_ms: s.speed, hand_radius: s.radius }, b.x, b.y, b.heading_x, b.heading_y, features.runner.config.gain);
    features.step();
    assert.deepEqual(features.looming, expected);
    assert(Object.isFrozen(features.looming));
}
assert.equal(spikeAlpha(120, 0), Math.exp(-1));
assert.equal(spikeAlpha(120, 120), 1);
assert.equal(spikeAlpha(100, 120), 0);
const base = 'ae3e417ed6dd0882550b95b3ff29b56c751d60fa', prior = JSON.parse(execFileSync('git', ['show', `${base}:apps/play/public/data/runtime.json`], { cwd: new URL('.', root) }).toString()), current = json('apps/play/public/data/runtime.json');
for (const [key, value] of Object.entries(prior))
    if (key !== 'profile_hashes')
        assert.equal(JSON.stringify(current[key]), JSON.stringify(value), `runtime ${key} byte-identical serialized value`);
for (const [key, value] of Object.entries(prior.profile_hashes))
    if (!['profiles/game-v2.json', 'apps/play/src/game.ts'].includes(key))
        assert.equal(current.profile_hashes[key], value, `neural identity ${key}`);
for (const path of ['profiles/freeze-v2.json', 'profiles/freeze-v2.1.json'])
    for (const [file, hash] of Object.entries(json(path).files))
        assert.equal(createHash('sha256').update(read(file)).digest('hex'), hash, `frozen ${file}`);
for (const [file, hash] of Object.entries(current.profile_hashes))
    assert.equal(createHash('sha256').update(read(file)).digest('hex'), hash, `runtime identity ${file}`);
for (const font of json('apps/play/public/fonts/manifest.json')) {
    const bytes = read('apps/play/public/fonts/' + font.file);
    assert.equal(bytes.subarray(0, 4).toString(), 'wOF2');
    assert.equal(createHash('sha256').update(bytes).digest('hex'), font.sha256);
}
for (const name of ['Doto', 'Atkinson'])
    assert.match(read('apps/play/public/fonts/' + name + '-OFL.txt').toString(), /SIL OPEN FONT LICENSE Version 1.1/);
console.log('PASS equal-area circle, repeated reflections, no-wall exact frames, actual read-only encoder features, neural identities, frozen files, display decay, local WOFF2 licenses');
