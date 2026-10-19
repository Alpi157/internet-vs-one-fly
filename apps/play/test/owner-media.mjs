// Review-only actual dev previews. Every neural flash comes from recorded spikes.
import assert from 'node:assert/strict';
import {chromium} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync,readdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {homedir} from 'node:os';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {serveDev,root,prefix} from './owner-server.mjs';
import {newGame,botRound,identityRuntime,buffer} from './owner-walking.ts';
import {replayLog} from '../src/game.ts';
const selected=JSON.parse(readFileSync(resolve(root,'profiles/owner-walking-a02-selected.json'))),out=resolve(root,'evidence/V2J/a02/media');mkdirSync(out,{recursive:true});
const cache=process.env.PLAYWRIGHT_BROWSERS_PATH??resolve(homedir(),'.cache/ms-playwright');
const ffmpeg=process.env.FLYBENCH_FFMPEG??resolve(cache,readdirSync(cache).filter(n=>n.startsWith('ffmpeg-')).sort().at(-1),'ffmpeg-linux');
const {server,origin}=await serveDev(),browser=await chromium.launch({headless:true});const receipts=[];
try{
 for(const [id,entry] of Object.entries(selected.presets)){
  if(!entry.offered)continue;
  for(const kind of ['quiet','bot4']){
   const planned=kind==='quiet'?newGame(entry.profile,1):botRound(entry.profile,1,4,0,false,6,10000).game;
   while(!planned.done&&planned.tick<20000)planned.step();
   const expected=await planned.log(),inputs=expected.inputs;let next=0;
   const page=await browser.newPage({viewport:{width:1280,height:900},locale:'en-US'}),external=[],observations=[],images=[];
   try{
    await page.route('**/*',r=>{const u=r.request().url();if(!u.startsWith(origin)&&!u.startsWith('data:')&&!u.startsWith('blob:')){external.push(u);return r.abort();}return r.continue();});
    await page.goto(origin+prefix+`?preview=${id}&test=1`);await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady,{},{timeout:60000});await page.evaluate(()=>document.fonts.ready);
    // Dev-only seed hook; the offered preset and drive are unchanged.
    await page.evaluate(()=>window.flyOwnerTest.resetSeeds(1,1001));await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');
    for(let i=0;i<200;i++){
     const target=Math.min((i+1)*100,expected.end_tick);let f=await page.evaluate(()=>window.flyTest.state());
     while(f.frame.tick<target){
      if(f.replaying){await page.evaluate(()=>window.flyTest.resume());}
      const tick=f.frame.tick;
      if(inputs[next]?.tick===tick){const input=inputs[next++];await page.evaluate(v=>window.flyTest.strike(v.x,v.y,v.hold_ms),input);}
      const stop=Math.min(target,inputs[next]?.tick??target),intervals=Math.max(1,(stop-tick)/20);
      await page.evaluate(n=>window.flyTest.advance(n),intervals);f=await page.evaluate(()=>window.flyTest.state());
     }
     await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
     const state=await page.evaluate(()=>window.flyTest.state());observations.push({video_ms:(i+1)*50,tick:state.frame.tick,body:state.frame.body,air:state.frame.air,replaying:state.replaying,spikes:state.frame.spikes});
     images.push(await page.screenshot({type:'jpeg',quality:85}));
    }
    const log=await page.evaluate(()=>window.flyTest.log());assert.equal(log.digest,expected.digest);assert.deepEqual(log.inputs,expected.inputs);assert.equal(external.length,0);
    assert((await replayLog(buffer,identityRuntime(entry.profile),entry.profile,log)).matches);
    const file=`${id}-${kind}-10s.webm`;
    execFileSync(ffmpeg,['-loglevel','error','-y','-f','image2pipe','-framerate','20','-vcodec','mjpeg','-i','pipe:0','-c:v','libvpx-vp9','-b:v','0','-crf','40','-pix_fmt','yuv420p',resolve(out,file)],{input:Buffer.concat(images),maxBuffer:1024*1024});
    const bytes=readFileSync(resolve(out,file)),receipt={preset:id,kind,file,neural_seed:1,environment_seed:1001,duration_seconds:10,fps:20,frames:200,log,profile_sha256:entry.profile_sha256,video_bytes:bytes.length,video_sha256:createHash('sha256').update(bytes).digest('hex'),matches_authoritative_node:true,matches_reexecution:true,external_requests:external,observations};
    writeFileSync(resolve(out,`${id}-${kind}-recording.json`),JSON.stringify(receipt,null,2)+'\n');receipts.push({...receipt,observations:undefined});console.log('Recorded',file,bytes.length,'bytes;',inputs.length,'strikes');
   }finally{await page.close();}
  }
 }
}finally{writeFileSync(resolve(out,'manifest.json'),JSON.stringify({code_sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),purpose:'Owner/reviewer-only media, not README hero',receipts},null,2)+'\n');await browser.close();await server.close();}
