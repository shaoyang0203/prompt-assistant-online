"""Offline structural regression tests. All semantic reviews are synthetic fixtures."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'scripts'))
import adapter
import flow
import knowledge
import prefs
from contracts import COMPILED_KINDS, ContractError, digest, validate_master
from compile_checks import AXES, prepare, review_hash
from master import display_value
from harness_store import Store


def fixture(case='portrait'):
    name = 'master.json' if case == 'portrait' else case + '.json'
    return json.loads((ROOT / 'tests/fixtures' / name).read_text(encoding='utf-8'))


def approved(case='portrait', manifest=True, target='generic', master=None):
    state = flow.new_task('regression', 'Synthetic regression request')
    flow.set_concepts(state, [dict(id=x, core=x, focus=x, feature=x, scene='Test scene ' + x) for x in 'ABC'])
    flow.select(state, 'A', 'synthetic:user-selection')
    flow.save_master(state, master if master is not None else fixture(case))
    flow.coordinate(state, 'pass', [], 'Synthetic test attestation, not a visual evaluation', ['camera_composition'])
    flow.show(state)
    flow.approve(state, 1, 'synthetic:user-confirmation')
    if manifest:
        flow.prepare_manifest(state, target)
    return state


def candidate(state, target=None):
    master = state['masters'][-1]
    selected = target or state.get('compilation_target', 'generic')
    facts = {k: v for k, v in master['items'].items() if v['kind'] in COMPILED_KINDS}
    segments = []
    for key, fact in facts.items():
        if fact['kind'] == 'aspect_ratio':
            continue
        value = fact['value']
        text = value['literal'] + ' ' + value['appearance'] if fact['kind'] == 'image_text' else value
        segments.append({'text': text, 'item_ids': [key]})
    return {'master_hash': digest(master), 'target': selected, 'segments': segments,
            'parameters': {'aspect_ratio': copy.deepcopy(master['items'][master['globals']['aspect_ratio']]['value'])}}


def review(state, artifact):
    facts = prepare(state)['manifest']['facts']
    return {'master_hash': artifact['master_hash'], 'artifact_hash': review_hash(artifact),
            'reviewer': 'synthetic-regression-fixture', 'evidence_ref': 'synthetic:not-a-real-semantic-review',
            'axes': {key: {'result': 'pass', 'note': 'Synthetic declaration only'} for key in AXES},
            'item_results': {key: {'result': 'pass', 'note': 'Synthetic declaration only'} for key in facts}}


class AuditRegressions(unittest.TestCase):
    def test_submit_without_master_returns_structured_fail(self):
        state = flow.new_task('empty-task', 'Synthetic request')
        before = copy.deepcopy(state)
        result = flow.submit(state, {}, {})
        self.assertEqual((result['result'], result['saved'], result['attempt']), ('fail', False, 0))
        self.assertIn('尚未创建视觉母版', result['problems'][0])
        self.assertEqual(state, before)

    def test_submit_without_master_cli(self):
        with tempfile.TemporaryDirectory(prefix='pa-empty-submit-') as temp:
            command = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'scripts/pa15.py'), '--data-dir', temp, '--task', 'empty-task']
            subprocess.run(command + ['new', '--request', 'Synthetic request'], capture_output=True, check=True)
            empty = Path(temp) / 'empty.json'
            empty.write_text('{}', encoding='utf-8')
            before = Store(temp).load('empty-task')
            result = subprocess.run(command + ['submit', '--candidate', str(empty), '--review', str(empty)], capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, '')
            self.assertEqual(json.loads(result.stdout)['attempt'], 0)
            self.assertEqual(Store(temp).load('empty-task'), before)

    def test_empty_correction_issue_rejected_without_mutation(self):
        state = flow.new_task('correction-test', 'Synthetic request')
        options = [dict(mode=mode, design='Synthetic', changes='Synthetic', reason='Synthetic', expected='Synthetic') for mode in ('strict', 'local', 'reconstruct')]
        for issue in ('', '  \n', None, 123):
            before = copy.deepcopy(state)
            with self.assertRaises(ContractError):
                flow.correction(state, {'issue': issue, 'intent': 'conflict', 'options': options})
            self.assertEqual(state, before)
        with self.assertRaises(ContractError):
            flow.correction(state, {'issue': 'Synthetic conflict', 'intent': 'conflict', 'options': [None, {}, {}]})
        self.assertEqual(flow.correction(state, {'issue': 'Synthetic conflict', 'intent': 'conflict', 'options': options})['applied'], False)

    def test_zone_reordering_requires_exact_structure_history(self):
        state = approved()
        master = copy.deepcopy(state['masters'][-1])
        zone = next(key for key, values in master['zones'].items() if len(values) > 1)
        master['zones'][zone].reverse()
        master.update(revision=2, parent_revision=1, changes=[])
        before = copy.deepcopy(state)
        with self.assertRaises(ContractError):
            flow.save_master(state, master)
        self.assertEqual(state, before)
        record = {'path': 'zones.' + zone, 'reason': 'Synthetic reordering', 'source_ref': 'synthetic:user'}
        for rows in ([record, record], [{**record, 'reason': '   '}], [{**record, 'path': 'zones.scene_art' if zone != 'scene_art' else 'zones.character_art'}]):
            master['structure_changes'] = rows
            with self.assertRaises(ContractError):
                flow.save_master(state, master)
            self.assertEqual(state, before)
        master['structure_changes'] = [record]
        flow.save_master(state, master)
        event = state['events'][-1]['structural_changes'][0]
        self.assertEqual(event['before'], before['masters'][-1]['zones'][zone])
        self.assertEqual(event['after'], master['zones'][zone])
        self.assertTrue(set(event['before']) <= set(state['events'][-1]['affected']))
        self.assertIn('Synthetic reordering', flow.show(state)['text'])
        with self.assertRaises(ContractError):
            flow.prepare_manifest(state)

    def test_global_reference_change_requires_history(self):
        initial = fixture()
        for key, text in (('di-test-text-a', 'A'), ('di-test-text-b', 'B')):
            initial['items'][key] = copy.deepcopy(initial['items'][initial['globals']['medium']])
            initial['items'][key].update(kind='image_text', value={'literal': text, 'appearance': 'Synthetic typography'})
            initial['changes'].append({'item_id': key, 'operation': 'add', 'reason': 'Synthetic text', 'source_ref': 'synthetic:user'})
            initial['globals']['image_text'].append(key)
        state = approved(master=initial)
        master = copy.deepcopy(initial)
        master.update(revision=2, parent_revision=1, changes=[])
        master['globals']['image_text'].reverse()
        with self.assertRaises(ContractError):
            flow.save_master(state, master)
        master['structure_changes'] = [{'path': 'globals.image_text', 'reason': 'Synthetic reference reorder', 'source_ref': 'synthetic:user'}]
        flow.save_master(state, master)
        event = state['events'][-1]['structural_changes'][0]
        self.assertEqual((event['before'], event['after']), (initial['globals']['image_text'], list(reversed(initial['globals']['image_text']))))
        self.assertEqual(master['items'], initial['items'])

    def test_structure_record_without_difference_is_rejected(self):
        state = approved()
        master = copy.deepcopy(state['masters'][-1])
        master.update(revision=2, parent_revision=1, changes=[])
        master['structure_changes'] = [{'path': 'globals.medium', 'reason': 'Synthetic no-op', 'source_ref': 'synthetic:user'}]
        with self.assertRaises(ContractError):
            flow.save_master(state, master)

    def test_pending_query_scoped_and_all_items_still_available(self):
        with tempfile.TemporaryDirectory(prefix='pa-pending-query-') as temp:
            store = prefs.Prefs(temp)
            rows = [('match', 'lighting', '室内', 'gpt-web'), ('other-scene', 'lighting', '室外', 'gpt-web'),
                    ('other-model', 'lighting', '室内', 'moss-image'), ('other-dimension', 'camera', '室内', 'gpt-web'), ('global', 'lighting', '*', '*')]
            for name, dimension, scene, model in rows:
                prefs.command_add(store, {'name': name, 'dimension': dimension, 'attributes': ['左侧窗光'], 'apply_mode': 'prefer', 'source': 'inferred', 'scope': {'scene': scene, 'model': model}})
            data = store.load()
            scoped = prefs.query_view(data, '室内', 'gpt-web', 'lighting')
            self.assertEqual({item['name'] for item in scoped['pending']}, {'match', 'global'})
            self.assertEqual({item['name'] for item in prefs.query_view(data)['pending']}, {'global'})
            self.assertEqual(prefs.command_list(store, None)['templates'], data['templates'])

    def test_selected_direction_cannot_be_overwritten(self):
        state = flow.new_task('selection', 'Test')
        concepts = [dict(id=x, core=x, focus=x, feature=x, scene=x) for x in 'ABC']
        flow.set_concepts(state, concepts)
        flow.select(state, 'A', 'synthetic:user')
        before = copy.deepcopy(state)
        with self.assertRaises(ContractError):
            flow.set_concepts(state, [dict(id=x, core=x, focus=x, feature=x, scene=x) for x in 'XYZ'])
        self.assertEqual(state, before)
        state['selected'] = 'missing'
        with self.assertRaises(ContractError):
            flow.save_master(state, fixture())

    def test_exhausted_budget_returns_fail_without_extra_attempt(self):
        state = approved()
        for attempt in (1, 2):
            report = flow.submit(state, {}, {})
            self.assertEqual((report['result'], report['attempt']), ('fail', attempt))
        before = copy.deepcopy(state)
        report = flow.submit(state, {}, {})
        self.assertEqual(report['result'], 'fail')
        self.assertFalse(report['saved'])
        self.assertIn('预算已耗尽', report['problems'][0])
        self.assertEqual(state, before)

    def test_manifest_required(self):
        state = approved(manifest=False)
        artifact = candidate(state, 'gpt-web')
        outcome = flow.submit(state, artifact, review(state, artifact))
        self.assertEqual(outcome['result'], 'fail')
        self.assertIn('manifest', outcome['problems'][0])
        self.assertEqual(state['attempts'], {})
        with self.assertRaises(ContractError):
            flow.deliver(state)

    def test_unconfirmed_master_rejected(self):
        state = approved()
        state['approvals'] = []
        outcome = flow.submit(state, {}, {})
        self.assertEqual(outcome['result'], 'fail')
        self.assertIn('尚未确认', outcome['problems'][0])
        self.assertEqual(state['attempts'], {})

    def test_route_mismatch_and_old_delivery_rejected(self):
        state = approved(target='gpt-web')
        artifact = candidate(state, 'generic')
        self.assertEqual(flow.submit(state, artifact, review(state, artifact))['result'], 'fail')
        state = approved()
        artifact = candidate(state)
        self.assertEqual(flow.submit(state, artifact, review(state, artifact))['result'], 'pass')
        flow.prepare_manifest(state, 'gpt-web')
        with self.assertRaises(ContractError):
            flow.deliver(state)

    def test_new_revision_needs_new_manifest(self):
        state = approved()
        master = copy.deepcopy(state['masters'][-1])
        key = next(key for key, item in master['items'].items() if item['kind'] == 'visual_fact' and item['constraint_strength'] == 'adjustable_design')
        master['items'][key]['value'] += '（合成测试局部更新）'
        master['revision'] = 2
        master['parent_revision'] = 1
        master['changes'] = [{'item_id': key, 'operation': 'update', 'reason': 'Synthetic local change', 'source_ref': 'synthetic:user'}]
        flow.begin_change(state, 'synthetic:user')
        flow.save_master(state, master)
        flow.coordinate(state, 'pass', [], 'Synthetic review', ['camera_composition'])
        flow.show(state)
        flow.approve(state, 2, 'synthetic:user')
        self.assertEqual(flow.submit(state, {}, {})['result'], 'fail')
        flow.prepare_manifest(state)
        artifact = candidate(state)
        self.assertEqual(flow.submit(state, artifact, review(state, artifact))['result'], 'pass')

    def test_natural_routes_and_complete_workflows(self):
        for case in ('portrait', 'environment', 'correction'):
            for route in adapter.routes():
                if route['prompt'] == 'json-layout':
                    continue
                with self.subTest(case=case, target=route['target']):
                    state = approved(case, manifest=False)
                    ratio_value = state['masters'][-1]['items'][state['masters'][-1]['globals']['aspect_ratio']]['value']
                    if route['supported_aspect_ratios'] is not None and adapter.ratio_text(ratio_value, normalized=True) not in route['supported_aspect_ratios']:
                        before = copy.deepcopy(state)
                        with self.assertRaises(ContractError):
                            flow.prepare_manifest(state, route['target'])
                        self.assertEqual(state, before)
                        continue
                    flow.prepare_manifest(state, route['target'])
                    artifact = candidate(state)
                    self.assertEqual(flow.submit(state, artifact, review(state, artifact))['result'], 'pass')
                    delivery = flow.deliver(state)
                    ratio = adapter.ratio_text(artifact['parameters']['aspect_ratio'])
                    if route['aspect_ratio'] == 'outside-prompt':
                        self.assertNotIn('Aspect ratio:', delivery['prompt'])
                        self.assertNotIn('--ar', delivery['prompt'])
                        self.assertEqual(delivery['external_settings']['aspect_ratio'], ratio)
                    elif route['ratio_format'] == 'midjourney-ar':
                        self.assertTrue(delivery['prompt'].endswith('--ar ' + ratio))
                    else:
                        self.assertTrue(delivery['prompt'].endswith('Aspect ratio: ' + ratio + '.'))

    def test_omission_and_uncertain_do_not_pass(self):
        state = approved()
        artifact = candidate(state)
        artifact['segments'].pop()
        self.assertEqual(flow.submit(state, artifact, review(state, artifact))['result'], 'fail')
        state = approved()
        artifact = candidate(state)
        check = review(state, artifact)
        check['axes']['relations']['result'] = 'uncertain'
        self.assertEqual(flow.submit(state, artifact, check)['result'], 'uncertain')
        with self.assertRaises(ContractError):
            flow.deliver(state)

    def test_ratio_change_requires_seven_checks(self):
        state = approved()
        master = copy.deepcopy(state['masters'][-1])
        key = master['globals']['aspect_ratio']
        master['items'][key]['value'] = {'width': 1, 'height': 1}
        master['revision'] = 2
        master['parent_revision'] = 1
        master['changes'] = [{'item_id': key, 'operation': 'update', 'reason': 'Synthetic ratio change', 'source_ref': 'synthetic:user'}]
        flow.begin_change(state, 'synthetic:user')
        flow.save_master(state, master, {'user_ref': 'synthetic:user', 'item_ids': [key]})
        with self.assertRaises(ContractError):
            flow.coordinate(state, 'pass', [], 'Synthetic', ['camera_composition'])
        axes = {axis: {'result': 'pass', 'note': 'Synthetic declaration'} for axis in flow.COMPOSITION_AXES}
        self.assertEqual(flow.coordinate(state, 'pass', [], 'Synthetic', ['camera_composition'], axes)['result'], 'pass')

    def test_ratio_metadata_independent_and_literal_display(self):
        master = fixture()
        item = master['items'][master['globals']['aspect_ratio']]
        item.update(design_source='user_specified', confirmation_status='confirmed', constraint_strength='adjustable_design')
        with self.assertRaises(ContractError):
            validate_master(master)
        item['constraint_strength'] = 'hard_constraint'
        validate_master(master)
        item.update(design_source='model_added', confirmation_status='confirmed')
        validate_master(master)
        literal = '第一行 "A"\n第二行 3:2'
        self.assertIn(literal, display_value({'kind': 'image_text', 'value': {'literal': literal, 'appearance': 'Test'}}))

    def test_moss_layout_and_invalid_coordinates(self):
        for valid in (True, False):
            state = approved(target='moss-image-layout')
            artifact = candidate(state)
            ratio = artifact['parameters']['aspect_ratio']
            artifact['parameters']['image_size'] = {key: value * 128 for key, value in ratio.items()}
            obj = {'summary': {'meta': [], 'canvas': 'single', 'caption': 'Synthetic layout, not a visual quality test'},
                   'items': [{'label': 'object', 'caption': 'Synthetic object', 'bbox': [-16, -16, 16, 16] if valid else [-999999, -16, 16, 16]}],
                   'bbox_coord_space': 'abs_centralized', 'bbox_format': 'yxyx'}
            artifact['segments'] = [{'text': json.dumps(obj), 'item_ids': [key for segment in artifact['segments'] for key in segment['item_ids']]}]
            if valid:
                self.assertEqual(flow.submit(state, artifact, review(state, artifact))['result'], 'pass')
                self.assertIn('prompt', flow.deliver(state))
            else:
                self.assertEqual(flow.submit(state, artifact, {})['result'], 'fail')

    def test_demo_target_and_real_task_not_autoreviewed(self):
        from preview_cases import authored_review, build, candidate_for
        data = build()
        state = approved(target='gpt-web')
        artifact = candidate_for(state, data['translations'])
        self.assertEqual(artifact['target'], 'gpt-web')
        self.assertEqual(flow.submit(state, artifact, authored_review(state, artifact))['result'], 'pass')
        state['masters'][-1]['master_id'] = 'real-task'
        with self.assertRaises(ContractError):
            authored_review(state, artifact)

    def test_preferences_reject_bad_types_without_saving(self):
        with tempfile.TemporaryDirectory(prefix='pa-audit-prefs-') as temp:
            store = prefs.Prefs(temp)
            good = {'name': '窗光', 'dimension': 'lighting', 'attributes': ['左侧柔窗光'], 'apply_mode': 'prefer'}
            prefs.command_add(store, good)
            before = store.path.read_bytes()
            for key, value in (('attributes', '腰细'), ('attributes', [1]), ('default_on', 'false'), ('default_on', 1), ('evidence', 'A0001'), ('source_items', 'x')):
                with self.subTest(key=key, value=value):
                    bad = {**good, key: value}
                    with self.assertRaises(ValueError):
                        prefs.command_add(store, bad)
                    self.assertEqual(store.path.read_bytes(), before)

    def test_inferred_types_and_pending_resume(self):
        with tempfile.TemporaryDirectory(prefix='pa-audit-infer-') as temp:
            store = prefs.Prefs(temp)
            prefs.command_archive_add(store, {'master': fixture(), 'prompt': 'Synthetic prompt', 'rating': '喜欢', 'target': 'image'})
            good = {'name': '窗光', 'dimension': 'lighting', 'attributes': ['左侧柔窗光'], 'apply_mode': 'prefer'}
            for update in ({'attributes': '腰细'}, {'default_on': 'false'}):
                before = store.path.read_bytes()
                with self.assertRaises(ValueError):
                    prefs.command_infer(store, {'request': 'Synthetic infer', 'basis': ['A0001'], 'candidates': [{**good, **update}]})
                self.assertEqual(store.path.read_bytes(), before)
            output = prefs.command_infer(store, {'request': 'Synthetic infer', 'basis': ['A0001'], 'candidates': [good]})
            template_id = output['templates'][0]['id']
            before = store.path.read_bytes()
            with self.assertRaises(ValueError):
                prefs.command_resume(store, template_id)
            self.assertEqual(store.path.read_bytes(), before)

    def test_knowledge_audit_does_not_claim_source_verification(self):
        result = knowledge.audit()
        self.assertEqual(result['entries'], 100)
        self.assertEqual(result['result_scope'], 'structure_only')
        self.assertEqual(result['structural_result'], 'pass')
        self.assertEqual(result['source_verification'], 'uncertain')
        self.assertEqual(len(result['source_warnings']), 43)
        env = {**os.environ, 'PYTHONIOENCODING': 'gbk'}
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/knowledge.py'), 'show', 'NOPE'], env=env, capture_output=True)
        self.assertEqual(result.returncode, 1)
        error = json.loads(result.stderr.decode('utf-8'))
        self.assertEqual(error['result'], 'fail')

    def test_disk_records_and_unconfirmed_rejection(self):
        with tempfile.TemporaryDirectory(prefix='pa-audit-store-') as temp:
            store = Store(temp)
            state = approved()
            store.create('regression', state)
            artifact = candidate(state)
            self.assertEqual(store.update('regression', lambda current: flow.submit(current, artifact, review(current, artifact)))['result'], 'pass')
            self.assertIn('prompt', flow.deliver(store.load('regression')))
            files = list((Path(temp) / 'tasks/regression/snapshots').glob('*.json'))
            self.assertGreaterEqual(len(files), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
