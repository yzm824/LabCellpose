/* 2.0 export contents: regions, channels and columns of the included CSV, one row per measurement or per object.
   Run with node --test engine/assets/test_export_contents.cjs; no browser or inference. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const LabQC = require('./manual_qc.js');
const LabExport = require('./export_table.js');
const Background = require('./background_stats.js');
const read = name => fs.readFileSync(path.join(__dirname, name), 'utf8');

const COLUMNS = ['field','segmentation_channel','object_id','region','measurement_channel','area_pixels','raw_mean','background_median','background_mean',
  'background_estimator','background_value','corrected_mean','raw_sum','corrected_sum','saturated_pixels','saturation_limit','touches_image_edge',
  'background_valid','expert_validated','exposure_seconds'];
const config = {title: 'RY26 CA vs DN', segmentation_channels: ['C1','C2'],
  channels: [{id:'C1',label:'C1 · mNG',measure:true},{id:'C2',label:'C2 · mCherry',measure:true},{id:'C3',label:'BF',measure:false}],
  fields: [{id:'f0',path:'/data/run.zip',member:'Exp/CA/Image 1.tif',label:'Exp/CA/Image 1.tif'},{id:'f1',path:'/data/DN/=evil.tif',label:'DN/=evil.tif'}]};
const stats = {f0:{valid:true,medians:{C1:10,C2:20},means:{C1:12,C2:25}}, f1:{valid:true,medians:{C1:11,C2:21},means:{C1:13,C2:26}}};
const objects = {f0:{C1:[{id:1},{id:2}],C2:[{id:1}]}, f1:{C1:[{id:1}],C2:[]}};
const fields = Object.fromEntries(Object.entries(objects).map(([f,o]) => [f, {objects:o, background:stats[f]}]));
const AREA = {whole:100, edge:60, interior:40};
function bundle() {
  const rows = [];
  for (const [f, bySeg] of Object.entries(objects)) for (const [seg, list] of Object.entries(bySeg)) for (const o of list) for (const region of ['whole','edge','interior']) {
    const empty = f === 'f0' && seg === 'C1' && o.id === 2 && region === 'interior';   // a small object without interior pixels
    for (const [k, ch] of ['C1','C2'].entries()) {
      const area = empty ? '' : AREA[region], raw = empty ? '' : 100 + 10*o.id + k + (region === 'edge' ? 0.5 : 0), bg = stats[f].medians[ch];
      rows.push([f, seg, String(o.id), region, ch, String(area), String(raw), String(bg), String(stats[f].means[ch]), 'median', String(bg),
        empty ? '' : String(raw - bg), empty ? '' : String(raw*area), empty ? '' : String(raw*area - area*bg), empty ? '' : '0', '65535',
        o.id === 2 ? 'True' : 'False', 'True', 'False', ch === 'C1' ? '0.5' : '0.25']);
    }
  }
  return {dataset_id:'export-test-dataset', source_csv_sha256:'csv', source_viewer_sha256:'viewer', segmentation_channels:['C1','C2'], columns:COLUMNS, rows};
}
const parse = text => text.replace(/^﻿/, '').trimEnd().split('\r\n').map(line => JSON.parse('[' + line + ']'));
const make = () => { const b = bundle(); return {b, qc: LabQC.create(b, fields, config)}; };
const KEY = {layout:'long', regions:['whole'], channels:['C1','C2'], columns:['image_name','image_folder','measurement_label','raw_mean','background_estimator','background_value','corrected_mean']};

test('all columns, one row per measurement, is byte-identical to the 1.4 included CSV', () => {
  const {b, qc} = make(), background = Background.create(b, fields);
  const reference = rows => LabQC.csv(background.columns, rows.map(r => background.exportRow(r, {})), true);
  assert.equal(qc.includedCSV('all'), reference(b.rows));
  assert.equal(qc.includedCSV('all', null), reference(b.rows));
  assert.equal(qc.includedCSV('all', LabExport.defaults(LabExport.check(qc.exportSchema()))), reference(b.rows));
  qc.toggle('f0','C1',1);
  assert.equal(qc.includedCSV('C1'), reference(b.rows.filter(r => r[1] === 'C1' && !(r[0] === 'f0' && r[2] === '1'))));
  assert.ok(!qc.includedCSV('all').startsWith('﻿'));
});

test('key values: whole ROI, readable names and the background actually used', () => {
  const {qc} = make(), table = parse(qc.includedCSV('all', KEY));
  assert.deepEqual(table[0], ['field','image_name','image_folder','segmentation_channel','object_id','region','measurement_channel','measurement_label',
    'raw_mean','background_estimator','background_value','corrected_mean']);
  assert.equal(table.length - 1, 4 * 2);
  assert.ok(table.slice(1).every(r => r[5] === 'whole'));
  assert.deepEqual(table[1], ['f0','Image 1.tif','CA','C1','1','whole','C1','C1 · mNG','110','median','10','100']);
  const evil = table.find(r => r[0] === 'f1');
  assert.deepEqual(evil.slice(1, 3), ["'=evil.tif", 'DN']);   // a formula-like file name stays inert text
  assert.equal(LabExport.presetName(LabExport.check(qc.exportSchema()), qc.exportOptions(KEY)), 'key');
});

test('one row per object holds the same numbers as one row per measurement', () => {
  const {qc} = make(), all = {layout:'wide', columns: LabExport.check(qc.exportSchema()).values, regions:['whole','edge','interior'], channels:['C1','C2']};
  const long = parse(qc.includedCSV('all', {...all, layout:'long'})), wide = parse(qc.includedCSV('all', all));
  assert.equal(wide.length - 1, 4);
  const header = wide[0], at = name => header.indexOf(name);
  assert.deepEqual(header.slice(0, 9), ['field','segmentation_channel','object_id','touches_image_edge','background_valid','expert_validated',
    'whole_area_pixels','edge_area_pixels','interior_area_pixels']);
  assert.ok(header.includes('C1_mNG_background_value') && header.includes('C2_mCherry_edge_corrected_mean'));
  assert.equal(new Set(header).size, header.length);
  const lc = long[0];
  for (const row of long.slice(1)) {
    const object = wide.find(w => w[0] === row[0] && w[1] === row[1] && w[2] === row[2]), prefix = row[4] === 'C1' ? 'C1_mNG' : 'C2_mCherry';
    for (const name of ['raw_mean','corrected_mean','raw_sum','corrected_sum','saturated_pixels'])
      assert.equal(object[at(`${prefix}_${row[3]}_${name}`)], row[lc.indexOf(name)], name);
    for (const name of ['background_median','background_mean','background_value','exposure_seconds','saturation_limit'])
      assert.equal(object[at(`${prefix}_${name}`)], row[lc.indexOf(name)], name);
    assert.equal(object[at(`${row[3]}_area_pixels`)], row[lc.indexOf('area_pixels')]);
  }
  const small = wide.find(w => w[0] === 'f0' && w[1] === 'C1' && w[2] === '2');
  assert.equal(small[at('interior_area_pixels')], '');
  assert.equal(small[at('C1_mNG_interior_raw_mean')], '');
});

test('regions, channels, QC exclusions and the background estimator shape every layout', () => {
  const {qc} = make();
  qc.setEstimator('C1', 'mean'); qc.toggle('f0','C1',2);
  const key = parse(qc.includedCSV('all', KEY)), row = key.find(r => r[0] === 'f0' && r[3] === 'C1' && r[6] === 'C1');
  assert.deepEqual(row.slice(8), ['110','mean','12','98']);
  assert.ok(!key.some(r => r[0] === 'f0' && r[3] === 'C1' && r[4] === '2'));
  const some = parse(qc.includedCSV('C2', {...KEY, regions:['edge','interior'], channels:['C2']}));
  assert.ok(some.slice(1).every(r => r[3] === 'C2' && r[6] === 'C2' && ['edge','interior'].includes(r[5])));
  assert.equal(some.length - 1, 2);
  const wide = parse(qc.includedCSV('all', {...KEY, layout:'wide'}));
  assert.equal(wide.length - 1, 3);
  assert.equal(qc.exportShape('all', {...KEY, layout:'wide'}).rows, 3);
  assert.equal(qc.exportShape('all', KEY).rows, 6);
  assert.equal(qc.exportShape('all', {...KEY, layout:'wide'}).columns.length, wide[0].length);
});

test('a byte-order mark is added only when readable names bring non-ASCII text', () => {
  const {qc} = make();
  assert.ok(qc.includedCSV('all', KEY).startsWith('﻿'));
  assert.ok(!qc.includedCSV('all', {...KEY, columns:['raw_mean','corrected_mean']}).startsWith('﻿'));
  const ascii = LabQC.create(bundle(), fields, {...config, channels: config.channels.map(c => ({...c, label: c.id}))});
  assert.ok(!ascii.includedCSV('all', KEY).startsWith('﻿'));
});

test('invalid or unknown export choices are rejected', () => {
  const {qc} = make();
  for (const bad of [{...KEY, columns:['__proto__']}, {...KEY, columns:['constructor']}, {...KEY, columns:['raw_mean','raw_mean']},
    {...KEY, regions:[]}, {...KEY, channels:[]}, {...KEY, channels:['C3']}, {...KEY, regions:['nucleus']}, {...KEY, layout:'pivot'},
    {...KEY, columns:'raw_mean'}, [], 'all', 7])
    assert.throws(() => qc.includedCSV('all', bad), /export|Choose/i, JSON.stringify(bad));
  assert.throws(() => LabExport.check({columns:['field'], values:[], names:[], regions:[], channels:[]}), /schema/);
  assert.throws(() => LabExport.check({...qc.exportSchema(), channels:[['C1']]}), /schema/);
});

test('channel prefixes are readable, ASCII and unique', () => {
  const schema = channels => ({channels});
  assert.deepEqual([...LabExport.prefixes(schema([['C1','C1 · mNG'],['C2','FITC'],['C3','C3 · 绿色'],['C4','C4']])).values()], ['C1_mNG','C2_FITC','C3','C4']);
  assert.deepEqual([...LabExport.prefixes(schema([['C1','x'],['C1_x','']])).values()], ['C1','C1_x']);
});

test('presets: detection and the fallback for results without a recorded background value', () => {
  const {qc} = make(), schema = LabExport.check(qc.exportSchema());
  assert.equal(LabExport.presetName(schema, LabExport.defaults(schema)), 'all');
  assert.equal(LabExport.presetName(schema, {...LabExport.defaults(schema), regions:['whole']}), 'custom');
  assert.equal(LabExport.suffix(schema, qc.exportOptions({...KEY, layout:'wide', channels:['C1']})), '_key_values_per_object_C1');
  const legacy = {...bundle(), columns: COLUMNS.filter(c => !['raw_sum','corrected_sum','background_mean','background_estimator','background_value'].includes(c))};
  legacy.rows = bundle().rows.map(r => r.filter((_, i) => legacy.columns.includes(COLUMNS[i])));
  const old = LabExport.check(LabQC.create(legacy, fields, config).exportSchema());
  assert.deepEqual(LabExport.preset(old, 'key').columns.sort(), ['background_median','corrected_mean','image_folder','image_name','measurement_label','raw_mean']);
});

/* The export view with a minimal DOM: cards, storage, requests, preview and file names. */
class El {
  constructor(tag) { Object.assign(this, {tagName:tag.toUpperCase(), children:[], attrs:{}, handlers:{}, style:{}, dataset:{}, textContent:'', value:'', checked:false, disabled:false, className:''}); }
  append(...c) { this.children.push(...c); } replaceChildren(...c) { this.children = [...c]; } remove() {}
  setAttribute(k, v) { this.attrs[k] = String(v); } getAttribute(k) { return this.attrs[k] ?? null; }
  addEventListener(n, f) { (this.handlers[n] ??= []).push(f); } fire(n) { (this.handlers[n] || []).forEach(f => f({target:this})); }
  click() { if (!this.disabled) this.fire('click'); }
  *walk() { yield this; for (const c of this.children) if (c instanceof El) yield* c.walk(); }
}
function dock({storage = new Map(), title = config.title} = {}) {
  const b = bundle(), qc = LabQC.create(b, fields, config), queue = [], hostEvents = {}, childEvents = {}, blobs = [], downloads = [], messages = [];
  const enqueue = (target, source, data) => { messages.push(data); queue.push({target, event:{source, data}}); };
  const host = {postMessage: data => enqueue(hostEvents, child, data)}, child = {postMessage: data => enqueue(childEvents, host, data)};
  const ids = {}; for (const id of ['qc-storage','qc-scope','qc-export-count','qc-load','qc-recovery','qc-backup','qc-reset','qc-reset-confirm','qc-contents-panel','qc-contents-summary','export-preview','export-shape','export-file','qc-progress']) ids[id] = new El('div');
  ids['qc-scope'].value = 'all'; ids['codex-visualization'] = {contentWindow: child};
  const buttons = ['included','audit','decisions'].map(kind => { const e = new El('button'); e.dataset.qcDownload = kind; e.disabled = true; return e; });
  const document = {getElementById: id => ids[id], querySelectorAll: () => buttons, body: {append() {}},
    createElement: tag => { const e = new El(tag); if (tag === 'a') e.click = function() { downloads.push({name: this.download, blob: blobs[Number(this.href.slice(5))]}); }; return e; }};
  const localStorage = {getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, String(v))};
  const context = vm.createContext({document, Blob, URL:{createObjectURL: x => { blobs.push(x); return 'blob:' + (blobs.length - 1); }, revokeObjectURL() {}},
    setTimeout() {}, addEventListener: (n, f) => hostEvents[n] = f, localStorage});
  const cfg = {dataset_id: b.dataset_id, source_csv_sha256: 'csv', source_viewer_sha256: 'viewer', segmentation_options: [['C1','C1 · mNG'],['C2','C2 · mCherry']], qc_store: null, title};
  vm.runInContext(read('export_table.js') + '\n' + read('export_panel.js') + '\n' + read('manual_qc_host.js').replace('__QC_HOST_CONFIG__', JSON.stringify(cfg)), context);
  const childContext = {LabQC: {...LabQC}, parent: host, addEventListener: (n, f) => childEvents[n] = f};
  vm.runInNewContext(read('manual_qc_bridge.js'), childContext);
  const bridge = childContext.LabQC.connect(qc, b, () => {});
  const pump = () => { let steps = 0; while (queue.length) { assert.ok(++steps < 200); const {target, event} = queue.shift(); target.message(event); } };
  pump();
  const panel = ids['qc-contents-panel'], find = pred => [...panel.walk()].find(pred);
  const button = text => find(e => e.tagName === 'BUTTON' && (e.textContent === text || e.children[0]?.textContent === text));   // a card is labelled by its first line
  const box = value => find(e => e.tagName === 'INPUT' && e.value === value);
  const toggle = value => { const e = box(value); e.checked = !e.checked; e.fire('change'); pump(); };
  const save = async kind => { buttons.find(e => e.dataset.qcDownload === kind).click(); pump(); const d = downloads.at(-1); return {name: d.name, text: await d.blob.text()}; };
  const text = e => [e.textContent, ...e.children.filter(c => c instanceof El).map(text)].join('|');
  return {qc, bridge, pump, ids, buttons, button, box, toggle, save, storage, downloads, messages, summary: () => ids['qc-contents-summary'].textContent,
    view: open => { context.labExportView(open); pump(); }, preview: () => text(ids['export-preview'])};
}

