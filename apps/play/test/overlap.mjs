// Generic visible text/control collision check. Only ancestor/owned-content
// relationships are excluded; there are no page/state/selector pair exemptions.
export async function overlaps(page){return page.evaluate(()=>{
 const boxes=[],clip=r=>({x:Math.max(0,r.left),y:Math.max(0,r.top),right:Math.min(innerWidth,r.right),bottom:Math.min(innerHeight,r.bottom)});
 const modal=document.querySelector('dialog[open]');
 const unclipped=e=>{for(let p=e;p;p=p.parentElement){const s=getComputedStyle(p),r=p.getBoundingClientRect();if((s.clip!=='auto'||s.clipPath!=='none'||s.overflow==='hidden')&&(r.width<=1||r.height<=1))return false;}return true;};
 const visible=e=>unclipped(e)&&(!modal||modal.contains(e))&&e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})&&!e.closest('[hidden]')&&!e.closest('dialog:not([open])');
 const add=(node,r,kind,label)=>{const b=clip(r);
  // Scroll containers clip their descendants, including a replay sheet's content.
  for(let p=node.parentElement;p;p=p.parentElement){const s=getComputedStyle(p),r=p.getBoundingClientRect();if(/auto|scroll|hidden|clip/.test(s.overflowX)){b.x=Math.max(b.x,r.left+p.clientLeft);b.right=Math.min(b.right,r.left+p.clientLeft+p.clientWidth);}if(/auto|scroll|hidden|clip/.test(s.overflowY)){b.y=Math.max(b.y,r.top+p.clientTop);b.bottom=Math.min(b.bottom,r.top+p.clientTop+p.clientHeight);}}
 if(b.right-b.x>1&&b.bottom-b.y>1)boxes.push({node,kind,label:label.slice(0,110),...b});};
 const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
 for(let n=walker.nextNode();n;n=walker.nextNode()){
  if(!n.textContent.trim()||!visible(n.parentElement)||n.parentElement.closest('script,style'))continue;
  const closed=n.parentElement.closest('details:not([open])');if(closed&&!closed.querySelector('summary')?.contains(n))continue;
  const range=document.createRange();range.selectNodeContents(n);for(const r of range.getClientRects())add(n,r,'text',n.textContent.trim());
 }
 for(const e of document.querySelectorAll('button,a,input,select,textarea,summary,[role="button"],[role="tab"],[tabindex]:not(canvas)'))if(visible(e))for(const r of e.getClientRects())add(e,r,'control',e.getAttribute('aria-label')||e.textContent.trim()||e.id||e.tagName);
 const collisions=[];
 for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){
  const a=boxes[i],b=boxes[j];if(a.node===b.node||a.node.contains(b.node)||b.node.contains(a.node))continue;
  const w=Math.min(a.right,b.right)-Math.max(a.x,b.x),h=Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y);
  if(w>.75&&h>.75)collisions.push({a:{kind:a.kind,label:a.label,x:a.x,y:a.y,right:a.right,bottom:a.bottom},b:{kind:b.kind,label:b.label,x:b.x,y:b.y,right:b.right,bottom:b.bottom},overlap:{width:w,height:h}});
 }
 return {boxes:boxes.length,collisions};
});}
