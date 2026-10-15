import './style.css';
import {fetchGraph} from '../../../packages/kernel-ts/src/transport.ts';
import type { Frame } from './game.ts';
const app = document.querySelector<HTMLDivElement>('#app')!;
app.innerHTML = `<main><header><a class="brand" href="./">FLYBENCH <span>FIELD NOTES / 002</span></a><span class="model-tag">provisional model</span></header>
<section class="title"><div><p class="eyebrow">MEET YOUR VERY SMALL OPPONENT</p><h1>Catch the <i>Fly.</i></h1></div><p>A tiny brain.<br>A big attitude.</p></section>
<div class="status"><span id="time">30.0 <small>SECONDS</small></span><span id="score">0 <small>CAUGHT</small></span><span id="strikes">6 <small>STRIKES LEFT</small></span></div>
<section class="play-layout"><div class="table-wrap"><canvas id="table" width="700" height="700" tabindex="0" aria-label="Fly arena. Hold to charge, release to strike. Enter strikes the center."></canvas><div id="intro"><span class="stamp">WANTED<br>ALIVE & BUZZING</span><h2>Six chances.<br>One little show-off.</h2><p>Tap for a flick. Hold for a slap.<br>Hold longer for a mighty swat.</p><button id="start" disabled>Waking the fly…</button><small>No account. No tracking. Just you and a fly.</small></div><div id="impact-label" aria-live="polite"></div><span class="table-note">SPECIMEN 01 / HANDLE WITH CURIOSITY</span></div>
<aside id="brain-panel"><div class="panel-top"><span class="eyebrow">BRAIN-CAM</span><b id="replay-badge">WAITING FOR YOUR MOVE</b></div><h2 id="brain-title">A look inside<br>the little troublemaker.</h2><canvas id="brain" width="560" height="420" aria-label="Recorded neuron activity map"></canvas><canvas id="timeline" width="560" height="120" aria-label="Recorded hand height, population rates, giant-fiber spikes and impact"></canvas><p id="caption">After each strike, watch the recorded neurons flash at quarter speed.</p><div class="legend"><span style="--dot:#0072b2">LC4</span><span style="--dot:#e69f00">LPLC2</span><span style="--dot:#cc79a7">Giant fiber</span><span style="--dot:#009e73">Walking DNs</span><span style="--dot:#74808b">Interior</span></div><small id="map-note">Relative soma positions. Missing coordinates appear in the side band.</small><div class="replay-actions" hidden><button id="again">Replay 0.25×</button><button id="continue">Next strike →</button></div></aside></section>
<div class="instruction"><strong id="charge-text">TAP: FLICK · HOLD: SLAP · LONG HOLD: SWAT</strong><span>The growing hand shadow is the looming stimulus the fly sees.</span></div>
<section class="bottom"><details><summary>What is real here? <span>+</span></summary><p id="model-counts"></p><p>Measured MaleCNS wiring drives a simplified neural model. Vision uses size and expansion features. Neurons share a uniform LIF model. Takeoff is abstract and follows heading with seeded jitter. Missing signs and turn directions remain explicit.</p><p><span id="science-status">Calibration status loading.</span> No wiring-superiority or human usability result is claimed.</p><a href="./model.html">Model card</a> · <a href="./preregistration.html">Pre-registration status</a> · <a href="https://male-cns.janelia.org/download/">MaleCNS v1.0, CC-BY</a></details><div class="settings"><button id="coupling">Try the coupling lab</button><button id="lab">Open lesion lab</button><span id="activity">0.0 Hz · circuit activity</span><label><input id="reduce" type="checkbox"> Reduced motion</label><label><input id="sound" type="checkbox" checked> Sound</label><button id="save-log">Save round log</button><button id="card">Save result card</button><button id="video" disabled>Save replay video</button></div></section><div id="lab-panel" hidden></div><section id="finding"><h2>What did we find?</h2><p>In this model, measured wiring stays stable at couplings where degree- and sign-matched shuffles saturate.</p><img src="./finding.png" alt="Measured T1a rate and N-SIGN null band across coupling" loading="lazy"><p>Uniform neurons, assumed signs and simplified inputs limit this result to the model; escape and walking comparisons had insufficient calibratable nulls. Robustness tests are pending.</p><a href="https://github.com/Alpi157/internet-vs-one-fly/blob/main/docs/preregistration-v2.md">Pre-registration</a> · <a href="https://github.com/Alpi157/internet-vs-one-fly/blob/main/docs/findings-v2e.md">Findings</a></section><p id="notice" role="status"></p><button id="coupling-invitation" hidden>Same neurons, different wiring. See the finding →</button><footer>A real wiring diagram. An imaginary fly. A very personal rivalry.</footer></main>`;
const couplingHost=document.createElement('div');couplingHost.id='coupling-host';couplingHost.hidden=true;document.body.append(couplingHost);
let couplingOpen=false;
const $ = (id: string) => document.getElementById(id)!;
document.querySelector('.table-wrap')!.prepend(document.querySelector('.status')!);
document.querySelector('.replay-actions')!.append($('card'),$('video'));
const table = $('table') as HTMLCanvasElement, brainCanvas = $('brain') as HTMLCanvasElement;
const timeline = $('timeline') as HTMLCanvasElement;
const base = import.meta.env.BASE_URL;
const shareURL = 'https://alpi157.github.io/internet-vs-one-fly/';
const history: Frame[] = [];
const ctx = table.getContext('2d')!, bc = brainCanvas.getContext('2d')!;
const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
let displayStatus='';
let runtime: any, profile: any, brain: any, buffer: ArrayBuffer;
let frame: Frame = { tick: 0, body: { x: 0, y: 0, heading_x: 1, heading_y: 0 }, air: false, applied: [false,0,0], gait: 0, activity_hz: 0, strike: null, impact: null, onset: false, spikes: [] };
let ready = false, started = false, replaying = false, paused = false, finished = false, catches = 0, used = 0;
let replayPinned: number|null=null;
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
            const stride = reduced ? 0 : Math.sin(f.gait*12+i*Math.PI)*5;
            c.lineTo(-18 + i * 12 + stride, sign * (18 + (i % 2) * 3));
            c.lineTo(-12 + i * 12, sign * 23);
            c.stroke();
        }
    c.fillStyle = '#fffdf2cc';
    c.strokeStyle = '#76948b';
    c.lineWidth = 1.5;
    for (const sign of [-1, 1]) {
        c.beginPath();
        c.ellipse(-8, sign * (f.air ? 20 : 14), f.air ? 30 : 22, f.air ? 17 : 10, sign * .45, 0, Math.PI * 2);
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
function drawTableBackground(c:CanvasRenderingContext2D) {
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
}
const boardLayer=document.createElement('canvas');boardLayer.width=700;boardLayer.height=700;drawTableBackground(boardLayer.getContext('2d')!);
function drawTable(f:Frame,c=ctx){
    c.drawImage(boardLayer,0,0);
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
        c.translate(0,-85*(1-progress));
        c.scale((50+radius*.4)/50,(50+radius*.4)/50);
        c.fillStyle = '#bd754c';
        c.strokeStyle = '#74482d';
        c.lineWidth = 2;
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
    if(f.air && !reduced) {
        const path=(replaying?replay:history).filter(v=>v.tick<=f.tick && v.tick>=f.tick-160 && v.air);
        c.strokeStyle='#fff9dfaa';c.lineWidth=6;c.beginPath();
        path.forEach((v,i)=>{const [x,y]=world(v.body.x,v.body.y);if(i===0)c.moveTo(x,y);else c.lineTo(x,y);});c.stroke();
    }
    fly(c, f);
    const impact = f.impact || (lastImpact && f.tick >= lastImpact.tick && f.tick <= lastImpact.tick + 400 ? lastImpact : null);
    if (impact) {
        if(!reduced && f.tick-impact.tick<60){c.fillStyle='#fff5ce55';c.fillRect(0,0,700,700);}
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
let brainLayer:HTMLCanvasElement|null=null;
let brainPositions:number[][]=[];
function drawBrain(f:Frame,c=bc){
    if(!brain)return;
    if(!brainLayer){
        brainLayer=document.createElement('canvas');brainLayer.width=560;brainLayer.height=420;
        const b=brainLayer.getContext('2d')!;b.fillStyle='#172f29';b.fillRect(0,0,560,420);
        b.fillStyle='#bbd2bf';b.font='12px system-ui';b.fillText('RELATIVE x/z PROJECTION',18,24);b.fillText('NO SOMA',465,24);
        b.strokeStyle='#61776c';b.beginPath();b.moveTo(449,38);b.lineTo(449,390);b.stroke();
        const band:Record<string,number>={};
        brainPositions=brain.nodes.map((n:any)=>{let x,y;if(n.position){x=24+n.position[0]*400;y=48+n.position[1]*330;}else{const gi=Object.keys(colors).indexOf(n.group),k=band[n.group]??0;band[n.group]=k+1;x=463+(k%7)*11;y=62+gi*64+Math.floor(k/7)*8;}b.globalAlpha=.22;b.fillStyle=colors[n.group];b.beginPath();b.arc(x,y,1.25,0,Math.PI*2);b.fill();return [x,y];});
    }
    c.drawImage(brainLayer,0,0);
    const observed=(replaying?replay:history).filter(v=>v.tick<=f.tick&&v.tick>=f.tick-100),last=new Map<number,number>();
    for(const v of [...observed,f])for(const event of v.spikes)for(const i of event.indices)last.set(i,event.tick);
    for(const [i,tick] of last){const n=brain.nodes[i],[x,y]=brainPositions[i],alpha=Math.max(.15,1-(f.tick-tick)/120);c.fillStyle=colors[n.group];c.globalAlpha=alpha*.25;c.beginPath();c.arc(x,y,n.group==='interior'?8:14,0,Math.PI*2);c.fill();c.globalAlpha=alpha;c.beginPath();c.arc(x,y,n.group==='giant fiber'?8:n.group==='interior'?3.5:5,0,Math.PI*2);c.fill();}
    c.globalAlpha=1;
}
function drawTimeline(f:Frame) {
    const c=timeline.getContext('2d')!, data=replaying?replay:history.slice(-65);
    c.fillStyle='#10251f';c.fillRect(0,0,560,120);
    if(!data.length || !brain)return;
    const first=data[0].tick,last=data.at(-1)!.tick,span=Math.max(20,last-first);
    const x=(tick:number)=>100+(tick-first)/span*445;
    const indexGroups=new Map<number,string>(brain.nodes.map((n:any)=>[n.index,n.group]));
    const groups=['LC4','LPLC2'];
    const rates=data.map(v=>groups.map(group=>v.spikes.reduce((n,e)=>n+e.indices.filter(i=>indexGroups.get(i)===group).length,0)/Math.max(1,brain.nodes.filter((n:any)=>n.group===group).length)/.01));
    c.font='10px monospace';
    for(let row=0;row<4;row++) {
        const y=19+row*25;c.fillStyle='#d7e7d4';
        const label=row===0?'HAND HEIGHT':row===3?'GIANT FIBER':groups[row-1]+' Hz';c.fillText(label,6,y);
        c.strokeStyle=row===0?'#f0ca81':row===3?colors['giant fiber']:colors[groups[row-1]];
        const maximum=row===0?8:row===3?1:Math.max(1,...rates.map(v=>v[row-1]));
        c.beginPath();
        for(let i=0;i<data.length;i++) {
            const v=data[i];const value=row===0?(v.strike && v.tick<=v.strike.impact_tick?Math.max(0,8-(v.tick-v.strike.start_tick)*.5*v.strike.speed):0):row===3?0:rates[i][row-1];
            const yy=y+3-value/maximum*18;
            if(i===0)c.moveTo(x(v.tick),yy);else {c.lineTo(x(v.tick),y+3-(row===0?(data[i-1].strike && data[i-1].tick<=data[i-1].strike.impact_tick?Math.max(0,8-(data[i-1].tick-data[i-1].strike.start_tick)*.5*data[i-1].strike.speed):0):row===3?0:rates[i-1][row-1])/maximum*18);c.lineTo(x(v.tick),yy);}
            if(row===3)for(const event of v.spikes)if(event.indices.some(j=>indexGroups.get(j)==='giant fiber')){c.moveTo(x(event.tick),y+3);c.lineTo(x(event.tick),y-15);}
        }
        c.stroke();
    }
    if(lastImpact && lastImpact.tick>=first && lastImpact.tick<=last){c.strokeStyle='#fff';c.setLineDash([3,3]);c.beginPath();c.moveTo(x(lastImpact.tick),0);c.lineTo(x(lastImpact.tick),120);c.stroke();c.setLineDash([]);}
    c.strokeStyle='#e69f00';c.beginPath();c.moveTo(x(f.tick),0);c.lineTo(x(f.tick),120);c.stroke();
}
function beginReplay() { replayPinned=null; replaying = true; paused = true; replayIndex = 0; replayStart = performance.now(); $('brain-panel').classList.add('active'); $('replay-badge').textContent = 'RECORDED / 0.25×'; $('brain-title').textContent = lastImpact?.caught ? 'A very close encounter.' : 'Gone in a buzz.'; $('caption').textContent = lastImpact?.lead_ms !== null ? `Giant fiber fired ${lastImpact.lead_ms} ms before your hand landed.` : 'Giant fiber never fired before your hand landed during this strike.'; document.querySelector<HTMLElement>('.replay-actions')!.hidden = false; ($('video') as HTMLButtonElement).disabled = !('MediaRecorder' in window) || !('captureStream' in table); $('continue').textContent = finished ? 'Play another round →' : 'Skip / next strike →'; }
let paintedTick=-1,paintedReplay=false;
function animate(now: number) {
    if(couplingOpen){requestAnimationFrame(animate);return;}
    frames++;
    let shown = frame;
    if (replaying && replay.length) {
        replayIndex = replayPinned ?? Math.max(0, Math.min(replay.length - 1, Math.floor((now - replayStart) / 40)));
        shown = replay[replayIndex];
    }
    if(shown.tick!==paintedTick||replaying!==paintedReplay||holdStart!==null){
      drawTable(shown);drawBrain(shown);drawTimeline(shown);paintedTick=shown.tick;paintedReplay=replaying;
    }
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
        history.push(frame);if(history.length>3000)history.shift();
        $('activity').textContent=frame.activity_hz.toFixed(1)+' Hz · circuit activity';
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
            $('coupling-invitation').hidden=false;
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
async function showCoupling(){
  send('pause');couplingOpen=true;app.hidden=true;
  const {openCoupling}=await import('./coupling.ts');
  await openCoupling(couplingHost,base,()=>{couplingOpen=false;app.hidden=false;paintedTick=-1;if(started&&!paused&&!finished)send('resume');});
  window.scrollTo(0,0);
}
$('coupling').onclick=showCoupling;$('coupling-invitation').onclick=showCoupling;

$('lab').onclick = async()=>{const {openLab}=await import('./lab.ts');openLab($('lab-panel'),async(mode:string)=>{
    paused=true;replaying=false;started=false;ready=false;history.length=0;replay=[];catches=0;used=0;finished=false;$('brain-panel').classList.remove('active');
    const {configureLab}=await import('./lab.ts');const selected=await configureLab(mode,buffer,runtime,base);
    $('intro').hidden=false;send('init',{buffer:selected.buffer,runtime:selected.runtime,profile,neuralSeed:2026092802,environmentSeed:8128,manual});
    displayStatus=selected.label;document.querySelector('.model-tag')!.textContent=displayStatus.toLowerCase();
    $('notice').textContent=selected.label+'; new round, explicit reset.';
});};
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
$('again').onclick = () => { replayPinned=null; replayStart = performance.now(); replaying = true; };
$('continue').onclick = () => { if (finished) {
    location.reload();
    return;
} replaying = false; paused = false; $('brain-panel').classList.remove('active'); document.querySelector<HTMLElement>('.replay-actions')!.hidden = true; $('charge-text').textContent = 'TAP: FLICK · HOLD: SLAP · LONG HOLD: SWAT'; send('resume'); };
function save(blob: Blob, name: string) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 10000); }
$('save-log').onclick = async () => save(new Blob([JSON.stringify(await request('log'), null, 2)], { type: 'application/json' }), 'flybench-round.json');
function composite(portrait=false) {
    const c=document.createElement('canvas');c.width=portrait?720:1200;c.height=portrait?1280:630;
    const g=c.getContext('2d')!;g.fillStyle='#f6edd9';g.fillRect(0,0,c.width,c.height);g.fillStyle='#183c31';
    g.font='bold 46px Georgia';g.fillText('Catch the Fly.',28,56);g.font='18px system-ui';
    g.fillText(`${catches} caught / ${used} strikes · ${displayStatus.toLowerCase()}`,28,88);
    if(portrait){g.drawImage(table,20,110,680,680);g.drawImage(brainCanvas,20,806,490,367);g.drawImage(timeline,20,1178,680,60);}
    else {g.drawImage(table,25,110,490,490);g.drawImage(brainCanvas,540,115,630,390);g.drawImage(timeline,540,510,630,80);}
    g.fillStyle='#183c31';g.font='16px system-ui';
    const caption=$('caption').textContent??'Recorded brain-cam';
    if(portrait){const words=caption.split(' ');let line='',y=850;for(const word of words){if(g.measureText(line+word).width>155){g.fillText(line,530,y);line='';y+=24;}line+=word+' ';}g.fillText(line,530,y);}
    g.font='14px monospace';g.fillText(shareURL,portrait?20:540,portrait?1260:618);
    return c;
}
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
    const canvas = composite(true), g = canvas.getContext('2d')!, stream = canvas.captureStream(25), recorder = new MediaRecorder(stream, { mimeType: mime });
    const chunks: Blob[] = [];
    recorder.ondataavailable = e => chunks.push(e.data);
    recorder.onstop = () => { save(new Blob(chunks, { type: mime }), mime.includes('mp4') ? 'fly-replay.mp4' : 'fly-replay.webm'); stream.getTracks().forEach(t => t.stop()); $('notice').textContent = 'Replay video saved.'; };
    $('notice').textContent = 'Recording your replay…';
    replayPinned=null;
    replaying = true;
    replayStart = performance.now();
    recorder.start();
    const timer = setInterval(() => g.drawImage(composite(true), 0, 0), 40);
    setTimeout(() => { clearInterval(timer); recorder.stop(); }, replay.length * 40 + 100);
};
(async () => {
    try {
        [runtime, profile, brain, buffer] = await Promise.all([fetch(base+'data/runtime.json').then(r => r.json()), fetch(base+'data/game.json').then(r => r.json()), fetch(base+'data/brain.json').then(r => r.json()), fetchGraph(base+'data/circuit.flygraph.gz')]);
        displayStatus=runtime.status;
        document.querySelector('.model-tag')!.textContent = displayStatus.toLowerCase();
        $('science-status').textContent = runtime.status + '. Stability differs from the registered shuffles; H1 and H2 have insufficient calibratable nulls.';
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
    (window as any).flyTest = { ready: () => ready, start, startLive:()=>{ready=false;send('init',{buffer,runtime,profile,neuralSeed:2026092802,environmentSeed:8128,manual:false});}, advance: (intervals: number) => request('advance', { intervals }), strike: (x: number, y: number, hold_ms: number) => send('strike', { x, y, hold_ms }), resume: () => ($('continue') as HTMLButtonElement).click(), log: () => request('log'), state: () => ({ frame, catches, used, finished, replaying, simSpeed, fps: frames / ((performance.now() - rafStart) / 1000) }), showReplay: () => beginReplay(), showRecorded: (kind:string)=>{const index=kind==='takeoff'?replay.findIndex(f=>f.air):replay.reduce((best,f,i)=>f.spikes.reduce((n,e)=>n+e.indices.length,0)>(replay[best]?.spikes.reduce((n,e)=>n+e.indices.length,0)??-1)?i:best,0);if(index<0)return false;replayPinned=index;drawTable(replay[index]);drawBrain(replay[index]);drawTimeline(replay[index]);return true;} };
