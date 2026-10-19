import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
const root=new URL('../public/data/',import.meta.url),dir=new URL('coupling/',root);
const packed=gunzipSync(readFileSync(new URL('circuit.flygraph.gz',dir)));
const original=unpackGraph(Uint8Array.from(packed).buffer);
const runtime=JSON.parse(readFileSync(new URL('runtime.json',dir),'utf8'));
const profile=JSON.parse(readFileSync(new URL('game.json',root),'utf8'));
const strength=JSON.parse(readFileSync(new URL('strength-demo.json',dir),'utf8'));
let messages:any[]=[];
const selfStub={postMessage(m:any){messages.push(m);},onmessage:null as any};
Object.assign(globalThis,{self:selfStub});
await import('../src/coupling-worker.ts');
for(const [family,file,identity] of [['N-SIGN','targets.json.gz',runtime.lab_identity],['N-STRENGTH','strength-targets.json.gz',strength.target_sha256]]){
 const targets=JSON.parse(gunzipSync(readFileSync(new URL(file,dir))).toString());
 const bytes=Buffer.alloc(targets.length*4);targets.forEach((v:number,i:number)=>bytes.writeInt32LE(v,i*4));
 assert.equal(createHash('sha256').update(bytes).digest('hex'),identity);
 const config=structuredClone(runtime);config.lab_identity=identity;messages=[];
 selfStub.onmessage({data:{kind:'init',buffer:original.slice(0),runtime:config,profile,targets,s:.039,generation:1}});
 const deadline=performance.now()+10000;
 while(!messages.some(m=>m.kind==='frame'||m.kind==='error')&&performance.now()<deadline)await new Promise(r=>setTimeout(r,5));
 selfStub.onmessage({data:{kind:'pause'}});
 assert(!messages.some(m=>m.kind==='error'),JSON.stringify(messages));
 const frame=messages.find(m=>m.kind==='frame');assert(frame, family+' did not execute through coupling worker');
 for(const panel of frame.panels){
  assert.deepEqual(panel.frames.map((f:any)=>f.tick),[20,40,60,80,100]);
  const observed=new Uint32Array(panel.counts.length);
  for(const f of panel.frames)for(const event of f.spikes)for(const i of event.indices)observed[i]++;
  assert.deepEqual(Array.from(observed),Array.from(panel.counts));
 }
 const first=JSON.stringify(frame.panels);
 messages=[];selfStub.onmessage({data:{kind:'scale',s:.039,generation:2}});
 while(!messages.some(m=>m.kind==='frame'||m.kind==='error')&&performance.now()<deadline)await new Promise(r=>setTimeout(r,5));
 selfStub.onmessage({data:{kind:'pause'}});
 assert.equal(JSON.stringify(messages.find(m=>m.kind==='frame').panels),first,'Reset repeats the same recorded sequence');
 assert.equal(frame.panels.length,2);assert(frame.panels.every((p:any)=>p.tick===100&&Number.isFinite(p.rate)&&p.counts.length===2641));
 console.log('PASS:',family,'loaded, target hash matches, existing coupling worker executes both circuits');
}
