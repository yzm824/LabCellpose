/* Setup page (3.0): the logic block of interface.html without a browser, and static checks of the page that uses it.
   Run with node --test desktop/test_interface.cjs. The page itself is exercised in WebKit by
   packaging/macos_app/validation_v3.0 (wkshot, native_check.py). */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const test = require('node:test');
const html = fs.readFileSync(path.join(__dirname, 'interface.html'), 'utf8');
const block = html.match(/<script id="setup-model">([\s\S]*?)<\/script>/);
assert.ok(block, 'interface.html has a setup-model script');
const sandbox = {module: {exports: {}}};
vm.runInNewContext(block[1], sandbox);
const S = sandbox.module.exports;
const plain = value => JSON.parse(JSON.stringify(value));   // objects from the page's context, as ordinary data

const records = [0, 1, 2, 3].map(i => ({index: i + 10, name: `${i < 2 ? 'CA' : 'DN'}/Image ${i + 1}.tif`, folder: i < 2 ? 'CA' : 'DN', shape: [3, 512, 512], dtype: 'uint16', metadata: {}}));
function state(extra = {}) {
  return {inventory: '/session/inventory.json', active: {count: 3, records}, selected: [13, 10], output: '/results', title: 'CA vs DN', device: 'auto', estimator: 'median',
    channels: S.channelsFor(3, [{preset: 'mNG'}, {preset: 'mCherry'}, {modality: 'TL-PH', preset: 'Phase'}]), settings: {...S.SETTINGS}, foreground: '', backgroundMask: '', ...extra};
}

test('channel roles start from the acquisition metadata', () => {
  const channels = plain(S.channelsFor(3, [{preset: 'mNG'}, {}, {modality: 'TL-PH', preset: 'Phase'}]));
  assert.deepEqual(channels, [{label: 'C1 · mNG', kind: 'fluorescence', measure: true, segment: true}, {label: 'C2', kind: 'fluorescence', measure: true, segment: false},
    {label: 'C3 · Phase', kind: 'phase', measure: false, segment: false}]);
  assert.deepEqual(plain(S.channelsFor(2)).map(c => [c.label, c.kind, c.measure, c.segment]), [['C1', 'fluorescence', true, true], ['C2', 'fluorescence', true, false]]);
  assert.deepEqual([plain(S.segmentIds(channels)), plain(S.measuredIds(channels))], [['C1'], ['C1', 'C2']]);
  assert.equal(S.signature(3, [{preset: 'mNG'}, {}, {preset: 'Phase'}]), '3|mNG||Phase');
  assert.notEqual(S.signature(3, [{preset: 'GFP'}]), S.signature(3, [{preset: 'mNG'}]));
});

test('the page says what is still missing before a run, in the order it asks for it', () => {
  assert.deepEqual(plain(S.missing({active: null})), ['choose images']);
  assert.deepEqual(plain(S.missing(state())), []);
  const none = state({selected: [], output: ''});
  none.channels.forEach(c => { c.segment = false; c.measure = false; });
  assert.deepEqual(plain(S.missing(none)), ['select at least one image', 'choose a channel to find cells in', 'choose a fluorescence channel to measure', 'choose where to save the results']);
  const bad = state({settings: {...S.SETTINGS, diameter: NaN, min_size: 1.5, flow_threshold: 9}});
  assert.deepEqual(plain(S.missing(bad)), ['set cell diameter to a number from 1 to 1000', 'set flow threshold to a number from 0 to 3', 'set smallest cell to a whole number from 1 to 1000000']);
  // A phase channel that is ticked for measuring does not count as measured.
  const phase = state(); phase.channels.forEach(c => c.measure = false); phase.channels[2].measure = true;
  assert.ok(plain(S.missing(phase)).includes('choose a fluorescence channel to measure'));
});

