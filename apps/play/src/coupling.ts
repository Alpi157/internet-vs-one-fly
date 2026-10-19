import {loadResults} from './results.ts';
import {fetchGraph} from '../../../packages/kernel-ts/src/transport.ts';
import {BrainView} from './brain-view.ts';
import {openLab} from './lab.ts';
import type {Frame} from './game.ts';
const repo='https://github.com/Alpi157/internet-vs-one-fly/blob/main/';
export function dotoNumber(value:number){const text=value.toFixed(2);return `<span class="sr-only">${text}</span><span aria-hidden="true">${text.replace('.', '<i class="decimal-dot"></i>')}</span>`;}
export function chartSVG(data:any,family:string,scale:number,width=800){
  const all=data.families.flatMap((f:any)=>f.points.flatMap((p:any)=>p.band));
  const max=Math.ceil(Math.max(...all,...data.measured.map((p:any)=>p.rate_hz))/50)*50;
  const grid=data.measured.map((p:any)=>p.s),lo=Math.min(...grid),hi=Math.max(...grid);
  const x=(s:number)=>60+Math.log(s/lo)/Math.log(hi/lo)*(width-80),y=(r:number)=>220-r/max*190;
  const path=(points:number[][])=>points.map(([s,r],i)=>`${i?'L':'M'}${x(s)},${y(r)}`).join(' ');
  const bands=data.families.map((f:any)=>{const pts=f.points;return `<path d="${path([...pts.map((p:any)=>[p.s,p.band[0]]),...pts.slice().reverse().map((p:any)=>[p.s,p.band[1]])])}Z" fill="${f.family===family?'#63f29a33':'none'}" stroke="#63f29a" ${f.family===family?'':'stroke-dasharray="5 5"'}/>`;}).join('');
  return `<svg id="coupling-canvas" viewBox="0 0 ${width} 260" preserveAspectRatio="none" role="img" aria-label="Registered measured rate curve and descriptive shuffle percentile bands. Logarithmic connection strength and linear rate axes. ${family} filled. Missing tails are not filled."><g font-family="Atkinson" font-size="17" fill="#9ba59c">${[0,max/2,max].map(n=>`<text x="8" y="${y(n)+6}">${n}</text>`).join('')}${data.x_ticks.map((s:number)=>`<text x="${x(s)}" y="252" text-anchor="${s===lo?'start':s===hi?'end':'middle'}">${s}</text>`).join('')}</g><path d="M60 ${y(data.reference_hz)}H${width-20}" stroke="#9ba59c" stroke-dasharray="4 5"/>${bands}${[[data.game_coupling,'Game'],[data.registered_coupling,'Test']].map(([s,label])=>`<path d="M${x(Number(s))} 30V220" stroke="#9ba59c" stroke-opacity=".45" stroke-dasharray="2 4"/><text x="${x(Number(s))}" y="20" text-anchor="middle" fill="#9ba59c" font-family="Atkinson" font-size="17">${label}</text>`).join('')}<path d="${path(data.measured.map((p:any)=>[p.s,p.rate_hz]))}" fill="none" stroke="#e9ede6" stroke-width="3"/><path d="M${x(scale)} 22V220" stroke="#e9ede6"/><path d="M60 220H${width-20}" stroke="#687369"/></svg>`;
}
export async function openCoupling(host:HTMLElement,base:string,onClose:()=>void,onLesion:(mode:string)=>Promise<void>){
  host.hidden=false;
  host.innerHTML=`<main class="coupling-view"><header><a href="${base}">Catch the fly</a><nav aria-label="Main"><button id="lab-play">Play</button><span aria-current="page">Wiring lab</span><a href="${base}how-it-works.html">How it works</a><a href="https://github.com/Alpi157/internet-vs-one-fly">Code and data ↗</a></nav></header><button id="coupling-close" class="back">‹ Back to the game</button><div class="segments lab-tabs" role="tablist" aria-label="Wiring lab"><button role="tab" aria-selected="true" aria-controls="shuffle-panel" id="shuffle-tab">Shuffle</button><button role="tab" aria-selected="false" aria-controls="silence-panel" id="silence-tab" tabindex="-1">Silence</button></div><section id="shuffle-panel" role="tabpanel" aria-labelledby="shuffle-tab" class="lab-layout"><div class="lab-intro"><h1>Scramble the wiring</h1><p class="phone-hint">Same neurons and partner counts. Only who connects to whom is shuffled.</p><p class="desktop-hint">Same neurons, each with the same number of excitatory and inhibitory partners. Only who connects to whom is shuffled. Then also keep each neuron's total input strength: most of the registered rate gap closes. In this model, the exploratory results suggest that how unevenly input strength is spread matters more than which partners connect.</p></div><div class="lab-control-card"><div class="segments shuffle-family" role="radiogroup" aria-label="Shuffle type"><label><input type="radio" name="shuffle-family" value="N-SIGN" checked>Shuffle partners</label><label><input type="radio" name="shuffle-family" value="N-STRENGTH">Keep input strength</label></div><p id="shuffle-note"></p><div class="coupling-controls"><label for="coupling-slider">Connection strength <output id="coupling-value"></output></label><input id="coupling-slider" aria-label="Connection strength" type="range" min="0" step="1" disabled><div class="slider-ticks"><span>Weaker</span><span class="setting-tick" id="game-tick">Game setting</span><span class="setting-tick" id="registered-tick">Registered test</span><span>Stronger</span></div><p id="coupling-value-note"></p></div><p id="lab-circuit"></p></div><div class="lab-brains">${['Real wiring','Shuffled partners'].map((title,i)=>`<section><h2 id="lab-title-${i}">${title}</h2><div id="lab-brain-${i}"></div><div id="lab-rate-${i}" class="live-rate">…</div><p class="rate-label">spikes a second, per neuron, live (last 250 ms)</p><details class="shuffle-info"><summary id="lab-seed-${i}">Loading identity…</summary><p id="lab-rule-${i}"></p></details></section>`).join('')}</div><figure class="lab-chart"><figcaption id="registered-title"></figcaption><div id="chart"></div><div class="chart-legend"><span>━ Real wiring</span><span class="band-key">Filled: selected shuffle</span><span>┄ Other shuffle</span><span id="reference-label"></span><span>Connection strength (log scale)</span></div><p id="grid-note"></p><details><summary>Registered data and model limits</summary><p id="coupling-caveat"></p><p id="coupling-identity"></p></details></figure><div class="lab-actions"><a href="${repo}docs/findings-v2f.md">Both tests were registered before they ran. Read the results</a><button id="coupling-drop" class="primary" disabled>Drop the hand on both</button><p id="coupling-status" role="status">Loading measured circuit and declared shuffles…</p><p class="coupling-note">Changing the shuffle or connection strength resets both simulations with the same noise seed. No threat is present until you drop the hand. Movement comes from each fly's neural decoder.</p></div></section><section id="silence-panel" role="tabpanel" aria-labelledby="silence-tab" hidden></section></main>`;
  const layout=host.querySelector('.lab-layout')!,left=document.createElement('div'),right=document.createElement('div');
  left.className='lab-left';right.className='lab-right';
  for(const selector of ['.lab-intro','.lab-control-card','.lab-actions'])left.append(host.querySelector(selector)!);
  for(const selector of ['.lab-brains','.lab-chart'])right.append(host.querySelector(selector)!);
  layout.append(left,right);
  const slider=host.querySelector<HTMLInputElement>('#coupling-slider')!,status=host.querySelector<HTMLElement>('#coupling-status')!;
  const worker=new Worker(new URL('./coupling-worker.ts',import.meta.url),{type:'module'});
  let runtime:any,results:any,original:ArrayBuffer,profile:any,targets:any,strength:any;
  let family='N-SIGN',scale=0,generation=0,closed=false,silence=false,speed=0,panels:any[]=[],views:BrainView[]=[],histories:Frame[][]=[[],[]],paintCount=0;
  const close=()=>{closed=true;worker.terminate();host.hidden=true;host.replaceChildren();(window as any).couplingTest=undefined;onClose();};
  host.querySelector<HTMLButtonElement>('#coupling-close')!.onclick=close;
  host.querySelector<HTMLButtonElement>('#lab-play')!.onclick=close;
  const drawChart=()=>{host.querySelector('#chart')!.innerHTML=chartSVG(results.chart,family,scale,innerWidth<900?400:800);};
  const reset=()=>{
    if(!runtime)return;generation++;panels=[];histories=[[],[]];status.textContent='Resetting both neural states…';
    host.querySelector('#coupling-value-note')!.textContent=scale===results.registered_coupling?'The registered rate test ran at this strength.':scale===results.calibrated_coupling?'The game runs at this strength.':'';
    slider.value=String(runtime.grid.indexOf(scale));host.querySelector('output')!.textContent=String(scale);
    const selected=family==='N-SIGN'?runtime.null_selection:{...strength,rule:strength.selection_rule};
    host.querySelector('#shuffle-note')!.textContent=family==='N-SIGN'?"Each neuron's total input strength changes.":'Total input strength kept. The gap mostly closes.';
    host.querySelector('#lab-title-1')!.textContent=family==='N-SIGN'?'Shuffled partners':'Shuffled, strength kept';
    for(let i=0;i<2;i++){
      host.querySelector(`#lab-rate-${i}`)!.textContent='…';
      host.querySelector(`#lab-seed-${i}`)!.textContent=i?`This shuffle: seed ${selected.seed}`:`Simulation noise: seed ${results.lab_seeds.neural}`;
      host.querySelector(`#lab-rule-${i}`)!.textContent=i?`${family}. ${selected.rule}`:`Measured T1a wiring. Both simulations use noise seed ${results.lab_seeds.neural} and environment seed ${results.lab_seeds.environment}. No shuffle is applied to this panel.`;
    }
    drawChart();worker.postMessage({kind:'init',buffer:original,runtime:{...runtime,lab_identity:family==='N-SIGN'?runtime.lab_identity:strength.target_sha256},targets:targets[family],profile,s:scale,generation});
  };
  const tabs=Array.from(host.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
  const tab=(index:number)=>{silence=index===1;tabs.forEach((t,i)=>{t.setAttribute('aria-selected',String(i===index));t.tabIndex=i===index?0:-1;});host.querySelector<HTMLElement>('#shuffle-panel')!.hidden=silence;host.querySelector<HTMLElement>('#silence-panel')!.hidden=!silence;if(silence)worker.postMessage({kind:'pause'});else reset();};
  tabs.forEach((t,i)=>{t.onclick=()=>tab(i);t.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?1:1-i;tab(n);tabs[n].focus();}};});
  const lesion=host.querySelector<HTMLElement>('#silence-panel')!;openLab(lesion,async mode=>{close();await onLesion(mode);});lesion.hidden=true;
  host.querySelectorAll<HTMLInputElement>('[name="shuffle-family"]').forEach(input=>input.onchange=()=>{family=input.value;scale=results.registered_coupling;reset();});
  slider.oninput=()=>{scale=runtime.grid[Number(slider.value)];reset();};
  host.querySelector<HTMLButtonElement>('#coupling-drop')!.onclick=()=>worker.postMessage({kind:'drop'});
  worker.onmessage=e=>{const m=e.data;if(m.kind==='error'){status.textContent=m.error;return;}if(m.kind==='frame'&&m.generation===generation&&!closed){panels=m.panels;speed=m.speed;panels.forEach((p,i)=>{histories[i].push(...p.frames);histories[i]=histories[i].slice(-100);host.querySelector(`#lab-rate-${i}`)!.innerHTML=dotoNumber(p.rate);});status.textContent=`${speed.toFixed(2)}× actual simulation speed. ${(panels[0].tick*.0005).toFixed(2)} simulated seconds. ${panels.some(p=>p.strike)?'Hand stimulus applied.':'No threat.'}`;}if(m.kind==='ended')status.textContent='Two simulated minutes recorded. Change a control to start again.';};
  const animate=()=>{if(closed)return;if(!silence)views.forEach((view,i)=>{const f=histories[i].at(-1);if(f){view.draw(f,histories[i]);paintCount++;}});requestAnimationFrame(animate);};
  try{
    const unpack=async(file:string)=>new Response((await fetch(base+'data/coupling/'+file)).body!.pipeThrough(new DecompressionStream('gzip'))).json();
    const [rt,brain,buf,sign,str,meta,pr,display,published]=await Promise.all([fetch(base+'data/coupling/runtime.json').then(r=>r.json()),fetch(base+'data/coupling/brain.json').then(r=>r.json()),fetchGraph(base+'data/coupling/circuit.flygraph.gz'),unpack('targets.json.gz'),unpack('strength-targets.json.gz'),fetch(base+'data/coupling/strength-demo.json').then(r=>r.json()),fetch(base+'data/game.json').then(r=>r.json()),fetch(base+'data/display-v1.json').then(r=>r.json()),loadResults(base)]);
    if(closed)return;runtime=rt;original=buf;targets={'N-SIGN':sign,'N-STRENGTH':str};strength=meta;profile=pr;results=published;scale=results.registered_coupling;
    views=[0,1].map(i=>{
      const target=host.querySelector<HTMLElement>(`#lab-brain-${i}`)!;
      const view=new BrainView(target,base,brain.nodes,display,'T1a');
      const caption=target.querySelector('.anatomy-caption')!,details=document.createElement('details');
      details.className='anatomy-info';details.innerHTML='<summary>About this anatomy</summary>';details.append(caption);target.append(details);return view;
    });
    slider.max=String(rt.grid.length-1);slider.disabled=false;host.querySelector<HTMLButtonElement>('#coupling-drop')!.disabled=false;
    for(const [id,value] of [['game-tick',results.calibrated_coupling],['registered-tick',results.registered_coupling]])host.querySelector<HTMLElement>('#'+id)!.style.left=`${rt.grid.indexOf(value)/(rt.grid.length-1)*100}%`;
    host.querySelector('#lab-circuit')!.textContent=`Lab circuit: ${results.circuit_counts.lab.toLocaleString('en-US')} neurons (T1a), the circuit used in the registered test. The game uses ${results.circuit_counts.game.toLocaleString('en-US')} (T1b).`;
    host.querySelector('#registered-title')!.textContent=`Registered results, ${results.chart.families[0].n} shuffles per family`;
    host.querySelector('#reference-label')!.textContent=`┄ ${results.chart.reference_hz} Hz reference`;
    host.querySelector('#grid-note')!.textContent=results.chart.caption;
    host.querySelector('#coupling-caveat')!.textContent=results.lab_drive_disclosure+' '+results.lab_caveat+' '+results.bin_note+' '+results.limitations;
    host.querySelector('#coupling-identity')!.textContent=`${brain.nodes.length.toLocaleString('en-US')} neurons per simulation. Live rates use observed spikes over up to 250 simulated ms. Chart: no-threat registered rates, per neuron. Display fade is smoothing only.`;
    reset();requestAnimationFrame(animate);
    (window as any).couplingTest={ready:()=>panels.length===2&&views.every(v=>v.ready),setScale:(s:number)=>{if(!runtime.grid.includes(s))throw Error('Off-grid coupling');scale=s;reset();},setFamily:(f:string)=>{const input=host.querySelector<HTMLInputElement>(`input[value="${f}"]`)!;input.checked=true;family=f;scale=results.registered_coupling;reset();},state:()=>({scale,family,generation,panels:panels.map(p=>({rate:p.rate,tick:p.tick,counts:Array.from(p.counts),seconds:p.seconds})),speed,paintCount,renderers:views.map(v=>v.renderer)}),draw:drawChart};
  }catch(e){worker.terminate();status.textContent='Lab data could not load: '+String(e);throw e;}
}
