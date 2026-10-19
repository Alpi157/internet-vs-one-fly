import assert from 'node:assert/strict';
import { chromium, firefox, webkit } from '../../../packages/kernel-ts/node_modules/playwright/index.mjs';
import { createServer } from 'node:http';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, extname } from 'node:path';
import { gzipSync, gunzipSync } from 'node:zlib';
import { unpackGraph } from '../../../packages/kernel-ts/src/transport.ts';
import { replayLog } from '../src/game.ts';
const root = resolve(import.meta.dirname, '../../..'), dist = resolve(root, 'apps/play/dist'), out = resolve(root, process.env.FLYBENCH_GAME_OUT ?? 'evidence/V2I/a02/game');
mkdirSync(out, { recursive: true });
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png' };
const server = createServer((req, res) => { try {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/favicon.ico') {
        res.writeHead(204).end();
        return;
    }
    const p = resolve(dist, '.' + (url.pathname === '/internet-vs-one-fly/' ? '/index.html' : url.pathname.replace('/internet-vs-one-fly/', '/')));
    if (!p.startsWith(dist + '/'))
        throw Error('path');
    res.setHeader('Content-Type', mime[extname(p)] ?? 'application/octet-stream');
    res.end(readFileSync(p));
}
catch {
    res.writeHead(404).end();
} });
await new Promise(r => server.listen(0, '127.0.0.1', r));
const origin = `http://127.0.0.1:${server.address().port}`, url = origin + '/internet-vs-one-fly/?test=1';
const packed = gunzipSync(readFileSync(resolve(dist, 'data/circuit.flygraph.gz'))), buffer = unpackGraph(packed.buffer.slice(packed.byteOffset, packed.byteOffset + packed.byteLength));
const runtime = JSON.parse(readFileSync(resolve(dist, 'data/runtime.json'))), profile = JSON.parse(readFileSync(resolve(dist, 'data/game.json'))), reports = [];
const axe = readFileSync(resolve(root, 'apps/play/node_modules/axe-core/axe.min.js'), 'utf8');
async function fps(page) { return page.evaluate(() => new Promise(resolve => { let count = 0; const start = performance.now(); function tick(now) { count++; if (now - start >= 3000)
    resolve(count / ((now - start) / 1000));
else
    requestAnimationFrame(tick); } requestAnimationFrame(tick); })); }