test('the export view offers ready-made tables, remembers the choice in this browser and names files by the analysis title', async () => {
  const d = dock();
  assert.equal(d.summary(), 'Everything');
  assert.equal((await d.save('included')).name, 'RY26_CA_vs_DN_included.csv');
  d.button('Key values').click(); d.pump();
  assert.equal(d.summary(), 'Key values');
  const key = await d.save('included');
  assert.equal(key.name, 'RY26_CA_vs_DN_included_key_values.csv');
  assert.equal(parse(key.text)[0].length, 12);
  d.button('One row per cell').click(); d.toggle('C2'); d.pump();
  assert.equal(d.summary(), 'One row per cell · 1 of 2 channels');
  const wide = await d.save('included');
  assert.equal(wide.name, 'RY26_CA_vs_DN_included_key_values_per_object_C1.csv');
  assert.equal(parse(wide.text).length - 1, 4);
  assert.equal(d.ids['qc-export-count'].textContent, '0 cells excluded · 24 of 24 measurement rows kept');
  assert.equal(d.ids['export-shape'].textContent, '4 rows × 9 columns');
  assert.equal(d.ids['export-file'].textContent, wide.name);                     // the file name is shown before saving
  // A new window (or another result) restores the preset and layout; channels start complete again.
  const again = dock({storage: d.storage});
  assert.equal(again.summary(), 'One row per cell');
  assert.equal(again.box('C2').checked, true);
  assert.equal((await again.save('decisions')).name, 'RY26_CA_vs_DN_qc_decisions.json');
});

