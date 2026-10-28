import assert from 'node:assert/strict';
import {chromium} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync,rmSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {serve,root,dist,prefix} from './site-server.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
async function legacyCapture(){
const media=resolve(root,'docs/media'),evidence=resolve(root,'evidence/V2I/a02');mkdirSync(evidence,{recursive:true});
const provenancePath=resolve(media,'media-provenance.json');
const profile=JSON.parse(readFileSync(resolve(dist,'data/game.json'))),results=JSON.parse(readFileSync(resolve(dist,'results-v2f.json')));
// This declaration is written before launching a browser or trying a seed.
const selection={declared_at:new Date().toISOString(),rule:'First neural seed in ascending integer order whose first hand escapes. Fixed aim at the initial fly, no warmup, fixed Enter-key hold. Environment seed is held fixed. No other outcome enters selection.',first_seed:1,aim:{x:0,y:0},warmup_intervals:0,hold_ms:(profile.hold_thresholds_ms[0]+profile.hold_thresholds_ms[1])/2,environment_seed:results.lab_seeds.environment};
const declaration=JSON.stringify(selection,null,2)+'\n';writeFileSync(resolve(evidence,'hero-selection-declaration.json'),declaration);
const provenance={schema:'flybench.media.v2i.a02',capture_code_sha256:hash(readFileSync(import.meta.filename)),base_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),viewport:{width:1440,height:900},display_only:true,game:{selection},lab:{},assets:{}};
writeFileSync(provenancePath,JSON.stringify(provenance,null,2)+'\n');
const browser=await chromium.launch({headless:true}),{server,origin}=await serve(),url=origin+prefix,frames='/tmp/flybench-v2i-a02-media-frames';
rmSync(frames,{recursive:true,force:true});mkdirSync(frames,{recursive:true});
try{
 const page=await browser.newPage({viewport:provenance.viewport}),external=[];
 await page.route('**/*',r=>{const u=r.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return r.abort();}return r.continue();});
 await page.goto(url+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);await page.evaluate(()=>document.fonts.ready);
 const reset=async seed=>{await page.evaluate(seed=>window.flyTest.resetSeed(seed),seed);await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');await page.locator('#table').focus();};
 const trials=[];let seed=selection.first_seed;
 for(;;seed++){
  await reset(seed);await page.keyboard.press('Enter');await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(()=>window.flyTest.state().replaying);
  const state=await page.evaluate(()=>window.flyTest.state());trials.push({seed,caught:state.catches>0});console.log('Hero selection',seed,state.catches?'caught':'escaped');if(!state.catches)break;
  assert(trials.length<10000,'No escape within safety bound; do not change the declared rule.');
 }
 selection.tried=trials.length;selection.trials=trials;selection.declaration_sha256=hash(declaration);
 if(process.argv.includes('--select')){provenance.game={selection,neural_seed:seed};writeFileSync(provenancePath,JSON.stringify(provenance,null,2)+'\n');process.exitCode=0;}else{
 await reset(seed);let index=0,observations=[];
 const capture=async()=>{await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));await page.screenshot({path:resolve(frames,`game-${String(index++).padStart(3,'0')}.png`)});observations.push(await page.evaluate(()=>({state:window.flyTest.state(),pill:document.getElementById('landing').textContent,stamp:document.getElementById('impact-label').textContent})));};
 await page.keyboard.press('Enter');
 while(!(await page.evaluate(()=>window.flyTest.state().replaying))){await page.evaluate(()=>window.flyTest.advance(1));await capture();}
 const log=await page.evaluate(()=>window.flyTest.log());assert.equal(log.neural_seed,seed);assert.deepEqual(log.inputs[0],{tick:0,...selection.aim,hold_ms:selection.hold_ms});
 const impact=observations.map(o=>o.state.frame.impact).find(Boolean);assert(impact&&!impact.caught);assert(observations.some(o=>o.state.frame.air));
 const liveFrames=index;
 // Record the ordinary quarter-speed UI on a fixed presentation clock. Replay
 // wraps are explicit; every rendered sample still comes from recorded frames.
 const replayClock=new Date();await page.clock.install({time:replayClock});await page.clock.pauseAt(new Date(replayClock.getTime()+1000));
 await page.evaluate(()=>{window.flyTest.showReplay();window.flyTest.measureReplay(true);});
 const replayTicks=[];
 for(let i=0;i<60;i++){await page.clock.runFor(50);replayTicks.push(await page.evaluate(()=>window.flyTest.state().replayTick));await page.screenshot({path:resolve(frames,`game-${String(index++).padStart(3,'0')}.png`)});}
 assert(new Set(replayTicks).size>20,'Replay playhead must move through recorded frames');
 assert(replayTicks.every((t,i)=>!i||t<replayTicks[i-1]||t-replayTicks[i-1]<=40),'Replay must advance at quarter speed, independent of screenshot overhead');
 await page.evaluate(()=>{window.flyTest.measureReplay(false);window.flyTest.showRecorded('flash');});await page.clock.runFor(100);
 await page.screenshot({path:resolve(media,'game-still.png')});
 const recordedTick=await page.evaluate(()=>window.flyTest.state().replayTick);
 const brain=await page.evaluate(()=>window.flyTest.brainSnapshot());const brainBytes=Buffer.from(brain.split(',')[1],'base64');writeFileSync(resolve(evidence,'hero-recorded-brain.png'),brainBytes);
 // A site card, using the same recorded BrainView frame and generated identity.
 const card=await page.evaluate(async({brain,count})=>{const c=document.createElement('canvas');c.width=1200;c.height=630;const g=c.getContext('2d');g.fillStyle='#000';g.fillRect(0,0,c.width,c.height);await document.fonts.load('900 72px Doto');const image=new Image();image.src=brain;await image.decode();g.drawImage(image,625,135,550,324);g.fillStyle='#e9ede6';g.font='900 72px Doto';g.fillText('Catch the fly',48,125);g.font='400 29px Atkinson';const lines=[`${count.toLocaleString('en-US')} neurons, wired as mapped`,'in a real male fruit fly.','Try to catch it.'];lines.forEach((s,i)=>g.fillText(s,48,245+i*44));g.fillStyle='#7fefaa';g.font='400 24px Atkinson';g.fillText('alpi157.github.io/internet-vs-one-fly/',48,563);return c.toDataURL();},{brain,count:results.circuit_counts.game});
 writeFileSync(resolve(root,'apps/play/public/og-image.png'),Buffer.from(card.split(',')[1],'base64'));
 provenance.game={selection,neural_seed:seed,environment_seed:selection.environment_seed,log,impact,frames:index,live_frames:liveFrames,frame_duration_ms:50,live_slowdown_factor:50/10,replay_seconds:60*50/1000,replay_speed:profile.replay_speed,replay_loop:true,replay_ticks:replayTicks,source:'Real Enter key input. Live phase advances one recorded control interval per frame; replay uses the ordinary quarter-speed renderer, looped to show three seconds of playback.',observed_takeoff:observations.some(o=>o.state.frame.air),observed_countdown:observations.some(o=>o.pill.includes('ms')),observed_escape_stamp:observations.some(o=>o.stamp==='Escaped'),og:{source:'Recorded hero replay frame with maximum observed spike count',brain_frame_sha256:hash(brainBytes),recorded_tick:recordedTick,kind:'Site card, no personal score'}};
 writeFileSync(resolve(evidence,'media-game-round.json'),JSON.stringify({log,impact,observations},null,2)+'\n');
 // Restore real wall-clock timers for the two live lab simulations.
 await page.clock.resume();await page.locator('[data-wiring]:visible').first().click();await page.waitForFunction(()=>window.couplingTest?.ready());
 const rt=JSON.parse(readFileSync(resolve(dist,'data/coupling/runtime.json'))),strength=JSON.parse(readFileSync(resolve(dist,'data/coupling/strength-demo.json')));
 provenance.lab={coupling:results.registered_coupling,neural_seed:results.lab_seeds.neural,environment_seed:results.lab_seeds.environment,sign:rt.null_selection,strength,observations:[],frame_duration_ms:100};index=0;
 for(const family of ['N-SIGN','N-STRENGTH']){
  await page.locator(`input[value="${family}"]`).check();await page.waitForFunction(()=>window.couplingTest?.ready());
  await page.waitForFunction(()=>window.couplingTest.state().panels[0].tick*.0005>=2,null,{timeout:60000});
  if(family==='N-SIGN')assert((await page.evaluate(()=>window.couplingTest.state())).panels[1].rate>results.chart.reference_hz);
  for(let i=0;i<40;i++){const start=Date.now();await page.screenshot({path:resolve(frames,`lab-${String(index++).padStart(3,'0')}.png`)});await page.waitForTimeout(Math.max(0,100-(Date.now()-start)));}
  provenance.lab.observations.push(await page.evaluate(()=>window.couplingTest.state()));
  if(family==='N-SIGN')await page.screenshot({path:resolve(media,'coupling-still.png')});
 }
 provenance.lab.frames=index;provenance.external_requests=external;assert.equal(external.length,0);
 for(const file of ['apps/play/public/data/runtime.json','apps/play/public/data/game.json','apps/play/public/data/coupling/runtime.json','apps/play/public/data/coupling/strength-demo.json','apps/play/public/data/anatomy/manifest.json','apps/play/public/og-image.png','apps/play/public/favicon.svg','docs/media/game-still.png','docs/media/coupling-still.png']){const b=readFileSync(resolve(root,file));provenance.assets[file]={bytes:b.length,sha256:hash(b)};}
 provenance.capture_source_sha256=Object.fromEntries(['main.ts','coupling.ts','coupling-worker.ts','brain-view.ts','field.ts','style.css','game.ts','worker.ts'].map(file=>['apps/play/src/'+file,hash(readFileSync(resolve(root,'apps/play/src/'+file)))]));
 writeFileSync(provenancePath,JSON.stringify(provenance,null,2)+'\n');
 }
}finally{await browser.close();await new Promise(r=>server.close(r));}

}

