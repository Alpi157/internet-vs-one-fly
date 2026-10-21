import assert from 'node:assert/strict';
import {BrainView,spikeAlpha,brainBackingSize,BRAIN_PIXEL_BUDGET,activityPixels} from '../src/brain-view.ts';
import {load,newGame,runtime} from './owner-walking.ts';
// An independent sparse oracle checks the optimized display buffer against
// actual recorded spikes, including forward playback and backward scrubbing.
const display=load('apps/play/public/data/display-v1.json');
const view=Object.create(BrainView.prototype) as BrainView;
(view as any).display=display;(view as any).nodes=Array(runtime.counts.N);
const game=newGame(load('profiles/game-v2.9.json'),1,8128);
for(let i=0;i<150;i++)game.step();
game.apply({tick:game.tick,x:game.runner.body.x,y:game.runner.body.y,hold_ms:600});
while(game.strike)game.step();
for(const frame of game.frames){
 const last=new Map<number,number>(),cutoff=frame.tick+2*display.spike_decay_tau_ms*Math.log(display.spike_alpha_threshold);
 for(const f of game.frames)if(f.tick>=cutoff&&f.tick<=frame.tick)for(const event of f.spikes)if(event.tick<=frame.tick)for(const i of event.indices)last.set(i,Math.max(last.get(i)??-1,event.tick));
 const expected=[...last].sort((a,b)=>a[0]-b[0]).map(([i,t])=>[i,spikeAlpha(frame.tick,t,display.spike_decay_tau_ms)]);
 assert.deepEqual(view.activityAt(frame,game.frames),expected);
 assert.deepEqual(view.activityAt(frame,game.frames.slice().reverse()),expected);
}
console.log('PASS optimized display activity equals independent recorded-spike oracle at every frame, in either traversal order');

for(const [width,height] of [[1,1],[0,0],[210,340],[680,500],[1187,280],[2400,1200]])for(const dpr of [1,2,3]){
 const b=brainBackingSize(width,height,dpr);assert(b.width*b.height<=BRAIN_PIXEL_BUDGET);if(!b.capped){assert.equal(b.width,Math.max(1,Math.ceil(width*dpr)));assert.equal(b.height,Math.max(1,Math.ceil(height*dpr)));}else assert(Math.abs(b.width/b.height-width/height)<.03);
}
const decision=load('decisions/D-V2M-SELECT-01.json');assert.equal(decision.selected_preset,'T0');assert.equal(decision.mechanics_change,'NONE; exact current production profile retained');assert.equal(decision.takeoff_speed_units_per_ms,load('profiles/game-v2.9.json').takeoff_speed);
if(process.argv.includes('--a02-preservation')||process.argv.includes('--a03-preservation')){
 const a03=process.argv.includes('--a03-preservation');
 const {readFileSync,writeFileSync}=await import('node:fs'),{createHash}=await import('node:crypto'),{execFileSync}=await import('node:child_process');
 const hash=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
 const {invariants}=await import('./v2m.ts');invariants();
 for(const [p,r] of Object.entries(load('evidence/V2M/a02/prior-a01-preservation.json').files) as any[])assert.equal(hash(p),r.sha256,p);
 for(const [p,h] of Object.entries(decision.references_sha256))assert.equal(hash(p),h,p);
 assert.equal(hash('docs/media/game-hero.gif'),decision.hero_sha256);
 assert.equal(load('evidence/V2M/acceptance/command-results.json').status,'PASS');
 const code_sha=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
 if(a03)for(const [p,r] of Object.entries(load('evidence/V2M/a03/prior-a02-preservation.json').files) as any[])assert.equal(hash(p),r.sha256,p);
 writeFileSync('evidence/V2M/'+(a03?'a03':'a02')+'/preservation-check.json',JSON.stringify({status:'PASS',code_sha,decision,prior_a01_files:Object.keys(load('evidence/V2M/a02/prior-a01-preservation.json').files).length},null,2)+'\n');
 console.log('PASS owner T0, production v2.9, a01 evidence/media and frozen science identities');
}
console.log('PASS device-pixel backing size boundaries, aspect and declared pixel cap');

const lines=new Float32Array([0,0,0,0,2,0,0,0,0,0,0,0,2,0,0,0]);
assert.deepEqual(Array.from(activityPixels(lines,[[0,4]],4,4,4,4,1,[0,0],[[0,0],[0,0]],true)),[.5,.5,0,2,1.5,.5,0,2,2.5,.5,0,2]);
const cord=new Float32Array([0,0,0,1,2,0,0,1]);assert.equal(activityPixels(cord,[[0,2]],4,4,4,4,1,[0,0],[[0,0],[0,0]],true).length,0);
assert.equal(activityPixels(cord,[[0,2]],4,4,4,4,1,[0,0],[[0,0],[0,0]],false).length,12);
console.log('PASS cached arbor pixels preserve per-neuron segment coverage and brain/cord scope');

const twoNeurons=new Float32Array([0,0,0,0,2,0,0,0,0,0,1,0,2,0,1,0]);
const channels=activityPixels(twoNeurons,[[0,2],[2,2]],4,4,4,4,1,[0,0],[[0,0],[0,0]],true);
assert.deepEqual(Array.from(channels).filter((_,i)=>i%4===2),[0,0,0,1,1,1]);
assert(Array.from(channels).filter((_,i)=>i%4===3).every(n=>n===1));
