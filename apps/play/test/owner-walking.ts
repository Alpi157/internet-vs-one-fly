// a02 game design measurements. No scientific model or a01 evidence is modified.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {Game,replayLog} from '../src/game.ts';
import {u32} from '../../../packages/kernel-ts/src/kernel.ts';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
export const root=new URL('../../../',import.meta.url).pathname;
export const load=(p:string)=>JSON.parse(readFileSync(root+p,'utf8'));
export const protocol=load('profiles/owner-walking-a02.json'),runtime=load('apps/play/public/data/runtime.json'),old=load('profiles/game-v2.7.json');
const packed=gunzipSync(readFileSync(root+'apps/play/public/data/circuit.flygraph.gz'));
export const buffer=unpackGraph(packed.buffer.slice(packed.byteOffset,packed.byteOffset+packed.byteLength));
export const out=root+'evidence/V2J/a02';
export const mean=(v:number[])=>v.length?v.reduce((a,b)=>a+b,0)/v.length:null;
export const median=(v:number[])=>{const s=v.slice().sort((a,b)=>a-b),n=s.length;return n?(s[Math.floor((n-1)/2)]+s[Math.floor(n/2)])/2:null;};
export const sha=(v:any)=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
export function save(path:string,data:any){mkdirSync(out+'/'+path.split('/').slice(0,-1).join('/'),{recursive:true});writeFileSync(out+'/'+path,JSON.stringify(data,null,2)+'\n');}
export function profileFor(id:string,forward?:number,takeoffSpeed?:number){
 const entry=protocol.presets[id],b=id==='C'?protocol.presets.B:entry;
 const drive={...b.drive,...(forward===undefined?{}:{forward})};
 if(drive.forward===null)throw Error('Unresolved D');
 return {...structuredClone(old),profile_id:`flybench.game.v2.8.owner-a02.${id}`,version:8,
  walking_drive:{...load('profiles/walking-grid-v1.json'),grid:undefined,targets:undefined,selection:undefined,measurement:undefined,selected:drive,copy:protocol.copy},
  takeoff_speed:takeoffSpeed??entry.takeoff_speed,owner_preset:{id,name:entry.name,production:false},
  physics_disclosure:id==='C'?entry.physics_disclosure:'Takeoff speed and all body rules as in v2.7.'};
}
export function identityRuntime(profile:any){return {...structuredClone(runtime),profile_hashes:{...runtime.profile_hashes,owner_playtest_profile:sha(profile)}};}
export function newGame(profile:any,seed:number,environmentSeed=1000+seed){return new Game(buffer,identityRuntime(profile),profile,seed,environmentSeed);}
function segments(flags:(boolean|null)[]){
 const result:any[]=[];let start=0,prior=flags[0];
 for(let i=1;i<=flags.length;i++)if(i===flags.length||flags[i]!==prior){
  if(prior!==null)result.push({walk:prior,seconds:(i-start)/100,left_censored:start===0||flags[start-1]===null,right_censored:i===flags.length||flags[i]===null});
  start=i;prior=flags[i];
 }
 return result;
}
export function pathMetrics(trace:any[]){
 const visible:(boolean|null)[]=[],decoded:(boolean|null)[]=[],visibleSpeeds:number[]=[],decodedSpeeds:number[]=[];
 let prior={x:0,y:0},priorAir=false,path=0,airCount=0,takeoffs=0;
 const cells=new Set<string>(),allowed=new Set<string>();
 for(let x=-3;x<=3;x++)for(let y=-3;y<=3;y++)if(Math.hypot(x*2,y*2)<=old.arena_radius)allowed.add(x+','+y);
 const points=[{x:0,y:0,air:false},...trace.map(f=>({...f.body,air:f.air}))];
 for(let i=0;i<trace.length;i++){
  const f=trace[i];path+=Math.hypot(f.body.x-prior.x,f.body.y-prior.y)/2;prior=f.body;
  if(f.air&&!priorAir)takeoffs++;
  const d=!priorAir&&Math.abs(f.applied[1])>=.002;decoded.push(d);if(d)decodedSpeeds.push(Math.abs(f.applied[1])*500);
  const cell=Math.floor(f.body.x/2+.5)+','+Math.floor(f.body.y/2+.5);if(!f.air&&allowed.has(cell))cells.add(cell);
  // d/dt of trailing 200 ms mean position. Twenty 10 ms displacements.
  airCount+=+(f.air||priorAir);if(i>=20)airCount-=+(trace[i-20].air||(i===20?false:trace[i-21].air));
  if(i>=19&&airCount===0){const a=points[i+1],b=points[i-19],speed=Math.hypot(a.x-b.x,a.y-b.y)/.2/2;const walk=speed>.5;visible.push(walk);if(walk)visibleSpeeds.push(speed);}else visible.push(null);
  priorAir=f.air;
 }
 return {visible:{speeds:visibleSpeeds,speed:median(visibleSpeeds),fraction:visible.filter(v=>v===true).length/trace.length,eligible_intervals:visible.filter(v=>v!==null).length,segments:segments(visible)},decoded:{speeds:decodedSpeeds,speed:median(decodedSpeeds),fraction:decoded.filter(Boolean).length/trace.length,segments:segments(decoded)},takeoffs,path_fly_lengths:path,net_fly_lengths:Math.hypot(prior.x,prior.y)/2,coverage:cells.size/allowed.size,visited_cells:[...cells],eligible_cells:allowed.size};
}
export async function quiet(profile:any,seed:number,seconds=30){
 const g=newGame(profile,seed),trace:any[]=[];let spikes=0;
 while(g.tick<seconds*2000){const f=g.step();spikes+=f.spikes.reduce((n,e)=>n+e.indices.length,0);trace.push({tick:f.tick,body:f.body,air:f.air,applied:f.applied});}
 if(g.tick!==seconds*2000||trace.length!==seconds*100)throw Error('Quiet clock/interval mismatch');
 return {seed,environment_seed:1000+seed,seconds,whole_rate_hz:spikes/runtime.counts.N/seconds,...pathMetrics(trace),trace,log:await g.log()};
}
export function summarize(rows:any[]){
 const metric=(key:string)=>{const all=rows.flatMap(r=>r[key].segments).filter(s=>!s.left_censored&&!s.right_censored);return {median_speed_fly_lengths_s:median(rows.flatMap(r=>r[key].speeds)),median_bout_s:median(all.filter(s=>s.walk).map(s=>s.seconds)),median_stop_s:median(all.filter(s=>!s.walk).map(s=>s.seconds)),walking_fraction:mean(rows.map(r=>r[key].fraction)),median_seed_speed_fly_lengths_s:median(rows.map(r=>r[key].speed).filter(v=>v!==null))};};
 // Completed visible and decoded segments are pooled across the fixed rounds.
 return {visible:metric('visible'),decoded:metric('decoded'),mean_path_fly_lengths:mean(rows.map(r=>r.path_fly_lengths)),mean_net_fly_lengths:mean(rows.map(r=>r.net_fly_lengths)),coverage:mean(rows.map(r=>r.coverage)),false_takeoffs_s:rows.reduce((n,r)=>n+r.takeoffs,0)/rows.reduce((n,r)=>n+r.seconds,0),whole_rate_hz:mean(rows.map(r=>r.whole_rate_hz))};
}
export function project(x:number,y:number,radius:number){const d=Math.hypot(x,y);if(d>radius){x*=radius/d*(1-Number.EPSILON);y*=radius/d*(1-Number.EPSILON);}while(Math.hypot(x,y)>radius){x*=1-2*Number.EPSILON;y*=1-2*Number.EPSILON;}return {x,y};}
export function botRound(profile:any,seed:number,bot:number,type:number,human:boolean,opportunities=6,endMs=30000){
 const g=newGame(profile,seed),records:any[]=[];let still=0,previous={x:0,y:0},previousAir=false;
 const step=()=>{const f=g.step(),speed=Math.hypot(f.body.x-previous.x,f.body.y-previous.y)/.01/2;still=!f.air&&!previousAir&&speed<=.5?still+1:0;previous=f.body;previousAir=f.air;return f;};
 const advance=(n:number)=>{for(let i=0;i<n&&!g.done&&g.tick<endMs*2;i++)step();};
 advance(150);
 for(let trial=0;trial<opportunities;trial++){
  if(trial)advance(100);
  if(bot===4)while(!g.done&&g.tick<endMs*2&&still<15)step();
  if(g.done||g.tick>=endMs*2){records.push({bot,human,type:profile.strikes[type].name,seed,trial,censored:true,reason:'No eligible opportunity within round'});continue;}
  const b={...g.runner.body},observed_tick=g.tick,held=g.runner.held[1],fall=8/profile.strikes[type].speed;
  let x=b.x+(bot===2?b.heading_x*held*fall:0),y=b.y+(bot===2?b.heading_y*held*fall:0);
  const still_ms=still*10;
  if(human){advance(20);x+=(u32(seed,71,trial,0)/2**32*2-1)*.3;y+=(u32(seed,71,trial,1)/2**32*2-1)*.3;}
  if(g.done||g.tick+Math.round(fall*2)>Math.min(endMs*2,profile.round_ms*2)){records.push({bot,human,type:profile.strikes[type].name,seed,trial,censored:true,reason:'Reaction or impact exceeds round'});continue;}
  const aim=project(x,y,profile.arena_radius);g.apply({tick:g.tick,...aim,hold_ms:[80,300,600][type]});
  while(g.strike&&!g.done&&g.tick<endMs*2)step();
  records.push({bot,human,seed,trial,observed_tick,observed_body:b,observed_forward:held,still_ms,censored:!g.lastImpact,...g.lastImpact});
 }
 return {game:g,records};
}
export function bots(profile:any,seeds:number[],one=false,onlyBot?:number,onlyType?:number,onlyHuman?:boolean){
 const records:any[]=[];
 for(const bot of onlyBot?[onlyBot]:[1,2,4])for(const human of onlyHuman===undefined?[false,true]:[onlyHuman])for(const type of onlyType===undefined?[0,1,2]:[onlyType])for(const seed of seeds)records.push(...botRound(profile,seed,bot,type,human,one?1:6).records);
 const rates=[1,2,4].flatMap(bot=>[false,true].flatMap(human=>profile.strikes.map((s:any)=>{const all=records.filter(r=>r.bot===bot&&r.human===human&&r.type===s.name),r=all.filter(v=>!v.censored);return {bot,human,type:s.name,n:r.length,censored:all.length-r.length,catches:r.filter(v=>v.caught).length,catch_rate:mean(r.map(v=>+v.caught))};}))).filter(r=>r.n||r.censored);
 return {records,rates};
}
export function restingSwat(profile:any,seeds:number[],trials=10){
 const records:any[]=[];for(const seed of seeds)for(let trial=0;trial<trials;trial++){
  const g=newGame(profile,seed,1000+seed+100*trial);let rest=0;
  while(!g.done&&rest<20){const f=g.step();rest=!f.air&&Math.abs(f.applied[1])<.002&&Math.abs(f.applied[2])<.0005?rest+1:0;}
  if(g.done||g.tick+640>profile.round_ms*2){records.push({seed,trial,censored:true});continue;}
  const aim=project(g.runner.body.x,g.runner.body.y,profile.arena_radius);g.apply({tick:g.tick,...aim,hold_ms:600});while(g.strike&&!g.done)g.step();
  records.push({seed,trial,environment_seed:1000+seed+100*trial,censored:!g.lastImpact,...g.lastImpact});
 }
 const resolved=records.filter(r=>!r.censored),escaped=resolved.filter(r=>!r.caught).length;
 return {records,opportunities:records.length,resolved:resolved.length,censored:records.length-resolved.length,escapes:escaped,conservative_escape_probability:escaped/records.length,resolved_escape_probability:escaped/resolved.length};
}
export function originalRestingSwat(profile:any,seeds:number[],rounds=2){
 const records:any[]=[];
 for(const seed of seeds)for(let round=0;round<rounds;round++){
  const g=newGame(profile,seed,1000+seed+100*round);
  for(let trial=0;trial<5;trial++){
   let rest=0;while(!g.done&&rest<20){const f=g.step();rest=!f.air&&Math.abs(f.applied[1])<.002&&Math.abs(f.applied[2])<.0005?rest+1:0;}
   if(g.done){records.push({seed,round,trial,censored:true});continue;}
   const aim=project(g.runner.body.x,g.runner.body.y,profile.arena_radius);g.apply({tick:g.tick,...aim,hold_ms:600});const impactTick=g.strike.impact_tick;
   while(g.strike&&!g.done)g.step();
   const impact=g.lastImpact?.tick===impactTick?g.lastImpact:null;
   records.push({seed,round,trial,environment_seed:1000+seed+100*round,censored:!impact,...impact});
  }
 }
 const resolved=records.filter(r=>!r.censored),escapes=resolved.filter(r=>!r.caught).length;
 return {protocol:'Exact a01 repeated-strike schedule',records,opportunities:records.length,resolved:resolved.length,censored:records.length-resolved.length,escapes,conservative_escape_probability:escapes/records.length,resolved_escape_probability:escapes/resolved.length};
}
async function main(){
 mkdirSync(out,{recursive:true});const cmd=process.argv[2],id=process.argv[3],seeds=protocol.measurement.validation_seeds;
 const receipt={code_sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),protocol_sha256:createHash('sha256').update(readFileSync(root+'profiles/owner-walking-a02.json')).digest('hex')};
 if(cmd==='--swat-dry'){
  const swat=originalRestingSwat(profileFor('A'),[101],1);save('original-swat/dry-run.json',{...receipt,classification:'PIPELINE_ONLY_EXCLUDED_FROM_SAFETY',swat});console.log('PASS original-schedule dry run',swat.opportunities,swat.censored);
 }else if(cmd==='--swat-original'){
  const original=id==='baseline',prior=original?null:load(`evidence/V2J/a02/presets/${id}.json`),profile=original?old:prior.profile;
  const swat=originalRestingSwat(profile,seeds);save(`original-swat/${id}.json`,{...receipt,swat});
  if(original){if(swat.conservative_escape_probability!==.88||swat.censored!==0)throw Error('Original control does not reproduce a01 176/200');}
  else {const result={...prior,swat,swat_revision:{...receipt,reason:'D-V2J-PROTOCOL-04: exact original repeated-strike workload; independent-round outputs retained'},offered:false,gates:{...prior.gates,resting_swat:swat.conservative_escape_probability>=.88}};save(`presets/${id}.json`,result);}
  console.log(id,'original swat',swat.escapes,'/',swat.opportunities,'censored',swat.censored,'conservative',swat.conservative_escape_probability);
 }else if(cmd==='--dry-run'){
  const p=profileFor('A'),q=await quiet(p,101,1),b=bots(p,[101],true),s=restingSwat(p,[101],1);
  save('dry-run.json',{...receipt,classification:'PIPELINE_ONLY_EXCLUDED_FROM_SELECTION',quiet:q,bot:b,swat:s});console.log('PASS dry run',b.rates.length,'bot/type/limit combinations');
 }else if(cmd==='--D'){
  const rows=[];for(const forward of protocol.presets.D.forward_candidates){const p=profileFor('D',forward),quietRows=[];for(const seed of protocol.measurement.selection_seeds){const q=await quiet(p,seed);save(`selection/D-${forward}/quiet-${seed}.json`,q);quietRows.push(q);}const summary=summarize(quietRows);rows.push({forward,summary,qualifies:summary.visible.median_bout_s!==null&&summary.visible.median_bout_s>=.3});console.log('D candidate',forward,summary.visible);}
  const selected=rows.find(r=>r.qualifies)?.forward??null;save('selection/D.json',{...receipt,rows,selected});console.log('D selected',selected);
 }else if(cmd==='--C'){
  const rows=[];for(const speed of protocol.presets.C.takeoff_speed_candidates){const profile=profileFor('C',undefined,speed),bot=bots(profile,protocol.measurement.selection_seeds,false,4,0,false),rate=bot.rates[0];rows.push({takeoff_speed:speed,bot,qualifies:rate.n>0&&rate.catch_rate!<=.65});console.log('C candidate',speed,rate);}
  const selected=rows.find(r=>r.qualifies)?.takeoff_speed??null;save('selection/C.json',{...receipt,rows,selected});console.log('C selected',selected);
 }else if(cmd==='--baseline'){
  const swat=restingSwat(old,seeds);save('baseline-swat.json',{...receipt,swat});console.log('Matched baseline',swat.conservative_escape_probability,swat.censored);
 }else if(cmd==='--preset'){
  const forward=id==='D'?load('evidence/V2J/a02/selection/D.json').selected:undefined,speed=id==='C'?load('evidence/V2J/a02/selection/C.json').selected:undefined;
  if(forward===null||speed===null){save(`presets/${id}.json`,{...receipt,id,offered:false,reason:'No declared selection candidate qualifies'});return;}
  const profile=profileFor(id,forward,speed),rows=[];
  for(const seed of seeds){const q=await quiet(profile,seed);save(`presets/${id}/quiet-${seed}.json`,q);rows.push(q);console.log(id,'quiet',seed);}
  const summary=summarize(rows),bot=bots(profile,seeds);console.log(id,'bots complete');const swat=restingSwat(profile,seeds);console.log(id,'swat complete');
  const replay=botRound(profile,1,4,0,false,2).game,log=await replay.log();await replayLog(buffer,identityRuntime(profile),profile,log);
  const baseline=load('evidence/V2J/a02/baseline-swat.json').swat.conservative_escape_probability;
  const gates={false_takeoffs:summary.false_takeoffs_s<=.05,whole_circuit:summary.whole_rate_hz!<50,resting_swat:swat.conservative_escape_probability>=protocol.safety.resting_swat_escape_min,replay:true,drive_parity:'PENDING'};
  save(`presets/${id}.json`,{...receipt,id,profile,profile_sha256:sha(profile),summary,bot,swat,replay:{log,status:'PASS'},gates,offered:false});console.log(id,summary,swat.conservative_escape_probability,gates);
 }else if(cmd==='--quiet-repair'){
  const prior=load(`evidence/V2J/a02/presets/${id}.json`),profile=prior.profile,rows=[];
  if(id==='D'&&profile.walking_drive.selected.forward!==load('evidence/V2J/a02/selection/D.json').selected)throw Error('D changed: run full preset validation instead of quiet repair');
  for(const seed of seeds){const q=await quiet(profile,seed);save(`presets/${id}/quiet-${seed}.json`,q);rows.push(q);console.log(id,'corrected quiet',seed);}
  const summary=summarize(rows),result={...prior,quiet_repair:{...receipt,reason:'seconds-to-ticks conversion corrected from 200 to 2000. Bot, swat and replay code/output unchanged; invalid 3 s quiet outputs retained under invalid-clock.',prior_result_sha256:sha(prior)},summary,gates:{...prior.gates,false_takeoffs:summary.false_takeoffs_s<=.05,whole_circuit:summary.whole_rate_hz!<50,resting_swat:prior.swat.conservative_escape_probability>=protocol.safety.resting_swat_escape_min}};
  save(`presets/${id}.json`,result);console.log(id,summary);
 }else if(cmd==='--finalize'){
  const parity=load('evidence/V2J/a02/parity/summary.json'),presets:any={};
  for(const id of ['A','B','C','D']){const r=load(`evidence/V2J/a02/presets/${id}.json`);if(r.gates){r.gates.drive_parity=parity.presets[id]===true;r.offered=Object.values(r.gates).every(v=>v===true);save(`presets/${id}.json`,r);}presets[id]={name:protocol.presets[id].name,offered:r.offered,reason:r.offered?'All safety gates pass':r.reason??Object.entries(r.gates).filter(([,v])=>v!==true).map(([k])=>k).join(', '),...(r.profile?{profile:r.profile,profile_sha256:r.profile_sha256}:{}),summary:r.summary,gates:r.gates};}
  const result={schema:'flybench.owner-walking-selection.v1',...receipt,production_profile:'flybench.game.v2.7',presets};
  writeFileSync(root+'profiles/owner-walking-a02-selected.json',JSON.stringify(result,null,2)+'\n');save('selection/offer.json',result);console.log(Object.entries(presets).map(([id,v]:any)=>({id,offered:v.offered,reason:v.reason})));
 }else throw Error('Expected --dry-run, --D, --C, --baseline, --preset ID --quiet-repair ID or --finalize');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await main();
