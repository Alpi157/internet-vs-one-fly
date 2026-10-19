import {Game} from './game.ts';
import {readGraph} from '../../../packages/kernel-ts/src/kernel.ts';
let games:Game[]=[], queues:Uint32Array[][]=[[],[]], sums:Uint32Array[]=[], paused=true;
let started=0, steps=0, timer:ReturnType<typeof setTimeout>, runtime:any, profile:any, original:ArrayBuffer, targets:number[];
let generation=0;
function init(scale:number){
  clearTimeout(timer);const config=structuredClone(runtime);config.config.model.runtime_synaptic_scale=scale;
  const scrambled=original.slice(0);readGraph(scrambled).targets.set(targets);
  const labProfile={...profile,walking_drive:undefined,round_ms:120000,max_strikes:1000,recording_max_intervals:12000};
  games=[new Game(original,config,labProfile,2027101401,8128),new Game(scrambled,{...config,graph_identity:runtime.lab_identity},labProfile,2027101401,8128)];
  queues=[[],[]];sums=games.map(g=>new Uint32Array(g.runner.state.graph.header.N));steps=0;started=performance.now();paused=false;
  self.postMessage({kind:'ready',s:scale,generation});tick();
}
function tick(){
  if(paused)return;
  const begin=performance.now();
  try{
    const panels=games.map((g,index)=>{
      const frame=g.step(),counts=new Uint32Array(sums[index].length);
      for(const event of frame.spikes)for(const i of event.indices)counts[i]++;
      queues[index].push(counts);for(let i=0;i<counts.length;i++)sums[index][i]+=counts[i];
      if(queues[index].length>25){const old=queues[index].shift()!;for(let i=0;i<old.length;i++)sums[index][i]-=old[i];}
      // Only the last second of event history is retained. Heat is observed counts
      // over the last 250 simulated ms; no neural interpolation or invented flash.
      if(g.frames.length>100)g.frames.shift();
      const seconds=queues[index].length*.01;
      return {tick:g.tick,body:frame.body,air:frame.air,strike:frame.strike,impact:frame.impact,
        frames:g.frames.slice(-5),counts:sums[index].slice(),seconds,rate:sums[index].reduce((a,b)=>a+b,0)/counts.length/seconds};
    });
    steps++;
    if(steps%5===0)self.postMessage({kind:'frame',panels,generation,speed:steps*.01/((performance.now()-started)/1000)});
    if(games.some(g=>g.done)){paused=true;self.postMessage({kind:'ended'});return;}
    timer=setTimeout(tick,Math.max(0,10-(performance.now()-begin)));
  }catch(e){paused=true;self.postMessage({kind:'error',error:String(e)});}
}
self.onmessage=e=>{
  const m=e.data;
  if(m.kind==='init'){original=m.buffer;runtime=m.runtime;profile=m.profile;targets=m.targets;generation=m.generation;init(m.s);}
  if(m.kind==='scale'){generation=m.generation;init(m.s);}
  if(m.kind==='pause'){paused=true;clearTimeout(timer);}
  if(m.kind==='drop')for(const g of games)g.apply({tick:g.tick,x:g.runner.body.x,y:g.runner.body.y,hold_ms:250});
};
