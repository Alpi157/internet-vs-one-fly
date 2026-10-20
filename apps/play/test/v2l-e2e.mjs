import assert from 'node:assert/strict';
import {chromium,firefox,webkit} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {serve,root,prefix} from './site-server.mjs';
import {overlaps} from './overlap.mjs';
import {replayLog} from '../src/game.ts';
import {buffer,runtime,load} from './owner-walking.ts';
const dry=process.argv.includes('--dry'),profile=load('profiles/game-v2.9.json');
const out=resolve(root,process.env.FLYBENCH_V2L_BROWSER_OUT??(dry?'evidence/V2L/dry-browser':'evidence/V2L/browser'));mkdirSync(out,{recursive:true});
const axe=readFileSync(resolve(root,'apps/play/node_modules/axe-core/axe.min.js'),'utf8'),reports=[];
const code_sha=execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
const {server,origin}=await serve(),url=origin+prefix;
const viewports=[{width:390,height:844},{width:1280,height:720},{width:1366,height:768},{width:1440,height:900},{width:1920,height:1080},{width:2560,height:1440}];
const fps=page=>page.evaluate(()=>new Promise(resolve=>{let count=0;const start=performance.now();function frame(t){count++;if(t-start>=3000)resolve(count/((t-start)/1000));else requestAnimationFrame(frame);}requestAnimationFrame(frame);}));
try{for(const [name,engine] of Object.entries({chromium,firefox,webkit})){
 if((dry&&name!==(process.env.FLYBENCH_BROWSER??'chromium'))||(process.env.FLYBENCH_BROWSER&&process.env.FLYBENCH_BROWSER!==name))continue;
 const browser=await engine.launch({headless:true});
 try{for(const viewport of viewports)for(const locale of dry?['en-US']:['en-US','ru-RU','de-DE']){
  if((process.env.FLYBENCH_WIDTH&&viewport.width!==Number(process.env.FLYBENCH_WIDTH))||(process.env.FLYBENCH_LOCALE&&locale!==process.env.FLYBENCH_LOCALE))continue;
  const context=await browser.newContext({viewport,locale,serviceWorkers:'block'}),page=await context.newPage(),external=[],errors=[],states=[];
  const report={browser:name,version:browser.version(),viewport,locale,status:'RUNNING',states,external_requests:external,errors};reports.push(report);
  const save=()=>writeFileSync(resolve(out,`matrix-${name}.json`),JSON.stringify({code_sha,reports},null,2)+'\n');
  await context.route('**/*',route=>{const u=route.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return route.abort();}return route.continue();});
  await context.addInitScript(()=>{try{localStorage.setItem('flybench.intro.v5','seen');}catch{}window.canvasText=new Set();const fill=CanvasRenderingContext2D.prototype.fillText;CanvasRenderingContext2D.prototype.fillText=function(text,...args){window.canvasText.add(String(text));return fill.call(this,text,...args);};});
  page.on('pageerror',e=>errors.push(String(e)));
  const go=async()=>{await page.goto(url+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);await page.evaluate(()=>{document.getElementById('sound').checked=false;return document.fonts.ready;});};
  const reset=async seed=>{await page.evaluate(seed=>{for(const d of document.querySelectorAll('dialog[open]'))d.close();window.flyTest.resetSeed(seed);},seed);await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');};
  async function record({seed=1,warmup=0,hold=0,aim}={}){
   await reset(seed);if(warmup)await page.evaluate(n=>window.flyTest.advance(n),warmup);
   await page.evaluate(({hold,aim})=>{const b=window.flyTest.state().frame.body;window.flyTest.strike(aim?.x??b.x,aim?.y??b.y,hold);},{hold,aim});await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(()=>window.flyTest.recordedFrames().length>0);
   return page.evaluate(()=>window.flyTest.state().lastImpact);
  }
  async function shot(state,{scroll=true}={}){
   if(scroll)await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(60);
   const collision=await overlaps(page),file=`${name}-${viewport.width}x${viewport.height}-${locale}-${state}.png`;
   const bounds=await page.evaluate(()=>{
    const modal=document.querySelector('dialog[open]'),root=modal??document.querySelector('#coupling-host:not([hidden])')??document.querySelector('main');
    const mustFitVertically=!!modal||!!root.closest('#app');
    const controls=[];for(const e of root.querySelectorAll('button,a,input,select,summary,label:has(input),[role=button],[role=tab]')){
     if(e.closest('[hidden]')||!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||e.closest('.sr-only'))continue;
     const closed=e.closest('details:not([open])');if(closed&&!closed.querySelector('summary')?.contains(e))continue;
     const r=e.getBoundingClientRect();if(r.width<1||r.height<1)continue;
     const inView=r.bottom>0&&r.top<innerHeight;
     controls.push({label:e.getAttribute('aria-label')||e.textContent.trim().slice(0,80),x:r.x,y:r.y,right:r.right,bottom:r.bottom,in_view:inView,contained:r.left>=-.75&&r.right<=innerWidth+.75&&(!mustFitVertically||r.top>=-.75&&r.bottom<=innerHeight+.75)});
    }
    let arena=null;if(window.flyTest&&document.getElementById('app')&&!document.getElementById('app').hidden){arena=window.flyTest.arenaBounds();arena.contained=arena.x>=-.75&&arena.y>=-.75&&arena.right<=innerWidth+.75&&arena.bottom<=innerHeight+.75;}
    return {arena,controls};
   });
   await page.screenshot({path:resolve(out,file)});await page.addScriptTag({content:axe});
   const accessibility=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));});
   const text=await page.evaluate(()=>[document.body.innerText,...[...document.querySelectorAll('[alt],[aria-label]')].map(e=>e.getAttribute('alt')||e.getAttribute('aria-label')),...window.canvasText].join('\n'));
   const localeErrors=[...text.matchAll(/\b5[ .\u00a0\u202f]555\b|\b\d+,\d{1,2}\b/g)].map(m=>m[0]);
   const result={state,file,overlap:collision,axe:accessibility,bounds,locale_errors:localeErrors,external_requests:external.slice()};states.push(result);save();
   assert.equal(collision.collisions.length,0,JSON.stringify({state,collisions:collision.collisions}));assert.equal(accessibility.length,0,JSON.stringify(accessibility));assert.equal(localeErrors.length,0,JSON.stringify(localeErrors));assert.equal(external.length,0);
   assert(bounds.controls.every(b=>b.contained),JSON.stringify({state,bad:bounds.controls.filter(b=>!b.contained)}));
   if(bounds.arena)assert(bounds.arena.contained,JSON.stringify({state,arena:bounds.arena}));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Horizontal overflow');
   // Long reading/story pages scroll by design. Visit every ordinary action
   // control and verify that it can be brought fully inside this same viewport.
   result.scrolled_control_bounds=await page.evaluate(()=>{
    if(document.querySelector('dialog[open]')||!document.querySelector('#coupling-host:not([hidden]),.science-page'))return [];
    const host=document.querySelector('#coupling-host:not([hidden])')??document.querySelector('.science-page'),saved={x:scrollX,y:scrollY},results=[];
    for(const e of host.querySelectorAll('button,a,input,select,summary,label:has(input),[role=button],[role=tab]')){
     if(e.closest('[hidden]')||!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))continue;
     const closed=e.closest('details:not([open])');if(closed&&!closed.querySelector('summary')?.contains(e))continue;
     e.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});const r=e.getBoundingClientRect();if(r.width<1||r.height<1)continue;
     results.push({label:(e.getAttribute('aria-label')||e.textContent.trim()).slice(0,80),x:r.x,y:r.y,right:r.right,bottom:r.bottom,contained:r.x>=-.75&&r.right<=innerWidth+.75&&r.y>=-.75&&r.bottom<=innerHeight+.75});
    }
    scrollTo(saved.x,saved.y);return results;
   });
   assert(result.scrolled_control_bounds.every(b=>b.contained),JSON.stringify({state,scrolled:result.scrolled_control_bounds.filter(b=>!b.contained)}));save();
  }
  try{
   await go();
   await page.evaluate(()=>{const a=document.createElement('button'),b=document.createElement('span');a.id='overlap-probe';a.style.cssText='position:fixed;top:0;left:0;width:100px;height:50px;z-index:999';a.textContent='Probe';b.id='overlap-probe-text';b.style.cssText='position:fixed;top:10px;left:10px;z-index:1000';b.textContent='Collision';document.body.append(a,b);});assert((await overlaps(page)).collisions.some(c=>c.a.label==='Collision'||c.b.label==='Collision'));await page.evaluate(()=>{document.getElementById('overlap-probe').remove();document.getElementById('overlap-probe-text').remove();});
   await page.click('#intro-help');await page.locator('#intro-next').focus();await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'intro-skip');await page.keyboard.press('Shift+Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'intro-next');await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>document.activeElement.id),'intro-help');report.intro_focus_trap_and_return=true;
   for(let card=1;card<=3;card++){await page.evaluate(n=>window.flyTest.intro(n),card);await shot('intro-'+card);await page.keyboard.press('Escape');}
   await page.click('#start');await page.evaluate(()=>window.flyTest.advance(150));await shot('idle');
   await page.locator('#table').focus();await page.keyboard.down('Space');await page.waitForFunction(()=>document.getElementById('hold-tile').classList.contains('ready'));assert.equal(await page.locator('#announcer').innerText(),'Big, slow hand ready');await shot('hold');await page.keyboard.up('Space');
   const caught=await record({seed:2,aim:{x:2,y:0}});assert(caught.caught);await page.evaluate(()=>window.flyTest.showStamp('caught'));await shot('caught');
   await page.emulateMedia({reducedMotion:'reduce'});await page.waitForFunction(()=>window.flyTest.state().reduced);await page.evaluate(()=>window.flyTest.showStamp('caught'));await shot('caught-reduced');await page.emulateMedia({reducedMotion:'no-preference'});
   const escaped=await record({warmup:150,hold:600});assert(!escaped.caught&&escaped.escape_onset_lead_ms>0);await page.evaluate(()=>window.flyTest.showStamp('escaped-flight'));await shot('escaped-flight');
   await page.emulateMedia({reducedMotion:'reduce'});await page.waitForFunction(()=>window.flyTest.state().reduced);await page.evaluate(()=>window.flyTest.showStamp('escaped-flight'));await shot('takeoff-reduced');await page.emulateMedia({reducedMotion:'no-preference'});
   await page.evaluate(()=>window.flyTest.showReplay());await page.waitForTimeout(100);await shot('replay');await page.click('#continue');await page.click('#intro-help');await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>document.activeElement.id),'intro-help');report.intro_return_after_replay=true;
   const walk=await record({seed:2,aim:{x:4,y:4}});assert(!walk.caught&&!(walk.escape_onset_lead_ms>0));await page.evaluate(()=>window.flyTest.showStamp('walk-out'));await shot('walk-out');
   for(let hand=1;hand<6;hand++){await page.evaluate(()=>window.flyTest.resume());await page.evaluate(()=>{const b=window.flyTest.state().frame.body;window.flyTest.strike(b.x,b.y,0);});await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(n=>window.flyTest.state().used===n&&window.flyTest.state().lastImpact?.tick===window.flyTest.recordedFrames().findLast(f=>f.impact)?.tick,hand+1);}
   const log=await page.evaluate(()=>window.flyTest.log());assert((await replayLog(buffer,runtime,profile,log)).matches,'Browser log must reexecute exactly in Node');report.replay_log=log;
   await page.evaluate(()=>window.flyTest.showRound());await shot('round');
   await page.locator('#round-sheet [data-wiring]').click();await page.waitForFunction(()=>window.couplingTest?.ready());await shot('lab-1');
   let before=await page.evaluate(()=>window.couplingTest.state());report.lab_sign_fps=await fps(page);let after=await page.evaluate(()=>window.couplingTest.state());assert(after.panels[0].tick>before.panels[0].tick&&after.paintCount>before.paintCount);report.lab_sign_speed=after.speed;assert(report.lab_sign_fps>=50,String(report.lab_sign_fps));
   await page.evaluate(()=>window.couplingTest.step(2));await page.waitForFunction(()=>window.couplingTest.ready());await shot('lab-2');
   before=await page.evaluate(()=>window.couplingTest.state());report.lab_strength_fps=await fps(page);after=await page.evaluate(()=>window.couplingTest.state());assert(after.panels[0].tick>before.panels[0].tick);report.lab_strength_speed=after.speed;assert(report.lab_strength_fps>=50,String(report.lab_strength_fps));
   await page.evaluate(()=>window.couplingTest.step(3));await shot('lab-3');
   await page.locator('#try-strength>summary').click();await page.locator('#try-yourself').scrollIntoViewIfNeeded();await shot('try-yourself',{scroll:false});
   await page.locator('[data-lesion="giant-fiber"]').click();await page.waitForFunction(()=>window.flyTest?.ready()&&document.getElementById('circuit-badge')?.checkVisibility());await shot('silenced');
   await page.goto(url+'how-it-works.html');await page.evaluate(()=>document.fonts.ready);await shot('how-top');await page.locator('#h-real').scrollIntoViewIfNeeded();await shot('how-middle',{scroll:false});
   await page.locator('#scientists>summary').click();await page.evaluate(()=>document.getElementById('scientists').scrollIntoView());await shot('how-details',{scroll:false});
   await go();await page.evaluate(()=>window.flyTest.startLive());await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');await page.waitForTimeout(500);before=await page.evaluate(()=>window.flyTest.state());report.game_fps=await fps(page);after=await page.evaluate(()=>window.flyTest.state());assert(after.frame.tick>before.frame.tick&&after.paintCount>before.paintCount);assert(report.game_fps>=55,String(report.game_fps));
   if(viewport.width===390&&locale==='en-US'){
    const isolated=await browser.newContext({viewport,serviceWorkers:'block'});await isolated.route('**/*',route=>{const u=route.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return route.abort();}return route.continue();});
    await isolated.addInitScript(()=>{Storage.prototype.getItem=()=>{throw Error('Storage unavailable');};Storage.prototype.setItem=()=>{throw Error('Storage unavailable');};});
    const first=await isolated.newPage();first.on('pageerror',e=>errors.push(String(e)));await first.goto(url+'?test=1');await first.waitForFunction(()=>document.querySelector('#first-visit')?.open);await first.keyboard.press('Escape');await first.waitForTimeout(100);assert.equal(await first.locator('#first-visit').evaluate(d=>d.open),false);await first.reload();await first.waitForFunction(()=>document.querySelector('#first-visit')?.open);await first.keyboard.press('Escape');await isolated.close();report.storage_failure_once_per_load=true;
   }
   assert.equal(external.length,0);assert.equal(errors.length,0,errors.join('\n'));report.status='PASS';
  }catch(e){report.status='FAIL';report.failure=e.stack??String(e);console.error(name,viewport,locale,report.failure);}
  finally{save();await context.close();}
  console.log(name,viewport.width,locale,report.status,'game',report.game_fps??'','lab',report.lab_sign_fps??'',report.lab_strength_fps??'');
 }}finally{await browser.close();}
}}finally{await new Promise(r=>server.close(r));}
if(reports.some(r=>r.status!=='PASS'))process.exitCode=1;
