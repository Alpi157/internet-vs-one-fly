import {readFileSync,writeFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
import {Game} from '../src/game.ts';
const data=new URL('../public/data/',import.meta.url),packed=gunzipSync(readFileSync(new URL('circuit.flygraph.gz',data)));
const buffer=unpackGraph(packed.buffer.slice(packed.byteOffset,packed.byteOffset+packed.byteLength));
const runtime=JSON.parse(readFileSync(new URL('runtime.json',data),'utf8')),profile=JSON.parse(readFileSync(process.env.FLYBENCH_PERF_PROFILE ?? new URL('game.json',data),'utf8'));
const game=new Game(buffer,runtime,profile,2026092802,8128);
const start=performance.now();
for(let i=0;i<1000;i++){if(i===100||i===400)game.apply({tick:game.tick,x:0,y:0,hold_ms:300});game.step();}
const wall=(performance.now()-start)/1000;
const report={scope:'selected graph, 10 simulated seconds, two standard scripted strikes, no per-interval hashing',parameters:runtime.parameters,wall_seconds:wall,wall_seconds_per_simulated_second:wall/10,digest:await game.digest()};
writeFileSync(new URL('../../../evidence/V2E/game/performance-'+(process.env.FLYBENCH_PHASE??'before')+'.json',import.meta.url),JSON.stringify(report,null,2)+'\n');console.log(report);
