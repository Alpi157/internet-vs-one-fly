// Generated from committed frozen analysis tables by experiments/v2f_publish.py.
let cached:Promise<any>|undefined;
export function loadResults(base:string){
  return cached??=fetch(base+'results-v2f.json').then(r=>{if(!r.ok)throw new Error('Results data unavailable');return r.json();});
}
export function renderResults(host:HTMLElement,results:any){
  host.replaceChildren();
  for(const text of [results.original,results.combined,...results.summary,results.bin_note,results.mechanism,results.limitations]){
    const p=document.createElement('p');p.textContent=text;host.append(p);
  }
}
