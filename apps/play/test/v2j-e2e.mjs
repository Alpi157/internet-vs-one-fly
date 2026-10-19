import assert from 'node:assert/strict';
import {chromium,firefox,webkit} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {serve,root,dist,prefix} from './site-server.mjs';
import {overlaps} from './overlap.mjs';
const out=resolve(root,process.env.FLYBENCH_V2J_BROWSER_OUT??'evidence/V2J/browser');mkdirSync(out,{recursive:true});
const axe=readFileSync(resolve(root,'apps/play/node_modules/axe-core/axe.min.js'),'utf8'),reports=[];
const {server,origin}=await serve(),url=origin+prefix;
const viewports=[{width:390,height:844},{width:1280,height:720},{width:1366,height:768},{width:1440,height:900},{width:1920,height:1080},{width:2560,height:1440}];
const fps=page=>page.evaluate(()=>new Promise(resolve=>{let count=0;const start=performance.now();function frame(t){count++;if(t-start>=3000)resolve(count/((t-start)/1000));else requestAnimationFrame(frame);}requestAnimationFrame(frame);}));
try{
 for(const [name,engine] of Object.entries({chromium,firefox,webkit})){
  if(process.env.FLYBENCH_BROWSER&&process.env.FLYBENCH_BROWSER!==name)continue;
  const browser=await engine.launch({headless:true});
  try{for(const [viewport,locale] of [...viewports.map(v=>[v,'en-US']),...(name==='chromium'?['ru-RU','de-DE'].map(l=>[{width:1440,height:900},l]):[])]){
   if(process.env.FLYBENCH_WIDTH&&viewport.width!==Number(process.env.FLYBENCH_WIDTH))continue;
   const context=await browser.newContext({viewport,locale,serviceWorkers:'block'}),page=await context.newPage(),external=[],errors=[],states=[];
   const report={browser:name,version:browser.version(),viewport,locale,status:'RUNNING',states,external_requests:external,errors};reports.push(report);
   const save=()=>writeFileSync(resolve(out,'matrix.json'),JSON.stringify({sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),reports},null,2)+'\n');
   await context.route('**/*',route=>{const u=route.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return route.abort();}return route.continue();});
   await context.addInitScript(()=>{window.canvasText=new Set();const fill=CanvasRenderingContext2D.prototype.fillText;CanvasRenderingContext2D.prototype.fillText=function(text,...args){window.canvasText.add(String(text));return fill.call(this,text,...args);};});
   page.on('pageerror',e=>errors.push(String(e)));
   async function shot(state){
    await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(100);
    const collision=await overlaps(page),file=`${name}-${viewport.width}x${viewport.height}-${locale}-${state}.png`;
    await page.screenshot({path:resolve(out,file)});await page.addScriptTag({content:axe});
    const accessibility=await page.evaluate(async()=>{const r=await window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));});
    const text=await page.evaluate(()=>[document.body.innerText,...[...document.querySelectorAll('[alt],[aria-label]')].map(e=>e.getAttribute('alt')||e.getAttribute('aria-label')),...window.canvasText].join('\n'));
    const localeErrors=[...text.matchAll(/\b5[ .\u00a0\u202f]555\b|\b\d+,\d{1,2}\b/g)].map(m=>m[0]);
    const result={state,file,overlap:collision,axe:accessibility,locale_errors:localeErrors};states.push(result);save();
    assert.equal(collision.collisions.length,0,JSON.stringify({state,collisions:collision.collisions}));assert.equal(accessibility.length,0,JSON.stringify(accessibility));assert.equal(localeErrors.length,0,JSON.stringify(localeErrors));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Horizontal overflow');
   }
   try{
    await page.goto(url+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);await page.evaluate(()=>document.fonts.ready);
    assert((await page.locator('#subtitle').innerText()).includes('5,555'));
    await page.evaluate(()=>{const a=document.createElement('button'),b=document.createElement('span');a.id='overlap-probe';a.style.cssText='position:fixed;top:0;left:0;width:100px;height:50px;z-index:999';a.textContent='Probe';b.id='overlap-probe-text';b.style.cssText='position:fixed;top:10px;left:10px;z-index:1000';b.textContent='Collision';document.body.append(a,b);});
    assert((await overlaps(page)).collisions.some(c=>c.a.label==='Collision'||c.b.label==='Collision'),'Overlap detector must catch unrelated visible text/control');
    await page.evaluate(()=>{document.getElementById('overlap-probe').remove();document.getElementById('overlap-probe-text').remove();});
    await page.click('#start');await page.evaluate(()=>window.flyTest.advance(150));await shot('game');
    await page.evaluate(()=>{const b=window.flyTest.state().frame.body;window.flyTest.strike(b.x,b.y,300);});await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(()=>window.flyTest.state().replaying);await shot('replay');await page.click('#continue');
    for(let i=1;i<6;i++){await page.evaluate(()=>window.flyTest.strike(0,0,300));await page.evaluate(()=>window.flyTest.advance(100));await page.waitForFunction(()=>window.flyTest.state().replaying);await page.click('#continue');}
    await shot('round-summary');
    await page.goto(url+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);await page.locator('[data-wiring]:visible').first().click();await page.waitForFunction(()=>window.couplingTest?.ready());await shot('lab-shuffle');await page.click('#silence-tab');await shot('lab-silence');
    await page.goto(url+'how-it-works.html');await page.evaluate(()=>document.fonts.ready);assert((await page.locator('#real').innerText()).includes('5,555'));await shot('how-it-works');
    await page.goto(url+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);await page.evaluate(()=>window.flyTest.startLive());await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');await page.waitForTimeout(1000);const before=await page.evaluate(()=>window.flyTest.state());report.game_fps=await fps(page);const after=await page.evaluate(()=>window.flyTest.state());assert(after.frame.tick>before.frame.tick&&after.paintCount>before.paintCount);assert(report.game_fps>=55,String(report.game_fps));assert.equal(external.length,0);assert.equal(errors.length,0,errors.join('\n'));report.status='PASS';
   }catch(e){report.status='FAIL';report.failure=String(e);console.error(name,viewport,locale,report.failure);}
   finally{save();await context.close();}
   console.log(name,viewport.width,locale,report.status,report.game_fps??'');
  }}finally{await browser.close();}
 }
}finally{await new Promise(r=>server.close(r));}
if(reports.some(r=>r.status!=='PASS'))process.exitCode=1;
