"""Analyse program-generated fields and record a SHA-256 of every input and output, to compare two computers.

    <bundled python> -I -B -X utf8 windows/cross_check.py --payload PAYLOAD --out NEW_DIR --device cpu [--reference FILE]

The fields are made with integer arithmetic only, so every system writes the same TIFF bytes; the script stops if they
differ from the reference. Then the bundled engine analyses them, and the masks and tables are compared with the
reference. Exit status: 0 identical, 3 the outputs differ, 2 the inputs differ. No laboratory image is involved, and
these fields say nothing about segmentation accuracy: they only show whether two computers compute the same thing.
"""
from pathlib import Path
import argparse, hashlib, json, platform, subprocess, sys, time

FIELDS = 3
SIZE = 768


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def box_blur(a, radius):
    """Mean over a (2r+1) square with edge padding, in integers."""
    import numpy as np
    k = 2 * radius + 1
    p = np.pad(a, radius, mode='edge').astype(np.int64)
    s = np.zeros((p.shape[0] + 1, p.shape[1] + 1), np.int64)
    s[1:, 1:] = p.cumsum(0).cumsum(1)
    total = s[k:, k:] - s[:-k, k:] - s[k:, :-k] + s[:-k, :-k]
    return total // (k * k)


def field(seed):
    """Two channels of ellipse-shaped 'cells' with uneven brightness, a dim texture and noise."""
    import numpy as np
    rng = np.random.Generator(np.random.PCG64(seed))
    yy, xx = np.mgrid[:SIZE, :SIZE]
    yy = yy.astype(np.int64); xx = xx.astype(np.int64)
    first = np.zeros((SIZE, SIZE), np.int64); second = np.zeros((SIZE, SIZE), np.int64)
    for _ in range(int(rng.integers(34, 46))):
        cy, cx = (int(v) for v in rng.integers(30, SIZE - 30, 2))
        a, b = (int(v) for v in rng.integers(16, 44, 2))
        tilt = int(rng.integers(-6, 7))          # shear in eighths: an integer stand-in for rotation
        bright, other = int(rng.integers(500, 3200)), int(rng.integers(200, 2600))
        dx = xx - cx; dy = (yy - cy) * 8 + dx * tilt
        d = dx * dx * b * b * 64 + dy * dy * a * a
        limit = a * a * b * b * 64
        inside = d < limit
        profile = (limit - d[inside]) * 1000 // limit            # 0..1000, highest in the middle
        first[inside] = np.maximum(first[inside], bright * (350 + profile * 65 // 100) // 1000)
        second[inside] = np.maximum(second[inside], other * (500 + profile // 2) // 1000)
    planes = []
    for plane, floor in ((first, 110), (second, 240)):
        texture = box_blur(rng.integers(0, 400, (SIZE, SIZE)).astype(np.int64), 3)
        soft = box_blur(plane, 2)
        value = floor + soft + soft * (texture - 200) // 900 + rng.integers(0, 45, (SIZE, SIZE))
        planes.append(np.clip(value, 0, 65535).astype(np.uint16))
    return np.stack(planes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', required=True); parser.add_argument('--out', required=True)
    parser.add_argument('--device', default='cpu'); parser.add_argument('--reference')
    args = parser.parse_args()
    import tifffile
    payload, out = Path(args.payload).resolve(), Path(args.out).resolve()
    if out.exists(): raise SystemExit('Choose a new output folder.')
    (out / 'input').mkdir(parents=True)
    inputs = {}
    for index in range(FIELDS):
        name = f'synthetic_{index + 1}.tif'
        tifffile.imwrite(out / 'input' / name, field(1000 + index), photometric='minisblack')
        inputs[name] = sha(out / 'input' / name)
    reference = json.loads(Path(args.reference).read_text(encoding='utf-8')) if args.reference else None
    report = dict(platform=platform.platform(), machine=platform.machine(), device=args.device, inputs=inputs)
    if reference and reference['inputs'] != inputs:
        report['result'] = 'inputs differ'
        (out / 'cross_check.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=1)); raise SystemExit(2)
    config = dict(schema_version=1, title='Cross-check on generated fields', plane_axis='channel',
        axis_evidence='Program-generated two-channel 2D fields',
        channels=[dict(id='C1', page=0, label='Generated A', kind='fluorescence', measure=True, saturation_value=65535),
                  dict(id='C2', page=1, label='Generated B', kind='fluorescence', measure=True, saturation_value=65535)],
        fields=[dict(id=Path(name).stem, path='input/' + name) for name in inputs], segmentation_channels=['C1'],
        edge_width_px=6, ratios=[],
        background=dict(mask_channel='C1', foreground_channel='C1', mad_multiplier=5, dilation_iterations=5, min_pixels=100, min_fraction=.01),
        parameters=dict(diameter=60, flow_threshold=.4, cellprob_threshold=0, min_size=15, normalize=True, niter=None, batch_size=4, do_3D=False),
        notes=['Generated fields for comparing computers; not a segmentation-accuracy benchmark.'])
    (out / 'config.json').write_text(json.dumps(config, indent=1) + '\n', encoding='utf-8', newline='\n')
    started = time.time()
    done = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(payload / 'app/launcher.py'), 'run',
                           '--config', str(out / 'config.json'), '--out', str(out / 'results'), '--device', args.device],
                          capture_output=True, text=True, encoding='utf-8')
    report['seconds'] = round(time.time() - started, 1)
    if done.returncode:
        print(done.stdout[-3000:]); print(done.stderr[-3000:]); raise SystemExit(1)
    results = out / 'results'
    events = [json.loads(line) for line in done.stdout.splitlines() if line.startswith('{')]
    report['objects'] = {e['field']: e['objects'] for e in events if e.get('event') == 'progress' and 'field' in e}
    report['seconds_per_field'] = [e['seconds'] for e in events if e.get('event') == 'progress' and 'field' in e]
    # fields.csv, the report and the manifests name this computer's folders; the masks and the two tables do not.
    compared = sorted((results / 'masks').glob('*.tif')) + sorted((results / 'background_masks').glob('*.tif')) + [results / 'measurements.csv', results / 'field_summary.csv']
    report['outputs'] = {p.relative_to(results).as_posix(): sha(p) for p in compared}
    manifest = json.loads((results / 'run_manifest.json').read_text(encoding='utf-8'))
    report['versions'] = manifest['versions']; report['python'] = manifest['python']; report['threads'] = manifest.get('threads')
    if reference:
        differing = sorted(k for k in set(report['outputs']) | set(reference['outputs']) if report['outputs'].get(k) != reference['outputs'].get(k))
        report['reference'] = dict(platform=reference.get('platform'), device=reference.get('device'), objects=reference.get('objects'))
        report['differing'] = differing; report['result'] = 'outputs differ' if differing else 'identical'
        if differing:
            # How far apart: pixels whose label differs, and whether a cell count changed.
            import numpy as np
            detail = {}
            for name in differing:
                if not name.startswith('masks/'): continue
                theirs = reference.get('mask_summary', {}).get(name)
                mine = tifffile.imread(results / name)
                detail[name] = dict(objects=int(mine.max()), foreground_pixels=int(np.count_nonzero(mine)), reference=theirs)
            report['mask_detail'] = detail
    else:
        import numpy as np
        report['mask_summary'] = {p.relative_to(results).as_posix(): dict(objects=int(tifffile.imread(p).max()), foreground_pixels=int(np.count_nonzero(tifffile.imread(p))))
                                  for p in sorted((results / 'masks').glob('*.tif'))}
    (out / 'cross_check.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=1))
    if reference and report['differing']: raise SystemExit(3)


if __name__ == '__main__':
    main()
