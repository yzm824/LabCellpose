/* Child-side bridge. The opaque sandbox delegates storage/downloads to its host. */
LabQC.connect=function(qc,bundle,render){
 'use strict';let ready=false,scope='all';
 const post=(type,extra={})=>parent.postMessage({type,dataset_id:bundle.dataset_id,...extra},'*');
 function publish(){if(!ready)return;post('qc-exports',{scope,included_csv:qc.includedCSV(scope),audit_csv:qc.auditCSV(),decisions_json:JSON.stringify(qc.snapshot(),null,2),...qc.scopeStats(scope),excluded_objects:qc.excludedCount()});}
 function change(fn){if(!ready)return;const base=qc.snapshot().revision;fn();render();publish();post('qc-save',{base_revision:base,state:qc.snapshot()});}
 addEventListener('message',event=>{
  if(event.source!==parent||event.data?.dataset_id!==bundle.dataset_id)return;
  const m=event.data;
  try{
   if(m.type==='qc-init'||m.type==='qc-external'){
    if(m.state)qc.load(m.state);else qc.load({schema_version:1,dataset_id:bundle.dataset_id,source_csv_sha256:bundle.source_csv_sha256,source_viewer_sha256:bundle.source_viewer_sha256,revision:0,excluded:[],history:[]});
    ready=true;render();publish();post('qc-loaded');
   }else if(m.type==='qc-scope'){
    if(m.scope!=='all'&&!bundle.segmentation_channels.includes(m.scope))throw Error('Invalid export scope');scope=m.scope;publish();
   }else if(m.type==='qc-import'){
    if(!ready)throw Error('Wait for QC to load before importing.');change(()=>qc.importState(m.state));
   }
  }catch(error){post('qc-error',{message:String(error.message).slice(0,500)});}
 });
 post('qc-ready');return {ready:()=>ready,change,publish};
};
