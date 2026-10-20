import assert from 'node:assert/strict';
import {chromium,firefox,webkit} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {serve,root,prefix} from './site-server.mjs';
import {serveDev} from './owner-server.mjs';
import {overlaps} from './overlap.mjs';
import {replayLog} from '../src/game.ts';
import {buffer,runtime,load} from './owner-walking.ts';
const dry=process.argv.includes('--dry'),profile=load('profiles/game-v2.9.json');
const out=resolve(root,process.env.FLYBENCH_V2M_BROWSER_OUT??(dry?'evidence/V2M/dry-browser':'evidence/V2M/browser'));mkdirSync(out,{recursive:true});
const axe=readFileSync(resolve(root,'apps/play/node_modules/axe-core/axe.min.js'),'utf8'),reports=[];
const code_sha=execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
const working_tree_dirty=!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim();
const source_sha256=Object.fromEntries(['main.ts','style.css','brain-view.ts','coupling.ts','intro.ts','owner-preview.ts','game.ts'].map(f=>['apps/play/src/'+f,createHash('sha256').update(readFileSync(resolve(root,'apps/play/src',f))).digest('hex')]));
const {server,origin}=await serve(),url=origin+prefix;const dev=await serveDev();
const viewports=[{width:390,height:844},{width:1440,height:900},{width:1920,height:1080},{width:2560,height:1440}];
const fps=page=>page.evaluate(()=>new Promise(resolve=>{let count=0;const start=performance.now();function frame(t){count++;if(t-start>=3000)resolve(count/((t-start)/1000));else requestAnimationFrame(frame);}requestAnimationFrame(frame);}));
try{for(const [name,engine] of Object.entries({chromium,firefox,webkit})){
 if((dry&&name!==(process.env.FLYBENCH_BROWSER??'chromium'))||(process.env.FLYBENCH_BROWSER&&process.env.FLYBENCH_BROWSER!==name))continue;
 const browser=await engine.launch({headless:true});
 try{for(const viewport of viewports)for(const locale of dry?['en-US']:['en-US','ru-RU']){
  if((process.env.FLYBENCH_WIDTH&&viewport.width!==Number(process.env.FLYBENCH_WIDTH))||(process.env.FLYBENCH_LOCALE&&locale!==process.env.FLYBENCH_LOCALE))continue;
  const context=await browser.newContext({viewport,locale,serviceWorkers:'block'}),page=await context.newPage(),external=[],errors=[],http_errors=[],states=[];
  const report={browser:name,version:browser.version(),viewport,locale,status:'RUNNING',states,external_requests:external,http_errors,errors};reports.push(report);
  const save=()=>writeFileSync(resolve(out,`matrix-${name}.json`),JSON.stringify({code_sha,working_tree_dirty,source_sha256,reports},null,2)+'\n');
  await context.route('**/*',route=>{const u=route.request().url();if(!u.startsWith(origin)&&!u.startsWith(dev.origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return route.abort();}return route.continue();});
  await context.addInitScript(()=>{try{localStorage.setItem('flybench.intro.v5','seen');}catch{}window.canvasText=new Set();const fill=CanvasRenderingContext2D.prototype.fillText;CanvasRenderingContext2D.prototype.fillText=function(text,...args){window.canvasText.add(String(text));if(this.canvas.classList.contains('brain-labels')){const m=this.measureText(String(text)),size=parseFloat(this.font.replace(/^600 /,'')),x=args[0]-(this.textAlign==='right'?m.width:this.textAlign==='center'?m.width/2:0),y=args[1];(this.canvas.labelRects??=[]).push({text:String(text),x,y:y-(m.actualBoundingBoxAscent??size),right:x+m.width,bottom:y+(m.actualBoundingBoxDescent??0),font:size});}return fill.call(this,text,...args);};const clear=CanvasRenderingContext2D.prototype.clearRect;CanvasRenderingContext2D.prototype.clearRect=function(...args){if(this.canvas.classList.contains('brain-labels'))this.canvas.labelRects=[];return clear.apply(this,args);};});
  page.on('pageerror',e=>errors.push(String(e)));page.on('response',r=>{if(r.status()>=400)http_errors.push({url:r.url(),status:r.status()});});
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
   const anatomy_labels=await page.evaluate(()=>Array.from(document.querySelectorAll('.brain-labels')).filter(e=>e.checkVisibility()).map(e=>{const scale=e.getBoundingClientRect().width/e.width,labels=(e.labelRects??[]).map(r=>({...r,css_font:r.font*scale})),collisions=[];for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++){const a=labels[i],b=labels[j];if(Math.min(a.right,b.right)>Math.max(a.x,b.x)&&Math.min(a.bottom,b.bottom)>Math.max(a.y,b.y))collisions.push([a.text,b.text]);}return {labels,collisions,contained:labels.every(r=>r.x>=0&&r.y>=0&&r.right<=e.width&&r.bottom<=e.height)};}));
   assert(anatomy_labels.every(v=>v.contained&&!v.collisions.length&&v.labels.every(r=>r.css_font>=13&&r.css_font<=16)),JSON.stringify({state,anatomy_labels}));
   await page.screenshot({path:resolve(out,file)});await page.addScriptTag({content:axe});
   const accessibility=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));});
   const text=await page.evaluate(()=>[document.body.innerText,...[...document.querySelectorAll('[alt],[aria-label]')].map(e=>e.getAttribute('alt')||e.getAttribute('aria-label')),...window.canvasText].join('\n'));
   const localeErrors=[...text.matchAll(/\b5[ .\u00a0\u202f]555\b|\b\d+,\d{1,2}\b/g)].map(m=>m[0]);
   const result={state,file,anatomy_labels,overlap:collision,axe:accessibility,bounds,locale_errors:localeErrors,external_requests:external.slice(),http_errors:http_errors.slice()};states.push(result);save();
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
   await page.click('#intro-help');assert.equal(await page.evaluate(()=>document.activeElement.id),'intro-title');await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'intro-next');await page.keyboard.press('Escape');report.intro_title_focus=true;
   const impact=await record({seed:1,warmup:150,hold:600});assert(!impact.caught);await page.evaluate(()=>window.flyTest.showReplay());
   if(viewport.width>=900){await page.waitForFunction(()=>!document.getElementById('field-next').hidden);assert(await page.locator('#field-continue').evaluate(e=>e.getBoundingClientRect().height>=56));}
   await shot('outcome-next');if(viewport.width<900)await shot('phone-replay');
   const indices=await page.evaluate(()=>{const f=window.flyTest.recordedFrames(),impact=window.flyTest.state().lastImpact;return [0,f.findIndex(f=>f.tick===impact.tick),f.length-1];});
   for(const [i,index] of indices.entries()){await page.evaluate(n=>window.flyTest.seekReplay(n),index);await shot(['scrub-first','scrub-impact','scrub-last'][i]);assert.equal(await page.evaluate(()=>window.flyTest.replayIndex()),index);}
   const range=page.locator('#replay-playhead');const hit=await range.boundingBox();assert(hit.height>=44);await page.mouse.move(hit.x+hit.width*.3,hit.y+hit.height/2);await page.mouse.down();await page.mouse.move(hit.x+hit.width*.7,hit.y+hit.height/2,{steps:8});await page.mouse.up();const dragged=await page.evaluate(()=>window.flyTest.replayIndex());assert(dragged>0&&dragged<indices[2]);await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>window.flyTest.replayIndex()),dragged);report.pointer_scrub_pauses=true;await range.focus();await page.keyboard.press('Home');assert.equal(await page.evaluate(()=>window.flyTest.replayIndex()),0);await page.keyboard.press('ArrowRight');assert.equal(await page.evaluate(()=>window.flyTest.replayIndex()),1);await page.keyboard.press('PageUp');assert.equal(await page.evaluate(()=>window.flyTest.replayIndex()),11);await page.keyboard.press('PageDown');assert.equal(await page.evaluate(()=>window.flyTest.replayIndex()),1);await page.keyboard.press('End');assert.equal(await page.evaluate(()=>window.flyTest.replayIndex()),indices[2]);report.keyboard_scrubbing=true;
   await page.evaluate(()=>window.flyTest.seekReplay(2));await page.waitForTimeout(50);const sought=await page.evaluate(()=>({activity:window.flyTest.replayActivity(),image:window.flyTest.brainSnapshot(),frame:window.flyTest.state().replayFrame,field:document.getElementById('table').toDataURL()}));
   await range.focus();await page.keyboard.press('Home');await page.selectOption('#replay-speed','0.025');await page.click('#pause-replay');await page.waitForFunction(()=>window.flyTest.replayIndex()===2);await page.click('#pause-replay');const played=await page.evaluate(()=>({activity:window.flyTest.replayActivity(),image:window.flyTest.brainSnapshot(),frame:window.flyTest.state().replayFrame,field:document.getElementById('table').toDataURL()}));assert.deepEqual(played,sought);report.scrub_matches_normal_playback=true;
   await page.locator('#brain-host input[value=whole]').check({force:true});await page.waitForTimeout(100);await shot('whole-landscape');
   const anatomyBounds=()=>page.evaluate(()=>{const box=document.querySelector('.brain-fullscreen .brain-image')??document.querySelector('#brain-host .brain-image');const r=box.getBoundingClientRect();return {width:r.width,height:r.height,scrollWidth:box.scrollWidth,clientWidth:box.clientWidth,scrollHeight:box.scrollHeight,clientHeight:box.clientHeight};});
   report.whole_box=await anatomyBounds();assert(report.whole_box.scrollWidth<=report.whole_box.clientWidth&&report.whole_box.scrollHeight<=report.whole_box.clientHeight);
   await page.locator('#brain-host .brain-expand').click();await page.waitForTimeout(100);await shot('brain-fullscreen');
   await page.locator('.brain-fullscreen .brain-image').evaluate(e=>{e.style.cssText='width:210px;height:340px!important;flex:none;margin:auto;';});await page.waitForTimeout(100);await shot('whole-portrait');report.portrait_box=await anatomyBounds();assert(report.portrait_box.height>report.portrait_box.width&&report.portrait_box.scrollHeight<=report.portrait_box.clientHeight);
   await page.locator('.brain-fullscreen .brain-image').evaluate(e=>e.removeAttribute('style'));await page.keyboard.press('Escape');await page.waitForFunction(()=>document.querySelector('#brain-host .brain-expand')===document.activeElement);report.expand_escape_focus_return=true;
   await page.locator('#table').focus();if(viewport.width<900)await page.locator('#replay-badge').evaluate(e=>{e.tabIndex=-1;e.focus();});await page.keyboard.press('Space');assert.equal(await page.evaluate(()=>window.flyTest.state().replaying),false);report.space_advances=true;
   const log=await page.evaluate(()=>window.flyTest.log());assert((await replayLog(buffer,runtime,profile,log)).matches);report.replay_log=log;
   for(let hand=1;hand<6;hand++){await page.evaluate(()=>{const b=window.flyTest.state().frame.body;window.flyTest.strike(b.x,b.y,0);});await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(n=>window.flyTest.state().used===n&&window.flyTest.state().replaying,hand+1);if(hand<5){await page.locator('#replay-badge').evaluate(e=>{e.tabIndex=-1;e.focus();});await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>window.flyTest.state().replaying),false);}}
   assert.equal(await page.locator('#continue').innerText(),'See your round');if(viewport.width>=900)assert.equal(await page.locator('#field-continue').innerText(),'See your round');await page.click('#continue');await page.waitForFunction(()=>document.querySelector('#round-sheet').open);report.enter_advances_and_sixth_hand_summary=true;
   await page.locator('#round-sheet [data-wiring]').click();await page.waitForFunction(()=>window.couplingTest?.ready());await page.waitForFunction(()=>window.couplingTest.state().mirrors.every(v=>!v.active||!v.visible||(v.ready>=2&&v.frames>0)));await page.waitForTimeout(200);report.lab_story_before=await page.evaluate(()=>window.couplingTest.state().mirrors);report.lab_story_fps=await fps(page);report.lab_story_after=await page.evaluate(()=>window.couplingTest.state().mirrors);assert(report.lab_story_after.every((v,i)=>!v.active||!v.visible||(v.ready>=2&&v.frames>report.lab_story_before[i].frames)),'Visible mirrors must present new recorded frames');assert(report.lab_story_fps>=50,String(report.lab_story_fps));await page.locator('#try-yourself').evaluate(e=>e.scrollIntoView({block:'start'}));await shot('try-yourself',{scroll:false});await page.locator('#try-live').evaluate(e=>e.scrollIntoView({block:'start'}));await shot('try-live-and-chart',{scroll:false});await page.locator('#silence-panel').scrollIntoViewIfNeeded();await shot('try-lesions',{scroll:false});
   await page.locator('#try-live').scrollIntoViewIfNeeded();let before=await page.evaluate(()=>window.couplingTest.state());report.lab_sign_fps=await fps(page);let after=await page.evaluate(()=>window.couplingTest.state());assert(after.panels[0].tick>before.panels[0].tick&&after.paintCount>before.paintCount);assert(report.lab_sign_fps>=50,String(report.lab_sign_fps));
   await page.evaluate(()=>window.couplingTest.setFamily('N-STRENGTH'));await page.waitForFunction(()=>window.couplingTest.ready());report.lab_strength_fps=await fps(page);assert(report.lab_strength_fps>=50,String(report.lab_strength_fps));
   await go();await page.evaluate(()=>window.flyTest.startLive());await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');await page.waitForTimeout(500);before=await page.evaluate(()=>window.flyTest.state());report.game_fps=await fps(page);after=await page.evaluate(()=>window.flyTest.state());assert(after.frame.tick>before.frame.tick&&after.paintCount>before.paintCount);assert(report.game_fps>=55,String(report.game_fps));
   for(const id of dry?[]:['T0','T1','T2','T3']){await page.goto(dev.origin+prefix+'?preview='+id+'&test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);assert((await page.locator('#owner-preview-badge').innerText()).includes(id));await page.click('#start');await page.evaluate(()=>window.flyTest.advance(150));await shot('preview-'+id);const selected=load('profiles/owner-takeoff-v2m-selected.json').presets[id];let previewLog=await page.evaluate(()=>window.flyTest.log());assert.equal(previewLog.profile_hashes.owner_playtest_profile,selected.profile_sha256);if(viewport.width===1440&&locale==='en-US'){await page.evaluate(()=>{const b=window.flyTest.state().frame.body;window.flyTest.strike(b.x,b.y,600);});await page.evaluate(()=>window.flyTest.advance(100));previewLog=await page.evaluate(()=>window.flyTest.log());assert((await replayLog(buffer,{...runtime,profile_hashes:{...runtime.profile_hashes,owner_playtest_profile:selected.profile_sha256}},selected.profile,previewLog)).matches);(report.preview_replays??={})[id]=previewLog;}}
   assert.equal(external.length,0);assert.equal(http_errors.length,0,JSON.stringify(http_errors));assert.equal(errors.length,0,errors.join('\n'));report.status='PASS';
  }catch(e){report.status='FAIL';report.failure=e.stack??String(e);console.error(name,viewport,locale,report.failure);}
  finally{save();await context.close();}
  console.log(name,viewport.width,locale,report.status,'game',report.game_fps??'','lab',report.lab_sign_fps??'',report.lab_strength_fps??'');
 }}finally{await browser.close();}
}}finally{await new Promise(r=>server.close(r));await dev.server.close();}
if(reports.some(r=>r.status!=='PASS'))process.exitCode=1;
