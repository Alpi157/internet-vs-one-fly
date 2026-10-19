import './style.css';
import { fetchGraph } from '../../../packages/kernel-ts/src/transport.ts';
import { loadResults, renderResults } from './results.ts';
import { MicroscopeField } from './field.ts';
import type { BrainView } from './brain-view.ts';
import type { Frame } from './game.ts';
const app = document.querySelector<HTMLDivElement>('#app')!, base = import.meta.env.BASE_URL, shareURL = 'https://alpi157.github.io/internet-vs-one-fly/';
const icon = (path: string) => `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;
const closeIcon = icon('M6 6L18 18M18 6L6 18'), pauseIcon = icon('M8 5V19M16 5V19'), playIcon = icon('M8 5L19 12L8 19Z');
app.innerHTML = `<main><header><div><h1>Catch the fly</h1><div class="subtitle-slot"><p id="subtitle">Loading the mapped circuit…</p><div id="circuit-badge" hidden><span id="circuit-label"></span><button id="restore-wiring">Restore</button></div></div></div><nav aria-label="Main"><a href="./" aria-current="page">Play</a><button data-wiring>Wiring lab</button><a href="./how-it-works.html">How it works</a><a href="https://github.com/Alpi157/internet-vs-one-fly">Code and data ↗</a></nav><button class="icon phone-help" data-how aria-label="How it works">?</button></header>
<div class="play-layout"><section class="game-column" aria-label="Game"><div class="stats"><div><strong id="score">0</strong><span>caught</span></div><div class="hand-count"><div id="pips" aria-hidden="true"></div><span id="strikes"></span></div></div><div class="field-wrap"><canvas id="table" tabindex="0" role="img" aria-label="Fly arena. Arrow keys aim. Hold Space and release to strike. Enter strikes at the reticle."></canvas><div id="intro"><button id="start" class="primary" disabled>Loading the fly…</button><small>No account. No tracking.</small></div><div id="landing" class="status-pill" hidden></div><div id="impact-label" class="status-pill" hidden></div></div><p id="time" class="sr-only"></p><div class="hint"><p><span class="phone-hint">Tap the fly to slap. Hold for a bigger, slower hand.</span><span class="desktop-hint">Click the fly to slap. Hold the button for a bigger, slower hand. Arrow keys aim. Space works too.</span></p><div id="looming"><span>Looming input</span><label>Size <meter id="loom-size" min="0" max="1" value="0"></meter></label><label>Expansion <meter id="loom-expansion" min="0" max="1" value="0"></meter></label></div></div><div class="game-actions"><button id="replay-last" disabled>Replay last hand</button><button data-wiring>Wiring lab</button></div></section><div id="desktop-brain"><aside id="brain-panel" aria-label="Brain replay"><p id="replay-badge">Live brain</p><h2 id="brain-title">Under the microscope</h2><p id="caption">Every flash is a recorded spike.</p><div id="brain-host"><p role="status">Loading real neuron skeletons…</p></div><canvas id="timeline" width="720" height="190" role="img" aria-label="Recorded hand height, looming cells and giant fiber spikes from 200 milliseconds before impact to hand lands"></canvas><div class="playback"><button id="pause-replay" class="icon" aria-label="Pause replay">${pauseIcon}</button><span>Quarter speed. Every flash is a recorded spike.</span></div><div class="replay-actions"><button id="continue" class="primary">Next hand</button><button id="video" disabled>Save clip</button></div><button class="desktop-wiring" data-wiring>Is it the wiring? Scramble it</button></aside></div></div><p id="notice" role="status"></p><div id="announcer" class="sr-only" aria-live="polite"></div></main>
<dialog id="replay-sheet" aria-label="Last hand replay"><div class="grabber"></div><button class="icon close" data-close aria-label="Close replay">${closeIcon}</button><div id="replay-slot"></div></dialog>
<dialog id="how-sheet" aria-labelledby="how-title"><div class="grabber"></div><button class="icon close" data-close aria-label="Close How it works">${closeIcon}</button><h2 id="how-title">What is real here?</h2><p id="model-counts"></p><p>Measured MaleCNS wiring drives a simplified neural model. Vision uses size and expansion features. Neurons share a uniform LIF model. Takeoff is abstract and follows heading with seeded jitter. Missing signs and turn directions remain explicit.</p><p id="science-status"></p><p id="walking-disclosure" hidden></p><p>No wiring-superiority or human usability result is claimed.</p><div class="links"><a href="./how-it-works.html">How it works: model, findings and data</a><a href="./preregistration.html">Original preregistration</a><a href="https://github.com/Alpi157/internet-vs-one-fly/blob/main/docs/preregistration-v2.1.md">Robustness preregistration</a><a href="https://github.com/Alpi157/internet-vs-one-fly/blob/main/docs/findings-v2f.md">Findings</a><a id="dataset-link">Zenodo dataset</a></div><div class="settings"><label><input type="checkbox" id="reduce">Reduced motion</label><label><input type="checkbox" id="sound" checked>Sound</label><button id="save-log">Save round log</button><button id="card">Save result card</button></div><details><summary>Registered results</summary><div id="finding-copy"></div></details></dialog>
<dialog id="wiring-sheet" aria-labelledby="wiring-title"><div class="grabber"></div><button class="icon close" data-close aria-label="Close Wiring lab">${closeIcon}</button><h2 id="wiring-title">Wiring lab</h2><p>Is it the wiring, or just speed?</p><button id="coupling">Scramble its connections and find out</button><button id="lab">Open lesion lab</button><div id="lab-panel" hidden></div></dialog>
<dialog id="round-sheet" aria-labelledby="round-title"><div class="grabber"></div><h2 id="round-title">Round over</h2><div class="summary-grid"><div><div class="scoreboard"><div><span>The fly</span><strong id="fly-score" class="escaped"></strong></div><span>vs</span><div><span>You</span><strong id="you-score"></strong></div></div><div id="hand-cells"></div><p class="round-legend">Filled: caught · Green ring: escaped · Empty: unused</p></div><div id="share-preview"></div></div><div class="round-actions"><button id="share">Share</button><button id="play-again" class="primary">Play again</button></div><p>Is it the wiring, or just speed?</p><button data-wiring>Scramble its connections and find out →</button></dialog>`;
const $ = (id: string) => document.getElementById(id)!, table = $('table') as HTMLCanvasElement, timeline = $('timeline') as HTMLCanvasElement;
const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' }), manual = new URLSearchParams(location.search).has('test');
let runtime: any, profile: any, display: any, brain: any, buffer: ArrayBuffer, field: MicroscopeField, brainView: BrainView | undefined;
let ready = false, started = false, paused = true, finished = false, replaying = false, replayPaused = false, catches = 0, used = 0, simSpeed = 0;
let frame: Frame = { tick: 0, body: { x: 0, y: 0, heading_x: 1, heading_y: 0 }, air: false, applied: [false, 0, 0], gait: 0, activity_hz: 0, strike: null, impact: null, onset: false, spikes: [] };
const history: Frame[] = [], impacts: any[] = [];
let replay: Frame[] = [], lastImpact: any = null, replayIndex = 0, replayStart = 0, replayPinned: number | null = null;
let aim = { x: 0, y: 0 }, reticle = false, holdStart: number | null = null, reduced = matchMedia('(prefers-reduced-motion: reduce)').matches, audio: AudioContext | null = null;
let couplingOpen = false, requestId = 0;
let autoStart = false;
const pending = new Map<number, (v: any) => void>();
let drawnTick = -1, drawnReplay = false;
window.addEventListener('resize', () => { drawnTick = -1; });
const send = (kind: string, extra: any = {}) => worker.postMessage({ kind, ...extra });
const request = (kind: string, extra: any = {}) => new Promise<any>(resolve => { const id = ++requestId; pending.set(id, resolve); send(kind, { ...extra, id }); });
function tone(caught: boolean) { if (!($('sound') as HTMLInputElement).checked)
    return; audio ??= new AudioContext(); void audio.resume(); const o = audio.createOscillator(), g = audio.createGain(); o.type = 'triangle'; o.frequency.setValueAtTime(caught ? 160 : 320, audio.currentTime); o.frequency.exponentialRampToValueAtTime(caught ? 60 : 750, audio.currentTime + .14); g.gain.setValueAtTime(.05, audio.currentTime); g.gain.exponentialRampToValueAtTime(.001, audio.currentTime + .2); o.connect(g).connect(audio.destination); o.start(); o.stop(audio.currentTime + .21); }
($('reduce') as HTMLInputElement).checked = reduced;
$('reduce').onchange = () => { reduced = ($('reduce') as HTMLInputElement).checked; drawnTick = -1; };
const media = matchMedia('(prefers-reduced-motion: reduce)');
media.onchange = e => { reduced = e.matches; ($('reduce') as HTMLInputElement).checked = reduced; drawnTick = -1; };
let returnFocus: HTMLElement | null = null;
let modalWasRunning = false;
function openSheet(id: string) { const d = $(id) as HTMLDialogElement; returnFocus = document.activeElement as HTMLElement; modalWasRunning = started && !paused && !finished; send('pause'); holdStart = null; d.showModal(); }
function closeSheet(d: HTMLDialogElement) { d.close(); if (d.id === 'replay-sheet')
    continueGame();
else if (modalWasRunning)
    send('resume'); returnFocus?.focus(); }
for (const d of Array.from(document.querySelectorAll<HTMLDialogElement>('dialog'))) {
    d.addEventListener('cancel', e => { if (d.id === 'round-sheet') {
        e.preventDefault();
        return;
    } e.preventDefault(); closeSheet(d); });
    d.querySelector<HTMLButtonElement>('[data-close]')?.addEventListener('click', () => closeSheet(d));
    d.addEventListener('keydown', e => { if (e.key !== 'Tab')
        return; const nodes = Array.from(d.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input,select,summary,[tabindex="0"]')).filter(n => n.getClientRects().length); const first = nodes[0], last = nodes.at(-1); if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
    }
    else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
    } });
}
document.querySelectorAll<HTMLElement>('[data-how]').forEach(b => b.onclick = () => openSheet('how-sheet'));
document.querySelectorAll<HTMLElement>('[data-wiring]').forEach(b => b.onclick = () => openSheet('wiring-sheet'));
function updateStats() {
    if (!profile) return;
    const activeStrike = frame.strike && frame.tick < frame.strike.impact_tick + profile.replay_post_ms * 2;
    const hand = Math.max(1, Math.min(used + (activeStrike || replaying || finished ? 0 : 1), profile.max_strikes));
    $('score').textContent = String(catches);
    $('strikes').textContent = `Hand ${hand} of ${profile.max_strikes}`;
    $('pips').innerHTML = Array.from({length:profile.max_strikes},(_,i)=>`<i class="pip ${impacts[i]?(impacts[i].caught?'caught':'escaped'):i===hand-1?'current':''}"></i>`).join('');
    $('time').textContent = `${Math.max(0,(profile.round_ms-frame.tick*.5)/1000).toFixed(1)} seconds remaining`;
}

function sentence(impact: any) { if (!impact)
    return 'Every flash is a recorded spike.'; return (impact.lead_ms === null ? 'Its giant fiber did not fire before your hand landed.' : `Its giant fiber fired ${impact.lead_ms} ms before your hand landed.`) + (impact.escape_onset_lead_ms === null ? '' : ` Takeoff began ${impact.escape_onset_lead_ms} ms before impact.`); }
function beginReplay() {
    if (!replay.length)
        return;
    replaying = true;
    paused = true;
    replayPaused = false;
    replayPinned = null;
    replayIndex = 0;
    replayStart = performance.now();
    send('pause');
    $('brain-title').textContent = lastImpact.caught ? 'Caught' : 'Escaped';
    $('brain-title').classList.toggle('escaped', !lastImpact.caught);
    $('replay-badge').textContent = `Hand ${used} of ${profile.max_strikes}`;
    $('caption').textContent = sentence(lastImpact);
    $('brain-panel').classList.add('active');
    $('continue').textContent = finished ? 'Round summary' : 'Next hand';
    ($('video') as HTMLButtonElement).disabled = !('MediaRecorder' in window) || !('captureStream' in table);
    ($('replay-last') as HTMLButtonElement).disabled = false;
    $('pause-replay').innerHTML = pauseIcon;
    $('pause-replay').setAttribute('aria-label', 'Pause replay');
    if (innerWidth < 900) {
        $('replay-slot').append($('brain-panel'));
        openSheet('replay-sheet');
    }
    updateStats();
}
function continueGame() { if (($('replay-sheet') as HTMLDialogElement).open)
    ($('replay-sheet') as HTMLDialogElement).close(); $('desktop-brain').append($('brain-panel')); replaying = false; replayPinned = null; drawnTick = -1; $('brain-panel').classList.remove('active'); if (finished) {
    showRound();
    return;
} paused = false; $('brain-title').textContent = 'Under the microscope'; $('brain-title').classList.remove('escaped'); $('replay-badge').textContent = 'Live brain'; $('caption').textContent = 'Every flash is a recorded spike.'; send('resume'); updateStats(); table.focus(); }
$('continue').onclick = continueGame;
$('replay-last').onclick = beginReplay;
$('pause-replay').onclick = () => { replayPaused = !replayPaused; if (!replayPaused) {
    replayPinned = null;
    replayStart = performance.now() - replayIndex * 40;
} $('pause-replay').innerHTML = replayPaused ? playIcon : pauseIcon; $('pause-replay').setAttribute('aria-label', replayPaused ? 'Play replay' : 'Pause replay'); };
function drawTimeline(f: Frame, frames = replay, impact = lastImpact, output = timeline) {
    const c = output.getContext('2d')!;
    c.fillStyle = '#0a0c0a';
    c.fillRect(0, 0, 720, 190);
    if (!impact || !brain)
        return;
    const first = impact.tick - profile.replay_pre_ms * 2, last = impact.tick, data = frames.filter(f => f.tick >= first && f.tick <= last), x = (t: number) => 180 + (t - first) / (last - first) * 515;
    const groups = new Map<number, string>(brain.nodes.map((n: any) => [n.index, n.group]));
    const population = brain.nodes.filter((n: any) => ['LC4', 'LPLC2'].includes(n.group)).length;
    const rates = data.map(v => v.spikes.reduce((n, e) => n + e.indices.filter(i => ['LC4', 'LPLC2'].includes(groups.get(i)!)).length, 0) / population / .01), maxRate = Math.max(1, ...rates);
    c.font = '24px Atkinson';
    for (let row = 0; row < 3; row++) {
        const y = 33 + row * 49;
        c.fillStyle = '#9ba59c';
        c.fillText(['Hand height', 'Looming cells', 'Giant fiber'][row], 0, y);
        c.strokeStyle = '#262b27';
        c.beginPath();
        c.moveTo(180, y + 8);
        c.lineTo(695, y + 8);
        c.stroke();
        c.strokeStyle = row === 0 ? '#c9d0c8' : '#63f29a';
        c.lineWidth = 2;
        c.beginPath();
        data.forEach((v, i) => { let value = 0; if (row === 0)
            value = v.strike ? Math.max(0, (v.strike.impact_tick - v.tick) / (v.strike.impact_tick - v.strike.start_tick)) : 0; if (row === 1)
            value = rates[i] / maxRate; if (row < 2) {
            const yy = y + 8 - value * 30;
            if (i === 0)
                c.moveTo(x(v.tick), yy);
            else {
                c.lineTo(x(v.tick), y + 8 - (row === 1 ? rates[i - 1] / maxRate : data[i - 1].strike ? Math.max(0, (data[i - 1].strike.impact_tick - data[i - 1].tick) / (data[i - 1].strike.impact_tick - data[i - 1].strike.start_tick)) : 0) * 30);
                c.lineTo(x(v.tick), yy);
            }
        }
        else
            for (const e of v.spikes)
                if (e.indices.some(i => groups.get(i) === 'giant fiber')) {
                    c.moveTo(x(e.tick), y + 8);
                    c.lineTo(x(e.tick), y - 22);
                } });
        c.stroke();
    }
    c.strokeStyle = '#e9ede6';
    c.setLineDash([4, 4]);
    c.beginPath();
    c.moveTo(x(last), 5);
    c.lineTo(x(last), 148);
    c.stroke();
    c.setLineDash([]);
    c.strokeStyle = '#7fefaa';
    c.beginPath();
    c.moveTo(x(Math.max(first, Math.min(last, f.tick))), 5);
    c.lineTo(x(Math.max(first, Math.min(last, f.tick))), 148);
    c.stroke();
    c.fillStyle = '#c9d0c8';
    c.fillText(`−${profile.replay_pre_ms} ms`, 180, 179);
    c.textAlign = 'right';
    c.fillText('hand lands', 695, 179);
    c.textAlign = 'left';
}
let loopReplay = false;
let paintCount = 0;
function animate(now: number) {
    if (!couplingOpen && field) {
        let shown = frame;
        if (replaying && replay.length) {
            if (!replayPaused)
                replayIndex = replayPinned ?? Math.max(0, loopReplay ? Math.floor((now - replayStart) / 40) % replay.length : Math.min(replay.length - 1, Math.floor((now - replayStart) / 40)));
            shown = replay[replayIndex];
        }
        if (shown.tick !== drawnTick || replaying !== drawnReplay || holdStart !== null) {
            field.draw(shown, { reduced, frames: replaying ? replay : history, aim, reticle, holdMs: holdStart === null ? null : now - holdStart, lastImpact });
            drawTimeline(shown);
            drawnTick = shown.tick;
            drawnReplay = replaying;
            paintCount++;
            const s = shown.strike;
            $('landing').hidden = !(s && shown.tick < s.impact_tick);
            if (s)
                $('landing').textContent = `Hand lands in ${Math.max(0, (s.impact_tick - shown.tick) * .5)} ms`;
            const impact = shown.impact || (lastImpact && shown.tick >= lastImpact.tick && shown.tick <= lastImpact.tick + profile.replay_post_ms * 2 ? lastImpact : null);
            $('impact-label').hidden = !impact;
            if (impact) {
                $('impact-label').textContent = impact.caught ? 'Caught' : 'Escaped';
                $('impact-label').classList.toggle('escaped', !impact.caught);
            }
        }
        if (innerWidth >= 900 || replaying)
            brainView?.draw(shown, replaying ? replay : history, !replaying);
    }
    requestAnimationFrame(animate);
}
worker.onmessage = event => { const m = event.data; if (m.kind === 'ready') {
    ready = true;
    ($('start') as HTMLButtonElement).disabled = false;
    $('start').textContent = 'Play';
    if(autoStart){autoStart=false;start();}
} if (m.kind === 'error') {
    $('notice').textContent = m.error;
    throw new Error(m.error);
} if (m.kind === 'frame') {
    frame = m.frame;
    history.push(frame);
    if (history.length > profile.recording_max_intervals)
        history.shift();
    catches = m.catches;
    used = m.strikes;
    finished = m.done;
    simSpeed = m.simulation_wall_s_per_sim_s;
    ($('loom-size') as HTMLMeterElement).value = m.looming.size_feature ?? 0;
    ($('loom-expansion') as HTMLMeterElement).value = m.looming.expansion_feature ?? 0;
    if (frame.impact) {
        lastImpact = frame.impact;
        impacts.push(lastImpact);
        tone(lastImpact.caught);
        $('announcer').textContent = `${lastImpact.caught ? 'Caught' : 'Escaped'}. Hand ${used} of ${profile.max_strikes}.`;
        if (!reduced) {
            navigator.vibrate?.(lastImpact.caught ? [30, 20, 40] : 15);
            table.classList.remove('shake');
            void table.offsetWidth;
            table.classList.add('shake');
        }
    }
    updateStats();
    if (finished && !frame.strike) {
        paused = true;
        showRound();
    }
} if (m.kind === 'replay') {
    replay = m.frames;
    lastImpact = m.impact;
    finished = m.done;
    beginReplay();
} if (m.kind === 'advanced' || m.kind === 'log') {
    pending.get(m.id)?.(m.log ?? m);
    pending.delete(m.id);
} };
function start() { if (!ready)
    return; started = true; paused = false; $('intro').hidden = true; send('start'); table.focus(); }
$('start').onclick = start;
const canStrike = () => started && !paused && !finished && (!frame.strike || frame.tick >= frame.strike.impact_tick + profile.replay_post_ms * 2);
function strike(hold_ms: number) { send('strike', { ...aim, hold_ms }); holdStart = null; drawnTick = -1; }
table.onpointerdown = e => { if (!canStrike())
    return; table.focus(); table.setPointerCapture(e.pointerId); aim = field.aim(e.clientX, e.clientY); reticle = false; holdStart = performance.now(); };
table.onpointermove = e => { if (holdStart !== null)
    aim = field.aim(e.clientX, e.clientY); };
table.onpointercancel = () => { holdStart = null; drawnTick = -1; };
table.onpointerup = e => { if (holdStart === null)
    return; aim = field.aim(e.clientX, e.clientY); strike(performance.now() - holdStart); };
table.onkeydown = e => { if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space', 'Enter'].includes(e.code))
    e.preventDefault(); if (!canStrike())
    return; reticle = true; if (e.code.startsWith('Arrow')) {
    const step = profile.arena_radius / 20;
    aim = field.clamp({ x: aim.x + (e.code === 'ArrowRight' ? step : e.code === 'ArrowLeft' ? -step : 0), y: aim.y + (e.code === 'ArrowUp' ? step : e.code === 'ArrowDown' ? -step : 0) });
    drawnTick = -1;
} if (e.code === 'Space' && !e.repeat && holdStart === null)
    holdStart = performance.now(); if (e.code === 'Enter' && !e.repeat)
    strike((profile.hold_thresholds_ms[0] + profile.hold_thresholds_ms[1]) / 2); };
table.onkeyup = e => { if (e.code === 'Space') {
    e.preventDefault();
    if (holdStart !== null)
        strike(performance.now() - holdStart);
} };
table.onblur = () => { holdStart = null; };
const couplingHost = document.createElement('div');
couplingHost.id = 'coupling-host';
couplingHost.hidden = true;
document.body.append(couplingHost);
async function selectCircuit(mode:string){
    const {configureLab}=await import('./lab.ts');const selected=await configureLab(mode,buffer,runtime,base);
    for(const d of Array.from(document.querySelectorAll<HTMLDialogElement>('dialog[open]')))d.close();
    reset();autoStart=true;
    send('init',{buffer:selected.buffer,runtime:selected.runtime,profile,neuralSeed:2026092802,environmentSeed:8128,manual});
    $('circuit-badge').hidden=mode==='real';$('subtitle').hidden=mode!=='real';
    const names:Record<string,string>={'LC4':'LC4','LPLC2':'LPLC2','giant-fiber':'Giant fiber','turning-DN':'Turning DN'};
    $('circuit-label').textContent=mode==='scramble'?`Uncalibrated full shuffle, seed ${runtime.lab_seed}`:`${names[mode]??'Measured wiring'}${mode==='real'?'':' silenced'}`;
    $('notice').textContent='Fresh round. Neural state explicitly reset.';
}
$('restore-wiring').onclick=()=>void selectCircuit('real');
async function showLab(){
    for(const dialog of Array.from(document.querySelectorAll<HTMLDialogElement>('dialog[open]')))dialog.close();
    send('pause');couplingOpen=true;app.hidden=true;window.scrollTo(0,0);
    const {openCoupling}=await import('./coupling.ts');
    await openCoupling(couplingHost,base,()=>{couplingOpen=false;app.hidden=false;drawnTick=-1;window.scrollTo(0,0);if(finished)showRound();else if(started&&!paused)send('resume');},selectCircuit);
}
$('coupling').onclick=showLab;
$('lab').onclick=showLab;
document.querySelectorAll<HTMLElement>('[data-wiring]').forEach(b=>b.onclick=showLab);
function reset() { $('desktop-brain').append($('brain-panel'));$('brain-panel').classList.remove('active');$('brain-title').textContent='Under the microscope';$('brain-title').classList.remove('escaped');$('replay-badge').textContent='Live brain';$('caption').textContent='Every flash is a recorded spike.'; started = false; paused = true; replaying = false; finished = false; ready = false; history.length = 0; impacts.length = 0; replay = []; lastImpact = null; used = 0; catches = 0; frame = { ...frame, tick: 0, body: { x: 0, y: 0, heading_x: 1, heading_y: 0 }, strike: null, impact: null, spikes: [], air: false, gait: 0 }; $('intro').hidden = false; drawnTick = -1; ($('replay-last') as HTMLButtonElement).disabled = true; updateStats(); }
function save(blob: Blob, name: string) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 10000); }
function wrap(c: CanvasRenderingContext2D, text: string, x: number, y: number, width: number, lineHeight: number) { let line = ''; for (const word of text.split(' ')) {
    if (c.measureText(line + word).width > width) {
        c.fillText(line, x, y);
        line = '';
        y += lineHeight;
    }
    line += word + ' ';
} c.fillText(line, x, y); }
function bestEscape() { return impacts.filter(i => !i.caught && i.lead_ms !== null).sort((a, b) => b.lead_ms - a.lead_ms)[0]; }
function number(c: CanvasRenderingContext2D, text: string, x: number, y: number, size: number) { c.font = `900 ${size}px Doto`; const parts = text.split('.'); c.fillText(parts[0], x, y); if (parts[1]) {
    x += c.measureText(parts[0]).width + size * .08;
    c.beginPath(); c.roundRect(x, y - size * .22, size * .16, size * .16, size * .056); c.fill();
    c.fillText(parts[1], x + size * .26, y);
} }
function shareCard() { const canvas = document.createElement('canvas'); canvas.width = 1200; canvas.height = 630; const c = canvas.getContext('2d')!; c.fillStyle = '#0a0c0a'; c.fillRect(0, 0, 1200, 630); c.fillStyle = '#e9ede6'; c.font = '900 38px Doto'; c.fillText('Catch the fly', 38, 62); const best = bestEscape(); const still = best ?? lastImpact; if (still && brainView?.ready) {
    const observed = history.filter(f => f.tick <= still.tick), f = observed.at(-1)!;
    c.drawImage(brainView.snapshotAt(f, observed), 24, 110, 600, 354);
    drawnTick = -1;
} c.fillStyle = best ? '#63f29a' : '#e9ede6'; number(c, best ? String(best.lead_ms) : String(catches), 650, 240, 100); c.font = '700 25px Atkinson'; c.fillText(best ? 'ms' : 'caught', 650, 290); c.fillStyle = '#e9ede6'; c.font = '400 30px Atkinson'; wrap(c, best ? `A simulated fruit fly brain beat my hand by ${best.lead_ms} ms.` : `I caught the simulated fly ${catches} ${catches===1?'time':'times'} in ${used} ${used===1?'hand':'hands'}.`, 650, 355, 510, 40); c.fillStyle = '#c9d0c8'; c.font = '400 24px Atkinson'; c.fillText(shareURL, 38, 580); c.font='400 18px Atkinson'; c.fillText(`Game profile v2.${profile.version}`,38,610); return canvas; }
const exportTable = document.createElement('canvas'), exportTimeline = document.createElement('canvas');
exportTimeline.width = 720; exportTimeline.height = 190;
function composite(portrait = false, recorded?: {frame: Frame, frames: Frame[], impact: any}) {
    if (!portrait) return shareCard();
    const canvas=document.createElement('canvas'); canvas.width=720; canvas.height=1280;
    const c=canvas.getContext('2d')!; c.fillStyle='#000'; c.fillRect(0,0,720,1280);
    c.fillStyle='#e9ede6'; c.font='900 36px Doto'; c.fillText('Catch the fly',24,46);
    if (recorded) {
        field.draw(recorded.frame,{reduced,frames:recorded.frames,aim:{x:0,y:0},reticle:false,holdMs:null,lastImpact:recorded.impact},exportTable);
        drawTimeline(recorded.frame,recorded.frames,recorded.impact,exportTimeline);
    }
    c.drawImage(recorded?exportTable:table,60,65,600,600);
    if (brainView?.ready) {
        const snapshot=recorded?brainView.snapshotAt(recorded.frame,recorded.frames):brainView.snapshot();
        const scale=Math.min(680/snapshot.width,400/snapshot.height);
        c.drawImage(snapshot,360-snapshot.width*scale/2,680,snapshot.width*scale,snapshot.height*scale);
    }
    if(recorded) {
        const f=recorded.frame,s=f.strike,impact=recorded.impact;
        const text=s&&f.tick<s.impact_tick?`Hand lands in ${(s.impact_tick-f.tick)*.5} ms`:f.tick>=impact.tick?(impact.caught?'Caught':'Escaped'):'';
        if(text){c.font='700 20px Atkinson';const w=c.measureText(text).width+32;c.fillStyle='#0b0d0bd1';c.beginPath();c.roundRect(360-w/2,90,w,40,20);c.fill();c.textAlign='center';c.fillStyle=text==='Escaped'?'#63f29a':'#e9ede6';c.fillText(text,360,117);c.textAlign='left';}
    }
    c.drawImage(recorded?exportTimeline:timeline,20,1085,680,179);c.fillStyle='#c9d0c8';c.font='16px Atkinson';c.fillText(shareURL,20,1270);return canvas;
}

function showRound() { send('pause'); replaying = false; paused = true; $('fly-score').textContent = String(impacts.length - catches); $('you-score').textContent = String(catches); $('hand-cells').innerHTML = Array.from({ length: profile.max_strikes }, (_, i) => `<div><span class="pip ${impacts[i] ? (impacts[i].caught ? 'caught' : 'escaped') : ''}" aria-hidden="true"></span><span>${i + 1}</span><span class="sr-only">${impacts[i] ? (impacts[i].caught ? 'Caught' : 'Escaped') : 'Unused'}</span></div>`).join(''); const card = shareCard(); card.setAttribute('role', 'img'); card.setAttribute('aria-label', `Game profile v2.${profile.version}. ` + (bestEscape() ? `A simulated fruit fly brain beat my hand by ${bestEscape().lead_ms} ms.` : `${catches} caught in ${used} hands`)); $('share-preview').replaceChildren(card); if (!($('round-sheet') as HTMLDialogElement).open)
    openSheet('round-sheet'); }
$('share').onclick = () => shareCard().toBlob(async (blob) => { if (!blob)
    return; const file = new File([blob], 'catch-the-fly.png', { type: 'image/png' }); if (navigator.canShare?.({ files: [file] })) {
    try {
        await navigator.share({ files: [file], title: 'Catch the fly' });
        return;
    }
    catch (e) {
        if ((e as Error).name === 'AbortError')
            return;
    }
} save(blob, 'catch-the-fly.png'); });
$('play-again').onclick = () => location.reload();
$('card').onclick = () => composite().toBlob(blob => { if (blob)
    save(blob, 'catch-the-fly.png'); });
$('save-log').onclick = async () => save(new Blob([JSON.stringify(await request('log'), null, 2)], { type: 'application/json' }), 'flybench-round.json');
$('video').onclick = async () => {
    if (!replay.length || !('MediaRecorder' in window)) return;
    const mime=['video/webm;codecs=vp9','video/webm','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
    if (!mime) { $('notice').textContent='Video export unavailable. Save a result card instead.'; return; }
    // Capture an immutable sequence. Closing the sheet or playing another hand
    // cannot replace a recorded frame with live activity in the exported clip.
    const recorded=replay.slice(),impact=structuredClone(lastImpact);
    let index=0;
    const canvas=composite(true,{frame:recorded[0],frames:recorded,impact}),c=canvas.getContext('2d')!;
    const stream=canvas.captureStream(25),recorder=new MediaRecorder(stream,{mimeType:mime}),chunks:Blob[]=[];
    recorder.ondataavailable=e=>chunks.push(e.data);
    recorder.onstop=()=>{save(new Blob(chunks,{type:mime}),mime.includes('mp4')?'fly-replay.mp4':'fly-replay.webm');stream.getTracks().forEach(t=>t.stop());};
    recorder.start();
    const timer=setInterval(()=>{index++;if(index>=recorded.length){clearInterval(timer);recorder.stop();return;}c.drawImage(composite(true,{frame:recorded[index],frames:recorded,impact}),0,0);},10/profile.replay_speed);
};

(async () => {
    try {
        [runtime, profile, display, brain, buffer] = await Promise.all([fetch(base + 'data/runtime.json').then(r => r.json()), fetch(base + 'data/game.json').then(r => r.json()), fetch(base + 'data/display-v1.json').then(r => r.json()), fetch(base + 'data/brain.json').then(r => r.json()), fetchGraph(base + 'data/circuit.flygraph.gz')]);
        if(import.meta.env.DEV){const {activateOwnerPreview}=await import('./owner-preview.ts');({profile,runtime}=await activateOwnerPreview(profile,runtime,(neuralSeed,environmentSeed)=>{reset();send('init',{buffer,runtime,profile,neuralSeed,environmentSeed,manual:true});}));}
        await document.fonts.ready;
        field = new MicroscopeField(table, profile, display, base, () => { drawnTick = -1; });
        $('subtitle').textContent = `${runtime.counts.N.toLocaleString('en-US')} neurons, wired as mapped in a real male fruit fly.`;
        $('model-counts').textContent = `Executed scope: ${runtime.counts.N.toLocaleString('en-US')} neurons, ${runtime.counts.source_accepted_E.toLocaleString('en-US')} connections, ${runtime.counts.represented_source_contacts.toLocaleString('en-US')} biological contacts. ${runtime.counts.zero_disabled_E.toLocaleString('en-US')} connections have disabled unknown signs.`;
        $('science-status').textContent = `This model passed the calibration registered in ${runtime.protocol_tag}. Connection strength ${runtime.parameters.s}. Escape and walking comparisons remain insufficient.`;
        if(profile.walking_drive?.selected){$('walking-disclosure').textContent=profile.walking_drive.copy.game;$('walking-disclosure').hidden=false;}
        updateStats();
        const random = crypto.getRandomValues(new Uint32Array(2));
        send('init', { buffer, runtime, profile, neuralSeed: manual ? 2026092802 : random[0], environmentSeed: manual ? 8128 : random[1], manual });
        requestAnimationFrame(() => requestAnimationFrame(async () => { const module = await import('./brain-view.ts'); brainView = new module.BrainView($('brain-host'), base, brain.nodes, display); const results=await loadResults(base);renderResults($('finding-copy'), results);($('dataset-link') as HTMLAnchorElement).href='https://doi.org/'+results.dataset_doi; if(new URLSearchParams(location.search).has('lab'))void showLab(); }));
    }
    catch (e) {
        $('notice').textContent = 'Local model data could not load: ' + String(e);
        throw e;
    }
})();
requestAnimationFrame(animate);
if (manual)
    (window as any).flyTest = { ready: () => ready, start, resetSeed: (neuralSeed:number) => { reset(); send('init', {buffer,runtime,profile,neuralSeed,environmentSeed:8128,manual:true}); }, brainSnapshot: () => brainView?.snapshot().toDataURL(), arenaBounds: () => { const r=table.getBoundingClientRect(), radius=r.width*field.arenaPixels/700;return {x:r.x+r.width/2-radius,y:r.y+r.height/2-radius,right:r.x+r.width/2+radius,bottom:r.y+r.height/2+radius}; }, startLive: () => { reset(); send('init', { buffer, runtime, profile, neuralSeed: 2026092802, environmentSeed: 8128, manual: false }); }, advance: (intervals: number) => request('advance', { intervals }), strike: (x: number, y: number, hold_ms: number) => send('strike', { x, y, hold_ms }), resume: continueGame, log: () => request('log'), state: () => ({ frame, replayTick: replay[replayIndex]?.tick, catches, used, finished, replaying, simSpeed, paintCount, reduced, anatomyReady: brainView?.ready, anatomyLoadMs: brainView?.loadMs, lod: brainView?.lod, renderer: brainView?.renderer }), measureReplay: (enabled: boolean) => { loopReplay = enabled; replayPaused = false; replayPinned = null; replayStart = performance.now(); }, showReplay: beginReplay, showRecorded: (kind: string) => { const index = kind === 'takeoff' ? replay.findIndex(f => f.air) : replay.reduce((best, f, i) => f.spikes.reduce((n, e) => n + e.indices.length, 0) > (replay[best]?.spikes.reduce((n, e) => n + e.indices.length, 0) ?? -1) ? i : best, 0); if (index < 0)
            return false; replayPinned = index; replayIndex = index; replayPaused = true; drawnTick = -1; return true; } };
