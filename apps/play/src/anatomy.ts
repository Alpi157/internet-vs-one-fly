/** FLYARB02: shared tree vertices with lossless parent-relative quantization. */
export interface ArborNeuron {
  bodyId: bigint; firstSegment: number; segmentCount: number;
  soma: [number,number]|null; missing: boolean;
}
export interface Arbors {
  bbox: number[]; step: number[]; neurons: ArborNeuron[];
  parents: Int32Array; quantized: Uint16Array; bufferBytes: number; allocatedArrayBytes:number;
  point(index:number):[number,number];
}
export function decodeArbors(buffer:ArrayBuffer):Arbors {
  const d=new DataView(buffer);
  if(d.byteLength<56||new TextDecoder().decode(new Uint8Array(buffer,0,8))!=='FLYARB02')throw new Error('Invalid arbor magic/header');
  const n=d.getUint32(8,true),s=d.getUint32(12,true),p=d.getUint32(16,true),base=56+n*24;
  if(s!==p||d.getUint32(20,true)!==0||base+p*8!==d.byteLength)throw new Error('Invalid arbor length/header');
  const bbox=Array.from({length:4},(_,i)=>d.getFloat64(24+i*8,true));
  const step=[(bbox[2]-bbox[0])/65535,(bbox[3]-bbox[1])/65535];
  if(!bbox.every(Number.isFinite)||!step.every(v=>v>0))throw new Error('Invalid arbor bounds');
  const parents=new Int32Array(p),quantized=new Uint16Array(p*2);
  let expected=0;const neurons:ArborNeuron[]=[];
  for(let i=0;i<n;i++){
    const offset=56+i*24,first=d.getUint32(offset+8,true),count=d.getUint32(offset+12,true),flags=d.getUint32(offset+20,true);
    if(first!==expected||flags&~3||(flags&1&&count)||first+count>p)throw new Error('Invalid neuron index/missing flag');
    expected+=count;
    neurons.push({bodyId:d.getBigUint64(offset,true),firstSegment:first,segmentCount:count,missing:Boolean(flags&1),
      soma:flags&2?null:[bbox[0]+d.getUint16(offset+16,true)*step[0],bbox[1]+d.getUint16(offset+18,true)*step[1]]});
    for(let j=first;j<first+count;j++){
      const delta=d.getUint32(base+j*4,true),parent=delta?j-delta:-1;
      if(parent!==-1&&(parent<first||parent>=j))throw new Error('Parent outside neuron or not topological');
      parents[j]=parent;
      quantized[j*2]=(d.getUint16(base+p*4+j*2,true)+(parent>=0?quantized[parent*2]:0))&65535;
      quantized[j*2+1]=(d.getUint16(base+p*6+j*2,true)+(parent>=0?quantized[parent*2+1]:0))&65535;
    }
  }
  if(expected!==p)throw new Error('Neuron index does not cover segments');
  return {bbox,step,neurons,parents,quantized,bufferBytes:buffer.byteLength,allocatedArrayBytes:parents.byteLength+quantized.byteLength,
    point(index:number){if(!Number.isInteger(index)||index<0||index>=p)throw new Error('Arbor point index');return [bbox[0]+quantized[index*2]*step[0],bbox[1]+quantized[index*2+1]*step[1]];}};
}
