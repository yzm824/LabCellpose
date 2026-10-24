"""Build a sandboxed review page over immutable measurements; no inference."""
from pathlib import Path
import base64, csv, hashlib, html, io, json

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
JPEG_PREFIX = 'data:image/jpeg;base64,'

def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')

def make_bundle(config, fields, csv_text):
    parsed = list(csv.reader(io.StringIO(csv_text)))
    if not parsed: raise ValueError('measurements.csv is empty')
    columns, rows = parsed[0], parsed[1:]
    index = {c:i for i,c in enumerate(columns)}
    missing = [c for c in ('field','segmentation_channel','object_id','region','measurement_channel') if c not in index]
    if missing: raise ValueError('measurements.csv lacks identity columns: '+', '.join(missing))
    if any(len(r)!=len(columns) for r in rows): raise ValueError('measurements.csv has rows with a different number of columns')
    known = {(f,s,str(o['id'])) for f,d in fields.items() for s,obs in d['objects'].items() for o in obs}
    seen = {(r[index['field']],r[index['segmentation_channel']],r[index['object_id']]) for r in rows}
    if seen != known:
        raise ValueError('CSV and displayed objects do not describe the same population')
    signatures = [(r[index['field']],r[index['segmentation_channel']],r[index['object_id']],r[index['region']],r[index['measurement_channel']]) for r in rows]
    if len(set(signatures)) != len(signatures): raise ValueError('Duplicate measurement records')
    viewer_sha = hashlib.sha256(packed(dict(config=config,fields=fields)).encode()).hexdigest()
    csv_sha = hashlib.sha256(csv_text.encode()).hexdigest()
    dataset_id = hashlib.sha256((viewer_sha+csv_sha).encode()).hexdigest()
    return dict(dataset_id=dataset_id,source_csv_sha256=csv_sha,source_viewer_sha256=viewer_sha,
        columns=columns,rows=rows,segmentation_channels=config['segmentation_channels'],background_estimator=config.get('background',{}).get('estimator','median'))

def substitute(template, marker, value):
    """Replace a template marker exactly once; inserted text is never scanned for further markers."""
    if template.count(marker) != 1: raise ValueError(f'Report template must contain {marker} exactly once')
    before, after = template.split(marker)
    return before + value + after

def render_html(config, fields, csv_text, runinfo, app_path=None, bundle=None, qc_store=None):
    bundle = bundle or make_bundle(config,fields,csv_text)
    app = (Path(app_path) if app_path else ASSETS/'viewer_app.html').read_text()
    payload = dict(config=config,fields=fields,run=runinfo,qc=bundle)
    app = substitute(app,'__PAYLOAD__',packed(payload))
    app = '<script>'+'\n'.join((ASSETS/name).read_text() for name in ('image_viewport.js','background_stats.js','export_table.js','manual_qc.js','manual_qc_bridge.js'))+'</script>\n'+app
    host = dict(dataset_id=bundle['dataset_id'],source_csv_sha256=bundle['source_csv_sha256'],source_viewer_sha256=bundle['source_viewer_sha256'],
        segmentation_options=[(ch['id'],ch['label']) for ch in config['channels'] if ch['id'] in config['segmentation_channels']],
        qc_store=qc_store,title=str(config.get('title') or '')[:200])
    controls = """<section id="qc-export" aria-label="Data export">
<div class="export-row"><strong class="export-heading">Data export</strong><label class="export-scope">Segmentation scope <select id="qc-scope"><option value="all">All segmentation inputs</option></select></label><details class="export-contents" id="qc-contents"><summary id="qc-contents-summary">Contents: All columns</summary><div class="more-panel" id="qc-contents-panel" role="group" aria-label="Included CSV contents"><p>Loading export choices…</p></div></details><button data-qc-download="included" disabled>Download included CSV</button><button data-qc-download="decisions" disabled>Save QC decisions JSON</button><details class="more-exports"><summary>More options</summary><div class="more-panel"><strong>Review records</strong><button data-qc-download="audit" disabled>Download exclusions CSV</button><label>Load QC decisions (replace current)<input id="qc-load" type="file" accept=".json,application/json"></label><a href="measurements.csv" download>Download original CSV — initial run settings, all objects</a><span>Choose regions, measurement channels and columns for the included CSV under Contents. Channel selectors on the page affect only the display and readout; the background estimator changes corrected values in the included CSV.</span></div></details></div>
<div class="export-meta"><span id="qc-export-count">Loading review state…</span><span id="qc-storage" role="status">Loading…</span></div>
</section>"""
    shell = (ASSETS/'viewer_shell.html').read_text()
    start=shell.index('<p><a href="measurements.csv"');end=shell.index('</p>',start)+4
    shell=shell[:start]+controls+shell[end:]
    shell=shell.replace('<a href="measurements.csv" download>', '<button id="qc-backup" disabled>Download previous QC backup</button><details><summary>Start a new review…</summary><p>Current saved decisions will be backed up. All objects will be included in the new review.</p><label><input id="qc-reset-confirm" type="checkbox"> I want to start with all objects included.</label><button id="qc-reset" disabled>Back up and start new review</button></details><a href="measurements.csv" download>')
    shell=shell.replace('<div class="export-meta">','<p id="qc-recovery" hidden>Saved QC needs recovery. Use More options to download its backup, load a valid QC JSON, or explicitly start a new review.</p><div class="export-meta">')
    # Insert the escaped report first, then the host script: user-controlled labels inside either can never
    # be interpreted as a template marker (a label such as "__APP__" previously broke the QC host script).
    shell=substitute(shell,'__APP__',html.escape(app,quote=True))
    host_script=substitute((ASSETS/'manual_qc_host.js').read_text(),'__QC_HOST_CONFIG__',packed(host))
    host_script=(ASSETS/'export_table.js').read_text()+'\n'+(ASSETS/'export_panel.js').read_text()+'\n'+host_script
    # Register the host listener BEFORE loading the iframe, to avoid losing qc-ready.
    shell=substitute(shell,'<!--QC_HOST_SCRIPT-->','<script>'+host_script+'</script>')
    return shell, bundle

