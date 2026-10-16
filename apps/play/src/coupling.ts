import {loadResults,renderResults} from './results.ts';
import {fetchGraph} from '../../../packages/kernel-ts/src/transport.ts';
const caption='Same neurons. Same number of excitatory and inhibitory inputs and outputs per neuron. Partners shuffled.';
const repo='https://github.com/Alpi157/internet-vs-one-fly/blob/main/';
export async function openCoupling(host:HTMLElement,base:string,onClose:()=>void){
  host.hidden=false;
  host.innerHTML=`<section class="coupling-view"><div class="coupling-heading"><div><p class="eyebrow">A CONTROLLED COMPARISON</p><h1>Same brain.<br><i>Different partners.</i></h1></div><button id="coupling-close">Back to the fly</button></div><p class="coupling-caption">${caption}</p><div class="coupling-controls"><label>Coupling <output id="coupling-value">0.01</output><input id="coupling-slider" aria-label="Coupling" type="range" min="0" max="10" value="2" step="1"></label><button id="coupling-drop">Drop the hand</button><button id="coupling-clip" disabled>Save the comparison</button></div><p id="coupling-status" role="status">Loading measured circuit and declared shuffle…</p><canvas id="coupling-canvas" width="1000" height="650" aria-label="Measured and scrambled brain heat maps, recorded rates and neural flies"></canvas><p class="coupling-note">Heat shows each neuron's observed firing rate over the last 250 simulated ms. The line marks 50 Hz. Relative x/z soma positions; units and anatomical orientation are unverified. Missing soma coordinates appear in a labeled band.</p><p class="coupling-note">Changing coupling explicitly resets both simulations with the same noise seed. No threat is present until you drop the hand. Movement comes from each fly's own neural decoder.</p><p id="coupling-identity" class="coupling-note"></p><details><summary>Registered results and limits</summary><div id="coupling-results"></div></details><p><a href="${repo}docs/preregistration-v2.md">Pre-registration</a> · <a href="${base}finding.png">H0 figure</a> · <a href="${repo}docs/findings-v2f.md">Findings and limitations</a></p></section>`;
  const canvas=host.querySelector<HTMLCanvasElement>('canvas')!,ctx=canvas.getContext('2d')!;
  const status=host.querySelector<HTMLElement>('#coupling-status')!,slider=host.querySelector<HTMLInputElement>('input')!;
  const worker=new Worker(new URL('./coupling-worker.ts',import.meta.url),{type:'module'});
  let runtime:any,brain:any,panels:any[]=[],speed=0,scale=.01,generation=0,closed=false,frameCount=0,begin=performance.now(),recording=false;
  let positions:number[][]=[],staticLayer:HTMLCanvasElement;
  const updateScale=(s:number)=>{scale=s;generation++;panels=[];slider.value=String(runtime.grid.indexOf(s));host.querySelector('output')!.textContent=String(s);status.textContent='Resetting both neural states…';worker.postMessage({kind:'scale',s,generation});};
  const draw=(c:CanvasRenderingContext2D,width=1000,height=650)=>{
    c.save();c.scale(width/1000,height/650);c.fillStyle='#f6edd9';c.fillRect(0,0,1000,650);
    for(let index=0;index<2;index++){
      const x=20+index*500,p=panels[index];c.fillStyle='#183c31';c.font='bold 30px Georgia';c.fillText(index?'Scrambled':'Measured',x+12,40);
      c.fillStyle='#172f29';c.fillRect(x,60,460,340);
      if(staticLayer)c.drawImage(staticLayer,x,60);
      if(p){
        // Only observed nonzero counts add heat to the cached static map.
        for(let i=0;i<p.counts.length;i++)if(p.counts[i]){
          const rate=p.counts[i]/p.seconds;const [px,py]=positions[i];
          c.globalAlpha=Math.min(1,rate/100);c.fillStyle='#ffd16c';c.fillRect(x+px-2,60+py-2,4,4);
        }
        c.globalAlpha=1;c.fillStyle='#183c31';c.font='bold 30px monospace';c.fillText(p.rate.toFixed(1)+' Hz',x+12,441);
        c.fillStyle='#c9cfb8';c.fillRect(x+12,456,430,15);c.fillStyle=p.rate>=50?'#bc532c':'#28634c';c.fillRect(x+12,456,Math.min(430,p.rate/200*430),15);
        c.strokeStyle='#183c31';c.beginPath();c.moveTo(x+12+430*.25,450);c.lineTo(x+12+430*.25,480);c.stroke();c.font='13px monospace';c.fillText('50 Hz',x+12+430*.25,496);
        c.fillStyle='#dfba7d';c.fillRect(x+12,516,430,108);
        const bx=x+227+p.body.x/6*200,by=570-p.body.y/6*42;
        if(p.strike&&p.tick<=p.strike.impact_tick){
          const progress=(p.tick-p.strike.start_tick)/(p.strike.impact_tick-p.strike.start_tick);
          c.fillStyle='#8e4b32';c.fillRect(x+227+p.strike.aim_x/6*200-12,540-p.strike.aim_y/6*42-20*(1-progress),24,26);
        }
        c.save();c.translate(bx,by);c.rotate(-Math.atan2(p.body.heading_y,p.body.heading_x));c.fillStyle='#fff8df';c.beginPath();c.ellipse(-3,-8,12,p.air?8:4,-.4,0,Math.PI*2);c.ellipse(-3,8,12,p.air?8:4,.4,0,Math.PI*2);c.fill();c.fillStyle='#183c31';c.beginPath();c.ellipse(0,0,10,5,0,0,Math.PI*2);c.fill();c.restore();
      }
    }
    c.restore();
  };
  let lastPaint=-1;
  function animate(){if(closed)return;frameCount++;const tick=panels[0]?.tick??0;if(tick!==lastPaint){draw(ctx);lastPaint=tick;}requestAnimationFrame(animate);}
  worker.onmessage=e=>{
    const m=e.data;if(m.kind==='error'){status.textContent=m.error;throw new Error(m.error);}
    if(m.kind==='frame'&&m.generation===generation){panels=m.panels;speed=m.speed;status.textContent=`s = ${scale} · ${speed.toFixed(2)}× actual simulation speed · ${(panels[0].tick*.0005).toFixed(2)} simulated seconds`+ (panels.some(p=>p.strike)?' · hand stimulus active':' · no threat');}
    if(m.kind==='ended')status.textContent='Two simulated minutes recorded. Move the slider to start a new comparison.';
  };
  host.querySelector<HTMLButtonElement>('#coupling-close')!.onclick=()=>{closed=true;worker.terminate();host.hidden=true;onClose();};
  host.querySelector<HTMLButtonElement>('#coupling-drop')!.onclick=()=>worker.postMessage({kind:'drop'});
  slider.oninput=()=>updateScale(runtime.grid[Number(slider.value)]);
  try{
    const [rt,b,buffer,targets,profile]=await Promise.all([fetch(base+'data/coupling/runtime.json').then(r=>r.json()),fetch(base+'data/coupling/brain.json').then(r=>r.json()),fetchGraph(base+'data/coupling/circuit.flygraph.gz'),fetch(base+'data/coupling/targets.json.gz').then(r=>new Response(r.body!.pipeThrough(new DecompressionStream('gzip'))).json()),fetch(base+'data/game.json').then(r=>r.json())]);
    runtime=rt;brain=b;positions=brain.nodes.map((n:any,i:number)=>n.position?[15+n.position[0]*365,30+n.position[1]*285]:[405+(i%5)*9,35+(Math.floor(i/5)%35)*8]);
    staticLayer=document.createElement('canvas');staticLayer.width=460;staticLayer.height=340;const bg=staticLayer.getContext('2d')!;bg.fillStyle='#172f29';bg.fillRect(0,0,460,340);bg.fillStyle='#496154';for(const [x,y] of positions)bg.fillRect(x,y,1,1);bg.fillStyle='#bcccb8';bg.font='10px monospace';bg.fillText('RELATIVE x/z',15,17);bg.fillText('NO SOMA',400,17);
    host.querySelector('#coupling-identity')!.textContent=`${brain.nodes.length.toLocaleString('en-US')} neurons in each simulation. N-SIGN seed ${runtime.null_selection.seed}; ${runtime.null_selection.rule} Kappa ${runtime.parameters.kappa}; isolated noise target ${runtime.parameters.nu0_hz} Hz. Uniform LIF model with assumed transmitter signs. The strength-preserving comparisons did not replicate; see registered results below.`;
    renderResults(host.querySelector<HTMLElement>('#coupling-results')!,await loadResults(base));
    worker.postMessage({kind:'init',buffer,runtime,targets,profile,s:scale,generation});draw(ctx);requestAnimationFrame(animate);
    const button=host.querySelector<HTMLButtonElement>('#coupling-clip')!;
    button.disabled=!('MediaRecorder' in window)||!('captureStream' in canvas);
    button.onclick=async()=>{
      if(recording)return;const mime=['video/webm;codecs=vp9','video/webm','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t));if(!mime)return;
      recording=true;button.disabled=true;slider.disabled=true;
      const portrait=document.createElement('canvas');portrait.width=720;portrait.height=1280;const g=portrait.getContext('2d')!,stream=portrait.captureStream(25),recorder=new MediaRecorder(stream,{mimeType:mime});const chunks:Blob[]=[];
      recorder.ondataavailable=e=>chunks.push(e.data);
      recorder.onstop=()=>{const blob=new Blob(chunks,{type:mime}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='measured-vs-scrambled.'+(mime.includes('mp4')?'mp4':'webm');a.click();setTimeout(()=>URL.revokeObjectURL(a.href),10000);stream.getTracks().forEach(t=>t.stop());recording=false;button.disabled=false;slider.disabled=false;};
      const paint=()=>{g.fillStyle='#f6edd9';g.fillRect(0,0,720,1280);g.fillStyle='#183c31';g.font='bold 43px Georgia';g.fillText('Measured vs Scrambled',28,70);g.font='23px monospace';g.fillText(`Coupling ${scale} · ${speed.toFixed(2)}× speed`,28,117);
        const capture=document.createElement('canvas');capture.width=1000;capture.height=650;draw(capture.getContext('2d')!);g.fillStyle='#f6edd9';g.fillRect(0,0,720,1280);g.fillStyle='#183c31';g.font='bold 43px Georgia';g.fillText('Measured vs Scrambled',28,70);g.font='23px monospace';g.fillText(`Coupling ${scale} · ${speed.toFixed(2)}× speed`,28,117);g.drawImage(capture,0,180,720,780);g.font='25px Georgia';['Same neurons. Same number of excitatory','and inhibitory inputs and outputs per neuron.','Partners shuffled.'].forEach((line,i)=>g.fillText(line,28,1040+i*38));g.font='17px monospace';g.fillText('A model result. Measured neural activity.',28,1200);};
      updateScale(.01);paint();recorder.start();const timer=setInterval(paint,40);
      for(const s of [.01,.02,.03,.039,.05,.06]){updateScale(s);await new Promise(r=>setTimeout(r,1000));}
      clearInterval(timer);recorder.stop();
    };
    (window as any).couplingTest={ready:()=>panels.length===2,setScale:updateScale,state:()=>({scale,panels:panels.map(p=>({rate:p.rate,tick:p.tick,counts:Array.from(p.counts),seconds:p.seconds})),speed,fps:frameCount/((performance.now()-begin)/1000)}),draw:()=>draw(ctx)};
  }catch(e){worker.terminate();status.textContent='Coupling data could not load: '+String(e);throw e;}
}
