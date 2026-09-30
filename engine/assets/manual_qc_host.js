(()=>{'use strict';
const cfg=__QC_HOST_CONFIG__,frame=document.getElementById('codex-visualization'),key='lab-cellpose-qc-v1:'+cfg.dataset_id;
const status=document.getElementById('qc-storage'),scope=document.getElementById('qc-scope'),count=document.getElementById('qc-export-count'),load=document.getElementById('qc-load');
const buttons=[...document.querySelectorAll('[data-qc-download]')];let files=null,current=null,storageOK=true;
const send=(type,extra={})=>frame.contentWindow.postMessage({type,dataset_id:cfg.dataset_id,...extra},'*');
function setStatus(text,error=false){status.textContent=text;status.style.color=error?'#a32d31':'#4b6072';}
function readSaved(){try{const raw=localStorage.getItem(key);return raw?JSON.parse(raw):null;}catch(e){storageOK=false;setStatus('Browser saving unavailable. Save QC decisions JSON before closing.',true);return null;}}
function validState(s){return s&&s.dataset_id===cfg.dataset_id&&s.source_csv_sha256===cfg.source_csv_sha256&&s.source_viewer_sha256===cfg.source_viewer_sha256&&Number.isSafeInteger(s.revision)&&s.revision>=0&&Array.isArray(s.excluded)&&Array.isArray(s.history)&&JSON.stringify(s).length<10000000;}
for(const[id,label]of cfg.segmentation_options){const option=document.createElement('option');option.value=id;option.textContent=label;scope.append(option);}
scope.addEventListener('change',()=>{files=null;buttons.forEach(b=>b.disabled=true);send('qc-scope',{scope:scope.value});});
addEventListener('message',event=>{
 if(event.source!==frame.contentWindow||event.data?.dataset_id!==cfg.dataset_id)return;
 const m=event.data;
 if(m.type==='qc-ready'){current=readSaved();send('qc-init',{state:current});}
 else if(m.type==='qc-loaded'){if(storageOK)setStatus('QC decisions are saved in this browser. Save JSON to transfer them.');}
 else if(m.type==='qc-error')setStatus(String(m.message).slice(0,500),true);
 else if(m.type==='qc-save'){
  if(!validState(m.state)||m.state.revision!==m.base_revision+1){setStatus('Invalid QC state; changes were not saved.',true);return;}
  const stored=storageOK?readSaved():current;
  if(stored&&stored.revision!==m.base_revision){current=stored;send('qc-external',{state:stored});setStatus('QC changed in another tab. Latest decisions loaded; please repeat your last action.',true);return;}
  current=m.state;
  try{localStorage.setItem(key,JSON.stringify(current));storageOK=true;setStatus('QC decisions saved in this browser.');}
  catch(e){storageOK=false;setStatus('Changes are in this tab only. Save QC decisions JSON before closing.',true);}
 }else if(m.type==='qc-exports'){
  if(m.scope!==scope.value||!['included_csv','audit_csv','decisions_json'].every(k=>typeof m[k]==='string'&&m[k].length<50000000))return;
  files={included:m.included_csv,audit:m.audit_csv,decisions:m.decisions_json};buttons.forEach(b=>b.disabled=false);
  count.textContent=`${m.included_rows.toLocaleString()} / ${m.total_rows.toLocaleString()} measurement rows included · ${m.excluded_objects} excluded candidates across this dataset`;
 }
});
addEventListener('storage',event=>{if(event.key===key){current=readSaved();send('qc-external',{state:current});setStatus('QC updated from another tab.');}});
buttons.forEach(b=>b.addEventListener('click',()=>{
 if(!files)return;const kind=b.dataset.qcDownload,ext=kind==='decisions'?'json':'csv',prefix={included:'included_measurements',audit:'excluded_candidates',decisions:'qc_decisions'}[kind];
 const blob=new Blob([files[kind]],{type:ext==='json'?'application/json;charset=utf-8':'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`${prefix}_${cfg.dataset_id.slice(0,10)}${kind==='included'?'_'+scope.value:''}.${ext}`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
}));
load.addEventListener('change',async()=>{const f=load.files?.[0];if(!f)return;try{if(f.size>10000000)throw Error('QC JSON is too large');const state=JSON.parse(await f.text());if(!validState(state))throw Error('QC file belongs to a different dataset or is invalid. Nothing was imported.');send('qc-import',{state});}catch(e){setStatus(e.message,true);}finally{load.value='';}});
})();
