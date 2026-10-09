/* 1.4 review-state storage: result-folder store, browser mirror/fallback and multi-window safety.
   Run with node --test engine/assets/test_qc_store.cjs; no browser or inference. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const LabQC = require('./manual_qc.js');
const hostCode = fs.readFileSync(path.join(__dirname, 'manual_qc_host.js'), 'utf8');
const bridgeCode = fs.readFileSync(path.join(__dirname, 'manual_qc_bridge.js'), 'utf8');

const bundle = {dataset_id:'store-test', source_csv_sha256:'csv', source_viewer_sha256:'viewer', segmentation_channels:['A'],
  columns:['field','segmentation_channel','object_id','measurement_channel'], rows:[['f0','A','1','C1'],['f0','A','2','C1'],['f0','A','3','C1']]};
const fields = {f0:{objects:{A:[{id:1},{id:2},{id:3}]}}};
const key = 'lab-cellpose-qc-v1:'+bundle.dataset_id;
const tick = () => new Promise(resolve => setImmediate(resolve));

/* A fake viewer server implementing launcher.ResultHandler's review-state rules. */
function fakeServer(initial=null) {
  const server = {state: initial, requests: [], fail: null, hold: false, held: []};
  server.fetch = async (url, options={}) => {
    assert.equal(url, 'qc_review_state.json'); assert.equal(options.headers['X-LabCellpose-QC'], 'token');
    const body = options.body ? JSON.parse(options.body) : null;
    server.requests.push({method:options.method, body});
    if (server.hold && options.method === 'POST') await new Promise(resolve => server.held.push(resolve));
    const reply = (status, value) => ({status, json: async () => value});
    if (server.fail) return reply(server.fail, {error:'read-only folder'});
    if (options.method === 'GET') return reply(200, {state: server.state, damaged: false});
    const {state, base_revision, replace} = body;
    if (server.state && !replace && JSON.stringify(server.state) !== JSON.stringify(state) && (base_revision === null || server.state.revision !== base_revision))
      return reply(409, {state: server.state, conflict: true});
    server.state = state; return reply(200, {ok: true, revision: state.revision});
  };
  return server;
}

function harness({server=null, storage=new Map(), quota=false, initial}={}) {
  const qc = LabQC.create(bundle, fields), queue = [], hostEvents = {}, childEvents = {};
  if (initial !== undefined) storage.set(key, initial);
  const enqueue = (target, source, data) => queue.push({target, event:{source, data}});
  const host = {postMessage:data=>enqueue(hostEvents, child, data)}, child = {postMessage:data=>enqueue(childEvents, host, data)};
  const element = () => { const handlers = {}; return {style:{},value:'',disabled:false,textContent:'',dataset:{},append(){},remove(){},
    addEventListener:(n,f)=>handlers[n]=f, trigger:n=>handlers[n]?.(), click(){if(!this.disabled)handlers.click?.();}}; };
  const elements = Object.fromEntries(['qc-storage','qc-scope','qc-export-count','qc-load','qc-recovery','qc-backup','qc-reset','qc-reset-confirm'].map(id=>[id,element()]));
  elements['qc-scope'].value = 'all'; elements['codex-visualization'] = {contentWindow: child};
  const buttons = ['included','audit','decisions'].map(kind=>{const b = element(); b.dataset.qcDownload = kind; b.disabled = true; return b;});
  const document = {getElementById:id=>elements[id], querySelectorAll:()=>buttons, body:{append(){}}, createElement:()=>element()};
  const cfg = {...bundle, segmentation_options:[['A','A']], qc_store: server ? {token:'token', path:'qc_review_state.json'} : null};
  const context = {document, Blob, URL:{createObjectURL:()=>'blob:0', revokeObjectURL(){}}, setTimeout(){}, addEventListener:(n,f)=>hostEvents[n]=f,
    localStorage:{getItem:k=>storage.get(k)??null, setItem:(k,v)=>{if(quota)throw Error('QuotaExceededError'); storage.set(k,v);}}};
  if (server) context.fetch = server.fetch;
  vm.runInNewContext(hostCode.replace('__QC_HOST_CONFIG__', JSON.stringify(cfg)), context);
  const childContext = {LabQC:{...LabQC}, parent:host, addEventListener:(n,f)=>childEvents[n]=f};
  vm.runInNewContext(bridgeCode, childContext);
  const bridge = childContext.LabQC.connect(qc, bundle, ()=>{});
  const pump = () => { let steps = 0; while (queue.length) { assert.ok(++steps < 200); const {target, event} = queue.shift(); target.message(event); } };
  const settle = async () => { for (let i = 0; i < 20; i++) { pump(); await tick(); } pump(); };
  pump();   // deliver qc-ready (and, without a store, the initial state) like the page load does
  if (!server) assert.equal(bridge.ready(), true);
  return {qc, bridge, pump, settle, storage, status:()=>elements['qc-storage'].textContent, hostEvents, buttons};
}

const stateWith = (revision, ids) => ({schema_version:1, dataset_id:bundle.dataset_id, source_csv_sha256:'csv', source_viewer_sha256:'viewer', revision,
  excluded: ids.map(id=>({field:'f0', segmentation_channel:'A', object_id:String(id), reason:'Manual exclusion', excluded_at:'2026-10-08T00:00:00Z'})), history: []});

