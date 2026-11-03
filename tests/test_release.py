"""Release integrity checks; no network, real user data, or image generation."""
import json
import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'scripts'))
import release


class ReleaseTests(unittest.TestCase):
    def test_missing_target_reference_is_rejected(self):
        registry = json.loads((ROOT / 'adapters/registry.json').read_text(encoding='utf-8'))
        for row in registry['adapters']:
            broken = copy.deepcopy(registry)
            next(item for item in broken['adapters'] if item['target'] == row['target'])['compiler_policy'].pop('reference')
            with self.subTest(target=row['target']), self.assertRaises(ValueError):
                release.verify_route_references(ROOT, broken, release.inventory(ROOT))

    def test_missing_or_escaping_route_file_is_rejected(self):
        registry = json.loads((ROOT / 'adapters/registry.json').read_text(encoding='utf-8'))
        for ref in ('references/adapters/absent.md', 'references/adapters/../../../outside.md'):
            broken = copy.deepcopy(registry)
            broken['adapters'][0]['compiler_policy']['reference'] = ref
            with self.subTest(reference=ref), self.assertRaises(ValueError):
                release.verify_route_references(ROOT, broken, release.inventory(ROOT))

    def test_manifest_detects_tampered_file(self):
        with tempfile.TemporaryDirectory(prefix='pa-release-tamper-') as temp:
            root = Path(temp) / 'source'
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns('.git', '__pycache__'))
            with (root / 'README.md').open('a', encoding='utf-8') as handle:
                handle.write('\nSynthetic modification\n')
            with self.assertRaises(ValueError):
                release.verify(root)

    def test_unexpected_report_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='pa-release-extra-') as temp:
            root = Path(temp) / 'source'
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns('.git', '__pycache__'))
            (root / 'private-report.md').write_text('Synthetic report', encoding='utf-8')
            with self.assertRaises(ValueError):
                release.verify(root)

    def test_existing_zip_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix='pa-release-existing-') as temp:
            output = Path(temp) / 'existing.zip'
            output.write_bytes(b'Existing archive sentinel')
            with self.assertRaises(ValueError):
                release.build(ROOT, output)
            self.assertEqual(output.read_bytes(), b'Existing archive sentinel')

    def test_reproducible_build_and_loadable_entry(self):
        with tempfile.TemporaryDirectory(prefix='pa-release-build-') as temp:
            first, second = Path(temp) / 'first.zip', Path(temp) / 'second.zip'
            release.build(ROOT, first)
            release.build(ROOT, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(release.SKILL_NAME + '/SKILL.md', archive.namelist())
                self.assertEqual(json.loads(archive.read(release.SKILL_NAME + '/RELEASE-MANIFEST.json'))['version'], '1.5.3')


if __name__ == '__main__':
    unittest.main(verbosity=2)
