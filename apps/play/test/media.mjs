import assert from 'node:assert/strict';
import {chromium} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync,rmSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {serve,root,dist,prefix} from './site-server.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
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