test('a run request follows the backend contract', () => {
  const s = state(); s.channels[1].segment = true; s.channels[2].measure = true;   // phase ticked by mistake: never sent as measured
  const request = plain(S.runRequest(s));
  assert.deepEqual(request.selected, [10, 13]);                                     // in image order, whatever the click order was
  assert.deepEqual(request.channels.map(c => [c.kind, c.measure, c.segment]), [['fluorescence', true, true], ['fluorescence', true, true], ['phase', false, false]]);
  assert.deepEqual([request.segmentation_channels, request.background_mask, request.foreground, request.background_estimator], [['C1', 'C2'], 'C1', 'C1', 'median']);
  assert.deepEqual([request.inventory, request.output, request.title, request.device, request.confirmed], ['/session/inventory.json', '/results', 'CA vs DN', 'auto', true]);
  assert.deepEqual(request.settings, {...S.SETTINGS});
  // Background choices follow the roles: a choice that is no longer possible falls back to the first possible one.
  assert.deepEqual(plain(S.background({...s, backgroundMask: 'C2', foreground: 'C2'})), {mask: 'C2', reference: 'C2'});
  s.channels[1].segment = false; s.channels[1].measure = false;
  assert.deepEqual(plain(S.background({...s, backgroundMask: 'C2', foreground: 'C2'})), {mask: 'C1', reference: 'C1'});
});

test('a trial uses only the settings that decide where cells are found', () => {
  const s = state(), request = plain(S.trialRequest(s, 12, 5));
  assert.deepEqual(request, {action: 'trial', token: 5, inventory: '/session/inventory.json', index: 12, segmentation_channels: ['C1'],
    settings: {diameter: 60, flow_threshold: .4, cellprob_threshold: 0, min_size: 15}, device: 'auto'});
  const key = S.trialKey(s, 12);
  for (const same of [{title: 'x'}, {output: '/else'}, {estimator: 'mean'}, {settings: {...s.settings, edge_width_px: 9, mad_multiplier: 3, dilation_iterations: 1}}])
    assert.equal(S.trialKey({...s, ...same}, 12), key);
  for (const other of [{settings: {...s.settings, diameter: 61}}, {settings: {...s.settings, flow_threshold: .5}}, {device: 'cpu'}, {inventory: '/other.json'}])
    assert.notEqual(S.trialKey({...s, ...other}, 12), key);
  assert.notEqual(S.trialKey(s, 13), key);
  const more = state(); more.channels[1].segment = true; assert.notEqual(S.trialKey(more, 12), key);
  assert.equal(S.trialReady(s), true);
  assert.equal(S.trialReady({...s, settings: {...s.settings, diameter: 0}}), false);
  assert.equal(S.trialReady({...s, settings: {...s.settings, edge_width_px: NaN}}), true);   // not a trial setting
  const noSegment = state(); noSegment.channels[0].segment = false; assert.equal(S.trialReady(noSegment), false);
});

test('presets carry names, roles and settings and are refused when they do not fit', () => {
  const s = state({estimator: 'mean', device: 'cpu', settings: {...S.SETTINGS, diameter: 42}}); s.channels[1].segment = true;
  const saved = plain(S.preset(s));
  assert.equal(saved.appPresetVersion, 1); assert.deepEqual([saved.background_mask, saved.foreground, saved.background_estimator], ['C1', 'C1', 'mean']);
  const fresh = state(), next = plain(S.applyPreset(fresh, saved));
  assert.deepEqual(next.channels, saved.channels); assert.equal(next.settings.diameter, 42);
  assert.deepEqual([next.estimator, next.device, next.backgroundMask, next.foreground, next.title], ['mean', 'cpu', 'C1', 'C1', 'CA vs DN']);
  // An unknown setting is ignored; a background choice the roles do not allow falls back.
  const odd = plain(S.applyPreset(fresh, {...saved, settings: {diameter: 'big', flow_threshold: 1}, background_mask: 'C3', foreground: 'C9', title: ''}));
  assert.deepEqual([odd.settings.diameter, odd.settings.flow_threshold, odd.backgroundMask, odd.foreground, odd.title], [60, 1, 'C1', 'C1', 'CA vs DN']);
  assert.throws(() => S.applyPreset(fresh, {...saved, channels: saved.channels.slice(0, 2)}), /2 channels; these images have 3/);
  assert.throws(() => S.applyPreset(fresh, {...saved, channels: saved.channels.map(c => ({...c, segment: false}))}), /find cells/);
  assert.throws(() => S.applyPreset(fresh, {...saved, channels: saved.channels.map(c => ({...c, kind: 'rgb'}))}), /channel type/);
  assert.throws(() => S.applyPreset(fresh, {...saved, background_estimator: 'mode'}), /estimator/);
  assert.throws(() => S.applyPreset(fresh, null), /not a LabCellpose preset/);
});

