import assert from 'node:assert/strict';
import {chromium,firefox,webkit} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {serve,root,dist,prefix} from './site-server.mjs';
const out=resolve(root,process.env.FLYBENCH_LAB_OUT??'evidence/V2I/browser');mkdirSync(out,{recursive:true});
const {server,origin}=await serve(),url=origin+prefix,results=JSON.parse(readFileSync(resolve(dist,'results-v2f.json'))),runtime=JSON.parse(readFileSync(resolve(dist,'data/runtime.json')));
const axe=readFileSync(resolve(root,'apps/play/node_modules/axe-core/axe.min.js'),'utf8'),reports=[];
async function fps(page){return page.evaluate(()=>new Promise(resolve=>{let count=0;const start=performance.now();function next(t){count++;if(t-start>=3000)resolve(count/((t-start)/1000));else requestAnimationFrame(next);}requestAnimationFrame(next);}));}
try{
 for(const [name,engine] of Object.entries({chromium,firefox,webkit})){
  if(process.env.FLYBENCH_BROWSER&&process.env.FLYBENCH_BROWSER!==name)continue;
  const browser=await engine.launch({headless:true});
  try{for(const viewport of [{width:390,height:844},{width:1440,height:900},{width:1280,height:720}]){
   const context=await browser.newContext({viewport,serviceWorkers:'block'}),external=[],errors=[],scans=[],shots=[],performanceRows=[];
   const report={browser:name,version:browser.version(),viewport,status:'RUNNING',axe:scans,screenshots:shots,fps:performanceRows,external_requests:external,errors};reports.push(report);
   await context.route('**/*',route=>{const u=route.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return route.abort();}return route.continue();});
   const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));page.on('response',r=>{if(r.status()>=400&&!r.url().includes('missing-page'))errors.push(`${r.status()} ${r.url()}`);});
   async function scan(state){await page.addScriptTag({content:axe});const r=await page.evaluate(async()=>{const r=await window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:r.incomplete.map(v=>({id:v.id,impact:v.impact}))};});scans.push({state,...r});assert.equal(r.violations.length,0,JSON.stringify({state,...r}));}
   async function shot(state,scroll=true){if(scroll)await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(100);const file=`${name}-${viewport.width}x${viewport.height}-${state}.png`;await page.screenshot({path:resolve(out,file)});shots.push(file);await scan(state);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'horizontal overflow');}
   await page.goto(url+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready());await page.locator('[data-wiring]:visible').first().click();await page.waitForFunction(()=>window.couplingTest?.ready(),{timeout:60000});
   assert.equal(await page.evaluate(()=>window.couplingTest.state().scale),runtime.parameters.s);
   for(const family of ['N-SIGN','N-STRENGTH']){
    await page.locator(`input[value="${family}"]`).check();await page.waitForFunction(()=>window.couplingTest?.ready());await page.waitForTimeout(1000);
    const before=await page.evaluate(()=>window.couplingTest.state());const rate=await fps(page);const after=await page.evaluate(()=>window.couplingTest.state());assert(after.panels[0].tick>before.panels[0].tick);assert(after.paintCount>before.paintCount);
    performanceRows.push({family,coupling:after.scale,raf_fps:rate,simulation_speed:after.speed,renderers:after.renderers});assert(rate>=50,`${name} ${family} ${rate} fps`);
    for(const p of after.panels)assert(Math.abs(p.rate-p.counts.reduce((a,b)=>a+b,0)/p.counts.length/p.seconds)<1e-10);
    await shot(family==='N-SIGN'?'lab-partners-calibrated':'lab-strength-calibrated');
    // Capture the chart separately where the full phone page necessarily scrolls.
    await page.locator('.lab-chart').scrollIntoViewIfNeeded();await shot(family+'-chart',false);
   }
   // Independent radio groups: one Whole CNS must not uncheck the other panel.
   await page.locator('#lab-brain-0 input[value=whole]').check();assert(await page.locator('#lab-brain-1 input[value=brain]').isChecked());await page.locator('#lab-brain-0 input[value=brain]').check();
   await page.evaluate(s=>window.couplingTest.setScale(s),Math.max(...results.chart.measured.map(p=>p.s)));await page.waitForFunction(()=>window.couplingTest.ready());await shot('lab-highest');await page.click('#coupling-drop');await page.waitForFunction(()=>document.getElementById('coupling-status').textContent.includes('Hand stimulus applied.'));
   await page.click('#silence-tab');await shot('lab-silence');assert(!await page.locator('#full-shuffle').isVisible());
   await page.click('[data-lesion=LC4]');await page.locator('#circuit-badge').waitFor({state:'visible'});await page.waitForFunction(()=>window.flyTest.ready());await page.evaluate(()=>window.flyTest.advance(10));await shot('game-silenced');assert.equal(await page.locator('#circuit-label').textContent(),'LC4 silenced');assert((await page.evaluate(()=>window.flyTest.log())).graph_identity.endsWith(':LC4'));
   await page.click('#restore-wiring');await page.locator('#circuit-badge').waitFor({state:'hidden'});await page.waitForFunction(()=>window.flyTest.ready());assert(!await page.locator('#circuit-badge').isVisible());assert((await page.evaluate(()=>window.flyTest.log())).graph_identity.endsWith(':real'));
   await page.goto(url+'how-it-works.html');await page.evaluate(()=>document.fonts.ready);await shot('how-top');await page.locator('#finding').scrollIntoViewIfNeeded();await shot('how-finding',false);assert.equal(await page.locator('#finding tbody tr').count(),results.comparison_rows.length);
   for(const file of ['model.html','preregistration.html']){await page.goto(url+file);assert(await page.locator('#finding').isVisible());assert.equal(await page.locator('meta[name=theme-color]').getAttribute('content'),'#000000');}
   const missing=await page.goto(url+'missing-page/nested');assert.equal(missing.status(),404);assert.equal(await page.locator('h1').textContent(),'Page not found');
   // Actual round, recorded inputs; summary viewport assertion covers every control.
   await page.goto(url+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready());await page.waitForFunction(()=>window.flyTest.state().anatomyReady);await page.click('#start');
   const profile=JSON.parse(readFileSync(resolve(dist,'data/game.json')));
   for(let i=0;i<profile.max_strikes;i++){await page.locator('#table').focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('Enter');await page.evaluate(()=>window.flyTest.advance(36));await page.waitForFunction(()=>window.flyTest.state().replaying);await page.click('#continue');}
   const bounds=await page.locator('#round-sheet button').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {text:n.textContent,x:r.x,y:r.y,right:r.right,bottom:r.bottom};}));
   assert(bounds.every(r=>r.x>=0&&r.y>=0&&r.right<=viewport.width&&r.bottom<=viewport.height),JSON.stringify(bounds));report.summary_controls=bounds;await shot('round-summary');
   assert.equal(errors.length,0,errors.join('\n'));assert.equal(external.length,0);report.status='PASS';console.log(name,viewport.width,performanceRows.map(r=>r.raf_fps.toFixed(1)).join(' / '));await context.close();
  }}catch(e){reports.at(-1).status='FAIL';reports.at(-1).failure=String(e);console.error(name,e);}finally{await browser.close();}
 }
}finally{await new Promise(r=>server.close(r));}
const report={sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),status:reports.every(r=>r.status==='PASS')?'PASS':'FAIL',scope:'Production build. Headless desktop engines at three CSS viewports. FPS is rAF opportunities over 3 seconds while both recorded-spike BrainViews and both worker simulations advance. Not physical phone measurements.',reports};
writeFileSync(resolve(out,'matrix.json'),JSON.stringify(report,null,2)+'\n');if(report.status!=='PASS')process.exitCode=1;
