import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {pathMetrics,protocol,load,root,profileFor,quiet} from './owner-walking.ts';
const trace=(n:number,speed:number,air=false)=>Array.from({length:n},(_,i)=>({tick:(i+1)*20,body:{x:speed*(i+1)*.01*2,y:0},air,applied:[false,speed/500,0]}));
const stationary=pathMetrics(trace(100,0));assert.equal(stationary.visible.speed,null);assert.equal(stationary.visible.fraction,0);
const constant=pathMetrics(trace(100,2));assert(Math.abs(constant.visible.speed-2)<1e-12);assert.equal(constant.visible.eligible_intervals,81);assert.equal(constant.visible.fraction,.81);
assert.equal(pathMetrics(trace(100,.4999)).visible.fraction,0,'Speed below threshold stays stopped');
assert(pathMetrics(trace(100,.5001)).visible.fraction>0,'Speed above threshold walks');
const rotating=trace(100,0);rotating.forEach(f=>f.applied[2]=.1);assert.equal(pathMetrics(rotating).visible.fraction,0,'Rotation alone is not visible walking');
const airborne=pathMetrics(trace(100,2,true));assert.equal(airborne.visible.eligible_intervals,0,'Takeoff is not walking');
const intermittent=trace(120,0);for(let i=20;i<80;i++)intermittent[i].body.x=(i-19)*.04;for(let i=80;i<120;i++)intermittent[i].body.x=2.4;
const bouts=pathMetrics(intermittent).visible.segments;assert(bouts.some(s=>s.walk&&!s.left_censored&&!s.right_censored));
const movingThreshold=protocol.measurement.visible_walking;assert(movingThreshold.includes('0.5'));
const old=load('profiles/game-v2.7.json'),C=profileFor('C',undefined,.045);for(const key of ['strikes','takeoff_duration_ms','takeoff_jitter_tangent','takeoff_rule','arena_radius'])assert.deepEqual(C[key],old[key]);
assert.equal(C.walking_drive.selected.forward,1.75);assert.equal(C.takeoff_speed,.045);
const manifest=existsSync(root+'evidence/V2J/a02/a01-preservation.json')?load('evidence/V2J/a02/a01-preservation.json'):{files:{}};for(const [path,hash] of Object.entries(manifest.files))assert.equal(createHash('sha256').update(readFileSync(root+path)).digest('hex'),hash,`a01 immutable: ${path}`);
if(existsSync(root+'profiles/owner-walking-a02-selected.json')){
 const selected=load('profiles/owner-walking-a02-selected.json');assert.equal(selected.production_profile,old.profile_id);
 for(const r of Object.values(selected.presets) as any[])if(r.offered)assert(Object.values(r.gates).every(v=>v===true));
}
const clock=await quiet(profileFor('A'),101,.2);assert.equal(clock.log.end_tick,400);assert.equal(clock.trace.length,20);
console.log('PASS a02 visible metrics, airborne exclusion, unchanged body rules, preserved a01 and offer safety');
