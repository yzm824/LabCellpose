"""Serving a different run on the same origin must not reuse the earlier report."""
import functools
import http.client
import http.server
import os
import json
from pathlib import Path
import tempfile
import threading
import unittest

from launcher import ResultHandler, prepare_viewer, LEGACY_NOTICE
from render_review import make_bundle


def can_symlink(folder):
    """Windows lets only some accounts create symbolic links; the link checks are skipped where it does not."""
    probe = Path(folder) / 'link-probe'
    try: probe.symlink_to(Path(folder) / 'link-target')
    except (OSError, NotImplementedError): return False
    probe.unlink(); return True


class ViewerServerTests(unittest.TestCase):
    def test_refresh_preserves_source_files_and_qc_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'run';source.mkdir()
            config={'channels':[{'id':'C1','label':'Test'}],'segmentation_channels':['C1']}
            fields={'field1':{'objects':{'C1':[{'id':1}]}}}
            csv='field,segmentation_channel,object_id,region,measurement_channel\r\nfield1,C1,1,whole,C1\r\n'
            (source/'viewer_data.json').write_text(json.dumps({'config':config,'fields':fields}))
            (source/'measurements.csv').write_bytes(csv.encode('utf-8'))
            (source/'run_manifest.json').write_text('{"version":"1.2.1","status":"complete"}')
            (source/'index.html').write_text('original saved report')
            before={p.name:p.read_bytes() for p in source.iterdir()}
            output=prepare_viewer(source,root/'refreshed.html')
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})
            self.assertIn(make_bundle(config,fields,csv)['dataset_id'], output.read_text())
            self.assertIn('labNativeMagnify',output.read_text())
            self.assertIn('sandbox="allow-scripts"',output.read_text())
            self.assertIn('Content-Security-Policy',output.read_text())
            empty=root/'legacy';empty.mkdir();self.assertEqual(prepare_viewer(empty,root/'unused').read_bytes(),LEGACY_NOTICE)
            for name in ('viewer_data.json','run_manifest.json','measurements.csv') if can_symlink(root) else ():
                original=source/name;original.unlink();original.symlink_to(root/'outside')
                (root/'outside').write_bytes(before[name])
                with self.assertRaises((ValueError,OSError)):prepare_viewer(source,root/'rejected.html')
                original.unlink();original.write_bytes(before[name])

    def test_older_result_and_csv_ignore_conditional_cache_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            html = root/'index.html'; html.write_text('NEWER REPORT')
            csv = root/'measurements.csv'; csv.write_text('NEWER CSV')
            handler = functools.partial(ResultHandler, directory=str(root),report_index=html)
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                conn = http.client.HTTPConnection(*server.server_address, timeout=5)
                try:
                    conn.request('GET', '/?view=first')
                    response = conn.getresponse(); last_modified = 'Wed, 30 Sep 2026 08:00:00 GMT'
                    self.assertEqual(response.read(), b'NEWER REPORT')
                    self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                    html.write_text('OLDER REPORT'); csv.write_text('OLDER CSV')
                    for path in (html, csv): os.utime(path, (1000000000,1000000000))
                    for url, body in [('/?view=second',b'OLDER REPORT'), ('/measurements.csv',b'OLDER CSV')]:
                        conn.request('GET', url, headers={'If-Modified-Since':last_modified, 'If-None-Match':'old'})
                        response = conn.getresponse()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), body)
                        self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                finally: conn.close()
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_legacy_code_symlinks_and_other_paths_are_not_served(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'run';source.mkdir()
            if not can_symlink(root): self.skipTest('symbolic links cannot be created here')
            (source/'index.html').write_text('<script>parent.CANARY=1;fetch("/secret")</script>')
            (root/'canary').write_text('PRIVATE CANARY')
            (source/'measurements.csv').symlink_to(root/'canary')
            (source/'secret').symlink_to(root/'canary')
            (source/'field_summary.csv').write_bytes(b'legitimate,summary\n1,2\n')
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(ResultHandler,directory=str(source)))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                conn=http.client.HTTPConnection(*server.server_address,timeout=5)
                for url in ('/','/index.html'):
                    conn.request('GET',url);r=conn.getresponse();body=r.read()
                    self.assertEqual(body,LEGACY_NOTICE);self.assertNotIn(b'CANARY',body)
                    # v1.4: same-origin requests only (review-state store); no third-party connections or framing.
                    self.assertIn("connect-src 'self'",r.getheader('Content-Security-Policy'))
                    self.assertIn("frame-ancestors 'self'",r.getheader('Content-Security-Policy'))
                    self.assertEqual(r.getheader('X-Frame-Options'),'SAMEORIGIN')
                for url in ('/measurements.csv','/secret','/%73ecret','/../canary','/%2e%2e/canary','/run_manifest.json'):
                    conn.request('GET',url);r=conn.getresponse();self.assertEqual(r.status,404);self.assertNotIn(b'PRIVATE CANARY',r.read())
                conn.request('GET','/field_summary.csv');r=conn.getresponse()
                self.assertEqual(r.status,200);self.assertEqual(r.read(),b'legitimate,summary\n1,2\n');self.assertIn('attachment',r.getheader('Content-Disposition'))
                conn.request('GET','/',headers={'Host':'foreign.example'});r=conn.getresponse();self.assertEqual(r.status,403);r.read();conn.close()
            finally:server.shutdown();server.server_close();thread.join(5)


if __name__ == '__main__': unittest.main()
