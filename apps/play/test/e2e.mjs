import {chromium,firefox,webkit} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {createServer} from 'node:http';
import {readFileSync,writeFileSync,mkdirSync,readdirSync,statSync} from 'node:fs';
import {resolve,extname,join} from 'node:path';
import {gzipSync} from 'node:zlib';
import {replayLog} from '../src/game.ts';
const root=resolve(import.meta.dirname,'../../..'),dist=resolve(root,'apps/play/dist'),out=resolve(root,'evidence/V2D/game');mkdirSync(out,{recursive:true});
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.webbin':'application/octet-stream'};
const server=createServer((req,res)=>{try{const url=new URL(req.url,'http://localhost');if(url.pathname==='/favicon.ico'){res.writeHead(204).end();return;}const path=resolve(dist,'.'+(url.pathname==='/'?'/index.html':url.pathname));if(!path.startsWith(dist+'/')){res.writeHead(403).end();return;}res.setHeader('Content-Type',mime[extname(path)]??'application/octet-stream');res.end(readFileSync(path));}catch{res.writeHead(404).end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const url=`http://127.0.0.1:${server.address().port}`;
const raw=readFileSync(resolve(dist,'data/circuit.webbin')),buffer=raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength);
const runtime=JSON.parse(readFileSync(resolve(dist,'data/runtime.json'))),profile=JSON.parse(readFileSync(resolve(dist,'data/game.json')));
const reports=[];
try{
for(const [name,engine] of Object.entries({chromium,firefox,webkit})){
 let browser;
 try{browser=await engine.launch({headless:true});}catch(error){reports.push({browser:name,status:'UNAVAILABLE',reason:String(error),operator_command:`sudo ${process.execPath} ${resolve(root,'packages/kernel-ts/node_modules/playwright/cli.js')} install-deps chromium firefox webkit`});continue;}
 try{
  const runs=[];
  for(const viewport of [{width:390,height:844},{width:1440,height:900}]){
   const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
   await page.goto(url+'/?test=1');await page.waitForFunction(()=>window.flyTest?.ready());
   const prefix=`${name}-${viewport.width}x${viewport.height}`;const screenshots=[];
   async function shot(stage){const file=`${prefix}-${stage}.png`;await page.screenshot({path:resolve(out,file)});screenshots.push(file);}
   await shot('start');await page.click('#start');
   const seen=new Set();
   for(let i=0;i<6;i++){
    const state=await page.evaluate(()=>window.flyTest.state());
    const x=i%2?5:state.frame.body.x,y=i%2?5:state.frame.body.y;
    await page.evaluate(({x,y})=>window.flyTest.strike(x,y,80),{x,y});
    await page.evaluate(()=>window.flyTest.advance(4));if(i===0)await shot('mid-strike');
    await page.evaluate(()=>window.flyTest.advance(4));
    const impact=await page.evaluate(()=>window.flyTest.state().frame.impact);
    if(!impact)throw new Error('missing authoritative impact');
    const result=impact.caught?'caught':'escaped';if(!seen.has(result)){await shot(result);seen.add(result);}
    await page.evaluate(()=>window.flyTest.advance(20));
    await page.waitForFunction(()=>window.flyTest.state().replaying);
    if(i===0){
      await page.locator('#brain-panel').scrollIntoViewIfNeeded();await shot('brain-cam');
      const card=page.waitForEvent('download');await page.click('#card');const downloaded=await card;if(!downloaded.suggestedFilename().endsWith('.png'))throw new Error('card export type');
      if(viewport.width===390 && await page.locator('#video').isEnabled()){
        const video=page.waitForEvent('download',{timeout:15000});await page.click('#video');const clip=await video;await clip.saveAs(resolve(out,`${name}-replay.${clip.suggestedFilename().split('.').at(-1)}`));
      }
      await page.locator('#table').scrollIntoViewIfNeeded();
    }
    if(i<5)await page.click('#continue');
   }
   const log=await page.evaluate(()=>window.flyTest.log());const result=await replayLog(buffer,runtime,profile,log);
   if(!result.matches)throw new Error('browser input log differs on Node re-execution');
   if(log.inputs.length!==6)throw new Error('round did not apply six strikes');
   if(!seen.has('caught')||!seen.has('escaped'))throw new Error('script did not capture both actual outcomes');
   const frameRate=await page.evaluate(()=>new Promise(resolve=>{let count=0;const start=performance.now();function tick(now){count++;if(now-start>=2000)resolve(count/((now-start)/1000));else requestAnimationFrame(tick);}requestAnimationFrame(tick);}));const perf=await page.evaluate(()=>window.flyTest.state());
   if(errors.length)throw new Error(errors.join('\n'));
   writeFileSync(resolve(out,`${prefix}-round.json`),JSON.stringify(log,null,2)+'\n');
   runs.push({viewport,status:'PASS',console_errors:errors,applied_inputs:log.inputs.length,digest:log.digest,node_replay_digest:result.digest,frame_rate_fps:frameRate,simulation_wall_seconds_per_simulated_second:perf.simSpeed,screenshots});
   await page.close();
  }
  reports.push({browser:name,version:browser.version(),status:'PASS',runs});
 }catch(error){reports.push({browser:name,status:'FAIL',reason:String(error)});}finally{await browser.close();}
}
}finally{await new Promise(r=>server.close(r));}
function files(path){return readdirSync(path).flatMap(n=>statSync(join(path,n)).isDirectory()?files(join(path,n)):[join(path,n)]);}
const sizes=files(dist).map(p=>({path:p.slice(dist.length+1),bytes:statSync(p).size,gzip_bytes:gzipSync(readFileSync(p)).length}));const gzip_bytes=sizes.reduce((n,v)=>n+v.gzip_bytes,0);
const report={status:reports.every(r=>r.status==='PASS')&&gzip_bytes<=1500000?'PASS':reports.some(r=>r.status==='FAIL')||gzip_bytes>1500000?'FAIL':'INCOMPLETE',reports,gzip_bytes,budget_bytes:1500000,sizes,measurement_scope:'Development host, headed rendering pipeline in headless engines, manual deterministic worker pacing; rAF count over a separate two-second rendering window after the scripted round. Simulation wall time includes step and trace capture, excludes message serialization and hashing.'};
writeFileSync(resolve(out,'e2e.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));if(report.status==='FAIL')process.exitCode=1;
