// This entire module is reachable only through main.ts's import.meta.env.DEV guard.
// Vite removes the import and its profile data from the production module graph.
import selection from '../../../profiles/owner-takeoff-v2m-selected.json';
import {sha256} from '../../../packages/kernel-ts/src/kernel.ts';
export async function activateOwnerPreview(profile:any,runtime:any,resetSeeds:(neuralSeed:number,environmentSeed:number)=>void){
    const id=new URLSearchParams(location.search).get('preview');
    if(id===null)return {profile,runtime};
    const entry=(selection.presets as Record<string,any>)[id];
    if(!entry?.offered)throw Error(`Owner preview ${id} is not offered: ${entry?.reason??'use T0, T1, T2 or T3'}`);
    if(new URLSearchParams(location.search).has('test'))(window as any).flyOwnerTest={resetSeeds};
    const effective=structuredClone(entry.profile);
    const hash=await sha256(new TextEncoder().encode(JSON.stringify(effective)));
    if(hash!==entry.profile_sha256)throw Error('Owner preview profile identity mismatch');
    const badge=document.createElement('p');badge.id='owner-preview-badge';badge.setAttribute('role','status');
    badge.textContent=`Preview ${id}: ${entry.name}`;
    badge.style.cssText='font-size:13px;line-height:1.4;color:#7fefaa;margin:0 8px;padding:4px 8px;border:1px solid #687369;border-radius:8px;max-width:200px;min-width:0;text-align:center';
    const stats=document.querySelector('.stats')!;stats.insertBefore(badge,stats.lastElementChild);
    const physics=document.createElement('p');physics.id='owner-preview-physics';
    physics.textContent=`Owner playtest: takeoff speed ${effective.takeoff_speed.toFixed(3)} units/ms. ${effective.physics_disclosure} Lab simulations have no walking drive.`;
    document.getElementById('walking-disclosure')!.after(physics);
    return {profile:effective,runtime:{...runtime,profile_hashes:{...runtime.profile_hashes,owner_playtest_profile:hash}}};
}
