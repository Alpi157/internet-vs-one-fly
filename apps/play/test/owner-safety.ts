import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {load,root,sha,summarize} from './owner-walking.ts';
const selection=load('profiles/owner-walking-a02-selected.json'),protocol=load('profiles/owner-walking-a02.json'),parity=load('evidence/V2J/a02/parity/summary.json');
const hash=(path:string)=>createHash('sha256').update(readFileSync(root+path)).digest('hex');
assert.equal(selection.protocol_sha256,hash('profiles/owner-walking-a02.json'));
const a01=load('evidence/V2J/drive/selection.json');assert.equal(a01.status,'TARGET_MISSED');assert.equal(a01.passing,0);assert.equal(a01.selected,null);
for(const [p,h] of Object.entries(load('evidence/V2J/a02/a01-preservation.json').files))assert.equal(hash(p),h,`a01 changed: ${p}`);
const d=load('evidence/V2J/a02/selection/D.json'),c=load('evidence/V2J/a02/selection/C.json');
assert.equal(d.selected,d.rows.find((r:any)=>r.summary.visible.median_bout_s>=.3)?.forward??null);
assert.equal(c.selected,c.rows.find((r:any)=>r.bot.rates[0].n>0&&r.bot.rates[0].catch_rate<=.65)?.takeoff_speed??null);
const baseline=load('evidence/V2J/a02/original-swat/baseline.json').swat;assert.equal(baseline.conservative_escape_probability,.88);assert.equal(baseline.opportunities,200);assert.equal(baseline.censored,0);
let offered=0;
for(const [id,entry] of Object.entries(selection.presets) as any[]){
 const r=load(`evidence/V2J/a02/presets/${id}.json`);assert.equal(entry.offered,r.offered);
 if(!r.profile)continue;
 const quiet=Array.from({length:20},(_,i)=>load(`evidence/V2J/a02/presets/${id}/quiet-${i+1}.json`));
 for(const q of quiet){assert.equal(q.seconds,30);assert.equal(q.log.end_tick,60000);assert.equal(q.trace.length,3000);assert.equal(q.log.profile_hashes.owner_playtest_profile,entry.profile_sha256);}
 assert.deepEqual(summarize(quiet),r.summary,'Quiet aggregate must match full 30 s records');
 assert.equal(entry.profile_sha256,sha(r.profile));assert.equal(parity.profile_hashes[id],entry.profile_sha256);
 const swat=r.swat;assert.equal(swat.protocol,'Exact a01 repeated-strike schedule');assert.equal(swat.opportunities,200);assert.equal(swat.conservative_escape_probability,swat.records.filter((v:any)=>!v.censored&&!v.caught).length/200);
 const expected={false_takeoffs:r.summary.false_takeoffs_s<=.05,whole_circuit:r.summary.whole_rate_hz<50,resting_swat:swat.conservative_escape_probability>=protocol.safety.resting_swat_escape_min,replay:r.replay.status==='PASS',drive_parity:parity.presets[id]===true};
 assert.deepEqual(r.gates,expected);assert.equal(entry.offered,Object.values(expected).every(Boolean));
 for(const rate of r.bot.rates){const records=r.bot.records.filter((v:any)=>v.bot===rate.bot&&v.human===rate.human&&v.type===rate.type),resolved=records.filter((v:any)=>!v.censored);assert.equal(rate.n,resolved.length);assert.equal(rate.censored,records.length-resolved.length);assert.equal(rate.catch_rate,resolved.filter((v:any)=>v.caught).length/resolved.length);}
 if(entry.offered)offered++;
}
assert(offered>0,'No safety-passing presets are offered');
assert.equal(hash('profiles/game-v2.json'),hash('profiles/game-v2.7.json'));assert.equal(hash('apps/play/public/data/game.json'),hash('profiles/game-v2.7.json'));
const media=load('evidence/V2J/a02/media/manifest.json');
for(const [p,h] of Object.entries(media.source_hashes))assert.equal(hash(p),h,`Media source changed: ${p}`);
assert.equal(media.receipts.length,offered*2);
for(const receipt of media.receipts){assert(selection.presets[receipt.preset].offered);assert.equal(receipt.profile_sha256,selection.presets[receipt.preset].profile_sha256);assert.equal(receipt.duration_seconds,10);assert.equal(receipt.frames,200);assert.equal(receipt.neural_seed,1);assert.equal(receipt.environment_seed,1001);assert.equal(receipt.matches_authoritative_node,true);assert.equal(receipt.matches_reexecution,true);assert.deepEqual(receipt.external_requests,[]);assert.equal(hash('evidence/V2J/a02/media/'+receipt.file),receipt.video_sha256);}
console.log('PASS offered preset safety gates, declared C/D selection, raw bot denominators, preserved a01 FAIL and unchanged production profile:',offered,'presets');
