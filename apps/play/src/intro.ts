/** First-visit explanation. Images are snapshots of recorded hero frames. */
export function createIntro(base:string,pause:()=>void,resume:()=>void){
 const dialog=document.createElement('dialog');dialog.id='first-visit';dialog.setAttribute('aria-labelledby','intro-title');
 dialog.innerHTML=`<div class="intro-heading"><span>Catch the fly</span><button id="intro-skip">Skip</button></div><div id="intro-picture"></div><div id="intro-copy"></div><div class="intro-bottom"><div id="intro-dots" aria-hidden="true"></div><button class="primary" id="intro-next">Next</button></div><p id="intro-note"></p>`;
 document.body.append(dialog);
 let step=1,count=0,seenThisLoad=false,prior:HTMLElement|null=null;
 const $=(id:string)=>dialog.querySelector<HTMLElement>('#'+id)!;
 const render=()=>{
  const number=count.toLocaleString('en-US');
  $('intro-picture').innerHTML=step===2?`<div class="intro-hands"><div><i class="tap-symbol" aria-hidden="true"></i><h3>Tap</h3><b>Fast hand</b><p>Small and quick. Hard for it to react in time.</p></div><div><i class="hold-symbol" aria-hidden="true"></i><h3>Hold</h3><b>Big, slow hand</b><p>Easy to aim. But the fly has time to see it coming.</p></div></div>`:`<img src="${base}intro-brain.png" alt="Recorded BrainView of the ${number} simulated neurons, drawn with real MaleCNS skeletons">${step===1?'<p class="intro-image-caption">Real neuron shapes from the MaleCNS map of a male fruit fly.</p>':`<img class="intro-timeline" src="${base}intro-timeline.png" alt="Recorded three-track timeline: Your hand, Looming detectors and Escape neuron">`}`;
  const titles=['This fly has a brain','Try to swat it','Then look inside its head'];
  const body=[`<p>${number} neurons, connected as in a real fruit fly’s brain, run live in your browser.</p><p>Its escapes are not scripted. They come from those neurons.</p>`,`<p>Six hands per round. The fly walks, stops and turns, so aim where it will be.</p>`,`<p>After every hand, a replay shows the cells that saw your hand coming and the one that made it jump.</p><p>Every flash is a spike that happened in the simulation.</p>`];
  $('intro-copy').innerHTML=`<p class="intro-step">${step} of 3</p><h2 id="intro-title" tabindex="-1">${titles[step-1]}</h2>${body[step-1]}`;
  $('intro-dots').innerHTML=[1,2,3].map(i=>`<i class="${i===step?'selected':''}"></i>`).join('');
  $('intro-next').textContent=step===3?'Play':'Next';$('intro-note').textContent=step===3?'Reopen this anytime with the ? button.':'';
 };
 const close=()=>{seenThisLoad=true;try{localStorage.setItem('flybench.intro.v5','seen');}catch{}dialog.close();resume();prior?.focus();};
 const show=(card=1)=>{step=card;prior=document.activeElement as HTMLElement;pause();render();if(!dialog.open)dialog.showModal();$('intro-skip').focus();};
 $('intro-skip').onclick=close;$('intro-next').onclick=()=>{if(step===3)close();else{step++;render();$('intro-title').focus();}};
 dialog.oncancel=e=>{e.preventDefault();close();};
 dialog.onkeydown=e=>{if(e.key!=='Tab')return;const nodes=Array.from(dialog.querySelectorAll<HTMLElement>('button,a[href]')).filter(e=>e.checkVisibility());const first=nodes[0],last=nodes.at(-1)!;if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}};
 return {show,setCount:(n:number)=>{count=n;},maybeShow:()=>{let seen=seenThisLoad;try{seen ||= localStorage.getItem('flybench.intro.v5')==='seen';}catch{}if(!seen)show();},close};
}
