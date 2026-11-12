"""Regression tests for the 1.4 reliability fixes (2026-10-08 audit): input isolation, review budget,
saved-result rendering, result-folder QC storage, viewer lifecycle and server hardening."""
import base64, functools, http.client, http.server, io, json, os, signal, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path
import numpy as np
import tifffile
import analyze, launcher, render_review
from analyze import ResourceLimitError

APP = Path(__file__).resolve().parent


def can_symlink(folder):
    """Windows lets only some accounts create symbolic links; the link checks are skipped where it does not."""
    probe = Path(folder) / 'link-probe'
    try: probe.symlink_to(Path(folder) / 'link-target')
    except (OSError, NotImplementedError): return False
    probe.unlink(); return True


def running(pid):
    """Whether a process still exists. (On Windows os.kill(pid, 0) would end it.)"""
    if os.name != 'nt':
        try: os.kill(pid, 0)
        except ProcessLookupError: return False
        return True
    import ctypes
    kernel = ctypes.WinDLL('kernel32')
    kernel.OpenProcess.restype = ctypes.c_void_p; kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]; kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle: return False
    try: return kernel.WaitForSingleObject(handle, 0) == 0x102   # WAIT_TIMEOUT: it has not exited
    finally: kernel.CloseHandle(handle)


def tiled_tiff_with_zero_tile_length(path):
    tifffile.imwrite(path, np.arange(2 * 32 * 32, dtype='uint16').reshape(2, 32, 32), photometric='minisblack', tile=(16, 16))
    with tifffile.TiffFile(path) as tf:
        tag = tf.pages[0].tags['TileLength']; offset = tag.valueoffset; width = 4 if int(tag.dtype) == 4 else 2
    raw = bytearray(path.read_bytes()); raw[offset:offset + width] = bytes(width)
    path.write_bytes(bytes(raw))


def jpeg_url(side, seed=0):
    from PIL import Image
    pixels = np.random.default_rng(seed).integers(0, 255, (side, side), dtype=np.uint8)
    out = io.BytesIO(); Image.fromarray(pixels).save(out, format='JPEG', quality=82)
    return render_review.JPEG_PREFIX + base64.b64encode(out.getvalue()).decode()


def saved_result(folder, previews=None):
    config = {'channels': [{'id': 'C1', 'label': 'Test'}], 'segmentation_channels': ['C1'], 'background': {'estimator': 'median'}}
    region = lambda path: {'area': 4, 'path': path, 'offset': [0, 0], 'channels': {'C1': {'mean': 5.0, 'sum': 20, 'saturated': 0, 'corrected': 4.0, 'correctedSum': 16.0, 'background': 1.0}}}
    fields = {'f1': {'shape': [32, 32], 'objects': {'C1': [{'id': 1, 'bbox': [0, 0, 2, 2], 'regions': {'whole': region('M0,0L2,0L2,2Z'), 'edge': region('M0,0L2,0L2,2ZM1,1Z'), 'interior': None}}]},
                     'background': {'valid': True, 'medians': {'C1': 1.0}}, 'images': previews or {}, 'fixedImages': previews or {}}}
    csv_text = 'field,segmentation_channel,object_id,region,measurement_channel\r\n' + ''.join(f'f1,C1,1,{r},C1\r\n' for r in ('whole', 'edge', 'interior'))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'viewer_data.json').write_text(json.dumps({'config': config, 'fields': fields}))
    (folder / 'measurements.csv').write_bytes(csv_text.encode())
    (folder / 'run_manifest.json').write_text('{"version":"1.3","status":"complete"}')
    (folder / 'index.html').write_text('original')
    return config, fields, csv_text


