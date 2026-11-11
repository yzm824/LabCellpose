(()=>{'use strict';
const cfg=__QC_HOST_CONFIG__,frame=document.getElementById('codex-visualization'),key='lab-cellpose-qc-v1:'+cfg.dataset_id;
const status=document.getElementById('qc-storage'),scope=document.getElementById('qc-scope'),count=document.getElementById('qc-export-count'),load=document.getElementById('qc-load');
const buttons=[...document.querySelectorAll('[data-qc-download]')];
// 3.0 export view and top bar; these elements are optional so that the same script serves any shell.
const optional=id=>document.getElementById(id)||null;
const progress=optional('qc-progress'),previewBox=optional('export-preview'),fileLabel=optional('export-file'),barTitle=optional('bar-title'),scopeWrap=optional('scope-wrap');
if(barTitle)barTitle.textContent=String(cfg.title||'');
if(scopeWrap)scopeWrap.hidden=cfg.segmentation_options.length<2;
let previewWanted=false,previewPending=null;
let current=null,storageOK=true,ready=false,revision=null,pending=null,nextRequest=0,countText='Loading review state…';
const recovery=document.getElementById('qc-recovery'),backupButton=document.getElementById('qc-backup'),resetButton=document.getElementById('qc-reset'),resetConfirm=document.getElementById('qc-reset-confirm');
let lastRaw=null,backupRaw=null,recovering=false,recoveryPending=null,awaitingLoad=true;
// v1.4: decisions are stored with the results (qc_review_state.json) when the viewer server offers it;
// localStorage remains a mirror and the fallback. Without a store the behaviour is unchanged.
const store=cfg.qc_store&&typeof fetch==='function'?cfg.qc_store:null;
let remoteOK=false,remoteRevision=null,saving=null,queued=null,initGeneration=0,unsaved=false,notice=null;
// v2.0: the dock chooses the included CSV's regions, channels, columns and layout; the report validates the choice again.
let exportSchema=null,contents=null,contentsKey=null,contentsPanel=null;
try{backupRaw=localStorage.getItem(key+':backup');}catch(e){}
backupButton.disabled=backupRaw===null;
const send=(type,extra={})=>frame.contentWindow.postMessage({type,dataset_id:cfg.dataset_id,...extra},'*');
function setStatus(text,error=false){status.textContent=text;status.title=text;status.dataset.state=error?'error':'ok';}
function updateButtons(){buttons.forEach(b=>b.disabled=!ready||pending!==null);}
// The export view shows the first rows of the table; they are requested only while that view is open.
function requestPreview(){
 if(!previewBox||!previewWanted||!ready||!contentsPanel)return;
 previewPending=++nextRequest;send('qc-preview-request',{request_id:previewPending,scope:scope.value,contents});
}
globalThis.labExportView=open=>{previewWanted=!!open;if(previewWanted){contentsPanel?.preview(null);requestPreview();}};

function invalidateExports(){ready=false;pending=null;previewPending=null;updateButtons();count.textContent='Updating review state…';}
function beginRecovery(message){recovering=true;awaitingLoad=true;invalidateExports();recovery.hidden=false;send('qc-block');if(lastRaw!==null){backupRaw=lastRaw;backupButton.disabled=false;}setStatus(message+' Original saved data is retained. In Export, load a valid review file or explicitly start a new review.',true);}
function readSaved(recover=true){
 try{lastRaw=localStorage.getItem(key);}catch(e){storageOK=false;setStatus('Local saving unavailable. Save a review file in Export before closing.',true);return current;}
 try{return lastRaw?JSON.parse(lastRaw):null;}catch(e){if(recover)beginRecovery('Saved QC JSON is damaged.');return undefined;}
}
function validState(s){return s&&s.schema_version===1&&s.dataset_id===cfg.dataset_id&&s.source_csv_sha256===cfg.source_csv_sha256&&s.source_viewer_sha256===cfg.source_viewer_sha256&&Number.isSafeInteger(s.revision)&&s.revision>=0&&Array.isArray(s.excluded)&&Array.isArray(s.history)&&new Blob([JSON.stringify(s)]).size<10000000;}
function writeLocal(state,backup=false){
 try{if(backup&&lastRaw!==null&&lastRaw!==JSON.stringify(state)){localStorage.setItem(key+':backup',lastRaw);backupRaw=lastRaw;backupButton.disabled=false;}
  localStorage.setItem(key,JSON.stringify(state));lastRaw=JSON.stringify(state);storageOK=true;return true;}
 catch(e){storageOK=false;return false;}
}
async function remoteRequest(method,body){
 const response=await fetch(store.path,{method,cache:'no-store',headers:body?{'X-LabCellpose-QC':store.token,'Content-Type':'application/json'}:{'X-LabCellpose-QC':store.token},body:body?JSON.stringify(body):undefined});
 let data=null;try{data=await response.json();}catch(e){}
 return {status:response.status,data};
}
function savedText(){return remoteOK?'Decisions saved with the results':'Decisions saved in this viewer';}
function loadState(state){current=state;send('qc-init',{state:current});}
function initialize(){
 awaitingLoad=true;invalidateExports();recoveryPending=null;
 if(!store){const saved=readSaved();if(saved!==undefined)loadState(saved);return;}
 const generation=++initGeneration,saved=readSaved(false);
 remoteRequest('GET').then(({status,data})=>{
  if(generation!==initGeneration)return;
  const remote=status===200&&data&&validState(data.state)?data.state:null;
  remoteOK=status===200;remoteRevision=remote?remote.revision:null;
  if(data?.damaged)notice='The review file in the result folder was damaged; it will be kept as a separate backup when decisions are next saved.';
  if(saved===undefined&&!remote){beginRecovery('Saved QC JSON is damaged.');return;}
  if(saved===undefined)writeLocal(remote,true);
  const chosen=remote&&(!saved||remote.revision>=saved.revision)?remote:saved;
  if(chosen===remote&&remote&&saved!==undefined&&JSON.stringify(saved)!==JSON.stringify(remote))writeLocal(remote);
  loadState(chosen);
  if(remoteOK&&chosen&&chosen!==remote)persist(chosen);   // migrate browser-only decisions into the result folder
 }).catch(()=>{
  if(generation!==initGeneration)return;
  remoteOK=false;if(saved===undefined){beginRecovery('Saved QC JSON is damaged.');return;}loadState(saved);
 });
}
function persist(state,replace=false){
 // One request at a time; later states supersede queued ones (each state holds every decision).
 if(saving){queued={state,replace:replace||queued?.replace};return;}
 saving=remoteRequest('POST',{base_revision:replace?null:remoteRevision,state,replace}).then(({status,data})=>{
  if(status===200){remoteRevision=state.revision;if(!queued&&state===current){unsaved=false;notice=null;writeLocal(state);setStatus('Decisions saved with the results');}}
  else if(status===409&&data?.state&&validState(data.state)){
   queued=null;invalidateExports();remoteRevision=data.state.revision;writeLocal(data.state);
   notice='The review changed in another result window. The latest saved decisions were loaded; please repeat your last action.';
   current=data.state;unsaved=false;send('qc-external',{state:current});setStatus(notice,true);
  }else{queued=null;remoteOK=false;saveLocally(current,'The result folder cannot store review decisions. ');}
 }).catch(()=>{queued=null;remoteOK=false;saveLocally(current,'Review storage became unavailable. ');}).finally(()=>{
  saving=null;if(queued&&remoteOK){const next=queued;queued=null;persist(next.state,next.replace);}
 });
}
function saveLocally(state,prefix=''){
 if(writeLocal(state)){unsaved=false;setStatus(prefix?prefix+'Decisions are saved in this viewer only; save a review file in Export to keep a copy.':'Decisions saved in this viewer',!!prefix);}
 else{unsaved=true;setStatus('Changes are in this window only. Save a review file in Export before closing.',true);}
}
function requestRecovery(state){awaitingLoad=true;recoveryPending={request_id:++nextRequest,expected_raw:lastRaw};invalidateExports();send('qc-block');send('qc-recover',{request_id:recoveryPending.request_id,state});}
for(const[id,label]of cfg.segmentation_options){const option=document.createElement('option');option.value=id;option.textContent=label;scope.append(option);}
function sendScope(){send('qc-scope',{scope:scope.value,contents});}
function setupContents(schema){
 if(exportSchema||typeof LabExport==='undefined')return;
 try{exportSchema=LabExport.check(schema);}catch(e){return;}
 const use=next=>{contents=next;contentsKey=LabExport.key(next);};
 contentsPanel=typeof LabExportPanel==='undefined'?null:LabExportPanel.attach(document,exportSchema,next=>{invalidateExports();use(next);sendScope();});
 use(contentsPanel?contentsPanel.options():LabExport.defaults(exportSchema));sendScope();
}
scope.addEventListener('change',()=>{invalidateExports();sendScope();});
addEventListener('message',event=>{
 if(event.source!==frame.contentWindow||event.data?.dataset_id!==cfg.dataset_id)return;
 const m=event.data;
 if(m.type==='qc-ready'){setupContents(m.export_schema);initialize();}
 else if(m.type==='qc-loaded'){awaitingLoad=false;recovering=false;recovery.hidden=true;resetConfirm.checked=false;resetButton.disabled=true;
  if(notice)setStatus(notice,true);else if(storageOK||remoteOK)setStatus(savedText());}
 else if(m.type==='qc-recovery-needed'){beginRecovery(m.message);}
 else if(m.type==='qc-recovered'){
  if(!recoveryPending||m.request_id!==recoveryPending.request_id)return;
  const expected=recoveryPending.expected_raw;recoveryPending=null;
  if(!validState(m.state)){beginRecovery('Recovery state is invalid.');return;}
  let live=expected;
  try{live=localStorage.getItem(key);}catch(e){storageOK=false;}
  if(live!==expected){initialize();setStatus('The review changed in another window. Check the latest state before recovering.',true);return;}
  if(expected!==null){backupRaw=expected;backupButton.disabled=false;}
  current=m.state;
  try{if(expected!==null)localStorage.setItem(key+':backup',expected);localStorage.setItem(key,JSON.stringify(current));lastRaw=JSON.stringify(current);storageOK=true;unsaved=false;}
  catch(e){storageOK=false;unsaved=!remoteOK;setStatus('Recovery is in this window only. Original saved data is retained; save a review file in Export before closing.',true);}
  if(remoteOK)persist(current,true);
  send('qc-init',{state:current});
 }
 else if(m.type==='qc-error'){
  if(m.request_id!==undefined&&m.request_id===previewPending){previewPending=null;return;}   // a newer status brings a fresh preview
  if(m.request_id!==undefined&&m.request_id!==pending?.request_id&&m.request_id!==recoveryPending?.request_id)return;
  if(m.request_id===recoveryPending?.request_id)recoveryPending=null;
  pending=null;updateButtons();count.textContent=countText;setStatus(String(m.message).slice(0,500),true);
 }
 else if(m.type==='qc-save'){
  if(!validState(m.state)||m.state.revision!==m.base_revision+1){invalidateExports();setStatus('Invalid review state; changes were not saved.',true);return;}
  if(remoteOK){current=m.state;unsaved=true;persist(current);return;}
  const stored=storageOK?readSaved():current;
  if(stored===undefined)return;
  if(stored&&stored.revision!==m.base_revision){invalidateExports();current=stored;notice='The review changed in another result window. Latest decisions loaded; please repeat your last action.';send('qc-external',{state:stored});setStatus(notice,true);return;}
  current=m.state;notice=null;
  try{localStorage.setItem(key,JSON.stringify(current));lastRaw=JSON.stringify(current);storageOK=true;unsaved=false;setStatus('Decisions saved in this viewer');}
  catch(e){storageOK=false;unsaved=true;setStatus('Changes are in this window only. Save a review file in Export before closing.',true);}
 }else if(m.type==='qc-status'){
  if(awaitingLoad||recovering||recoveryPending||m.scope!==scope.value||(contentsKey!==null&&m.export_key!==contentsKey))return;
  if(!['revision','included_rows','total_rows','excluded_objects','export_rows','export_columns'].every(k=>Number.isSafeInteger(m[k])&&m[k]>=0)||m.included_rows>m.total_rows){invalidateExports();setStatus('Invalid export state. Reload the results before exporting.',true);return;}
  if(revision!==m.revision)pending=null;
  revision=m.revision;ready=true;updateButtons();
  const n=(v,word)=>`${v.toLocaleString('en-US')} ${v===1?word:word+'s'}`;
  countText=`${n(m.excluded_objects,'cell')} excluded · ${m.included_rows.toLocaleString('en-US')} of ${n(m.total_rows,'measurement row')} kept`;
  count.textContent=pending?'Preparing export…':countText;
  contentsPanel?.shape(m.export_rows,m.export_columns);
  if(progress&&Number.isSafeInteger(m.reviewed_images)&&Number.isSafeInteger(m.total_images)&&m.total_images>0)progress.textContent=`${m.reviewed_images} of ${n(m.total_images,'image')} reviewed`;
  if(fileLabel)fileLabel.textContent=fileName('included',scope.value);
  requestPreview();
 }else if(m.type==='qc-preview-response'){
  if(m.request_id!==previewPending)return;
  previewPending=null;
  const text=x=>typeof x==='string'&&x.length<=4000;
  if(!ready||m.scope!==scope.value||m.export_key!==contentsKey||m.revision!==revision||!Array.isArray(m.columns)||m.columns.length>60||!m.columns.every(text)||!Array.isArray(m.rows)||m.rows.length>40
   ||!m.rows.every(r=>Array.isArray(r)&&r.length<=60&&r.every(text))||!Number.isSafeInteger(m.total_rows)||!Number.isSafeInteger(m.total_columns))return;
  contentsPanel?.preview({columns:m.columns,rows:m.rows,total_rows:m.total_rows,total_columns:m.total_columns});
 }else if(m.type==='qc-export-response'){
  if(!pending||m.request_id!==pending.request_id)return;
  const request=pending;pending=null;updateButtons();count.textContent=countText;
  if(!ready||m.kind!==request.kind||m.scope!==scope.value||m.revision!==revision||(request.kind==='included'&&request.contents_key!==null&&m.export_key!==request.contents_key)||typeof m.content!=='string'){
   setStatus('The review changed or the export failed. Please request the export again.',true);return;
  }
  try{download(m.kind,m.content,m.scope);}catch(e){setStatus('Export failed: '+String(e.message).slice(0,400),true);}
 }
});
addEventListener('storage',event=>{
 if(event.key!==key)return;
 // Never replace decisions that exist only in this window; the result-folder store reports conflicts itself.
 if(unsaved){notice='Another window saved different decisions. This window still holds unsaved changes; save a review file in Export before closing.';setStatus(notice,true);return;}
 if(remoteOK)return;
 initialize();
});
buttons.forEach(b=>b.addEventListener('click',()=>{
 if(!ready||pending)return;
 pending={request_id:++nextRequest,kind:b.dataset.qcDownload,scope:scope.value,revision,contents,contents_key:contentsKey};
 updateButtons();count.textContent='Preparing export…';send('qc-export-request',pending);
}));
// File names start with the analysis title (or a short dataset ID); characters that are unsafe in file names are replaced.
const fileStem=(String(cfg.title||'').normalize('NFC').replace(/[\/\\:*?"<>|\u0000-\u001f\u007f]+/g,' ').trim().replace(/\s+/g,'_').replace(/^[.-]+/,'').slice(0,80))||'LabCellpose_'+cfg.dataset_id.slice(0,10);
function fileName(kind,exportScope){
 const ext=['decisions','backup'].includes(kind)?'json':'csv',prefix={included:'included',audit:'excluded_objects',decisions:'qc_decisions',backup:'qc_recovery_backup'}[kind];
 return `${fileStem}_${prefix}${kind==='included'?(exportScope==='all'?'':'_'+exportScope)+(exportSchema&&contents?LabExport.suffix(exportSchema,contents):''):''}.${ext}`;
}
function download(kind,content,exportScope){
 const json=['decisions','backup'].includes(kind);
 const blob=new Blob([content],{type:json?'application/json;charset=utf-8':'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=fileName(kind,exportScope);
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
}
backupButton.addEventListener('click',()=>{if(backupRaw!==null)download('backup',backupRaw,'all');});
resetConfirm.addEventListener('change',()=>{resetButton.disabled=!resetConfirm.checked;});
resetButton.addEventListener('click',()=>{if(resetConfirm.checked)requestRecovery(null);});
load.addEventListener('change',async()=>{const f=load.files?.[0];if(!f)return;try{if(f.size>=10000000)throw Error('The review file is too large');const state=JSON.parse(await f.text());if(!validState(state))throw Error('This review file belongs to a different dataset or is invalid. Nothing was imported.');if(recovering)requestRecovery(state);else{invalidateExports();send('qc-import',{state});}}catch(e){setStatus(e.message,true);}finally{load.value='';}});
})();
