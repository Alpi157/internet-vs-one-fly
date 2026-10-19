/** Production A validation, using the frozen a02 workload and authoritative Game. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {Game,replayLog} from '../src/game.ts';
import {WalkingDrive} from '../src/walking-drive.ts';
import {root,load,runtime,buffer,quiet,summarize,bots,botRound,originalRestingSwat,old} from './owner-walking.ts';
const out=root+'evidence/V2J/a03',profile=load('profiles/game-v2.json'),protocol=load('profiles/walking-a03.json'),prior=load('evidence/V2J/a02/presets/A.json');
const hash=(p:string)=>createHash('sha256').update(readFileSync(root+p)).digest('hex');
function save(p:string,v:any){mkdirSync(out+'/'+p.split('/').slice(0,-1).join('/'),{recursive:true});writeFileSync(out+'/'+p,JSON.stringify(v,null,2)+'\n');}
const receipt=()=>({code_sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),protocol_sha256:hash('profiles/walking-a03.json'),profile_sha256:hash('profiles/game-v2.json')});
function samePreview(){
 const reference=load('profiles/owner-walking-a02-selected.json').presets.A.profile;
 const normalize=(p:any)=>{p=structuredClone(p);for(const k of ['profile_id','owner_preset','change_reason'])delete p[k];for(const k of ['copy','selection_decision','history'])delete p.walking_drive[k];return p;};
 assert.deepEqual(normalize(profile),normalize(reference),'No engine parameter may differ from preview A');assert.equal(profile.profile_id,'flybench.game.v2.8');
 assert.deepEqual(profile,load('apps/play/public/data/game.json'));
}
function preservation(){
 for(const [p,v] of Object.entries(load('evidence/V2J/a03/prior-preservation.json').files) as any[])assert.equal(hash(p),v.sha256,`Prior record changed: ${p}`);
 for(const [p,h] of Object.entries(load('evidence/V2J/a02/a01-preservation.json').files))assert.equal(hash(p),h,`a01 changed: ${p}`);
 for(const name of ['evidence/V2J/frozen-check.json','evidence/V2J/protected-assets.json','profiles/freeze-v2.json','profiles/freeze-v2.1.json'])for(const [p,h] of Object.entries(load(name).files))assert.equal(hash(p),h,`Frozen: ${p}`);
}
async function parity(){
 mkdirSync(out+'/parity',{recursive:true});save('parity/profiles.json',{A:profile});
 execFileSync(root+'.venv/bin/python',['tests/owner_walking_reference.py',out+'/parity/profiles.json',out+'/parity/reference.json.gz'],{cwd:root,stdio:'inherit'});
 const rows=JSON.parse(gunzipSync(readFileSync(out+'/parity/reference.json.gz')).toString()),bits=(values:number[])=>{const b=Buffer.alloc(values.length*8);values.forEach((v,i)=>b.writeDoubleLE(v,i*8));return b.toString('hex');};
 for(const row of rows){const d=new WalkingDrive(row.seed,row.point);for(const expected of row.intervals)assert.equal(bits([...d.next(),...d.snapshot()]),expected);d.reset();assert.equal(bits([...d.next(),...d.snapshot()]),row.intervals[0]);}
 save('parity/summary.json',{...receipt(),status:'PASS',seeds:rows.map((r:any)=>r.seed),intervals_per_seed:3000,bit_exact:true,reset:true});
}
samePreview();
const cmd=process.argv[2];
if(cmd==='--dry'){
 const q=await quiet(profile,101,1),bot=bots(profile,[101],true),swat=originalRestingSwat(profile,[101],1);
 const g=new Game(buffer,runtime,profile,101,8128);for(let i=0;i<150;i++)g.step();const b=g.runner.body;g.apply({tick:g.tick,x:b.x,y:b.y,hold_ms:300});while(g.strike)g.step();
 save('dry-run.json',{...receipt(),classification:'PIPELINE_ONLY_EXCLUDED_FROM_VALIDATION_AND_HERO_SELECTION',quiet:q,bot,swat,hero_log:await g.log()});console.log('PASS a03 dry run: quiet, 18 bot combinations, original swat, hero timing');
}else if(cmd==='--measure'){
 const rows=[];for(const seed of protocol.measurement_seeds){const q=await quiet(profile,seed);save(`quiet/seed-${seed}.json`,q);rows.push(q);console.log('A quiet',seed);}
 const summary=summarize(rows),bot=bots(profile,protocol.measurement_seeds);console.log('A bots complete');
 const swat=originalRestingSwat(profile,protocol.measurement_seeds),baseline=originalRestingSwat(old,protocol.measurement_seeds);assert.equal(baseline.escapes,176);assert.equal(baseline.censored,0);
 const g=botRound(profile,1,4,0,false,2).game,log=await g.log();await replayLog(buffer,runtime,profile,log);await parity();
 const differences={summary_equal:JSON.stringify(summary)===JSON.stringify(prior.summary),bot_rates_equal:JSON.stringify(bot.rates)===JSON.stringify(prior.bot.rates),bot_records_equal:JSON.stringify(bot.records)===JSON.stringify(prior.bot.records),swat_equal:JSON.stringify(swat)===JSON.stringify(prior.swat)};
 const gates={false_takeoffs:summary.false_takeoffs_s<=.05,whole_circuit:summary.whole_rate_hz!<50,resting_swat:swat.conservative_escape_probability>=.88,replay:true,drive_parity:true};
 save('A.json',{...receipt(),summary,bot,swat,baseline,replay:{status:'PASS',log},gates,differences_from_a02:differences});
 console.log(JSON.stringify({summary,gates,differences},null,2));assert(Object.values(gates).every(Boolean));assert(Object.values(differences).every(Boolean),'Report differences; never silently retune');
}else if(cmd==='--check'){
 preservation();const r=load('evidence/V2J/a03/A.json');assert.equal(r.code_sha,receipt().code_sha,'Metrics must be rerun on the submitted SHA');assert.deepEqual(summarize(protocol.measurement_seeds.map((s:number)=>load(`evidence/V2J/a03/quiet/seed-${s}.json`))),r.summary);assert(Object.values(r.gates).every(v=>v===true));assert(Object.values(r.differences_from_a02).every(v=>v===true));assert.equal(r.profile_sha256,hash('profiles/game-v2.json'));assert.equal(load('evidence/V2J/a03/parity/summary.json').bit_exact,true);
 const p=load('docs/media/media-provenance.json');assert.equal(p.game.log.schema,'flybench.game-round.v3');assert.equal(p.game.selection.hold_ms,300);assert.equal(p.game.log.inputs[0].tick,3000);assert.equal(p.game.selection.tried,p.game.neural_seed);assert(p.game.observed_escape_stamp);assert.equal(p.game.walk_slowdown_factor,1);assert.equal(p.game.live_slowdown_factor,5);assert.equal(p.game.replay_speed,.25);
 save('safety-check.json',{...receipt(),status:'PASS',no_retuning:true,preservation:'PASS',gates:r.gates,differences_from_a02:r.differences_from_a02});console.log('PASS production A safety, parity, exact a02 outcomes, hero rule and prior/frozen preservation');
}else throw Error('Expected --dry, --measure or --check');