class InputIsolation(unittest.TestCase):
    def test_zero_tile_length_is_one_unsupported_file_not_a_failed_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); folder = root / 'images'; folder.mkdir()
            tifffile.imwrite(folder / 'good.tif', np.ones((2, 16, 16), dtype='uint16'), photometric='minisblack')
            tiled_tiff_with_zero_tile_length(folder / 'zero_tile.tif')
            with self.assertRaisesRegex(ValueError, 'Invalid or truncated TIFF'): analyze.read_stack((folder / 'zero_tile.tif').read_bytes())
            analyze.inspect_input(folder, root / 'inventory.json')
            records = {Path(r['path']).name: r for r in json.loads((root / 'inventory.json').read_text())['records']}
            self.assertEqual(records['good.tif']['status'], 'inspected')
            self.assertEqual(records['zero_tile.tif']['status'], 'unsupported')
            self.assertIn('ZeroDivisionError', records['zero_tile.tif']['error'])

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'this system has no FIFOs')
    def test_fifo_sidecar_and_fifo_input_do_not_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); folder = root / 'images'; (folder / 'MetaData').mkdir(parents=True)
            tifffile.imwrite(folder / 'cell.tif', np.ones((2, 16, 16), dtype='uint16'), photometric='minisblack')
            os.mkfifo(folder / 'MetaData' / 'cell.xml'); os.mkfifo(root / 'input.tif')
            def unblock():  # if a reader ever blocks, release it so the test fails instead of hanging
                time.sleep(8)
                for fifo in (folder / 'MetaData' / 'cell.xml', root / 'input.tif'):
                    try: fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK); os.close(fd)
                    except OSError: pass
            threading.Thread(target=unblock, daemon=True).start()
            started = time.time()
            analyze.inspect_input(folder, root / 'inventory.json')
            record = json.loads((root / 'inventory.json').read_text())['records'][0]
            self.assertEqual(record['status'], 'unsupported'); self.assertIn('not a regular file', record['error'])
            with self.assertRaisesRegex(ValueError, 'special file'): analyze.inspect_input(root / 'input.tif', root / 'second.json')
            self.assertLess(time.time() - started, 5)


class ConfigLimits(unittest.TestCase):
    def config(self, **parameters):
        return dict(schema_version=1, plane_axis='channel', axis_evidence='fixture', fields=[dict(id='f1', path='x.tif')],
                    channels=[dict(id='C1', page=0, kind='fluorescence', measure=True)], segmentation_channels=['C1'], edge_width_px=2,
                    background=dict(mask_channel='C1', foreground_channel='C1', mad_multiplier=5, dilation_iterations=1, min_pixels=1, min_fraction=0),
                    parameters=dict(do_3D=False, **parameters), ratios=[])

    def test_diameter_bounds_the_enlarged_segmentation_image(self):
        analyze.check_scaled_size([1, 1024, 1024], 4, 'image')          # 7680 px per side: allowed
        analyze.check_scaled_size([1, 4096, 4096], 15, 'image')         # exactly 8192 px per side
        with self.assertRaisesRegex(ResourceLimitError, 'at least 4 px'): analyze.check_scaled_size([1, 1024, 1024], 3, 'image')
        with self.assertRaisesRegex(ResourceLimitError, 'at least 15 px'): analyze.check_scaled_size([1, 4096, 4096], 1, 'image')
        for bad in (0, -1, float('nan'), True, '60'):
            with self.assertRaisesRegex(ValueError, 'diameter'): analyze.validate_config(self.config(diameter=bad))
        with self.assertRaisesRegex(ValueError, 'Unsupported Cellpose parameters'): analyze.validate_config(self.config(diameter=30, tile_overlap=0.5))
        analyze.validate_config(self.config(diameter=30, flow_threshold=0.4, cellprob_threshold=0, min_size=15, normalize=True, niter=None, batch_size=4))

    def test_ids_must_be_safe_in_the_browser_viewer(self):
        for bad in ('constructor', 'toString', '__proto__', '-ctrl', '_x', 'a b', ''):
            c = self.config(diameter=30); c['channels'][0]['id'] = bad
            c['segmentation_channels'] = [bad]; c['background'].update(mask_channel=bad, foreground_channel=bad)
            with self.assertRaises(ValueError): analyze.validate_config(c)
            c = self.config(diameter=30); c['fields'][0]['id'] = bad
            with self.assertRaises(ValueError): analyze.validate_config(c)