def render(config, fields, csv_text, runinfo, destination, app_path=None, bundle=None, qc_store=None):
    shell, bundle = render_html(config, fields, csv_text, runinfo, app_path, bundle, qc_store)
    Path(destination).write_text(shell)
    return {k:bundle[k] for k in ['dataset_id','source_csv_sha256','source_viewer_sha256']}

def display_fields(fields):
    """Presentation-only copy of saved viewer fields for reopening a run (QC identity is computed from the originals).
    Drops values the viewer recomputes: the inner-band outline (whole + interior outline) and stored corrected
    values; keeps the stored background for any channel without field-level median statistics."""
    view = json.loads(json.dumps(fields))
    for f in view.values():
        medians = (f.get('background') or {}).get('medians') or {}
        for objects in (f.get('objects') or {}).values():
            for o in objects:
                regions = o.get('regions') or {}
                if regions.get('edge') and regions.get('whole') and isinstance(regions['whole'].get('path'), str):
                    regions['edge']['path'] = None
                for r in regions.values():
                    for cid, m in ((r or {}).get('channels') or {}).items():
                        if not isinstance(m, dict): continue
                        for key in ('corrected','correctedSum'): m.pop(key, None)
                        if cid in medians:
                            for key in ('background','backgroundMedian','backgroundMean','backgroundEstimator'): m.pop(key, None)
    return view

def downscale_previews(fields, side):
    """Re-encode stored JPEG previews no larger than side px (display only; measurements are untouched)."""
    from PIL import Image
    for f in fields.values():
        for group in ('images','fixedImages'):
            for cid, url in list((f.get(group) or {}).items()):
                if not isinstance(url, str) or not url.startswith(JPEG_PREFIX): continue
                with Image.open(io.BytesIO(base64.b64decode(url[len(JPEG_PREFIX):], validate=True))) as im:
                    if im.format != 'JPEG' or max(im.size) <= side: continue
                    im = im.convert('L'); im.thumbnail((side,side), Image.Resampling.LANCZOS)
                    out = io.BytesIO(); im.save(out, format='JPEG', quality=82)
                f[group][cid] = JPEG_PREFIX + base64.b64encode(out.getvalue()).decode()
        f['previewMaxSide'] = min(side, f.get('previewMaxSide') or side)
    return fields

def render_within(config, fields, csv_text, runinfo, destination, limit, qc_store=None, sides=(1280,1024,768,512,384)):
    """Render a saved run so the served report stays within limit bytes, shrinking previews only if needed."""
    bundle = make_bundle(config, fields, csv_text)
    view = display_fields(fields)
    for side in (None,)+tuple(sides):
        if side: view = downscale_previews(view, side)
        shell, _ = render_html(config, view, csv_text, runinfo, bundle=bundle, qc_store=qc_store)
        data = shell.encode('utf-8')
        if len(data) <= limit:
            Path(destination).write_bytes(data)
            return {k:bundle[k] for k in ['dataset_id','source_csv_sha256','source_viewer_sha256']}
    raise ValueError(f'This saved result needs {len(data)/2**20:.0f} MiB to review interactively, above the {limit>>20} MiB viewer limit. '
                     'Its CSV files and masks are unchanged and remain available in the result folder.')