test('re-importing the review\'s own saved JSON does not duplicate its history', ()=>{
  const qc = LabQC.create(bundle, fields);
  for (let i = 0; i < 6; i++) qc.toggle('f0','A',1+(i%3));
  const saved = JSON.parse(JSON.stringify(qc.snapshot()));
  qc.importState(saved); qc.importState(JSON.parse(JSON.stringify(qc.snapshot())));
  assert.equal(qc.snapshot().history.length, 6 + 2);
  const other = LabQC.create(bundle, fields); other.toggle('f0','A',2,'Second reviewer');
  qc.importState(other.snapshot());                        // a different review still contributes its entries
  assert.equal(qc.snapshot().history.length, 8 + 1 + 1);
  assert.equal(qc.excludedCount(), 1);
});

test('decisions are saved with the results; a full browser quota no longer blocks saving', async()=>{
  const server = fakeServer(), h = harness({server, quota:true}); await h.settle();
  h.bridge.change(()=>h.qc.toggle('f0','A',1)); await h.settle();
  assert.equal(server.state.revision, 1); assert.equal(server.state.excluded.length, 1);
  assert.match(h.status(), /saved with the results/);
  assert.doesNotMatch(h.status(), /window only/);
});

test('browser-only decisions from 1.3 are migrated into the result folder', async()=>{
  const server = fakeServer(), h = harness({server, initial: JSON.stringify(stateWith(4, [2]))}); await h.settle();
  assert.equal(h.qc.excludedCount(), 1);
  assert.equal(server.state.revision, 4); assert.equal(server.requests.at(-1).body.base_revision, null);
});

test('a newer result-folder state wins over the browser copy and refreshes it', async()=>{
  const server = fakeServer(stateWith(9, [1,3])), h = harness({server, initial: JSON.stringify(stateWith(2, [2]))}); await h.settle();
  assert.equal(h.qc.snapshot().revision, 9); assert.equal(JSON.parse(h.storage.get(key)).revision, 9);
  assert.equal(server.requests.filter(r=>r.method==='POST').length, 0);
});

test('damaged browser copy recovers from a valid result-folder state and is backed up', async()=>{
  const server = fakeServer(stateWith(3, [1])), h = harness({server, initial:'{damaged'}); await h.settle();
  assert.equal(h.qc.excludedCount(), 1); assert.equal(h.bridge.ready(), true);
  assert.equal(h.storage.get(key+':backup'), '{damaged');
});

test('saves are sent one at a time and coalesced, so rapid clicks never look like conflicts', async()=>{
  const server = fakeServer(), h = harness({server}); await h.settle();
  server.hold = true;
  h.bridge.change(()=>h.qc.toggle('f0','A',1)); h.pump(); await tick();
  h.bridge.change(()=>h.qc.toggle('f0','A',2)); h.pump();
  h.bridge.change(()=>h.qc.toggle('f0','A',3)); h.pump();
  assert.equal(server.requests.filter(r=>r.method==='POST').length, 1);
  server.hold = false; server.held.splice(0).forEach(resolve=>resolve()); await h.settle();
  const posts = server.requests.filter(r=>r.method==='POST');
  assert.equal(posts.length, 2); assert.equal(posts[1].body.base_revision, 1); assert.equal(posts[1].body.state.revision, 3);
  assert.equal(server.state.excluded.length, 3); assert.match(h.status(), /saved with the results/);
});

test('a save conflict loads the other window\'s decisions and the warning stays visible', async()=>{
  const server = fakeServer(), h = harness({server}); await h.settle();
  server.state = stateWith(5, [3]);                         // another window saved meanwhile
  h.bridge.change(()=>h.qc.toggle('f0','A',1)); await h.settle();
  assert.equal(h.qc.snapshot().revision, 5); assert.equal(h.qc.isExcluded('f0','A',3), true);
  assert.match(h.status(), /another result window/);
});

test('an unwritable result folder falls back to browser storage with a visible notice', async()=>{
  const server = fakeServer(), h = harness({server}); await h.settle();
  server.fail = 507;
  h.bridge.change(()=>h.qc.toggle('f0','A',2)); await h.settle();
  assert.equal(JSON.parse(h.storage.get(key)).excluded.length, 1);
  assert.match(h.status(), /cannot store review decisions/);
  h.bridge.change(()=>h.qc.toggle('f0','A',3)); await h.settle();      // later saves use the browser copy
  assert.equal(JSON.parse(h.storage.get(key)).excluded.length, 2);
});

test('without a store: another window cannot silently replace this window\'s unsaved decisions', ()=>{
  const storage = new Map(), a = harness({storage, quota:true});
  a.bridge.change(()=>a.qc.toggle('f0','A',1)); a.pump();
  assert.equal(a.qc.isExcluded('f0','A',1), true); assert.match(a.status(), /window only/);
  storage.set(key, JSON.stringify(stateWith(7, [3])));                 // window B saved
  a.hostEvents.storage({key}); a.pump();
  assert.equal(a.qc.isExcluded('f0','A',1), true); assert.equal(a.qc.isExcluded('f0','A',3), false);
  assert.match(a.status(), /unsaved changes/);
});

test('without a store: the conflict warning is not replaced by the saved message', ()=>{
  const storage = new Map(), a = harness({storage}); a.bridge.change(()=>a.qc.toggle('f0','A',1)); a.pump();
  assert.equal(JSON.parse(storage.get(key)).revision, 1);
  storage.set(key, JSON.stringify(stateWith(9, [2])));
  a.bridge.change(()=>a.qc.toggle('f0','A',3)); a.pump();
  assert.equal(a.qc.snapshot().revision, 9); assert.match(a.status(), /another result window/);
});
