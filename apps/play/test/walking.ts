// Game-design measurements only. All actions use the authoritative Game loop.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {Game} from '../src/game.ts';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
const root=new URL('../../../',import.meta.url).pathname;
const load=(p:string)=>JSON.parse(readFileSync(root+p,'utf8'));
const runtime=load('apps/play/public/data/runtime.json'),old=load('profiles/game-v2.7.json'),draft=load('profiles/game-v2.8.json');
const packed=gunzipSync(readFileSync(root+'apps/play/public/data/circuit.flygraph.gz')),buffer=unpackGraph(packed.buffer.slice(packed.byteOffset,packed.byteOffset+packed.byteLength));
const out=root+'evidence/V2J/drive';mkdirSync(out,{recursive:true});
const mean=(xs:number[])=>xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null;
const median=(xs:number[])=>{const s=xs.slice().sort((a,b)=>a-b),n=s.length;return n?(s[Math.floor((n-1)/2)]+s[Math.floor(n/2)])/2:null;};
const moving=(v:number[])=>Math.abs(v[1])>=.002||Math.abs(v[2])>=.0005;
function quiet(profile:any,seed:number,seconds=30){
 const game=new Game(buffer,runtime,profile,seed,1000+seed),segments:any[]=[],cells=new Set<string>(),speeds:number[]=[],portCounts=runtime.config.groups.map(()=>0);
 const indexGroup=new Map<number,number>();runtime.config.groups.forEach((g:number[],k:number)=>g.forEach(id=>indexGroup.set(id,k)));
 const allowed=new Set<string>();for(let x=-3;x<=3;x++)for(let y=-3;y<=3;y++)if(Math.hypot(x*2,y*2)<=profile.arena_radius)allowed.add(x+','+y);
 let path=0,prior={x:0,y:0},moved=0,walked=0,wasAir=false,takeoffs=0,allSpikes=0,walk=false,duration=0,inputWalk=0;
 for(let n=0;n<seconds*100;n++){
  const f=game.step(),isWalking=!wasAir&&Math.abs(f.applied[1])>=.002;
  if(isWalking!==walk){if(duration)segments.push({walk,seconds:duration/100,left_censored:segments.length===0,right_censored:false});walk=isWalking;duration=0;}duration++;
  walked+=+isWalking;moved+=+moving(f.applied);if(isWalking)speeds.push(Math.abs(f.applied[1])*500);
  if((game.runner as any).walking?.walk)inputWalk++;
  path+=Math.hypot(f.body.x-prior.x,f.body.y-prior.y)/2;prior=f.body;
  if(f.air&&!wasAir)takeoffs++;wasAir=f.air;
  const cell=Math.floor(f.body.x/2+.5)+','+Math.floor(f.body.y/2+.5);if(!f.air&&allowed.has(cell))cells.add(cell);
  for(const e of f.spikes)for(const i of e.indices){allSpikes++;const group=indexGroup.get(Number(game.runner.state.graph.ids[i]));if(group!==undefined)portCounts[group]++;}
 }
 segments.push({walk,seconds:duration/100,left_censored:segments.length===0,right_censored:true});
 return {seed,environment_seed:1000+seed,seconds,moving_fraction:moved/(seconds*100),walking_fraction:walked/(seconds*100),input_walk_fraction:inputWalk/(seconds*100),path_fly_lengths:path,net_fly_lengths:Math.hypot(prior.x,prior.y)/2,takeoffs,false_takeoffs_s:takeoffs/seconds,whole_rate_hz:allSpikes/runtime.counts.N/seconds,group_rates_hz:portCounts.map((n:number,i:number)=>n/runtime.config.groups[i].length/seconds),coverage:cells.size/allowed.size,visited_cells:[...cells],eligible_cells:allowed.size,speeds,segments};
}
function bots(profile:any,seeds:number[],one=false){
 const records:any[]=[];
 for(const bot of [1,2])for(let type=0;type<3;type++)for(const seed of seeds){
  const game=new Game(buffer,runtime,profile,seed,1000+seed);
  for(let n=0;n<150;n++)game.step();
  for(let trial=0;trial<(one?1:6);trial++){
   if(trial)for(let n=0;n<100&&!game.done;n++)game.step();
   if(game.done){records.push({bot,type:profile.strikes[type].name,seed,trial,censored:true});continue;}
   const b=game.runner.body,fall=8/profile.strikes[type].speed;
   let x=b.x+(bot===2?b.heading_x*game.runner.held[1]*fall:0),y=b.y+(bot===2?b.heading_y*game.runner.held[1]*fall:0);
   const d=Math.hypot(x,y);if(d>profile.arena_radius){x*=profile.arena_radius/d*(1-Number.EPSILON);y*=profile.arena_radius/d*(1-Number.EPSILON);}
   game.apply({tick:game.tick,x,y,hold_ms:[80,300,600][type]});while(game.strike&&!game.done)game.step();records.push({bot,seed,trial,censored:false,...game.lastImpact});
  }
 }
 return {records,rates:[1,2].flatMap(bot=>profile.strikes.map((s:any)=>{const r=records.filter(v=>v.bot===bot&&v.type===s.name&&!v.censored);return {bot,type:s.name,n:r.length,catch_rate:mean(r.map(v=>+v.caught))};})),pooled:[1,2].map(bot=>mean(records.filter(v=>v.bot===bot&&!v.censored).map(v=>+v.caught)))};
}
function restingSwat(profile:any,seeds:number[],one=false){
 const records:any[]=[];
 for(const seed of seeds)for(let round=0;round<(one?1:2);round++){
  const g=new Game(buffer,runtime,profile,seed,1000+seed+round*100);
  for(let trial=0;trial<(one?1:5);trial++){
   let rest=0;while(!g.done&&rest<20){const f=g.step();rest=!f.air&&!moving(f.applied)?rest+1:0;}
   if(g.done){records.push({seed,round,trial,censored:true});continue;}
   const b=g.runner.body;g.apply({tick:g.tick,x:b.x,y:b.y,hold_ms:600});while(g.strike&&!g.done)g.step();records.push({seed,round,trial,censored:false,...g.lastImpact});
  }
 }
 return {records,censored:records.filter(v=>v.censored).length,escape_probability:mean(records.filter(v=>!v.censored).map(v=>+!v.caught))};
}
function summarize(rows:any[]){
 const segments=rows.flatMap(r=>r.segments).filter(s=>!s.left_censored&&!s.right_censored);
 return {median_walking_speed_fly_lengths_s:median(rows.flatMap(r=>r.speeds)),median_walk_bout_s:median(segments.filter(s=>s.walk).map(s=>s.seconds)),median_stop_bout_s:median(segments.filter(s=>!s.walk).map(s=>s.seconds)),walking_fraction:mean(rows.map(r=>r.walking_fraction)),moving_fraction:mean(rows.map(r=>r.moving_fraction)),input_walk_fraction:mean(rows.map(r=>r.input_walk_fraction)),mean_path_fly_lengths:mean(rows.map(r=>r.path_fly_lengths)),mean_net_fly_lengths:mean(rows.map(r=>r.net_fly_lengths)),mean_grid_coverage:mean(rows.map(r=>r.coverage)),false_takeoffs_s:mean(rows.map(r=>r.false_takeoffs_s)),whole_rate_hz:mean(rows.map(r=>r.whole_rate_hz))};
}
const grid:any[]=[];for(const forward of draft.walking_drive.grid.forward)for(const turn_sigma of draft.walking_drive.grid.turn_sigma)for(const walk_seconds of draft.walking_drive.grid.walk_seconds)for(const stop_seconds of draft.walking_drive.grid.stop_seconds)grid.push({forward,turn_sigma,walk_seconds,stop_seconds});
const command=process.argv[2],index=Number(process.argv[3]??0),dry=command==='--dry-run';
if(command==='--select'){
 const rows=grid.map((_,i)=>load(`evidence/V2J/drive/point-${i}.json`));
 const passing=rows.filter(r=>r.passes).sort((a,b)=>a.distance-b.distance||a.point.forward-b.point.forward||a.point.turn_sigma-b.point.turn_sigma||a.index-b.index);
 const selection={status:passing.length?'SELECTED_PENDING_VALIDATION':'TARGET_MISSED',rule:draft.walking_drive.selection,passing:passing.length,selected:passing[0]?.point??null,selected_index:passing[0]?.index??null,rows:rows.map(({quiet,bot,swat,...r})=>({...r,bot_rates:bot.rates,swat_escape:swat.escape_probability}))};writeFileSync(out+'/selection.json',JSON.stringify(selection,null,2)+'\n');console.log(JSON.stringify(selection));
}else{
 const baseline=command==='--before'||command==='--grid-before',validation=command==='--validate';
 const seeds=dry?[101]:command==='--before'||validation?draft.walking_drive.measurement.validation_seeds:draft.walking_drive.measurement.grid_seeds;
 const point=validation?load('evidence/V2J/drive/selection.json').selected:grid[index];
 if(validation&&!point)throw Error('No passing point to validate');
 const profile=baseline?old:{...draft,walking_drive:{...draft.walking_drive,selected:point}};
 const rows=seeds.map(seed=>quiet(profile,seed,dry?1:30));console.log('quiet complete',index);
 const bot=bots(profile,seeds,dry),swat=restingSwat(profile,seeds,dry),summary=summarize(rows),t=draft.walking_drive.targets;
 const reference=baseline||dry?swat.escape_probability:load(validation?'evidence/V2J/drive/before.json':'evidence/V2J/drive/grid-before.json').swat.escape_probability;
 const between=(v:number|null,r:number[])=>v!==null&&v>=r[0]&&v<=r[1];
 const flags:any={};for(const k of ['median_walking_speed_fly_lengths_s','median_walk_bout_s','median_stop_bout_s','walking_fraction'])flags[k]=between((summary as any)[k],t[k]);
 Object.assign(flags,{coverage:summary.mean_grid_coverage!>=t.mean_grid_coverage_min,false_takeoffs:summary.false_takeoffs_s!<=t.false_takeoffs_s_max,rate:summary.whole_rate_hz!<t.whole_rate_hz_max_exclusive,swat:swat.censored===0&&swat.escape_probability!>=reference,bot1:between(bot.pooled[0],t.bot1_catch),bot2:between(bot.pooled[1],t.bot2_catch)});
 const values=[summary.median_walking_speed_fly_lengths_s,summary.median_walk_bout_s,summary.median_stop_bout_s,summary.walking_fraction,summary.mean_grid_coverage,...bot.pooled],centers=[2.25,1.25,.9,.55,1,.275,.45],scales=[.75,.75,.6,.15,.5,.075,.10];
 const distance=values.some(v=>v===null)?null:values.reduce((s:number,v,i)=>s+((v!-centers[i])/scales[i])**2,0);
 const result={sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),index,point:baseline?null:point,seeds,classification:dry?'DRY_RUN_NOT_SELECTION_EVIDENCE':'GAME_DESIGN_NOT_SCIENCE',summary,bot,swat,flags,passes:Object.values(flags).every(Boolean),distance,quiet:rows};
 const name=dry?'dry-run':command==='--grid-before'?'grid-before':baseline?'before':validation?'validation':`point-${index}`;
 writeFileSync(out+'/'+name+'.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({name,summary,bot:bot.pooled,swat:swat.escape_probability,flags}));
}
