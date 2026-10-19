import assert from 'node:assert/strict';
import {chromium,firefox,webkit} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {serveDev,root,prefix} from './owner-server.mjs';
import {overlaps} from './overlap.mjs';
const selection=JSON.parse(readFileSync(resolve(root,'profiles/owner-walking-a02-selected.json'))),out=resolve(root,'evidence/V2J/a02/preview');mkdirSync(out,{recursive:true});
const axe=readFileSync(resolve(root,'apps/play/node_modules/axe-core/axe.min.js'),'utf8'),reports=[];
const {server,origin}=await serveDev();
const persist=()=>writeFileSync(resolve(out,'matrix.json'),JSON.stringify({sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),reports},null,2)+'\n');
try{
 for(const [engineName,engine] of Object.entries({chromium,firefox,webkit})){
  if(process.env.FLYBENCH_BROWSER&&process.env.FLYBENCH_BROWSER!==engineName)continue;
  const browser=await engine.launch({headless:true});
  try{for(const [id,entry] of Object.entries(selection.presets)){
   if(!entry.offered||(process.env.FLYBENCH_PRESET&&process.env.FLYBENCH_PRESET!==id))continue;
   const cases=[{width:390,height:844,locale:'en-US'},{width:1440,height:900,locale:'en-US'},...(engineName==='chromium'?['ru-RU','de-DE'].map(locale=>({width:1440,height:900,locale})):[])];
   for(const {locale,...viewport} of cases){
    if(process.env.FLYBENCH_WIDTH&&viewport.width!==Number(process.env.FLYBENCH_WIDTH))continue;
    const context=await browser.newContext({viewport,locale,serviceWorkers:'block'}),page=await context.newPage(),external=[],errors=[],states=[];
    const report={preset:id,browser:engineName,version:browser.version(),viewport,locale,status:'RUNNING',external_requests:external,errors,states};reports.push(report);persist();
    await context.route('**/*',r=>{const u=r.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return r.abort();}return r.continue();});
    page.on('pageerror',e=>errors.push(String(e)));
    try{
     await page.goto(origin+prefix+`?preview=${id}&test=1`);await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady,{},{timeout:60000});await page.evaluate(()=>document.fonts.ready);
     assert((await page.locator('#owner-preview-badge').innerText()).startsWith(`Preview ${id}: ${entry.name}`));
     assert((await page.locator('#subtitle').innerText()).includes('5,555'));
     assert((await page.locator('#owner-preview-physics').textContent()).includes(entry.profile.takeoff_speed.toFixed(3)));
     await page.evaluate(()=>window.flyTest.resetSeed(1));await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');await page.evaluate(()=>window.flyTest.advance(150));
     async function capture(state){
      await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(100);const overlap=await overlaps(page);assert.equal(overlap.collisions.length,0,JSON.stringify(overlap.collisions));
      await page.addScriptTag({content:axe});const violations=await page.evaluate(async()=>{const r=await window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}));});assert.deepEqual(violations,[]);
      const file=`${id}-${engineName}-${viewport.width}-${locale}-${state}.png`;await page.screenshot({path:resolve(out,file)});states.push({state,file,overlap,axe:violations});
     }
     await capture('game');const f=await page.evaluate(()=>window.flyTest.state().frame);await page.evaluate(f=>window.flyTest.strike(f.body.x,f.body.y,80),f);await page.evaluate(()=>window.flyTest.advance(60));await page.waitForFunction(()=>window.flyTest.state().replaying);
     assert.match(await page.locator('#caption').innerText(),/giant fiber (fired|did not fire)/);await capture('replay');
     const log=await page.evaluate(()=>window.flyTest.log());assert.equal(log.schema,'flybench.game-round.v3');assert.equal(log.profile_hashes.owner_playtest_profile,entry.profile_sha256);
     report.replay_sentence=await page.locator('#caption').innerText();report.recorded_spikes=f.spikes.reduce((n,e)=>n+e.indices.length,0);report.log=log;
     assert.deepEqual(errors,[]);assert.deepEqual(external,[]);report.status='PASS';
    }catch(e){report.status='FAIL';report.error=String(e);persist();throw e;}finally{persist();await context.close();}
   }
  }}finally{await browser.close();}
 }
 // Unoffered/invalid presets cannot silently enter an unvalidated current.
 const browser=await chromium.launch({headless:true});try{const page=await browser.newPage();await page.goto(origin+prefix+'?preview=Z&test=1');await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('not offered'));assert.equal(await page.evaluate(()=>window.flyTest.ready()),false);}finally{await browser.close();}
 console.log('PASS dev-only preset badge, ordinary recorded BrainView/replay sentence, English locales, overlap, axe and network:',reports.length,'contexts');
}finally{persist();await server.close();}
