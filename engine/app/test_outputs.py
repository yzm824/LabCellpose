"""2.0 result-folder readability: image names for field IDs and fields.csv. No inference."""
import csv, tempfile, unittest
from pathlib import Path
import analyze


class FieldIndex(unittest.TestCase):
    def test_image_names_follow_the_export_rule(self):
        cases = [(dict(id='f0', path='/data/run.zip', member='Exp/CA/Image 1.tif'), ('Image 1.tif', 'CA')),
                 (dict(id='f1', path='/data/run.zip', member='Image 2.tif'), ('Image 2.tif', 'run.zip')),
                 (dict(id='f2', path='/data/DN/Image 3.tif', label='DN/Image 3.tif'), ('Image 3.tif', 'DN')),
                 (dict(id='f3', label='legacy'), ('legacy', '')), (dict(id='f4'), ('f4', '')),
                 # A path written by Windows is split at backslashes on every system; a ZIP member never is.
                 (dict(id='f5', path=r'C:\Users\lab\Exp\CA\Image 1.tif'), ('Image 1.tif', 'CA')),
                 (dict(id='f6', path=r'\\server\share\DN\Image 2.tif'), ('Image 2.tif', 'DN')),
                 (dict(id='f7', path=r'D:\data\run.zip', member='Image 3.tif'), ('Image 3.tif', 'run.zip')),
                 (dict(id='f8', path=r'D:\data\run.zip', member=r'Exp/CA\x/Image 4.tif'), ('Image 4.tif', r'CA\x')),
                 (dict(id='f9', path=r'/data/odd\name/Image 5.tif'), ('Image 5.tif', r'odd\name'))]
        for field, expected in cases:
            self.assertEqual(analyze.image_names(field), expected, field)

    def test_fields_csv_maps_ids_to_images_and_masks_with_inert_text(self):
        config = dict(segmentation_channels=['C1', 'C4'], fields=[
            dict(id='field_a', path='/data/run.zip', member='Exp/CA/Image 1.tif', input_sha256='a'*64),
            dict(id='field_b', path='/data/=HYPERLINK(1)/-80C.tif', input_sha256='b'*64)])
        with tempfile.TemporaryDirectory() as temp:
            analyze.write_field_index(Path(temp), config)
            rows = list(csv.DictReader(open(Path(temp)/'fields.csv', encoding='utf-8')))
        self.assertEqual([r['field'] for r in rows], ['field_a', 'field_b'])
        self.assertEqual((rows[0]['image_name'], rows[0]['image_folder'], rows[0]['archive_member']), ('Image 1.tif', 'CA', 'Exp/CA/Image 1.tif'))
        self.assertEqual(rows[0]['masks'], 'masks/field_a_C1.tif; masks/field_a_C4.tif')
        self.assertEqual(rows[0]['background_mask'], 'background_masks/field_a.tif')
        self.assertEqual((rows[1]['image_name'], rows[1]['image_folder']), ("'-80C.tif", "'=HYPERLINK(1)"))
        self.assertEqual(rows[1]['source_path'], '/data/=HYPERLINK(1)/-80C.tif')


if __name__ == '__main__':
    unittest.main(verbosity=2)
