import {configureLab} from '../src/lab.ts';
import {createHash} from 'node:crypto';
import {unpackGraph} from '../../../packages/kernel-ts/src/transport.ts';
import {gunzipSync} from 'node:zlib';
import {chromium,firefox,webkit} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {createServer} from 'node:http';
import {readFileSync,writeFileSync,mkdirSync,readdirSync,statSync} from 'node:fs';
import {resolve,extname,join} from 'node:path';
import {gzipSync} from 'node:zlib';
import {replayLog} from '../src/game.ts';
const root=resolve(import.meta.dirname,'../../..'),dist=resolve(root,'apps/play/dist'),out=resolve(root,process.env.FLYBENCH_GAME_OUT??'evidence/V2E/game');mkdirSync(out,{recursive:true});
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.webbin':'application/octet-stream'};
const server=createServer((req,res)=>{try{const url=new URL(req.url,'http://localhost');if(url.pathname==='/favicon.ico'){res.writeHead(204).end();return;}const path=resolve(dist,'.'+(url.pathname==='/internet-vs-one-fly/'?'/index.html':url.pathname.replace('/internet-vs-one-fly/','/')));if(!path.startsWith(dist+'/')){res.writeHead(403).end();return;}res.setHeader('Content-Type',mime[extname(path)]??'application/octet-stream');res.end(readFileSync(path));}catch{res.writeHead(404).end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const url=`http://127.0.0.1:${server.address().port}`;
const raw=readFileSync(resolve(dist,'data/circuit.flygraph.gz')),packed=gunzipSync(raw),buffer=unpackGraph(packed.buffer.slice(packed.byteOffset,packed.byteOffset+packed.byteLength));
const runtime=JSON.parse(readFileSync(resolve(dist,'data/runtime.json'))),profile=JSON.parse(readFileSync(resolve(dist,'data/game.json')));
if(createHash('sha256').update(new Uint8Array(buffer)).digest('hex')!==runtime.transport.unpacked_sha256)throw new Error('Lossless transport mismatch');
const reports=[],clips=[];
try{
for(const [name,engine] of Object.entries({chromium,firefox,webkit})){
 let browser;
 try{browser=await engine.launch({headless:true});}catch(error){reports.push({browser:name,status:'UNAVAILABLE',reason:String(error),operator_command:`sudo ${process.execPath} ${resolve(root,'packages/kernel-ts/node_modules/playwright/cli.js')} install-deps chromium firefox webkit`});continue;}
 try{
  const runs=[];
  for(const viewport of [{width:390,height:844},{width:1440,height:900}]){
   const page=await browser.newPage({viewport});const errors=[],requests=[];page.on('response',r=>{requests.push(r.url());if(r.status()>=400)errors.push('HTTP '+r.status()+' '+r.url());});page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
   await page.goto(url+'/internet-vs-one-fly/?test=1');await page.waitForFunction(()=>window.flyTest?.ready());
   const prefix=`${name}-${viewport.width}x${viewport.height}`;const screenshots=[];let capturedTakeoff=false;const board=await page.locator('#table').boundingBox();if(viewport.width===390 && (!board||board.height<844*.6||board.y+board.height>844))throw new Error('Mobile board is not the above-fold hero');
   async function shot(stage){const file=`${prefix}-${stage}.png`;await page.screenshot({path:resolve(out,file)});screenshots.push(file);}
   const meta=await page.locator('meta[property="og:image"]').getAttribute('content');if(meta!=='https://alpi157.github.io/internet-vs-one-fly/og-image.png')throw new Error('OG base path');
   if(!(await page.request.get(url+'/internet-vs-one-fly/og-image.png')).ok())throw new Error('Missing OG image');
   if(requests.some(v=>v.includes('/coupling/')||v.includes('/coupling-')))throw new Error('Coupling data eagerly loaded');
   await shot('start');await page.click('#start');
   const seen=new Set();
   for(let i=0;i<6;i++){
    const state=await page.evaluate(()=>window.flyTest.state());
    const x=i%2?5:state.frame.body.x,y=i%2?5:state.frame.body.y;
    const hold_ms=i<2?80:600,intervals=Math.round(8/profile.strikes[i<2?0:2].speed/10),half=Math.floor(intervals/2);
    await page.evaluate(({x,y,hold_ms})=>window.flyTest.strike(x,y,hold_ms),{x,y,hold_ms});
    await page.evaluate(n=>window.flyTest.advance(n),half);if(i===0)await shot('mid-strike');
    await page.evaluate(n=>window.flyTest.advance(n),intervals-half);
    const impact=await page.evaluate(()=>window.flyTest.state().frame.impact);
    if(!impact)throw new Error('missing authoritative impact');
    const result=impact.caught?'caught':'escaped';if(!seen.has(result)){await shot(result);seen.add(result);}
    await page.evaluate(()=>window.flyTest.advance(20));
    await page.waitForFunction(()=>window.flyTest.state().replaying);
    if(!capturedTakeoff && await page.evaluate(()=>window.flyTest.showRecorded('takeoff'))){await page.evaluate(()=>document.getElementById('brain-panel').classList.remove('active'));await shot('takeoff');await page.evaluate(()=>document.getElementById('brain-panel').classList.add('active'));capturedTakeoff=true;}
    if(i===2){
      if(!await page.evaluate(()=>window.flyTest.showRecorded('flash')))throw new Error('No recorded flash');await shot('brain-cam-flash');
      const [downloaded]=await Promise.all([page.waitForEvent('download'),page.click('#card')]);await downloaded.saveAs(resolve(out,`${prefix}-card.png`));const cardBytes=readFileSync(resolve(out,`${prefix}-card.png`));if(cardBytes.readUInt32BE(16)!==1200||cardBytes.readUInt32BE(20)!==630)throw new Error('Result card dimensions');if(!downloaded.suggestedFilename().endsWith('.png'))throw new Error('card export type');
      if(viewport.width===390 && await page.locator('#video').isEnabled()){
        const [clip]=await Promise.all([page.waitForEvent('download',{timeout:15000}),page.click('#video')]);const clipPath=resolve(out,`${name}-replay.${clip.suggestedFilename().split('.').at(-1)}`);await clip.saveAs(clipPath);const clipBytes=readFileSync(clipPath);const dimensions=await page.evaluate(base64=>new Promise((resolve,reject)=>{const video=document.createElement('video');video.onloadedmetadata=()=>resolve({width:video.videoWidth,height:video.videoHeight});video.onerror=()=>reject(new Error('Exported clip unreadable'));video.src='data:video/webm;base64,'+base64;}),clipBytes.toString('base64'));if(dimensions.width!==720||dimensions.height!==1280)throw new Error('Portrait clip dimensions');clips.push({browser:name,bytes:clipBytes.length,...dimensions});
      }

    }
    if(i<5)await page.click('#continue');
   }
   if(!capturedTakeoff)throw new Error('No recorded takeoff in scripted round');
   const log=await page.evaluate(()=>window.flyTest.log());const result=await replayLog(buffer,runtime,profile,log);
   if(!result.matches)throw new Error('browser input log differs on Node re-execution');
   if(log.inputs.length!==6)throw new Error('round did not apply six strikes');
   if(!seen.has('caught')||!seen.has('escaped'))throw new Error('script did not capture both actual outcomes');
   const selectedPerformance=await page.evaluate(()=>window.flyTest.state().simSpeed);
   await page.evaluate(()=>{document.getElementById('brain-panel').classList.remove('active');});
   await page.click('#lab');await page.selectOption('#lab-mode','scramble');await page.waitForFunction(()=>window.flyTest.ready());await page.click('#start');await page.evaluate(()=>window.flyTest.advance(20));await page.evaluate(()=>window.scrollTo(0,0));await shot('lab-scrambled');
   const labLog=await page.evaluate(()=>window.flyTest.log());const lab=await configureLab('scramble',buffer,runtime,url+'/internet-vs-one-fly/');const labReplay=await replayLog(lab.buffer,lab.runtime,profile,labLog);if(!labReplay.matches)throw new Error('Lab Node replay mismatch');
   const frameRate=await page.evaluate(()=>new Promise(resolve=>{let count=0;const start=performance.now();function tick(now){count++;if(now-start>=2000)resolve(count/((now-start)/1000));else requestAnimationFrame(tick);}requestAnimationFrame(tick);}));const perf=await page.evaluate(()=>window.flyTest.state());
   if(errors.length)throw new Error(errors.join('\n'));
   writeFileSync(resolve(out,`${prefix}-round.json`),JSON.stringify(log,null,2)+'\n');
   runs.push({viewport,status:'PASS',console_errors:errors,applied_inputs:log.inputs.length,digest:log.digest,node_replay_digest:result.digest,frame_rate_fps:frameRate,simulation_wall_seconds_per_simulated_second:selectedPerformance,lab_simulation_wall_seconds_per_simulated_second:perf.simSpeed,screenshots,takeoff_captured:capturedTakeoff,lab_node_replay_digest:labReplay.digest,board_bounds:board});
   await page.evaluate(()=>window.flyTest.startLive());await page.waitForFunction(()=>window.flyTest.ready());await page.evaluate(()=>window.flyTest.start());
   const liveGameFPS=await page.evaluate(()=>new Promise(resolve=>{let count=0;const start=performance.now();function frame(now){count++;if(now-start>=3000)resolve(count/((now-start)/1000));else requestAnimationFrame(frame);}requestAnimationFrame(frame);}));
   runs.at(-1).live_game_fps=liveGameFPS;
   if(name==='webkit'&&viewport.width===390&&liveGameFPS<55)throw new Error('Live WebKit game below 55 fps');
   await page.click('#coupling');await page.waitForFunction(()=>window.couplingTest?.ready());
   const coupling=[];
   for(const scale of [.01,.03,.06]){
     await page.evaluate(s=>window.couplingTest.setScale(s),scale);
     await page.waitForFunction(s=>window.couplingTest.state().scale===s&&window.couplingTest.state().panels[0]?.tick>=4000,scale,{timeout:60000});
     const measured=await page.evaluate(()=>new Promise(resolve=>{let count=0;const start=performance.now();function frame(now){count++;if(now-start>=2000)resolve(count/((now-start)/1000));else requestAnimationFrame(frame);}requestAnimationFrame(frame);}));
     await shot('coupling-'+scale);const state=await page.evaluate(()=>window.couplingTest.state());
     for(const p of state.panels){const rate=p.counts.reduce((a,b)=>a+b,0)/2641/p.seconds;if(Math.abs(rate-p.rate)>1e-10)throw new Error('Heat counts disagree with rate meter');}
     if(name==='webkit'&&viewport.width===390&&measured<55)throw new Error('Live WebKit coupling lab below 55 fps');
     coupling.push({scale,fps:measured,speed:state.speed,rates:state.panels.map(p=>p.rate),ticks:state.panels.map(p=>p.tick)});
   }
   await page.click('#coupling-drop');
   if(name==='chromium'&&viewport.width===390&&await page.locator('#coupling-clip').isEnabled()){
     const [clip]=await Promise.all([page.waitForEvent('download',{timeout:30000}),page.click('#coupling-clip')]);const clipPath=resolve(out,'measured-vs-scrambled.webm');await clip.saveAs(clipPath);
     const dimensions=await page.evaluate(base64=>new Promise((resolve,reject)=>{const v=document.createElement('video');v.onloadedmetadata=()=>resolve([v.videoWidth,v.videoHeight]);v.onerror=()=>reject(new Error('Coupling clip unreadable'));v.src='data:video/webm;base64,'+base64;}),readFileSync(clipPath).toString('base64'));
     if(dimensions[0]!==720||dimensions[1]!==1280)throw new Error('Coupling clip dimensions');
   }
   if(process.env.FLYBENCH_CAPTURE_HERO==='1'&&name==='chromium'&&viewport.width===1440){
     mkdirSync(resolve(out,'hero-frames'),{recursive:true});let index=0;
     for(const scale of [.01,.02,.03,.039,.05,.06]){await page.evaluate(s=>window.couplingTest.setScale(s),scale);for(let i=0;i<10;i++){await page.waitForTimeout(100);await page.locator('.coupling-view').screenshot({path:resolve(out,'hero-frames',String(index++).padStart(3,'0')+'.png')});}}
   }
   if(errors.length)throw new Error(errors.join('\n'));
   runs.at(-1).coupling=coupling;runs.at(-1).base_path_resources='PASS';runs.at(-1).coupling_lazy_load='PASS';
   await page.close();
  }
  reports.push({browser:name,version:browser.version(),status:'PASS',runs});
 }catch(error){reports.push({browser:name,status:'FAIL',reason:String(error)});}finally{await browser.close();}
}
}finally{await new Promise(r=>server.close(r));}
function files(path){return readdirSync(path).flatMap(n=>statSync(join(path,n)).isDirectory()?files(join(path,n)):[join(path,n)]);}
const sizes=files(dist).map(p=>({path:p.slice(dist.length+1),bytes:statSync(p).size,gzip_bytes:p.endsWith('.gz')?statSync(p).size:gzipSync(readFileSync(p)).length}));const gzip_bytes=sizes.filter(v=>!v.path.includes('lab-targets')&&!v.path.includes('/lab-')&&!v.path.includes('/coupling')).reduce((n,v)=>n+v.gzip_bytes,0);
const report={status:reports.every(r=>r.status==='PASS')&&gzip_bytes<=1500000?'PASS':reports.some(r=>r.status==='FAIL')||gzip_bytes>1500000?'FAIL':'INCOMPLETE',reports,clips,gzip_bytes,lab_gzip_bytes:sizes.filter(v=>v.path.includes('lab-targets')||v.path.includes('/lab-')).reduce((n,v)=>n+v.gzip_bytes,0),coupling_gzip_bytes:sizes.filter(v=>v.path.includes('/coupling')).reduce((n,v)=>n+v.gzip_bytes,0),budget_bytes:1500000,sizes,measurement_scope:'Development host, headed rendering pipeline in headless engines, manual deterministic worker pacing; rAF count over a separate two-second rendering window after the scripted round. Simulation wall time includes step and trace capture, excludes message serialization and hashing. live_game_fps uses a three-second running worker window. Coupling fps uses two seconds with paired simulations running; heat snapshots arrive every 50 simulated ms and remain recorded observations between updates.'};
writeFileSync(resolve(out,'e2e.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));if(report.status==='FAIL')process.exitCode=1;
