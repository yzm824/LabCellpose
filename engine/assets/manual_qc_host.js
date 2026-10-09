(()=>{'use strict';
const cfg=__QC_HOST_CONFIG__,frame=document.getElementById('codex-visualization'),key='lab-cellpose-qc-v1:'+cfg.dataset_id;
const status=document.getElementById('qc-storage'),scope=document.getElementById('qc-scope'),count=document.getElementById('qc-export-count'),load=document.getElementById('qc-load');
const buttons=[...document.querySelectorAll('[data-qc-download]')];
let current=null,storageOK=true,ready=false,revision=null,pending=null,nextRequest=0,countText='Loading review state…';
const recovery=document.getElementById('qc-recovery'),backupButton=document.getElementById('qc-backup'),resetButton=document.getElementById('qc-reset'),resetConfirm=document.getElementById('qc-reset-confirm');
let lastRaw=null,backupRaw=null,recovering=false,recoveryPending=null,awaitingLoad=true;
// v1.4: decisions are stored with the results (qc_review_state.json) when the viewer server offers it;
// localStorage remains a mirror and the fallback. Without a store the behaviour is unchanged.
const store=cfg.qc_store&&typeof fetch==='function'?cfg.qc_store:null;
let remoteOK=false,remoteRevision=null,saving=null,queued=null,initGeneration=0,unsaved=false,notice=null;
try{backupRaw=localStorage.getItem(key+':backup');}catch(e){}
backupButton.disabled=backupRaw===null;
const send=(type,extra={})=>frame.contentWindow.postMessage({type,dataset_id:cfg.dataset_id,...extra},'*');
function setStatus(text,error=false){status.textContent=text;status.style.color=error?'#a32d31':'#4b6072';}
function updateButtons(){buttons.forEach(b=>b.disabled=!ready||pending!==null);}
function invalidateExports(){ready=false;pending=null;updateButtons();count.textContent='Updating review state…';}
function beginRecovery(message){recovering=true;awaitingLoad=true;invalidateExports();recovery.hidden=false;send('qc-block');if(lastRaw!==null){backupRaw=lastRaw;backupButton.disabled=false;}setStatus(message+' Original saved data is retained. Load a valid QC JSON or explicitly start a new review in More options.',true);}
function readSaved(recover=true){
 try{lastRaw=localStorage.getItem(key);}catch(e){storageOK=false;setStatus('Local saving unavailable. Save QC decisions JSON before closing.',true);return current;}
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
function savedText(){return remoteOK?'QC decisions are saved with the results (qc_review_state.json). Save JSON to transfer them.':'QC decisions are saved in this viewer. Save JSON to transfer them.';}
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
  if(status===200){remoteRevision=state.revision;if(!queued&&state===current){unsaved=false;notice=null;writeLocal(state);setStatus('QC decisions saved with the results.');}}
  else if(status===409&&data?.state&&validState(data.state)){
   queued=null;invalidateExports();remoteRevision=data.state.revision;writeLocal(data.state);
   notice='QC changed in another result window. The latest saved decisions were loaded; please repeat your last action.';
   current=data.state;unsaved=false;send('qc-external',{state:current});setStatus(notice,true);
  }else{queued=null;remoteOK=false;saveLocally(current,'The result folder cannot store review decisions. ');}
 }).catch(()=>{queued=null;remoteOK=false;saveLocally(current,'Review storage became unavailable. ');}).finally(()=>{
  saving=null;if(queued&&remoteOK){const next=queued;queued=null;persist(next.state,next.replace);}
 });
}
function saveLocally(state,prefix=''){
 if(writeLocal(state)){unsaved=false;setStatus(prefix?prefix+'Decisions are saved in this viewer only; save QC decisions JSON to keep a copy.':'QC decisions saved in this viewer.',!!prefix);}
 else{unsaved=true;setStatus('Changes are in this window only. Save QC decisions JSON before closing.',true);}
}
function requestRecovery(state){awaitingLoad=true;recoveryPending={request_id:++nextRequest,expected_raw:lastRaw};invalidateExports();send('qc-block');send('qc-recover',{request_id:recoveryPending.request_id,state});}
for(const[id,label]of cfg.segmentation_options){const option=document.createElement('option');option.value=id;option.textContent=label;scope.append(option);}
scope.addEventListener('change',()=>{invalidateExports();send('qc-scope',{scope:scope.value});});
addEventListener('message',event=>{
 if(event.source!==frame.contentWindow||event.data?.dataset_id!==cfg.dataset_id)return;
 const m=event.data;
 if(m.type==='qc-ready'){initialize();}
 else if(m.type==='qc-loaded'){awaitingLoad=false;recovering=false;recovery.hidden=true;resetConfirm.checked=false;resetButton.disabled=true;
  if(notice)setStatus(notice,true);else if(storageOK||remoteOK)setStatus(savedText());}
 else if(m.type==='qc-recovery-needed'){beginRecovery(m.message);}
 else if(m.type==='qc-recovered'){
  if(!recoveryPending||m.request_id!==recoveryPending.request_id)return;
  const expected=recoveryPending.expected_raw;recoveryPending=null;
  if(!validState(m.state)){beginRecovery('Recovery state is invalid.');return;}
  let live=expected;
  try{live=localStorage.getItem(key);}catch(e){storageOK=false;}
  if(live!==expected){initialize();setStatus('QC changed in another window. Review the latest state before recovering.',true);return;}
  if(expected!==null){backupRaw=expected;backupButton.disabled=false;}
  current=m.state;
  try{if(expected!==null)localStorage.setItem(key+':backup',expected);localStorage.setItem(key,JSON.stringify(current));lastRaw=JSON.stringify(current);storageOK=true;unsaved=false;}
  catch(e){storageOK=false;unsaved=!remoteOK;setStatus('Recovery is in this window only. Original saved data is retained; export QC decisions JSON before closing.',true);}
  if(remoteOK)persist(current,true);
  send('qc-init',{state:current});
 }
 else if(m.type==='qc-error'){
  if(m.request_id!==undefined&&m.request_id!==pending?.request_id&&m.request_id!==recoveryPending?.request_id)return;
  if(m.request_id===recoveryPending?.request_id)recoveryPending=null;
  pending=null;updateButtons();count.textContent=countText;setStatus(String(m.message).slice(0,500),true);
 }
 else if(m.type==='qc-save'){
  if(!validState(m.state)||m.state.revision!==m.base_revision+1){invalidateExports();setStatus('Invalid QC state; changes were not saved.',true);return;}
  if(remoteOK){current=m.state;unsaved=true;persist(current);return;}
  const stored=storageOK?readSaved():current;
  if(stored===undefined)return;
  if(stored&&stored.revision!==m.base_revision){invalidateExports();current=stored;notice='QC changed in another result window. Latest decisions loaded; please repeat your last action.';send('qc-external',{state:stored});setStatus(notice,true);return;}
  current=m.state;notice=null;
  try{localStorage.setItem(key,JSON.stringify(current));lastRaw=JSON.stringify(current);storageOK=true;unsaved=false;setStatus('QC decisions saved in this viewer.');}
  catch(e){storageOK=false;unsaved=true;setStatus('Changes are in this window only. Save QC decisions JSON before closing.',true);}
 }else if(m.type==='qc-status'){
  if(awaitingLoad||recovering||recoveryPending||m.scope!==scope.value)return;
  if(!['revision','included_rows','total_rows','excluded_objects'].every(k=>Number.isSafeInteger(m[k])&&m[k]>=0)||m.included_rows>m.total_rows){invalidateExports();setStatus('Invalid export state. Reload the results before exporting.',true);return;}
  if(revision!==m.revision)pending=null;
  revision=m.revision;ready=true;updateButtons();
  countText=`${m.included_rows.toLocaleString()} / ${m.total_rows.toLocaleString()} measurement rows included · ${m.excluded_objects} excluded objects across this dataset`;
  count.textContent=pending?'Preparing export…':countText;
 }else if(m.type==='qc-export-response'){
  if(!pending||m.request_id!==pending.request_id)return;
  const request=pending;pending=null;updateButtons();count.textContent=countText;
  if(!ready||m.kind!==request.kind||m.scope!==scope.value||m.revision!==revision||typeof m.content!=='string'){
   setStatus('QC changed or the export failed. Please request the export again.',true);return;
  }
  try{download(m.kind,m.content,m.scope);}catch(e){setStatus('Export failed: '+String(e.message).slice(0,400),true);}
 }
});
addEventListener('storage',event=>{
 if(event.key!==key)return;
 // Never replace decisions that exist only in this window; the result-folder store reports conflicts itself.
 if(unsaved){notice='Another window saved different QC decisions. This window still holds unsaved changes; save QC decisions JSON before closing.';setStatus(notice,true);return;}
 if(remoteOK)return;
 initialize();
});
buttons.forEach(b=>b.addEventListener('click',()=>{
 if(!ready||pending)return;
 pending={request_id:++nextRequest,kind:b.dataset.qcDownload,scope:scope.value,revision};
 updateButtons();count.textContent='Preparing export…';send('qc-export-request',pending);
}));
function download(kind,content,exportScope){
 const ext=['decisions','backup'].includes(kind)?'json':'csv',prefix={included:'included_measurements',audit:'excluded_candidates',decisions:'qc_decisions',backup:'qc_recovery_backup'}[kind];
 const blob=new Blob([content],{type:ext==='json'?'application/json;charset=utf-8':'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=`${prefix}_${cfg.dataset_id.slice(0,10)}${kind==='included'?'_'+exportScope:''}.${ext}`;
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
}
backupButton.addEventListener('click',()=>{if(backupRaw!==null)download('backup',backupRaw,'all');});
resetConfirm.addEventListener('change',()=>{resetButton.disabled=!resetConfirm.checked;});
resetButton.addEventListener('click',()=>{if(resetConfirm.checked)requestRecovery(null);});
load.addEventListener('change',async()=>{const f=load.files?.[0];if(!f)return;try{if(f.size>=10000000)throw Error('QC JSON is too large');const state=JSON.parse(await f.text());if(!validState(state))throw Error('QC file belongs to a different dataset or is invalid. Nothing was imported.');if(recovering)requestRecovery(state);else{invalidateExports();send('qc-import',{state});}}catch(e){setStatus(e.message,true);}finally{load.value='';}});
})();
