import {u32} from '../../../packages/kernel-ts/src/kernel.ts';

// Game-only input. This object receives a seed and declared parameters, never a
// runner, body, hand, callback or environment. All time is integer intervals.
export type DrivePoint = {forward:number;turn_sigma:number;walk_seconds:number;stop_seconds:number};
export function logUnit(x:number):number {
    let exponent=0;
    while(x<1){x*=2;exponent--;}
    const z=(x-1)/(x+1), square=z*z;
    let term=z,sum=z;
    for(let k=1;k<18;k++){term=term*square;sum=sum+term/(2*k+1);}
    return 2*sum+exponent*0.6931471805599453;
}
export class WalkingDrive {
    seed:number;point:DrivePoint;interval=0;counter=0;walk=false;remaining=0;turn=0;
    constructor(environmentSeed:number,point:DrivePoint){
        this.seed=u32(environmentSeed,97,0,0);this.point=structuredClone(point);
        if(!Object.values(point).every(v=>Number.isFinite(v)&&v>0))throw Error('Invalid walking drive point');
        this.reset();
    }
    uniform(){return (u32(this.seed,97,this.counter++,0)+.5)/4294967296;}
    dwell(){return Math.max(1,Math.ceil(-logUnit(this.uniform())*(this.walk?this.point.walk_seconds:this.point.stop_seconds)/.01));}
    normal(){
        for(;;){const x=2*this.uniform()-1,y=2*this.uniform()-1,s=x*x+y*y;
            if(s>0&&s<1)return x*Math.sqrt(-2*logUnit(s)/s);}
    }
    reset(){this.interval=0;this.counter=0;this.turn=0;this.walk=this.uniform()<this.point.walk_seconds/(this.point.walk_seconds+this.point.stop_seconds);this.remaining=this.dwell();}
    next():[number,number,number,number]{
        if(this.remaining===0){this.walk=!this.walk;this.remaining=this.dwell();}
        // Exact OU transition at 10 ms, tau=0.75 s. Constants are pinned in profile.
        this.turn=0.9867551618071957*this.turn+0.16221667807859647*this.point.turn_sigma*this.normal();
        this.remaining--;this.interval++;
        return this.walk?[this.point.forward,0,Math.max(0,this.turn),Math.max(0,-this.turn)]:[0,0,0,0];
    }
    snapshot(){return [this.seed,this.interval,this.counter,+this.walk,this.remaining,this.turn];}
}