async function captureA03(){
 const v2k=process.argv.includes('--v2k'),dry=process.argv.includes('--dry-run');
 const media=resolve(root,'docs/media'),evidence=resolve(root,v2k?'evidence/V2K':'evidence/V2J/a03'),frames=v2k?'/tmp/flybench-v2k-media-frames':'/tmp/flybench-v2j-a03-media-frames';
 const provenancePath=resolve(media,'media-provenance.json'),previous=JSON.parse(readFileSync(provenancePath));
 const protocol=JSON.parse(readFileSync(resolve(root,v2k?'profiles/media-v2k.json':'profiles/walking-a03.json'))),profile=JSON.parse(readFileSync(resolve(dist,'data/game.json'))),results=JSON.parse(readFileSync(resolve(dist,'results-v2f.json')));
 const selection={...protocol.hero},declaration=JSON.stringify(selection,null,2)+'\n';
 // The committed protocol and this provenance precede every selected seed and capture.
 assert.equal(readFileSync(resolve(evidence,'hero-selection-declaration.json'),'utf8'),declaration);
 const provenance={schema:v2k?'flybench.media.v2k.a01':'flybench.media.v2j.a03',capture_code_sha256:hash(readFileSync(import.meta.filename)),base_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),viewport:{width:1440,height:900},display_only:true,game:{selection},lab:previous.lab,history:v2k?protocol.history:undefined,lab_historical_capture_commit:previous.historical_capture_commit??previous.lab_historical_capture_commit??previous.base_commit,assets:{}};
 writeFileSync(provenancePath,JSON.stringify(provenance,null,2)+'\n');
 mkdirSync(frames,{recursive:true});if(!dry)assert.equal((await import('node:fs')).readdirSync(frames).length,0,'Fresh capture directory required');
 const browser=await chromium.launch({headless:true}),{server,origin}=await serve(),external=[];
 try{
  const page=await browser.newPage({viewport:provenance.viewport});await page.route('**/*',r=>{const u=r.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return r.abort();}return r.continue();});
  await page.goto(origin+prefix+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);await page.evaluate(()=>document.fonts.ready);
  const reset=async seed=>{await page.evaluate(seed=>window.flyTest.resetSeed(seed),seed);await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');};
  const strike=async()=>page.evaluate(hold=>{const b=window.flyTest.state().frame.body;window.flyTest.strike(b.x,b.y,hold);return {x:b.x,y:b.y};},selection.hold_ms);
  if(dry){await reset(101);await page.evaluate(()=>window.flyTest.advance(150));const aim=await strike();await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(()=>window.flyTest.state().replaying);const state=await page.evaluate(()=>window.flyTest.state());assert.equal((await page.evaluate(()=>window.flyTest.log())).inputs[0].hold_ms,selection.hold_ms);writeFileSync(resolve(evidence,'hero-dry-run.json'),JSON.stringify({excluded_seed:101,aim,impact:state.lastImpact,anatomy_ready:state.anatomyReady,status:'PASS'},null,2)+'\n');console.log('Excluded media dry run',state.lastImpact);return;}
  const trials=[];let seed=selection.first_seed;
  for(;;seed++){
   await reset(seed);await page.evaluate(()=>window.flyTest.advance(150));const aim=await strike();await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(()=>window.flyTest.state().replaying);
   const state=await page.evaluate(()=>window.flyTest.state());const impact=state.lastImpact,qualifies=!impact.caught&&(!v2k||(impact.escape_onset_lead_ms!==null&&impact.escape_onset_lead_ms>0));trials.push({seed,aim,caught:impact.caught,lead_ms:impact.lead_ms,escape_onset_lead_ms:impact.escape_onset_lead_ms,qualifies});console.log('Hero selection',seed,JSON.stringify(impact));if(qualifies)break;assert(trials.length<10000);
  }
  selection.tried=trials.length;selection.trials=trials;selection.declaration_sha256=hash(declaration);writeFileSync(resolve(evidence,'hero-selection.json'),JSON.stringify({selection,code_sha:provenance.base_commit},null,2)+'\n');
  await reset(seed);let index=0;const observations=[];
  const capture=async()=>{await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));await page.screenshot({path:resolve(frames,`game-${String(index++).padStart(3,'0')}.png`)});observations.push(await page.evaluate(()=>({state:window.flyTest.state(),pill:document.getElementById('landing').textContent,stamp:document.getElementById('impact-label').textContent})));};
  for(let i=0;i<30;i++){await capture();await page.evaluate(()=>window.flyTest.advance(5));}
  const aim=await strike();
  while(!(await page.evaluate(()=>window.flyTest.state().replaying))){await page.evaluate(()=>window.flyTest.advance(1));await capture();}
  const log=await page.evaluate(()=>window.flyTest.log());assert.equal(log.neural_seed,seed);assert.deepEqual(log.inputs,[{tick:3000,...aim,hold_ms:selection.hold_ms}]);assert.equal(log.schema,'flybench.game-round.v3');
  const impact=observations.map(o=>o.state.frame.impact).find(Boolean);assert(impact&&!impact.caught);if(v2k)assert(impact.escape_onset_lead_ms>0);assert(observations.some(o=>o.state.frame.air));const liveFrames=index;
  const clock=new Date();await page.clock.install({time:clock});await page.clock.pauseAt(new Date(clock.getTime()+1000));await page.evaluate(()=>{window.flyTest.showReplay();window.flyTest.measureReplay(true);});const replayTicks=[];
  for(let i=0;i<60;i++){await page.clock.runFor(50);replayTicks.push(await page.evaluate(()=>window.flyTest.state().replayTick));await page.screenshot({path:resolve(frames,`game-${String(index++).padStart(3,'0')}.png`)});}
  const recorded=await page.evaluate(()=>window.flyTest.recordedFrames()),gfIndices=new Set(JSON.parse(readFileSync(resolve(dist,'data/brain.json'))).nodes.filter(n=>n.group==='giant fiber').map(n=>n.index)),gfSpikes=recorded.flatMap(f=>f.spikes).filter(e=>e.indices.some(i=>gfIndices.has(i))),gfLitFrames=replayTicks.map((tick,index)=>({index,tick,spikes:gfSpikes.filter(e=>e.tick<=tick&&tick-e.tick<=120)})).filter(f=>f.spikes.length);if(v2k)assert(gfLitFrames.length>0,'Recorded replay must visibly light the giant fiber');
  assert(new Set(replayTicks).size>20);assert(replayTicks.every((t,i)=>!i||t<replayTicks[i-1]||t-replayTicks[i-1]<=40));
  await page.evaluate(()=>{window.flyTest.measureReplay(false);window.flyTest.showRecorded('flash');});await page.clock.runFor(100);await page.screenshot({path:resolve(media,'game-still.png')});
  const recordedTick=await page.evaluate(()=>window.flyTest.state().replayTick),brain=await page.evaluate(()=>window.flyTest.brainSnapshot()),brainBytes=Buffer.from(brain.split(',')[1],'base64');writeFileSync(resolve(evidence,'hero-recorded-brain.png'),brainBytes);
  const card=await page.evaluate(async({brain,count})=>{const c=document.createElement('canvas');c.width=1200;c.height=630;const g=c.getContext('2d');g.fillStyle='#000';g.fillRect(0,0,1200,630);await document.fonts.load('900 72px Doto');const im=new Image();im.src=brain;await im.decode();g.drawImage(im,625,135,550,324);g.fillStyle='#e9ede6';g.font='900 72px Doto';g.fillText('Catch the fly',48,125);g.font='400 29px Atkinson';[`${count.toLocaleString('en-US')} neurons, wired as mapped`,'in a real male fruit fly.','Try to catch it.'].forEach((s,i)=>g.fillText(s,48,245+i*44));g.fillStyle='#7fefaa';g.font='400 24px Atkinson';g.fillText('alpi157.github.io/internet-vs-one-fly/',48,563);return c.toDataURL();},{brain,count:results.circuit_counts.game});writeFileSync(resolve(root,'apps/play/public/og-image.png'),Buffer.from(card.split(',')[1],'base64'));
  provenance.game={selection,neural_seed:seed,environment_seed:selection.environment_seed,log,impact,frames:index,live_frames:liveFrames,walk_frames:30,frame_duration_ms:50,walk_slowdown_factor:1,live_slowdown_factor:5,replay_seconds:3,replay_speed:profile.replay_speed,replay_loop:true,replay_ticks:replayTicks,source:`Authoritative UI input hook at tick 3000, fixed ${selection.hold_ms} ms ${v2k?'swat':'slap'}. Walk: five 10 ms intervals per 50 ms frame (real speed). Strike: one interval per frame (5x slower). Ordinary recorded replay: quarter speed, explicit loop.`,gf_lit_frames:gfLitFrames,observed_takeoff:observations.some(o=>o.state.frame.air),observed_countdown:observations.some(o=>o.pill.includes('ms')),observed_escape_stamp:observations.some(o=>o.stamp==='Escaped'),og:{source:selection.og_rule,brain_frame_sha256:hash(brainBytes),recorded_tick:recordedTick,kind:'Site card, no personal score'}};
  assert(provenance.game.observed_escape_stamp);provenance.external_requests=external;assert.equal(external.length,0);
  for(const file of ['apps/play/public/data/runtime.json','apps/play/public/data/game.json','apps/play/public/data/coupling/runtime.json','apps/play/public/data/coupling/strength-demo.json','apps/play/public/data/anatomy/manifest.json','apps/play/public/og-image.png','apps/play/public/favicon.svg','docs/media/game-still.png','docs/media/coupling-still.png','docs/media/coupling-hero.gif']){const b=readFileSync(resolve(root,file));provenance.assets[file]={...previous.assets[file],bytes:b.length,sha256:hash(b)};}
  provenance.capture_source_sha256=Object.fromEntries(['main.ts','coupling.ts','coupling-worker.ts','brain-view.ts','field.ts','style.css','game.ts','worker.ts'].map(f=>['apps/play/src/'+f,hash(readFileSync(resolve(root,'apps/play/src/'+f)))]));
  writeFileSync(resolve(evidence,'media-game-round.json'),JSON.stringify({log,impact,observations},null,2)+'\n');writeFileSync(provenancePath,JSON.stringify(provenance,null,2)+'\n');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
}
async function captureV2L(){
 const dry=process.argv.includes('--dry-run'),media=resolve(root,'docs/media'),evidence=resolve(root,'evidence/V2L'),frames='/tmp/flybench-v2l-media-frames';
 mkdirSync(frames,{recursive:true});mkdirSync(evidence,{recursive:true});
 const protocol=JSON.parse(readFileSync(resolve(root,'profiles/ui-v2l.json'))),selection={...protocol.hero},declaration=JSON.stringify(selection,null,2)+'\n';
 const declaredProtocol=JSON.parse(execFileSync('git',['show','78b554e:profiles/ui-v2l.json'],{cwd:root,encoding:'utf8'}));assert.deepEqual(protocol,declaredProtocol,'Protocol fixed before capture');
 writeFileSync(resolve(evidence,'hero-selection-declaration.json'),declaration);
 const profile=JSON.parse(readFileSync(resolve(dist,'data/game.json'))),results=JSON.parse(readFileSync(resolve(dist,'results-v2f.json')));
 const provenance={schema:'flybench.media.v2l.a01',capture_code_sha256:hash(readFileSync(import.meta.filename)),base_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),protocol_commit:'78b554e',viewport:{width:1440,height:900},display_only:true,history:'docs/media/history/v2k-provenance.json',game:{selection},lab:{},assets:{},engineering_fixture_probes:JSON.parse(readFileSync(resolve(evidence,'fixture-probes.json')))};
 const browser=await chromium.launch({headless:true}),{server,origin}=await serve(),external=[];
 try{
  const page=await browser.newPage({viewport:provenance.viewport});await page.route('**/*',r=>{const u=r.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return r.abort();}return r.continue();});
  await page.addInitScript(()=>{localStorage.setItem('flybench.intro.v5','seen');});
  await page.goto(origin+prefix+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);await page.evaluate(()=>{document.getElementById('sound').checked=false;return document.fonts.ready;});
  const reset=async seed=>{await page.evaluate(seed=>{for(const d of document.querySelectorAll('dialog[open]'))d.close();window.flyTest.resetSeed(seed);},seed);await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');};
  const strike=async()=>page.evaluate(hold=>{const b=window.flyTest.state().frame.body;window.flyTest.strike(b.x,b.y,hold);return {x:b.x,y:b.y};},selection.hold_ms);
  if(dry){await reset(101);await page.evaluate(()=>window.flyTest.advance(150));const aim=await strike();await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(()=>window.flyTest.recordedFrames().length>0);await page.evaluate(()=>{window.flyTest.showReplay();window.flyTest.showRecorded('flash');});await page.waitForTimeout(100);const observed=await page.evaluate(()=>({state:window.flyTest.state(),frames:window.flyTest.recordedFrames(),brain:window.flyTest.brainSnapshot()}));writeFileSync(resolve(root,'apps/play/public/intro-brain.png'),Buffer.from(observed.brain.split(',')[1],'base64'));await page.locator('#timeline').screenshot({path:resolve(root,'apps/play/public/intro-timeline.png')});delete observed.brain;writeFileSync(resolve(evidence,'hero-dry-run.json'),JSON.stringify({excluded_seed:101,aim,...observed,status:'PASS'},null,2)+'\n');return;}
  const trials=[];let seed=selection.first_seed;
  for(;;seed++){
   await reset(seed);await page.evaluate(()=>window.flyTest.advance(150));const aim=await strike();await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(()=>window.flyTest.recordedFrames().length>0);
   const impact=await page.evaluate(()=>window.flyTest.state().lastImpact),qualifies=!impact.caught&&impact.escape_onset_lead_ms>0;
   trials.push({seed,aim,caught:impact.caught,lead_ms:impact.lead_ms,escape_onset_lead_ms:impact.escape_onset_lead_ms,qualifies});console.log('Hero selection',seed,impact);if(qualifies)break;assert(trials.length<10000);
  }
  selection.tried=trials.length;selection.trials=trials;selection.declaration_sha256=hash(declaration);
  writeFileSync(resolve(evidence,'hero-selection.json'),JSON.stringify({selection,code_sha:provenance.base_commit},null,2)+'\n');
  const clock=new Date();await page.clock.install({time:clock});await page.clock.pauseAt(new Date(clock.getTime()+1000));
  await reset(seed);let index=0;const observations=[];
  const capture=async()=>{await page.clock.runFor(50);await page.screenshot({path:resolve(frames,`game-${String(index++).padStart(3,'0')}.png`)});observations.push(await page.evaluate(()=>({state:window.flyTest.state(),pill:document.getElementById('landing').textContent,stamp:document.getElementById('impact-label').hidden?'':document.getElementById('stamp-word').textContent})));};
  for(let i=0;i<30;i++){await capture();await page.evaluate(()=>window.flyTest.advance(5));}
  const aim=await strike();
  while(!(await page.evaluate(()=>window.flyTest.recordedFrames().length))){await page.evaluate(()=>window.flyTest.advance(1));await capture();}
  // Finish the declared 1.6 s impact stamp using the presentation clock. The
  // authoritative simulation is paused at the same post-impact boundary as play.
  while(await page.evaluate(()=>window.flyTest.state().stamp))await capture();
  const log=await page.evaluate(()=>window.flyTest.log()),liveFrames=index;
  assert.equal(log.schema,'flybench.game-round.v4');assert.deepEqual(log.inputs,[{tick:3000,...aim,hold_ms:600}]);
  const impact=observations.map(o=>o.state.frame.impact).find(Boolean);assert(impact&&!impact.caught&&impact.escape_onset_lead_ms>0);
  await page.evaluate(()=>{window.flyTest.showReplay();window.flyTest.measureReplay(true);});const replayTicks=[];
  for(let i=0;i<60;i++){await capture();replayTicks.push(await page.evaluate(()=>window.flyTest.state().replayTick));}
  const recorded=await page.evaluate(()=>window.flyTest.recordedFrames()),gfIndices=new Set(JSON.parse(readFileSync(resolve(dist,'data/brain.json'))).nodes.filter(n=>n.group==='giant fiber').map(n=>n.index)),gfSpikes=recorded.flatMap(f=>f.spikes).filter(e=>e.indices.some(i=>gfIndices.has(i))),gfLitFrames=replayTicks.map((tick,index)=>({index,tick,spikes:gfSpikes.filter(e=>e.tick<=tick&&tick-e.tick<=120)})).filter(f=>f.spikes.length);
  assert(gfLitFrames.length>0);assert(new Set(replayTicks).size>20);assert(replayTicks.every((t,i)=>!i||t<replayTicks[i-1]||t-replayTicks[i-1]<=40));
  await page.evaluate(()=>{window.flyTest.measureReplay(false);window.flyTest.showRecorded('flash');});await page.clock.runFor(100);await page.screenshot({path:resolve(media,'game-still.png')});
  const recordedTick=await page.evaluate(()=>window.flyTest.state().replayTick),brain=await page.evaluate(()=>window.flyTest.brainSnapshot()),brainBytes=Buffer.from(brain.split(',')[1],'base64');
  writeFileSync(resolve(evidence,'hero-recorded-brain.png'),brainBytes);writeFileSync(resolve(root,'apps/play/public/intro-brain.png'),brainBytes);
  await page.locator('#timeline').screenshot({path:resolve(root,'apps/play/public/intro-timeline.png')});
  const card=await page.evaluate(async({brain,count})=>{const c=document.createElement('canvas');c.width=1200;c.height=630;const g=c.getContext('2d');g.fillStyle='#000';g.fillRect(0,0,1200,630);await document.fonts.load('900 72px Doto');const im=new Image();im.src=brain;await im.decode();g.drawImage(im,625,135,550,324);g.fillStyle='#e9ede6';g.font='900 72px Doto';g.fillText('Catch the fly',48,125);g.font='400 29px Atkinson';[`${count.toLocaleString('en-US')} simulated neurons`,'A fly brain from its real wiring.','Try to swat it.'].forEach((s,i)=>g.fillText(s,48,245+i*44));g.fillStyle='#7fefaa';g.font='400 24px Atkinson';g.fillText('alpi157.github.io/internet-vs-one-fly/',48,563);return c.toDataURL();},{brain,count:results.circuit_counts.game});writeFileSync(resolve(root,'apps/play/public/og-image.png'),Buffer.from(card.split(',')[1],'base64'));
  provenance.game={selection,neural_seed:seed,environment_seed:selection.environment_seed,log,impact,frames:index,live_frames:liveFrames,walk_frames:30,frame_duration_ms:50,walk_slowdown_factor:1,live_slowdown_factor:5,replay_seconds:3,replay_speed:.25,replay_loop:true,replay_ticks:replayTicks,source:'Authoritative current-position swat after 1500 ms at real speed. Strike intervals shown 5x slower. Stamp lasts 1.6 presentation seconds. Replay uses ordinary quarter speed; every neural frame is recorded.',gf_lit_frames:gfLitFrames,quiet_walk_takeoffs:observations.filter((o,i)=>i<30&&o.state.frame.onset).map(o=>o.state.frame.tick),observed_takeoff:observations.some(o=>o.state.frame.air),observed_countdown:observations.some(o=>o.pill.includes('ms')),observed_escape_stamp:observations.some(o=>o.stamp==='Escaped'),og:{source:selection.og_rule,brain_frame_sha256:hash(brainBytes),recorded_tick:recordedTick,kind:'Site card, no personal score'},intro:{brain:'Same recorded maximum-spike hero frame as OG',timeline:'Canvas snapshot of its three recorded tracks',recorded_tick:recordedTick}};
  // Five seconds of an actual caught hand for the first half of the review clip.
  await reset(2);await page.evaluate(()=>window.flyTest.strike(2,0,0));
  for(let i=0;i<100;i++){if(i<40)await page.evaluate(()=>window.flyTest.advance(1));await page.clock.runFor(50);await page.screenshot({path:resolve(frames,`review-${String(i).padStart(3,'0')}.png`)});}
  const caughtLog=await page.evaluate(()=>window.flyTest.log()),caughtImpact=await page.evaluate(()=>window.flyTest.state().lastImpact);assert(caughtImpact.caught);
  provenance.review={seconds:10,frames:200,frame_duration_ms:50,caught:{seed:2,log:caughtLog,impact:caughtImpact,source_frames:[0,99]},escaped:{seed,source:'First 100 hero source frames',source_frames:[0,99]}};
  for(let i=0;i<100;i++)writeFileSync(resolve(frames,`review-${String(i+100).padStart(3,'0')}.png`),readFileSync(resolve(frames,`game-${String(i).padStart(3,'0')}.png`)));
  await page.clock.resume();await page.locator('[data-wiring]:visible').first().click();await page.waitForFunction(()=>window.couplingTest?.ready());
  provenance.lab={coupling:results.registered_coupling,neural_seed:results.lab_seeds.neural,environment_seed:results.lab_seeds.environment,sign:JSON.parse(readFileSync(resolve(dist,'data/coupling/runtime.json'))).null_selection,strength:JSON.parse(readFileSync(resolve(dist,'data/coupling/strength-demo.json'))),observations:[],frames:80,frame_duration_ms:100,story_steps:[1,2],registered_medians:results.registered_story};
  let labIndex=0;
  for(const step of [1,2]){await page.evaluate(step=>window.couplingTest.step(step),step);await page.waitForFunction(()=>window.couplingTest.ready());await page.waitForFunction(()=>window.couplingTest.state().panels[0].tick*.0005>=2,null,{timeout:60000});
   for(let i=0;i<40;i++){const start=Date.now();await page.screenshot({path:resolve(frames,`lab-${String(labIndex++).padStart(3,'0')}.png`)});await page.waitForTimeout(Math.max(0,100-(Date.now()-start)));}
   provenance.lab.observations.push(await page.evaluate(()=>window.couplingTest.state()));if(step===1)await page.screenshot({path:resolve(media,'coupling-still.png')});
  }
  provenance.external_requests=external;assert.equal(external.length,0);
  for(const file of ['apps/play/public/data/runtime.json','apps/play/public/data/game.json','apps/play/public/data/coupling/runtime.json','apps/play/public/data/coupling/game-v2.8.json','apps/play/public/data/coupling/strength-demo.json','apps/play/public/data/anatomy/manifest.json','apps/play/public/og-image.png','apps/play/public/intro-brain.png','apps/play/public/intro-timeline.png','docs/media/game-still.png','docs/media/coupling-still.png']){const b=readFileSync(resolve(root,file));provenance.assets[file]={bytes:b.length,sha256:hash(b)};}
  provenance.capture_source_sha256=Object.fromEntries(['main.ts','coupling.ts','coupling-worker.ts','brain-view.ts','field.ts','style.css','game.ts','worker.ts','intro.ts','chrome.ts','outcome.ts'].map(f=>['apps/play/src/'+f,hash(readFileSync(resolve(root,'apps/play/src/'+f)))]));
  writeFileSync(resolve(evidence,'media-game-round.json'),JSON.stringify({log,impact,observations},null,2)+'\n');writeFileSync(resolve(media,'media-provenance.json'),JSON.stringify(provenance,null,2)+'\n');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
}

