"""Build a sandboxed review page over immutable measurements; no inference."""
from pathlib import Path
import csv, hashlib, html, io, json

ASSETS = Path(__file__).resolve().parents[1] / 'assets'

def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')

def make_bundle(config, fields, csv_text):
    parsed = list(csv.reader(io.StringIO(csv_text)))
    columns, rows = parsed[0], parsed[1:]
    index = {c:i for i,c in enumerate(columns)}
    known = {(f,s,str(o['id'])) for f,d in fields.items() for s,obs in d['objects'].items() for o in obs}
    seen = {(r[index['field']],r[index['segmentation_channel']],r[index['object_id']]) for r in rows}
    if seen != known or any(len(r)!=len(columns) for r in rows):
        raise ValueError('CSV and displayed objects do not describe the same population')
    signatures = [(r[index['field']],r[index['segmentation_channel']],r[index['object_id']],r[index['region']],r[index['measurement_channel']]) for r in rows]
    if len(set(signatures)) != len(signatures): raise ValueError('Duplicate measurement records')
    viewer_sha = hashlib.sha256(packed(dict(config=config,fields=fields)).encode()).hexdigest()
    csv_sha = hashlib.sha256(csv_text.encode()).hexdigest()
    dataset_id = hashlib.sha256((viewer_sha+csv_sha).encode()).hexdigest()
    return dict(dataset_id=dataset_id,source_csv_sha256=csv_sha,source_viewer_sha256=viewer_sha,
        columns=columns,rows=rows,segmentation_channels=config['segmentation_channels'])

def render(config, fields, csv_text, runinfo, destination, app_path=None, bundle=None):
    bundle = bundle or make_bundle(config,fields,csv_text)
    app = (Path(app_path) if app_path else ASSETS/'viewer_app.html').read_text()
    payload = dict(config=config,fields=fields,run=runinfo,qc=bundle)
    app = app.replace('__PAYLOAD__',packed(payload))
    app = '<script>'+ (ASSETS/'manual_qc.js').read_text()+'\n'+(ASSETS/'manual_qc_bridge.js').read_text()+'</script>\n'+app
    host = dict(dataset_id=bundle['dataset_id'],source_csv_sha256=bundle['source_csv_sha256'],source_viewer_sha256=bundle['source_viewer_sha256'],
        segmentation_options=[(ch['id'],ch['label']) for ch in config['channels'] if ch['id'] in config['segmentation_channels']])
    controls = '''<section id="qc-export" style="max-width:1160px;margin:0 auto 16px;padding:14px;background:#F8F8FA;border:1px solid #DADBE3;border-top:3px solid #9A8C98;border-radius:7px;font:14px system-ui;line-height:1.5">
<strong>Quality control and data export</strong> · All FOVs, measurement channels, and ROIs<br>
<label>Export: segmentation input <select id="qc-scope"><option value="all">All segmentation inputs (separate object populations)</option></select></label>
<div style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0"><button data-qc-download="included" disabled>Download included CSV</button><button data-qc-download="audit" disabled>Download exclusions CSV</button><button data-qc-download="decisions" disabled>Save QC decisions JSON</button><label style="padding:5px;border:1px solid #9A8C98;border-radius:4px;cursor:pointer">Load QC decisions (replace current)<input id="qc-load" type="file" accept=".json,application/json" style="display:block;max-width:230px"></label></div>
<div id="qc-export-count">Loading review state…</div><div id="qc-storage" role="status">Loading…</div>
<details><summary>Unfiltered source data</summary><a href="measurements.csv" download>Download original CSV — includes manually excluded objects</a></details>
</section>'''
    shell = (ASSETS/'viewer_shell.html').read_text()
    start=shell.index('<p><a href="measurements.csv"');end=shell.index('</p>',start)+4
    shell=shell[:start]+controls+shell[end:]
    host_script=(ASSETS/'manual_qc_host.js').read_text().replace('__QC_HOST_CONFIG__',packed(host))
    # Register the host listener BEFORE loading the iframe, to avoid losing qc-ready.
    host_start=shell.index('<script>(()=>{const frame=')
    shell=shell[:host_start]+'<script>'+host_script+'</script>\n'+shell[host_start:]
    shell=shell.replace('__APP__',html.escape(app,quote=True))
    Path(destination).write_text(shell)
    return {k:bundle[k] for k in ['dataset_id','source_csv_sha256','source_viewer_sha256']}