test('changing contents cancels a pending export and the report re-checks the request', async () => {
  const d = dock();
  d.buttons[0].click();                         // request with all columns, not yet delivered
  d.button('Key values').click(); d.pump();      // contents change before the reply
  assert.equal(d.downloads.length, 0);
  const csv = await d.save('included');
  assert.equal(parse(csv.text)[0].length, 12);
  const request = d.messages.findLast(m => m.type === 'qc-export-request');
  d.ids['codex-visualization'].contentWindow.postMessage({...request, request_id: 99, contents: {...request.contents, columns: ['raw_mean']}});
  d.pump();
  assert.ok(d.messages.some(m => m.type === 'qc-error' && /contents changed/i.test(m.message)));
  assert.equal(d.downloads.length, 1);
});

test('the last region or channel cannot be cleared, and damaged preferences fall back to all columns', () => {
  const d = dock();
  d.button('Key values').click(); d.pump();
  d.toggle('whole');
  assert.equal(d.box('whole').checked, true);
  assert.equal(d.summary(), 'Key values');
  d.toggle('C1'); d.toggle('C2');
  assert.equal(d.box('C2').checked, true);
  for (const saved of ['{broken', JSON.stringify({preset:'custom', columns:['nope', 7], regions:['nowhere'], layout:'sideways'}), JSON.stringify([1])]) {
    const s = new Map([['lab-cellpose-export-contents-v1', saved]]), fresh = dock({storage: s});
    assert.match(fresh.summary(), /^(Everything|Custom)$/);
    assert.equal(fresh.box('whole').checked && fresh.box('edge').checked && fresh.box('interior').checked, true);
  }
});

