const assert=require('node:assert/strict');
const test=require('node:test');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const {create}=require('./image_viewport.js');

test('pinch keeps the image coordinate under the cursor fixed',()=>{
 const v=create();v.setImage(1000,600,'a');v.zoomAt(2,[300,200]);
 assert.deepEqual(v.state().box,[150,100,500,300]);
 v.zoomAt(.5,[300,200]);assert.deepEqual(v.state().box,[0,0,1000,600]);
});
test('pan and zoom stay within image bounds, including extreme and invalid inputs',()=>{
 const v=create();v.setImage(1200,400,'a');v.zoomAt(1000);assert.equal(v.state().scale,32);
 v.pan(1e9,-1e9);assert.deepEqual(v.state().box,[1162.5,0,37.5,12.5]);
 const before=v.state();for(const f of [NaN,Infinity,-1,0])v.zoomAt(f);v.pan(NaN,2);assert.deepEqual(v.state(),before);
 v.zoomAt(.0001);assert.deepEqual(v.state().box,[0,0,1200,400]);
});
test('channel redraws preserve zoom; a new FOV resets the viewport',()=>{
 const v=create();v.setImage(900,600,'field1');v.zoomAt(3);const zoomed=v.state();
 v.setImage(900,600,'field1');assert.deepEqual(v.state(),zoomed);
 v.setImage(900,600,'field2');assert.deepEqual(v.state().box,[0,0,900,600]);
});
test('object focus preserves aspect ratio and never pans beyond an edge',()=>{
 const v=create();v.setImage(1200,400,'a');v.focus([1180,380,1200,400]);
 const [x,y,w,h]=v.state().box;assert.ok(x>=0&&y>=0&&x+w<=1200&&y+h<=400);assert.equal(w/h,3);
 assert.ok(x<=1180&&y<=380&&x+w>=1200&&y+h>=400);v.fit();assert.equal(v.state().scale,1);
});

function mounted(){
 const events={},messages={},parent={},classes=new Map();let capture=false;
 const svg={clientHeight:500,attrs:{},classList:{toggle:(k,v)=>classes.set(k,v)},
  setAttribute(k,v){this.attrs[k]=v;},getBoundingClientRect:()=>({left:20,top:30,right:1020,bottom:530}),
  getScreenCTM:()=>({inverse:()=>({})}),createSVGPoint:()=>({x:0,y:0,matrixTransform(){const b=api.state().box;return {x:b[0]+(this.x-20)/1000*b[2],y:b[1]+(this.y-30)/500*b[3]};}}),
  addEventListener:(n,f)=>events[n]=f,setPointerCapture(){capture=true;},hasPointerCapture:()=>capture,releasePointerCapture(){capture=false;}};
 const context={parent,addEventListener:(n,f)=>messages[n]=f};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'image_viewport.js'),'utf8'),context);
 const api=context.LabImageViewport.attach(svg,()=>{});api.setImage(1000,500,'a');
 const event=(extra={})=>({clientX:520,clientY:280,deltaX:0,deltaY:0,deltaMode:0,button:0,pointerId:1,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...extra});
 return {api,svg,events,messages,parent,event};
}
test('native gesture routing accepts only parent events over the image',()=>{
 const h=mounted();const data={type:'viewer-native-gesture',factor:2,x:520,y:280};
 h.messages.message({source:{},data});assert.equal(h.api.state().scale,1);
 h.messages.message({source:h.parent,data:{...data,x:5}});assert.equal(h.api.state().scale,1);
 h.messages.message({source:h.parent,data});assert.equal(h.api.state().scale,2);
 assert.equal(h.svg.attrs.viewBox,'250 125 500 250');
});
test('ordinary scroll is preserved at fit; browser pinch and zoomed pan operate on the image',()=>{
 const h=mounted(),normal=h.event({deltaY:30});h.events.wheel(normal);assert.equal(normal.prevented,undefined);
 const pinch=h.event({deltaY:-100,ctrlKey:true});h.events.wheel(pinch);assert.ok(h.api.state().scale>1);assert.equal(pinch.prevented,true);
 const before=h.api.state().box[1],pan=h.event({deltaY:20});h.events.wheel(pan);assert.ok(h.api.state().box[1]>before);assert.equal(pan.prevented,true);
 const start=h.event();h.events.gesturestart(start);h.events.gesturechange(h.event({scale:1.2}));assert.equal(start.prevented,true);
});
test('dragging suppresses a subsequent object click, including click-to-exclude mode',()=>{
 const h=mounted();h.api.zoomAt(3);h.events.pointerdown(h.event());
 h.events.pointermove(h.event({clientX:600}));h.events.pointerup(h.event({clientX:600}));
 assert.equal(h.api.suppressClick(),true);const click=h.event();h.events.click(click);assert.equal(click.stopped,true);
});
test('keyboard alternatives zoom, pan, and reset',()=>{
 const h=mounted();h.events.keydown(h.event({key:'+'}));assert.equal(h.api.state().scale,1.25);
 const before=h.api.state().box[0];h.events.keydown(h.event({key:'ArrowRight'}));assert.ok(h.api.state().box[0]>before);
 h.events.keydown(h.event({key:'0'}));assert.equal(h.api.state().scale,1);
});
