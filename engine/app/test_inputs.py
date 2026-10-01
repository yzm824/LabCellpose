"""Input regressions shared by the app, inspection CLI, and analysis CLI."""
import io
import json
import os
import struct
import zipfile
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

import numpy as np
import tifffile

from analyze import inspect_input, leica_metadata, load_fields, read_stack
import analyze
from test_contract import config


def xml(camera='', channel='', dimension=''):
    return (f'<Root><ChannelDescription LUTName="Gray" {channel}/>'
            f'<WideFieldChannelInfo><IndividualCameraInfo LUT="Gray" {camera}/>'
            f'</WideFieldChannelInfo>{dimension}</Root>')


class InputTests(unittest.TestCase):
    def test_bad_zip_member_decode_is_isolated_from_good_fields(self):
        raw=io.BytesIO();tifffile.imwrite(raw,np.zeros((8,9),dtype='uint16'))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for kind in ('deflate','encrypted','unsupported'):
                z=root/(kind+'.zip')
                with zipfile.ZipFile(z,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('good.tif',raw.getvalue());archive.writestr('bad.tif',raw.getvalue())
                with zipfile.ZipFile(z) as archive:info=archive.getinfo('bad.tif')
                data=bytearray(z.read_bytes());local=info.header_offset
                central=data.index(b'PK\x01\x02',data.index(b'PK\x01\x02')+4)
                if kind=='deflate':
                    start=local+30+len(info.filename);data[start:start+4]=b'\xff'*4
                elif kind=='encrypted':
                    struct.pack_into('<H',data,local+6,1);struct.pack_into('<H',data,central+8,1)
                else:
                    struct.pack_into('<H',data,local+8,99);struct.pack_into('<H',data,central+10,99)
                z.write_bytes(data);out=root/(kind+'.json');inspect_input(z,out)
                self.assertEqual(json.loads(out.read_text())['counts'],{'inspected':1,'unsupported':1})

    def test_corrupt_tiffs_do_not_abort_mixed_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,raw in [('empty',b'II*\x00\x00\x00\x00\x00'),('truncated',b'II*\x00\x08\x00\x00\x00\x01')]:
                (root/(name+'.tif')).write_bytes(raw)
            tifffile.imwrite(root/'good.tif',np.zeros((8,9),dtype='uint16'))
            inspect_input(root,root/'inventory.json')
            result=json.loads((root/'inventory.json').read_text())
            self.assertEqual(result['counts'],{'inspected':1,'unsupported':2})

    def test_decode_limits_are_checked_before_pixel_allocation(self):
        raw=io.BytesIO();tifffile.imwrite(raw,np.zeros((2,32,32),dtype='uint16'),photometric='minisblack')
        for limits in ({'MAX_STACK_BYTES':4095},{'MAX_PLANE_PIXELS':1023},{'MAX_CHANNELS':1}):
            with patch.multiple(analyze,**limits),patch.object(tifffile.TiffPage,'asarray',side_effect=AssertionError('decoded')):
                with self.assertRaises(analyze.ResourceLimitError):read_stack(raw.getvalue())
        with patch.object(tifffile.TiffPage,'asarray',side_effect=AssertionError('decoded')):
            with self.assertRaisesRegex(ValueError,'Batch exceeds'):read_stack(raw.getvalue(),4095)
        data,_=read_stack(raw.getvalue(),4096);self.assertEqual(data.nbytes,4096)
        # A tiny container claiming 160 MiB must fail at the real (unmocked)
        # threshold, before any attempt to decode its inconsistent pixel blocks.
        huge=io.BytesIO();tifffile.imwrite(huge,np.zeros((5,8,8),dtype='uint16'),photometric='minisblack')
        encoded=bytearray(huge.getvalue())
        with tifffile.TiffFile(io.BytesIO(encoded)) as tf:
            for page in tf.pages:
                for name in ('ImageWidth','ImageLength'):
                    tag=page.tags[name];struct.pack_into('<H' if tag.dtype==3 else '<I',encoded,tag.valueoffset,4096)
        with patch.object(tifffile.TiffPage,'asarray',side_effect=AssertionError('decoded')):
            with self.assertRaisesRegex(ValueError,'128 MiB'):read_stack(bytes(encoded))

    def test_file_archive_metadata_and_entry_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'raw';p.write_bytes(b'x'*101)
            with self.assertRaises(analyze.ResourceLimitError):analyze.read_source(p,limit=100)
            z=root/'images.zip'
            with zipfile.ZipFile(z,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('image.tif',b'0'*101);archive.writestr('second.tif',b'0')
            self.assertEqual(analyze.read_source(z,'second.tif',100),b'0')
            with self.assertRaises(analyze.ResourceLimitError):analyze.read_source(z,'image.tif',100)
            with patch.object(analyze,'MAX_ZIP_ENTRIES',1),patch.object(zipfile,'ZipFile',side_effect=AssertionError('opened')):
                with self.assertRaises(analyze.ResourceLimitError):
                    with analyze.open_archive(z):pass
            with patch.object(analyze,'MAX_METADATA_BYTES',4):
                with self.assertRaises(analyze.ResourceLimitError):leica_metadata(b'<Root/>')
            raw=bytearray(z.read_bytes());at=raw.rfind(b'PK\x05\x06');struct.pack_into('<HH',raw,at+8,65535,65535);z.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'ZIP64'):
                with analyze.open_archive(z):pass

    def test_content_confirmation_covers_same_stat_replacement_and_sidecars(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'image.tif';(root/'MetaData').mkdir();side=root/'MetaData/image.xml'
            def image(value):
                tifffile.imwrite(p,np.full((8,9),value,dtype='uint16'))
            image(100);inspect_input(root,root/'inventory.json')
            field=json.loads((root/'inventory.json').read_text())['records'][0]
            analyze.read_field_sources(field,root)
            st=p.stat();image(900);os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
            self.assertEqual(p.stat().st_size,st.st_size)
            with self.assertRaisesRegex(ValueError,'changed'):analyze.read_field_sources(field,root)
            image(100);side.write_text(xml('ExposureTime="1.0"'))
            with self.assertRaisesRegex(ValueError,'changed'):analyze.read_field_sources(field,root)
            field['metadata_sha256']=analyze.digest(side.read_bytes());analyze.read_field_sources(field,root)
            st=side.stat();side.write_text(xml('ExposureTime="9.0"'));os.utime(side,ns=(st.st_atime_ns,st.st_mtime_ns))
            with self.assertRaisesRegex(ValueError,'changed'):analyze.read_field_sources(field,root)
            z=root/'images.zip'
            with zipfile.ZipFile(z,'w') as archive:archive.write(p,'image.tif');archive.write(side,'MetaData/image.xml')
            zipped=dict(field,path=str(z),member='image.tif',metadata_sha256=analyze.digest(side.read_bytes()))
            analyze.read_field_sources(zipped,root)
            with zipfile.ZipFile(z,'w') as archive:archive.write(p,'image.tif');archive.writestr('MetaData/image.xml',xml('ExposureTime="2.0"'))
            with self.assertRaisesRegex(ValueError,'changed'):analyze.read_field_sources(zipped,root)

    def test_aggregate_limits_and_new_config_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('a','b'):tifffile.imwrite(root/(name+'.tif'),np.zeros((2,8,9),dtype='uint16'),photometric='minisblack')
            c=config();c['fields']=[dict(id=n,path=n+'.tif') for n in ('a','b')]
            with patch.object(analyze,'MAX_BATCH_BYTES',400):
                with self.assertRaisesRegex(ValueError,'Batch exceeds'):load_fields(c,root)
            with patch.object(analyze,'MAX_INSPECT_BYTES',400):
                with self.assertRaisesRegex(ValueError,'Batch exceeds'):inspect_input(root,root/'inventory.json')
            self.assertFalse((root/'inventory.json').exists())
            c['input_confirmation']='sha256-v1'
            with self.assertRaisesRegex(ValueError,'digest|SHA|scan'):analyze.validate_config(c)
    def test_missing_optional_metadata_is_unknown(self):
        metadata = leica_metadata(xml())
        channel = metadata['channels'][0]
        for key in ('exposure_seconds', 'recorded_max', 'excitation_nm', 'emission_nm'):
            self.assertIsNone(channel[key])
        self.assertIsNone(metadata['pixel_size_um'])

    def test_metadata_values_and_pixel_spacing(self):
        result = leica_metadata(xml('ExposureTime="0.1" ExcitationWavelength="488"', 'Max="4095"',
            '<DimensionDescription DimID="1" NumberOfElements="10" Length="0.00002" Unit="m"/>'
            '<DimensionDescription DimID="2" NumberOfElements="20" Length="0.00006" Unit="m"/>'))
        self.assertEqual(result['channels'][0]['exposure_seconds'], 0.1)
        self.assertEqual(result['channels'][0]['recorded_max'], 4095)
        np.testing.assert_allclose(result['pixel_size_um'], [2, 3])

    def test_invalid_metadata_has_actionable_value_errors(self):
        for value in ('invalid', 'nan', 'inf', '-1', '0'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'XML.*ExposureTime'):
                leica_metadata(xml(f'ExposureTime="{value}"'))
        with self.assertRaisesRegex(ValueError, 'XML.*Max'):
            leica_metadata(xml(channel='Max="nan"'))
        with self.assertRaisesRegex(ValueError, 'XML.*NumberOfElements'):
            leica_metadata(xml(dimension='<DimensionDescription DimID="1" NumberOfElements="0" Length="1" Unit="m"/>'))

    def test_inventory_isolates_malformed_files_and_accepts_missing_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'MetaData').mkdir()
            for name, metadata in [('missing', xml()), ('malformed', xml('ExposureTime="oops"')), ('valid', None)]:
                tifffile.imwrite(root/(name+'.tif'), np.zeros((8, 9), dtype='uint16'), photometric='minisblack')
                if metadata: (root/'MetaData'/(name+'.xml')).write_text(metadata)
            inspect_input(root, root/'inventory.json')
            result = json.loads((root/'inventory.json').read_text())
            self.assertEqual(result['counts'], {'inspected': 2, 'unsupported': 1})
            bad = next(r for r in result['records'] if r['status']=='unsupported')
            self.assertIn('ExposureTime', bad['error'])
            c = config(); c['channels'] = c['channels'][:1]
            c['fields'] = [dict(id='missing', path='missing.tif')]
            fields, _ = load_fields(c, root)
            self.assertIsNone(fields['missing']['exposures']['A'])
            self.assertIsNone(fields['missing']['limits']['A'])

    def test_known_z_time_axes_rejected_by_reader_inventory_and_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for axes, shape in [('TYX',(2,8,9)), ('ZYX',(2,8,9)), ('TCYX',(2,2,8,9))]:
                with self.subTest(axes=axes):
                    path = root/(axes+'.tif')
                    tifffile.imwrite(path, np.zeros(shape, dtype='uint16'), photometric='minisblack', metadata={'axes':axes})
                    with self.assertRaisesRegex(ValueError, 'Z/time'): read_stack(path.read_bytes())
                    c = config(); c['fields'] = [dict(id='bad', path=path.name)]
                    with self.assertRaisesRegex(ValueError, 'Z/time'): load_fields(c, root)
            inspect_input(root, root/'inventory.json')
            self.assertEqual(json.loads((root/'inventory.json').read_text())['counts'], {'inspected':0,'unsupported':3})

    def test_2d_channels_and_ambiguous_pages_remain_supported(self):
        for axes, shape in [('YX',(8,9)), ('CYX',(2,8,9)), ('QYX',(2,8,9)), ('IYX',(2,8,9))]:
            with self.subTest(axes=axes):
                data = np.arange(np.prod(shape), dtype='uint16').reshape(shape)
                buffer = io.BytesIO()
                tifffile.imwrite(buffer, data, photometric='minisblack', metadata={'axes':axes})
                actual, _ = read_stack(buffer.getvalue())
                np.testing.assert_array_equal(actual, data.reshape((-1,8,9)))


if __name__ == '__main__': unittest.main()
