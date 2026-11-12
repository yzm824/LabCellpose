"""Portable local entry point: no agent SDK, installation or network downloads."""
from pathlib import Path
import argparse, contextlib, hashlib, hmac, http.server, importlib.metadata, io, json, os, platform, re, secrets, signal, stat, subprocess, sys, tempfile, threading, time, unittest, uuid
APP=Path(__file__).resolve().parent
ROOT=APP.parent
sys.path.insert(0,str(APP))
import analyze
VERSION=analyze.VERSION

WINDOWS=os.name=='nt'

def system_check():
    if WINDOWS:
        import sysconfig
        if sysconfig.get_platform()!='win-amd64':raise ValueError('The 64-bit Windows runtime of this package is required.')
        if sys.getwindowsversion().major<10:raise ValueError('This runtime requires Windows 10 or later.')
        # Every file is read and written as UTF-8; without this mode Windows would use the system code page.
        if not sys.flags.utf8_mode:raise ValueError('Use LabCellpose.cmd so the bundled runtime starts in UTF-8 mode.')
    else:
        if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('Apple Silicon macOS is required; use a native terminal.')
        version=tuple(int(n) for n in platform.mac_ver()[0].split('.')[:2])
        if version<(14,0):raise ValueError('This runtime requires macOS 14 or later. Only macOS 27 has been tested for this pilot release.')
    if Path(sys.prefix).resolve()!=(ROOT/'runtime').resolve():raise ValueError(f"Use LabCellpose.{'cmd' if WINDOWS else 'command'} so the bundled runtime is selected.")
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
        slug=re.sub(r'[^A-Za-z0-9_-]+','_',str(Path(name).with_suffix('')))[-65:].strip('_-')
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

RESULT_FILE_LIMIT = analyze.REVIEW_REPORT_LIMIT
VIEWER_DATA_LIMIT = 384 << 20
QC_STATE_NAME = 'qc_review_state.json'
QC_STATE_LIMIT = 16 << 20
RESULT_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; frame-src 'self'; frame-ancestors 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'"
LEGACY_NOTICE = b'''<!doctype html><html lang="en"><meta charset="utf-8"><title>LabCellpose - older result</title>
<style>body{font:16px -apple-system,system-ui;color:#22223b;max-width:720px;margin:70px auto;padding:24px;line-height:1.6}a{color:#43547b}</style>
<h1>This older result has no reusable viewer data</h1><p>Its original HTML is not executed. Your original analysis files have not been changed.</p>
<p><a href="measurements.csv" download>Download original measurements (CSV)</a></p>
<p>Use Show result folder to access the saved files. Re-run the original images to create an interactive report in this version.</p></html>'''
_QC_LOCK = threading.Lock()

def _unlinked(path):
    """Windows: the entry itself, which must not be a symbolic link or a junction. Other reparse points are not
    links: files kept in a cloud-synced folder such as OneDrive carry one and must stay readable."""
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_reparse_tag', 0) in (0xA000000C, 0xA0000003):   # symlink, mount point
        raise OSError(f'{Path(path).name} is a link; links are not opened')
    return info

def _result_child(folder, name):
    """Windows: the path of a direct child of a result folder that is a real folder."""
    if not stat.S_ISDIR(_unlinked(folder).st_mode): raise NotADirectoryError(str(folder))
    if not name or Path(name).name != name: raise ValueError(f'{name} is not a file of the result folder')
    return os.path.join(folder, name)

def open_result_file(folder, name, limit=RESULT_FILE_LIMIT):
    """Read only a regular, non-symlink child; do not resolve then re-open a link."""
    if WINDOWS:
        # No O_NOFOLLOW or openat here: refuse links first, then check that the file that was opened is that entry.
        path = _result_child(folder, name); entry = _unlinked(path)
        fd = os.open(path, os.O_RDONLY | os.O_BINARY)
    else:
        entry = None
        root_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
        finally: os.close(root_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f'{name} is not a regular file; links and special files are not opened')
        if entry is not None and (info.st_ino, info.st_dev) != (entry.st_ino, entry.st_dev):
            raise ValueError(f'{name} changed while it was opened')
        if info.st_size > limit:
            raise ValueError(f'{name} is {info.st_size/2**20:.0f} MiB, above the {limit>>20} MiB limit for opening results')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd); raise