class ReviewBudget(unittest.TestCase):
    def test_previews_shrink_to_fit_and_unreviewable_batches_are_refused_before_inference(self):
        rng = np.random.default_rng(1)
        data = {f'f{i}': {'planes': {'C1': rng.integers(0, 4000, (900, 900), dtype=np.uint16)}} for i in range(3)}
        c = {'channels': [{'id': 'C1'}]}; fixed = {'C1': (0.0, 4000.0)}
        side, previews, total = analyze.build_previews(data, c, fixed)
        self.assertEqual(side, 900); self.assertLessEqual(total, analyze.PREVIEW_BUDGET)
        original = analyze.PREVIEW_BUDGET
        try:
            analyze.PREVIEW_BUDGET = total // 3
            side, previews, small = analyze.build_previews(data, c, fixed)
            self.assertLess(side, 900); self.assertLessEqual(small, analyze.PREVIEW_BUDGET)
            self.assertEqual(previews['f0']['previewMaxSide'], side)
            analyze.PREVIEW_BUDGET = 1000
            with self.assertRaisesRegex(ResourceLimitError, 'too many to review'): analyze.build_previews(data, c, fixed)
        finally: analyze.PREVIEW_BUDGET = original

    def test_field_report_bytes_counts_escaped_payload(self):
        vf = {'objects': {'C1': [{'id': 1, 'regions': {'whole': {'path': 'M0,0Z'}}}]}, 'images': {'C1': 'x' * 10000}}
        rows = [dict(field='f', segmentation_channel='C1', object_id=1, region='whole', measurement_channel='C1')]
        size = analyze.field_report_bytes(vf, rows, list(rows[0]))
        self.assertGreater(size, 40); self.assertLess(size, 1000)   # previews are budgeted separately

    def test_saved_runs_render_within_the_limit_with_unchanged_qc_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'run'
            config, fields, csv_text = saved_result(folder, {'C1': jpeg_url(1024)})
            identity = render_review.make_bundle(config, fields, csv_text)['dataset_id']
            full = len(render_review.render_html(config, fields, csv_text, {}, bundle=render_review.make_bundle(config, fields, csv_text))[0].encode())
            ids = render_review.render_within(config, fields, csv_text, {}, Path(temp) / 'small.html', full // 2)
            self.assertEqual(ids['dataset_id'], identity)
            page = (Path(temp) / 'small.html').read_text()
            self.assertLessEqual(len(page.encode()), full // 2); self.assertIn('previewMaxSide', page)
            with self.assertRaisesRegex(ValueError, 'viewer limit'):
                render_review.render_within(config, fields, csv_text, {}, Path(temp) / 'none.html', 1000)
            view = render_review.display_fields(fields)['f1']['objects']['C1'][0]['regions']
            self.assertIsNone(view['edge']['path']); self.assertEqual(view['whole']['path'], 'M0,0L2,0L2,2Z')
            self.assertNotIn('background', view['whole']['channels']['C1'])   # field medians exist
            self.assertNotIn('correctedSum', view['whole']['channels']['C1'])  # recomputed in the viewer
            fields['f1']['background'] = {'valid': True}
            self.assertEqual(render_review.display_fields(fields)['f1']['objects']['C1'][0]['regions']['whole']['channels']['C1']['background'], 1.0)

    def test_placeholder_text_in_labels_cannot_break_the_report(self):
        config = {'channels': [{'id': 'C1', 'label': '__APP__ <!--QC_HOST_SCRIPT--> __QC_HOST_CONFIG__ __PAYLOAD__ /*__UI_CSS__*/'}], 'segmentation_channels': ['C1']}
        fields = {'f1': {'objects': {'C1': [{'id': 1}]}}}
        csv_text = 'field,segmentation_channel,object_id,region,measurement_channel\r\nf1,C1,1,whole,C1\r\n'
        page, _ = render_review.render_html(config, fields, csv_text, {})
        host = json.loads(page.split("const cfg=", 1)[1].split(",frame=document", 1)[0])
        self.assertEqual(host['segmentation_options'][0][1], config['channels'][0]['label'])
        self.assertEqual(page.count('id="codex-visualization"'), 1); self.assertEqual(page.count('data-srcdoc='), 1)


class ResultServer(unittest.TestCase):
    def serve(self, folder, store=True):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(
            launcher.ResultHandler, directory=str(folder), qc_store={'token': 'secret-token', 'dataset_id': 'ds'} if store else None))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        return server.server_port

    def call(self, port, method, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        base = {'Host': f'127.0.0.1:{port}', 'X-LabCellpose-QC': 'secret-token'}
        if body is not None: base['Content-Type'] = 'application/json'
        base.update(headers or {})
        conn.request(method, '/' + launcher.QC_STATE_NAME, body=json.dumps(body) if body is not None else None, headers={k: v for k, v in base.items() if v is not None})
        r = conn.getresponse(); data = r.read(); conn.close()
        try: data = json.loads(data)
        except ValueError: pass
        return r.status, data

    def state(self, revision, excluded=()):
        return {'schema_version': 1, 'dataset_id': 'ds', 'revision': revision, 'excluded': list(excluded), 'history': []}

    def test_review_state_is_stored_with_the_result_and_guarded(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); port = self.serve(folder)
            self.assertEqual(self.call(port, 'GET'), (200, {'state': None, 'damaged': False}))
            for headers in ({'X-LabCellpose-QC': None}, {'X-LabCellpose-QC': 'wrong'}, {'Host': 'evil.example'}, {'Origin': 'http://evil.example'}):
                self.assertEqual(self.call(port, 'POST', {'base_revision': None, 'state': self.state(1)}, headers)[0], 403)
            self.assertEqual(self.call(port, 'POST', {'base_revision': None, 'state': self.state(1)}, {'Content-Type': 'text/plain'})[0], 415)
            self.assertEqual(self.call(port, 'POST', {'base_revision': None, 'state': dict(self.state(1), dataset_id='other')})[0], 400)
            self.assertEqual(self.call(port, 'POST', {'base_revision': None, 'state': self.state(1)})[0], 200)
            self.assertEqual(json.loads((folder / launcher.QC_STATE_NAME).read_text())['revision'], 1)
            self.assertEqual(self.call(port, 'POST', {'base_revision': 1, 'state': self.state(2)})[0], 200)
            status, data = self.call(port, 'POST', {'base_revision': 1, 'state': self.state(2, ['x'])})   # stale base
            self.assertEqual(status, 409); self.assertEqual(data['state']['revision'], 2)
            self.assertEqual(self.call(port, 'POST', {'base_revision': None, 'state': self.state(0), 'replace': True})[0], 200)
            self.assertEqual(len(list(folder.glob('qc_review_state.backup-*.json'))), 1)
            (folder / launcher.QC_STATE_NAME).write_text('{damaged')
            self.assertEqual(self.call(port, 'GET')[1]['damaged'], True)
            self.assertEqual(self.call(port, 'POST', {'base_revision': None, 'state': self.state(3)})[0], 200)
            self.assertEqual(len(list(folder.glob('qc_review_state.damaged-*.json'))), 1)
            if can_symlink(folder):
                (folder / launcher.QC_STATE_NAME).unlink(); (folder / 'outside.json').write_text('KEEP')
                (folder / launcher.QC_STATE_NAME).symlink_to(folder / 'outside.json')
                self.assertEqual(self.call(port, 'POST', {'base_revision': None, 'state': self.state(4)})[0], 507)
                self.assertEqual((folder / 'outside.json').read_text(), 'KEEP')
            plain = self.serve(folder, store=False)
            self.assertEqual(self.call(plain, 'GET')[0], 404)

    def test_server_headers_idle_timeout_and_quiet_logging(self):
        self.assertEqual(launcher.ResultHandler.timeout, 30)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); (folder / 'field_summary.csv').write_text('a\n1\n'); port = self.serve(folder)
            stderr = io.StringIO(); old = sys.stderr; sys.stderr = stderr
            try:
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5); conn.request('GET', '/field_summary.csv'); r = conn.getresponse(); r.read(); conn.close()
            finally: sys.stderr = old
            self.assertEqual(r.status, 200); self.assertEqual(r.getheader('X-Frame-Options'), 'SAMEORIGIN')
            self.assertIn("frame-ancestors 'self'", r.getheader('Content-Security-Policy')); self.assertEqual(stderr.getvalue(), '')


