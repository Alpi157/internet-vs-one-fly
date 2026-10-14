import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
import {readGraph} from '../../../packages/kernel-ts/src/kernel.ts';
import {configureLab} from '../src/lab.ts';
import {Game} from '../src/game.ts';
const data=new URL('../public/data/',import.meta.url),raw=gunzipSync(readFileSync(new URL('circuit.flygraph.gz',data)));
const buffer=unpackGraph(raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength));
const runtime=JSON.parse(readFileSync(new URL('runtime.json',data),'utf8')),profile=JSON.parse(readFileSync(new URL('game.json',data),'utf8'));
const digest=(v:ArrayBuffer)=>createHash('sha256').update(new Uint8Array(v)).digest('hex');
assert.equal(digest(buffer),runtime.transport.unpacked_sha256);
const graph=readGraph(buffer),original=digest(buffer);
for(const mode of ['LC4','LPLC2','giant-fiber','turning-DN']){
 const lab=await configureLab(mode,buffer,runtime,'');
 const removed=mode==='LC4'||mode==='LPLC2'?Object.entries(runtime.config.visual).filter(([key])=>key.startsWith(mode+'_')).flatMap(([,values])=>values as number[]):Array.from(graph.ids).flatMap((id,i)=>(mode==='giant-fiber'?runtime.config.groups.slice(0,2):runtime.config.groups.slice(3,5)).flat().includes(Number(id))?[i]:[]);
 const game=new Game(lab.buffer,lab.runtime,profile,2026092802,8128);game.apply({tick:0,x:0,y:0,hold_ms:600});
 for(let i=0;i<52;i++){const frame=game.step();assert(!frame.spikes.some(e=>e.indices.some(j=>removed.includes(j))));}
 assert.equal(digest(buffer),original);
}
console.log('PASS lossless transport, four executable lesions, isolated mutable state');
