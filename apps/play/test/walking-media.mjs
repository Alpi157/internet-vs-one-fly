// Review-only recording; never selects a point or changes the shipped profile.
import assert from 'node:assert/strict';
import {chromium} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,readdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {homedir} from 'node:os';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {serve,root,prefix} from './site-server.mjs';
const out=resolve(root,'evidence/V2J/media');mkdirSync(out,{recursive:true});
const profile=JSON.parse(readFileSync(resolve(root,'profiles/game-v2.8.json'))),row=JSON.parse(readFileSync(resolve(root,'evidence/V2J/drive/point-0.json')));
profile.walking_drive.selected=row.point;
const declaration={purpose:'Review only. Unselected first grid point, not a passing point or production v2.8.',point_index:0,point:row.point,neural_seed:1,environment_seed:8128,seconds:10,fps:20,rule:'First grid point, fixed seed 1. Capture every fifth actual 10 ms interval. No threat. No missing neural observations are invented; BrainView receives the ordinary recorded spike history.'};
writeFileSync(resolve(out,'walking-declaration.json'),JSON.stringify(declaration,null,2)+'\n');
const {server,origin}=await serve(),browser=await chromium.launch({headless:true}),frames=mkdtempSync('/tmp/flybench-v2j-walking-');
try{
 const page=await browser.newPage({viewport:{width:1280,height:720},locale:'en-US'}),external=[],observations=[],images=[];
 await page.route('**/*',route=>{const u=route.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return route.abort();}if(u.endsWith('/data/game.json'))return route.fulfill({contentType:'application/json',body:JSON.stringify(profile)});return route.continue();});
 await page.goto(origin+prefix+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);await page.evaluate(()=>document.fonts.ready);
 await page.evaluate(()=>window.flyTest.resetSeed(1));await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');
 await page.evaluate(()=>{document.getElementById('caption').textContent='Review only: unselected grid point 0. Recorded spikes.';});
 for(let i=0;i<200;i++){
  await page.evaluate(()=>window.flyTest.advance(5));await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const f=await page.evaluate(()=>window.flyTest.state().frame);observations.push({tick:f.tick,body:f.body,air:f.air,applied:f.applied,recorded_spike_count:f.spikes.reduce((n,e)=>n+e.indices.length,0)});
  images.push(await page.screenshot({type:'jpeg',quality:85,path:resolve(frames,String(i).padStart(4,'0')+'.jpg')}));
 }
 const log=await page.evaluate(()=>window.flyTest.log());assert.equal(log.inputs.length,0);assert.equal(log.end_tick,20000);assert.equal(external.length,0);
 const cache=process.env.PLAYWRIGHT_BROWSERS_PATH??resolve(homedir(),'.cache/ms-playwright');
 const ffmpeg=process.env.FLYBENCH_FFMPEG??resolve(cache,readdirSync(cache).filter(n=>n.startsWith('ffmpeg-')).sort().at(-1),'ffmpeg-linux');
 execFileSync(ffmpeg,['-loglevel','error','-y','-f','image2pipe','-framerate','20','-vcodec','mjpeg','-i','pipe:0','-c:v','libvpx-vp9','-b:v','0','-crf','40','-pix_fmt','yuv420p',resolve(out,'walking-10s.webm')],{input:Buffer.concat(images),maxBuffer:1024*1024});
 const bytes=readFileSync(resolve(out,'walking-10s.webm'));
 writeFileSync(resolve(out,'walking-recording.json'),JSON.stringify({declaration,profile,log,observations,external_requests:external,video:{bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),frames:200,duration_seconds:10},code_sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim()},null,2)+'\n');
 console.log('Recorded review-only 10 s walking clip',bytes.length);
}finally{await browser.close();await new Promise(r=>server.close(r));}
