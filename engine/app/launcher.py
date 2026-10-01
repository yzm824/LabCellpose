"""Portable local entry point: no agent SDK, installation or network downloads."""
from pathlib import Path
import argparse, contextlib, hashlib, http.server, importlib.metadata, io, json, os, platform, re, stat, subprocess, sys, tempfile, unittest, uuid
APP=Path(__file__).resolve().parent
ROOT=APP.parent
sys.path.insert(0,str(APP))
import analyze
VERSION=analyze.VERSION

def system_check():
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('Apple Silicon macOS is required; use a native terminal.')
    version=tuple(int(n) for n in platform.mac_ver()[0].split('.')[:2])
    if version<(14,0):raise ValueError('This runtime requires macOS 14 or later. Only macOS 27 has been tested for this pilot release.')
    if Path(sys.prefix).resolve()!=(ROOT/'runtime').resolve():raise ValueError('Use LabCellpose.command so the bundled runtime is selected.')
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['CELLPOSE_LOCAL_MODELS_PATH']=str(ROOT/'models')
    os.environ['MPLBACKEND']='Agg'
    os.environ['PYTHONNOUSERSITE']='1'

def doctor(verify=False):
    system_check()
    expected=json.loads((ROOT/'DEPENDENCIES.json').read_text())
    if platform.python_version()!=expected['python']:raise ValueError('Bundled Python version mismatch')
    actual={p['name']:importlib.metadata.version(p['name']) for p in expected['packages']}
    wrong={p['name']:[p['version'],actual[p['name']]] for p in expected['packages'] if actual[p['name']]!=p['version']}
    if wrong:raise ValueError('Dependency mismatch: '+json.dumps(wrong))
    import torch,numpy,scipy,tifffile,skimage
    for mod in [torch,numpy,scipy,tifffile,skimage]:
        if not Path(mod.__file__).resolve().is_relative_to(ROOT/'runtime'):raise ValueError('A module was loaded outside the bundled runtime')
    model=ROOT/'models/cpsam_v2'
    if not model.is_file():raise ValueError('Bundled model is missing')
    if analyze.file_sha(model)!=analyze.MODEL_SHA256:raise ValueError('Bundled model checksum mismatch')
    if verify:
        hashes=json.loads((ROOT/'FILE_HASHES.json').read_text())
        for relative,expected_sha in hashes.items():
            p=ROOT/relative
            if not p.is_file() or analyze.file_sha(p)!=expected_sha:raise ValueError('Package integrity check failed: '+relative)
    report=dict(package=VERSION,platform=platform.platform(),python=platform.python_version(),runtime=str(ROOT/'runtime'),
        package_dependencies=len(actual),model='cpsam_v2',model_sha256=analyze.MODEL_SHA256,
        mps_available=torch.backends.mps.is_available(),cpu_available=True,full_integrity_verified=verify,
        isolated_python=sys.flags.isolated==1,network_downloads_required=False)
    print(json.dumps(report,indent=2),flush=True)
    return report

def prepare(args):
    target=Path(args.out).expanduser().resolve()
    inventory_path=target.with_name(target.stem+'.inventory.json')
    if target.exists() or inventory_path.exists():raise ValueError('Configuration or inventory already exists; choose a new name.')
    if not args.confirm_channel_map:raise ValueError('Confirm the preset channel order with the researcher, then pass --confirm-channel-map.')
    if args.limit is not None and args.limit<1:raise ValueError('--limit must be positive')
    preset_path=ROOT/'presets/ryu-five-channel.json' if args.preset=='ryu-five-channel' else Path(args.preset).expanduser().resolve()
    config=json.loads(preset_path.read_text())
    target.parent.mkdir(parents=True,exist_ok=True)
    analyze.inspect_input(args.input,inventory_path)
    inventory=json.loads(inventory_path.read_text())
    records=[]
    for r in inventory['records']:
        if r['status']!='inspected':continue
        if args.match and args.match.casefold() not in (r.get('member') or r['path']).casefold():continue
        if r['shape'][0]!=len(config['channels']):raise ValueError('Preset channel count does not match '+(r.get('member') or r['path']))
        records.append(r)
    if not records:raise ValueError('No supported matching images. Inspect the inventory before proceeding.')
    selected=records if args.all_fields else records[:args.limit or 1]
    fields=[]
    for r in selected:
        name=r.get('member') or Path(r['path']).name
        slug=re.sub(r'[^A-Za-z0-9_-]+','_',str(Path(name).with_suffix(''))).strip('_')[-65:]
        fid=(slug or 'field')+'_'+hashlib.sha256(name.encode()).hexdigest()[:8]
        f={'id':fid,'path':r['path']}
        f.update(input_sha256=r['input_sha256'], metadata_sha256=r['metadata_sha256'])
        if r.get('member'):f['member']=r['member']
        fields.append(f)
    config['fields']=fields
    config['input_confirmation']='sha256-v1'
    config['axis_evidence']='Researcher explicitly confirmed the preset channel order and co-registered 2D TIFF pages during preparation.'
    if args.segmentation:config['segmentation_channels']=args.segmentation.split(',')
    analyze.validate_config(config)
    analyze.dump(target,config)
    print(json.dumps({'config':str(target),'inventory':str(inventory_path),'selected_fields':fields,
        'supported_matching_fields':len(records),'unsupported_files':inventory['counts']['unsupported'],
        'selection':'all requested' if args.all_fields else 'pilot subset; default is one field',
        'next':'Review the inventory and config, then run LabCellpose.command run --config ... --out NEW_DIRECTORY'},indent=2),flush=True)

