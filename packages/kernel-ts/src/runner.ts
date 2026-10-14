import {KernelState,readGraph,concatBytes,sha256} from './kernel.ts';
import type {Model,Noise,WebGraph} from './kernel.ts';
import {encodeHand} from './encoding.ts';
import type {Strike} from './encoding.ts';
import {decodeSpikes} from './decoder.ts';
import {advanceBody} from './body.ts';
import type {Body} from './body.ts';
export type RunnerConfig={model:Model;noise:Noise;gain:number;groups:number[][];visual:Record<string,number[]>;decoder:any;body_enabled:boolean;output_clamp?:boolean};
export class RunnerV2 {
  state:KernelState;
  config:RunnerConfig;
  body:Body={x:0,y:0,heading_x:1,heading_y:0};
  rates=Array(6).fill(0);
  held:[boolean,number,number]=[false,0,0];
  previousEscape=false;
  constructor(graph:WebGraph,config:RunnerConfig){this.state=new KernelState(graph,config.model,config.noise);this.config=structuredClone(config);}
  reset(){this.state=new KernelState(this.state.graph,this.config.model,this.config.noise);this.body={x:0,y:0,heading_x:1,heading_y:0};this.rates=Array(6).fill(0);this.held=[false,0,0];this.previousEscape=false;}
  step(strike:Strike){
    const applied=this.held;
    const encoded=encodeHand(strike,this.body.x,this.body.y,this.body.heading_x,this.body.heading_y,this.config.gain);
    const drive=new Float64Array(this.state.graph.header.N);
    for(const [name,indices] of Object.entries(this.config.visual))for(const i of indices)drive[i]=encoded[name.toLowerCase()+'_drive'];
    const output=new Set(this.config.groups.flat());
    const spikes:number[]=[];
    const recordedSpikes:{tick:number;indices:number[]}[]=[];
    const zero=new Float64Array(drive.length);
    for(let tick=0;tick<20;tick++) {
      const afterImpact=strike.active && strike.downward_speed_per_ms>0 && strike.downward_speed_per_ms*(strike.elapsed_ms+tick*.5)>=8;
      this.state.step(afterImpact?zero:drive);
      const indices=this.state.firedIndices.slice();
      for(const i of indices){const body=Number(this.state.graph.ids[i]);if(output.has(body))spikes.push(body);}
      if(indices.length)recordedSpikes.push({tick:this.state.tick,indices});
    }
    const p=this.config.decoder;
    const result=decodeSpikes(spikes,this.rates,this.config.groups,p.decay,p.forward_gain,p.turn_gain,p.minimum_speed,p.maximum_speed,p.maximum_turn_rate);
    if(this.config.body_enabled)this.body=advanceBody(this.body,applied[1],applied[2]);
    this.rates=result.rates;
    this.held=this.config.output_clamp ? [false,0,0]:result.command;
    const onset=this.held[0]&&!this.previousEscape;
    this.previousEscape=this.held[0];
    return {applied,command:this.held,onset,encoded,recordedSpikes};
  }
  async digest(){
    const floats=new Uint8Array(4*8+6*8+1+8+8+1);
    const view=new DataView(floats.buffer);
    const vals=[this.body.x,this.body.y,this.body.heading_x,this.body.heading_y,...this.rates];
    vals.forEach((v,i)=>view.setFloat64(i*8,v,true));
    view.setUint8(80,this.held[0]?1:0);view.setFloat64(81,this.held[1],true);view.setFloat64(89,this.held[2],true);view.setUint8(97,this.previousEscape?1:0);
    return sha256(concatBytes([new TextEncoder().encode('FlyBench v2c runner state v1\0'),this.state.neuralBytes(),floats]));
  }
}
export async function runCase(buffer:ArrayBuffer,log:any,digests=true){
  const runner=new RunnerV2(readGraph(buffer),log.config);
  const actual:string[]=[];
  const started=performance.now();
  for (const interval of log.intervals){runner.step(interval.strike);if(digests)actual.push(await runner.digest());}
  const wall=(performance.now()-started)/1000;
  return {digests:actual,wall_seconds:wall,wall_seconds_per_simulated_second:wall/(log.intervals.length*.01)};
}
