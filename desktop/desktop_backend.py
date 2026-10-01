"""Desktop adapter for the frozen LabCellpose engine. No agent or network API."""
from pathlib import Path
import argparse
import base64
import contextlib
import datetime
import hashlib
import io
import json
import math
import os
import sys
import traceback
import uuid


def emit(event, **values):
    print(json.dumps(dict(event=event, **values), ensure_ascii=False, allow_nan=False), flush=True)


def reject_axes(record):
    from analyze import validate_2d_axes
    validate_2d_axes(record.get('tiff_axes', ''), record['shape'][0])


def snapshot(path):
    stat = Path(path).stat()
    return [stat.st_size, stat.st_mtime_ns]


def preview_images(analyze, record):
    import numpy as np
    from PIL import Image
    if record.get('source_snapshot') != snapshot(record['path']):
        raise ValueError('Input changed after inspection; re-scan image files.')
    require_input_digests(record)
    _, raw, _, _ = analyze.read_field_sources(record, Path('.'))
    planes, _ = analyze.read_stack(raw)
    previews = []
    for plane in planes:
        lo, hi = np.percentile(plane, [1, 99.9])
        pixels = np.clip((plane.astype(float)-lo)/max(float(hi-lo), 1), 0, 1)
        image = Image.fromarray(np.round(pixels*255).astype('uint8'))
        image.thumbnail((640, 640))
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        previews.append('data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode())
    return previews


def preview(analyze, request):
    inventory = json.loads(Path(request['inventory']).read_text())
    index = request.get('index')
    if type(index) is not int or not 0 <= index < len(inventory['records']):
        raise ValueError('Invalid preview field')
    record = inventory['records'][index]
    if record['status'] != 'inspected':
        raise ValueError('This image is not a supported field')
    reject_axes(record)
    emit('preview', index=index, inventory=request['inventory'], previews=preview_images(analyze, record))


def inspect(analyze, source, destination):
    analyze.inspect_input(source, destination)
    inventory = json.loads(destination.read_text())
    groups = {}
    for index, record in enumerate(inventory['records']):
        record['index'] = index
        if record['status'] != 'inspected':
            continue
        try:
            reject_axes(record)
            record['source_snapshot'] = snapshot(record['path'])
        except (OSError, ValueError) as error:
            record.update(status='unsupported', error=str(error))
            continue
        count = record['shape'][0]
        groups.setdefault(count, []).append(record)
    inventory['counts'] = {s: sum(r['status'] == s for r in inventory['records'])
                           for s in ('inspected', 'unsupported')}
    analyze.dump(destination, inventory)
    result = []
    for count, records in sorted(groups.items()):
        first = records[0]
        result.append(dict(count=count, records=[dict(index=r['index'], name=r.get('member') or r['path'],
            shape=r['shape'], dtype=r['dtype'], axes=r.get('tiff_axes'), metadata=r.get('metadata', {}))
            for r in records], previews=preview_images(analyze, first)))
    emit('inventory', path=str(destination), groups=result,
         rejected=[dict(name=r.get('member') or r['path'], error=r.get('error', 'Unsupported image'))
                   for r in inventory['records'] if r['status'] != 'inspected'])


def bounded_number(settings, key, default, lower, upper, integer=False):
    value = settings.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f'{key}: enter a number')
    value = float(value)
    if not math.isfinite(value) or not lower <= value <= upper or (integer and not value.is_integer()):
        raise ValueError(f'{key} must be between {lower} and {upper}')
    return int(value) if integer else value


def require_input_digests(record):
    import re
    if not re.fullmatch(r'[0-9a-f]{64}',str(record.get('input_sha256',''))) or 'metadata_sha256' not in record or (record['metadata_sha256'] is not None and not re.fullmatch(r'[0-9a-f]{64}',str(record['metadata_sha256']))):
        raise ValueError('This inventory has no confirmed input digests; re-scan the images.')


