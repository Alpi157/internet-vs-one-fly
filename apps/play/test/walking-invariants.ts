import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {Game,replayLog} from '../src/game.ts';
import {GameRunner} from '../src/game-runner.ts';
const root=new URL('../../../',import.meta.url),load=(p:string)=>JSON.parse(readFileSync(new URL(p,root),'utf8'));
const packed=gunzipSync(readFileSync(new URL('apps/play/public/data/circuit.flygraph.gz',root)));
const {unpackGraph}=await import('../../../packages/kernel-ts/src/transport.ts');
const buffer=unpackGraph(packed.buffer.slice(packed.byteOffset,packed.byteOffset+packed.byteLength));
const runtime=load('apps/play/public/data/runtime.json'),profile=load('profiles/game-v2.8.json'),old=load('profiles/game-v2.7.json');
profile.walking_drive.selected={forward:1.5,turn_sigma:.5,walk_seconds:1,stop_seconds:.6};
const quiet=new Game(buffer,runtime,profile,1,1001),threat=new Game(buffer,runtime,profile,1,1001);
assert(quiet.runner instanceof GameRunner&&threat.runner instanceof GameRunner);
threat.apply({tick:0,x:0,y:0,hold_ms:600});
for(let n=0;n<100;n++){quiet.step();threat.step();assert.deepEqual(quiet.runner.walking.snapshot(),threat.runner.walking.snapshot(),'Hand cannot affect the dedicated drive stream');}
const log=await threat.log();assert.equal(log.schema,'flybench.game-round.v3');assert((await replayLog(buffer,runtime,profile,log)).matches);
await assert.rejects(()=>replayLog(buffer,runtime,profile,{...log,schema:'flybench.game-round.v2'}),/Unsupported replay schema/);
for(const mode of ['LC4','LPLC2','giant-fiber','turning-DN','scramble']){
 const labRuntime={...runtime,profile_hashes:{...runtime.profile_hashes,lab_mode:mode}};
 const current=new Game(buffer,labRuntime,profile,1,2),previous=new Game(buffer,labRuntime,old,1,2);
 assert(!(current.runner instanceof GameRunner),'Lab has no walking drive');
 for(let n=0;n<20;n++)assert.deepEqual(current.step(),previous.step());
}
const clamped=new Game(buffer,{...runtime,config:{...runtime.config,output_clamp:true}},profile,1,1001);
for(let n=0;n<100;n++)clamped.step();assert.deepEqual(clamped.runner.body,{x:0,y:0,heading_x:1,heading_y:0});
assert(clamped.frames.some(f=>f.spikes.length),'Current generates recorded spikes even with movement clamped');
console.log('PASS drive/hand independence, exact replay, schema rejection, unchanged lab, and output-clamp causality');
