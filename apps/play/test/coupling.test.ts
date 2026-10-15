import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
import {RunnerV2} from '../../../packages/kernel-ts/src/runner.ts';
import {readGraph} from '../../../packages/kernel-ts/src/kernel.ts';
const dir=new URL('../public/data/coupling/',import.meta.url);
const packed=gunzipSync(readFileSync(new URL('circuit.flygraph.gz',dir)));
const original=unpackGraph(packed.buffer.slice(packed.byteOffset,packed.byteOffset+packed.byteLength));
const targets=JSON.parse(gunzipSync(readFileSync(new URL('targets.json.gz',dir))).toString());
const runtime=JSON.parse(readFileSync(new URL('runtime.json',dir),'utf8'));
const cases=JSON.parse(readFileSync(new URL('parity.json',dir),'utf8')).cases;
for(const c of cases){
 const buffer=original.slice(0),graph=readGraph(buffer);if(c.family==='N-SIGN')graph.targets.set(targets);
 const config=structuredClone(runtime.config);config.model.runtime_synaptic_scale=c.s;config.noise.seed=2027101401;
 const runner=new RunnerV2(graph,config);let count=0;
 for(let i=0;i<c.intervals;i++){const value=runner.step({active:false,aim_x:0,aim_y:0,elapsed_ms:0,downward_speed_per_ms:0});count+=value.recordedSpikes.reduce((n,e)=>n+e.indices.length,0);}
 assert.equal(count,c.total_spikes);assert.equal(await runner.digest(),c.final_digest);
}
console.log('PASS coupling: Python/Node no-threat digests and recorded spike counts, both graphs at all three couplings');