test('3.0: a table by condition and the preview of the first rows', async () => {
  const d = dock();
  d.view(true);                                                                     // the export view opens: the preview is requested
  assert.match(d.preview(), /\|field\|segmentation_channel\|object_id\|region\|measurement_channel\|/);
  assert.match(d.preview(), /\|f0\|C1\|1\|whole\|C1\|100\|110\|/);                       // the first row, as it will be written
  assert.match(d.preview(), /These are all the rows of the saved file\.$/);            // 24 rows fit the preview of 40
  d.button('By condition').click(); d.pump();
  assert.equal(d.summary(), 'By condition');
  // Two segmentation inputs are separate populations: with both in scope, each column says which cells it lists.
  assert.match(d.preview(), /CA \| C1_mNG_whole_corrected_mean \| cells from C1\|DN \| C1_mNG_whole_corrected_mean \| cells from C1\|/);
  assert.equal(parse((await d.save('included')).text)[0].length, 8);
  d.ids['qc-scope'].value = 'C1'; d.ids['qc-scope'].fire('change'); d.pump();
  assert.match(d.preview(), /CA \| C1_mNG_whole_corrected_mean\|DN \| C1_mNG_whole_corrected_mean\|/);
  const saved = await d.save('included');
  assert.equal(saved.name, 'RY26_CA_vs_DN_included_C1_by_condition.csv');
  const table = parse(saved.text);
  assert.deepEqual(table[0], ['CA | C1_mNG_whole_corrected_mean', 'DN | C1_mNG_whole_corrected_mean', 'CA | C2_mCherry_whole_corrected_mean', 'DN | C2_mCherry_whole_corrected_mean']);
  assert.equal(d.ids['export-shape'].textContent, `${table.length - 1} rows × 4 columns`);
  d.toggle('C2'); d.pump();                                                         // one channel left: plain condition names
  assert.equal(d.summary(), 'By condition · 1 of 2 channels');
  assert.deepEqual(parse((await d.save('included')).text)[0], ['CA', 'DN']);
  assert.equal(d.downloads.at(-1).name, 'RY26_CA_vs_DN_included_C1_by_condition_C1.csv');
  assert.equal(d.box('image_name').disabled, true);                                 // names cannot be columns of this table
  assert.equal(d.box('raw_mean').disabled, false);
  // An exclusion made while the view is open refreshes the preview.
  const before = d.preview();
  d.bridge.change(() => d.qc.toggle('f0', 'C1', 1)); d.pump();
  assert.notEqual(d.preview(), before);
  d.view(false); const closed = d.messages.filter(m => m.type === 'qc-preview-request').length;
  d.bridge.change(() => d.qc.undoLast()); d.pump();
  assert.equal(d.messages.filter(m => m.type === 'qc-preview-request').length, closed);   // no preview work while the view is closed
  const again = dock({storage: d.storage});
  assert.equal(again.summary(), 'By condition');
});

test('image names split a path written by Windows at backslashes, like image_names in analyze.py', () => {
  const n = LabExport.names({fields: [
    {id:'a', path:'C:\\Users\\lab\\Exp\\CA\\Image 1.tif'}, {id:'b', path:'\\\\server\\share\\DN\\Image 2.tif'},
    {id:'c', path:'D:\\data\\run.zip', member:'Image 3.tif'}, {id:'d', path:'D:\\data\\run.zip', member:'Exp/CA\\x/Image 4.tif'},
    {id:'e', path:'/data/odd\\name/Image 5.tif'}, {id:'f', path:'/data/DN/Image 6.tif', label:'DN/Image 6.tif'}]});
  assert.deepEqual(['a','b','c','d','e','f'].map(id => [n.field(id,'image_name'), n.field(id,'image_folder')]),
    [['Image 1.tif','CA'], ['Image 2.tif','DN'], ['Image 3.tif','run.zip'], ['Image 4.tif','CA\\x'], ['Image 5.tif','odd\\name'], ['Image 6.tif','DN']]);
});
