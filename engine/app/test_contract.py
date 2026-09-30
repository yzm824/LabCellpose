"""Small analytic fixtures: original-pixel math, empty regions and input rejection."""
import argparse, io, json, tempfile, unittest
from pathlib import Path
import numpy as np
import tifffile
from analyze import measure_field, make_background, read_stack, validate_config, inspect_input, load_fields, run

def config():
    return dict(schema_version=1,plane_axis='channel',axis_evidence='synthetic fixture',
        channels=[dict(id='A',page=0,kind='fluorescence',measure=True),dict(id='B',page=1,kind='fluorescence',measure=True)],
        fields=[dict(id='sample',path='unused')],segmentation_channels=['A'],edge_width_px=1,
        background=dict(mask_channel='A',foreground_channel='A',mad_multiplier=5,dilation_iterations=0,min_pixels=10,min_fraction=.01),
        parameters={'do_3D':False},ratios=[])

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.c=config();self.labels=np.zeros((20,30),dtype='uint32');self.labels[5:8,8:12]=1;self.labels[12,15]=2
        self.a=np.full((20,30),10,dtype='uint16');self.a[self.labels>0]=110
        self.b=np.full((20,30),20,dtype='uint16');self.b[self.labels>0]=220
        self.planes={'A':self.a,'B':self.b}
    def test_known_arithmetic_and_empty_interior(self):
        obs,rows=measure_field('sample',self.planes,self.labels,'A',{'A':10,'B':20},True,self.c,{'A':65535,'B':220})
        self.assertEqual(len(rows),12)
        one=obs[0]['regions'];self.assertEqual(one['whole']['area'],12)
        self.assertEqual(one['whole']['channels']['A']['mean'],110)
        self.assertEqual(one['whole']['channels']['A']['corrected'],100)
        self.assertEqual(one['whole']['channels']['A']['correctedSum'],1200)
        self.assertEqual(one['whole']['channels']['B']['saturated'],12)
        self.assertEqual(one['interior']['area'],2)
        self.assertIsNone(obs[1]['regions']['interior'])
        self.assertTrue(all(r['raw_mean'] is None for r in rows if r['object_id']==2 and r['region']=='interior'))
    def test_invalid_background_and_negative_values(self):
        obs,_=measure_field('s',self.planes,self.labels,'A',{'A':200,'B':300},True,self.c,{'A':None,'B':None})
        self.assertEqual(obs[0]['regions']['whole']['channels']['A']['corrected'],-90)
        self.assertIsNone(obs[0]['regions']['whole']['channels']['A']['saturated'])
        obs,_=measure_field('s',self.planes,self.labels,'A',{'A':10,'B':20},False,self.c,{'A':None,'B':None})
        self.assertEqual(obs[0]['regions']['whole']['channels']['A']['mean'],110)
        self.assertIsNone(obs[0]['regions']['whole']['channels']['A']['corrected'])
    def test_background_uses_raw_field(self):
        bg,values,info=make_background(self.planes,{'A':self.labels},self.c)
        self.assertEqual(values,{'A':10,'B':20});self.assertTrue(info['valid']);self.assertFalse(np.any(bg[self.labels>0]))
        self.c['background']['min_pixels']=1000
        self.assertFalse(make_background(self.planes,{'A':self.labels},self.c)[2]['valid'])
    def test_non_square_variable_channel_count_and_rgb_rejection(self):
        stream=io.BytesIO();tifffile.imwrite(stream,np.stack([self.a,self.b]),photometric='minisblack')
        loaded,_=read_stack(stream.getvalue());self.assertEqual(loaded.shape,(2,20,30));self.assertTrue(np.array_equal(loaded[1],self.b))
        stream=io.BytesIO();tifffile.imwrite(stream,np.zeros((20,30,3),dtype='uint8'),photometric='rgb')
        with self.assertRaises(ValueError): read_stack(stream.getvalue())
    def test_channel_roles_and_axis_require_evidence(self):
        validate_config(self.c)
        self.c['plane_axis']='unknown'
        with self.assertRaises(ValueError): validate_config(self.c)

    def test_inventory_reports_unsupported_preview_without_weakening_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'MetaData').mkdir()
            for name in ['field','Preview']:
                tifffile.imwrite(d/(name+'.tif'),np.stack([self.a,self.b]),photometric='minisblack')
            (d/'MetaData/Preview.xml').write_text('<Root><ChannelDescription/><DimensionDescription DimID="3" NumberOfElements="2"/></Root>')
            inspect_input(d,d/'inventory.json')
            info=json.loads((d/'inventory.json').read_text())
            self.assertEqual(info['counts'],{'inspected':1,'unsupported':1})
            self.c['fields']=[dict(id='bad',path='Preview.tif')]
            with self.assertRaisesRegex(ValueError,'nontrivial Z/T'):
                load_fields(self.c,d)

    def test_wrong_checkpoint_is_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'config.json').write_text(json.dumps(self.c))
            args=argparse.Namespace(config=str(d/'config.json'),out=str(d/'new_run'),weights=str(d/'unused'),weights_sha256='0'*64,device='cpu')
            with self.assertRaisesRegex(ValueError,'pinned to cpsam_v2'): run(args)
            self.assertFalse((d/'new_run').exists())
        self.c=config();self.c['channels'][0]['kind']='phase'
        with self.assertRaises(ValueError): validate_config(self.c)

if __name__=='__main__':unittest.main()
