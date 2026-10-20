/** Fixed owner playtest. All records are descriptive; no selection or tuning. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {Worker,isMainThread,parentPort,workerData} from 'node:worker_threads';
import {u32} from '../../../packages/kernel-ts/src/kernel.ts';
import {replayLog} from '../src/game.ts';
import {root,load,buffer,newGame,identityRuntime,quiet,summarize,botRound,project,originalRestingSwat,sha} from './owner-walking.ts';
export const protocol=load('profiles/owner-takeoff-v2m.json'),base=load('profiles/game-v2.9.json');
const out=root+'evidence/V2M';
const hash=(p:string)=>createHash('sha256').update(readFileSync(root+p)).digest('hex');
const receipt=()=>({code_sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),protocol_sha256:hash('profiles/owner-takeoff-v2m.json'),measurement_source_sha256:hash('apps/play/test/v2m.ts')});
export function preset(id:string){const p=protocol.presets[id];assert(p,'Unknown preset');return {...structuredClone(base),profile_id:`flybench.game.v2.9.owner-v2m.${id}`,takeoff_speed:p.takeoff_speed,takeoff_duration_ms:p.takeoff_duration_ms,takeoff_path_arena_units:p.nominal_path_units,owner_preset:{id,name:id,production:false},physics_disclosure:'Takeoff speed is an abstract body-physics game parameter, not a neural parameter. Flight duration scales to keep the path about six arena units. Walking, neural onset, direction, jitter and reflection are unchanged.'};}
export function skilledRound(profile:any,seed:number,type:number,human:boolean,opportunities=6,endMs=30000){
 const g=newGame(profile,seed),records:any[]=[];let still=0,previous={x:0,y:0},previousAir=false;
 const step=()=>{const f=g.step(),speed=Math.hypot(f.body.x-previous.x,f.body.y-previous.y)/.01/2;still=!f.air&&!previousAir&&speed<=.5?still+1:0;previous=f.body;previousAir=f.air;};
 const advance=(n:number)=>{for(let i=0;i<n&&!g.done&&g.tick<endMs*2;i++)step();};advance(150);
 for(let trial=0;trial<opportunities;trial++){
  if(trial)advance(100);while(!g.done&&g.tick<endMs*2&&still<15)step();
  if(g.done||g.tick>=endMs*2){records.push({bot:5,human,type:profile.strikes[type].name,seed,trial,censored:true,reason:'No eligible opportunity within round'});continue;}
  const b={...g.runner.body},observed_tick=g.tick,held=g.runner.held[1],fall=8/profile.strikes[type].speed,still_ms=still*10;
  let x=b.x,y=b.y;
  if(human){advance(12);x+=(u32(seed,71,trial,0)/2**32*2-1)*.15;y+=(u32(seed,71,trial,1)/2**32*2-1)*.15;}
  if(g.done||g.tick+Math.round(fall*2)>Math.min(endMs*2,profile.round_ms*2)){records.push({bot:5,human,type:profile.strikes[type].name,seed,trial,censored:true,reason:'Reaction or impact exceeds round'});continue;}
  g.apply({tick:g.tick,...project(x,y,profile.arena_radius),hold_ms:profile.strikes[type].name==='flick'?80:600});
  while(g.strike&&!g.done&&g.tick<endMs*2)step();
  records.push({bot:5,human,seed,trial,observed_tick,observed_body:b,observed_forward:held,still_ms,censored:!g.lastImpact,...g.lastImpact});
 }
 return {game:g,records};
}
function botRecords(profile:any,bot:number,seeds:number[],hands:string[],one=false){
 const records:any[]=[];
 for(const human of [false,true])for(const name of hands)for(const seed of seeds){
  const type=profile.strikes.findIndex((s:any)=>s.name===name);
  records.push(...(bot===5?skilledRound(profile,seed,type,human,one?1:6):botRound(profile,seed,bot,type,human,one?1:6)).records);
 }return records;
}
function rates(records:any[]){return [1,2,4,5].flatMap(bot=>[false,true].flatMap(human=>['flick','swat'].map(type=>{const all=records.filter(r=>r.bot===bot&&r.human===human&&r.type===type),r=all.filter(v=>!v.censored),catches=r.filter(v=>v.caught).length;return {bot,human,type,n:r.length,censored:all.length-r.length,catches,catch_rate:r.length?catches/r.length:null};}))).filter(r=>r.n||r.censored);}
async function bots(profile:any,seeds:number[],hands=['flick','swat'],one=false){const parts=await Promise.all([1,2,4,5].map(bot=>new Promise<any>((resolve,reject)=>{const w=new Worker(new URL(import.meta.url),{workerData:{profile,bot,seeds,hands,one}});w.once('message',resolve);w.once('error',reject);w.once('exit',code=>{if(code)reject(Error('Worker exit '+code));});})));const records=parts.flat();return {records,rates:rates(records)};}
function leads(records:any[],bot=4,human=false){
 const all=records.filter(r=>r.bot===bot&&r.human===human&&r.type==='flick'&&!r.censored),values=all.map(r=>r.escape_onset_lead_ms).filter(v=>typeof v==='number').sort((a,b)=>a-b);
 return {bot,human,resolved:all.length,no_onset:all.length-values.length,nonpositive:values.filter(v=>v<=0).length,values_ms:values,nearest_rank_ms:Object.fromEntries([0,.1,.25,.5,.75,.9,1].map(q=>[String(q),values[Math.max(0,Math.ceil(q*values.length)-1)]??null]))};
}
function save(p:string,v:any){mkdirSync(out+'/'+p.split('/').slice(0,-1).join('/'),{recursive:true});writeFileSync(out+'/'+p,JSON.stringify(v,null,2)+'\n');}
export function invariants(){
 assert.deepEqual(base,load('profiles/game-v2.json'));assert.deepEqual(base,load('apps/play/public/data/game.json'));
 for(const [p,h] of Object.entries(load('evidence/V2M/protected.json').files))assert.equal(hash(p),h,p);
 for(const [p,v] of Object.entries(load('evidence/V2M/prior-preservation.json').files) as any[])assert.equal(hash(p),v.sha256,p);
 for(const row of load('archive/raw-records-manifest.json').files){assert.equal(readFileSync(root+row.path).length,row.bytes,row.path);assert.equal(hash(row.path),row.sha256,row.path);}
}
async function main(){
 const cmd=process.argv[2],seeds=protocol.measurement.validation_seeds;
 if(cmd==='--dry'){
  const rows=[];
  for(const id of Object.keys(protocol.presets)){const p=preset(id),q=await quiet(p,101,1),bot=await bots(p,[101],undefined,true),swat=originalRestingSwat(p,[101],1),g=skilledRound(p,101,0,true,1).game,log=await g.log();assert((await replayLog(buffer,identityRuntime(p),p,log)).matches);rows.push({id,quiet:q,bot,swat,replay:log});}
  const b4=botRound(base,101,4,0,false,1).records,b5=skilledRound(base,101,0,false,1).records;
  assert.deepEqual(b5.map(r=>({...r,bot:4})),b4,'Unrestricted bot 5 exactly matches bot 4');
  save('dry-run.json',{...receipt(),classification:'PIPELINE_ONLY_SEED_101_EXCLUDED',rows});console.log('PASS four preset dry runs, skilled bot, exact replay and unchanged unrestricted stop rule');
 }else if(cmd==='--baseline'){
  const swat=originalRestingSwat(load('profiles/game-v2.7.json'),seeds);
  assert.equal(swat.escapes,176);assert.equal(swat.opportunities,200);assert.equal(swat.censored,0);
  save('baseline-swat.json',{...receipt(),profile:'flybench.game.v2.7',swat});console.log('PASS original V2J control: 176/200 resting-swat escapes, zero censored');
 }else if(cmd==='--diagnose'){
  invariants();const before=await bots(load('profiles/game-v2.8.json'),seeds,['flick']),after=await bots(base,seeds,['flick']);
  const prior=load('evidence/V2L/validation.json');
  for(const [name,v] of [['before',before],['after',after]] as const)assert.deepEqual(v.records.filter(r=>r.bot!==5),prior.bot[name].records.filter((r:any)=>r.type==='flick'));
  const result={...receipt(),before,after,resting_onset_leads:{v28:leads(before.records),v29:leads(after.records)},skilled_onset_leads:{v28:leads(before.records,5,true),v29:leads(after.records,5,true)},prior_bot_records_exact:true};
  save('diagnosis.json',result);console.log(JSON.stringify({before:before.rates,after:after.rates,resting:result.resting_onset_leads,skilled:result.skilled_onset_leads}));
 }else if(cmd==='--preset'){
  const id=process.argv[3],p=preset(id),rows=[];
  for(const seed of seeds){const q=await quiet(p,seed);rows.push(q);save(`presets/${id}/quiet-${seed}.json`,q);}
  const summary=summarize(rows),bot=await bots(p,seeds),swat=originalRestingSwat(p,seeds),g=skilledRound(p,1,0,true,2).game,log=await g.log(),replayed=await replayLog(buffer,identityRuntime(p),p,log);
  const parity=load('evidence/V2M/parity/summary.json').presets[id];assert.equal(parity.profile_sha256,sha(p));
  const gates={false_takeoffs:summary.false_takeoffs_s<=.05,circuit_rate:rows.every(r=>r.whole_rate_hz<50),resting_swat:swat.conservative_escape_probability>=.88,replay:replayed.matches,parity:parity.bit_exact===true};
  save(`presets/${id}.json`,{...receipt(),id,profile:p,profile_sha256:sha(p),summary,bot,swat,replay:{log,status:replayed.matches?'PASS':'FAIL'},gates,offered:Object.values(gates).every(Boolean)});console.log(id,JSON.stringify({summary,rates:bot.rates,swat:swat.escapes,censored:swat.censored,gates}));
 }else if(cmd==='--offer'){
  const parity=load('evidence/V2M/parity/summary.json'),presets:any={};
  for(const id of Object.keys(protocol.presets)){
   const r=load(`evidence/V2M/presets/${id}.json`);assert.equal(r.profile_sha256,sha(preset(id)));assert.equal(parity.presets[id].profile_sha256,r.profile_sha256);
   const gates={...r.gates,parity:parity.presets[id].bit_exact===true};
   presets[id]={name:`${id} · ${r.profile.takeoff_speed.toFixed(3)} units/ms`,profile:r.profile,profile_sha256:r.profile_sha256,gates,offered:Object.values(gates).every(Boolean),reason:Object.values(gates).every(Boolean)?'All V2J safety gates pass':'Safety gate failed'};
  }
  const result={schema:'flybench.owner-takeoff-offer.v1',protocol_sha256:receipt().protocol_sha256,production_profile:base.profile_id,presets};
  writeFileSync(root+'profiles/owner-takeoff-v2m-selected.json',JSON.stringify(result,null,2)+'\n');save('offer.json',{...receipt(),...result});console.log('Fixed presets:',Object.entries(presets).map(([id,p]:any)=>[id,p.offered,p.gates]));
 }else if(cmd==='--check'){
  invariants();const selection=load('profiles/owner-takeoff-v2m-selected.json'),parity=load('evidence/V2M/parity/summary.json');
  assert.equal(parity.code_sha,receipt().code_sha);assert.equal(load('evidence/V2M/diagnosis.json').code_sha,receipt().code_sha);assert.equal(load('evidence/V2M/baseline-swat.json').code_sha,receipt().code_sha);
  for(const id of Object.keys(protocol.presets)){const r=load(`evidence/V2M/presets/${id}.json`);assert.equal(r.code_sha,receipt().code_sha);assert.equal(r.protocol_sha256,receipt().protocol_sha256);assert.equal(r.measurement_source_sha256,receipt().measurement_source_sha256);assert.deepEqual(r.bot.rates,rates(r.bot.records));assert.deepEqual(selection.presets[id].gates,{...r.gates,parity:parity.presets[id].bit_exact});assert.equal(selection.presets[id].profile_sha256,sha(preset(id)));}
  save('preservation-check.json',{...receipt(),status:'PASS'});console.log('PASS final-SHA measurements, frozen, raw, prior records, production physics, walking and lab identities');
 }
 else throw Error('Expected --dry, --diagnose, --preset ID or --check');
}
if(!isMainThread)parentPort!.postMessage(botRecords(workerData.profile,workerData.bot,workerData.seeds,workerData.hands,workerData.one));
else if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await main();
