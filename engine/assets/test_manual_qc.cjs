/* Run with node --test engine/assets/test_manual_qc.cjs; no browser or inference. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const LabQC = require('./manual_qc.js');
const hostCode = fs.readFileSync(path.join(__dirname, 'manual_qc_host.js'), 'utf8');
const bridgeCode = fs.readFileSync(path.join(__dirname, 'manual_qc_bridge.js'), 'utf8');

function harness(options={}) {
  const bundle = options.bundle||{dataset_id:'test-dataset', source_csv_sha256:'csv-hash', source_viewer_sha256:'viewer-hash',
    segmentation_channels:['A','B'], columns:['field','segmentation_channel','object_id','measurement_channel'],
    rows:[['f0','A','1','C1'],['f0','A','1','C2'],['f0','A','2','C1'],['f0','B','1','C1'],['f1','A','1','C1']]};
  const fields = options.fields||{f0:{objects:{A:[{id:1},{id:2}],B:[{id:1}]}}, f1:{objects:{A:[{id:1}],B:[]}}};
  const qc = LabQC.create(bundle, fields), queue = [], hostEvents = {}, childEvents = {};
  const blobs = [], downloads = [], messages = [], storage = new Map(), generations = {included:0,audit:0};
  const key='lab-cellpose-qc-v1:'+bundle.dataset_id;
  if(options.initial!==undefined)storage.set(key,options.initial);
  for (const [kind, method] of [['included','includedCSV'],['audit','auditCSV']]) {
    const original = qc[method]; qc[method] = (...args) => { generations[kind]++; return original(...args); };
  }
  const enqueue = (target, source, data) => { messages.push(data); queue.push({target, event:{source,data}}); };
  const host = {postMessage:data=>enqueue(hostEvents, child, data)};
  const child = {postMessage:data=>enqueue(childEvents, host, data)};
  function element() {
    const handlers = {};
    return {style:{},value:'',disabled:false,textContent:'',dataset:{},append(){},remove(){},
      addEventListener:(name,fn)=>handlers[name]=fn,
      trigger:(name)=>handlers[name]?.(),
      click(){if(!this.disabled)handlers.click?.();}};
  }
  const elements = Object.fromEntries(['qc-storage','qc-scope','qc-export-count','qc-load','qc-recovery','qc-backup','qc-reset','qc-reset-confirm'].map(id=>[id,element()]));
  elements['qc-scope'].value = 'all'; elements['codex-visualization'] = {contentWindow:child};
  const buttons = Object.fromEntries(['included','audit','decisions'].map(kind=>{
    const button = element(); button.dataset.qcDownload=kind;button.disabled=true;return [kind,button];
  }));
  const document = {getElementById:id=>elements[id],querySelectorAll:()=>Object.values(buttons),body:{append(){}},
    createElement:tag=>tag==='a'?{click(){downloads.push({name:this.download,blob:blobs[Number(this.href.slice(5))]});},remove(){}}:element()};
  const cfg = {...bundle, segmentation_options:[['A','A'],['B','B']]};
  vm.runInNewContext(hostCode.replace('__QC_HOST_CONFIG__',JSON.stringify(cfg)), {
    document,Blob,URL:{createObjectURL(blob){blobs.push(blob);return 'blob:'+(blobs.length-1);},revokeObjectURL(){}},
    setTimeout(){},addEventListener:(name,fn)=>hostEvents[name]=fn,
    localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>{if(options.quota)throw Error('Quota exceeded');storage.set(key,value);}}});
  const context = {LabQC:{...LabQC},parent:host,addEventListener:(name,fn)=>childEvents[name]=fn};
  vm.runInNewContext(bridgeCode, context);
  const bridge = context.LabQC.connect(qc,bundle,()=>{});
  function pump() { let steps=0; while(queue.length) {assert.ok(++steps<100);const {target,event}=queue.shift();target.message(event);} }
  function receive(data) {hostEvents.message({source:child,data:{dataset_id:bundle.dataset_id,...data}});}
  pump();
  return {bundle,qc,bridge,pump,receive,buttons,elements,downloads,messages,generations,storage,hostEvents,key};
}

test('damaged JSON and malformed history can recover from a valid import with the original backed up',async()=>{
  const reference=harness();reference.qc.toggle('f0','A',1);const saved=reference.qc.snapshot();
  for(const initial of ['{broken',JSON.stringify({...saved,history:[{action:'exclude',at:'invalid'}]})]){
    const h=harness({initial});assert.equal(h.bridge.ready(),false);assert.equal(h.buttons.included.disabled,true);
    assert.equal(h.storage.get(h.key),initial);
    const load=h.elements['qc-load'];load.files=[{size:100,text:async()=>JSON.stringify(saved)}];
    await load.trigger('change');h.pump();
    assert.equal(h.qc.excludedCount(),1);assert.equal(h.bridge.ready(),true);assert.equal(h.buttons.included.disabled,false);
    assert.equal(h.storage.get(h.key+':backup'),initial);
    h.buttons.included.click();h.pump();assert.equal((await h.downloads[0].blob.text()).split('\r\n').length,5);
  }
});

test('explicit reset backs up corrupt state; quota failure keeps the original and permits in-window export',async()=>{
  for(const quota of [false,true]){
    const initial='{original damaged state',h=harness({initial,quota});
    h.elements['qc-reset'].click();h.pump();assert.equal(h.bridge.ready(),false);
    h.elements['qc-reset-confirm'].checked=true;h.elements['qc-reset-confirm'].trigger('change');h.elements['qc-reset'].click();h.pump();
    assert.equal(h.qc.excludedCount(),0);assert.equal(h.buttons.included.disabled,false);
    if(quota){assert.equal(h.storage.get(h.key),initial);assert.match(h.elements['qc-storage'].textContent,/window only/);}
    else assert.equal(h.storage.get(h.key+':backup'),initial);
    h.elements['qc-backup'].click();assert.equal(await h.downloads.at(-1).blob.text(),initial);
    h.buttons.decisions.click();h.pump();assert.equal(JSON.parse(await h.downloads.at(-1).blob.text()).excluded.length,0);
  }
});

test('recovery cannot overwrite a concurrent saved review',()=>{
  const h=harness({initial:'{broken'}),state=h.qc.snapshot();state.revision=7;
  h.elements['qc-reset-confirm'].checked=true;h.elements['qc-reset-confirm'].trigger('change');h.elements['qc-reset'].click();
  h.storage.set(h.key,JSON.stringify(state));h.pump();
  assert.equal(h.qc.snapshot().revision,7);assert.equal(JSON.parse(h.storage.get(h.key)).revision,7);
});

test('history, revision and UTF-8 byte limits reject mutations atomically and keep exported states readable',()=>{
  const h=harness(),at='2026-09-30T00:00:00Z';
  for(const change of [s=>{s.revision=Number.MAX_SAFE_INTEGER;},s=>{s.history=Array.from({length:50000},()=>({action:'exclude',at}));},s=>{s.history=[{action:'note',at,padding:'x'.repeat(9999500)}];}]){
    const state=h.qc.snapshot();state.history=[];state.revision=0;change(state);h.qc.load(state);const before=JSON.stringify(h.qc.snapshot());
    if(state.history[0]?.padding){state.history[0].padding+='x'.repeat(9999900-Buffer.byteLength(JSON.stringify(state)));h.qc.load(state);}
    const exact=JSON.stringify(h.qc.snapshot());assert.throws(()=>h.qc.toggle('f0','A',1),/limit/);assert.equal(JSON.stringify(h.qc.snapshot()),exact);
    h.qc.load(JSON.parse(exact));assert.equal(h.qc.excludedCount(),0);
  }
  const unicode=h.qc.snapshot();unicode.history=[{action:'note',at,padding:'汉'.repeat(3400000)}];
  assert.throws(()=>h.qc.load(unicode),/large/);
});

test('import and undo do not consume prior decisions or undo state when a limit is reached',()=>{
  const h=harness(),s=h.qc.snapshot();s.history=Array.from({length:49999},()=>({action:'note',at:'2026-09-30T00:00:00Z'}));h.qc.load(s);
  h.qc.toggle('f0','A',1);const before=JSON.stringify(h.qc.snapshot());assert.equal(h.qc.canUndo(),true);
  assert.throws(()=>h.qc.undoLast(),/limit/);assert.throws(()=>h.qc.importState(s),/limit/);
  assert.equal(h.qc.canUndo(),true);assert.equal(JSON.stringify(h.qc.snapshot()),before);
  h.bridge.change(()=>h.qc.toggle('f0','A',2));h.pump();assert.match(h.elements['qc-storage'].textContent,/limit/);
});

test('spreadsheet formulas are inert text while signed scientific measurements remain numeric',()=>{
  for(const reason of ['=1+1','+1+2','-1+2','@SUM(A1:A2)','\t=1+1','\r=1+1','\n=1+1','\u00a0=1+1']){
    const h=harness(),s=h.qc.snapshot();s.excluded=[{field:'f0',segmentation_channel:'A',object_id:'1',reason,excluded_at:'2026-09-30T00:00:00Z'}];h.qc.importState(s);
    assert.ok(h.qc.auditCSV().includes('"\''+reason+'"'));assert.equal(h.qc.decision('f0','A',1).reason,reason);
  }
  assert.equal(LabQC.csv(['field','corrected_mean','corrected_sum'],[['=1+1','-12.5','-1.2e+3']],true),'"field","corrected_mean","corrected_sum"\r\n"\'=1+1","-12.5","-1.2e+3"\r\n');
});

test('exports are generated on demand; an exclusion removes only its FOV/input/object rows', async()=>{
  const h=harness(); assert.deepEqual(h.generations,{included:0,audit:0});
  h.bridge.change(()=>h.qc.toggle('f0','A',1)); h.pump();
  assert.deepEqual(h.generations,{included:0,audit:0});
  h.buttons.included.click(); h.pump();
  assert.deepEqual(h.generations,{included:1,audit:0});
  assert.equal(await h.downloads[0].blob.text(), '"field","segmentation_channel","object_id","measurement_channel"\r\n"f0","A","2","C1"\r\n"f0","B","1","C1"\r\n"f1","A","1","C1"\r\n');
  h.bridge.change(()=>h.qc.undoLast()); h.pump();
  h.buttons.decisions.click(); h.pump();
  assert.equal(JSON.parse(await h.downloads[1].blob.text()).excluded.length,0);
  assert.equal(JSON.parse(await h.downloads[1].blob.text()).revision,2);
});

test('an export above the old 50-million-character limit downloads the current content', async()=>{
  const h=harness();h.buttons.included.click();h.pump();
  h.qc.includedCSV=()=> 'CURRENT\n'+'x'.repeat(50000000);
  h.bridge.change(()=>h.qc.toggle('f0','A',1));h.pump();
  h.buttons.included.click();h.pump();
  const blob=h.downloads.at(-1).blob;
  assert.equal(blob.size,50000008);assert.equal(await blob.slice(0,8).text(),'CURRENT\n');
  assert.equal(h.downloads.length,2);assert.equal(h.buttons.included.disabled,false);
});

test('a scope change cancels an outstanding export; each new request has a fresh identity', async()=>{
  const h=harness();h.buttons.included.click();
  h.elements['qc-scope'].value='B';h.elements['qc-scope'].trigger('change');h.pump();
  assert.equal(h.downloads.length,0);
  h.buttons.included.click();h.pump();
  assert.equal(h.downloads.length,1);assert.ok(h.downloads[0].name.endsWith('_B.csv'));
  assert.equal((await h.downloads[0].blob.text()).split('\r\n').length,3);
});

test('a QC change cancels an outstanding export; stale and duplicate replies cannot download',()=>{
  const h=harness();h.buttons.included.click();
  h.bridge.change(()=>h.qc.toggle('f0','A',1));h.pump();assert.equal(h.downloads.length,0);
  h.buttons.included.click();h.pump();assert.equal(h.downloads.length,1);
  const response=h.messages.findLast(m=>m.type==='qc-export-response');h.receive(response);
  assert.equal(h.downloads.length,1);
});

test('malformed replies fail visibly and allow a new request without retaining a prior CSV',()=>{
  const h=harness();h.buttons.included.click();
  const request=h.messages.findLast(m=>m.type==='qc-export-request');
  h.receive({...request,type:'qc-export-response',content:null});
  assert.match(h.elements['qc-storage'].textContent,/export failed/);h.pump();
  assert.equal(h.downloads.length,0);assert.equal(h.buttons.included.disabled,false);
  h.buttons.included.click();h.pump();assert.equal(h.downloads.length,1);
});

test('another window changing QC invalidates pending exports and restores the saved revision',()=>{
  const h=harness();h.buttons.included.click();
  const saved=h.qc.snapshot();saved.revision=10;
  const key='lab-cellpose-qc-v1:'+h.bundle.dataset_id;
  h.storage.set(key,JSON.stringify(saved));h.hostEvents.storage({key});h.pump();
  assert.equal(h.downloads.length,0);assert.equal(h.qc.snapshot().revision,10);
  h.buttons.included.click();h.pump();assert.equal(h.downloads.length,1);
});

test('QC JSON import updates exports; a mismatched dataset leaves current decisions intact', async()=>{
  const h=harness();h.bridge.change(()=>h.qc.toggle('f0','A',1));h.pump();
  const saved=h.qc.snapshot();h.bridge.change(()=>h.qc.undoLast());h.pump();
  const load=h.elements['qc-load'];load.files=[{size:100,text:async()=>JSON.stringify(saved)}];
  await load.trigger('change');h.pump();assert.equal(h.qc.excludedCount(),1);
  load.files=[{size:100,text:async()=>JSON.stringify({...saved,dataset_id:'wrong'})}];
  await load.trigger('change');h.pump();assert.equal(h.qc.excludedCount(),1);
  assert.match(h.elements['qc-storage'].textContent,/different dataset/);
  h.buttons.audit.click();h.pump();assert.match(await h.downloads[0].blob.text(),/"f0","A","1"/);
});

test('background changes invalidate pending exports and survive host storage and reopening',async()=>{
 const bundle={dataset_id:'background-test',source_csv_sha256:'raw',source_viewer_sha256:'fields',segmentation_channels:['A'],columns:['field','segmentation_channel','object_id','region','measurement_channel','area_pixels','raw_mean','raw_sum','background_median','corrected_mean','corrected_sum'],rows:[['f0','A','1','whole','C1','2','25','50','10','15','30']]};
 const fields={f0:{objects:{A:[{id:1}]},background:{valid:true,medians:{C1:10},means:{C1:30}}}};
 const h=harness({bundle,fields});h.buttons.included.click();
 h.bridge.change(()=>h.qc.setEstimator('C1','mean'));h.pump();assert.equal(h.downloads.length,0);
 assert.equal(JSON.parse(h.storage.get(h.key)).background_estimators.C1,'mean');
 h.buttons.included.click();h.pump();assert.match(await h.downloads[0].blob.text(),/"-5","-10"/);
 const reopened=harness({bundle,fields,initial:h.storage.get(h.key)});assert.equal(reopened.qc.estimator('C1'),'mean');
 reopened.buttons.decisions.click();reopened.pump();assert.equal(JSON.parse(await reopened.downloads[0].blob.text()).background_estimators.C1,'mean');
});