test('images are grouped by folder; counts, titles, paths and the ruler read naturally', () => {
  const folders = plain(S.folders(records));
  assert.deepEqual(folders.map(f => [f.name, f.records.map(r => r.index)]), [['CA', [10, 11]], ['DN', [12, 13]]]);
  assert.deepEqual(plain(S.folders([{index: 0}, {index: 1, folder: 'x'}])).map(f => f.name), ['', 'x']);
  assert.equal(S.runSummary(state()), '2 images · cells found in 1 channel · 2 channels measured');
  assert.equal(S.plural(1, 'image'), '1 image'); assert.equal(S.plural(1200, 'cell'), '1,200 cells');
  assert.equal(S.titleFor('/data/Experiment 12.zip'), 'Experiment 12'); assert.equal(S.titleFor('/data/plate/'), 'plate'); assert.equal(S.titleFor('/data/a.TIFF'), 'a');
  assert.equal(S.titleFor(''), 'Fluorescence analysis');
  assert.equal(S.shortPath('/Users/someone/Desktop/results'), '…/Desktop/results'); assert.equal(S.shortPath('/results'), '/results');
  // A path written by Windows is split at backslashes and shown with them; a backslash in a macOS name is just a character.
  assert.equal(S.titleFor('C:\\Users\\lab\\Experiment 12.zip'), 'Experiment 12'); assert.equal(S.titleFor('D:\\data\\plate\\'), 'plate');
  assert.equal(S.shortPath('C:\\Users\\lab\\Desktop\\results'), '…\\Desktop\\results'); assert.equal(S.shortPath('D:\\results'), 'D:\\results');
  assert.equal(S.shortPath('/data/odd\\name/x/y'), '…/x/y'); assert.equal(S.titleFor('/data/odd\\name.zip'), 'odd\\name');
  assert.equal(S.lineDiameter(0, 0, 30, 40), 50); assert.equal(S.lineDiameter(5, 5, 5, 5), 1); assert.equal(S.lineDiameter(0, 0, 9000, 0), 1000);
});

test('the page refers only to elements that exist, and marks the engine scripts it shares with the review', () => {
  const page = html.slice(html.lastIndexOf('<script>'));
  const used = new Set([...page.matchAll(/\$\('([A-Za-z_][\w-]*)'\)/g)].map(m => m[1]));
  for (const group of page.matchAll(/for\(const (?:\[?id\b[^\]]*\]?|id) of \[([^\]]*)\]\)/g)) for (const m of group[1].matchAll(/'([A-Za-z_][\w-]*)'/g)) used.add(m[1]);
  const defined = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
  const settings = Object.keys(S.SETTINGS);
  assert.deepEqual([...used].filter(id => !defined.has(id)).sort(), []);
  assert.deepEqual(settings.filter(id => !defined.has(id)), []);                    // every setting has its field
  assert.ok(used.size > 50);
  const shared = [...html.matchAll(/\/\*__INCLUDE:([\w.]+)__\*\//g)].map(m => m[1]);
  assert.deepEqual(shared, ['ui.css', 'ui_kit.js', 'image_viewport.js', 'review_model.js']);   // one stylesheet and kit for every step
  for (const name of shared) assert.ok(fs.existsSync(path.join(__dirname, '../engine/assets', name)));
  assert.match(html, /connect-src 'none'/);                                         // the setup page never talks to a network
});
