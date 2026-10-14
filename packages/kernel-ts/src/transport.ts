// Lossless transport only. Reconstruct the existing FLYWEB1 bytes before execution.
export async function fetchGraph(url:string):Promise<ArrayBuffer> {
    const response=await fetch(url);if(!response.ok)throw new Error('Graph download failed');
    const decompressed=await new Response(response.body!.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
    return unpackGraph(decompressed);
}
export function unpackGraph(raw:ArrayBuffer):ArrayBuffer {
    const bytes=new Uint8Array(raw),view=new DataView(raw);
    if(new TextDecoder().decode(bytes.subarray(0,8))!=='FLYPACK1')throw new Error('Packed graph magic');
    const size=view.getUint32(8,true),headerBytes=bytes.slice(12,12+size),header=JSON.parse(new TextDecoder().decode(headerBytes));
    let cursor=12+size;
    const take=()=>{let n=0,shift=0;for(let i=0;i<8;i++){if(cursor>=bytes.length)throw new Error('Truncated packed graph');const b=bytes[cursor++];n+=(b&127)*2**shift;if(!(b&128))return n;shift+=7;}throw new Error('Invalid varint');};
    const prefix=12+size,payload=prefix+(8-prefix%8)%8;
    const length=Math.max(...Object.values(header.sections).map((s:any)=>s.byte_offset+s.byte_length));
    const output=new ArrayBuffer(payload+length),out=new Uint8Array(output),v=new DataView(output);
    out.set(new TextEncoder().encode('FLYWEB1\0'));v.setUint32(8,size,true);out.set(headerBytes,12);
    const start=(name:string)=>payload+header.sections[name].byte_offset;
    out.set(bytes.subarray(cursor,cursor+header.N*8),start('ids'));cursor+=header.N*8;
    const offsets:number[]=[0];for(let i=0;i<header.N;i++)offsets.push(offsets[i]+take());
    if(offsets.at(-1)!==header.E)throw new Error('Packed edge count');
    offsets.forEach((value,i)=>v.setBigInt64(start('offsets')+i*8,BigInt(value),true));
    for(let i=0;i<header.N;i++){let target=0;for(let e=offsets[i];e<offsets[i+1];e++){target+=take();if(target>=header.N)throw new Error('Target outside graph');v.setInt32(start('targets')+e*4,target,true);}}
    const counts:number[]=[];for(let e=0;e<header.E;e++){const count=take();counts.push(count);v.setBigUint64(start('counts')+e*8,BigInt(count),true);}
    for(let i=0;i<header.N;i++){const sign=bytes[cursor++]-1;if(![-1,0,1].includes(sign))throw new Error('Invalid sign');for(let e=offsets[i];e<offsets[i+1];e++)v.setFloat64(start('weights')+e*8,counts[e]*sign,true);}
    if(cursor!==bytes.length)throw new Error('Trailing packed graph bytes');
    return output;
}
