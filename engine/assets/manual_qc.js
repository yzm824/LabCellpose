/* Deterministic manual exclusions. No image inference or intensity modification. */
(function(root){
'use strict';
const key=(field,seg,id)=>JSON.stringify([field,seg,String(id)]);
const cell=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
const csv=(columns,rows)=>[columns,...rows].map(r=>r.map(cell).join(',')).join('\r\n')+'\r\n';
function create(bundle,fields){
 const known=new Set();for(const[f,d]of Object.entries(fields))for(const[s,objects]of Object.entries(d.objects))for(const o of objects)known.add(key(f,s,o.id));
 const ix=Object.fromEntries(bundle.columns.map((c,i)=>[c,i]));
 for(const col of ['field','segmentation_channel','object_id'])if(ix[col]===undefined)throw Error('CSV identity column missing: '+col);
 const rows=bundle.rows.map(r=>({values:r,key:key(r[ix.field],r[ix.segmentation_channel],r[ix.object_id]),seg:r[ix.segmentation_channel]}));
 if(rows.some(r=>!known.has(r.key)))throw Error('CSV/viewer object identity mismatch');
 let excluded=new Map(),history=[],revision=0,undo=[];
 const copy=x=>JSON.parse(JSON.stringify(x));
 const snapshot=()=>({schema_version:1,dataset_id:bundle.dataset_id,source_csv_sha256:bundle.source_csv_sha256,source_viewer_sha256:bundle.source_viewer_sha256,revision,excluded:[...excluded.values()].map(copy),history:copy(history)});
 function parse(state){
  if(!state||state.schema_version!==1||state.dataset_id!==bundle.dataset_id||state.source_csv_sha256!==bundle.source_csv_sha256||state.source_viewer_sha256!==bundle.source_viewer_sha256)throw Error('QC file belongs to a different dataset or format; nothing was imported.');
  if(!Number.isSafeInteger(state.revision)||state.revision<0||!Array.isArray(state.excluded)||!Array.isArray(state.history))throw Error('Invalid QC state');
  if(state.excluded.length>known.size||state.history.length>50000)throw Error('QC state is too large');
  const next=new Map();for(const e of state.excluded){
   if(!e||typeof e.field!=='string'||typeof e.segmentation_channel!=='string'||!['string','number'].includes(typeof e.object_id)||typeof e.reason!=='string'||e.reason.length>2000||typeof e.excluded_at!=='string'||!Number.isFinite(Date.parse(e.excluded_at)))throw Error('Invalid exclusion record');
   const k=key(e.field,e.segmentation_channel,e.object_id);if(!known.has(k)||next.has(k))throw Error('Unknown or duplicate candidate in QC file');
   next.set(k,{field:e.field,segmentation_channel:e.segmentation_channel,object_id:String(e.object_id),reason:e.reason,excluded_at:e.excluded_at});
  }
  for(const h of state.history)if(!h||typeof h.action!=='string'||typeof h.at!=='string'||!Number.isFinite(Date.parse(h.at)))throw Error('Invalid QC history');
  return {next,history:copy(state.history),revision:state.revision};
 }
 function load(state){const v=parse(state);excluded=v.next;history=v.history;revision=v.revision;undo=[];}
 function change(action,apply,detail={}){undo.push([...excluded.entries()].map(copy));if(undo.length>100)undo.shift();apply();history.push({action,at:new Date().toISOString(),...detail});revision++;}
 function toggle(field,seg,id,reason='Manual exclusion'){
  const k=key(field,seg,id);if(!known.has(k))throw Error('Unknown candidate');
  if(typeof reason!=='string'||reason.length>2000)throw Error('Invalid exclusion reason');
  const was=excluded.has(k),at=new Date().toISOString();
  change(was?'restore':'exclude',()=>{if(was)excluded.delete(k);else excluded.set(k,{field,segmentation_channel:seg,object_id:String(id),reason:reason.trim()||'Manual exclusion',excluded_at:at});},{field,segmentation_channel:seg,object_id:String(id),reason});
 }
 function undoLast(){if(!undo.length)return false;excluded=new Map(undo.pop());history.push({action:'undo',at:new Date().toISOString()});revision++;return true;}
 function importState(state){const v=parse(state);if(history.length+v.history.length+1>50000)throw Error('Combined QC history is too large');change('import',()=>{excluded=v.next;history.push(...v.history.map(h=>({...h,imported_from_revision:v.revision})));},{imported_exclusions:v.next.size,source_revision:v.revision});}
 function filtered(scope){return rows.filter(r=>(scope==='all'||r.seg===scope)&&!excluded.has(r.key)).map(r=>r.values);}
 function includedCSV(scope){return csv(bundle.columns,filtered(scope));}
 function auditCSV(){const columns=['dataset_id','field','segmentation_channel','object_id','reason','excluded_at'];return csv(columns,[...excluded.values()].map(e=>[bundle.dataset_id,e.field,e.segmentation_channel,e.object_id,e.reason,e.excluded_at]));}
 return {key,snapshot,load,importState,toggle,undoLast,canUndo:()=>undo.length>0,
  isExcluded:(f,s,id)=>excluded.has(key(f,s,id)),decision:(f,s,id)=>excluded.get(key(f,s,id)),
  excludedCount:()=>excluded.size,includedCSV,auditCSV,filtered,
  scopeStats:scope=>({included_rows:filtered(scope).length,total_rows:rows.filter(r=>scope==='all'||r.seg===scope).length})};
}
const api={create,key,csv};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LabQC=api;
})(globalThis);
