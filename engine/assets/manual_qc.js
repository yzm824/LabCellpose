/* Deterministic review decisions and background corrections; raw pixels unchanged. */
(function(root){
'use strict';
const key=(field,seg,id)=>JSON.stringify([field,seg,String(id)]);
const Background=typeof module!=='undefined'&&module.exports?require('./background_stats.js'):root.LabBackground;
const Export=typeof module!=='undefined'&&module.exports?require('./export_table.js'):root.LabExport;
const csv=(columns,rows,measurement=false)=>Export.csv(columns,rows,measurement?columns.map(c=>Export.NUMERIC.has(c)):[]);
const MAX_HISTORY=50000,MAX_STATE_BYTES=10000000;
const stateTooLarge=s=>{const text=JSON.stringify(s);return text.length>=MAX_STATE_BYTES||new TextEncoder().encode(text).length>=MAX_STATE_BYTES;};
function create(bundle,fields,config={}){
 const known=new Set(),units=new Set(),unitKey=(field,seg)=>JSON.stringify([field,seg]);
 for(const[f,d]of Object.entries(fields))for(const[s,objects]of Object.entries(d.objects)){units.add(unitKey(f,s));for(const o of objects)known.add(key(f,s,o.id));}
 const ix=Object.fromEntries(bundle.columns.map((c,i)=>[c,i]));
 for(const col of ['field','segmentation_channel','object_id'])if(ix[col]===undefined)throw Error('CSV identity column missing: '+col);
 const rows=bundle.rows.map(r=>({values:r,key:key(r[ix.field],r[ix.segmentation_channel],r[ix.object_id]),seg:r[ix.segmentation_channel]}));
 if(rows.some(r=>!known.has(r.key)))throw Error('CSV/viewer object identity mismatch');
 const background=Background.create(bundle,fields);
 // Export contents choose among the included CSV's columns (after background additions); names come from the run configuration.
 // A CSV without region/measurement-channel columns keeps the fixed full export.
 let exportSchema=null;try{exportSchema=Export.schema(background.columns,bundle.rows,config||{});}catch(e){}
 const exportNames=Export.names(config||{});
 // 3.0: an image (field × segmentation input) can be marked as reviewed; saved only when used, so older versions read the same file.
 let excluded=new Map(),history=[],revision=0,undo=[],estimators={},reviewed=new Map();
 const marks=m=>m.size?{reviewed:[...m.values()]}:{};
 const copy=x=>JSON.parse(JSON.stringify(x));
 const snapshot=()=>({schema_version:1,dataset_id:bundle.dataset_id,source_csv_sha256:bundle.source_csv_sha256,source_viewer_sha256:bundle.source_viewer_sha256,revision,excluded:[...excluded.values()].map(copy),history:copy(history),background_estimators:{...estimators},...copy(marks(reviewed))});
 function parse(state){
  if(!state||state.schema_version!==1||state.dataset_id!==bundle.dataset_id||state.source_csv_sha256!==bundle.source_csv_sha256||state.source_viewer_sha256!==bundle.source_viewer_sha256)throw Error('QC file belongs to a different dataset or format; nothing was imported.');
  if(!Number.isSafeInteger(state.revision)||state.revision<0||!Array.isArray(state.excluded)||!Array.isArray(state.history))throw Error('Invalid QC state');
  if(state.excluded.length>known.size||state.history.length>MAX_HISTORY||stateTooLarge(state))throw Error('QC state is too large');
  const next=new Map();for(const e of state.excluded){
   if(!e||typeof e.field!=='string'||typeof e.segmentation_channel!=='string'||!['string','number'].includes(typeof e.object_id)||typeof e.reason!=='string'||e.reason.length>2000||typeof e.excluded_at!=='string'||!Number.isFinite(Date.parse(e.excluded_at)))throw Error('Invalid exclusion record');
   const k=key(e.field,e.segmentation_channel,e.object_id);if(!known.has(k)||next.has(k))throw Error('Unknown or duplicate candidate in QC file');
   next.set(k,{field:e.field,segmentation_channel:e.segmentation_channel,object_id:String(e.object_id),reason:e.reason,excluded_at:e.excluded_at});
  }
  for(const h of state.history)if(!h||typeof h.action!=='string'||typeof h.at!=='string'||!Number.isFinite(Date.parse(h.at)))throw Error('Invalid QC history');
  const done=new Map();if(state.reviewed!==undefined){
   if(!Array.isArray(state.reviewed)||state.reviewed.length>units.size)throw Error('Invalid reviewed-image list');
   for(const r of state.reviewed){
    if(!r||typeof r.field!=='string'||typeof r.segmentation_channel!=='string'||typeof r.reviewed_at!=='string'||!Number.isFinite(Date.parse(r.reviewed_at)))throw Error('Invalid reviewed-image record');
    const k=unitKey(r.field,r.segmentation_channel);if(!units.has(k)||done.has(k))throw Error('Unknown or duplicate image in QC file');
    done.set(k,{field:r.field,segmentation_channel:r.segmentation_channel,reviewed_at:r.reviewed_at});
   }
  }
  return {next,history:copy(state.history),revision:state.revision,estimators:background.validate(state.background_estimators??{}),reviewed:done};
 }
 function load(state){const v=parse(state);excluded=v.next;history=v.history;revision=v.revision;estimators=v.estimators;reviewed=v.reviewed;undo=[];}
 function commit(next,nextHistory,nextUndo,nextEstimators=estimators,nextReviewed=reviewed){
  if(revision>=Number.MAX_SAFE_INTEGER||nextHistory.length>MAX_HISTORY)throw Error('QC limit reached. Save QC decisions JSON, then start a new review in More options. Existing decisions are unchanged.');
  const state={schema_version:1,dataset_id:bundle.dataset_id,source_csv_sha256:bundle.source_csv_sha256,source_viewer_sha256:bundle.source_viewer_sha256,revision:revision+1,excluded:[...next.values()],history:nextHistory,background_estimators:nextEstimators,...marks(nextReviewed)};
  if(stateTooLarge(state))throw Error('QC size limit reached. Save QC decisions JSON before starting a new review. Existing decisions are unchanged.');
  excluded=next;history=nextHistory;undo=nextUndo;estimators={...nextEstimators};reviewed=nextReviewed;revision++;
 }
 function change(action,apply,detail={},importedHistory=[],nextEstimators=estimators,nextReviewed=reviewed){const next=new Map(excluded);apply(next);commit(next,[...history,...importedHistory,{action,at:new Date().toISOString(),...detail}],[...undo,{excluded:[...excluded.entries()],estimators:{...estimators},reviewed:[...reviewed.entries()]}].slice(-100),nextEstimators,nextReviewed);}
 function toggle(field,seg,id,reason='Manual exclusion'){
  const k=key(field,seg,id);if(!known.has(k))throw Error('Unknown candidate');
  if(typeof reason!=='string'||reason.length>2000)throw Error('Invalid exclusion reason');
  const was=excluded.has(k),at=new Date().toISOString();
  change(was?'restore':'exclude',next=>{if(was)next.delete(k);else next.set(k,{field,segmentation_channel:seg,object_id:String(id),reason:reason.trim()||'Manual exclusion',excluded_at:at});},{field,segmentation_channel:seg,object_id:String(id),reason});
 }
 // Every object of one segmentation input in one field, as a single undoable change; earlier exclusions keep their reason and time.
 function setAll(field,seg,exclude,reason='Manual exclusion'){
  const objects=fields[field]?.objects?.[seg];if(!Array.isArray(objects))throw Error('Unknown field or segmentation input');
  if(typeof reason!=='string'||reason.length>2000)throw Error('Invalid exclusion reason');
  const todo=objects.map(o=>[key(field,seg,o.id),String(o.id)]).filter(([k])=>excluded.has(k)!==exclude);if(!todo.length)return 0;
  const at=new Date().toISOString(),why=reason.trim()||'Manual exclusion';
  change(exclude?'exclude-all':'restore-all',next=>{for(const[k,id]of todo)if(exclude)next.set(k,{field,segmentation_channel:seg,object_id:id,reason:why,excluded_at:at});else next.delete(k);},
   {field,segmentation_channel:seg,objects:todo.length,...(exclude?{reason}:{})});
  return todo.length;
 }
 // Several objects, possibly in different images, as a single undoable change.
 function setMany(items,exclude,reason='Manual exclusion'){
  if(!Array.isArray(items)||items.length>known.size)throw Error('Invalid selection');
  if(typeof reason!=='string'||reason.length>2000)throw Error('Invalid exclusion reason');
  const todo=new Map();for(const item of items){
   if(!Array.isArray(item)||item.length!==3)throw Error('Invalid selection');
   const[field,seg,id]=item,k=key(field,seg,id);if(!known.has(k))throw Error('Unknown candidate');
   if(excluded.has(k)!==exclude)todo.set(k,{field,segmentation_channel:seg,object_id:String(id)});
  }
  if(!todo.size)return 0;
  const at=new Date().toISOString(),why=reason.trim()||'Manual exclusion';
  change(exclude?'exclude-many':'restore-many',next=>{for(const[k,o]of todo)if(exclude)next.set(k,{...o,reason:why,excluded_at:at});else next.delete(k);},{objects:todo.size,...(exclude?{reason}:{})});
  return todo.size;
 }
 function setReviewed(field,seg,done){
  const k=unitKey(field,seg);if(!units.has(k))throw Error('Unknown field or segmentation input');
  if(reviewed.has(k)===!!done)return false;
  const next=new Map(reviewed),at=new Date().toISOString();if(done)next.set(k,{field,segmentation_channel:seg,reviewed_at:at});else next.delete(k);
  change(done?'reviewed':'unreviewed',()=>{},{field,segmentation_channel:seg},[],estimators,next);return true;
 }
 function undoLast(){if(!undo.length)return false;const prior=undo.at(-1);commit(new Map(prior.excluded),[...history,{action:'undo',at:new Date().toISOString()}],undo.slice(0,-1),prior.estimators,new Map(prior.reviewed));return true;}
 // History entries already present (e.g. re-loading this review's own saved JSON) are not appended again.
 const canon=h=>JSON.stringify(Object.keys(h).filter(k=>k!=='imported_from_revision').sort().map(k=>[k,h[k]]));
 function importState(state){const v=parse(state),present=new Set(history.map(canon)),added=v.history.filter(h=>!present.has(canon(h))).map(h=>({...h,imported_from_revision:v.revision}));
  change('import',next=>{next.clear();for(const[k,e]of v.next)next.set(k,e);},{imported_exclusions:v.next.size,source_revision:v.revision,imported_history:added.length,already_present_history:v.history.length-added.length},added,v.estimators,v.reviewed);}
 function setEstimator(channel,method){
  const next=background.validate({...estimators,[channel]:method});
  if(background.method(estimators,channel)===method)return;
  change('background-estimator',()=>{},{channel,method},[],next);
 }
 function filtered(scope){return rows.filter(r=>(scope==='all'||r.seg===scope)&&!excluded.has(r.key)).map(r=>r.values);}
 function exportOptions(o){if(exportSchema)return Export.normalize(exportSchema,o);if(o!=null)throw Error('This result offers the full export only.');return null;}
 const exportKey=o=>{const options=exportOptions(o);return options?Export.key(options):'full';};
 function includedCSV(scope,o){
  const options=exportOptions(o),table=filtered(scope).map(r=>background.exportRow(r,estimators));
  return options?Export.text(Export.build(exportSchema,options,table,exportNames),options):csv(background.columns,table,true);
 }
 // The first rows of the included CSV exactly as they will be written, for the export preview.
 function exportPreview(scope,o,limit=40){
  const options=exportOptions(o);
  const table=options?exportTable(scope,options):{columns:[...background.columns],rows:filtered(scope).map(r=>background.exportRow(r,estimators))};
  return {columns:table.columns,rows:table.rows.slice(0,limit).map(r=>r.map(v=>v==null?'':String(v))),total_rows:table.rows.length};
 }
 function exportTable(scope,options){return Export.build(exportSchema,options,filtered(scope).map(r=>background.exportRow(r,estimators)),exportNames);}
 function exportShape(scope,o){
  const options=exportOptions(o);if(!options)return {rows:filtered(scope).length,columns:[...background.columns]};
  if(options.layout==='groups'){const table=exportTable(scope,options);return {rows:table.rows.length,columns:table.columns};}
  const regions=new Set(options.regions),channels=new Set(options.channels),objects=new Set();let count=0;
  for(const r of rows)if((scope==='all'||r.seg===scope)&&!excluded.has(r.key)&&regions.has(String(r.values[ix.region]))&&channels.has(String(r.values[ix.measurement_channel]))){count++;objects.add(r.key);}
  return {rows:options.layout==='wide'?objects.size:count,columns:Export.plan(exportSchema,options).map(c=>c.name)};
 }
 function auditCSV(){const columns=['dataset_id','field','segmentation_channel','object_id','reason','excluded_at'];return csv(columns,[...excluded.values()].map(e=>[bundle.dataset_id,e.field,e.segmentation_channel,e.object_id,e.reason,e.excluded_at]));}
 return {key,snapshot,load,validate:state=>{parse(state);return copy(state);},importState,toggle,setAll,setMany,setReviewed,undoLast,canUndo:()=>undo.length>0,
  isReviewed:(f,s)=>reviewed.has(unitKey(f,s)),reviewedCount:()=>reviewed.size,unitCount:()=>units.size,
  setEstimator,estimator:channel=>background.method(estimators,channel),canUseEstimator:background.available,
  measurement:(field,channel,m,area)=>background.measurement(field,channel,m,area,estimators),
  isExcluded:(f,s,id)=>excluded.has(key(f,s,id)),decision:(f,s,id)=>{const e=excluded.get(key(f,s,id));return e?copy(e):undefined;},
  excludedCount:()=>excluded.size,includedCSV,auditCSV,filtered,
  exportSchema:()=>exportSchema&&copy(exportSchema),exportOptions,exportKey,exportShape,exportPreview,
  scopeStats:scope=>({included_rows:filtered(scope).length,total_rows:rows.filter(r=>scope==='all'||r.seg===scope).length})};
}
const api={create,key,csv};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LabQC=api;
})(globalThis);
