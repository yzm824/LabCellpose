/* Image-space navigation only. Never changes image pixels, masks, or measurements. */
(function(root){
'use strict';
const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
function create(onChange=()=>{}){
 let width=1,height=1,key=null,box=[0,0,1,1];
 const state=()=>({box:[...box],scale:width/box[2],width,height});
 function apply(next){
  const scale=clamp(width/next[2],1,32),w=width/scale,h=height/scale;
  box=[clamp(next[0],0,width-w),clamp(next[1],0,height-h),w,h];onChange(state());
 }
 function fit(){apply([0,0,width,height]);}
 function setImage(w,h,id){
  if(!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0)throw Error('Invalid image dimensions');
  if(id!==key||width!==w||height!==h){width=w;height=h;key=id;fit();}
 }
 function zoomAt(factor,point=[box[0]+box[2]/2,box[1]+box[3]/2]){
  if(!Number.isFinite(factor)||factor<=0||!point.every(Number.isFinite))return;
  const scale=clamp(width/box[2]*factor,1,32),w=width/scale,h=height/scale;
  const u=clamp((point[0]-box[0])/box[2],0,1),v=clamp((point[1]-box[1])/box[3],0,1);
  apply([point[0]-u*w,point[1]-v*h,w,h]);
 }
 function pan(dx,dy){if(Number.isFinite(dx)&&Number.isFinite(dy))apply([box[0]+dx,box[1]+dy,box[2],box[3]]);}
 function focus(bbox){
  if(!bbox||bbox.length!==4||!bbox.every(Number.isFinite))return;
  const[x0,y0,x1,y1]=bbox,scale=clamp(Math.min(width/(x1-x0+64),height/(y1-y0+64)),1,32);
  apply([(x0+x1-width/scale)/2,(y0+y1-height/scale)/2,width/scale,height/scale]);
 }
 return {state,setImage,fit,zoomAt,pan,focus};
}
function attach(svg,onChange){
 const viewport=create(state=>{svg.setAttribute('viewBox',state.box.join(' '));svg.classList.toggle('is-zoomed',state.scale>1.001);onChange(state);});
 let drag=null,suppressUntil=0,gestureScale=1;
 const inside=(x,y)=>{const r=svg.getBoundingClientRect();return x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom;};
 function point(x,y){const matrix=svg.getScreenCTM();if(!matrix)return null;const p=svg.createSVGPoint();p.x=x;p.y=y;const q=p.matrixTransform(matrix.inverse());return [q.x,q.y];}
 function zoom(factor,x,y){if(!inside(x,y))return false;const p=point(x,y);if(!p)return false;viewport.zoomAt(factor,p);return true;}
 svg.addEventListener('wheel',event=>{
  const unit=event.deltaMode===1?16:event.deltaMode===2?svg.clientHeight:1;
  if(event.ctrlKey){if(zoom(Math.exp(-clamp(event.deltaY*unit,-400,400)*.008),event.clientX,event.clientY))event.preventDefault();}
  else if(viewport.state().scale>1.001){
   const p=point(event.clientX,event.clientY),q=point(event.clientX+event.deltaX*unit,event.clientY+event.deltaY*unit);
   if(p&&q){event.preventDefault();viewport.pan(q[0]-p[0],q[1]-p[1]);}
  }
 },{passive:false});
 svg.addEventListener('gesturestart',e=>{gestureScale=1;e.preventDefault();},{passive:false});
 svg.addEventListener('gesturechange',e=>{if(Number.isFinite(e.scale)&&e.scale>0){zoom(e.scale/gestureScale,e.clientX,e.clientY);gestureScale=e.scale;}e.preventDefault();},{passive:false});
 svg.addEventListener('gestureend',e=>{gestureScale=1;e.preventDefault();},{passive:false});
 addEventListener('message',e=>{
  const m=e.data;if(e.source!==parent||m?.type!=='viewer-native-gesture'||!Number.isFinite(m.x)||!Number.isFinite(m.y)||!Number.isFinite(m.factor))return;
  zoom(m.factor,m.x,m.y);
 });
 svg.addEventListener('pointerdown',e=>{if(e.button!==0||viewport.state().scale<=1.001)return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,moved:false};});
 svg.addEventListener('pointermove',e=>{
  if(!drag||drag.id!==e.pointerId)return;
  const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
  if(!drag.moved&&Math.hypot(dx,dy)<4)return;
  if(!drag.moved){drag.moved=true;svg.setPointerCapture(e.pointerId);}
  const p=point(drag.x,drag.y),q=point(e.clientX,e.clientY);
  if(p&&q)viewport.pan(p[0]-q[0],p[1]-q[1]);
  drag.x=e.clientX;drag.y=e.clientY;e.preventDefault();
 });
 const end=e=>{if(drag?.id===e.pointerId){if(drag.moved)suppressUntil=Date.now()+300;if(svg.hasPointerCapture(e.pointerId))svg.releasePointerCapture(e.pointerId);drag=null;}};
 svg.addEventListener('pointerup',end);svg.addEventListener('pointercancel',end);
 svg.addEventListener('click',e=>{if(Date.now()<suppressUntil){e.preventDefault();e.stopImmediatePropagation();}},true);
 svg.addEventListener('keydown',e=>{
  if(e.key==='+'||e.key==='=')viewport.zoomAt(1.25);
  else if(e.key==='-')viewport.zoomAt(.8);
  else if(e.key==='0'||e.key==='Escape')viewport.fit();
  else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){
   const s=viewport.state();viewport.pan(e.key==='ArrowLeft'?-s.box[2]*.1:e.key==='ArrowRight'?s.box[2]*.1:0,e.key==='ArrowUp'?-s.box[3]*.1:e.key==='ArrowDown'?s.box[3]*.1:0);
  }else return;e.preventDefault();
 });
 return {...viewport,suppressClick:()=>Date.now()<suppressUntil};
}
const api={create,attach};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LabImageViewport=api;
})(globalThis);
