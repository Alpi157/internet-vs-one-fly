// Isolated preview harness. No import or change to game UI or simulation.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {build} from '../../../packages/kernel-ts/node_modules/esbuild/lib/main.js';
import {chromium,firefox,webkit} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
const root=resolve(import.meta.dirname,'../../..'),out=resolve(root,process.env.FLYBENCH_ANATOMY_OUT??'evidence/V2G/browser');mkdirSync(out,{recursive:true});
const data=resolve(root,'apps/play/public/data/anatomy');
const js=(await build({entryPoints:[resolve(root,'apps/play/src/anatomy.ts')],bundle:true,format:'esm',write:false})).outputFiles[0].text;
const pageHTML='<!doctype html><meta name="viewport" content="width=device-width"><style>body{margin:0;background:black;color:white}canvas{display:block;width:100%;height:100vh}</style><canvas></canvas>';
const server=createServer((req,res)=>{
 try{
  const name=new URL(req.url,'http://localhost').pathname;
  if(name==='/favicon.ico'){res.writeHead(204).end();return;}
  if(name==='/'){res.setHeader('Content-Type','text/html');res.end(pageHTML);return;}
  if(name==='/decoder.js'){res.setHeader('Content-Type','text/javascript');res.end(js);return;}
  if(!['/manifest.json','/neuropils.json','/t1a-phone.arbors.gz','/t1b-phone.arbors.gz'].includes(name)){res.writeHead(404).end();return;}
  res.setHeader('Content-Type',name.endsWith('.json')?'application/json':'application/octet-stream');res.end(readFileSync(resolve(data,'.'+name)));
 }catch{res.writeHead(500).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const url=`http://127.0.0.1:${server.address().port}`;const results=[];
try{
 for(const [browserName,engine] of Object.entries({chromium,firefox,webkit})){
  const browser=await engine.launch({headless:true});
  try{
   for(const viewport of [{width:390,height:844},{width:1440,height:900}]){
    const page=await browser.newPage({viewport});const errors=[];
    page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
    await page.goto(url);
    for(const circuit of ['T1a','T1b']){
     const report=await page.evaluate(async({circuit,viewport})=>{
      const {decodeArbors}=await import('/decoder.js');
      const manifest=await fetch('/manifest.json').then(r=>r.json()),rois=await fetch('/neuropils.json').then(r=>r.json());
      const asset=manifest.assets.find(a=>a.circuit===circuit&&a.lod==='phone');
      const response=await fetch('/'+asset.file),buffer=await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
      const before=performance.memory?.usedJSHeapSize??null;const times=[];let decoded;
      for(let i=0;i<5;i++){const start=performance.now();decoded=decodeArbors(buffer);times.push(performance.now()-start);}
      const after=performance.memory?.usedJSHeapSize??null;
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer))).map(v=>v.toString(16).padStart(2,'0')).join('');
      const canvas=document.querySelector('canvas');canvas.width=viewport.width;canvas.height=viewport.height;const c=canvas.getContext('2d');
      c.fillStyle='black';c.fillRect(0,0,canvas.width,canvas.height);
      const [x0,y0,x1,y1]=decoded.bbox,scale=Math.min((canvas.width-36)/(x1-x0),(canvas.height-155)/(y1-y0));
      const drawPoint=p=>[18+(p[0]-x0)*scale,110+(p[1]-y0)*scale];
      function path(points){if(!points.length)return;c.beginPath();points.forEach((p,i)=>{const q=drawPoint(p);i?c.lineTo(...q):c.moveTo(...q);});c.stroke();}
      c.strokeStyle='#cc28ad';c.lineWidth=.5;
      for(const roi of rois.rois)for(const contour of roi.contours_um)path(contour);
      c.strokeStyle='#a6c4cf';c.globalAlpha=.065;c.lineWidth=.35;
      for(let i=0;i<decoded.parents.length;i++){
       const parent=decoded.parents[i];if(parent<0)continue;
       c.strokeStyle=decoded.bridges[i]?'#efaf39':'#a6c4cf';c.globalAlpha=decoded.bridges[i]?.8:.065;c.lineWidth=decoded.bridges[i]?1:.35;c.setLineDash(decoded.bridges[i]?[3,2]:[]);
       c.beginPath();c.moveTo(...drawPoint(decoded.point(parent)));c.lineTo(...drawPoint(decoded.point(i)));c.stroke();
      }
      c.setLineDash([]);c.globalAlpha=.065;
      c.fillStyle='#a6c4cf';for(let i=0;i<decoded.parents.length;i++)if(decoded.parents[i]<0){const q=drawPoint(decoded.point(i));c.fillRect(q[0],q[1],.5,.5);}
      c.globalAlpha=1;c.fillStyle='white';c.font='11px monospace';
      for(const [i,line] of [`${circuit}: ${decoded.neurons.length} real neuron skeleton slots`,'Composite layout: brain frontal view,','VNC ventral view; not a single projection.','Amber bridges: layout, not anatomy'].entries())c.fillText(line,18,20+i*18);
      c.strokeStyle='white';c.lineWidth=2;const y=canvas.height-24;c.beginPath();c.moveTo(20,y);c.lineTo(20+100*scale,y);c.stroke();c.fillText('100 µm',20,y-8);
      return {circuit,viewport,uncompressed_sha256:hash,neurons:decoded.neurons.length,missing:decoded.neurons.filter(n=>n.missing).length,
       decode_ms:times,median_decode_ms:[...times].sort((a,b)=>a-b)[2],coordinate_and_index_buffer_bytes:buffer.byteLength,decoder_allocated_array_bytes:decoded.allocatedArrayBytes,
       browser_heap_before_bytes:before,browser_heap_after_bytes:after,
       memory_scope:'Exact binary storage bytes; browser performance.memory readings when available. Object overhead, GPU memory and total process RSS are not measured.',
       canvas_scale_pixels_per_um:scale,scale_bar_um:100,view:manifest.frame.view,
       layout_bridges:decoded.bridges.reduce((a,b)=>a+b,0),format:decoded.format};
     },{circuit,viewport});
     const manifest=JSON.parse(readFileSync(resolve(data,'manifest.json'))),asset=manifest.assets.find(a=>a.circuit===circuit&&a.lod==='phone');
     assert.equal(report.uncompressed_sha256,asset.uncompressed_sha256);assert.equal(report.neurons,asset.neurons);assert.equal(report.missing,asset.missing_skeletons.length);
     assert.equal(report.layout_bridges,asset.layout_bridges);assert.equal(report.format,'FLYARB03');assert.equal(report.view,manifest.frame.view);
     assert.equal(errors.length,0,errors.join('\n'));
     const screenshot=`${browserName}-${viewport.width}x${viewport.height}-${circuit}.png`;await page.screenshot({path:resolve(out,screenshot)});
     results.push({browser:browserName,status:'PASS',...report,screenshot,console_errors:errors});
    }
    await page.close();
   }
  }finally{await browser.close();}
 }
 writeFileSync(resolve(out,'decode-results.json'),JSON.stringify({classification:'Data-only anatomy decoder and static canvas, no simulation',results},null,2)+'\n');
 console.log('PASS: phone assets decoded and drawn in Chromium, Firefox and WebKit at both viewports; hashes, screenshots, decode times and memory scope recorded');
}finally{await new Promise(r=>server.close(r));}
