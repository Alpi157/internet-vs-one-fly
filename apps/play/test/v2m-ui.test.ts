import assert from 'node:assert/strict';
import {BrainView,spikeAlpha} from '../src/brain-view.ts';
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
