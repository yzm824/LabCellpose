/* Export view (3.0): choose what the exported table contains and see its first rows before saving.
   The choice is remembered in this browser only, as a convenience; measurement channels always start fully selected
   so a new result never silently loses a channel. */
(function(root){
'use strict';
const STORE='lab-cellpose-export-contents-v1';
const LABELS={image_name:'Image file name',image_folder:'Image folder',measurement_label:'Measurement channel name',segmentation_label:'Segmentation channel name',
 raw_mean:'Raw mean',background_value:'Background used',background_estimator:'Background estimator',background_median:'Background median',background_mean:'Background mean',corrected_mean:'Corrected mean',
 raw_sum:'Raw integrated intensity',corrected_sum:'Corrected integrated intensity',area_pixels:'Area (pixels)',saturated_pixels:'Saturated pixels',saturation_limit:'Saturation limit',
 exposure_seconds:'Exposure (s)',touches_image_edge:'Touches image edge',background_valid:'Background valid',expert_validated:'Expert validated'};
const GROUPS=[['Names',['image_name','image_folder','measurement_label','segmentation_label']],['Intensity',['raw_mean','background_value','background_estimator','background_median','background_mean','corrected_mean']],
 ['Integrated intensity',['raw_sum','corrected_sum']],['Area and quality',['area_pixels','saturated_pixels','saturation_limit','exposure_seconds','touches_image_edge','background_valid','expert_validated']]];
const REGIONS={whole:'Whole cell',edge:'Inner boundary band',interior:'Interior'};
// A card is a ready-made table. Its contents can still be adjusted; the card then becomes Custom.
const CARDS=[
 ['all','Everything','Every region and column, one row per measurement: measurements.csv with your review applied.'],
 ['key','Key values','Whole cell: raw mean, background and corrected mean, with image and channel names. One row per measurement.'],
 ['cells','One row per cell','The key values with the channels side by side, one row for each cell.'],
 ['prism','By condition','One column per image folder and one row per cell: corrected mean of the whole cell. Paste it into a column table in Prism.'],
 ['custom','Custom','Choose the rows, regions, channels and columns yourself.']];
const LAYOUTS=[['long','One row per measurement','Cell × region × channel, as in measurements.csv.'],['wide','One row per cell','Each cell on one row; channels and regions side by side.'],
 ['groups','One column per condition','Each image folder is a column; each row is one cell. Choose the measured values to list.']];
const QUALIFIER={wide:'one row per cell',groups:'one column per condition'};
function attach(doc,schema,onChange){
 const panel=doc.getElementById('qc-contents-panel'),summary=doc.getElementById('qc-contents-summary');
 if(!panel||!summary)return null;
 const X=root.LabExport,base=X.defaults(schema);
 function restore(){
  let saved=null;try{saved=JSON.parse(root.localStorage.getItem(STORE));}catch(e){}
  if(!saved||typeof saved!=='object'||Array.isArray(saved))return base;
  try{
   const layout=['wide','groups'].includes(saved.layout)?saved.layout:'long';
   if(saved.preset==='prism')return X.preset(schema,'prism',base);
   if(saved.preset==='all'||saved.preset==='key')return X.preset(schema,saved.preset,{...base,layout:layout==='groups'?'long':layout});
   const allowed=[...schema.values,...schema.names],unique=(list,ok)=>Array.isArray(list)?[...new Set(list.filter(x=>ok.includes(x)))]:null;
   const columns=unique(saved.columns,allowed),regions=unique(saved.regions,schema.regions);
   return X.normalize(schema,{layout,columns:columns??base.columns,regions:regions?.length?regions:base.regions,channels:base.channels});
  }catch(e){return base;}
 }
 let options=restore(),adjusting=false;
 const el=(tag,props={},...children)=>{const e=doc.createElement(tag);for(const[k,v]of Object.entries(props))k==='text'?e.textContent=v:k==='class'?e.className=v:e[k]=v;e.append(...children.filter(Boolean));return e;};
 const checks={columns:new Map(),regions:new Map(),channels:new Map()},cardButtons=new Map(),layoutButtons=new Map();
 const note=el('p',{class:'contents-note'}),hint=el('p',{class:'contents-note contents-hint',role:'status'});
 // A tip is advice; anything else said here is a choice that could not be applied.
 const say=(text,tip=false)=>{hint.textContent=text;hint.className='contents-note contents-hint'+(tip?' tip':'');};
 const check=(group,value,label,code)=>{const input=el('input',{type:'checkbox',value});checks[group].set(value,input);input.addEventListener('change',()=>edit(group,value,input));
  return el('label',{class:'contents-check'},input,el('span',{text:label}),code?el('code',{text:code}):null);};
 const section=(title,...children)=>el('fieldset',{class:'contents-section'},el('legend',{text:title}),...children);
 const known=new Set(GROUPS.flatMap(g=>g[1])),other=schema.values.filter(c=>!known.has(c));
 const groups=[...GROUPS,['Other',other]].map(([title,list])=>[title,list.filter(c=>schema.values.includes(c)||schema.names.includes(c))]).filter(g=>g[1].length);
 const cards=el('div',{class:'contents-cards'},...CARDS.map(([name,label,text])=>{
  const b=el('button',{type:'button',class:'contents-card'},el('strong',{text:label}),el('span',{text}));
  b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>choose(name));cardButtons.set(name,b);return b;}));
 const layouts=el('div',{class:'segmented'},...LAYOUTS.map(([value,label])=>{const b=el('button',{type:'button',text:label});b.setAttribute('aria-pressed','false');
  b.addEventListener('click',()=>apply(value==='groups'&&options.layout!=='groups'?groupsFrom(options):{...options,layout:value}));layoutButtons.set(value,b);return b;}));
 const details=el('div',{class:'contents-adjust'},
  section('Rows',layouts,note),
  section('Regions',el('div',{class:'contents-options'},...schema.regions.map(r=>check('regions',r,REGIONS[r]||r)))),
  section('Measurement channels',el('div',{class:'contents-options'},...schema.channels.map(([id,label])=>check('channels',id,label,label.includes(id)?'':id)))),
  section('Columns',el('div',{class:'contents-columns'},...groups.map(([title,list])=>el('div',{class:'contents-group'},el('span',{class:'contents-group-title',text:title}),...list.map(c=>check('columns',c,LABELS[c]||c,c))))),
   el('p',{class:'contents-note',text:'Always included: field, segmentation_channel, object_id; with one row per measurement also region and measurement_channel. Image names come from the analysed files; channel names from the run settings.'})));
 const adjust=el('button',{type:'button',class:'contents-toggle'});
 adjust.addEventListener('click',()=>{adjusting=!adjusting;render();});
 const table=doc.getElementById('export-preview'),shapeLabel=doc.getElementById('export-shape');
 panel.replaceChildren(cards,hint,adjust,details);
 // A table by condition needs a measured value: keep the chosen ones, or start from the corrected mean.
 function groupsFrom(o){return X.grouped(schema,o.columns).length?{...o,layout:'groups'}:{...X.preset(schema,'prism',o),regions:o.regions};}
 function card(o=options){
  const name=X.presetName(schema,o);
  if(o.layout==='groups')return name==='prism'?'prism':'custom';
  return name==='all'&&o.layout==='long'?'all':name==='key'?(o.layout==='wide'?'cells':'key'):'custom';
 }
 function choose(name){
  if(name==='custom'){adjusting=true;say('Tick the rows, regions and columns you need.',true);render();return;}
  say('');
  try{apply(name==='prism'?X.preset(schema,'prism',options):X.preset(schema,name==='cells'?'key':name,{...options,layout:name==='cells'?'wide':'long'}));}
  catch(e){say(e.message);}
 }
 function edit(group,value,input){
  const list=new Set(options[group]);input.checked?list.add(value):list.delete(value);
  if(group!=='columns'&&!list.size){input.checked=true;say(`Keep at least one ${group==='regions'?'region':'measurement channel'}.`);return;}
  apply({...options,[group]:[...list]});
 }
 function describe(){
  const name=card(),parts=[CARDS.find(c=>c[0]===name)[1]];
  if(name==='custom'&&QUALIFIER[options.layout])parts.push(QUALIFIER[options.layout]);
  if(options.channels.length<schema.channels.length)parts.push(`${options.channels.length} of ${schema.channels.length} channels`);
  return parts.join(' · ');
 }
 function render(){
  const name=card(),groupable=new Set(X.grouped(schema,[...schema.values]));
  for(const[group,map]of Object.entries(checks))for(const[value,input]of map)input.checked=options[group].includes(value);
  for(const[value,b]of cardButtons)b.setAttribute('aria-pressed',String(value===name));
  for(const[value,b]of layoutButtons)b.setAttribute('aria-pressed',String(value===options.layout));
  // Columns that cannot appear in the chosen arrangement are unavailable rather than silently ignored.
  for(const[value,input]of checks.columns)input.disabled=options.layout==='groups'?!groupable.has(value):options.layout==='wide'&&value==='measurement_label';
  note.textContent=LAYOUTS.find(l=>l[0]===options.layout)[2]+(options.layout==='wide'?' Channel names appear in the column names.':'');
  const open=adjusting||name==='custom';details.hidden=!open;adjust.textContent=open?'Hide the details':'Adjust rows, regions, channels and columns';adjust.hidden=name==='custom';
  summary.textContent=describe();
 }
 function apply(next){
  try{options=X.normalize(schema,next);}catch(e){say(e.message);render();return;}
  say('');if(shapeLabel)shapeLabel.textContent='Updating…';render();
  try{root.localStorage.setItem(STORE,JSON.stringify({preset:X.presetName(schema,options),layout:options.layout,columns:options.columns,regions:options.regions}));}catch(e){}
  onChange(options);
 }
 render();
 return {options:()=>options,describe,
  shape(rows,columns){
   if(shapeLabel)shapeLabel.textContent=`${rows.toLocaleString('en-US')} ${rows===1?'row':'rows'} × ${columns.toLocaleString('en-US')} ${columns===1?'column':'columns'}`;
  },
  // The first rows of the table, exactly as they will be written.
  preview(data){
   if(!table)return;
   if(!data){table.replaceChildren(el('p',{class:'preview-note',text:'Preparing the preview…'}));return;}
   const head=el('tr',{},...data.columns.map(c=>el('th',{text:c})));
   const body=data.rows.map(r=>el('tr',{},...r.map(v=>el('td',{text:v}))));
   const more=[];
   if(data.total_columns>data.columns.length)more.push(`${data.total_columns-data.columns.length} more columns`);
   if(data.total_rows>data.rows.length)more.push(`${(data.total_rows-data.rows.length).toLocaleString('en-US')} more rows`);
   table.replaceChildren(el('table',{},el('thead',{},head),el('tbody',{},...body)),
    el('p',{class:'preview-note',text:data.total_rows?(more.length?'… and '+more.join(', ')+' in the saved file.':'These are all the rows of the saved file.'):'No rows: every cell in this selection is excluded or has no value.'}));
  }};
}
root.LabExportPanel={attach,STORE};
})(globalThis);
