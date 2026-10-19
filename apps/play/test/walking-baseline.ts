import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {Game} from '../src/game.ts';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
const root=new URL('../../../',import.meta.url).pathname,load=(p:string)=>JSON.parse(readFileSync(root+'/'+p,'utf8'));
const runtime=load('apps/play/public/data/runtime.json'),profile=load('profiles/game-v2.7.json'),display=load('apps/play/public/data/display-v1.json');
const packed=gunzipSync(readFileSync(root+'/apps/play/public/data/circuit.flygraph.gz'));const buffer=unpackGraph(packed.buffer.slice(packed.byteOffset,packed.byteOffset+packed.byteLength));
const out=process.env.FLYBENCH_BASELINE_OUT??root+'/evidence/V2J/baseline';mkdirSync(out,{recursive:true});
const rows:any[]=[],strikes:any[]=[];const moving=(v:number[])=>Math.abs(v[1])>=.002||Math.abs(v[2])>=.0005;
const declaration={base_sha:'f7ee0eabd0b8efaf24e32f2f093164d526a35892',profile:profile.profile_id,neural_seeds:'1..20',environment_seeds:'1001..1020',no_threat_seconds:30,fly_length:display.fly_length_arena_units,moving_deadband:{speed:.002,turn:.0005},resting_strikes:'For each type and seed: two independent five-strike rounds with the same neural seed and environment seeds 1000+seed+round*100. Before each strike wait until grounded and 20 consecutive nonmoving intervals (at least 200 ms). Aim exactly at current position; holds 80,300,600 ms. Censor any strike not reached before round ends. Escape means neural onset before impact; physical miss reported separately.',bout_censoring:'first/last segments flagged; distributions reported separately for completed and all observed segments'};
writeFileSync(out+'/declaration.json',JSON.stringify(declaration,null,2));
const started=performance.now();
for(let seed=1;seed<=20;seed++){
 const g=new Game(buffer,runtime,profile,seed,1000+seed);let path=0,count=0,takeoffs=0,prev={x:0,y:0},wasAir=false,totalSpikes=0;const groups=runtime.config.groups.map((x:number[])=>new Set(x)),counts=groups.map(()=>0);let bout=0,prior=false;const segments:any[]=[];
 while(!g.done){const f=g.step();const m=moving(f.applied);if(m!==prior){if(bout)segments.push({moving:prior,ms:bout*10,left_censored:segments.length===0,right_censored:false});bout=0;prior=m;}bout++;count+=+m;path+=Math.hypot(f.body.x-prev.x,f.body.y-prev.y);prev=f.body;if(f.air&&!wasAir)takeoffs++;wasAir=f.air;for(const e of f.spikes)for(const i of e.indices){totalSpikes++;const id=Number(g.runner.state.graph.ids[i]);groups.forEach((s:Set<number>,j:number)=>{if(s.has(id))counts[j]++;});}}
 segments.push({moving:prior,ms:bout*10,left_censored:segments.length===0,right_censored:true});
 rows.push({seed,moving_fraction:count/3000,path_fly_lengths:path/display.fly_length_arena_units,net_fly_lengths:Math.hypot(prev.x,prev.y)/display.fly_length_arena_units,takeoffs,takeoffs_per_second:takeoffs/30,group_rates_hz:counts.map((n:number,i:number)=>n/groups[i].size/30),whole_rate_hz:totalSpikes/runtime.counts.N/30,segments});
 writeFileSync(out+'/quiet.json',JSON.stringify(rows,null,2));console.log('quiet',seed,rows.at(-1).moving_fraction,rows.at(-1).path_fly_lengths,'wall',((performance.now()-started)/1000).toFixed(1));
}
for(let type=0;type<3;type++)for(let seed=1;seed<=20;seed++)for(let round=0;round<2;round++){
 const g=new Game(buffer,runtime,profile,seed,1000+seed+100*round);
 for(let trial=0;trial<5;trial++){
  let rest=0;while(!g.done&&rest<20){const f=g.step();rest=!f.air&&!moving(f.applied)?rest+1:0;}
  if(g.done){strikes.push({type:profile.strikes[type].name,seed,round,trial,censored:true});continue;}
  const b=g.runner.body,tick=g.tick;g.apply({tick,x:b.x,y:b.y,hold_ms:[80,300,600][type]});while(g.strike&&!g.done)g.step();
  const impact=g.lastImpact;strikes.push({type:profile.strikes[type].name,seed,round,trial,censored:!impact,neural_escape:impact?.escape_onset_lead_ms!==null&&impact?.escape_onset_lead_ms>0,...impact});
 }
 writeFileSync(out+'/strikes.json',JSON.stringify(strikes,null,2));console.log('strikes',type,seed,round,'wall',((performance.now()-started)/1000).toFixed(1));
}
console.log('DONE');