def make_config(request, inventory):
    if request.get('confirmed') is not True:
        raise ValueError('Confirm the registered 2D channel order and measurement roles.')
    selected = request.get('selected', [])
    if not selected or len(set(selected)) != len(selected):
        raise ValueError('Select one or more unique image fields.')
    records = inventory['records']
    fields = []; decoded_bytes = 0
    channels = request['channels']
    if not 1 <= len(channels) <= 32:
        raise ValueError('Select a channel group containing 1–32 channels.')
    for index in selected:
        if type(index) is not int or not 0 <= index < len(records):
            raise ValueError('Invalid field selection')
        record = records[index]
        if record['status'] != 'inspected' or record['shape'][0] != len(channels):
            raise ValueError('All selected fields must match the chosen channel count.')
        reject_axes(record)
        if record.get('source_snapshot') != snapshot(record['path']):
            raise ValueError('Input changed after inspection; select it again before analysis.')
        require_input_digests(record)
        from analyze import MAX_BATCH_BYTES
        decoded_bytes += math.prod(record['shape']) * (2 if record['dtype']=='uint16' else 1)
        if decoded_bytes > MAX_BATCH_BYTES:
            raise ValueError('Selection exceeds 256 MiB of decoded pixels; select fewer fields.')
        identity = record['path']+'|'+str(record.get('member', ''))
        field = dict(id='field_'+hashlib.sha256(identity.encode()).hexdigest()[:16], path=record['path'],
            label=str(record.get('member') or Path(record['path']).name))
        if record.get('member'):
            field['member'] = record['member']
        field.update(input_sha256=record['input_sha256'],metadata_sha256=record['metadata_sha256'])
        fields.append(field)
    clean = []
    for page, channel in enumerate(channels):
        kind = channel.get('kind')
        if kind not in ('fluorescence', 'phase', 'other'):
            raise ValueError('Choose each channel type.')
        measure = channel.get('measure') is True
        if measure and kind != 'fluorescence':
            raise ValueError('Only fluorescence channels can be used for intensity measurements.')
        clean.append(dict(id=f'C{page+1}', page=page,
            label=str(channel.get('label') or f'C{page+1}')[:100], kind=kind, measure=measure))
    measured = [c['id'] for c in clean if c['measure']]
    segs = request.get('segmentation_channels')
    if segs is None: segs = [request.get('segmentation')]
    valid_ids = [c['id'] for c in clean]
    if not isinstance(segs, list) or not segs or any(type(s) is not str or s not in valid_ids for s in segs) or len(set(segs)) != len(segs):
        raise ValueError('Select one or more unique segmentation channels.')
    segs = [cid for cid in valid_ids if cid in segs]
    estimator = request.get('background_estimator', 'median')
    if estimator not in ('median','mean'): raise ValueError('Choose Median or Mean for background estimation.')
    anchor = request.get('background_mask', segs[0])
    foreground = request.get('foreground')
    if anchor not in segs or foreground not in measured:
        raise ValueError('Choose a selected segmentation channel for background exclusion and a measured fluorescence reference.')
    settings = request.get('settings', {})
    parameters = dict(diameter=bounded_number(settings, 'diameter', 60, 1, 1000),
        flow_threshold=bounded_number(settings, 'flow_threshold', .4, 0, 3),
        cellprob_threshold=bounded_number(settings, 'cellprob_threshold', 0, -10, 10),
        min_size=bounded_number(settings, 'min_size', 15, 1, 1000000, True),
        normalize=True, niter=None, batch_size=4, do_3D=False)
    return dict(schema_version=1, title=str(request.get('title') or 'Cell fluorescence analysis')[:150],
        plane_axis='channel', input_confirmation='sha256-v1', axis_evidence='User confirmed registered 2D channel pages and channel roles in the desktop app.',
        channels=clean, fields=fields, segmentation_channels=segs, parameters=parameters,
        edge_width_px=bounded_number(settings, 'edge_width_px', 6, 1, 100, True), ratios=[],
        background=dict(mask_channel=anchor, foreground_channel=foreground, estimator=estimator,
            mad_multiplier=bounded_number(settings, 'mad_multiplier', 5, .1, 100),
            dilation_iterations=bounded_number(settings, 'dilation_iterations', 5, 0, 100, True),
            min_fraction=.01, min_pixels=100),
        notes=['LabCellpose 1.3; independent channel segmentation with a shared per-field background estimate.',
               'Objects from different segmentation channels are separate populations; object IDs do not establish correspondence.',
               'Whole, inner-edge and interior regions are geometric; no inferred nucleus, plasma membrane or Golgi identity.',
               'The user must inspect segmentation and background; technical completion does not establish biological accuracy.'])


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, value):
        for stream in self.streams:
            stream.write(value)
            stream.flush()
        return len(value)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def run(analyze, launcher, request):
    inventory_path = Path(request['inventory']).resolve()
    inventory = json.loads(inventory_path.read_text())
    config = make_config(request, inventory)
    analyze.validate_config(config)
    parent = Path(request['output']).expanduser().resolve()
    if not parent.is_dir():
        raise ValueError('Choose an existing output folder.')
    if parent.is_relative_to(launcher.ROOT):
        raise ValueError('Save results outside the application bundle.')
    device = request.get('device', 'auto')
    if device not in ('auto', 'cpu', 'mps'):
        raise ValueError('Unsupported device')
    workspace = parent / ('LabCellpose_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    workspace.mkdir()
    analyze.dump(workspace/'config.json', config)
    analyze.dump(workspace/'input_inventory.json', inventory)
    emit('workspace', path=str(workspace))
    with (workspace/'analysis.log').open('w') as log:
        with contextlib.redirect_stdout(Tee(sys.stdout, log)), contextlib.redirect_stderr(Tee(sys.stderr, log)):
            try:
                launcher.run_analysis(workspace/'config.json', workspace/'results', device)
            except BaseException:
                traceback.print_exc()
                raise
    manifest = json.loads((workspace/'results/run_manifest.json').read_text())
    validation = json.loads((workspace/'results/validation.json').read_text())
    if manifest.get('status') != 'complete' or validation.get('passed') is not True:
        raise ValueError('Analysis did not pass its technical checks; keep the output for diagnosis.')
    emit('finished', result=str(workspace/'results'), objects=validation['objects'], rows=validation['measurement_rows'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', required=True)
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    payload = Path(args.payload).resolve()
    sys.path.insert(0, str(payload/'app'))
    import analyze
    import launcher
    launcher.system_check()
    request = json.loads(Path(args.request).read_text())
    if request['action'] == 'inspect':
        inspect(analyze, request['input'], Path(request['inventory']))
    elif request['action'] == 'run':
        run(analyze, launcher, request)
    elif request['action'] == 'preview':
        preview(analyze, request)
    else:
        raise ValueError('Unknown task')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        emit('cancelled', message='Stopped. Partial output is retained; a new run gets a new folder.')
        sys.exit(130)
    except Exception as error:
        emit('error', message=f'{type(error).__name__}: {error}')
        sys.exit(1)
