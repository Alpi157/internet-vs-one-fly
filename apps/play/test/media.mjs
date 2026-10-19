import {chromium} from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {serve,root,dist,prefix} from './site-server.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
const browser=await chromium.launch({headless:true});
if(process.argv.includes('--icons')){
 try{const page=await browser.newPage(),svg=readFileSync(resolve(root,'docs/design/v4/assets/fly.svg'),'utf8');for(const size of [180,192,512]){await page.setViewportSize({width:size,height:size});await page.setContent(`<style>body{margin:0;background:#000}svg{width:100vw;height:100vh;padding:10%}</style>${svg}`);await page.screenshot({path:resolve(root,`apps/play/public/icon-${size}.png`)});}}finally{await browser.close();}process.exit(0);
}
const {server,origin}=await serve(),url=origin+prefix,frames='/tmp/flybench-v2i-media-frames';mkdirSync(frames,{recursive:true});
const media=resolve(root,'docs/media'),provenance={schema:'flybench.media.v2i',capture_code_sha256:hash(readFileSync(import.meta.filename)),base_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),viewport:{width:1440,height:900},display_only:true,game:{},lab:{},assets:{}};
try{
 const page=await browser.newPage({viewport:provenance.viewport});await page.goto(url+'?test=1');await page.waitForFunction(()=>window.flyTest?.ready()&&window.flyTest.state().anatomyReady);await page.evaluate(()=>document.fonts.ready);await page.click('#start');
 let index=0;const capture=async()=>{await page.waitForTimeout(60);await page.screenshot({path:resolve(frames,`game-${String(index++).padStart(3,'0')}.png`)});};
 // A real keyboard-played hand, manually clocked for reproducible recorded frames.
 await page.locator('#table').focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('Enter');
 for(let i=0;i<16;i++){await page.evaluate(()=>window.flyTest.advance(1));await capture();}
 await page.evaluate(()=>window.flyTest.advance(20));await page.waitForFunction(()=>window.flyTest.state().replaying);
 // Replay is the UI's quarter-speed recorded sequence. No synthetic neural frames.
 await page.evaluate(()=>window.flyTest.showReplay());for(let i=0;i<30;i++){await capture();await page.waitForTimeout(40);}
 await page.evaluate(()=>window.flyTest.showRecorded('flash'));await page.waitForTimeout(100);await page.screenshot({path:resolve(media,'game-still.png')});
 const log=await page.evaluate(()=>window.flyTest.log());writeFileSync(resolve(root,'evidence/V2I/media-game-round.json'),JSON.stringify(log,null,2)+'\n');
 provenance.game={neural_seed:log.neural_seed,environment_seed:log.environment_seed,log,frames:index,frame_duration_ms:100,source:'Real Enter key strike followed by the UI recorded replay; live phase clocked one recorded control interval per capture.'};
 // The social card is the existing share renderer of the same real recorded frame.
 const [card]=await Promise.all([page.waitForEvent('download'),page.evaluate(()=>document.getElementById('card').click())]);await card.saveAs(resolve(root,'apps/play/public/og-image.png'));
 await page.locator('[data-wiring]:visible').first().click();await page.waitForFunction(()=>window.couplingTest?.ready());
 const rt=JSON.parse(readFileSync(resolve(dist,'data/coupling/runtime.json'))),strength=JSON.parse(readFileSync(resolve(dist,'data/coupling/strength-demo.json'))),game=JSON.parse(readFileSync(resolve(dist,'data/runtime.json')));
 provenance.lab={coupling:game.parameters.s,neural_seed:2027101401,environment_seed:8128,sign:rt.null_selection,strength,observations:[],frame_duration_ms:100};
 index=0;
 for(const family of ['N-SIGN','N-STRENGTH']){
  await page.locator(`input[value="${family}"]`).check();await page.waitForFunction(()=>window.couplingTest.ready());
  for(let i=0;i<24;i++){await page.screenshot({path:resolve(frames,`lab-${String(index++).padStart(3,'0')}.png`)});await page.waitForTimeout(70);}
  provenance.lab.observations.push(await page.evaluate(()=>window.couplingTest.state()));
 }
 await page.screenshot({path:resolve(media,'coupling-still.png')});provenance.lab.frames=index;
 for(const file of ['apps/play/public/data/runtime.json','apps/play/public/data/game.json','apps/play/public/data/coupling/runtime.json','apps/play/public/data/coupling/strength-demo.json','apps/play/public/data/anatomy/manifest.json','apps/play/public/og-image.png','apps/play/public/favicon.svg','docs/media/game-still.png','docs/media/coupling-still.png']){const b=readFileSync(resolve(root,file));provenance.assets[file]={bytes:b.length,sha256:hash(b)};}
 provenance.capture_source_sha256=Object.fromEntries(['main.ts','coupling.ts','coupling-worker.ts','brain-view.ts','field.ts','style.css','game.ts','worker.ts'].map(file=>['apps/play/src/'+file,hash(readFileSync(resolve(root,'apps/play/src/'+file)))]));
 writeFileSync(resolve(media,'media-provenance.json'),JSON.stringify(provenance,null,2)+'\n');
}finally{await browser.close();await new Promise(r=>server.close(r));}
