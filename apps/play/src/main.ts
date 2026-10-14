import './style.css';
import type { Frame } from './game.ts';
const app = document.querySelector<HTMLDivElement>('#app')!;
app.innerHTML = `<main><header><a class="brand" href="/">FLYBENCH <span>FIELD NOTES / 002</span></a><span class="model-tag">provisional model</span></header>
<section class="title"><div><p class="eyebrow">MEET YOUR VERY SMALL OPPONENT</p><h1>Catch the <i>Fly.</i></h1></div><p>A tiny brain.<br>A big attitude.</p></section>
<div class="status"><span id="time">30.0 <small>SECONDS</small></span><span id="score">0 <small>CAUGHT</small></span><span id="strikes">6 <small>STRIKES LEFT</small></span></div>
<section class="play-layout"><div class="table-wrap"><canvas id="table" width="700" height="700" tabindex="0" aria-label="Fly arena. Hold to charge, release to strike. Enter strikes the center."></canvas><div id="intro"><span class="stamp">WANTED<br>ALIVE & BUZZING</span><h2>Six chances.<br>One little show-off.</h2><p>Tap for a flick. Hold for a slap.<br>Hold longer for a mighty swat.</p><button id="start" disabled>Waking the fly…</button><small>No account. No tracking. Just you and a fly.</small></div><div id="impact-label" aria-live="polite"></div><span class="table-note">SPECIMEN 01 / HANDLE WITH CURIOSITY</span></div>
<aside id="brain-panel"><div class="panel-top"><span class="eyebrow">BRAIN-CAM</span><b id="replay-badge">WAITING FOR YOUR MOVE</b></div><h2 id="brain-title">A look inside<br>the little troublemaker.</h2><canvas id="brain" width="560" height="420" aria-label="Recorded neuron activity map"></canvas><p id="caption">After each strike, watch the recorded neurons flash at quarter speed.</p><div class="legend"><span style="--dot:#0072b2">LC4</span><span style="--dot:#e69f00">LPLC2</span><span style="--dot:#cc79a7">Giant fiber</span><span style="--dot:#009e73">Walking DNs</span><span style="--dot:#74808b">Interior</span></div><small id="map-note">Relative soma positions. Missing coordinates appear in the side band.</small><div class="replay-actions" hidden><button id="again">Replay 0.25×</button><button id="continue">Next strike →</button></div></aside></section>
<div class="instruction"><strong id="charge-text">TAP: FLICK · HOLD: SLAP · LONG HOLD: SWAT</strong><span>The growing hand shadow is the looming stimulus the fly sees.</span></div>
<section class="bottom"><details><summary>What is real here? <span>+</span></summary><p id="model-counts"></p><p>Measured MaleCNS wiring drives a simplified neural model. Vision uses size and expansion features. Neurons share a uniform LIF model. Takeoff is abstract and follows heading with seeded jitter. Missing signs and turn directions remain explicit.</p><p>No calibrated model or wiring-superiority result is claimed. The science track stopped before pre-registration.</p><a href="/model.html">Model card</a> · <a href="/preregistration.html">Pre-registration status</a> · <a href="https://male-cns.janelia.org/download/">MaleCNS v1.0, CC-BY</a></details><div class="settings"><label><input id="reduce" type="checkbox"> Reduced motion</label><label><input id="sound" type="checkbox" checked> Sound</label><button id="save-log">Save round log</button><button id="card">Save result card</button><button id="video" disabled>Save replay video</button></div></section><p id="notice" role="status"></p><footer>A real wiring diagram. An imaginary fly. A very personal rivalry.</footer></main>`;
const $ = (id: string) => document.getElementById(id)!;
const table = $('table') as HTMLCanvasElement, brainCanvas = $('brain') as HTMLCanvasElement;
const ctx = table.getContext('2d')!, bc = brainCanvas.getContext('2d')!;
const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
let runtime: any, profile: any, brain: any, buffer: ArrayBuffer;
let frame: Frame = { tick: 0, body: { x: 0, y: 0, heading_x: 1, heading_y: 0 }, air: false, strike: null, impact: null, onset: false, spikes: [] };
let ready = false, started = false, replaying = false, paused = false, finished = false, catches = 0, used = 0;
let replay: Frame[] = [], lastImpact: any = null, replayIndex = 0, replayStart = 0;
let aim = { x: 0, y: 0 }, holdStart: number | null = null, reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
let sound: AudioContext | null = null, lastSoundTick = -1, frames = 0, rafStart = performance.now(), simSpeed = 0;
const manual = new URLSearchParams(location.search).has('test');
const pending = new Map<number, (value: any) => void>();
let requestId = 0;
($('reduce') as HTMLInputElement).checked = reduced;
$('reduce').onchange = () => reduced = ($('reduce') as HTMLInputElement).checked;
function tone(caught: boolean) {
    if (!($('sound') as HTMLInputElement).checked)
        return;
    sound ??= new AudioContext();
    void sound.resume();
    const o = sound.createOscillator(), g = sound.createGain();
    o.type = caught ? 'triangle' : 'sawtooth';
    o.frequency.setValueAtTime(caught ? 160 : 320, sound.currentTime);
    o.frequency.exponentialRampToValueAtTime(caught ? 60 : 750, sound.currentTime + .14);
    g.gain.setValueAtTime(.05, sound.currentTime);
    g.gain.exponentialRampToValueAtTime(.001, sound.currentTime + .2);
    o.connect(g).connect(sound.destination);
    o.start();
    o.stop(sound.currentTime + .21);
}
function send(kind: string, extra: any = {}) { worker.postMessage({ kind, ...extra }); }
function request(kind: string, extra: any = {}) { const id = ++requestId; return new Promise<any>(resolve => { pending.set(id, resolve); send(kind, { ...extra, id }); }); }
function world(x: number, y: number) { const scale = 700 / (profile?.arena_half_size * 2 || 12); return [350 + x * scale, 350 - y * scale]; }
function fly(c: CanvasRenderingContext2D, f: Frame) {
    const [x, y] = world(f.body.x, f.body.y);
    c.save();
    c.translate(x, y);
    c.rotate(-Math.atan2(f.body.heading_y, f.body.heading_x));
    if (f.air && !reduced) {
        c.strokeStyle = '#fff9df';
        c.lineWidth = 5;
        for (let i = 0; i < 3; i++) {
            c.beginPath();
            c.moveTo(-28 - i * 15, -7 + i * 6);
            c.lineTo(-58 - i * 15, -7 + i * 6);
            c.stroke();
        }
    }
    c.fillStyle = '#23352e22';
    c.beginPath();
    c.ellipse(4, 7, 22, 10, 0, 0, Math.PI * 2);
    c.fill();
    c.strokeStyle = '#253f35';
    c.lineWidth = 2.3;
    for (const sign of [-1, 1])
        for (let i = 0; i < 3; i++) {
            c.beginPath();
            c.moveTo(-8 + i * 9, sign * 6);
            c.lineTo(-18 + i * 12, sign * (18 + (i % 2) * 3));
            c.lineTo(-12 + i * 12, sign * 23);
            c.stroke();
        }
    c.fillStyle = '#fffdf2cc';
    c.strokeStyle = '#76948b';
    c.lineWidth = 1.5;
    for (const sign of [-1, 1]) {
        c.beginPath();
        c.ellipse(-8, sign * 14, 22, 10, sign * .45, 0, Math.PI * 2);
        c.fill();
        c.stroke();
    }
    c.fillStyle = '#24483c';
    c.beginPath();
    c.ellipse(-5, 0, 18, 10, 0, 0, Math.PI * 2);
    c.fill();
    c.strokeStyle = '#82ad8c';
    c.lineWidth = 2;
    c.beginPath();
    c.moveTo(-12, -8);
    c.lineTo(-12, 8);
    c.stroke();
    c.fillStyle = '#18372c';
    c.beginPath();
    c.ellipse(12, 0, 12, 11, 0, 0, Math.PI * 2);
    c.fill();
    for (const sign of [-1, 1]) {
        c.fillStyle = '#f0ad56';
        c.beginPath();
        c.ellipse(18, sign * 6, 6, 5, 0, 0, Math.PI * 2);
        c.fill();
        c.fillStyle = '#fff9e6';
        c.beginPath();
        c.arc(20, sign * 6 - 1, 2, 0, Math.PI * 2);
        c.fill();
    }
    c.restore();
}
function drawTable(f: Frame, c = ctx) {
    c.fillStyle = '#debb81';
    c.fillRect(0, 0, 700, 700);
    for (let y = 0; y < 700; y += 140) {
        c.fillStyle = y % 280 ? '#e4c38c' : '#dfba7d';
        c.fillRect(0, y, 700, 140);
        c.strokeStyle = '#aa814327';
        c.lineWidth = 2;
        c.beginPath();
        c.moveTo(0, y + 138);
        c.lineTo(700, y + 138);
        c.stroke();
        for (let i = 0; i < 5; i++) {
            c.beginPath();
            c.moveTo(0, y + 17 + i * 24);
            c.bezierCurveTo(230, y + 4 + i * 24, 430, y + 28 + i * 24, 700, y + 14 + i * 24);
            c.stroke();
        }
    }
    c.strokeStyle = '#fff8e244';
    c.lineWidth = 2;
    c.strokeRect(16, 16, 668, 668);
    // A mug ring and notebook corner give the table scale, without game geometry.
    c.strokeStyle = '#a3793833';
    c.lineWidth = 5;
    c.beginPath();
    c.arc(630, 73, 43, 0, Math.PI * 2);
    c.stroke();
    const s = f.strike;
    if (s && f.tick <= s.impact_tick) {
        const [x, y] = world(s.aim_x, s.aim_y), progress = Math.max(0, Math.min(1, (f.tick - s.start_tick) / (s.impact_tick - s.start_tick))), radius = s.radius * 700 / (profile.arena_half_size * 2);
        c.save();
        c.translate(x, y);
        c.fillStyle = `rgba(51,43,31,${.07 + .29 * progress})`;
        c.beginPath();
        c.ellipse(0, 0, radius * (.2 + .8 * progress), radius * (.2 + .8 * progress), 0, 0, Math.PI * 2);
        c.fill();
        c.save();
        c.scale(radius * (.2 + .8 * progress) / 50, radius * (.2 + .8 * progress) / 50);
        c.fillStyle = `rgba(30,32,26,${.1 + .25 * progress})`;
        c.beginPath();
        c.ellipse(0, 12, 22, 24, 0, 0, Math.PI * 2);
        c.fill();
        for (let finger = 0; finger < 4; finger++) {
            c.beginPath();
            c.roundRect(-22 + finger * 12, -37 + (finger === 0 || finger === 3 ? 8 : 0), 10, 49, 5);
            c.fill();
        }
        c.beginPath();
        c.ellipse(-27, 11, 9, 20, -.55, 0, Math.PI * 2);
        c.fill();
        c.restore();
        c.strokeStyle = '#fff4da';
        c.lineWidth = 2;
        c.setLineDash([4, 5]);
        c.beginPath();
        c.arc(0, 0, radius, 0, Math.PI * 2);
        c.stroke();
        c.restore();
    }
    fly(c, f);
    const impact = f.impact || (lastImpact && f.tick >= lastImpact.tick && f.tick <= lastImpact.tick + 400 ? lastImpact : null);
    if (impact) {
        const [x, y] = world(impact.position.x, impact.position.y);
        c.save();
        c.translate(x, y - 45);
        c.rotate(-.1);
        c.fillStyle = impact.caught ? '#f6edca' : '#24483c';
        c.fillRect(-68, -24, 136, 43);
        c.fillStyle = impact.caught ? '#24483c' : '#fff7de';
        c.font = 'bold 27px Georgia';
        c.textAlign = 'center';
        c.fillText(impact.caught ? 'GOTCHA!' : 'NICE TRY.', 0, 6);
        c.restore();
    }
    if (holdStart !== null && !replaying) {
        const [x, y] = world(aim.x, aim.y);
        c.strokeStyle = '#fff9dc';
        c.lineWidth = 6;
        c.beginPath();
        c.arc(x, y, 32, -Math.PI / 2, -Math.PI / 2 + Math.min(1, (performance.now() - holdStart) / 800) * Math.PI * 2);
        c.stroke();
    }
}
const colors: Record<string, string> = { 'LC4': '#0072b2', 'LPLC2': '#e69f00', 'giant fiber': '#cc79a7', 'walking DNs': '#009e73', 'interior': '#74808b' };
function drawBrain(f: Frame, c = bc) {
    c.fillStyle = '#172f29';
    c.fillRect(0, 0, 560, 420);
    if (!brain)
        return;
    const active = new Set(f.spikes.flatMap(s => s.indices));
    c.fillStyle = '#bbd2bf';
    c.font = '12px system-ui';
    c.fillText('RELATIVE x/z PROJECTION', 18, 24);
    c.fillText('NO SOMA', 465, 24);
    c.strokeStyle = '#61776c';
    c.beginPath();
    c.moveTo(449, 38);
    c.lineTo(449, 390);
    c.stroke();
    const band: Record<string, number> = {};
    for (const n of brain.nodes) {
        let x, y;
        if (n.position) {
            x = 24 + n.position[0] * 400;
            y = 48 + n.position[1] * 330;
        }
        else {
            const gi = Object.keys(colors).indexOf(n.group);
            const k = band[n.group] ?? 0;
            band[n.group] = k + 1;
            x = 463 + (k % 7) * 11;
            y = 62 + gi * 64 + Math.floor(k / 7) * 8;
        }
        c.globalAlpha = active.has(n.index) ? 1 : .2;
        c.fillStyle = colors[n.group];
        c.beginPath();
        c.arc(x, y, active.has(n.index) ? (n.group === 'giant fiber' ? 5 : 2.6) : 1.25, 0, Math.PI * 2);
        c.fill();
    }
    c.globalAlpha = 1;
}
function beginReplay() { replaying = true; paused = true; replayIndex = 0; replayStart = performance.now(); $('brain-panel').classList.add('active'); $('replay-badge').textContent = 'RECORDED / 0.25×'; $('brain-title').textContent = lastImpact?.caught ? 'A very close encounter.' : 'Gone in a buzz.'; $('caption').textContent = lastImpact?.lead_ms !== null ? `Giant fiber fired ${lastImpact.lead_ms} ms before your hand landed.` : 'Giant fiber never fired before your hand landed during this strike.'; document.querySelector<HTMLElement>('.replay-actions')!.hidden = false; ($('video') as HTMLButtonElement).disabled = !('MediaRecorder' in window) || !('captureStream' in table); $('continue').textContent = finished ? 'Play another round →' : 'Next strike →'; }
function animate(now: number) {
    frames++;
    let shown = frame;
    if (replaying && replay.length) {
        replayIndex = Math.max(0, Math.min(replay.length - 1, Math.floor((now - replayStart) / 40)));
        shown = replay[replayIndex];
    }
    drawTable(shown);
    drawBrain(shown);
    if (holdStart !== null) {
        const ms = now - holdStart;
        $('charge-text').textContent = ms < 180 ? 'FLICK / QUICK & SMALL' : ms < 500 ? 'SLAP / A LITTLE MORE HAND' : 'SWAT / SLOW & MIGHTY';
    }
    requestAnimationFrame(animate);
}
worker.onmessage = event => {
    const m = event.data;
    if (m.kind === 'ready') {
        ready = true;
        ($('start') as HTMLButtonElement).disabled = false;
        $('start').textContent = 'Let’s dance →';
    }
    if (m.kind === 'error') {
        $('notice').textContent = m.error;
        throw new Error(m.error);
    }
    if (m.kind === 'frame') {
        frame = m.frame;
        catches = m.catches;
        used = m.strikes;
        finished = m.done;
        simSpeed = m.simulation_wall_s_per_sim_s;
        $('time').innerHTML = `${Math.max(0, 30 - frame.tick * .0005).toFixed(1)} <small>SECONDS</small>`;
        $('score').innerHTML = `${catches} <small>CAUGHT</small>`;
        $('strikes').innerHTML = `${6 - used} <small>STRIKES LEFT</small>`;
        if (frame.impact && frame.tick !== lastSoundTick) {
            lastSoundTick = frame.tick;
            lastImpact = frame.impact;
            tone(frame.impact.caught);
            if (!reduced) {
                navigator.vibrate?.(frame.impact.caught ? [30, 20, 40] : 15);
                table.classList.remove('shake');
                void table.offsetWidth;
                table.classList.add('shake');
            }
        }
        if (finished) {
            paused = true;
            $('notice').textContent = `Round complete: ${catches} catches from ${used} strikes.`;
            document.querySelector<HTMLElement>('.replay-actions')!.hidden = false;
            $('continue').textContent = 'Play another round →';
        }
    }
    if (m.kind === 'replay') {
        replay = m.frames;
        lastImpact = m.impact;
        finished = m.done;
        beginReplay();
    }
    if (m.kind === 'log' || m.kind === 'advanced') {
        pending.get(m.id)?.(m.log ?? m);
        pending.delete(m.id);
    }
};
function start() { if (!ready)
    return; started = true; paused = false; $('intro').hidden = true; send('start'); }
