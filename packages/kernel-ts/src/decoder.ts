export function decodeSpikes(spikes: number[], prior:number[], groups:number[][], decay:number, forwardGain:number,turnGain:number,minSpeed:number,maxSpeed:number,maxTurn:number): {command:[boolean,number,number];rates:number[]} {
  const rates=groups.map((group,i)=>{
    if(!group.length)return 0;
    let count=0;for(const body of spikes)if(group.includes(body))count++;
    return decay*prior[i]+(1-decay)*count/group.length/.01;
  });
  const escape=spikes.some(v=>groups[0].includes(v)||groups[1].includes(v));
  let speed=forwardGain*(rates[5]-rates[2]);
  if(speed<minSpeed)speed=minSpeed;else if(speed>maxSpeed)speed=maxSpeed;
  let turn=turnGain*(rates[3]-rates[4]);
  if(turn < -maxTurn)turn=-maxTurn;else if(turn>maxTurn)turn=maxTurn;
  return {command:[escape,speed,turn],rates};
}
