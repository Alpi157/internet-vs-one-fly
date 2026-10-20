import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {Game,replayLog} from '../src/game.ts';
import {root,load,buffer,runtime} from './owner-walking.ts';
const out=root+'evidence/V2L/parity';mkdirSync(out,{recursive:true});
const profile=load('profiles/game-v2.9.json'),old=load('profiles/game-v2.8.json');
const bits=(xs:number[])=>{const b=Buffer.alloc(xs.length*8);xs.forEach((v,i)=>b.writeDoubleLE(v,i*8));return b.toString('hex');};
const temp=mkdtempSync('/tmp/flybench-v2l-parity-')+'/graph.webbin';writeFileSync(temp,Buffer.from(buffer));
execFileSync(root+'.venv/bin/python',['tests/v2l_reference.py',temp,out+'/python.json.gz'],{cwd:root,stdio:'inherit'});
const rows=JSON.parse(gunzipSync(readFileSync(out+'/python.json.gz')).toString());
let reflections=0,airIntervals=0;
for(const row of rows){
 const g=new Game(buffer,runtime,profile,row.seed,1000+row.seed);
 for(let i=0;i<row.intervals.length;i++){
  if([150,500,800].includes(i)){const b=g.runner.body;g.apply({tick:g.tick,x:b.x,y:b.y,hold_ms:[600,299.999,300][[150,500,800].indexOf(i)]});}
  const previous=g.airDirection.slice(),f=g.step(),r=row.intervals[i],b=f.body;
  assert.equal(bits([b.x,b.y,b.heading_x,b.heading_y,...f.applied.map(Number),...g.runner.held.map(Number),...(g.runner as any).walking.snapshot(),...g.airDirection,g.airUntil]),r.bits,`seed ${row.seed} interval ${i}`);
  const counts=new Uint32Array(runtime.counts.N);f.spikes.forEach(e=>e.indices.forEach(j=>counts[j]++));assert.equal(createHash('sha256').update(new Uint8Array(counts.buffer)).digest('hex'),r.counts_sha256);
  assert.equal(f.air,r.air);assert.equal(f.onset,r.onset);
  if(f.impact)assert.deepEqual({tick:f.impact.tick,caught:f.impact.caught,type:f.impact.type,position:f.impact.position},r.impact);
  if(f.air)airIntervals++;if(!f.onset&&JSON.stringify(previous)!==JSON.stringify(g.airDirection))reflections++;
 }
 assert((await replayLog(buffer,runtime,profile,await g.log())).matches);
}
assert(reflections>0,'Fixture must cover circle reflection');assert(airIntervals>0);
for(const [hold,name] of [[0,'flick'],[299.999,'flick'],[300,'swat'],[600,'swat']] as const){const g=new Game(buffer,runtime,profile,1,2);g.apply({tick:0,x:0,y:0,hold_ms:hold});assert.equal(g.strike.name,name);}
const a=new Game(buffer,runtime,old,1,8128),b=new Game(buffer,runtime,profile,1,8128);
for(const g of [a,b])g.apply({tick:0,x:0,y:0,hold_ms:600});
let first:number|undefined;
while(first===undefined||b.tick<first+240){const x=a.step(),y=b.step();assert.deepEqual(x.body,y.body,'First 120 ms of actual takeoff unchanged');assert.deepEqual(x.spikes,y.spikes);if(y.onset&&first===undefined)first=y.tick;}
const log=await b.log();assert.equal(log.schema,'flybench.game-round.v4');await assert.rejects(()=>replayLog(buffer,runtime,profile,{...log,schema:'flybench.game-round.v3'}),/Unsupported replay schema/);await assert.rejects(()=>replayLog(buffer,runtime,old,log),/Unsupported replay schema/);
writeFileSync(out+'/summary.json',JSON.stringify({status:'PASS',code_sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),seeds:rows.map((r:any)=>r.seed),intervals:rows.reduce((n:number,r:any)=>n+r.intervals.length,0),bit_exact_body_command_drive:true,recorded_spike_counts:true,airIntervals,reflections,first_120_ms_unchanged:true,schema4:true},null,2)+'\n');
console.log('PASS Python/TypeScript game-loop parity, reflections, spikes, replay, 300 ms boundary, first 120 ms and schema rejection');
