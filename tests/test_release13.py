"""Regression checks for 1.3; all data is synthetic and isolated."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_harness as fixtures
from harness_core import Store, HarnessError, PACKAGE, export_data, import_data, validate_records


class Release13Tests(unittest.TestCase):
    setUp = fixtures.HarnessTests.setUp
    feedback = fixtures.HarnessTests.feedback
    evidence = fixtures.HarnessTests.evidence
    candidate = fixtures.HarnessTests.candidate
    pairs = fixtures.HarnessTests.pairs
    authorize = fixtures.HarnessTests.authorize
    rewrite_zip = fixtures.HarnessTests.rewrite_zip

    def disk(self):
        return {p.relative_to(self.store.root).as_posix(): p.read_bytes()
                for p in self.store.root.rglob('*') if p.is_file()}

    def generations(self):
        return {p.name for p in (self.store.root / 'generations').iterdir()}

    def test_forget_missing_id_no_change(self):
        self.feedback(features=['柔光'], long_term=True)
        before = self.disk()
        with self.assertRaises(HarnessError):
            self.store.manage('forget', confirm=True)
        self.assertEqual(before, self.disk())

    def test_forget_unknown_id_no_change(self):
        self.candidate()
        before = self.disk()
        with self.assertRaisesRegex(HarnessError, '不存在'):
            self.store.manage('forget', 'nonexistent', confirm=True)
        self.assertEqual(before, self.disk())

    def test_delete_requires_confirmation(self):
        f = self.feedback()['feedback']
        for operation in ('forget', 'clear'):
            before = self.disk()
            with self.assertRaises(HarnessError):
                self.store.manage(operation, f['id'])
            self.assertEqual(before, self.disk())

    def test_forget_only_cascades_related_records(self):
        c = self.candidate()
        self.authorize()
        self.store.experiment(c['id'], self.pairs(), 'synthetic')
        unrelated = copy.deepcopy(self.store.load())
        f = self.feedback(features=['柔光'], long_term=True)['feedback']
        target = self.store.load()['user_preferences']['preferences'][0]
        self.assertTrue(self.store.manage('forget', target['id'], confirm=True)['saved'])
        after = self.store.load()
        for key in ('candidates', 'experiments', 'learned_overrides'):
            self.assertEqual(unrelated[key], after[key])
        self.assertNotIn(f['id'], [x['id'] for x in after['user_preferences']['feedback']])
        self.store.manage('forget', c['evidence'][0], confirm=True)
        for key in ('candidates', 'experiments', 'learned_overrides'):
            self.assertEqual([], self.store.load()[key])

    def test_forget_empty_evidence_target(self):
        self.feedback(features=['柔光'], long_term=True)
        def detach(d):
            d['user_preferences']['preferences'][0]['evidence'] = []
        self.store.change(detach)
        target = self.store.load()['user_preferences']['preferences'][0]
        self.store.manage('forget', target['id'], confirm=True)
        self.assertEqual([], self.store.load()['user_preferences']['preferences'])
        self.assertEqual(1, len(self.store.load()['user_preferences']['feedback']))

    def test_shared_evidence_is_preserved(self):
        self.feedback(features=['柔光', '暖色'], long_term=True)
        before = self.store.load()['user_preferences']
        self.store.manage('forget', before['preferences'][0]['id'], confirm=True)
        after = self.store.load()['user_preferences']
        self.assertEqual(before['feedback'], after['feedback'])
        self.assertEqual([before['preferences'][1]], after['preferences'])

    def test_forget_write_failure_keeps_current(self):
        f = self.feedback(features=['柔光'], long_term=True)['feedback']
        before = self.disk()
        with patch('harness_core.atomic', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.manage('forget', f['id'], confirm=True)
        self.assertEqual(before, self.disk())

    def test_forget_pointer_publication_failure_is_atomic(self):
        f = self.feedback()['feedback']
        before = self.disk()
        replace = os.replace
        def fail_current(src, dest):
            if Path(dest).name == 'CURRENT':
                raise OSError('publication failure')
            return replace(src, dest)
        with patch('harness_core.os.replace', side_effect=fail_current):
            with self.assertRaises(OSError):
                self.store.manage('forget', f['id'], confirm=True)
        self.assertEqual(before, self.disk())

    def test_clear_current_records_preserves_history(self):
        self.candidate()
        self.feedback(features=['永久'], permanent=True)
        before = self.disk()
        self.assertTrue(self.store.manage('clear', confirm=True)['saved'])
        data = self.store.load()
        for k in ('feedback', 'preferences', 'constraints'):
            self.assertEqual([], data['user_preferences'][k])
        for k in ('candidates', 'experiments', 'learned_overrides'):
            self.assertEqual([], data[k])
        for name, raw in before.items():
            if name.startswith('generations/'):
                self.assertEqual(raw, (self.store.root / name).read_bytes())

    def test_opposite_preferences_conflict_on_write_and_query(self):
        self.feedback(features=['柔光'], long_term=True)
        self.feedback(features=['柔光'], long_term=True, rating='厌恶')
        prefs = self.store.load()['user_preferences']['preferences']
        self.assertEqual(['conflict', 'conflict'], [p['status'] for p in prefs])
        result = self.store.applicable('户外人物', 'Z-Image')
        self.assertEqual([], result['preferences'])
        self.assertEqual(2, len(result['conflicts']))

    def test_legacy_active_opposites_are_exposed_at_query(self):
        self.feedback(features=['柔光'], long_term=True)
        self.feedback(features=['柔光'], long_term=True, rating='厌恶')
        def legacy(d):
            for p in d['user_preferences']['preferences']:
                p['status'] = 'active'
        self.store.change(legacy)
        self.assertEqual(2, len(self.store.applicable('户外人物', 'Z-Image')['conflicts']))

    def test_duplicate_preference_retains_both_evidence_records(self):
        self.feedback(features=['柔光'], long_term=True)
        self.feedback(features=['柔光'], long_term=True, prompt_id='second')
        data = self.store.load()['user_preferences']
        self.assertEqual(1, len(data['preferences']))
        self.assertEqual({f['id'] for f in data['feedback']}, set(data['preferences'][0]['evidence']))

    def test_scope_model_version_and_polarity_not_merged(self):
        self.feedback(features=['柔光'], long_term=True)
        for extra in ({'model': 'Krea 2'}, {'context': '宫廷'}, {'model_version': 'v2'}):
            self.feedback(features=['柔光'], long_term=True, rating='厌恶', **extra)
        prefs = self.store.load()['user_preferences']['preferences']
        self.assertEqual(4, len(prefs))
        self.assertTrue(all(p['status'] == 'active' for p in prefs))

    def test_whitespace_feedback_rejected_without_data_change(self):
        for extra in ({'features': [' ']}, {'features': ['\t\n'], 'permanent': True},
                      {'inference': '  ', 'long_term': True}):
            before = self.disk()
            with self.assertRaises(HarnessError):
                self.feedback(**extra)
            self.assertEqual(before, self.disk())

    def test_import_whitespace_preference_rejected(self):
        self.feedback(features=['柔光'], long_term=True)
        data = self.store.load()['user_preferences']
        data['preferences'][0]['content'] = ' \n'
        file = self.root / 'bad.json'
        file.write_text(json.dumps(data), encoding='utf-8')
        before = self.disk()
        with self.assertRaises(HarnessError):
            import_data(self.store, file)
        self.assertEqual(before, self.disk())

    def test_weak_inference_stays_distinct_from_confirmation(self):
        self.feedback(inference='柔光', long_term=True, confirmed=False)
        self.feedback(features=['柔光'], long_term=True)
        prefs = self.store.load()['user_preferences']['preferences']
        self.assertEqual(2, len(prefs))
        inferred = next(p for p in prefs if p['source'] == 'Agent 推断')
        self.assertEqual('弱', inferred['weight'])
        self.assertFalse(inferred['hard'])

    def test_repeat_check_has_no_generation_growth(self):
        before = self.generations()
        for _ in range(4):
            self.assertTrue(self.store.probe()['available'])
        self.assertEqual(before, self.generations())
        self.assertTrue((self.store.root / 'health.json').exists())

    def test_repeated_noop_operations_no_generation_growth(self):
        self.store.start('same')
        before = self.generations()
        self.store.start('same')
        self.store.toggle(False)
        self.store.configure({'min_feedback': 3})
        self.assertFalse(self.store.manage('learning', value=True)['saved'])
        self.store.change(lambda data: None)
        self.assertEqual(before, self.generations())

    def test_paused_learning_no_snapshot_or_log(self):
        self.store.manage('learning', value=False)
        before = self.disk()
        for _ in range(3):
            self.assertFalse(self.feedback()['saved'])
        self.assertEqual(before, self.disk())

    def test_repeated_rejection_journal_no_generation_growth(self):
        before = self.generations()
        logs = len(self.store.load()['evolution_log'])
        for _ in range(3):
            with self.assertRaises(HarnessError):
                self.store.candidate('规则', [], '目的', '因素', '语境')
        self.assertEqual(before, self.generations())
        self.assertEqual(logs + 3, len(self.store.load()['evolution_log']))
        self.feedback()
        after = self.store.load()
        self.assertEqual(logs + 4, len(after['evolution_log']))
        self.assertEqual(len(before) + 1, len(self.generations()))
        validate_records(after)

    def test_real_business_change_publishes_one_generation(self):
        before = self.generations()
        self.feedback(features=['柔光'], long_term=True)
        self.assertEqual(len(before) + 1, len(self.generations()))

    def test_corrupt_audit_does_not_get_overwritten(self):
        with self.assertRaises(HarnessError):
            self.store.candidate('规则', [], '目标', '因素', '语境')
        path = self.store._journal_path()
        path.write_text('broken', encoding='utf-8')
        self.assertFalse(self.store.probe()['available'])
        self.assertEqual('broken', path.read_text(encoding='utf-8'))

    def test_rejected_audit_survives_export_and_next_generation(self):
        with self.assertRaises(HarnessError):
            self.store.candidate('规则', [], '目标', '因素', '语境')
        event = self.store.load()['evolution_log'][-1]
        file = self.root / 'audit-export.zip'
        export_data(self.store, file)
        dest = Store(self.root / 'audit-import')
        import_data(dest, file)
        self.assertIn(event, dest.load()['evolution_log'])
        self.feedback()
        self.assertEqual(1, sum(e['id'] == event['id'] for e in self.store.load()['evolution_log']))

    def test_122_migration_is_still_accepted(self):
        from harness_core import encoded
        self.feedback(features=['柔光'], long_term=True)
        file = self.root / 'source.zip'
        export_data(self.store, file)
        def old_manifest(entries):
            manifest = json.loads(entries['manifest.json'])
            manifest['source_version'] = '1.22'
            manifest['source_skill'] = 'prompt-assistant-online-v1-22-harness'
            entries['manifest.json'] = encoded(manifest)
        file = self.rewrite_zip(file, old_manifest)
        dest = Store(self.root / 'old-import')
        import_data(dest, file)
        self.assertEqual(self.store.load()['user_preferences'], dest.load()['user_preferences'])

    def test_whitespace_candidate_is_rejected(self):
        self.store.toggle(True)
        with self.assertRaises(HarnessError):
            self.store.candidate('  ', [], '目标', '因素', '语境')
        self.assertEqual([], self.store.load()['candidates'])

    def test_three_import_types_preserve_or_reset_explicit_fields(self):
        self.feedback(features=['柔光'], long_term=True)
        for kind in ('preferences', 'harness', 'full'):
            with self.subTest(kind=kind):
                file = self.root / (kind + ('.json' if kind == 'preferences' else '.zip'))
                export_data(self.store, file, kind)
                target = Store(self.root / ('target-' + kind))
                target.probe(create=True)
                target.toggle(True)
                target.manage('authorize', value=True, confirm=True)
                target.configure({'min_feedback': 7})
                target.manage('learning', value=False)
                target.start('existing-chat')
                before = target.load()
                result = import_data(target, file)
                after = target.load()
                self.assertTrue(Path(result['backup']).exists())
                self.assertEqual(before['user_preferences']['settings'], after['user_preferences']['settings'])
                self.assertEqual(7, after['config']['min_feedback'])
                if kind == 'preferences':
                    self.assertEqual(before['config'], after['config'])
                    self.assertEqual(before['sessions'], after['sessions'])
                    self.assertEqual(before['candidates'], after['candidates'])
                else:
                    self.assertFalse(after['config']['enabled'])
                    self.assertFalse(after['config']['authorized_overrides'])
                    self.assertEqual({}, after['sessions'])

    def test_import_opposites_mark_both_sides_and_duplicates_merge(self):
        self.feedback(features=['柔光'], long_term=True)
        file = self.root / 'preferences.json'
        export_data(self.store, file, 'preferences')
        dest = Store(self.root / 'merge')
        dest.probe(create=True)
        values = dict(prompt_id='other', rating='特别喜欢', raw='synthetic', features=['柔光'],
                      context='户外人物', model='Z-Image', confirmed=True, long_term=True)
        dest.feedback(**values)
        import_data(dest, file)
        self.assertEqual(1, len(dest.load()['user_preferences']['preferences']))
        dest.feedback(**{**values, 'rating': '厌恶'})
        self.assertEqual(2, len(dest.applicable('户外人物', 'Z-Image')['conflicts']))

    def test_cli_missing_id_reports_failure_utf8_without_cache_flags(self):
        env = os.environ.copy()
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        env['PYTHONIOENCODING'] = 'ascii'
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / 'skill'
            shutil.copytree(PACKAGE, package)
            result = subprocess.run([sys.executable, str(package/'scripts/harness.py'),
                '--data-dir', str(self.store.root), 'manage', 'forget', '--confirm'],
                env=env, capture_output=True)
            self.assertEqual(1, result.returncode)
            failure = json.loads(result.stderr.decode('utf-8'))
            self.assertFalse(failure['saved'])
            self.assertEqual([], list(package.rglob('__pycache__')))

    def test_all_entrypoints_twice_without_cache_flags(self):
        env = os.environ.copy()
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / 'skill'
            shutil.copytree(PACKAGE, package)
            commands = [('harness.py', '--help'), ('check_harness_environment.py', '--help'),
                        ('export_harness.py', '--help'), ('import_harness.py', '--help'),
                        ('build_release.py', '--help'), ('validate_harness.py',)]
            for _ in range(2):
                for script, *args in commands:
                    result = subprocess.run([sys.executable, str(package/'scripts'/script), *args],
                                            env=env, capture_output=True)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual([], list(package.rglob('__pycache__')))

    def test_real_cache_pollution_still_rejected(self):
        from validate_harness import validate_package
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / 'skill'
            shutil.copytree(PACKAGE, package)
            cache = package / 'scripts/__pycache__'
            cache.mkdir()
            (cache/'bad.pyc').write_bytes(b'synthetic')
            self.assertFalse(validate_package(package)['valid'])

