import {build} from 'esbuild';
import {chromium,firefox,webkit} from 'playwright';
import {createServer} from 'node:http';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {gzipSync} from 'node:zlib';
const root=resolve(import.meta.dirname,'../../..');
const bundled=await build({entryPoints:[resolve(root,'packages/kernel-ts/src/worker.ts')],bundle:true,write:false,format:'iife',platform:'browser',target:'es2022',minify:true});
const worker=bundled.outputFiles[0].contents;
const files=new Map([['/',{type:'text/html',bytes:Buffer.from('<!doctype html><title>FlyBench parity</title>')}],['/worker.js',{type:'text/javascript',bytes:worker}]]);
const logs=new Map();
const bundles=[];
for(const name of ['fixture','t1a','t1b']) {
 const stem=name==='fixture'?resolve(root,'packages/kernel-ts/test/fixtures/v2c-runner'):resolve(root,'data/compiled/v2',name+'-runner');
 if(!existsSync(stem+'.json'))continue;
 const log=JSON.parse(readFileSync(stem+'.json','utf8'));
 const graph=readFileSync(name==='fixture'?resolve(root,'packages/kernel-ts/test/fixtures/escape.webbin'):stem+'.webbin');logs.set(name,log);
 files.set('/'+name+'.json',{type:'application/json',bytes:Buffer.from(JSON.stringify(log))});
 files.set('/'+name+'.webbin',{type:'application/octet-stream',bytes:graph});
 bundles.push({graph:name,worker_javascript_bytes:worker.length,worker_gzip_bytes:gzipSync(worker).length,graph_bytes:graph.length,graph_gzip_bytes:gzipSync(graph).length,total_gzip_transfer_bytes:gzipSync(worker).length+gzipSync(graph).length,definition:'worker JS plus binary graph, independently gzip compressed; no test logs or dependencies'});
}
const server=createServer((req,res)=>{const file=files.get(req.url);if(!file){res.writeHead(404).end();return;}res.writeHead(200,{'Content-Type':file.type});res.end(file.bytes);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url=`http://127.0.0.1:${server.address().port}`;
const reports=[];
try {
 for(const [name,engine] of Object.entries({chromium,firefox,webkit})) {
  let browser;
  try {browser=await engine.launch({headless:true});}
  catch(error){reports.push({browser:name,status:'UNAVAILABLE',reason:String(error)});continue;}
  try {
   const page=await browser.newPage();await page.goto(url);
   const cases=[];
   for(const graph of ['fixture','t1a','t1b']) {
    if(!logs.has(graph)){cases.push({graph,status:'UNAVAILABLE',reason:'local export absent'});continue;}
    const result=await page.evaluate(async({graph})=>{
     const buffer=await (await fetch('/'+graph+'.webbin')).arrayBuffer();
     const log=await (await fetch('/'+graph+'.json')).json();
     const run=(digests)=>new Promise((resolve,reject)=>{
      const worker=new Worker('/worker.js');worker.onerror=e=>{worker.terminate();reject(new Error(e.message));};
      worker.onmessage=e=>{worker.terminate();if(e.data.error)reject(new Error(e.data.error));else resolve(e.data.result);};
      worker.postMessage({id:1,buffer:buffer.slice(0),log,digests});
     });
     const parity=await run(true);
     const timings=[];
     if(graph!=='fixture')for(let i=0;i<3;i++)timings.push((await run(false)).wall_seconds_per_simulated_second);
     return {parity,timings};
    },{graph});
    const log=logs.get(graph);
    const mismatches=result.parity.digests.flatMap((digest,i)=>digest===log.intervals[i].expected_state_sha256?[]:[i+1]);
    cases.push({graph,status:mismatches.length?'FAIL':'PASS',intervals:log.intervals.length,mismatches,digests:result.parity.digests,wall_seconds_per_simulated_second:result.timings,parameters:log.parameters});
   }
   reports.push({browser:name,version:browser.version(),status:cases.every(c=>c.status==='PASS')?'PASS':'FAIL',cases});
  } catch(error){reports.push({browser:name,status:'FAIL',reason:String(error)});}
  finally {await browser.close();}
 }
} finally {await new Promise(resolve=>server.close(resolve));}
const report={schema:'flybench.v2c.browser-parity',status:reports.some(r=>r.status==='FAIL')?'FAIL':reports.every(r=>r.status==='PASS')?'PASS':'INCOMPLETE',browser_reports:reports,bundles,timing_definition:'Three fresh workers, 2 simulated seconds each, same active C7 grid point and strike log; interval hashing disabled for timing. Cold worker initialization excluded. Development machine only.'};
const out=resolve(root,'evidence/V2C/p3');mkdirSync(out,{recursive:true});writeFileSync(resolve(out,'browser-parity.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({status:report.status,browsers:reports.map(r=>({browser:r.browser,status:r.status,cases:r.cases?.map(({digests,...c})=>c)})),bundles}));
if(report.status==='FAIL')process.exitCode=1;
