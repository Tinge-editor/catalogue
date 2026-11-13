import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
import struct
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build import RESEARCH_OUTPUT, RESEARCH_SOURCE, build, source_digest
from verify_manifest import main as verify_manifest

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
        self.assertEqual((a / 'privacy.html').read_bytes(), (Path(__file__).resolve().parents[1] / 'public' / 'privacy.html').read_bytes())
        self.assertEqual((a / 'privacy.html').read_bytes(), (b / 'privacy.html').read_bytes())
        self.assertEqual((a / 'preset-license.txt').read_bytes(), (Path(__file__).resolve().parents[1] / 'public' / 'preset-license.txt').read_bytes())
        self.assertEqual((a / 'support.html').read_bytes(), (Path(__file__).resolve().parents[1] / 'public' / 'support.html').read_bytes())

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

    def test_one_time_reset_is_limited_to_exact_source_pair(self):
        prior = self.previous()
        old = json.loads(prior.read_text())
        self.row['version'] = '2'
        updated = json.loads(json.dumps(self.value))
        with patch('build.APPROVED_RESET', (source_digest(old), source_digest(updated))):
            out = self.build(prior)
            self.assertEqual(json.loads((out / 'catalogue.json').read_bytes())['looks'][0]['version'], '2')
            self.row['description'] = 'Changed beyond the approved reset'
            with self.assertRaisesRegex(ValueError, 'changed or removed'):
                self.build(prior)

    def test_nonproduction_manifest_is_rejected(self):
        out = self.build()
        manifest = json.loads((out / 'catalogue.json').read_text())
        manifest['isDemo'] = True
        path = self.root / 'nonproduction.json'
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'invalid catalogue header'):
            verify_manifest(path)

    def manifest_with(self, mutate):
        manifest = json.loads((self.build() / 'catalogue.json').read_text())
        package = json.loads(base64.b64decode(manifest['looks'][0]['package']))
        mutate(package[0])
        data = json.dumps(package).encode()
        manifest['looks'][0].update(package=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest())
        path = self.root / f'manifest-{self.counter}.json'
        path.write_text(json.dumps(manifest))
        return path

    def test_verify_manifest_accepts_engine_11_and_checks_advanced_fields(self):
        def engine(version):
            def mutate(p):
                p['schemaVersion'] = p['engineVersion'] = version
                p['baseStrength'] = 1
                p['advanced'] = {'red': 1, 'green': 1, 'blue': 1, 'curve': [0, 0.25, 0.5, 0.75, 1], 'highlights': 0.2}
            return mutate
        verify_manifest(self.manifest_with(engine(11)))
        with self.assertRaisesRegex(ValueError, 'unsupported schema or engine'):
            verify_manifest(self.manifest_with(engine(12)))
        cases = {
            'unsupported advanced field': lambda a: a.update(futureDial=1),
            'invalid advanced field highlights': lambda a: a.update(highlights=2),
            'invalid advanced field curve': lambda a: a.update(curve=[0, 0.5, 0.4, 0.75, 1]),
            'invalid advanced field colorMix': lambda a: a.update(colorMix=[{'hue': 0, 'saturation': 0, 'luminance': 0}] * 7),
            'invalid advanced field colorGrading': lambda a: a.update(colorGrading={'tones': [], 'blending': 0.5, 'balance': 0}),
            'need red, green, blue and curve': lambda a: a.pop('red'),
        }
        for message, change in cases.items():
            def mutate(p, change=change):
                engine(11)(p)
                change(p['advanced'])
            with self.assertRaisesRegex(ValueError, message):
                verify_manifest(self.manifest_with(mutate))
        def too_early(p):
            engine(6)(p)
            p['advanced']['whites'] = 0.1
        with self.assertRaisesRegex(ValueError, 'needs engine 7'):
            verify_manifest(self.manifest_with(too_early))

    def test_verify_manifest_checks_vibrance_vignette_and_monochrome(self):
        def look(engine, **fields):
            def mutate(p):
                p['schemaVersion'] = p['engineVersion'] = engine
                p['baseStrength'] = 1
                p['advanced'] = {'red': 1, 'green': 1, 'blue': 1, 'curve': [0, 0.25, 0.5, 0.75, 1], **fields}
            return mutate
        verify_manifest(self.manifest_with(look(11, vibrance=0.3, vignette=-0.4, vignetteMidpoint=0.6, monochrome=[0.1] * 8)))
        for fields, message in (({'vibrance': 0.3}, 'needs engine 11'), ({'monochrome': [0] * 8}, 'needs engine 11')):
            with self.assertRaisesRegex(ValueError, message):
                verify_manifest(self.manifest_with(look(10, **fields)))
        for fields in ({'vibrance': 1.5}, {'vignette': -2}, {'vignetteMidpoint': 1.1}, {'monochrome': [0] * 7}, {'monochrome': [2] + [0] * 7}):
            with self.assertRaisesRegex(ValueError, 'invalid advanced field'):
                verify_manifest(self.manifest_with(look(11, **fields)))

    def test_verify_manifest_checks_calibrated_white_balance(self):
        def look(engine, **fields):
            def mutate(p):
                p['schemaVersion'] = p['engineVersion'] = engine
                p['baseStrength'] = 1
                p['advanced'] = {'red': 1, 'green': 1, 'blue': 1, 'curve': [0, 0.25, 0.5, 0.75, 1], **fields}
            return mutate
        verify_manifest(self.manifest_with(look(11, warmth=0.2, tint=-0.1)))
        with self.assertRaisesRegex(ValueError, 'needs engine 11'):
            verify_manifest(self.manifest_with(look(10, warmth=0.2)))
        for fields in ({'warmth': 1.5}, {'tint': -1.01}, {'tint': 'warm'}):
            with self.assertRaisesRegex(ValueError, 'invalid advanced field'):
                verify_manifest(self.manifest_with(look(11, **fields)))

    def test_verify_manifest_checks_halation_and_bloom(self):
        def look(engine, **fields):
            def mutate(p):
                p['schemaVersion'] = p['engineVersion'] = engine
                p['baseStrength'] = 1
                p['advanced'] = {'red': 1, 'green': 1, 'blue': 1, 'curve': [0, 0.25, 0.5, 0.75, 1], **fields}
            return mutate
        verify_manifest(self.manifest_with(look(11, halation=0.4, halationThreshold=0.8, bloom=0.2, bloomThreshold=0.5)))
        with self.assertRaisesRegex(ValueError, 'needs engine 11'):
            verify_manifest(self.manifest_with(look(10, bloom=0.2)))
        for fields in ({'halation': -0.1}, {'bloom': 1.2}, {'halationThreshold': 2}, {'bloomThreshold': 'high'}):
            with self.assertRaisesRegex(ValueError, 'invalid advanced field'):
                verify_manifest(self.manifest_with(look(11, **fields)))

    def test_first_party_release_rejects_empty_or_reserved_listings(self):
        for mutation in ('empty', 'reserved', 'wrong_catalogue'):
            original = json.loads(json.dumps(self.value))
            if mutation == 'empty': self.value['versions'] = []
            elif mutation == 'reserved': self.row['id'] = 'original'
            else: self.value['catalogID'] = 'other'
            self.write()
            with self.assertRaisesRegex(ValueError, 'first-party catalogue'):
                build(self.source, self.root / ('production-' + mutation), VALIDATOR, require_production=True)
            self.value = original
            self.row = self.value['versions'][0]

    def research(self, mutate=None):
        manifest = json.loads((self.build() / 'catalogue.json').read_text())
        manifest['catalogID'], manifest['title'] = 'tinge-research', 'Research looks'
        manifest['looks'][0] = dict(manifest['looks'][0], id='research-look', name='Research Look')
        if mutate: mutate(manifest)
        path = self.root / f'research-{self.counter}.json'
        path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        return path

    def build_with_research(self, path):
        self.counter += 1
        self.write()
        output = self.root / f'output-{self.counter}'
        build(self.source, output, VALIDATOR, research_path=path, require_production=True)
        return output

    def test_research_catalogue_is_copied_beside_unchanged_production(self):
        plain = self.build()
        path = self.research()
        out = self.build_with_research(path)
        self.assertEqual((out / RESEARCH_OUTPUT).read_bytes(), path.read_bytes())
        self.assertEqual((out / 'catalogue.json').read_bytes(), (plain / 'catalogue.json').read_bytes())
        self.assertFalse((plain / RESEARCH_OUTPUT).exists())
        self.assertEqual(json.loads((out / 'catalogue.json').read_text())['catalogID'], 'tinge')

    def test_research_catalogue_identity_and_content_are_checked(self):
        def look(**changes): return lambda m: m['looks'][0].update(changes)
        cases = {
            'reuse the production': lambda m: m.update(catalogID='tinge'),
            'reuse the production ': lambda m: m.update(title='Tinge catalogue'),
            'header': lambda m: m.update(isDemo=True),
            'collides': look(id='look'),
            'reserved': look(id='personal-1'),
        }
        for message, mutate in cases.items():
            with self.assertRaisesRegex(ValueError, message.strip()):
                self.build_with_research(self.research(mutate))
        with self.assertRaises(Exception):
            self.build_with_research(self.research(look(sha256='0' * 64)))
        self.assertFalse((self.root / f'output-{self.counter}').exists())

    def test_research_catalogue_cannot_reuse_retired_production_id(self):
        # A renamed production look keeps its old ID as an unlisted, retained version.
        self.value['versions'].append(dict(self.row, id='old-look', listed=False))
        retired = self.research(lambda m: m['looks'][0].update(id='old-look'))
        with self.assertRaisesRegex(ValueError, 'collides'):
            self.build_with_research(retired)

    def test_repository_catalogues_do_not_share_look_ids(self):
        if not RESEARCH_SOURCE.is_file():
            self.skipTest('no experimental research catalogue in this checkout')
        production = json.loads((RESEARCH_SOURCE.parents[2] / 'catalogue' / 'source.json').read_text())
        research = json.loads(RESEARCH_SOURCE.read_text())
        self.assertFalse({r['id'] for r in production['versions']} & {l['id'] for l in research['looks']})

    def test_repository_research_catalogue_passes_validator(self):
        if not RESEARCH_SOURCE.is_file():
            self.skipTest('no experimental research catalogue in this checkout')
        verify_manifest(RESEARCH_SOURCE)

    def test_mutating_old_version_and_path_escape_are_rejected(self):
        old = self.previous()
        self.row['name'] = 'Changed'
        with self.assertRaisesRegex(ValueError, 'changed or removed'): self.build(old)
        self.row['name'] = 'Look'
        self.row['packagePath'] = '../other.json'
        with self.assertRaisesRegex(ValueError, 'outside'): self.build()


if __name__ == '__main__':
    unittest.main()