def read_result_file(folder, name, limit=RESULT_FILE_LIMIT):
    with open_result_file(folder,name,limit) as stream: raw = stream.read(limit+1)
    if len(raw)>limit: raise ValueError(f'{name} grew beyond the {limit>>20} MiB limit while it was read')
    return raw

def valid_qc_state(state, dataset_id):
    return (isinstance(state, dict) and state.get('schema_version') == 1 and state.get('dataset_id') == dataset_id
            and type(state.get('revision')) is int and state['revision'] >= 0
            and isinstance(state.get('excluded'), list) and isinstance(state.get('history'), list))

def read_qc_state(folder, dataset_id):
    """Returns (state|None, raw|None, damaged)."""
    try: raw = read_result_file(folder, QC_STATE_NAME, QC_STATE_LIMIT)
    except FileNotFoundError: return None, None, False
    try: state = json.loads(raw)
    except ValueError: return None, raw, True
    return (state, raw, False) if valid_qc_state(state, dataset_id) else (None, raw, True)

def write_qc_file(folder, name, data, replace_existing):
    """Write a new file inside the result folder without following links; atomic replace for the QC state."""
    if WINDOWS:
        temp = _result_child(folder, f'.{name}.{uuid.uuid4().hex}.tmp' if replace_existing else name)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY, 0o644)   # O_EXCL never opens an existing link
        try:
            with os.fdopen(fd, 'wb', closefd=False) as stream: stream.write(data); stream.flush(); os.fsync(fd)
        finally: os.close(fd)
        if replace_existing:
            target = _result_child(folder, name)
            for attempt in range(20):
                # Replacing fails while another request still has the old file open for reading; that takes a moment.
                try: os.replace(temp, target); break
                except PermissionError:
                    if attempt == 19: os.unlink(temp); raise
                    time.sleep(0.05)
        return
    root_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        temp = f'.{name}.{uuid.uuid4().hex}.tmp' if replace_existing else name
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=root_fd)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as stream: stream.write(data); stream.flush(); os.fsync(fd)
        finally: os.close(fd)
        if replace_existing: os.replace(temp, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
    finally: os.close(root_fd)

class ResultHandler(http.server.SimpleHTTPRequestHandler):
    """Serve a trusted temporary report, explicit data downloads and the run's QC review state only."""
    timeout = 30  # drop idle keep-alive connections instead of holding a thread forever

    def __init__(self, *args, report_index=None, qc_store=None, **kwargs):
        self.report_index = report_index
        self.qc_store = qc_store
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        pass  # no per-request stderr output: the app pipe must not be able to stall the server

    def trusted_request(self):
        port = self.server.server_port
        if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            self.send_error(403, 'Invalid result viewer host'); return False
        return True

    def qc_authorized(self):
        if not self.qc_store: self.send_error(404, 'Review state storage is not available'); return False
        port = self.server.server_port
        origin = self.headers.get('Origin')
        if origin not in (None, f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
            self.send_error(403, 'Invalid origin'); return False
        if not hmac.compare_digest(self.headers.get('X-LabCellpose-QC', ''), self.qc_store['token']):
            self.send_error(403, 'Missing review session token'); return False
        return True

    def json_reply(self, status, value):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(body)

    def send_head(self):
        from urllib.parse import urlsplit
        if not self.trusted_request(): return None
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
            elif path == '/' + QC_STATE_NAME:
                if self.qc_authorized(): self.get_qc_state()
                return None
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

    def get_qc_state(self):
        try: state, _, damaged = read_qc_state(self.directory, self.qc_store['dataset_id'])
        except (OSError, ValueError) as error:
            self.json_reply(409, {'error': f'Saved review state cannot be read: {error}'}); return
        self.json_reply(200, {'state': state, 'damaged': damaged})

    def do_POST(self):
        from urllib.parse import urlsplit
        if not self.trusted_request(): return
        if urlsplit(self.path).path != '/' + QC_STATE_NAME: self.send_error(404, 'Result asset not available'); return
        if not self.qc_authorized(): return
        if not self.headers.get('Content-Type', '').startswith('application/json'): self.send_error(415, 'JSON required'); return
        try: length = int(self.headers.get('Content-Length', ''))
        except ValueError: self.send_error(411, 'Length required'); return
        if not 0 < length <= QC_STATE_LIMIT: self.send_error(413, 'Review state is too large'); return
        try:
            request = json.loads(self.rfile.read(length))
            state, base, replace = request['state'], request.get('base_revision'), request.get('replace') is True
        except (ValueError, KeyError, TypeError):
            self.send_error(400, 'Invalid review state request'); return
        dataset_id = self.qc_store['dataset_id']
        if not valid_qc_state(state, dataset_id) or (base is not None and type(base) is not int):
            self.send_error(400, 'Review state does not belong to this result'); return
        data = json.dumps(state, ensure_ascii=False, allow_nan=False).encode('utf-8')
        with _QC_LOCK:
            try:
                stored, raw, damaged = read_qc_state(self.directory, dataset_id)
                if stored is not None and not replace and stored != state and (base is None or stored['revision'] != base):
                    self.json_reply(409, {'state': stored, 'conflict': True}); return
                if raw is not None and (damaged or (replace and stored != state)):
                    kind = 'damaged' if damaged else 'backup'
                    write_qc_file(self.directory, f'qc_review_state.{kind}-{time.strftime("%Y%m%d_%H%M%S")}-{uuid.uuid4().hex[:6]}.json', raw, False)
                write_qc_file(self.directory, QC_STATE_NAME, data, True)
            except (OSError, ValueError) as error:
                self.json_reply(507, {'error': f'The result folder cannot store review decisions: {error}'}); return
        self.json_reply(200, {'ok': True, 'revision': state['revision']})

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy',RESULT_CSP)
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','SAMEORIGIN')
        super().end_headers()

def prepare_viewer(folder, destination, qc_token=None, info=None):
    """Refresh presentation in temporary storage; preserve run data and QC identity."""
    from render_review import render_within
    source = folder/'viewer_data.json'
    if not source.exists() and not source.is_symlink():
        destination.write_bytes(LEGACY_NOTICE);return destination
    viewer = json.loads(read_result_file(folder,'viewer_data.json',VIEWER_DATA_LIMIT))
    runinfo = json.loads(read_result_file(folder,'run_manifest.json'))
    store = dict(token=qc_token, path=QC_STATE_NAME) if qc_token else None
    ids = render_within(viewer['config'], viewer['fields'], read_result_file(folder,'measurements.csv').decode('utf-8'), runinfo,
                        destination, RESULT_FILE_LIMIT, qc_store=store)
    if info is not None: info.update(ids)
    return destination

def when_parent_exits(action, interval=1.0):
    """Run action once, on a background thread, when the process that started this one has exited."""
    parent = os.getppid()
    if WINDOWS:
        # A Windows process keeps the ID of its parent after the parent has gone, so wait on the parent itself.
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p; kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.WaitForSingleObject.restype = ctypes.c_uint32; kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        handle = kernel.OpenProcess(0x00100000, False, parent)   # SYNCHRONIZE
        if not handle: return
        def watch():
            if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) == 0: action()
    else:
        def watch():
            while True:
                time.sleep(interval)
                if os.getppid() != parent:
                    action(); return
    threading.Thread(target=watch, daemon=True).start()

def stop_when_orphaned(server, interval=1.0):
    """The desktop app owns this server; if the app exits abnormally, stop instead of holding the port."""
    when_parent_exits(server.shutdown, interval)

def stdin_lines():
    """Lines of standard input for a background thread, read from the descriptor itself. A daemon thread that is
    waiting inside sys.stdin when the program ends can abort the interpreter's shutdown."""
    pending = b''
    if WINDOWS:
        # Never wait inside a read here. While any thread waits in a read of the standard-input pipe, Windows makes
        # every library that sets up its own C runtime while loading (numpy's and torch's do) wait for that read
        # too, and the program stands still. So look whether something has arrived, and read only what is there.
        import ctypes, msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.PeekNamedPipe.restype = ctypes.c_int
        kernel.PeekNamedPipe.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        try: handle = msvcrt.get_osfhandle(0)
        except (OSError, ValueError): return
        waiting = ctypes.c_uint32(0)
    while True:
        size = 65536
        if WINDOWS:
            if not kernel.PeekNamedPipe(handle, None, 0, None, ctypes.byref(waiting), None): return   # the other end has closed
            if not waiting.value:
                time.sleep(0.1); continue
            size = min(waiting.value, 65536)
        try: chunk = os.read(0, size)
        except OSError: return
        if not chunk: return
        pending += chunk
        while b'\n' in pending:
            line, pending = pending.split(b'\n', 1)
            yield line.decode('utf-8', 'replace').rstrip('\r')

def stop_on_request(server):
    """--control-stdin: the app ends this viewer by writing 'stop' to it or closing its input. Windows cannot
    deliver SIGTERM to a process, and ending it by force would leave the temporary report behind."""
    def watch():
        for line in stdin_lines():
            if line.strip() == 'stop': break
        server.shutdown()
    threading.Thread(target=watch, daemon=True).start()

def _interrupt(signum, frame):
    raise KeyboardInterrupt

def view(args):
    folder=Path(args.run).expanduser().resolve()
    if not (folder/'index.html').is_file():raise ValueError('Result folder must contain index.html')
    import functools,webbrowser
    signal.signal(signal.SIGTERM, _interrupt)  # the app stops viewers with SIGTERM: still remove the temporary report
    with tempfile.TemporaryDirectory(prefix='labcellpose-view-') as temp:
        token=secrets.token_urlsafe(32);info={}
        report_index=prepare_viewer(folder,Path(temp)/'index.html',qc_token=token,info=info)
        store=dict(token=token,dataset_id=info['dataset_id']) if info else None
        handler=functools.partial(ResultHandler,directory=str(folder),report_index=report_index,qc_store=store)
        with http.server.ThreadingHTTPServer(('127.0.0.1',args.port),handler) as server:
            # Keep the origin stable for QC storage while giving each viewer session a fresh URL.
            url=f'http://127.0.0.1:{server.server_port}/?view={uuid.uuid4().hex}'
            print(json.dumps({'viewer':url,'serving':str(folder),'stop':'Ctrl+C','qc_note':'Review decisions are saved in qc_review_state.json inside the result folder when it is writable; save QC JSON for transfer.'}),flush=True)
            stop_when_orphaned(server)
            if args.control_stdin:stop_on_request(server)
            if not args.no_open:webbrowser.open(url)
            try:server.serve_forever()
            except KeyboardInterrupt:pass

def main():
    p=argparse.ArgumentParser(description=f'LabCellpose {VERSION}: offline analysis and review on this computer.')
    commands=p.add_subparsers(dest='command')
    d=commands.add_parser('doctor',help='Check bundled runtime, libraries and model');d.add_argument('--verify-all',action='store_true')
    t=commands.add_parser('self-test',help='Check numerical contracts, optionally run synthetic inference');t.add_argument('--inference',action='store_true');t.add_argument('--out');t.add_argument('--device',choices=['auto','cpu','mps'],default='auto')
    i=commands.add_parser('inspect',help='Inventory raw TIFFs, a folder or ZIP');i.add_argument('--input',required=True);i.add_argument('--out',required=True)
    a=commands.add_parser('prepare',help='Create an editable experiment config; default is a one-field pilot');a.add_argument('--input',required=True);a.add_argument('--preset',default='ryu-five-channel');a.add_argument('--confirm-channel-map',action='store_true');a.add_argument('--out',required=True);a.add_argument('--match');a.add_argument('--segmentation',help='Comma-separated channel IDs; must include the background mask channel')
    selection=a.add_mutually_exclusive_group();selection.add_argument('--limit',type=int);selection.add_argument('--all-fields',action='store_true')
    r=commands.add_parser('run',help='Analyze with bundled model and fixed methods');r.add_argument('--config',required=True);r.add_argument('--out',required=True);r.add_argument('--device',choices=['auto','cpu','mps'],default='auto')
    v=commands.add_parser('view',help='Serve a result folder on localhost');v.add_argument('--run',required=True);v.add_argument('--port',type=int,default=8765);v.add_argument('--no-open',action='store_true');v.add_argument('--control-stdin',action='store_true',help="stop when 'stop' is written to standard input or it closes")
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
