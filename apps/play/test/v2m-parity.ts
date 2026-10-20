import assert from 'node:assert/strict';
import {writeFileSync,readFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {preset,protocol} from './v2m.ts';
import {root,buffer,newGame,sha,load} from './owner-walking.ts';
import {WalkingDrive} from '../src/walking-drive.ts';
const out=root+'evidence/V2M/parity';mkdirSync(out,{recursive:true});
const temp=mkdtempSync('/tmp/flybench-v2m-parity-'),graph=temp+'/graph.webbin';writeFileSync(graph,Buffer.from(buffer));
const bits=(xs:number[])=>{const b=Buffer.alloc(xs.length*8);xs.forEach((x,i)=>b.writeDoubleLE(x,i*8));return b.toString('hex');};
const profiles=Object.fromEntries(Object.keys(protocol.presets).map(id=>[id,preset(id)])),results:any={};
writeFileSync(out+'/profiles.json',JSON.stringify(profiles));
execFileSync(root+'.venv/bin/python',['tests/owner_walking_reference.py',out+'/profiles.json',out+'/drive.json.gz'],{cwd:root,stdio:'inherit'});
for(const row of JSON.parse(gunzipSync(readFileSync(out+'/drive.json.gz')).toString())){
 const drive=new WalkingDrive(row.seed,row.point);
 for(const expected of row.intervals)assert.equal(bits([...drive.next(),...drive.snapshot()]),expected);
 drive.reset();assert.equal(bits([...drive.next(),...drive.snapshot()]),row.intervals[0]);
}
for(const [id,p] of Object.entries(profiles)){
 writeFileSync(temp+'/profile.json',JSON.stringify(p));
 execFileSync(root+'.venv/bin/python',['tests/v2l_reference.py',graph,out+`/${id}.json.gz`,temp+'/profile.json'],{cwd:root,stdio:'inherit'});
 const rows=JSON.parse(gunzipSync(readFileSync(out+`/${id}.json.gz`)).toString());let air=0,reflections=0;
 for(const row of rows){
  const g=newGame(p,row.seed);
  for(let i=0;i<row.intervals.length;i++){
   if([150,500,800].includes(i)){const b=g.runner.body;g.apply({tick:g.tick,x:b.x,y:b.y,hold_ms:[600,299.999,300][[150,500,800].indexOf(i)]});}
   const before=g.airDirection.slice(),f=g.step(),r=row.intervals[i],b=f.body,counts=new Uint32Array(g.runner.state.graph.header.N);
   assert.equal(bits([b.x,b.y,b.heading_x,b.heading_y,...f.applied.map(Number),...g.runner.held.map(Number),...(g.runner as any).walking.snapshot(),...g.airDirection,g.airUntil]),r.bits,`${id} seed ${row.seed} interval ${i}`);
   f.spikes.forEach(e=>e.indices.forEach(j=>counts[j]++));assert.equal(createHash('sha256').update(new Uint8Array(counts.buffer)).digest('hex'),r.counts_sha256);
   assert.equal(f.air,r.air);assert.equal(f.onset,r.onset);if(f.impact)assert.deepEqual({tick:f.impact.tick,caught:f.impact.caught,type:f.impact.type,position:f.impact.position},r.impact);
   if(f.air)air++;if(!f.onset&&JSON.stringify(before)!==JSON.stringify(g.airDirection))reflections++;
  }
 }assert(air&&reflections);results[id]={profile_sha256:sha(p),bit_exact:true,air_intervals:air,reflections};
}
writeFileSync(out+'/summary.json',JSON.stringify({status:'PASS',code_sha:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),drive:{seeds:5,intervals:3000,reset:true},presets:results},null,2)+'\n');
console.log('PASS all four presets: Python/TypeScript body, held command, drive, spikes and reflection parity');
