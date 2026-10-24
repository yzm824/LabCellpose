/* Export dock (2.0): choose what the included CSV contains. The choice is remembered in this browser only, as a convenience;
   measurement channels always start fully selected so a new result never silently loses a channel. */
(function(root){
'use strict';
const STORE='lab-cellpose-export-contents-v1';
const LABELS={image_name:'Image file name',image_folder:'Image folder',measurement_label:'Measurement channel name',segmentation_label:'Segmentation channel name',
 raw_mean:'Raw mean',background_value:'Background used',background_estimator:'Background estimator',background_median:'Background median',background_mean:'Background mean',corrected_mean:'Corrected mean',
 raw_sum:'Raw integrated intensity',corrected_sum:'Corrected integrated intensity',area_pixels:'Area (pixels)',saturated_pixels:'Saturated pixels',saturation_limit:'Saturation limit',
 exposure_seconds:'Exposure (s)',touches_image_edge:'Touches image edge',background_valid:'Background valid',expert_validated:'Expert validated'};
const GROUPS=[['Names',['image_name','image_folder','measurement_label','segmentation_label']],['Intensity',['raw_mean','background_value','background_estimator','background_median','background_mean','corrected_mean']],
 ['Integrated intensity',['raw_sum','corrected_sum']],['Area and quality',['area_pixels','saturated_pixels','saturation_limit','exposure_seconds','touches_image_edge','background_valid','expert_validated']]];
const REGIONS={whole:'Whole ROI',edge:'Inner boundary band',interior:'Interior ROI'};
const PRESETS=[['all','All columns','Every region and column, as in measurements.csv, with your QC and background choices applied.'],
 ['key','Key values','Whole ROI: raw mean, background used (with its estimator) and corrected mean, plus image and channel names.'],
 ['custom','Custom','Your own selection of regions and columns.']];
const LAYOUTS=[['long','One row per measurement','Object × region × channel, as in measurements.csv.'],['wide','One row per object','Each object on one row; channels and regions side by side.']];
function attach(doc,schema,onChange){
 const panel=doc.getElementById('qc-contents-panel'),summary=doc.getElementById('qc-contents-summary');
 if(!panel||!summary)return null;
 const X=root.LabExport,base=X.defaults(schema);
 function restore(){
  let saved=null;try{saved=JSON.parse(root.localStorage.getItem(STORE));}catch(e){}
  if(!saved||typeof saved!=='object'||Array.isArray(saved))return base;
  try{
   const layout=saved.layout==='wide'?'wide':'long';
   if(saved.preset==='all'||saved.preset==='key')return X.preset(schema,saved.preset,{...base,layout});
   const allowed=[...schema.values,...schema.names],unique=(list,ok)=>Array.isArray(list)?[...new Set(list.filter(x=>ok.includes(x)))]:null;
   const columns=unique(saved.columns,allowed),regions=unique(saved.regions,schema.regions);
   return X.normalize(schema,{layout,columns:columns??base.columns,regions:regions?.length?regions:base.regions,channels:base.channels});
  }catch(e){return base;}
 }
 let options=restore();
 const el=(tag,props={},...children)=>{const e=doc.createElement(tag);for(const[k,v]of Object.entries(props))k==='text'?e.textContent=v:k==='class'?e.className=v:e[k]=v;e.append(...children.filter(Boolean));return e;};
 const checks={columns:new Map(),regions:new Map(),channels:new Map()},presetButtons=new Map(),layoutButtons=new Map();
 const note=el('p',{class:'contents-note'}),hint=el('p',{class:'contents-note',role:'status'}),shape=el('p',{class:'contents-shape'}),header=el('p',{class:'contents-header'});
 const check=(group,value,label,code)=>{const input=el('input',{type:'checkbox',value});checks[group].set(value,input);input.addEventListener('change',()=>edit(group,value,input));
  return el('label',{class:'contents-check'},input,el('span',{text:label}),code?el('code',{text:code}):null);};
 const section=(title,...children)=>el('fieldset',{class:'contents-section'},el('legend',{text:title}),...children);
 const segmented=(items,map,act)=>el('div',{class:'segmented'},...items.map(([value,label])=>{const b=el('button',{type:'button',text:label});b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>act(value));map.set(value,b);return b;}));
 const known=new Set(GROUPS.flatMap(g=>g[1])),other=schema.values.filter(c=>!known.has(c));
 const groups=[...GROUPS,['Other',other]].map(([title,list])=>[title,list.filter(c=>schema.values.includes(c)||schema.names.includes(c))]).filter(g=>g[1].length);
 panel.replaceChildren(
  el('strong',{text:'Export contents'}),
  section('Preset',segmented(PRESETS,presetButtons,name=>{if(name!=='custom')apply(X.preset(schema,name,options));else{hint.textContent='Tick the regions and columns you need.';}}),note),
  section('Rows',segmented(LAYOUTS,layoutButtons,layout=>apply({...options,layout}))),
  section('Regions',el('div',{class:'contents-options'},...schema.regions.map(r=>check('regions',r,REGIONS[r]||r)))),
  section('Measurement channels',el('div',{class:'contents-options'},...schema.channels.map(([id,label])=>check('channels',id,label,label.includes(id)?'':id)))),
  section('Columns',el('div',{class:'contents-columns'},...groups.map(([title,list])=>el('div',{class:'contents-group'},el('span',{class:'contents-group-title',text:title}),...list.map(c=>check('columns',c,LABELS[c]||c,c))))),
   el('p',{class:'contents-note',text:'Always included: field, segmentation_channel, object_id; with one row per measurement also region and measurement_channel. Image names come from the analysed files; channel names from the run settings.'})),
  hint,shape,header);
 function edit(group,value,input){
  const list=new Set(options[group]);input.checked?list.add(value):list.delete(value);
  if(group!=='columns'&&!list.size){input.checked=true;hint.textContent=`Keep at least one ${group==='regions'?'region':'measurement channel'}.`;return;}
  apply({...options,[group]:[...list]});
 }
 function describe(){
  const name=X.presetName(schema,options),parts=[PRESETS.find(p=>p[0]===name)[1]];
  if(options.layout==='wide')parts.push('one row per object');
  if(options.channels.length<schema.channels.length)parts.push(`${options.channels.length} of ${schema.channels.length} channels`);
  return parts.join(' · ');
 }
 function render(){
  const name=X.presetName(schema,options);
  for(const[group,map]of Object.entries(checks))for(const[value,input]of map)input.checked=options[group].includes(value);
  for(const[value,b]of presetButtons)b.setAttribute('aria-pressed',String(value===name));
  for(const[value,b]of layoutButtons)b.setAttribute('aria-pressed',String(value===options.layout));
  const measurementName=checks.columns.get('measurement_label');if(measurementName)measurementName.disabled=options.layout==='wide';
  note.textContent=`${PRESETS.find(p=>p[0]===name)[2]} ${LAYOUTS.find(l=>l[0]===options.layout)[2]}${options.layout==='wide'?' Channel names appear in the column names.':''}`;
  summary.textContent='Contents: '+describe();
 }
 function apply(next){
  try{options=X.normalize(schema,next);}catch(e){hint.textContent=e.message;render();return;}
  hint.textContent='';shape.textContent='Updating…';header.textContent='';render();
  try{root.localStorage.setItem(STORE,JSON.stringify({preset:X.presetName(schema,options),layout:options.layout,columns:options.columns,regions:options.regions}));}catch(e){}
  onChange(options);
 }
 render();
 return {options:()=>options,describe,
  shape(rows,columns,names){
   shape.textContent=`This CSV: ${rows.toLocaleString()} ${rows===1?'row':'rows'} × ${columns} ${columns===1?'column':'columns'}${options.layout==='wide'?' (one per object)':''}.`;
   header.textContent=Array.isArray(names)&&names.length?'Columns: '+names.slice(0,40).join(', ')+(columns>40?`, … (${columns-40} more)`:''):'';
  }};
}
root.LabExportPanel={attach,STORE};
})(globalThis);
