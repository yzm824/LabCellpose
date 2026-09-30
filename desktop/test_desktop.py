import copy
import tempfile
import unittest
from pathlib import Path
from desktop_backend import make_config, reject_axes, snapshot


class DesktopContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)/'image.tif'
        self.source.write_bytes(b'fixture: no inference in config tests')
        self.inventory = {'records': [dict(path=str(self.source), member=None, status='inspected',
            shape=[4, 40, 60], tiff_axes='QYX', source_snapshot=snapshot(self.source))]}
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


if __name__ == '__main__': unittest.main(verbosity=2)
