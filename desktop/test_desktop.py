import copy
import json
import contextlib
import io
import hashlib
import tempfile
import unittest
from pathlib import Path
from desktop_backend import make_config, reject_axes, snapshot, preview, inspect, display_name, friendly_error, plain


class DesktopContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)/'image.tif'
        self.source.write_bytes(b'fixture: no inference in config tests')
        self.inventory = {'records': [dict(path=str(self.source), member=None, status='inspected',
            shape=[4, 40, 60], dtype='uint16', tiff_axes='QYX', source_snapshot=snapshot(self.source),
            input_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(), metadata_sha256=None)]}
        self.request = dict(confirmed=True, selected=[0], segmentation='C4', foreground='C2',
            channels=[dict(label='First', kind='fluorescence', measure=True),
                      dict(label='Second', kind='fluorescence', measure=True),
                      dict(label='Ignored', kind='other', measure=False),
                      dict(label='Phase', kind='phase', measure=False)])

    def test_different_channel_counts_and_explicit_measurement_roles(self):
        config = make_config(self.request, self.inventory)
        self.assertEqual(config['segmentation_channels'], ['C4'])
        self.assertEqual(config['background']['foreground_channel'], 'C2')
        self.assertEqual([c['id'] for c in config['channels'] if c['measure']], ['C1', 'C2'])
        self.assertNotIn('saturation_value', config['channels'][0])
        self.assertNotIn('fields', self.request)
        self.assertEqual(config['input_confirmation'], 'sha256-v1')
        self.assertEqual(config['fields'][0]['input_sha256'], self.inventory['records'][0]['input_sha256'])
        for count in (1, 2, 5, 6):
            request = dict(self.request, channels=[dict(label=f'Ch{x}', kind='fluorescence', measure=True)
                for x in range(count)], segmentation='C1', foreground='C1')
            inventory = copy.deepcopy(self.inventory); inventory['records'][0]['shape'][0] = count
            self.assertEqual(len(make_config(request, inventory)['channels']), count)

    def test_phase_measurement_and_unmeasured_background_are_rejected(self):
        for change in ('phase', 'foreground'):
            request = copy.deepcopy(self.request)
            if change == 'phase': request['channels'][3]['measure'] = True
            else: request['foreground'] = 'C3'
            with self.assertRaises(ValueError): make_config(request, self.inventory)

    def test_background_estimator_default_and_explicit_choice(self):
        self.assertEqual(make_config(self.request,self.inventory)['background']['estimator'],'median')
        self.assertEqual(make_config(dict(self.request,background_estimator='mean'),self.inventory)['background']['estimator'],'mean')
        for value in ('auto',None,False):
            with self.assertRaisesRegex(ValueError,'Median or Mean'):
                make_config(dict(self.request,background_estimator=value),self.inventory)

    def test_changed_source_and_missing_confirmation(self):
        with self.assertRaisesRegex(ValueError, 'Confirm'):
            make_config(dict(self.request, confirmed=False), self.inventory)
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            make_config(self.request, self.inventory)

    def test_selection_and_mixed_channel_counts(self):
        for selected in ([], [0, 0], [8], [True]):
            with self.assertRaises(ValueError): make_config(dict(self.request, selected=selected), self.inventory)
        self.inventory['records'][0]['shape'][0] = 5
        with self.assertRaisesRegex(ValueError, 'channel count'):
            make_config(self.request, self.inventory)

    def test_known_z_time_axes_and_invalid_settings(self):
        for axis in ('ZYX', 'TYX', 'TCYX'):
            with self.assertRaisesRegex(ValueError, 'Z/time'): reject_axes(dict(shape=[4, 40, 60], tiff_axes=axis))
        for values in ({'diameter': float('nan')}, {'min_size': 1.5}, {'flow_threshold': -1}, {'edge_width_px': 0}):
            with self.assertRaises(ValueError): make_config(dict(self.request, settings=values), self.inventory)

    def test_independent_segmentation_inputs_and_shared_background(self):
        request = dict(self.request, segmentation_channels=['C4','C2'], background_mask='C4')
        config = make_config(request, self.inventory)
        self.assertEqual(config['segmentation_channels'], ['C2','C4'])
        self.assertEqual(config['background']['mask_channel'], 'C4')
        self.assertEqual(config['fields'][0]['label'], 'image.tif')
        for inputs in ([], ['C2','C2'], ['C9'], 'C2', [True]):
            with self.assertRaises(ValueError):
                make_config(dict(request, segmentation_channels=inputs), self.inventory)
        with self.assertRaises(ValueError):
            make_config(dict(request, background_mask='C1'), self.inventory)

    def test_preview_uses_requested_field_and_rejects_changed_input(self):
        import numpy as np
        import tifffile
        import analyze
        first=Path(self.temp.name)/'first.tif'; second=Path(self.temp.name)/'second.tif'
        tifffile.imwrite(first,np.zeros((2,30,40),dtype='uint16'),photometric='minisblack')
        data=np.zeros((2,30,40),dtype='uint16');data[:,5:15,10:20]=1000
        tifffile.imwrite(second,data,photometric='minisblack')
        records=[dict(path=str(p),status='inspected',shape=[2,30,40],source_snapshot=snapshot(p),
            input_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),metadata_sha256=None) for p in (first,second)]
        inventory=Path(self.temp.name)/'inventory.json';inventory.write_text(json.dumps({'records':records}))
        results=[]
        for index in (0,1):
            capture=io.StringIO()
            with contextlib.redirect_stdout(capture): preview(analyze,dict(inventory=str(inventory),index=index))
            results.append(json.loads(capture.getvalue()))
        self.assertNotEqual(results[0]['previews'],results[1]['previews'])
        self.assertEqual(results[1]['index'],1)
        for index in (-1,2,True):
            with self.assertRaises(ValueError): preview(analyze,dict(inventory=str(inventory),index=index))
        second.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError,'changed'):
            preview(analyze,dict(inventory=str(inventory),index=1))

    def test_selected_batch_budget_and_old_inventory_require_rescan(self):
        self.inventory['records'][0]['shape']=[4,8192,8192]
        with self.assertRaisesRegex(ValueError, '256 MiB'):
            make_config(self.request,self.inventory)
        self.inventory['records'][0].pop('input_sha256')
        with self.assertRaisesRegex(ValueError, 'scan'):
            make_config(self.request,self.inventory)

    def test_small_diameter_that_would_enlarge_images_too_far_is_refused_before_running(self):
        self.inventory['records'][0]['shape']=[4,1024,1024]
        self.assertEqual(make_config(dict(self.request,settings={'diameter':4}),self.inventory)['parameters']['diameter'],4)
        with self.assertRaisesRegex(ValueError,'at least 4 px'):
            make_config(dict(self.request,settings={'diameter':3}),self.inventory)

    def test_inventory_event_carries_previews_for_the_first_group_only(self):
        import numpy as np
        import tifffile
        import analyze
        folder=Path(self.temp.name)/'mixed';folder.mkdir()
        for name,count in (('two.tif',2),('three.tif',3)):
            tifffile.imwrite(folder/name,np.full((count,24,24),100,dtype='uint16'),photometric='minisblack')
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture): inspect(analyze,str(folder),Path(self.temp.name)/'inventory.json')
        event=json.loads(capture.getvalue().strip().splitlines()[-1])
        self.assertEqual([g['count'] for g in event['groups']],[2,3])
        self.assertEqual(len(event['groups'][0]['previews']),2)
        self.assertIsNone(event['groups'][1]['previews'])

    def test_images_are_named_by_their_path_in_the_chosen_folder_and_problems_in_plain_words(self):
        import numpy as np
        import tifffile
        import analyze
        folder=Path(self.temp.name)/'experiment'
        for condition in ('CA','DN'):
            (folder/condition).mkdir(parents=True)
            tifffile.imwrite(folder/condition/'Image 1.tif',np.full((2,24,24),100,dtype='uint16'),photometric='minisblack')
        (folder/'notes.pdf').write_bytes(b'%PDF-1.7')   # other files in a folder are ignored, not reported
        capture=io.StringIO(); destination=Path(self.temp.name)/'inventory.json'
        with contextlib.redirect_stdout(capture): inspect(analyze,str(folder),destination)
        lines=capture.getvalue().strip().splitlines()
        self.assertEqual([json.loads(line)['event'] for line in lines],['inventory'])   # no raw command-line summary
        event=json.loads(lines[0])
        self.assertEqual([r['name'] for r in event['groups'][0]['records']],['CA/Image 1.tif','DN/Image 1.tif'])
        self.assertEqual(event['rejected'],[])
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture): inspect(analyze,str(folder/'notes.pdf'),Path(self.temp.name)/'pdf.json')
        self.assertEqual(json.loads(capture.getvalue())['rejected'],[dict(name='notes.pdf',error='Not a TIFF image.')])
        inventory=json.loads(destination.read_text())
        request=dict(self.request,selected=[r['index'] for r in event['groups'][0]['records']],segmentation='C1',foreground='C1',
            channels=[dict(label='A',kind='fluorescence',measure=True),dict(label='B',kind='fluorescence',measure=True)])
        self.assertEqual([f['label'] for f in make_config(request,inventory)['fields']],['CA/Image 1.tif','DN/Image 1.tif'])
        self.assertEqual(display_name(dict(path='/x/run.zip',member='Run/DN/Image 1.tif'),'/x/run.zip'),'Run/DN/Image 1.tif')
        self.assertEqual(display_name(dict(path=str(self.source)),str(self.source)),'image.tif')
        self.assertEqual(display_name(dict(path='/elsewhere/a.tif'),str(folder)),'a.tif')
        self.assertEqual(friendly_error('ValueError: Invalid or truncated TIFF'),'Invalid or truncated TIFF')
        self.assertEqual(plain(ValueError('Choose an existing output folder.')),'Choose an existing output folder.')
        self.assertEqual(plain(KeyError('C9')),"KeyError: 'C9'")


if __name__ == '__main__': unittest.main(verbosity=2)
