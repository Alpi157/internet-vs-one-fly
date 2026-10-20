import assert from 'node:assert/strict';
import {readFileSync,readdirSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {chromium} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {serve,root,dist,prefix} from './site-server.mjs';
const out=resolve(root,process.env.FLYBENCH_OWNER_PRODUCTION_OUT??'evidence/V2J/a03/production');mkdirSync(out,{recursive:true});
const files=[];function scan(dir){for(const e of readdirSync(dir,{withFileTypes:true})){const p=resolve(dir,e.name);if(e.isDirectory())scan(p);else if(/\.(js|html|json|css)$/.test(e.name)){const text=readFileSync(p,'utf8');for(const marker of ['flyOwnerTest','owner-preview-badge','Owner preview','owner_playtest_profile','flybench.game.v2.8.owner-a02','busy, quicker takeoff','owner-walking-a02'])assert(!text.includes(marker),`Production contains dev marker ${marker}: ${p}`);files.push(p.slice(dist.length+1));}}}scan(dist);
assert(!files.some(p=>p.includes('owner-preview')));
assert.equal(JSON.parse(readFileSync(resolve(dist,'data/game.json'))).profile_id,'flybench.game.v2.9');
const {server,origin}=await serve(),browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({viewport:{width:1280,height:720}}),external=[];
 await page.route('**/*',r=>{const u=r.request().url();if(!u.startsWith(origin)&&!u.startsWith('blob:')&&!u.startsWith('data:')){external.push(u);return r.abort();}return r.continue();});
 await page.addInitScript(()=>localStorage.setItem('flybench.intro.v5','seen'));
 await page.goto(origin+prefix+'?preview=C&test=1');await page.waitForFunction(()=>window.flyTest?.ready());
 assert.equal(await page.locator('#owner-preview-badge').count(),0);await page.evaluate(()=>window.flyTest.resetSeed(1));await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');await page.evaluate(()=>window.flyTest.advance(100));
 const log=await page.evaluate(()=>window.flyTest.log());assert.equal(log.schema,'flybench.game-round.v4');assert(!('owner_playtest_profile' in log.profile_hashes));assert.equal(external.length,0);
 writeFileSync(resolve(out,'check.json'),JSON.stringify({status:'PASS',scanned_files:files,query_ignored:'?preview=C',profile:'flybench.game.v2.9',log,external_requests:external},null,2)+'\n');
 console.log('PASS production bundle has no preview module/data/activation path; preview query runs production v2.9 A');
}finally{await browser.close();await new Promise(r=>server.close(r));}
