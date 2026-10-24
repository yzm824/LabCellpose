/* Child-side bridge. The opaque sandbox delegates storage/downloads to its host. */
LabQC.connect=function(qc,bundle,render){
 'use strict';let ready=false,scope='all',contents=qc.exportOptions(null);
 const post=(type,extra={})=>parent.postMessage({type,dataset_id:bundle.dataset_id,...extra},'*');
 function publish(){if(!ready)return;const shape=qc.exportShape(scope,contents);
  post('qc-status',{scope,revision:qc.snapshot().revision,...qc.scopeStats(scope),excluded_objects:qc.excludedCount(),
   export_key:qc.exportKey(contents),export_rows:shape.rows,export_columns:shape.columns.length,export_header:shape.columns.slice(0,200)});}
 const empty=()=>({schema_version:1,dataset_id:bundle.dataset_id,source_csv_sha256:bundle.source_csv_sha256,source_viewer_sha256:bundle.source_viewer_sha256,revision:0,excluded:[],history:[]});
 function change(fn){if(!ready)return;try{const base=qc.snapshot().revision;fn();render();publish();post('qc-save',{base_revision:base,state:qc.snapshot()});}catch(error){post('qc-error',{message:String(error.message).slice(0,500)});publish();}}
 addEventListener('message',event=>{
  if(event.source!==parent||event.data?.dataset_id!==bundle.dataset_id)return;
  const m=event.data;
  try{
   if(m.type==='qc-init'||m.type==='qc-external'){
    ready=false;qc.load(m.state||empty());
    ready=true;render();post('qc-loaded');publish();
   }else if(m.type==='qc-block'){
    ready=false;render();
   }else if(m.type==='qc-recover'){
    const state=qc.validate(m.state||empty());
    post('qc-recovered',{request_id:m.request_id,state});
   }else if(m.type==='qc-scope'){
    if(m.scope!=='all'&&!bundle.segmentation_channels.includes(m.scope))throw Error('Invalid export scope');
    const next=qc.exportOptions(m.contents??null);scope=m.scope;contents=next;publish();
   }else if(m.type==='qc-import'){
    if(!ready)throw Error('Wait for QC to load before importing.');change(()=>qc.importState(m.state));
   }else if(m.type==='qc-export-request'){
    if(!ready||m.scope!==scope||m.revision!==qc.snapshot().revision)throw Error('QC changed; please request the export again.');
    if(!Number.isSafeInteger(m.request_id)||!['included','audit','decisions'].includes(m.kind))throw Error('Invalid export request');
    if(m.kind==='included'&&qc.exportKey(m.contents??null)!==qc.exportKey(contents))throw Error('Export contents changed; please request the export again.');
    const content=m.kind==='included'?qc.includedCSV(scope,contents):m.kind==='audit'?qc.auditCSV():JSON.stringify(qc.snapshot());
    post('qc-export-response',{request_id:m.request_id,kind:m.kind,scope,revision:m.revision,export_key:qc.exportKey(contents),content});
   }
  }catch(error){if(m.type==='qc-init'||m.type==='qc-external'){ready=false;render();post('qc-recovery-needed',{message:String(error.message).slice(0,500)});}else post('qc-error',{request_id:m.request_id,message:String(error.message).slice(0,500)});publish();}
 });
 post('qc-ready',{export_schema:qc.exportSchema()});return {ready:()=>ready,change,publish};
};