try {
    for (const [name, engine] of Object.entries({ chromium, firefox, webkit })) {
        if (process.env.FLYBENCH_BROWSER && name !== process.env.FLYBENCH_BROWSER)
            continue;
        let browser;
        try {
            browser = await engine.launch({ headless: true });
            for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 1366, height: 768 }]) {
                const context = await browser.newContext({ viewport, serviceWorkers: 'block' }), external = [], errors = [], requests = new Set(), screenshots = [], scans = [];
                let initial = true;
                context.on('request', r => { if (initial)
                    requests.add(r.url()); if (!r.url().startsWith(origin) && !r.url().startsWith('data:') && !r.url().startsWith('blob:'))
                    external.push(r.url()); });
                await context.route('**/*', route => { const u = route.request().url(); if (!u.startsWith(origin) && !u.startsWith('data:') && !u.startsWith('blob:'))
                    return route.abort(); return route.continue(); });
                const page = await context.newPage();
                page.on('pageerror', e => { errors.push(String(e)); console.error('PAGE', String(e)); });
                page.on('console', m => { if (m.type() === 'error')
                    errors.push(m.text()); });
                page.on('response', r => { if (r.status() >= 400)
                    errors.push(`${r.status()} ${r.url()}`); });
                const prefix = `${name}-${viewport.width}x${viewport.height}`;
                await page.goto(url);
                await page.waitForFunction(() => window.flyTest?.ready());
                await page.addScriptTag({ content: axe });
                await page.waitForFunction(() => window.flyTest.state().anatomyReady, { timeout: 60000 });
                await page.evaluate(() => document.fonts.ready);
                initial = false;
                async function scan(state) { const result = await page.evaluate(async () => { const r = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } }); return { violations: r.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => ({ target: n.target, summary: n.failureSummary })) })), incomplete: r.incomplete.map(v => ({ id: v.id, impact: v.impact })) }; }); scans.push({ state, ...result }); const bad = result.violations.filter(v => ['critical', 'serious'].includes(v.impact)); assert.equal(bad.length, 0, JSON.stringify({ state, bad })); }
                async function shot(state) { await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(80); const file = `${prefix}-${state}.png`; await page.screenshot({ path: resolve(out, file) }); screenshots.push(file); await scan(state); }
                await shot('start');
                assert(await page.evaluate(() => document.fonts.check('900 32px Doto') && document.fonts.check('400 16px Atkinson')));
                const board = await page.locator('#table').boundingBox();
                assert(Math.abs(board.width - board.height) < 1);
                if (viewport.width === 390)
                    assert(board.width * 304 / 350 <= 390);
                await page.click('#start');
                await page.mouse.move(board.x + board.width / 2, board.y + board.height / 2);
                await page.mouse.down();
                await page.waitForTimeout(250);
                await shot('charging');
                await page.mouse.up();
                await page.evaluate(() => window.flyTest.advance(8));
                await page.locator('#landing').waitFor({ state: 'visible' });
                assert.equal(await page.locator('#strikes').innerText(),`Hand 1 of ${profile.max_strikes}`);assert(await page.locator('#pips .pip').first().evaluate(e=>e.classList.contains('current')));
                await shot('mid-strike');
                await page.evaluate(post => { const f=window.flyTest.state().frame; return window.flyTest.advance((f.strike.impact_tick+post*2-f.tick)/20); },profile.replay_post_ms);
                await page.waitForFunction(() => window.flyTest.state().replaying);
                await page.evaluate(() => window.flyTest.showRecorded('flash'));
                await shot('replay-brain');
                if (viewport.width === 390) {
                    await page.locator('#replay-sheet .close').focus();
                    await page.keyboard.press('Shift+Tab');
                    assert(await page.evaluate(() => document.getElementById('replay-sheet').contains(document.activeElement)));
                    await page.keyboard.press('Escape');
                    assert(!(await page.locator('#replay-sheet').evaluate(d => d.open)));
                    assert.equal(await page.evaluate(() => document.activeElement.id), 'table');
                    await page.click('#replay-last');
                }
                await page.getByLabel('Whole CNS', { exact: true }).check();
                await shot('replay-whole');
                await page.getByLabel('Brain', { exact: true }).check();
                await page.evaluate(() => window.flyTest.measureReplay(true));
                const replayFPS = await fps(page);
                await page.evaluate(() => window.flyTest.measureReplay(false));
                const clipCapability=await page.evaluate(()=>({mediaRecorder:typeof MediaRecorder!=='undefined',canvasCapture:'captureStream' in HTMLCanvasElement.prototype}));
                if(viewport.width===390 && await page.locator('#video').isEnabled()) {
                    const [clip] = await Promise.all([page.waitForEvent('download',{timeout:20000}),(async()=>{await page.click('#video');await page.keyboard.press('Escape');await page.click('#replay-last');})()]);
                    const clipPath=resolve(out,`${prefix}-replay.${clip.suggestedFilename().split('.').at(-1)}`);await clip.saveAs(clipPath);
                    const bytes=readFileSync(clipPath),dimensions=await page.evaluate(({base64,mime})=>new Promise((resolve,reject)=>{const video=document.createElement('video');video.onloadedmetadata=()=>resolve([video.videoWidth,video.videoHeight]);video.onerror=()=>reject(Error('Unreadable replay clip'));video.src='data:'+mime+';base64,'+base64;}),{base64:bytes.toString('base64'),mime:clipPath.endsWith('.mp4')?'video/mp4':'video/webm'});assert.deepEqual(dimensions,[720,1280]);
                }
                await page.click('#continue');
                // Remaining round is keyboard only. The second hand is deliberately far from the fly.
                let escaped = false;
                for (let hand = 1; hand < profile.max_strikes; hand++) {
                    await page.locator('#table').focus();
                    if (hand === 1)
                        for (let i = 0; i < 18; i++)
                            await page.keyboard.press('ArrowRight');
                    else {
                        await page.keyboard.press('ArrowLeft');
                        await page.keyboard.press('ArrowUp');
                    }
                    if (hand === 2) {
                        for (let i = 0; i < 18; i++)
                            await page.keyboard.press('ArrowLeft');
                        await page.keyboard.down('Space');
                        await page.waitForTimeout(550);
                        await page.keyboard.up('Space');
                    }
                    else
                        await page.keyboard.press('Enter');
                    const intervals = hand === 2 ? 32 : 16;
                    await page.evaluate(n => window.flyTest.advance(n), intervals);
                    const impact = await page.evaluate(() => window.flyTest.state().frame.impact);
                    assert(impact);assert.equal(await page.locator('#strikes').innerText(),`Hand ${hand+1} of ${profile.max_strikes}`);assert(await page.locator('#pips .pip').nth(hand).evaluate((e,caught)=>e.classList.contains(caught?'caught':'escaped'),impact.caught));
                    if (!impact.caught && !escaped) {
                        await shot('impact-escaped');
                        escaped = true;
                    }
                    await page.evaluate(() => window.flyTest.advance(20));
                    await page.waitForFunction(() => window.flyTest.state().replaying);
                    await page.locator('#continue').focus();
                    await page.keyboard.press('Enter');
                }
                assert(escaped);
                const summaryBounds=await page.locator('#round-sheet button').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {id:n.id,text:n.textContent,x:r.x,y:r.y,right:r.right,bottom:r.bottom};}));
                assert(summaryBounds.every(r=>r.x>=0&&r.y>=0&&r.right<=viewport.width&&r.bottom<=viewport.height),JSON.stringify(summaryBounds));
                await shot('round-summary');
                const [download] = await Promise.all([page.waitForEvent('download'), page.click('#share')]);
                const shareFile = `${prefix}-share-card.png`;
                await download.saveAs(resolve(out, shareFile));
                screenshots.push(shareFile);
                assert.equal(readFileSync(resolve(out, shareFile)).readUInt32BE(16), 1200);
                const log = await page.evaluate(() => window.flyTest.log());
                assert.equal(log.inputs.length, profile.max_strikes);
                const verified = await replayLog(buffer, runtime, profile, log);
                assert(verified.matches);
                writeFileSync(resolve(out, `${prefix}-round.json`), JSON.stringify(log, null, 2));
                await page.click('#play-again');
                await page.waitForFunction(() => window.flyTest?.ready());
                await page.addScriptTag({ content: axe });
                await page.evaluate(()=>document.getElementById('how-sheet').showModal());
                await shot('how-it-works');
                await page.keyboard.press('Escape');
                await page.emulateMedia({ reducedMotion: 'reduce' });
                await page.click('#start');
                await page.keyboard.press('Enter');
                await page.evaluate(() => window.flyTest.advance(8));
                await shot('reduced-motion');
                assert((await page.evaluate(() => window.flyTest.state())).reduced);
                await page.emulateMedia({ reducedMotion: 'no-preference' });
                await page.evaluate(() => window.flyTest.startLive());
                await page.waitForFunction(() => window.flyTest.ready());
                await page.evaluate(() => window.flyTest.start());
                await page.waitForFunction(() => window.flyTest.state().anatomyReady);
                const liveFPS = await fps(page);
                const state = await page.evaluate(() => window.flyTest.state()), heap = await page.evaluate(() => performance.memory?.usedJSHeapSize ?? null);
                // A separate complete round uses only real keyboard events, including start and next-hand buttons.
                await page.goto(url);
                await page.waitForFunction(() => window.flyTest?.ready());
                await page.locator('#start').focus();
                await page.keyboard.press('Enter');
                for (let n = 0; n < profile.max_strikes; n++) {
                    await page.keyboard.press('ArrowRight');
                    await page.keyboard.press('Enter');
                    await page.evaluate(() => window.flyTest.advance(36));
                    await page.waitForFunction(() => window.flyTest.state().replaying);
                    await page.locator('#continue').focus();
                    await page.keyboard.press('Enter');
                }
                assert.equal((await page.evaluate(() => window.flyTest.log())).inputs.length, profile.max_strikes);
                // A completed-round modal must not keep the coupling lab inert.
                await page.locator('#round-sheet [data-wiring]').click();await page.locator('#coupling-canvas').waitFor({state:'visible'});await page.waitForFunction(()=>window.couplingTest?.ready());await page.locator('#coupling-close:visible, #lab-play:visible').first().click();await page.locator('#round-sheet').waitFor({state:'visible'});
                // Both existing labs remain reachable from Wiring lab.
                await page.locator('#round-sheet [data-wiring]').click();
                await page.click('#silence-tab');
                await page.click('[data-lesion=LC4]');
                await page.locator('#circuit-badge').waitFor({state:'visible'});
                await page.waitForFunction(() => window.flyTest.ready());
                await page.evaluate(() => window.flyTest.advance(10));
                assert.equal((await page.evaluate(() => window.flyTest.log())).graph_identity.endsWith(':LC4'), true);
                await page.locator('[data-wiring]:visible').first().click();
                await page.locator('#coupling-canvas').waitFor({state:'visible'});
                await page.waitForFunction(() => window.couplingTest?.ready());
                await page.waitForFunction(() => window.couplingTest.state().panels[0]?.tick > 0);
                assert(await page.locator('#coupling-canvas').isVisible());
                const initialFiles = [...requests].filter(u => u.startsWith(origin)).map(u => u.split('/internet-vs-one-fly/')[1]?.split('?')[0] || 'index.html').filter(p => !p.includes('data/anatomy/') && p !== 'data/brain.json' && !p.includes('circuit.flygraph') && !p.includes('favicon'));
                const unique = [...new Set(initialFiles)];
                const initialSizes = unique.map(p => { const b = readFileSync(resolve(dist, p)); return { path: p, bytes: b.length, gzip_bytes: p.endsWith('.gz') || p.endsWith('.woff2') ? b.length : gzipSync(b).length }; });
                assert.equal(external.length, 0, external.join('\n'));
                assert.equal(errors.length, 0, errors.join('\n'));
                console.log(prefix, JSON.stringify({ liveFPS, replayFPS, renderer: state.renderer }));
                assert(liveFPS >= (viewport.width === 390 ? 55 : 50), `live ${liveFPS}`);
                assert(replayFPS >= 50, `replay ${replayFPS}`);
                reports.push({ browser: name, version: browser.version(), viewport, status: 'PASS', live_fps: liveFPS, replay_fps: replayFPS, anatomy_load_ms: state.anatomyLoadMs, anatomy_lod: state.lod, renderer: state.renderer, js_heap_bytes: heap, initial_download_bytes: initialSizes.reduce((n, f) => n + f.bytes, 0), initial_gzip_bytes: initialSizes.reduce((n, f) => n + f.gzip_bytes, 0), initial_files: initialSizes, axe: scans, screenshots, external_requests: external, keyboard_full_round: 'PASS', focus_trap_escape_return: 'PASS', node_replay: 'PASS', labs: 'PASS', clip_capability:clipCapability, errors });
                console.log(`${prefix}: PASS live ${liveFPS.toFixed(1)} fps, replay ${replayFPS.toFixed(1)} fps`);
                if(viewport.width===390) {
                    const fallback=await context.newPage();await fallback.addInitScript(()=>{const get=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return type==='webgl2'?null:get.call(this,type,...args);};});
                    await fallback.goto(url);await fallback.waitForFunction(()=>window.flyTest?.state().anatomyReady);assert.equal(await fallback.evaluate(()=>window.flyTest.state().renderer),'Canvas soma fallback');await fallback.click('#start');await fallback.keyboard.press('Enter');await fallback.evaluate(()=>window.flyTest.advance(36));await fallback.waitForFunction(()=>window.flyTest.state().replaying);await fallback.screenshot({path:resolve(out,`${prefix}-canvas-fallback.png`)});reports.at(-1).canvas_fallback='PASS';await fallback.close();
                }
                assert.equal(external.length,0,external.join('\n'));
                await context.close();
            }
        }
        catch (e) {
            reports.push({ browser: name, status: 'FAIL', reason: String(e) });
            console.error(name, e);
        }
        finally {
            await browser?.close();
        }
    }
}
finally {
    await new Promise(r => server.close(r));
}
const report = { status: reports.every(r => r.status === 'PASS') ? 'PASS' : 'FAIL', scope: 'Production Vite build; headless desktop host engines, not physical phones. rAF opportunities over 3 seconds during active worker gameplay and recorded replay. Initial requests exclude graph, anatomy transports and the legacy soma map data/brain.json; include UI, runtime metadata, fonts and generated results. Gzip sizes are calculated; server sends uncompressed bytes. Anatomy load includes fetch, decompression, decode and GPU upload; heap is engine-exposed JS only.', reports };
writeFileSync(resolve(out, 'e2e.json'), JSON.stringify(report, null, 2) + '\n');
if (report.status !== 'PASS')
    process.exitCode = 1;