class ViewerLifecycle(unittest.TestCase):
    def start(self, folder, parent_code=None, control=False):
        runtime_env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
        command = [sys.executable, '-I', '-B', '-X', 'utf8', '-u', str(APP / 'launcher.py'), 'view', '--run', str(folder), '--port', '0', '--no-open']
        if control:
            return subprocess.Popen(command + ['--control-stdin'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=runtime_env)
        if parent_code is None:
            return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=runtime_env)
        # -B everywhere: a test must never write bytecode into the signed application bundle.
        return subprocess.Popen([sys.executable, '-I', '-B', '-c', parent_code, json.dumps(command)], stdout=subprocess.PIPE, env=runtime_env)

    def temp_reports(self):
        root = Path(tempfile.gettempdir()); return set(root.glob('labcellpose-view-*'))

    @unittest.skipIf(os.name == 'nt', 'Windows cannot deliver SIGTERM; the app asks the viewer to stop instead')
    def test_sigterm_removes_the_temporary_report(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'run'; saved_result(folder)
            before = self.temp_reports(); viewer = self.start(folder)
            info = json.loads(viewer.stdout.readline()); self.assertIn('viewer', info)
            created = self.temp_reports() - before; self.assertEqual(len(created), 1)
            viewer.send_signal(signal.SIGTERM); viewer.wait(10); viewer.stdout.close()
            self.assertFalse(any(p.exists() for p in created))

    def test_stop_request_and_closed_input_remove_the_temporary_report(self):
        for request in (b'stop\n', None):   # the app writes 'stop', or its side of the pipe closes
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp) / 'run'; saved_result(folder)
                before = self.temp_reports(); viewer = self.start(folder, control=True)
                info = json.loads(viewer.stdout.readline()); self.assertIn('viewer', info)
                created = self.temp_reports() - before; self.assertEqual(len(created), 1)
                if request: viewer.stdin.write(request); viewer.stdin.flush()
                else: viewer.stdin.close()
                self.assertEqual(viewer.wait(10), 0); viewer.stdout.close()
                if request: viewer.stdin.close()
                self.assertFalse(any(p.exists() for p in created))

    def test_viewer_exits_when_its_parent_dies(self):
        parent = ('import json,subprocess,sys,time\n'
                  'p=subprocess.Popen(json.loads(sys.argv[1]),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)\n'
                  'print(p.pid,flush=True);print(p.stdout.readline().decode().strip(),flush=True);time.sleep(600)')
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'run'; saved_result(folder)
            holder = self.start(folder, parent)
            child = int(holder.stdout.readline()); url = holder.stdout.readline().decode(); self.assertIn('viewer', url)
            port = int(json.loads(url)['viewer'].split(':')[2].split('/')[0])
            holder.kill(); holder.wait(5)
            deadline = time.time() + 10
            while time.time() < deadline:
                if not running(child): break
                time.sleep(0.2)
            else:
                os.kill(child, getattr(signal, 'SIGKILL', signal.SIGTERM)); self.fail('orphaned viewer kept running')
            import socket
            with socket.socket() as s: s.bind(('127.0.0.1', port))          # port released


if __name__ == '__main__': unittest.main()