async function encodeV2LReview(){
 const frames='/tmp/flybench-v2l-media-frames',provenancePath=resolve(root,'docs/media/media-provenance.json'),provenance=JSON.parse(readFileSync(provenancePath));
 const source=Array.from({length:200},(_,i)=>'data:image/png;base64,'+readFileSync(resolve(frames,`video-${String(i).padStart(3,'0')}.png`)).toString('base64'));
 const browser=await chromium.launch({headless:true}),{server,origin}=await serve();
 try{
  const page=await browser.newPage();await page.goto(origin+prefix+'404.html');
  const movie=await page.evaluate(async frames=>{
   const canvas=document.createElement('canvas');canvas.width=960;canvas.height=600;document.body.replaceChildren(canvas);const g=canvas.getContext('2d');
   const images=await Promise.all(frames.map(src=>new Promise(resolve=>{const im=new Image();im.onload=()=>resolve(im);im.src=src;})));
   const mime=['video/webm;codecs=vp9','video/webm'].find(t=>MediaRecorder.isTypeSupported(t));if(!mime)throw Error('Chromium review encoder unavailable');
   const stream=canvas.captureStream(20),recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:2000000}),chunks=[];
   recorder.ondataavailable=e=>chunks.push(e.data);const stopped=new Promise(resolve=>recorder.onstop=resolve);
   g.drawImage(images[0],0,0);recorder.start();const start=performance.now(),at=[];
   for(let i=0;i<images.length;i++){await new Promise(r=>setTimeout(r,Math.max(0,start+i*50-performance.now())));g.drawImage(images[i],0,0);at.push(performance.now()-start);}
   await new Promise(r=>setTimeout(r,Math.max(0,start+10000-performance.now())));const elapsed=performance.now()-start;recorder.stop();await stopped;stream.getTracks().forEach(t=>t.stop());
   const bytes=new Uint8Array(await new Blob(chunks,{type:mime}).arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
   return {base64:btoa(binary),mime,elapsed_ms:elapsed,presentation_timestamps_ms:at};
  },source);
  const bytes=Buffer.from(movie.base64,'base64');delete movie.base64;writeFileSync(resolve(root,'evidence/V2L/review.webm'),bytes);
  provenance.review={...provenance.review,...movie,bytes:bytes.length,sha256:hash(bytes),width:960,height:600,source:'Two sequences of 100 captured UI frames, caught then escaped, encoded at 20 frames per second for 10 seconds. No neural re-execution or invented observations.'};
  assert(movie.elapsed_ms>=9990&&movie.elapsed_ms<10200);writeFileSync(resolve(root,'evidence/V2L/review-clip.json'),JSON.stringify(provenance.review,null,2)+'\n');writeFileSync(provenancePath,JSON.stringify(provenance,null,2)+'\n');console.log('Review clip',bytes.length,'bytes;',movie.elapsed_ms,'ms');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
}

