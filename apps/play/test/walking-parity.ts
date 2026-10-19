import assert from 'node:assert/strict';
import {readFileSync,mkdirSync,writeFileSync,mkdtempSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {gunzipSync} from 'node:zlib';
import {WalkingDrive} from '../src/walking-drive.ts';
import {GameRunner} from '../src/game-runner.ts';
import {readGraph} from '../../../packages/kernel-ts/src/kernel.ts';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
const root=new URL('../../../',import.meta.url).pathname,out=process.env.FLYBENCH_WALKING_PARITY_OUT??root+'evidence/V2J/parity';mkdirSync(out,{recursive:true});
const packed=gunzipSync(readFileSync(root+'apps/play/public/data/circuit.flygraph.gz')),buffer=unpackGraph(packed.buffer.slice(packed.byteOffset,packed.byteOffset+packed.byteLength));
const graphPath=mkdtempSync('/tmp/flybench-v2j-parity-')+'/circuit.webbin';writeFileSync(graphPath,Buffer.from(buffer));
execFileSync(root+'.venv/bin/python',['tests/walking_reference.py',out,graphPath],{cwd:root,stdio:'inherit'});
const vectors=JSON.parse(readFileSync(out+'/reference.json','utf8'));
const bits=(x:number[])=>{const b=Buffer.alloc(x.length*8);x.forEach((v,i)=>b.writeDoubleLE(v,i*8));return b.toString('hex');};
for(const v of vectors.drives){const d=new WalkingDrive(v.environment_seed,v.point);for(const expected of v.intervals)assert.equal(bits([...d.next(),...d.snapshot()]),expected);d.reset();assert.equal(bits([...d.next(),...d.snapshot()]),v.intervals[0]);}
const runtime=JSON.parse(readFileSync(root+'apps/play/public/data/runtime.json','utf8'));
const runner=new GameRunner(readGraph(buffer),{...runtime.config,noise:{...runtime.config.noise,seed:77}},88,vectors.point);
for(const row of vectors.neural){
 const value=runner.step(row.strike);assert.equal(await runner.digest(),row.digest);assert.equal(bits([...runner.walking.snapshot(),...value.command.map(Number)]),row.bits);
 const counts=Array(runner.state.graph.header.N).fill(0);value.recordedSpikes.forEach(e=>e.indices.forEach(i=>counts[i]++));assert.deepEqual(counts,row.counts);
}
runner.reset();assert.equal(runner.state.tick,0);assert.deepEqual(runner.walking.snapshot(),new WalkingDrive(88,vectors.point).snapshot());
console.log('PASS bit-exact Python/TypeScript drive, reset, neural states, commands and recorded counts:',vectors.drives.length,'seeds x 3000 drive intervals;',vectors.neural.length,'T1b neural intervals');
