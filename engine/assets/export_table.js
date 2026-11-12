/* Export contents (2.0): regions, measurement channels and columns of the included CSV, one row per measurement or per object.
   3.0 adds a table by condition: one column per image folder and one row per cell, for column tables in statistics software.
   Shared by the report, which builds the CSV, and the export view, which offers the choices. Values are never recomputed here. */
(function(root){
'use strict';
const IDENTITY=['field','segmentation_channel','object_id','region','measurement_channel'],OBJECT_IDENTITY=['field','segmentation_channel','object_id'];
const NAMES=['image_name','image_folder','segmentation_label','measurement_label'];
const ANCHOR={image_name:'field',image_folder:'field',segmentation_label:'segmentation_channel',measurement_label:'measurement_channel'};
const REGIONS=['whole','edge','interior'],LAYOUTS=['long','wide','groups'];
const ORDER=['area_pixels','raw_mean','background_median','background_mean','background_estimator','background_value','corrected_mean','raw_sum','corrected_sum','saturated_pixels','saturation_limit','touches_image_edge','background_valid','expert_validated','exposure_seconds'];
// One row per object: what a value depends on besides the object. Anything else (including unknown columns) varies by region and channel.
const PER_OBJECT=new Set(['touches_image_edge','background_valid','expert_validated']),PER_REGION=new Set(['area_pixels']);
const PER_CHANNEL=new Set(['background_median','background_mean','background_estimator','background_value','saturation_limit','exposure_seconds']);
const NUMERIC=new Set(['object_id','area_pixels','raw_mean','background_median','background_mean','background_value','corrected_mean','raw_sum','corrected_sum','saturated_pixels','saturation_limit','touches_image_edge','background_valid','expert_validated','exposure_seconds']);
const KEY={names:['image_name','image_folder','measurement_label'],values:['raw_mean','background_estimator','background_value','corrected_mean'],regions:['whole']};
// A table by condition lists one measured value per cell: text, per-object flags and per-field background values do not form such columns.
const UNGROUPED='All images';
const numeric=/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;
const cell=(v,numericCell=false)=>{let s=String(v??'');if(!(numericCell&&numeric.test(s)&&Number.isFinite(Number(s)))&&/^[\s\u0000-\u001f\u007f-\u009f]*[=+@-]/u.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
const csv=(columns,rows,numericFlags=[])=>[columns.map(v=>cell(v)).join(','),...rows.map(r=>r.map((v,i)=>cell(v,numericFlags[i])).join(','))].join('\r\n')+'\r\n';
const strings=(x,max=100000)=>Array.isArray(x)&&x.length<=max&&x.every(v=>typeof v==='string');
const fail=message=>{throw Error(message);};

function schema(columns,rows,config={}){
 const ix=new Map(columns.map((c,i)=>[c,i]));
 for(const c of IDENTITY)if(!ix.has(c))fail('CSV identity column missing: '+c);
 const regions=new Set(),channels=new Set();for(const r of rows){regions.add(String(r[ix.get('region')]));channels.add(String(r[ix.get('measurement_channel')]));}
 const configured=(config.channels||[]).map(c=>String(c.id)),labels=new Map((config.channels||[]).map(c=>[String(c.id),String(c.label??c.id)]));
 return {columns:[...columns],values:columns.filter(c=>!IDENTITY.includes(c)),names:[...NAMES],
  regions:[...REGIONS.filter(r=>regions.has(r)),...[...regions].filter(r=>!REGIONS.includes(r))],
  channels:[...configured.filter(id=>channels.has(id)),...[...channels].filter(id=>!configured.includes(id))].map(id=>[id,labels.get(id)||id])};
}
// The dock receives the schema from the sandboxed report; accept only its documented shape.
function check(s){
 if(!s||typeof s!=='object'||![s.columns,s.values,s.names,s.regions].every(x=>strings(x))||!Array.isArray(s.channels)||!s.channels.every(c=>strings(c)&&c.length===2))fail('Invalid export schema');
 if(!IDENTITY.every(c=>s.columns.includes(c))||!s.regions.length||!s.channels.length)fail('Invalid export schema');
 return {columns:[...s.columns],values:[...s.values],names:[...s.names],regions:[...s.regions],channels:s.channels.map(c=>[...c])};
}
const allChannels=s=>s.channels.map(c=>c[0]);
function defaults(s){return {layout:'long',columns:[...s.values],regions:[...s.regions],channels:allChannels(s)};}
// Presets choose columns and regions; layout and channels are kept. 'prism' is the table by condition: corrected mean of the whole ROI.
function preset(s,name,base=defaults(s)){
 if(name==='all')return {...base,columns:[...s.values],regions:[...s.regions]};
 if(name==='prism'){
  const value=['corrected_mean','raw_mean'].find(c=>s.values.includes(c))??grouped(s,s.values)[0];
  if(!value)fail('This result has no measured value for a table by condition.');
  return normalize(s,{...base,layout:'groups',columns:[value],regions:s.regions.includes('whole')?['whole']:[s.regions[0]]});
 }
 if(name!=='key')fail('Unknown export preset');
 const values=KEY.values.filter(c=>s.values.includes(c)),regions=KEY.regions.filter(r=>s.regions.includes(r));
 if(!s.values.includes('background_value')&&s.values.includes('background_median'))values.splice(values.indexOf('corrected_mean'),0,'background_median');
 return normalize(s,{...base,columns:[...KEY.names.filter(n=>s.names.includes(n)),...values],regions:regions.length?regions:[...s.regions]});
}
function normalize(s,o){
 if(o==null)return defaults(s);
 if(typeof o!=='object'||Array.isArray(o))fail('Invalid export contents');
 const pick=(list,allowed,what,required)=>{
  if(!strings(list,allowed.length)||new Set(list).size!==list.length||list.some(x=>!allowed.includes(x)))fail('Invalid export '+what);
  if(required&&!list.length)fail('Choose at least one '+what+' to export.');
  return allowed.filter(x=>list.includes(x));
 };
 const layout=o.layout??'long';if(!LAYOUTS.includes(layout))fail('Invalid export layout');
 const columns=pick(o.columns,[...s.values,...s.names],'column',false);
 if(layout==='groups'&&!grouped(s,columns).length)fail('Choose at least one measured value, such as corrected_mean, for a table by condition.');
 return {layout,columns,regions:pick(o.regions,s.regions,'region',true),channels:pick(o.channels,allChannels(s),'channel',true)};
}
const key=o=>JSON.stringify([o.layout,o.columns,o.regions,o.channels]);
function presetName(s,o){
 const same=(a,b)=>a.length===b.length&&a.every(x=>b.includes(x));
 if(o.layout==='groups'){let p=null;try{p=preset(s,'prism',o);}catch(e){}return p&&same(p.columns,o.columns)&&same(p.regions,o.regions)?'prism':'custom';}
 for(const name of ['all','key']){const p=preset(s,name,o);if(same(p.columns,o.columns)&&same(p.regions,o.regions))return name;}
 return 'custom';
}
// ASCII column prefixes for one row per object, such as "C1_mNG" for channel C1 labelled "C1 · mNG"; plain IDs if they would clash.
function prefixes(s){
 const slug=x=>String(x).normalize('NFKD').replace(/[^\x00-\x7F]/g,'').replace(/[^A-Za-z0-9]+/g,'_').replace(/^_+|_+$/g,'').slice(0,40);
 const named=s.channels.map(([id,label])=>{const sid=slug(id),sl=slug(label);return !sid||sid!==id?id:!sl||sl===id?id:sl.startsWith(id+'_')?sl:id+'_'+sl;});
 return new Map(s.channels.map(([id],i)=>[id,new Set(named).size===named.length?named[i]:id]));
}
const rank=c=>{const i=ORDER.indexOf(c);return i<0?ORDER.length:i;};
const grouped=(s,columns)=>s.values.filter(c=>columns.includes(c)&&NUMERIC.has(c)&&!PER_OBJECT.has(c)&&!PER_CHANNEL.has(c)).map((c,i)=>[c,i]).sort((a,b)=>rank(a[0])-rank(b[0])||a[1]-b[1]).map(x=>x[0]);
// Output columns: name, source column or derived name, and the region/channel a value belongs to (one row per object).
function plan(s,o){
 if(o.layout==='groups')fail('A table by condition gets its columns from the data.');
 const chosen=new Set(o.columns),out=[];
 const withNames=c=>{out.push({name:c,source:c});for(const n of NAMES)if(ANCHOR[n]===c&&chosen.has(n)&&!(o.layout==='wide'&&n==='measurement_label'))out.push({name:n,derived:n});};
 if(o.layout==='long'){for(const c of s.columns)if(IDENTITY.includes(c))withNames(c);else if(chosen.has(c))out.push({name:c,source:c});return out;}
 OBJECT_IDENTITY.forEach(withNames);
 const values=s.values.filter(c=>chosen.has(c)).map((c,i)=>[c,i]).sort((a,b)=>rank(a[0])-rank(b[0])||a[1]-b[1]).map(x=>x[0]);
 const prefix=prefixes(s);
 for(const c of values)if(PER_OBJECT.has(c))out.push({name:c,source:c,scope:'object'});
 for(const r of o.regions)for(const c of values)if(PER_REGION.has(c))out.push({name:`${r}_${c}`,source:c,region:r});
 // Per channel, values follow measurements.csv order (raw, background, corrected, …); a value measured per region repeats for each region.
 for(const ch of o.channels)for(const c of values){
  if(PER_CHANNEL.has(c))out.push({name:`${prefix.get(ch)}_${c}`,source:c,channel:ch});
  else if(!PER_OBJECT.has(c)&&!PER_REGION.has(c))for(const r of o.regions)out.push({name:`${prefix.get(ch)}_${r}_${c}`,source:c,channel:ch,region:r});
 }
 if(new Set(out.map(c=>c.name)).size!==out.length)fail('Export column names are not unique; use one row per measurement.');
 return out;
}
// Components of a path as it was written (path_parts in analyze.py is the same rule). Text that starts like a Windows
// path, with a drive letter or \\server, is also split at backslashes, on every system; anything else at '/' only.
function pathParts(text){
 text=String(text||'');
 if(/^(?:[A-Za-z]:[\\/]|\\\\)/.test(text))text=text.replace(/\\/g,'/');
 return text.split('/').filter(Boolean);
}
// Readable names: image file and folder from the analysed source, channel labels from the run configuration.
function names(config={}){
 const fields=new Map(),channels=new Map((config.channels||[]).map(c=>[String(c.id),String(c.label??c.id)]));
 for(const f of config.fields||[]){
  if(!f||typeof f!=='object')continue;
  const parts=f.member?String(f.member).split('/').filter(Boolean):pathParts(f.path||f.label||f.id||'');
  const archive=f.member&&typeof f.path==='string'?pathParts(f.path).at(-1)||'':'';
  fields.set(String(f.id),{image_name:parts.at(-1)||String(f.label||f.id||''),image_folder:parts.length>1?parts.at(-2):archive});
 }
 return {field:(id,n)=>fields.get(String(id))?.[n]??(n==='image_name'?String(id):''),channel:id=>channels.get(String(id))??String(id)};
}
// One column per condition (the folder that holds the image) and one row per cell. Several values, regions, channels or segmentation
// inputs give one block of condition columns each; cells without a value (empty region, unavailable background) are left out.
function buildGroups(s,o,rows,label){
 const ix=new Map(s.columns.map((c,i)=>[c,i])),at=c=>ix.get(c),regions=new Set(o.regions),channels=new Set(o.channels),values=grouped(s,o.columns),prefix=prefixes(s);
 const conditions=[],conditionOf=new Map(),segs=[],blocks=new Map(),first=o.channels[0];
 for(const r of rows){
  const reg=String(r[at('region')]),ch=String(r[at('measurement_channel')]);if(!regions.has(reg)||!channels.has(ch))continue;
  const field=String(r[at('field')]),seg=String(r[at('segmentation_channel')]);
  let condition=conditionOf.get(field);if(condition===undefined){condition=label.field(field,'image_folder')||UNGROUPED;conditionOf.set(field,condition);if(!conditions.includes(condition))conditions.push(condition);}
  if(!segs.includes(seg))segs.push(seg);
  for(const c of values){
   const perRegion=PER_REGION.has(c);if(perRegion&&ch!==first)continue;   // a value measured once per region is listed once
   const v=r[at(c)];if(v===''||v==null)continue;
   const k=JSON.stringify([seg,perRegion?'':ch,reg,c]);let block=blocks.get(k);if(!block)blocks.set(k,block=new Map());
   let list=block.get(condition);if(!list)block.set(condition,list=[]);list.push(v);
  }
 }
 const order=[];for(const seg of segs)for(const c of values)for(const ch of PER_REGION.has(c)?['']:o.channels)for(const reg of o.regions){const k=JSON.stringify([seg,ch,reg,c]);if(blocks.has(k))order.push([k,seg,ch,reg,c]);}
 // A column is named after its condition; what it lists and which cells it comes from are added only when they vary.
 const columns=[],lists=[],kinds=new Set(order.map(([,,ch,reg,c])=>JSON.stringify([ch,reg,c]))).size;
 for(const[k,seg,ch,reg,c]of order)for(const condition of conditions){
  columns.push([condition,kinds>1?(ch?`${prefix.get(ch)}_${reg}_${c}`:`${reg}_${c}`):'',segs.length>1?'cells from '+seg:''].filter(Boolean).join(' | '));
  lists.push(blocks.get(k).get(condition)||[]);
 }
 if(new Set(columns).size!==columns.length)fail('Condition names are not unique; use one row per measurement.');
 const length=lists.reduce((n,l)=>Math.max(n,l.length),0);
 return {columns,rows:Array.from({length},(_,i)=>lists.map(l=>i<l.length?l[i]:'')),numeric:columns.map(()=>true)};
}
function build(s,o,rows,label=names()){
 if(o.layout==='groups')return buildGroups(s,o,rows,label);
 const spec=plan(s,o),ix=new Map(s.columns.map((c,i)=>[c,i])),at=c=>ix.get(c),regions=new Set(o.regions),channels=new Set(o.channels);
 const derived=(n,r)=>n==='image_name'||n==='image_folder'?label.field(r[at('field')],n):label.channel(r[at(n==='segmentation_label'?'segmentation_channel':'measurement_channel')]);
 const value=(c,r)=>c.derived?derived(c.derived,r):r[at(c.source)];
 const numericFlags=spec.map(c=>!c.derived&&NUMERIC.has(c.source));
 const keep=r=>regions.has(String(r[at('region')]))&&channels.has(String(r[at('measurement_channel')]));
 if(o.layout==='long')return {columns:spec.map(c=>c.name),rows:rows.filter(keep).map(r=>spec.map(c=>value(c,r))),numeric:numericFlags};
 const common=[],byRegion=new Map(),byChannel=new Map(),byCell=new Map(),add=(m,k,i)=>{if(!m.has(k))m.set(k,[]);m.get(k).push(i);};
 spec.forEach((c,i)=>c.region&&c.channel?add(byCell,c.region+'\u0000'+c.channel,i):c.region?add(byRegion,c.region,i):c.channel?add(byChannel,c.channel,i):common.push(i));
 const objects=new Map();
 for(const r of rows){
  if(!keep(r))continue;
  const id=JSON.stringify(OBJECT_IDENTITY.map(c=>String(r[at(c)]))),reg=String(r[at('region')]),ch=String(r[at('measurement_channel')]);
  let out=objects.get(id);if(!out)objects.set(id,out=new Array(spec.length));
  for(const i of [...common,...(byRegion.get(reg)||[]),...(byChannel.get(ch)||[]),...(byCell.get(reg+'\u0000'+ch)||[])]){
   const v=value(spec[i],r);
   if(out[i]===undefined)out[i]=v;
   else if(String(out[i]??'')!==String(v??''))fail(`One row per object is unavailable: ${spec[i].name} differs within object ${String(r[at('object_id')])} of ${String(r[at('field')])}. Use one row per measurement.`);
  }
 }
 return {columns:spec.map(c=>c.name),rows:[...objects.values()].map(r=>r.map(v=>v===undefined?'':v)),numeric:numericFlags};
}
// Exports that add readable names and contain non-ASCII text start with a UTF-8 byte-order mark so spreadsheet apps decode them.
function text(table,o){const body=csv(table.columns,table.rows,table.numeric);return (o.layout==='groups'||o.columns.some(c=>NAMES.includes(c)))&&/[^\x00-\x7F]/.test(body)?'﻿'+body:body;}
function suffix(s,o){
 const parts=[],name=presetName(s,o);
 if(o.layout==='groups')parts.push('by_condition',...(name==='prism'?[]:[...grouped(s,o.columns),...(o.regions.length<s.regions.length?o.regions:[])]));
 else if(name!=='all')parts.push(name==='key'?'key_values':'custom');
 if(o.layout==='wide')parts.push('per_object');
 if(o.channels.length<s.channels.length)parts.push(o.channels.join('-'));
 return parts.length?'_'+parts.join('_').replace(/[^A-Za-z0-9_-]+/g,'_').slice(0,80):'';
}
const api={IDENTITY,OBJECT_IDENTITY,NAMES,NUMERIC,UNGROUPED,schema,check,defaults,preset,presetName,normalize,key,plan,prefixes,names,grouped,build,text,suffix,cell,csv};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LabExport=api;
})(globalThis);
