/* 3.0 review workspace: reviewed images, multi-object decisions, the table by condition, the export preview and the
   display helpers. Run with node --test engine/assets/test_review_v3.cjs; no browser or inference. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const LabQC = require('./manual_qc.js');
const LabExport = require('./export_table.js');
const LabReview = require('./review_model.js');
const bridgeCode = fs.readFileSync(path.join(__dirname, 'manual_qc_bridge.js'), 'utf8');

const COLUMNS = ['field','segmentation_channel','object_id','region','measurement_channel','area_pixels','raw_mean','background_median','background_mean',
  'background_estimator','background_value','corrected_mean','raw_sum','corrected_sum','saturated_pixels','saturation_limit','touches_image_edge',
  'background_valid','expert_validated','exposure_seconds'];
const config = {title: 'CA vs DN', segmentation_channels: ['C1'],
  channels: [{id:'C1',label:'C1 · mNG',kind:'fluorescence',measure:true},{id:'C2',label:'C2 · mCherry',kind:'fluorescence',measure:true},{id:'C3',label:'Phase',kind:'phase',measure:false}],
  fields: [{id:'ca1',path:'/d/run.zip',member:'Exp/CA/Image 1.tif'},{id:'ca2',path:'/d/run.zip',member:'Exp/CA/Image 2.tif'},{id:'dn1',path:'/d/run.zip',member:'Exp/DN/Image 1.tif'}]};
const counts = {ca1: 2, ca2: 1, dn1: 3};
const stats = Object.fromEntries(Object.keys(counts).map(f => [f, {valid:true, medians:{C1:10,C2:20}, means:{C1:12,C2:24}}]));
const fields = Object.fromEntries(Object.entries(counts).map(([f, n]) => [f, {background: stats[f],
  objects: {C1: Array.from({length:n}, (_, i) => ({id:i+1, edgeTouch:false, regions:{whole:{area:100, channels:{C1:{saturated:0},C2:{saturated:0}}}}}))}}]));
function bundle() {
  const rows = []; let seed = 0;
  for (const [f, n] of Object.entries(counts)) for (let id = 1; id <= n; id++) for (const region of ['whole','edge','interior']) for (const ch of ['C1','C2']) {
    const raw = 100 + (++seed), area = region === 'whole' ? 100 : 50, bg = stats[f].medians[ch];
    const missing = f === 'dn1' && id === 3 && region === 'interior';
    rows.push([f, 'C1', String(id), region, ch, missing ? '' : String(area), missing ? '' : String(raw), String(bg), String(stats[f].means[ch]), 'median', String(bg),
      missing ? '' : String(raw - bg), missing ? '' : String(raw * area), missing ? '' : String(raw * area - area * bg), '0', '65535', 'False', 'True', 'False', '0.5']);
  }
  return {dataset_id:'v3-test', source_csv_sha256:'csv', source_viewer_sha256:'viewer', segmentation_channels:['C1'], columns:COLUMNS, rows};
}
const make = () => { const b = bundle(); return {b, qc: LabQC.create(b, fields, config)}; };
const parse = text => text.replace(/^﻿/, '').trimEnd().split('\r\n').map(line => JSON.parse('[' + line + ']'));

test('several objects in different images are excluded or restored as one undoable step', () => {
  const {qc} = make();
  qc.toggle('ca1','C1',1,'Debris or artefact'); const before = qc.snapshot().revision;
  assert.equal(qc.setMany([['ca1','C1',1],['ca1','C1',2],['dn1','C1',3]], true, 'Merged / connected cells'), 2);
  assert.equal(qc.snapshot().revision, before + 1); assert.equal(qc.excludedCount(), 3);
  assert.equal(qc.decision('ca1','C1',1).reason, 'Debris or artefact');          // an earlier decision keeps its reason
  assert.equal(qc.decision('dn1','C1',3).reason, 'Merged / connected cells');
  const last = qc.snapshot().history.at(-1);
  assert.deepEqual({...last, at: undefined}, {action:'exclude-many', at:undefined, objects:2, reason:'Merged / connected cells'});
  assert.equal(qc.setMany([['ca1','C1',2]], true), 0); assert.equal(qc.snapshot().revision, before + 1);
  assert.equal(qc.undoLast(), true); assert.equal(qc.excludedCount(), 1);
  assert.equal(qc.setMany([['ca1','C1',1],['ca2','C1',1]], false), 1); assert.equal(qc.excludedCount(), 0);
  assert.equal(qc.snapshot().history.at(-1).action, 'restore-many');
  for (const bad of [null, [['ca1','C1']], [['ca1','C1',9]], [['zz','C1',1]], 'ca1'])
    assert.throws(() => qc.setMany(bad, true), /Invalid selection|Unknown candidate/);
  assert.throws(() => qc.setMany([['ca1','C1',1]], true, 'x'.repeat(2001)), /Invalid exclusion reason/);
});

test('reviewed images are saved with the decisions, undone like any change, and absent from the file until used', () => {
  const {qc} = make();
  qc.toggle('ca1','C1',1);
  assert.equal('reviewed' in qc.snapshot(), false);                                 // files without reviews keep the 2.x shape
  assert.equal(qc.setReviewed('ca1','C1',true), true); assert.equal(qc.setReviewed('ca1','C1',true), false);
  assert.equal(qc.isReviewed('ca1','C1'), true); assert.equal(qc.reviewedCount(), 1); assert.equal(qc.unitCount(), 3);
  const saved = qc.snapshot();
  assert.deepEqual(saved.reviewed.map(r => [r.field, r.segmentation_channel]), [['ca1','C1']]);
  assert.equal(saved.history.at(-1).action, 'reviewed');
  const reopened = make().qc; reopened.load(saved);
  assert.equal(reopened.isReviewed('ca1','C1'), true); assert.equal(reopened.isExcluded('ca1','C1',1), true);
  assert.equal(qc.undoLast(), true); assert.equal(qc.isReviewed('ca1','C1'), false); assert.equal(qc.isExcluded('ca1','C1',1), true);
  qc.setReviewed('dn1','C1',true); qc.setReviewed('dn1','C1',false); assert.equal(qc.reviewedCount(), 0);
  assert.equal(qc.snapshot().history.at(-1).action, 'unreviewed');
  const other = make().qc; other.setReviewed('ca2','C1',true); qc.importState(other.snapshot());
  assert.equal(qc.isReviewed('ca2','C1'), true);                                    // a loaded review brings its marks
  assert.throws(() => qc.setReviewed('zz','C1',true), /Unknown field/);
  for (const reviewed of [[{field:'zz',segmentation_channel:'C1',reviewed_at:'2026-11-11T00:00:00Z'}], [{field:'ca1',segmentation_channel:'C1',reviewed_at:'never'}],
    [saved.reviewed[0], saved.reviewed[0]], 'ca1'])
    assert.throws(() => make().qc.load({...saved, reviewed}), /reviewed|image/i);
});

test('table by condition: one column per folder, one row per cell, values as in the included CSV', () => {
  const {b, qc} = make(), schema = LabExport.check(qc.exportSchema());
  const prism = LabExport.preset(schema, 'prism', {...LabExport.defaults(schema), channels: ['C1']});
  assert.deepEqual([prism.layout, prism.columns, prism.regions, prism.channels], ['groups', ['corrected_mean'], ['whole'], ['C1']]);
  assert.equal(LabExport.presetName(schema, prism), 'prism'); assert.equal(LabExport.suffix(schema, prism), '_by_condition_C1');
  const corrected = (f, id) => b.rows.find(r => r[0] === f && r[2] === String(id) && r[3] === 'whole' && r[4] === 'C1')[11];
  let table = parse(qc.includedCSV('all', prism));
  assert.deepEqual(table[0], ['CA', 'DN']);
  assert.deepEqual(table.slice(1), [[corrected('ca1',1), corrected('dn1',1)], [corrected('ca1',2), corrected('dn1',2)], [corrected('ca2',1), corrected('dn1',3)]]);
  assert.deepEqual(qc.exportShape('all', prism), {rows: 3, columns: ['CA','DN']});
  qc.setMany([['ca1','C1',2],['dn1','C1',1]], true);                                 // excluded cells leave their column
  table = parse(qc.includedCSV('all', prism));
  assert.deepEqual(table.slice(1), [[corrected('ca1',1), corrected('dn1',2)], [corrected('ca2',1), corrected('dn1',3)]]);
  qc.setEstimator('C1', 'mean');                                                     // the chosen background estimator applies
  assert.equal(parse(qc.includedCSV('all', prism))[1][0], String(Number(corrected('ca1',1)) - 2));
});

test('table by condition: several channels or values give labelled blocks; missing values are skipped', () => {
  const {qc} = make(), schema = LabExport.check(qc.exportSchema());
  const two = LabExport.preset(schema, 'prism', LabExport.defaults(schema));
  let table = parse(qc.includedCSV('all', two));
  assert.deepEqual(table[0], ['CA | C1_mNG_whole_corrected_mean', 'DN | C1_mNG_whole_corrected_mean', 'CA | C2_mCherry_whole_corrected_mean', 'DN | C2_mCherry_whole_corrected_mean']);
  const custom = LabExport.normalize(schema, {layout:'groups', columns:['area_pixels','raw_mean'], regions:['interior'], channels:['C1','C2']});
  assert.equal(LabExport.presetName(schema, custom), 'custom'); assert.equal(LabExport.suffix(schema, custom), '_by_condition_area_pixels_raw_mean_interior');
  table = parse(qc.includedCSV('all', custom));
  assert.deepEqual(table[0].slice(0, 2), ['CA | interior_area_pixels', 'DN | interior_area_pixels']);   // area once per region, not per channel
  assert.equal(table[0].length, 6);
  assert.deepEqual(table.slice(1).map(r => r[1]), ['50', '50', '']);                     // DN object 3 has no interior pixels
  for (const columns of [[], ['image_name'], ['touches_image_edge','background_value']])
    assert.throws(() => LabExport.normalize(schema, {layout:'groups', columns, regions:['whole'], channels:['C1']}), /measured value/);
  assert.throws(() => LabExport.plan(schema, two), /from the data/);
  // Images that are not in a folder form one column; a non-ASCII folder name gets a byte-order mark for spreadsheet apps.
  const flat = {...config, fields: [{id:'ca1',path:'/d/a.tif'},{id:'ca2',path:'/d/b.tif'},{id:'dn1',path:'/条件/c.tif'}]};
  const text = LabQC.create(bundle(), fields, flat).includedCSV('all', LabExport.preset(schema, 'prism', {...LabExport.defaults(schema), channels:['C1']}));
  assert.ok(text.startsWith('﻿')); assert.deepEqual(parse(text)[0], ['d', '条件']);
  assert.equal(parse(LabQC.create(bundle(), fields, {...config, fields: []}).includedCSV('all', {...two, channels:['C1']}))[0][0], LabExport.UNGROUPED);
});

test('the export preview shows the first rows exactly as the CSV will contain them', () => {
  const {qc} = make(), schema = LabExport.check(qc.exportSchema());
  const all = qc.exportPreview('all', null, 3), full = parse(qc.includedCSV('all'));
  assert.deepEqual(all.columns, full[0]); assert.equal(all.total_rows, full.length - 1); assert.equal(all.rows.length, 3);
  assert.deepEqual(all.rows[0], full[1].map(String));
  const prism = LabExport.preset(schema, 'prism', {...LabExport.defaults(schema), channels:['C1']});
  assert.deepEqual(qc.exportPreview('all', prism).columns, ['CA','DN']); assert.equal(qc.exportPreview('all', prism).total_rows, 3);
  // Through the bridge: a preview answers only for the contents the report currently holds.
  const sent = [], childEvents = {}, host = {postMessage: data => sent.push(data)};
  const context = {LabQC: {...LabQC}, parent: host, addEventListener: (n, f) => childEvents[n] = f};
  vm.runInNewContext(bridgeCode, context);
  const b = bundle(); context.LabQC.connect(qc, b, () => {});
  const deliver = data => childEvents.message({source: host, data: {dataset_id: b.dataset_id, ...data}});
  deliver({type:'qc-init', state:null}); deliver({type:'qc-scope', scope:'all', contents: prism});
  const status = sent.filter(m => m.type === 'qc-status').at(-1);
  assert.deepEqual([status.export_rows, status.export_columns, status.reviewed_images, status.total_images], [3, 2, 0, 3]);
  deliver({type:'qc-preview-request', request_id: 7, scope:'all', contents: prism});
  const reply = sent.at(-1);
  assert.deepEqual([reply.type, reply.request_id, reply.columns, reply.total_rows, reply.total_columns], ['qc-preview-response', 7, ['CA','DN'], 3, 2]);
  deliver({type:'qc-preview-request', request_id: 8, scope:'all', contents: null});   // stale contents
  assert.deepEqual([sent.at(-2).type, sent.at(-2).request_id], ['qc-error', 8]);
});

test('conditions come from image folders; blind review hides them behind a fixed shuffled order', () => {
  const ids = config.fields.map(f => f.id), c = LabReview.conditions(config, ids);
  assert.deepEqual(c.groups, [{name:'CA', fields:['ca1','ca2']}, {name:'DN', fields:['dn1']}]);
  assert.equal(c.of.get('dn1'), 'DN'); assert.equal(c.image('ca2'), 'Image 2.tif');
  assert.deepEqual(LabReview.conditions({fields:[{id:'a',path:'/x/a.tif'}]}, ['a','b']).groups, [{name:'x', fields:['a']}, {name:'', fields:['b']}]);
  const many = Array.from({length: 12}, (_, i) => 'f' + i), first = LabReview.blind('dataset-1', many);
  assert.deepEqual(LabReview.blind('dataset-1', many), first);                       // stable for a dataset
  assert.deepEqual([...first.order].sort(), [...many].sort()); assert.notDeepEqual(first.order, many);
  assert.notDeepEqual(LabReview.blind('dataset-2', many).order, first.order);
  assert.equal(first.label.get(first.order[0]), 'Image 01'); assert.equal(first.label.get(first.order[11]), 'Image 12');
});

test('review flags are hints from robust size limits, edges and saturation; gallery order is stable', () => {
  const object = (id, area, extra = {}) => ({id, edgeTouch: false, regions: {whole: {area, channels: {C1: {saturated: 0}}}}, ...extra});
  const typical = [900, 950, 1000, 1000, 1050, 1100, 980, 1020, 990, 1010].map((a, i) => object(i + 1, a));
  const data = {f0: {objects: {C1: [...typical, object(11, 60), object(12, 9000), object(13, 1000, {edgeTouch: true})]}},
    f1: {objects: {C1: [{id: 1, edgeTouch: false, regions: {whole: {area: 1000, channels: {C1: {saturated: 4}}}}}]}}};
  const flags = LabReview.flagger(data, 'C1', ['C1']);
  assert.deepEqual(data.f0.objects.C1.map(flags).filter(f => f.length), [['small'], ['large'], ['edge']]);
  assert.deepEqual(flags(data.f1.objects.C1[0]), ['saturated']);
  assert.deepEqual(LabReview.flagger({f: {objects: {C1: [object(1, 10), object(2, 100000)]}}}, 'C1')(object(1, 10)), []);   // too few objects for size limits
  assert.ok(Object.keys(LabReview.FLAGS).every(k => ['edge','small','large','saturated'].includes(k)));
  const cells = [{id: 1, flags: [], area: 5, value: 1}, {id: 2, flags: ['edge','small'], area: 3, value: 9}, {id: 3, flags: ['edge'], area: 4, value: null}, {id: 4, flags: [], area: 1, value: 4}];
  assert.deepEqual(LabReview.order(cells, 'flagged').map(c => c.id), [2, 3, 1, 4]);
  assert.deepEqual(LabReview.order(cells, 'area').map(c => c.id), [4, 2, 3, 1]);
  assert.deepEqual(LabReview.order(cells, 'value').map(c => c.id), [2, 4, 1, 3]);
  assert.deepEqual(LabReview.order(cells, 'position').map(c => c.id), [1, 2, 3, 4]);
});

test('plot statistics, axis ticks, jitter and channel colours', () => {
  assert.deepEqual(LabReview.summary([4, 1, 3, 2, NaN, null]), {n: 4, min: 1, max: 4, q1: 1.75, median: 2.5, q3: 3.25});
  assert.deepEqual(LabReview.summary([]), {n: 0, min: null, max: null, q1: null, median: null, q3: null});
  assert.deepEqual(LabReview.ticks(0, 100), [0, 50, 100]); assert.deepEqual(LabReview.ticks(-30, 170), [-50, 0, 50, 100, 150, 200]);
  assert.deepEqual(LabReview.ticks(0.12, 0.47), [0.1, 0.2, 0.3, 0.4, 0.5]); assert.equal(LabReview.ticks(5, 5).length >= 2, true);
  assert.deepEqual(LabReview.ticks(NaN, 1), []);
  const j = LabReview.jitter('f0|C1|1'); assert.equal(j, LabReview.jitter('f0|C1|1')); assert.ok(j >= -1 && j <= 1);
  const colours = LabReview.colours([{id:'C1',label:'C1 · mNG',kind:'fluorescence'},{id:'C2',label:'mCherry',kind:'fluorescence'},{id:'C3',label:'Cy5',kind:'fluorescence'},
    {id:'C4',label:'GFP again',kind:'fluorescence'},{id:'C5',label:'Phase',kind:'phase'},{id:'C6',label:'unknown',kind:'fluorescence'}]);
  assert.deepEqual([...colours.values()].slice(0, 3), ['#35E06F', '#FF5AD9', '#FFB13B']);
  assert.equal(colours.get('C5'), LabReview.GREY);
  assert.equal(new Set([colours.get('C1'), colours.get('C2'), colours.get('C3'), colours.get('C4'), colours.get('C6')]).size, 5);   // no two fluorescence channels share a colour
});
