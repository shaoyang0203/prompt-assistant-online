"""Package preservation and migration regressions; no creative quality scoring."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import test_harness as fixtures
from harness_core import Store, PACKAGE, VERSION, SKILL, encoded, export_data, import_data
from validate_harness import validate_package


class Release14Tests(unittest.TestCase):
    setUp = fixtures.HarnessTests.setUp
    feedback = fixtures.HarnessTests.feedback
    rewrite_zip = fixtures.HarnessTests.rewrite_zip

    def test_130_migration_remains_importable(self):
        self.feedback(features=['soft light'], long_term=True)
        path = self.root / 'old.zip'
        export_data(self.store, path)
        def old_manifest(entries):
            manifest = json.loads(entries['manifest.json'])
            manifest['source_version'] = '1.3.0-harness'
            manifest['source_skill'] = 'prompt-assistant-online-v1-3-0-harness'
            entries['manifest.json'] = encoded(manifest)
        dest = Store(self.root / 'new')
        import_data(dest, self.rewrite_zip(path, old_manifest))
        self.assertEqual(self.store.load()['user_preferences'], dest.load()['user_preferences'])
        self.assertFalse(dest.load()['config']['enabled'])

    def test_export_uses_current_identity(self):
        from harness_core import load_archive
        path = self.root / 'current.zip'
        export_data(self.store, path)
        _, manifest = load_archive(path)
        self.assertEqual('1.4.0-harness', VERSION)
        self.assertEqual('prompt-assistant-online-v1-4-0-harness', SKILL)
        self.assertEqual(VERSION, manifest['source_version'])
        self.assertEqual(SKILL, manifest['source_skill'])

    def test_style_library_is_required_and_integrity_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'skill'
            shutil.copytree(PACKAGE, root)
            library = root / 'references/风格推荐库.md'
            original = library.read_bytes()
            library.unlink()
            self.assertFalse(validate_package(root)['valid'])
            library.write_bytes(original + b'\nchanged')
            self.assertFalse(validate_package(root)['valid'])

    def test_original_composition_knowledge_remains_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'skill'
            shutil.copytree(PACKAGE, root)
            name = 'references/视觉设计系统/04-构图与空间.md'
            path = root / name
            path.write_bytes(path.read_bytes().replace('第一视觉锚点'.encode(), '已改变的内容'.encode(), 1))
            manifest = root / 'harness/design-protocol-integrity.json'
            revision = json.loads(manifest.read_text(encoding='utf-8'))
            revision['files'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(revision, ensure_ascii=False), encoding='utf-8')
            result = validate_package(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('受保护' in e for e in result['errors']))