def run_analysis(config,out,device):
    system_check()
    args=argparse.Namespace(config=str(config),out=str(out),weights=str(ROOT/'models/cpsam_v2'),weights_sha256=analyze.MODEL_SHA256,device=device)
    analyze.run(args)

def self_test(args):
    doctor()
    suite=unittest.defaultTestLoader.discover(str(APP),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise ValueError('Numerical contract tests failed')
    if args.inference:
        if not args.out:raise ValueError('--inference requires --out NEW_DIRECTORY')
        dest=Path(args.out).expanduser().resolve()
        if dest.exists():raise ValueError('Self-test output directory already exists')
        dest.mkdir(parents=True)
        import numpy as np,tifffile
        y,x=np.mgrid[:256,:256];a=np.full((256,256),100.,dtype=float)
        for cx,cy,sx,sy in [(62,62,20,14),(168,77,23,17),(100,177,16,24)]:
            a+=1800*np.exp(-(((x-cx)/sx)**2+((y-cy)/sy)**2)/2)
        stack=np.stack([a,a*1.7+50]).astype('uint16');tifffile.imwrite(dest/'synthetic.tif',stack,photometric='minisblack')
        config=dict(schema_version=1,title='Synthetic installation test',plane_axis='channel',axis_evidence='Program-generated two-channel 2D fixture',
          channels=[dict(id='C1',page=0,label='Synthetic A',kind='fluorescence',measure=True,saturation_value=65535),dict(id='C2',page=1,label='Synthetic B',kind='fluorescence',measure=True,saturation_value=65535)],
          fields=[dict(id='synthetic',path='synthetic.tif')],segmentation_channels=['C1'],edge_width_px=6,ratios=[],
          background=dict(mask_channel='C1',foreground_channel='C1',mad_multiplier=5,dilation_iterations=5,min_pixels=100,min_fraction=.01),
          parameters=dict(diameter=40,flow_threshold=.4,cellprob_threshold=0,min_size=15,normalize=True,niter=None,batch_size=4,do_3D=False),
          notes=['Synthetic installation check, not a biological segmentation-accuracy benchmark.'])
        analyze.dump(dest/'config.json',config)
        run_analysis(dest/'config.json',dest/'results',args.device)
    print('SELF-TEST PASSED',flush=True)

RESULT_FILE_LIMIT = 128 << 20
RESULT_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; frame-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
LEGACY_NOTICE = b'''<!doctype html><html lang="en"><meta charset="utf-8"><title>LabCellpose - older result</title>
<style>body{font:16px -apple-system,system-ui;color:#22223b;max-width:720px;margin:70px auto;padding:24px;line-height:1.6}a{color:#43547b}</style>
<h1>This older result has no reusable viewer data</h1><p>Its original HTML is not executed. Your original analysis files have not been changed.</p>
<p><a href="measurements.csv" download>Download original measurements (CSV)</a></p>
<p>Use Show result folder to access the saved files. Re-run the original images to create an interactive report in this version.</p></html>'''

def open_result_file(folder, name):
    """Read only a regular, non-symlink child; do not resolve then re-open a link."""
    root_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
    finally: os.close(root_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > RESULT_FILE_LIMIT:
            raise ValueError('Result file is not a regular file within the 128 MiB viewer limit')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd); raise

def read_result_file(folder, name):
    with open_result_file(folder,name) as stream: raw = stream.read(RESULT_FILE_LIMIT+1)
    if len(raw)>RESULT_FILE_LIMIT: raise ValueError('Result file grew beyond the viewer size limit')
    return raw

class ResultHandler(http.server.SimpleHTTPRequestHandler):
    """Serve a trusted temporary report and explicit data downloads only."""
    def __init__(self, *args, report_index=None, **kwargs):
        self.report_index = report_index
        super().__init__(*args, **kwargs)

    def send_head(self):
        from urllib.parse import urlsplit
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            self.send_error(403, 'Invalid result viewer host'); return None
        path = urlsplit(self.path).path
        try:
            if path in ('/', '/index.html'):
                if self.report_index:
                    target = Path(self.report_index)
                    stream = open_result_file(target.parent,target.name)
                else: stream = io.BytesIO(LEGACY_NOTICE)
                content_type = 'text/html; charset=utf-8'
            elif path in ('/measurements.csv','/field_summary.csv'):
                stream = open_result_file(self.directory,path[1:])
                content_type = 'text/csv; charset=utf-8'
            else:
                self.send_error(404, 'Result asset not available'); return None
            size = len(stream.getbuffer()) if isinstance(stream,io.BytesIO) else os.fstat(stream.fileno()).st_size
            self.send_response(200)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(size))
            if content_type.startswith('text/csv'): self.send_header('Content-Disposition',f'attachment; filename="{path[1:]}"')
            self.end_headers();return stream
        except (OSError,ValueError):
            self.send_error(404, 'Result asset is unavailable or unsafe');return None

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy',RESULT_CSP)
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()

