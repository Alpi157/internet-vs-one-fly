import {RunnerV2} from '../../../packages/kernel-ts/src/runner.ts';
import {encodeHand} from '../../../packages/kernel-ts/src/encoding.ts';
import type {Strike} from '../../../packages/kernel-ts/src/encoding.ts';
import {decodeSpikes} from '../../../packages/kernel-ts/src/decoder.ts';
import {WalkingDrive} from './walking-drive.ts';

// The scientific RunnerV2 remains unchanged. This game adapter adds only current
// before the unchanged kernel and records the spikes used by the unchanged decoder.
export class GameRunner extends RunnerV2 {
    walking:WalkingDrive;
    ports:number[][];
    constructor(graph:any,config:any,environmentSeed:number,point:any){
        super(graph,config);this.walking=new WalkingDrive(environmentSeed,point);
        const byId=new Map(Array.from(graph.ids,(id:any,i)=>[Number(id),i] as [number,number]));
        this.ports=[5,2,3,4].map(g=>config.groups[g].map((id:number)=>byId.get(id)));
        const forbidden=new Set([...config.groups.slice(0,2).flat().map((id:number)=>byId.get(id)),...Object.values(config.visual).flat()]);
        if(this.ports.flat().some(i=>i===undefined||forbidden.has(i)))throw Error('Walking ports overlap sensory or escape ports');
    }
    reset(){super.reset();this.walking.reset();}
    step(strike:Strike){
        const applied=this.held;
        const encoded=encodeHand(strike,this.body.x,this.body.y,this.body.heading_x,this.body.heading_y,this.config.gain);
        const walking=new Float64Array(this.state.graph.header.N), currents=this.walking.next();
        this.ports.forEach((indices,g)=>{for(const i of indices)walking[i]=currents[g];});
        const drive=walking.slice();
        for(const [name,indices] of Object.entries(this.config.visual))for(const i of indices)drive[i]+=encoded[name.toLowerCase()+'_drive'];
        const output=new Set(this.config.groups.flat()),spikes:number[]=[],recordedSpikes:{tick:number;indices:number[]}[]=[];
        for(let tick=0;tick<20;tick++){
            const afterImpact=strike.active&&strike.downward_speed_per_ms>0&&strike.downward_speed_per_ms*(strike.elapsed_ms+tick*.5)>=8;
            this.state.step(afterImpact?walking:drive);
            const indices=this.state.firedIndices.slice();
            for(const i of indices){const id=Number(this.state.graph.ids[i]);if(output.has(id))spikes.push(id);}
            if(indices.length)recordedSpikes.push({tick:this.state.tick,indices});
        }
        const p=this.config.decoder,result=decodeSpikes(spikes,this.rates,this.config.groups,p.decay,p.forward_gain,p.turn_gain,p.minimum_speed,p.maximum_speed,p.maximum_turn_rate);
        this.rates=result.rates;this.held=this.config.output_clamp?[false,0,0]:result.command;
        const onset=this.held[0]&&!this.previousEscape;this.previousEscape=this.held[0];
        return {applied,command:this.held,onset,encoded,recordedSpikes};
    }
}
