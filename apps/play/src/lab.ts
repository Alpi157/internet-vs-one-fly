import {readGraph} from '../../../packages/kernel-ts/src/kernel.ts';
export function openLab(panel:HTMLElement,onChange:(mode:string)=>Promise<void>,seed?:number){
    panel.hidden=false;
    panel.innerHTML=`<h2>Switch off a cell type, then play</h2><div class="lesion-options">${[['LC4','LC4 off','One looming detector'],['LPLC2','LPLC2 off','The other looming detector'],['giant-fiber','Escape neuron off','The giant fiber'],['turning-DN','Steering off','The turning neurons']].map(([value,label,note])=>`<button data-lesion="${value}"><b>${label}</b><span>${note}</span></button>`).join('')}</div><p>LC4 and LPLC2 detect looming. The escape neuron triggers the jump. Steering neurons turn the fly. Each starts a fresh round.</p><p>Restore the real wiring anytime from the game.</p><details><summary>More</summary><button data-lesion="scramble" id="full-shuffle">Uncalibrated full shuffle${seed===undefined?'':`, seed ${seed}`}</button><p>This N-FULL shuffle uses the game's fixed parameters. It is not a calibrated control.</p><p>Silencing removes incoming and outgoing connections and direct drive for the selected neurons. Each change resets the round.</p></details>`;
    if(seed===undefined)fetch(import.meta.env.BASE_URL+'data/runtime.json').then(r=>r.json()).then(r=>{panel.querySelector('#full-shuffle')!.textContent=`Uncalibrated full shuffle, seed ${r.lab_seed}`;});
    panel.querySelectorAll<HTMLButtonElement>('[data-lesion]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await onChange(b.dataset.lesion!);}finally{b.disabled=false;}});
}
export async function configureLab(mode:string,buffer:ArrayBuffer,runtime:any,base:string){
    const config=structuredClone(runtime);const copy=buffer.slice(0);const graph=readGraph(copy);
    if(mode==='scramble'){
        const response=await fetch(base+'data/lab-targets.json.gz');if(!response.ok)throw new Error('Scramble data unavailable');
        const targets=await new Response(response.body!.pipeThrough(new DecompressionStream('gzip'))).json();
        if(targets.length!==graph.targets.length)throw new Error('Scramble graph size mismatch');
        graph.targets.set(targets);config.graph_identity=runtime.lab_identity;
    }else if(mode!=='real'){
        const indices=mode==='LC4'||mode==='LPLC2'?Object.entries(config.config.visual).filter(([key])=>key.startsWith(mode+'_')).flatMap(([,value])=>value as number[]):Array.from(graph.ids).flatMap((body,i)=>{const groups=mode==='giant-fiber'?config.config.groups.slice(0,2):config.config.groups.slice(3,5);return groups.flat().includes(Number(body))?[i]:[];});
        const removed=new Set(indices);
        for(let source=0;source<graph.header.N;source++)for(let edge=Number(graph.offsets[source]);edge<Number(graph.offsets[source+1]);edge++)if(removed.has(source)||removed.has(graph.targets[edge]))graph.weights[edge]=0;
        for(const i of indices)config.config.noise.population_mask[i]=false;
        for(const key of Object.keys(config.config.visual))config.config.visual[key]=config.config.visual[key].filter((i:number)=>!removed.has(i));
    }
    // Graph objects are reconstructed by Game; repack mutated arrays into the ordinary format.
    // The loader returns a conventional web graph buffer for lab mutations.
    config.graph_identity+=':'+mode;config.profile_hashes={...config.profile_hashes,lab_mode:mode};
    return {buffer:copy,runtime:config,label:mode==='scramble'?'Fixed-parameter scramble, not calibrated':mode==='real'?runtime.status:mode+' lesion'};
}