def prepare_viewer(folder, destination):
    """Refresh presentation in temporary storage; preserve run data and QC identity."""
    source = folder/'viewer_data.json'
    if not source.exists() and not source.is_symlink():
        destination.write_bytes(LEGACY_NOTICE);return destination
    from render_review import render
    viewer = json.loads(read_result_file(folder,'viewer_data.json'))
    runinfo = json.loads(read_result_file(folder,'run_manifest.json'))
    render(viewer['config'], viewer['fields'], read_result_file(folder,'measurements.csv').decode('utf-8'), runinfo, destination)
    return destination

def view(args):
    folder=Path(args.run).expanduser().resolve()
    if not (folder/'index.html').is_file():raise ValueError('Result folder must contain index.html')
    import functools,webbrowser
    with tempfile.TemporaryDirectory(prefix='labcellpose-view-') as temp:
        report_index=prepare_viewer(folder,Path(temp)/'index.html')
        handler=functools.partial(ResultHandler,directory=str(folder),report_index=report_index)
        with http.server.ThreadingHTTPServer(('127.0.0.1',args.port),handler) as server:
            # Keep the origin stable for QC storage while giving each viewer session a fresh URL.
            url=f'http://127.0.0.1:{server.server_port}/?view={uuid.uuid4().hex}'
            print(json.dumps({'viewer':url,'serving':str(folder),'stop':'Ctrl+C','qc_note':'Keep this port for browser QC persistence; save QC JSON for transfer.'}),flush=True)
            if not args.no_open:webbrowser.open(url)
            try:server.serve_forever()
            except KeyboardInterrupt:pass

def main():
    p=argparse.ArgumentParser(description=f'LabCellpose {VERSION}: offline Apple Silicon analysis and review. Read START_HERE.md first.')
    commands=p.add_subparsers(dest='command')
    d=commands.add_parser('doctor',help='Check bundled runtime, libraries and model');d.add_argument('--verify-all',action='store_true')
    t=commands.add_parser('self-test',help='Check numerical contracts, optionally run synthetic inference');t.add_argument('--inference',action='store_true');t.add_argument('--out');t.add_argument('--device',choices=['auto','cpu','mps'],default='auto')
    i=commands.add_parser('inspect',help='Inventory raw TIFFs, a folder or ZIP');i.add_argument('--input',required=True);i.add_argument('--out',required=True)
    a=commands.add_parser('prepare',help='Create an editable experiment config; default is a one-field pilot');a.add_argument('--input',required=True);a.add_argument('--preset',default='ryu-five-channel');a.add_argument('--confirm-channel-map',action='store_true');a.add_argument('--out',required=True);a.add_argument('--match');a.add_argument('--segmentation',help='Comma-separated channel IDs; must include the background mask channel')
    selection=a.add_mutually_exclusive_group();selection.add_argument('--limit',type=int);selection.add_argument('--all-fields',action='store_true')
    r=commands.add_parser('run',help='Analyze with bundled model and fixed methods');r.add_argument('--config',required=True);r.add_argument('--out',required=True);r.add_argument('--device',choices=['auto','cpu','mps'],default='auto')
    v=commands.add_parser('view',help='Serve a result folder on localhost');v.add_argument('--run',required=True);v.add_argument('--port',type=int,default=8765);v.add_argument('--no-open',action='store_true')
    args=p.parse_args()
    if not args.command:p.print_help();return
    system_check()
    # Keep plotting caches out of user/home directories and the portable package.
    with tempfile.TemporaryDirectory(prefix='labcellpose-cache-') as cache:
        os.environ['MPLCONFIGDIR']=cache
        if args.command=='doctor':doctor(args.verify_all)
        elif args.command=='self-test':self_test(args)
        elif args.command=='inspect':analyze.inspect_input(args.input,args.out)
        elif args.command=='prepare':prepare(args)
        elif args.command=='run':run_analysis(Path(args.config).expanduser().resolve(),Path(args.out).expanduser().resolve(),args.device)
        elif args.command=='view':view(args)

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Interrupted. Keep partial output for diagnosis; retry in a new output directory.',file=sys.stderr);sys.exit(130)
    except Exception as e:print(f'ERROR: {type(e).__name__}: {e}',file=sys.stderr);sys.exit(1)
