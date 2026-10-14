import {readGraph} from '../../../packages/kernel-ts/src/kernel.ts';
export function openLab(panel:HTMLElement,onChange:(mode:string)=>Promise<void>){
    panel.hidden=!panel.hidden;
    if(panel.dataset.initialized)return;
    panel.dataset.initialized='true';
    panel.innerHTML='<h2>Lesion lab</h2><p>Each change resets the round and reruns the neural simulation. The activity meter reports recorded whole-circuit spikes per neuron per second over the last 10 ms.</p><label>Experiment <select id="lab-mode"><option value="real">Measured wiring</option><option value="LC4">LC4 lesion</option><option value="LPLC2">LPLC2 lesion</option><option value="giant-fiber">Giant-fiber lesion</option><option value="turning-DN">Turning-DN lesion</option><option value="scramble">Scrambled wiring</option></select></label><p>Scrambled wiring: fixed-parameter scramble, not calibrated. N-FULL seed 202710159999. Lesions silence their neurons, including incoming/outgoing edges and direct drive.</p>';
    panel.querySelector('select')!.onchange=async e=>{const select=e.target as HTMLSelectElement;select.disabled=true;try{await onChange(select.value);}finally{select.disabled=false;}};
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
