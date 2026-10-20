/** Descriptive paired game validation. No scientific calibration or tuning. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {Worker,isMainThread,parentPort,workerData} from 'node:worker_threads';
import {Game,replayLog} from '../src/game.ts';
import {root,load,runtime,buffer,quiet,summarize,botRound,originalRestingSwat} from './owner-walking.ts';
const profile=load('profiles/game-v2.9.json'),old=load('profiles/game-v2.8.json'),protocol=load('profiles/ui-v2l.json'),out=root+'evidence/V2L';
const hash=(p:string)=>createHash('sha256').update(readFileSync(root+p)).digest('hex');
const receipt=()=>({code_sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),validation_source_sha256:hash('apps/play/test/v2l.ts'),profile_sha256:hash('profiles/game-v2.9.json'),protocol_sha256:hash('profiles/ui-v2l.json')});
function save(p:string,v:any){mkdirSync(out+'/'+p.split('/').slice(0,-1).join('/'),{recursive:true});writeFileSync(out+'/'+p,JSON.stringify(v,null,2)+'\n');}
function pairs(bot:number,seeds:number[],one=false){
 const before:any[]=[],after:any[]=[],changed:any[]=[],prefix_audits:any[]=[];
 for(const human of [false,true])for(const name of ['flick','swat'])for(const seed of seeds){
  const a=botRound(old,seed,bot,old.strikes.findIndex((s:any)=>s.name===name),human,one?1:6);
  const b=botRound(profile,seed,bot,profile.strikes.findIndex((s:any)=>s.name===name),human,one?1:6);
  before.push(...a.records);after.push(...b.records);
  const first=b.game.frames.find((f,i)=>{const prior=a.game.frames[i];return prior&&JSON.stringify(f.body)!==JSON.stringify(prior.body);})?.tick??null;
  const fixed=new Game(buffer,runtime,profile,seed,1000+seed);let inputIndex=0,prefix:any=null;
  while(fixed.tick<a.game.tick&&!fixed.done){
   const input=a.game.inputs[inputIndex];if(input?.tick===fixed.tick){assert(fixed.apply(input));inputIndex++;}
   const f=fixed.step(),prior=a.game.frames[f.tick/20-1];
   if(JSON.stringify(f.body)!==JSON.stringify(prior.body)){prefix={tick:f.tick,takeoff_onset_tick:f.air_start_tick,flight_age_ms:(f.tick-f.air_start_tick!)*.5,old_body:prior.body,new_body:f.body,old_air:prior.air,new_air:f.air,applied_old_inputs:inputIndex,previous_input_tick:a.game.inputs[inputIndex-1]?.tick??null};break;}
  }
  assert.equal(prefix?.tick??null,first,'Adaptive bots must match fixed-input reexecution until first physical divergence');
  prefix_audits.push({bot,human,hand:name,seed,first_divergence:prefix});
  for(let i=0;i<a.records.length;i++){
   const x=a.records[i],y=b.records[i];
   if(x.censored!==y.censored||(!x.censored&&!y.censored&&x.caught!==y.caught))changed.push({bot,human,hand:name,seed,trial:i,before:x,after:y,first_body_divergence_tick:first,fixed_input_prefix:prefix,reason:x.censored!==y.censored?'Longer flight changes later resting eligibility, so an opportunity becomes available or exceeds the round.':first!==null&&first<=Math.min(x.observed_tick,y.observed_tick)?'A previous extended flight changes the observed body pose; later sensory input and neural trajectory can then differ.':'This impact follows the end of the original 120 ms flight window; the still-flying body follows the extended flight instead of landed walking.',observation_clock_changed:x.observed_tick!==y.observed_tick});
  }
 }
 const rates=(records:any[])=>[false,true].flatMap(human=>['flick','swat'].map(type=>{const all=records.filter(r=>r.human===human&&r.type===type),r=all.filter(v=>!v.censored);return {bot,human,type,n:r.length,censored:all.length-r.length,catches:r.filter(v=>v.caught).length,catch_rate:r.filter(v=>v.caught).length/r.length};}));
 return {before:{records:before,rates:rates(before)},after:{records:after,rates:rates(after)},changed,prefix_audits};
}
async function measuredBots(seeds:number[],one=false){const parts=await Promise.all([1,2,4].map(bot=>new Promise<any>((resolve,reject)=>{const w=new Worker(new URL(import.meta.url),{workerData:{bot,seeds,one}});w.once('message',r=>{console.log('paired bot',bot,'complete');resolve(r);});w.once('error',reject);w.once('exit',code=>{if(code)reject(Error('Worker exit '+code));});})));return {before:{records:parts.flatMap(p=>p.before.records),rates:parts.flatMap(p=>p.before.rates)},after:{records:parts.flatMap(p=>p.after.records),rates:parts.flatMap(p=>p.after.rates)},changed:parts.flatMap(p=>p.changed),prefix_audits:parts.flatMap(p=>p.prefix_audits)};}
function invariants(){
 assert.deepEqual(profile,load('profiles/game-v2.json'));assert.deepEqual(profile,load('apps/play/public/data/game.json'));
 assert.deepEqual(profile.walking_drive.selected,old.walking_drive.selected);
 const allowed=['profile_id','version','hold_thresholds_ms','strikes','takeoff_duration_ms','change_reason','physics_disclosure','walking_drive','takeoff_path_arena_units'];
 for(const k of Object.keys(old))if(!allowed.includes(k))assert.deepEqual(profile[k],old[k],k);
 const normalized=(p:any)=>{const v=structuredClone(p.walking_drive);delete v.copy;return v;};assert.deepEqual(normalized(profile),normalized(old));
 assert.deepEqual(profile.strikes,[old.strikes[0],old.strikes[2]]);assert.deepEqual(profile.hold_thresholds_ms,[300]);assert.equal(profile.takeoff_speed,.018);assert.equal(profile.takeoff_duration_ms,330);
 assert.deepEqual(load('apps/play/public/data/coupling/game-v2.8.json'),old);
 for(const [p,h] of Object.entries(load('evidence/V2L/protected.json').files))assert.equal(hash(p),h,p);
 for(const [p,v] of Object.entries(load('evidence/V2L/prior-preservation.json').files) as any[])assert.equal(hash(p),v.sha256,p);
 for(const row of load('archive/raw-records-manifest.json').files){const p=row.path;assert.equal(readFileSync(root+p).length,row.bytes,p);assert.equal(hash(p),row.sha256,p);}
}
if(!isMainThread){parentPort!.postMessage(pairs(workerData.bot,workerData.seeds,workerData.one));}
else if(process.argv.includes('--prefix-dry')){const bot=await measuredBots([101],true);save('prefix-dry-run.json',{...receipt(),classification:'PIPELINE_ONLY_SEED_101_EXCLUDED',bot});console.log('PASS fixed-input prefix replay dry run');}
else if(process.argv.includes('--fixture-probes')){
 const records:any[]=[];
 const exercise=async(seed:number,warmup:number,hold:number,aim?:{x:number,y:number})=>{const g=new Game(buffer,runtime,profile,seed,8128);for(let i=0;i<warmup;i++)g.step();const b=g.runner.body;g.apply({tick:g.tick,x:aim?.x??b.x,y:aim?.y??b.y,hold_ms:hold});while(g.strike)g.step();records.push({seed,warmup_intervals:warmup,hold_ms:hold,log:await g.log(),impact:g.lastImpact,quiet_onsets:g.frames.filter(f=>f.onset&&f.tick<3000).map(f=>f.tick)});};
 for(const seed of [1,2,3,4,5,6]){await exercise(seed,0,0,{x:0,y:0});await exercise(seed,150,600);}
 for(const seed of [2,3,4])for(const x of [1.5,2,2.5])await exercise(seed,0,0,{x,y:0});
 save('fixture-probes.json',{...receipt(),classification:'ENGINEERING_FIXTURES_NOT_HERO_SELECTION',reason:'Retain all seed 1-6 diagnostic workload probes used to choose an actual caught presentation fixture and inspect pre-strike spontaneous flights. Rule was already frozen; these do not change ascending hero selection. Recomputed with identical game parameters for a complete machine-readable trace.',seeds:[1,2,3,4,5,6],records});console.log('Recorded all 21 diagnostic fixture probes; no selection or tuning');
}else if(process.argv.includes('--dry')){
 const q=await quiet(profile,101,1),bot=await measuredBots([101],true),swat=originalRestingSwat(profile,[101],1);
 const g=new Game(buffer,runtime,profile,101,8128);for(let i=0;i<150;i++)g.step();const b=g.runner.body;g.apply({tick:g.tick,x:b.x,y:b.y,hold_ms:600});while(g.strike)g.step();const log=await g.log();assert((await replayLog(buffer,runtime,profile,log)).matches);
 save('dry-run.json',{...receipt(),classification:'PIPELINE_ONLY_SEED_101_EXCLUDED',quiet:q,bot,swat,hero_log:log,hero_impact:g.lastImpact});console.log('PASS dry: both hands, all bot limits, swat schedule, hero procedure and replay');
}else if(process.argv.includes('--measure')){
 invariants();const rows=[],baseline=[];
 for(const seed of protocol.measurement_seeds){const a=await quiet(old,seed),b=await quiet(profile,seed);save(`quiet/v28-${seed}.json`,a);save(`quiet/v29-${seed}.json`,b);baseline.push(a);rows.push(b);console.log('quiet pair',seed);}
 const bot=await measuredBots(protocol.measurement_seeds),swat=originalRestingSwat(profile,protocol.measurement_seeds),priorSwat=originalRestingSwat(old,protocol.measurement_seeds);
 const prior=load('evidence/V2J/a03/A.json');assert.deepEqual(bot.before.records,prior.bot.records.filter((r:any)=>r.type!=='slap'));assert.deepEqual(priorSwat,prior.swat);
 const summary=summarize(rows),before=summarize(baseline),gates={spontaneous_takeoffs:summary.false_takeoffs_s<=.05,circuit_rate:rows.every(r=>r.whole_rate_hz<50)};
 const result={...receipt(),classification:'DESCRIPTIVE_ENGINEERING_NO_TUNING',before,summary,per_seed_circuit_below_50:rows.every(r=>r.whole_rate_hz<50),bot,changed_outcomes:bot.changed.length,changed_catch_outcomes:bot.changed.filter(r=>!r.before.censored&&!r.after.censored).length,changed_censoring:bot.changed.filter(r=>r.before.censored!==r.after.censored).length,swat,priorSwat,baseline_exactly_reproduces_v2j:true,gates};save('validation.json',result);console.log(JSON.stringify({before,summary,gates,changed_outcomes:result.changed_outcomes,swat:swat.escapes,censored:swat.censored}));assert(Object.values(gates).every(Boolean));
}else if(process.argv.includes('--check')){invariants();const r=load('evidence/V2L/validation.json');assert.equal(r.code_sha,receipt().code_sha);assert.equal(r.profile_sha256,receipt().profile_sha256);assert.equal(r.protocol_sha256,receipt().protocol_sha256);assert(Object.values(r.gates).every(Boolean));save('preservation-check.json',{...receipt(),status:'PASS',protected_files:Object.keys(load('evidence/V2L/protected.json').files).length,prior_files:Object.keys(load('evidence/V2L/prior-preservation.json').files).length});console.log('PASS final-SHA validation and protected/prior identities');}
else throw Error('Expected --dry, --measure or --check');
