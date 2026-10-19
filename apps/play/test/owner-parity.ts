import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {gunzipSync} from 'node:zlib';
import {WalkingDrive} from '../src/walking-drive.ts';
import {root,out,load,profileFor,sha} from './owner-walking.ts';
const profiles:any={};for(const id of ['A','B','C','D']){
 const f=id==='D'?load('evidence/V2J/a02/selection/D.json').selected:undefined,s=id==='C'?load('evidence/V2J/a02/selection/C.json').selected:undefined;
 if(f!==null&&s!==null)profiles[id]=profileFor(id,f,s);
}
mkdirSync(out+'/parity',{recursive:true});writeFileSync(out+'/parity/profiles.json',JSON.stringify(profiles));
execFileSync(root+'.venv/bin/python',['tests/owner_walking_reference.py',out+'/parity/profiles.json',out+'/parity/reference.json.gz'],{cwd:root,stdio:'inherit'});
const rows=JSON.parse(gunzipSync(readFileSync(out+'/parity/reference.json.gz')).toString());
const bits=(v:number[])=>{const b=Buffer.alloc(v.length*8);v.forEach((x,i)=>b.writeDoubleLE(x,i*8));return b.toString('hex');};
for(const r of rows){const drive=new WalkingDrive(r.seed,r.point);for(const expected of r.intervals)assert.equal(bits([...drive.next(),...drive.snapshot()]),expected,`${r.preset} seed ${r.seed}`);drive.reset();assert.equal(bits([...drive.next(),...drive.snapshot()]),r.intervals[0]);}
writeFileSync(out+'/parity/summary.json',JSON.stringify({status:'PASS',presets:Object.fromEntries(Object.keys(profiles).map(k=>[k,true])),seeds:5,intervals:3000,profile_hashes:Object.fromEntries(Object.entries(profiles).map(([k,v])=>[k,sha(v)])),reference_bytes:readFileSync(out+'/parity/reference.json.gz').length},null,2)+'\n');
console.log('PASS bit-exact a02 Python/TypeScript currents, state and reset:',Object.keys(profiles).join(', '),'x 5 seeds x 3000 intervals');
