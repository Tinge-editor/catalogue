import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
import struct

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build import build

VALIDATOR = Path(os.environ['TINGE_VALIDATOR']).resolve()
FIXTURE = Path(__file__).parent / 'fixtures' / 'preset.json'


class CatalogueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / 'look.json'
        self.package.write_bytes(FIXTURE.read_bytes())
        self.row = {'id': 'look', 'version': '1', 'name': 'Look', 'description': 'A look', 'author': 'Tinge', 'license': 'Test permission', 'categories': ['Natural'], 'packagePath': 'look.json', 'sha256': hashlib.sha256(self.package.read_bytes()).hexdigest(), 'status': 'approved', 'price': 'free', 'redistributionApproved': True, 'rightsEvidence': 'Synthetic test asset', 'listed': True}
        self.value = {'catalogID': 'tinge', 'title': 'Tinge catalogue', 'versions': [self.row]}
        self.source = self.root / 'source.json'
        self.counter = 0

    def write(self):
        self.source.write_text(json.dumps(self.value), encoding='utf-8')

    def build(self, previous=None):
        self.counter += 1
        self.write()
        output = self.root / f'output-{self.counter}'
        build(self.source, output, VALIDATOR, previous)
        return output

    def previous(self):
        self.write()
        p = self.root / 'previous.json'
        p.write_bytes(self.source.read_bytes())
        return p

    def test_valid_deterministic_and_stable_asset(self):
        a, b = self.build(), self.build()
        self.assertEqual((a / 'catalogue.json').read_bytes(), (b / 'catalogue.json').read_bytes())
        row = json.loads((a / 'catalogue.json').read_bytes())['looks'][0]
        self.assertEqual(base64.b64decode(row['package']), self.package.read_bytes())
        self.assertEqual(row['sha256'], self.row['sha256'])
        asset = f'assets/look/1/{self.row["sha256"]}.json'
        self.assertEqual((a / asset).read_bytes(), (b / asset).read_bytes())
        self.assertNotIn('rightsEvidence', row)

    def test_missing_metadata_duplicate_and_missing_file(self):
        del self.row['author']
        with self.assertRaises(ValueError): self.build()
        self.row['author'] = 'Tinge'
        self.value['versions'].append(dict(self.row))
        with self.assertRaisesRegex(ValueError, 'duplicate'): self.build()
        self.value['versions'].pop()
        self.package.unlink()
        with self.assertRaisesRegex(ValueError, 'missing'): self.build()

    def test_invalid_checksum_and_permission(self):
        self.row['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'checksum'): self.build()
        self.row['sha256'] = hashlib.sha256(self.package.read_bytes()).hexdigest()
        self.row['redistributionApproved'] = False
        with self.assertRaisesRegex(ValueError, 'redistribution'): self.build()

    def test_unsupported_and_invalid_lut_rejected(self):
        for modify in ('schema', 'lut'):
            p = json.loads(FIXTURE.read_text())
            if modify == 'schema': p[0]['schemaVersion'] = p[0]['engineVersion'] = 999
            else:
                p[0]['schemaVersion'] = p[0]['engineVersion'] = 5
                p[0]['baseStrength'] = 1
                p[0]['lut'] = {'dimension': 1, 'rgba': ''}
                self.row['lutEncoding'] = {'input': 'sRGB', 'output': 'sRGB'}
            self.package.write_text(json.dumps(p))
            self.row['sha256'] = hashlib.sha256(self.package.read_bytes()).hexdigest()
            with self.assertRaises(Exception): self.build()
            self.assertFalse((self.root / f'output-{self.counter}').exists())

    def test_valid_native_lut_package(self):
        p = json.loads(FIXTURE.read_text())
        p[0]['schemaVersion'] = p[0]['engineVersion'] = 5
        p[0]['baseStrength'] = 1
        rgba = b''.join(struct.pack('<4f', float(r), float(g), float(b), 1.0)
                        for b in range(2) for g in range(2) for r in range(2))
        p[0]['lut'] = {'dimension': 2, 'rgba': base64.b64encode(rgba).decode('ascii')}
        self.package.write_text(json.dumps(p))
        self.row['sha256'] = hashlib.sha256(self.package.read_bytes()).hexdigest()
        self.row['lutEncoding'] = {'input': 'sRGB', 'output': 'sRGB'}
        out = self.build()
        self.assertEqual(len(json.loads((out / 'catalogue.json').read_bytes())['looks']), 1)

    def test_lut_requires_explicit_input_and_output_encoding(self):
        p = json.loads(FIXTURE.read_text())
        p[0]['schemaVersion'] = p[0]['engineVersion'] = 5
        p[0]['baseStrength'] = 1
        p[0]['lut'] = {'dimension': 2, 'rgba': ''}
        self.package.write_text(json.dumps(p))
        self.row['sha256'] = hashlib.sha256(self.package.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'input and output'): self.build()
        self.row['lutEncoding'] = {'input': 'Rec.709', 'output': 'sRGB'}
        with self.assertRaisesRegex(ValueError, 'input and output'): self.build()

    def test_rejects_mismatched_embedded_lut_encoding(self):
        p = json.loads(FIXTURE.read_text())
        p[0]['schemaVersion'] = p[0]['engineVersion'] = 10
        p[0]['baseStrength'] = 1
        p[0]['lut'] = {'dimension': 2, 'rgba': '', 'interpretation': {'input': 'rec709', 'output': 'sRGB'}}
        self.package.write_text(json.dumps(p))
        self.row['sha256'] = hashlib.sha256(self.package.read_bytes()).hexdigest()
        self.row['lutEncoding'] = {'input': 'sRGB', 'output': 'sRGB'}
        with self.assertRaisesRegex(ValueError, 'conflicts'): self.build()

    def test_unapproved_and_paid_records_are_rejected(self):
        for status, price in [('draft', 'free'), ('approved', 'paid')]:
            row = {'id': 'not-public', 'version': '1', 'status': status, 'price': price}
            self.value['versions'].append(row)
            with self.assertRaisesRegex(ValueError, 'only approved free'): self.build()
            self.value['versions'].pop()

    def test_update_remove_and_rollback_preserve_assets(self):
        old = self.previous()
        self.row['listed'] = False
        newer = dict(self.row, version='2', listed=True)
        self.value['versions'].append(newer)
        out = self.build(old)
        self.assertEqual(json.loads((out / 'catalogue.json').read_bytes())['looks'][0]['version'], '2')
        self.assertEqual(len(list((out / 'assets').rglob('*.json'))), 2)
        prev2 = self.previous()
        self.row['listed'], newer['listed'] = True, False
        rolled = self.build(prev2)
        self.assertEqual(json.loads((rolled / 'catalogue.json').read_bytes())['looks'][0]['version'], '1')
        self.assertEqual(len(list((rolled / 'assets').rglob('*.json'))), 2)
        newer['listed'] = False
        self.row['listed'] = False
        removed = self.build(prev2)
        self.assertEqual(json.loads((removed / 'catalogue.json').read_bytes())['looks'], [])
        self.assertEqual(len(list((removed / 'assets').rglob('*.json'))), 2)
        self.value['versions'].pop()
        with self.assertRaisesRegex(ValueError, 'changed or removed'): self.build(prev2)

    def test_mutating_old_version_and_path_escape_are_rejected(self):
        old = self.previous()
        self.row['name'] = 'Changed'
        with self.assertRaisesRegex(ValueError, 'changed or removed'): self.build(old)
        self.row['name'] = 'Look'
        self.row['packagePath'] = '../other.json'
        with self.assertRaisesRegex(ValueError, 'outside'): self.build()


if __name__ == '__main__':
    unittest.main()