$('start').onclick = start;
function point(event: PointerEvent) { const rect = table.getBoundingClientRect(), b = profile.arena_half_size; return { x: Math.max(-b, Math.min(b, ((event.clientX - rect.left) / rect.width * 2 - 1) * b)), y: Math.max(-b, Math.min(b, (1 - (event.clientY - rect.top) / rect.height * 2) * b)) }; }
table.onpointerdown = e => { if (!started || paused || finished || frame.strike)
    return; table.setPointerCapture(e.pointerId); aim = point(e); holdStart = performance.now(); };
table.onpointermove = e => { aim = point(e); };
table.onpointercancel = () => holdStart = null;
table.onpointerup = e => { if (holdStart === null)
    return; const hold_ms = performance.now() - holdStart; holdStart = null; aim = point(e); send('strike', { ...aim, hold_ms }); $('charge-text').textContent = 'COMMITTED. THE HAND IS ON ITS WAY.'; };
table.onkeydown = e => { if (e.code === 'Enter' && started && !paused && !finished) {
    e.preventDefault();
    send('strike', { x: 0, y: 0, hold_ms: 250 });
} };
$('again').onclick = () => { replayStart = performance.now(); replaying = true; };
$('continue').onclick = () => { if (finished) {
    location.reload();
    return;
} replaying = false; paused = false; document.querySelector<HTMLElement>('.replay-actions')!.hidden = true; $('charge-text').textContent = 'TAP: FLICK · HOLD: SLAP · LONG HOLD: SWAT'; send('resume'); };
function save(blob: Blob, name: string) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 10000); }
$('save-log').onclick = async () => save(new Blob([JSON.stringify(await request('log'), null, 2)], { type: 'application/json' }), 'flybench-round.json');
function composite() { const c = document.createElement('canvas'); c.width = 1200; c.height = 800; const g = c.getContext('2d')!; g.fillStyle = '#f6edd9'; g.fillRect(0, 0, 1200, 800); g.fillStyle = '#183c31'; g.font = 'bold 54px Georgia'; g.fillText('Catch the Fly.', 35, 66); g.font = '22px system-ui'; g.fillText(`${catches} caught / ${used} strikes · provisional model`, 35, 105); g.drawImage(table, 30, 135, 620, 620); g.drawImage(brainCanvas, 670, 180, 500, 375); g.font = '19px system-ui'; g.fillText('Recorded brain-cam · MaleCNS v1.0 wiring', 670, 610); g.fillText('Simplified neurons, vision and takeoff', 670, 644); return c; }
$('card').onclick = () => composite().toBlob(blob => { if (blob)
    save(blob, 'catch-the-fly.png'); });