async function captureV2N(){
 const sourceCommit='1b670a9d371ce406a1865aa5c4b91085b4f87fea',dry=process.argv.includes('--dry-run');
 const git=(...args)=>execFileSync('git',args,{cwd:root});
 assert.equal(git('rev-parse','v2m-accepted^{commit}').toString().trim(),sourceCommit);
 assert.equal(git('diff',sourceCommit,'--','apps/play/src','apps/play/public').length,0,'Capture only accepted, unmodified sources and public assets');
 const media=resolve(root,'docs/media'),evidence=resolve(root,'evidence/V2N'),frames=resolve(evidence,'source-frames');
 mkdirSync(evidence,{recursive:true});
 const previous=JSON.parse(readFileSync(resolve(media,'history/v2m-provenance.json')));
 const selection={...previous.game.selection};for(const k of ['tried','trials','declaration_sha256'])delete selection[k];
 assert.deepEqual(selection,JSON.parse(readFileSync(resolve(root,'profiles/ui-v2l.json'))).hero);
 const declaration=JSON.stringify(selection,null,2)+'\n';
 writeFileSync(resolve(evidence,'hero-selection-declaration.json'),declaration);
 const sourcePaths=git('ls-tree','-r','--name-only',sourceCommit,'--','apps/play/src').toString().trim().split('\n');
 const sourceHashes=Object.fromEntries(sourcePaths.map(p=>{const data=readFileSync(resolve(root,p));assert.equal(hash(data),hash(git('show',sourceCommit+':'+p)),p);return [p,hash(data)];}));
 const profile=JSON.parse(readFileSync(resolve(dist,'data/game.json'))),results=JSON.parse(readFileSync(resolve(dist,'results-v2f.json')));
 assert.deepEqual(profile,JSON.parse(git('show',sourceCommit+':apps/play/public/data/game.json')));
 assert.equal(profile.profile_id,'flybench.game.v2.9');assert.equal(profile.takeoff_speed,.018);assert.equal(profile.takeoff_duration_ms,330);
 const browser=await chromium.launch({headless:true}),{server,origin}=await serve(),external=[];
 const setup=async dpr=>{
  const page=await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:dpr});
  await page.route('**/*',r=>{const u=r.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return r.abort();}return r.continue();});
  await page.addInitScript(()=>localStorage.setItem('flybench.intro.v5','seen'));
  await page.goto(origin+prefix+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);
  await page.evaluate(()=>{document.getElementById('sound').checked=false;return document.fonts.ready;});
  return page;
 };
 const reset=async page=>{await page.evaluate(()=>{for(const d of document.querySelectorAll('dialog[open]'))d.close();window.flyTest.resetSeed(1);});await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');};
 const strike=async page=>page.evaluate(()=>{const b=window.flyTest.state().frame.body;window.flyTest.strike(b.x,b.y,600);return {x:b.x,y:b.y};});
 const geometry=async(page,selectors)=>page.evaluate(selectors=>selectors.map(s=>{const e=document.querySelector(s),b=e.getBoundingClientRect();return {selector:s,x:b.x,y:b.y,width:b.width,height:b.height,visible:e.checkVisibility()};}),selectors);
 try{
  if(dry){
   const probes=[];
   for(const dpr of [1,2]){
    const page=await setup(dpr);await reset(page);await page.evaluate(()=>window.flyTest.advance(150));await strike(page);await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(()=>window.flyTest.recordedFrames().length>0);
    const log=await page.evaluate(()=>window.flyTest.log()),recorded=await page.evaluate(()=>window.flyTest.recordedFrames()),impact=await page.evaluate(()=>window.flyTest.state().lastImpact);
    assert(!impact.caught&&impact.escape_onset_lead_ms>0,'STOP: frozen seed 1 no longer qualifies; never try another seed');
    assert.deepEqual(impact,previous.game.impact);assert.deepEqual(log,previous.game.log);
    const clock=new Date();await page.clock.install({time:clock});await page.clock.pauseAt(new Date(clock.getTime()+1000));
    await page.evaluate(()=>{window.flyTest.showReplay();window.flyTest.measureReplay(true);});
    const ticks=[],playheads=[];for(let i=0;i<60;i++){await page.clock.runFor(50);ticks.push(await page.evaluate(()=>window.flyTest.state().replayTick));playheads.push(await page.locator('#replay-playhead').inputValue());}
    const layout=await geometry(page,['#table','#brain-panel','#brain-host','#timeline','#replay-playhead','.playback']);
    const brain=await page.locator('#brain-host .brain-image canvas').first().evaluate(c=>({width:c.width,height:c.height,cssWidth:c.getBoundingClientRect().width,cssHeight:c.getBoundingClientRect().height}));
    assert(brain.width*brain.height<=1048576);
    await page.screenshot({path:resolve(evidence,`preflight-dpr${dpr}.png`)});
    await page.clock.resume();await page.locator('[data-wiring]:visible').first().click();await page.waitForFunction(()=>window.couplingTest?.ready()&&window.couplingTest.state().rendering.slice(0,2).every(r=>r.ready));
    const labLayout=await geometry(page,['.story-layout','#story-live','.lab-brains','#lab-brain-0','#lab-brain-1']);
    const labState=await page.evaluate(()=>window.couplingTest.state());assert.equal(labState.scale,.039);assert.equal(labState.family,'N-SIGN');
    const labCanvases=await page.locator('#story-live canvas[aria-label="Recorded neural activity on MaleCNS anatomy"]').evaluateAll(cs=>cs.map(c=>({width:c.width,height:c.height,cssWidth:c.getBoundingClientRect().width,cssHeight:c.getBoundingClientRect().height})));
    assert(labCanvases.every(c=>c.width*c.height<=32768));
    await page.screenshot({path:resolve(evidence,`preflight-lab-dpr${dpr}.png`)});
    probes.push({device_scale_factor:dpr,log,impact,recorded_sha256:hash(JSON.stringify(recorded)),replay_ticks:ticks,playheads,layout,brain,lab_layout:labLayout,lab_canvases:labCanvases});await page.close();
   }
   const differences=['log','impact','recorded_sha256','replay_ticks','playheads','layout','lab_layout'].filter(key=>JSON.stringify(probes[0][key])!==JSON.stringify(probes[1][key]));
   const report={status:'PASS',capture_source_commit:sourceCommit,device_scale_factor:differences.length?1:2,differences,reason:differences.length?'Use 1x because DPR changed '+differences.join(', '):'1x and 2x have identical game/lab CSS layouts, authoritative log, impact, recorded frames, replay ticks and advancing scrubber values. Game BrainView uses 1,008,000 pixels at 2x, within its unchanged 1,048,576-pixel budget. Lab activity respects its existing 32,768-pixel cap at both DPRs. Only raster resolution changes.',probes};
   writeFileSync(resolve(evidence,'scale-factor-preflight.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS seed 1 qualifies at both DPRs; selected DPR',report.device_scale_factor);return;
  }
  const preflight=JSON.parse(readFileSync(resolve(evidence,'scale-factor-preflight.json')));assert.equal(preflight.status,'PASS');
  assert(!(await import('node:fs')).existsSync(frames),'Use a fresh V2N capture directory');mkdirSync(frames);
  const page=await setup(preflight.device_scale_factor),clock=new Date();await page.clock.install({time:clock});await page.clock.pauseAt(new Date(clock.getTime()+1000));await reset(page);
  let index=0;const observations=[];
  const capture=async()=>{await page.clock.runFor(50);await page.screenshot({path:resolve(frames,`game-${String(index++).padStart(3,'0')}.png`)});observations.push(await page.evaluate(()=>({state:window.flyTest.state(),pill:document.getElementById('landing').textContent,stamp:document.getElementById('impact-label').hidden?'':document.getElementById('stamp-word').textContent})));};
  for(let i=0;i<30;i++){await capture();await page.evaluate(()=>window.flyTest.advance(5));}
  const aim=await strike(page);
  while(!(await page.evaluate(()=>window.flyTest.recordedFrames().length))){await page.evaluate(()=>window.flyTest.advance(1));await capture();}
  while(await page.evaluate(()=>window.flyTest.state().stamp))await capture();
  const log=await page.evaluate(()=>window.flyTest.log()),impact=await page.evaluate(()=>window.flyTest.state().lastImpact),liveFrames=index;
  assert(!impact.caught&&impact.escape_onset_lead_ms>0,'STOP: frozen seed 1 no longer qualifies');assert.deepEqual(impact,previous.game.impact);assert.deepEqual(log,previous.game.log);
  assert.deepEqual(log.inputs,[{tick:3000,...aim,hold_ms:600}]);
  await page.evaluate(()=>{window.flyTest.showReplay();window.flyTest.measureReplay(true);});const replayTicks=[],playheads=[];
  for(let i=0;i<60;i++){await capture();replayTicks.push(await page.evaluate(()=>window.flyTest.state().replayTick));playheads.push(Number(await page.locator('#replay-playhead').inputValue()));}
  assert(new Set(replayTicks).size>20&&new Set(playheads).size>20);assert(replayTicks.every((t,i)=>!i||t<replayTicks[i-1]||t-replayTicks[i-1]<=40));assert(await page.locator('#replay-playhead').isVisible());assert.equal(await page.locator('#replay-speed').inputValue(),'0.25');
  const recorded=await page.evaluate(()=>window.flyTest.recordedFrames()),gfIndices=new Set(JSON.parse(readFileSync(resolve(dist,'data/brain.json'))).nodes.filter(n=>n.group==='giant fiber').map(n=>n.index)),gfSpikes=recorded.flatMap(f=>f.spikes).filter(e=>e.indices.some(i=>gfIndices.has(i))),gfLitFrames=replayTicks.map((tick,index)=>({index,tick,spikes:gfSpikes.filter(e=>e.tick<=tick&&tick-e.tick<=120)})).filter(f=>f.spikes.length);
  assert(gfLitFrames.length>0);
  // The still is one of these exact captured replay frames, at maximum recorded activity.
  const stillIndex=liveFrames+replayTicks.reduce((best,t,i)=>{const count=t=>recorded.find(f=>f.tick===t)?.spikes.reduce((n,e)=>n+e.indices.length,0)??0;return count(t)>count(replayTicks[best])?i:best;},0);
  writeFileSync(resolve(media,'game-still.png'),readFileSync(resolve(frames,`game-${String(stillIndex).padStart(3,'0')}.png`)));
  const provenance={schema:'flybench.media.v2n',capture_source_commit:sourceCommit,capture_source_sha256:sourceHashes,capture_code_sha256:hash(readFileSync(import.meta.filename)),viewport:{width:1440,height:900},device_scale_factor:preflight.device_scale_factor,scale_factor_reason:preflight.reason,scale_factor_evidence:'evidence/V2N/scale-factor-preflight.json',display_only:true,history:'docs/media/history/v2m-provenance.json',game:{selection:{...selection,tried:1,trials:[{seed:1,aim,caught:impact.caught,lead_ms:impact.lead_ms,escape_onset_lead_ms:impact.escape_onset_lead_ms,qualifies:true}],declaration_sha256:hash(declaration)},neural_seed:1,environment_seed:8128,profile_id:profile.profile_id,takeoff:'T0',log,impact,frames:index,live_frames:liveFrames,walk_frames:30,frame_duration_ms:50,walk_slowdown_factor:1,live_slowdown_factor:5,replay_seconds:3,replay_speed:.25,replay_loop:true,replay_ticks:replayTicks,replay_playheads:playheads,replay_controls_visible:true,gf_lit_frames:gfLitFrames,observed_takeoff:observations.some(o=>o.state.frame.air),observed_countdown:observations.some(o=>o.pill.includes('ms')),observed_escape_stamp:observations.some(o=>o.stamp==='Escaped'),still_source_frame:stillIndex},lab:{coupling:results.registered_coupling,neural_seed:results.lab_seeds.neural,environment_seed:results.lab_seeds.environment,sign:JSON.parse(readFileSync(resolve(dist,'data/coupling/runtime.json'))).null_selection,strength:JSON.parse(readFileSync(resolve(dist,'data/coupling/strength-demo.json'))),observations:[],frames:80,frame_duration_ms:100,story_steps:[1,2],registered_medians:results.registered_story,still_source_frame:39},assets:{}};
  assert.equal(provenance.lab.coupling,.039);assert.equal(provenance.lab.neural_seed,2027101401);assert.equal(provenance.lab.environment_seed,8128);
  writeFileSync(resolve(evidence,'media-game-round.json'),JSON.stringify({log,impact,observations,recorded},null,2)+'\n');
  await page.clock.resume();await page.locator('[data-wiring]:visible').first().click();await page.waitForFunction(()=>window.couplingTest?.ready());let labIndex=0;
  for(const step of [1,2]){
   await page.evaluate(step=>window.couplingTest.step(step),step);await page.waitForFunction(()=>window.couplingTest.ready());await page.waitForFunction(()=>window.couplingTest.state().panels[0].tick*.0005>=2,null,{timeout:60000});
   for(let i=0;i<40;i++){const start=Date.now();await page.screenshot({path:resolve(frames,`lab-${String(labIndex++).padStart(3,'0')}.png`)});await page.waitForTimeout(Math.max(0,100-(Date.now()-start)));}
   const state=await page.evaluate(()=>window.couplingTest.state());assert.equal(state.scale,.039);assert.equal(state.step,step);provenance.lab.observations.push(state);
  }
  writeFileSync(resolve(media,'coupling-still.png'),readFileSync(resolve(frames,'lab-039.png')));
  provenance.external_requests=external;assert.equal(external.length,0);
  const rawInventory=readFileSync(resolve(evidence,'raw-records-before.json'));
  provenance.preservation={raw_inventory:{path:'evidence/V2N/raw-records-before.json',bytes:rawInventory.length,sha256:hash(rawInventory),files:Object.keys(JSON.parse(rawInventory).files).length}};
  for(const file of ['game-still.png','coupling-still.png']){const p='docs/media/'+file,b=readFileSync(resolve(root,p));provenance.assets[p]={bytes:b.length,sha256:hash(b),size:[1440*preflight.device_scale_factor,900*preflight.device_scale_factor]};}
  provenance.source_frames_sha256=Object.fromEntries((await import('node:fs')).readdirSync(frames).sort().map(p=>[p,hash(readFileSync(resolve(frames,p)))]));
  writeFileSync(resolve(media,'media-provenance.json'),JSON.stringify(provenance,null,2)+'\n');console.log('V2N capture complete:',index,'game frames,',labIndex,'lab frames');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
}

if(process.argv.includes('--v2n'))await captureV2N();else if(process.argv.includes('--v2l-review'))await encodeV2LReview();else if(process.argv.includes('--v2l'))await captureV2L();else if(process.argv.includes('--a03')||process.argv.includes('--v2k'))await captureA03();else await legacyCapture();
