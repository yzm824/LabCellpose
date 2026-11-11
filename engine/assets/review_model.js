/* Review workspace logic (3.0): conditions, blind labels, review flags, ordering, plot statistics and channel colours.
   Display and navigation only: nothing here changes a mask, a measurement or a QC decision. */
(function(root){
'use strict';
const Export=typeof module!=='undefined'&&module.exports?require('./export_table.js'):root.LabExport;

// Conditions are the folders that hold the images (the same rule as the image_folder export column), in first-appearance order.
function conditions(config,fieldIds){
 const names=Export.names(config||{}),groups=[],of=new Map();
 for(const id of fieldIds){
  const name=names.field(id,'image_folder')||'';of.set(id,name);
  let group=groups.find(g=>g.name===name);if(!group)groups.push(group={name,fields:[]});
  group.fields.push(id);
 }
 return {groups,of,image:id=>names.field(id,'image_name')};
}

function hash(text){let h=2166136261;for(let i=0;i<text.length;i++){h^=text.charCodeAt(i);h=Math.imul(h,16777619);}return h>>>0;}
function random(seed){
 return ()=>{seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296;};
}
// Blind review: images in a fixed shuffled order with neutral names, so neither the order nor the name reveals the condition.
// The order depends only on the dataset, so it is the same every time the result is opened.
function blind(datasetId,fieldIds){
 const next=random(hash(String(datasetId))),order=[...fieldIds];
 for(let i=order.length-1;i>0;i--){const j=Math.floor(next()*(i+1));[order[i],order[j]]=[order[j],order[i]];}
 const width=String(order.length).length;
 return {order,label:new Map(order.map((id,i)=>[id,'Image '+String(i+1).padStart(width,'0')]))};
}

function quantile(sorted,q){
 if(!sorted.length)return null;
 const at=(sorted.length-1)*q,lo=Math.floor(at),hi=Math.ceil(at);
 return sorted[lo]+(sorted[hi]-sorted[lo])*(at-lo);
}
function summary(values){
 const s=values.filter(Number.isFinite).sort((a,b)=>a-b);
 return {n:s.length,min:s.length?s[0]:null,max:s.length?s[s.length-1]:null,q1:quantile(s,.25),median:quantile(s,.5),q3:quantile(s,.75)};
}

const FLAGS={edge:'Touches the image edge',small:'Much smaller than most objects',large:'Much larger than most objects',saturated:'Contains saturated pixels'};
// Reasons to look at an object first. They are hints for the reviewer; nothing is excluded automatically.
// Size limits: more than 3 scaled MADs from the median log area of every object of this segmentation input in the run,
// and at least a factor of two from the median area, so a very uniform population is not flagged for ordinary variation.
function flagger(fields,seg,measured=[]){
 const areas=[];
 for(const f of Object.values(fields))for(const o of f.objects?.[seg]||[]){const a=o.regions?.whole?.area;if(a>0)areas.push(Math.log(a));}
 let lo=-Infinity,hi=Infinity;
 if(areas.length>=8){
  const s=areas.sort((a,b)=>a-b),mid=quantile(s,.5),mad=quantile(s.map(v=>Math.abs(v-mid)).sort((a,b)=>a-b),.5);
  const reach=Math.max(3*1.4826*mad,Math.LN2);lo=mid-reach;hi=mid+reach;
 }
 return o=>{
  const whole=o.regions?.whole,a=whole?.area>0?Math.log(whole.area):null,list=[];
  if(o.edgeTouch)list.push('edge');
  if(a!==null&&a<lo)list.push('small');else if(a!==null&&a>hi)list.push('large');
  if(measured.some(c=>whole?.channels?.[c]?.saturated>0))list.push('saturated');
  return list;
 };
}

// Gallery order. Cells arrive in image order, then object ID; ties keep that order.
function order(cells,mode){
 const by={flagged:(a,b)=>b.flags.length-a.flags.length,area:(a,b)=>(a.area??Infinity)-(b.area??Infinity),
  value:(a,b)=>(b.value??-Infinity)-(a.value??-Infinity)}[mode]||(()=>0);
 return cells.map((c,i)=>[c,i]).sort((a,b)=>by(a[0],b[0])||a[1]-b[1]).map(x=>x[0]);
}

// Axis ticks at round numbers covering [min, max].
function ticks(min,max,count=4){
 if(!Number.isFinite(min)||!Number.isFinite(max))return [];
 if(max<=min){max=min+1;min=min-1;}
 const raw=(max-min)/count,mag=10**Math.floor(Math.log10(raw)),norm=raw/mag,step=(norm>5?10:norm>2?5:norm>1?2:1)*mag;
 const out=[];for(let v=Math.floor(min/step)*step;v<=max+step*1e-9;v+=step)out.push(Math.abs(v)<step*1e-9?0:Number(v.toPrecision(12)));
 if(out[out.length-1]<max)out.push(Number((out[out.length-1]+step).toPrecision(12)));
 return out;
}
// A repeatable horizontal offset in [-1, 1] for a plotted point.
const jitter=key=>hash(String(key))/2147483648-1;

// Display colours. Known fluorophore and filter names get their customary colour; other fluorescence channels take the next free
// colour; transmitted-light and display-only channels stay grey. Colours never enter a measurement.
const PALETTE=['#35E06F','#FF5AD9','#39C5FF','#FFB13B','#8F9BFF','#FF7A6B'],GREY='#FFFFFF';
const KNOWN=[[/cy5|647|640|far.?red|irfp|\bapc\b/,'#FFB13B'],[/dapi|hoechst|bfp|405|blue/,'#5B8CFF'],
 [/gfp|fitc|mng|neon|488|green|yfp|venus|citrine/,'#35E06F'],[/mcherry|rfp|tomato|cy3|561|555|594|scarlet|texas|ruby|red/,'#FF5AD9']];
function colours(channels){
 const used=new Set(),out=new Map();
 for(const ch of channels){
  if(ch.kind&&ch.kind!=='fluorescence'){out.set(ch.id,GREY);continue;}
  const text=String(ch.label??ch.id).toLowerCase();
  let colour=KNOWN.find(([pattern,c])=>pattern.test(text)&&!used.has(c))?.[1];
  if(!colour)colour=PALETTE.find(c=>!used.has(c))||PALETTE[out.size%PALETTE.length];
  used.add(colour);out.set(ch.id,colour);
 }
 return out;
}

const api={conditions,blind,quantile,summary,FLAGS,flagger,order,ticks,jitter,colours,GREY};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LabReview=api;
})(globalThis);