$('video').onclick = async () => {
    if (!replay.length || !('MediaRecorder' in window) || !('captureStream' in table))
        return;
    const mime = ['video/webm;codecs=vp9', 'video/webm', 'video/mp4'].find(t => MediaRecorder.isTypeSupported(t));
    if (!mime) {
        $('notice').textContent = 'Video export unavailable in this browser. Save a result card instead.';
        return;
    }
    const canvas = composite(), g = canvas.getContext('2d')!, stream = canvas.captureStream(25), recorder = new MediaRecorder(stream, { mimeType: mime });
    const chunks: Blob[] = [];
    recorder.ondataavailable = e => chunks.push(e.data);
    recorder.onstop = () => { save(new Blob(chunks, { type: mime }), mime.includes('mp4') ? 'fly-replay.mp4' : 'fly-replay.webm'); stream.getTracks().forEach(t => t.stop()); $('notice').textContent = 'Replay video saved.'; };
    $('notice').textContent = 'Recording your replay…';
    replaying = true;
    replayStart = performance.now();
    recorder.start();
    const timer = setInterval(() => g.drawImage(composite(), 0, 0), 40);
    setTimeout(() => { clearInterval(timer); recorder.stop(); }, replay.length * 40 + 100);
};
(async () => {
    try {
        [runtime, profile, brain, buffer] = await Promise.all([fetch('/data/runtime.json').then(r => r.json()), fetch('/data/game.json').then(r => r.json()), fetch('/data/brain.json').then(r => r.json()), fetch('/data/circuit.webbin').then(r => r.arrayBuffer())]);
        $('model-counts').textContent = `Executed scope: ${runtime.counts.N.toLocaleString()} neurons, ${runtime.counts.source_accepted_E.toLocaleString()} connections, ${runtime.counts.represented_source_contacts.toLocaleString()} biological contacts. ${runtime.counts.zero_disabled_E.toLocaleString()} connections have disabled unknown signs.`;
        $('map-note').textContent = `Relative x/z soma projection; ${brain.missing} neurons without somaLocation are grouped in the side band. Anatomical camera orientation is unverified.`;
        const random = new Uint32Array(2);
        crypto.getRandomValues(random);
        send('init', { buffer, runtime, profile, neuralSeed: manual ? 2026092802 : random[0], environmentSeed: manual ? 8128 : random[1], manual });
    }
    catch (e) {
        $('notice').textContent = 'Local model data could not load. Run the documented export command.';
        throw e;
    }
})();
requestAnimationFrame(animate);
if (manual)
    (window as any).flyTest = { ready: () => ready, start, advance: (intervals: number) => request('advance', { intervals }), strike: (x: number, y: number, hold_ms: number) => send('strike', { x, y, hold_ms }), resume: () => ($('continue') as HTMLButtonElement).click(), log: () => request('log'), state: () => ({ frame, catches, used, finished, replaying, simSpeed, fps: frames / ((performance.now() - rafStart) / 1000) }), showReplay: () => beginReplay() };
