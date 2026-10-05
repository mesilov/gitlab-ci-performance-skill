import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


PATH = Path(__file__).resolve().parents[1] / 'skills/gitlab-ci-performance/scripts/report_trace.py'
parser = None
if PATH.exists():
    spec = importlib.util.spec_from_file_location('report_trace', PATH)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)

CONTRACT = PATH.with_name('report_contract.py')
contract = None
if CONTRACT.exists():
    spec = importlib.util.spec_from_file_location('report_contract', CONTRACT)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)

AT = '2026-10-04T00:00:00Z'
TRACE_KEYS = {'job_id', 'state', 'reason_code', 'sha256', 'prefix_sha256', 'bytes_read',
              'line_count', 'parser_version', 'fetched_at', 'analyzed_at', 'cached',
              'coverage', 'evidence'}
NODE_KEYS = {'id', 'kind', 'code', 'parent_id', 'timing', 'cached', 'complete', 'lines',
             'push_coverage', 'buildkit', 'identity', 'source_label'}


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(parser, 'safe trace parser must exist')

    def parse(self, text, **kwargs):
        result = parser.parse_trace(42, text.encode(), fetched_at=AT, analyzed_at=AT, **kwargs)
        if contract:
            contract.validate(result, kind='trace')
        return result

    def test_empty_and_unavailable_have_distinct_provenance(self):
        empty = self.parse('')
        self.assertEqual(empty['state'], 'empty')
        self.assertEqual(empty['sha256'], hashlib.sha256(b'').hexdigest())
        self.assertEqual(empty['coverage'], {'recognized_lines': 0, 'total_lines': 0,
                                             'truncated': False, 'complete': True})
        unavailable = parser.empty_trace(42, 'unavailable', 'transport_error', AT)
        self.assertIsNone(unavailable['sha256'])
        self.assertFalse(unavailable['coverage']['complete'])
        self.assertEqual(set(unavailable), TRACE_KEYS)

    def test_unsupported_preserves_bytes_hash_and_physical_line_count(self):
        result = self.parse('password=top-secret\nplain output\n')
        self.assertEqual(result['state'], 'unsupported')
        self.assertEqual(result['line_count'], 2)
        self.assertEqual(result['bytes_read'], len(b'password=top-secret\nplain output\n'))
        self.assertEqual(result['evidence'], [])
        self.assertEqual(result['coverage']['recognized_lines'], 0)

    def test_section_markers_are_allowlisted_with_whole_second_precision(self):
        result = self.parse('\x1b[0Ksection_start:100:prepare_executor[collapsed=true]\r\x1b[0Ksecret runner\n'
                            'section_end:104:prepare_executor\r\n'
                            'section_start:105:secret_CUSTOM\r\n'
                            'section_end:109:secret_CUSTOM\r\n')
        self.assertEqual(result['state'], 'available')
        self.assertEqual([n['code'] for n in result['evidence']], ['prepare_executor', 'unknown_phase'])
        first = result['evidence'][0]
        self.assertEqual(first['timing'], {'duration_seconds': 4.0, 'start_seconds': 0.0,
                         'end_seconds': 4.0, 'origin': 'section', 'quality': 'exact', 'precision_seconds': 1.0})
        self.assertEqual(first['lines'], {'start': 1, 'end': 2})
        self.assertNotIn('secret', json.dumps(result))

    def test_missing_section_end_is_partial_and_never_fabricates_duration(self):
        result = self.parse('section_start:100:step_script\r\nsecret\n')
        node = result['evidence'][0]
        self.assertEqual(result['state'], 'partial')
        self.assertFalse(node['complete'])
        self.assertIsNone(node['timing']['duration_seconds'])
        self.assertEqual(node['timing']['quality'], 'partial')

    def test_reversed_section_has_unknown_timing(self):
        result = self.parse('section_start:100:step_script\r\nsection_end:99:step_script\r\n')
        timing = result['evidence'][0]['timing']
        self.assertIsNone(timing['duration_seconds'])
        self.assertIsNone(timing['end_seconds'])
        self.assertFalse(result['evidence'][0]['complete'])

    def test_timestamped_commands_use_safe_labels_and_intervals(self):
        result = self.parse('2026-10-04T00:00:00.100Z $ echo SECRET_ARG token=xyz\n'
                            '2026-10-04T00:00:02.250Z SECRET_OUTPUT\n'
                            '2026-10-04T00:00:03.500Z $ env SECRET_ENV=xxx command\n'
                            '2026-10-04T00:00:04.750Z done\n')
        commands = result['evidence']
        self.assertEqual([n['code'] for n in commands], ['script_command', 'script_command'])
        self.assertEqual(commands[0]['timing']['duration_seconds'], 3.4)
        self.assertEqual(commands[0]['timing']['origin'], 'log_interval')
        self.assertEqual(commands[1]['timing']['duration_seconds'], 1.25)
        self.assertFalse(commands[1]['complete'])
        self.assertEqual(commands[1]['timing']['quality'], 'partial')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_buildkit_frames_deduplicate_and_export_parts_are_nested(self):
        result = self.parse('#0 building with "SECRET-builder" instance using docker driver\n'
                            '#1 [internal] load build definition from SECRET-Dockerfile\n'
                            '#1 DONE 0.1s\n'
                            '#2 [build 1/2] RUN apt-get install SECRET-package\n'
                            '#2 DONE 2.4s\n'
                            '#2 DONE 2.4s\n'
                            '#3 exporting to docker image\n'
                            '#3 exporting layers 1.2s done\n'
                            '#3 unpacking to SECRET-registry/image:latest 0.5s done\n'
                            '#3 DONE 2.0s\n')
        nodes = result['evidence']
        images = [n for n in nodes if n['kind'] == 'image']
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]['push_coverage'], 'excluded')
        operations = [n for n in nodes if n['kind'] == 'operation']
        self.assertEqual(len(operations), 3)
        self.assertEqual(operations[1]['timing']['duration_seconds'], 2.4)
        export = operations[2]
        self.assertEqual(export['code'], 'export_local_unpack')
        parts = [n for n in nodes if n['kind'] == 'part']
        self.assertEqual(len(parts), 2)
        self.assertTrue(all(n['parent_id'] == export['id'] for n in parts))
        self.assertEqual([n['timing']['duration_seconds'] for n in parts], [1.2, 0.5])
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertTrue(all(set(n) == NODE_KEYS for n in nodes))

    def test_export_manifest_and_config_stay_in_one_build(self):
        result = self.parse('#0 building with "default" instance using docker driver\n'
                            '#1 [stage-0 1/1] FROM example\n#1 DONE 1.0s\n'
                            '#2 exporting to image\n#2 exporting layers 2.0s done\n'
                            '#2 exporting manifest sha256:example done\n'
                            '#2 exporting config sha256:example done\n'
                            '#2 naming to example/service:tag done\n'
                            '#2 unpacking to example/service:tag 1.0s done\n'
                            '#2 DONE 3.0s\n')
        images = [n for n in result['evidence'] if n['kind'] == 'image']
        self.assertEqual(len(images), 1)
        operations = [n for n in result['evidence'] if n['kind'] == 'operation']
        self.assertEqual(len(operations), 2)
        export = operations[1]
        self.assertEqual(export['lines'], {'start': 4, 'end': 10})
        self.assertEqual(export['timing']['duration_seconds'], 3.0)

    def test_original_buildkit_operation_titles_are_preserved_separately_from_category(self):
        result = self.parse('#0 building with "default" instance using docker driver\n'
                            '#1 [internal] load build definition from Dockerfile\n#1 DONE 0.1s\n'
                            '#8 [internal] load build context\n#8 DONE 2.0s\n'
                            '#16 exporting to image\n#16 DONE 3.0s\n')
        operations = {n['buildkit']['step_id']:n for n in result['evidence']
                      if n['kind']=='operation'}
        expected = {
            1: ('other_operation', '[internal] load build definition from Dockerfile', 2),
            8: ('context_application_copy', '[internal] load build context', 4),
            16: ('export_local_unpack', 'exporting to image', 6),
        }
        for step, (code, title, line) in expected.items():
            with self.subTest(step=step):
                self.assertEqual(operations[step]['code'], code)
                self.assertEqual(operations[step]['source_label'], {
                    'state':'original', 'text':title, 'origin':'buildkit_header',
                    'lines':{'start':line, 'end':line}})

    def test_export_suboperation_titles_are_preserved_without_destination_or_duration(self):
        result = self.parse('#16 exporting to image\n'
                            '#16 exporting layers 2.0s done\n'
                            '#16 unpacking to registry.example/group/service:tag 1.0s done\n'
                            '#16 DONE 3.0s\n')
        parts = [n for n in result['evidence'] if n['kind']=='part']
        self.assertEqual([n['source_label'] for n in parts], [
            {'state':'original', 'text':'exporting layers', 'origin':'buildkit_progress',
             'lines':{'start':2, 'end':2}},
            {'state':'redacted', 'text':'unpacking to [redacted]', 'origin':'buildkit_progress',
             'lines':{'start':3, 'end':3}},
        ])

    def test_same_category_keeps_distinct_safe_titles(self):
        result = self.parse('#1 [internal] load build context\n#1 DONE 1s\n'
                            '#2 [stage 1/2] COPY private.pem /app/private.pem\n#2 DONE 1s\n')
        operations = [n for n in result['evidence'] if n['kind']=='operation']
        self.assertEqual([n['code'] for n in operations],
                         ['context_application_copy', 'context_application_copy'])
        self.assertEqual([n['source_label']['text'] for n in operations],
                         ['[internal] load build context', '[stage 1/2] COPY [redacted]'])
        self.assertEqual(operations[1]['source_label']['state'], 'redacted')
        self.assertNotIn('private.pem', json.dumps(result))

    def test_titles_survive_ansi_timestamps_redraws_and_reused_step_ids(self):
        first = ('2026-10-04T00:00:00Z 00O \x1b[32m#0 building with "default" instance using docker driver\x1b[0m\n'
                 '2026-10-04T00:00:01Z 00O \x1b[32m#8 [internal] load build context\x1b[0m\n'
                 '2026-10-04T00:00:02Z 00O #8 DONE 1s\n'
                 '2026-10-04T00:00:03Z 00O #8 [internal] load build context\n')
        second = ('2026-10-04T00:00:04Z 00O #0 building with "default" instance using docker driver\n'
                  '2026-10-04T00:00:05Z 00O #8 exporting to image\n'
                  '2026-10-04T00:00:06Z 00O #8 DONE 1s\n')
        result = self.parse(first + second)
        operations = [n for n in result['evidence'] if n['kind']=='operation']
        self.assertEqual([n['source_label']['text'] for n in operations],
                         ['[internal] load build context', 'exporting to image'])
        self.assertEqual(operations[0]['source_label']['lines'], {'start':2, 'end':2})

    def test_operation_titles_never_export_arguments_markup_or_overlong_text(self):
        secret = 'PRIVATE_TOKEN=hunter2'
        result = self.parse(f'#1 [secret-stage 1/2] RUN <img src=x onerror=alert(1)> {secret}\n'
                            '#1 DONE 1s\n'
                            '#2 [internal] ' + ('x' * 200) + '\n#2 DONE 1s\n')
        operations = [n for n in result['evidence'] if n['kind']=='operation']
        self.assertEqual(operations[0]['source_label'], {
            'state':'redacted', 'text':'[stage 1/2] RUN [redacted]',
            'origin':'buildkit_header', 'lines':{'start':1, 'end':1}})
        self.assertEqual(operations[1]['source_label'], {
            'state':'unavailable', 'text':None, 'origin':'unknown', 'lines':None})
        payload = json.dumps(result)
        for unsafe in (secret, '<img', 'secret-stage', 'x' * 129):
            self.assertNotIn(unsafe, payload)

    def test_identity_and_source_step_ids_have_physical_provenance(self):
        result = self.parse('#0 building with "default" instance using docker driver\n'
                            '#16 exporting to image\n#16 exporting manifest sha256:example done\n'
                            '#16 naming to registry.example:5000/group/service:tag done\n'
                            '#16 unpacking to registry.example:5000/group/service:tag 1s done\n#16 DONE 3s\n')
        image = result['evidence'][0]
        self.assertEqual(image['identity'], {'state':'known','name':'service','origin':'buildkit_naming',
                                           'step_id':16,'lines':{'start':4,'end':4}})
        self.assertTrue(all(n['buildkit']=={'step_id':16} for n in result['evidence'][1:]))
        self.assertNotIn('registry.example', json.dumps(result))
        self.assertNotIn(':tag', json.dumps(result))

    def test_identical_banners_and_ids_are_new_builds_after_completion(self):
        build = ('#0 building with "default" instance using docker driver\n'
                 '#1 [1/1] COPY app /app\n#1 CACHED\n#2 exporting to image\n'
                 '#2 naming to example/service:tag done\n#2 DONE 1s\n')
        result = self.parse(build + build)
        images = [n for n in result['evidence'] if n['kind']=='image']
        self.assertEqual(len(images), 2)
        self.assertEqual([n['identity']['name'] for n in images], ['service','service'])
        self.assertEqual(result['state'], 'available')

    def test_digest_extraction_progress_updates_cumulative_from_duration(self):
        digest = 'a'*64
        result = self.parse('#1 [1/1] FROM example/base\n#1 DONE 2s\n'
                            f'#1 [1/1] FROM example/base\n#1 extracting sha256:{digest} 3.0s done\n'
                            '#1 DONE 5s\n#1 DONE 5s\n')
        ops = [n for n in result['evidence'] if n['kind']=='operation']
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]['timing']['duration_seconds'], 5)
        self.assertEqual(result['state'], 'available')

    def test_conflicting_done_without_supported_progress_remains_partial(self):
        result = self.parse('#1 [1/1] RUN arbitrary\n#1 DONE 2s\n#1 DONE 5s\n')
        self.assertEqual(result['state'], 'partial')

    def test_unknown_conflicting_and_sensitive_identities_are_not_invented(self):
        unknown=self.parse('#1 [1/1] FROM example/base\n#1 DONE 1s\n')['evidence'][0]
        self.assertEqual(unknown['identity']['state'], 'unknown')
        self.assertIsNone(unknown['identity']['name'])
        conflict=self.parse('#2 exporting to image\n#2 naming to example/one:tag done\n'
                            '#2 naming to example/two:tag done\n#2 DONE 1s\n')['evidence'][0]
        self.assertEqual(conflict['identity']['state'], 'conflicting')
        self.assertIsNone(conflict['identity']['name'])
        for target in ['https://user:password@example/image', 'user:password@example/image',
                       'example/$ENV/image', 'example/image?token=abc', 'SECRET-registry/image:latest',
                       'example/access_token_abcdef:latest', 'example/image:SECRET_TAG']:
            with self.subTest(target=target):
                result=self.parse(f'#2 exporting to image\n#2 naming to {target} done\n#2 DONE 1s\n')
                self.assertIsNone(result['evidence'][0]['identity']['name'])
                self.assertNotIn(target, json.dumps(result))
        malformed=self.parse('#2 exporting to image\n#2 naming to example/service:tag done secret\n#2 DONE 1s\n')
        self.assertEqual(malformed['evidence'][0]['identity']['state'], 'unknown')

    def test_conflicting_export_steps_retain_resolvable_first_provenance(self):
        result=self.parse('#1 exporting to image\n#1 naming to example/one:tag done\n#1 DONE 1s\n'
                          '#2 exporting to image\n#2 naming to example/two:tag done\n#2 DONE 1s\n')
        identity=result['evidence'][0]['identity']
        self.assertEqual(identity['state'],'conflicting')
        self.assertIsNone(identity['name'])
        self.assertEqual(identity['step_id'],1)
        self.assertEqual(identity['lines'],{'start':2,'end':2})

    def test_failed_canceled_and_partial_sessions_remain_distinct(self):
        result=self.parse('#0 building with "default" instance using docker driver\n'
                          '#1 [1/1] RUN command\n#1 ERROR: private output\n'
                          '#0 building with "default" instance using docker driver\n'
                          '#1 [1/1] RUN command\n#1 CANCELED\n')
        self.assertEqual(len([n for n in result['evidence'] if n['kind']=='image']), 2)
        self.assertEqual(result['state'], 'partial')
        self.assertNotIn('private', json.dumps(result))

    def test_limit_still_processes_closures_and_identity_of_admitted_nodes(self):
        from unittest.mock import patch
        with patch.object(parser,'MAX_EVIDENCE_NODES',2):
            full=self.parse('#16 exporting to image\n#16 naming to example/service:tag done\n#16 DONE 3s\n')
            limited=self.parse('#16 exporting to image\n#16 exporting layers 2s done\n'
                               '#16 naming to example/service:tag done\n#16 DONE 3s\n')
        self.assertEqual(full['state'], 'available')
        self.assertEqual(limited['reason_code'], 'evidence_limit')
        self.assertTrue(limited['evidence'][1]['complete'])
        self.assertEqual(limited['evidence'][0]['identity']['name'], 'service')

    def test_repeated_step_ids_are_scoped_to_explicit_sessions(self):
        result = self.parse('#0 building with "one" instance using docker driver\n#1 [1/1] RUN secret\n#1 DONE 2s\n'
                            '#0 building with "two" instance using docker driver\n#1 [1/1] RUN secret2\n#1 DONE 5s\n')
        operations = [n for n in result['evidence'] if n['kind'] == 'operation']
        self.assertEqual(len(operations), 2)
        self.assertNotEqual(operations[0]['parent_id'], operations[1]['parent_id'])
        self.assertNotEqual(operations[0]['id'], operations[1]['id'])

    def test_cached_is_not_a_measured_zero(self):
        result = self.parse('#1 [build 1/1] COPY SECRET .\n#1 CACHED\n')
        operation = next(n for n in result['evidence'] if n['kind'] == 'operation')
        self.assertTrue(operation['cached'])
        self.assertTrue(operation['complete'])
        self.assertIsNone(operation['timing']['duration_seconds'])
        self.assertEqual(operation['code'], 'context_application_copy')

    def test_partial_build_and_truncated_prefix_hash(self):
        raw = '#1 [build 1/1] RUN SECRET\n#1 2.3 SECRET_OUTPUT\n'
        result = self.parse(raw, truncated=True)
        self.assertEqual(result['state'], 'partial')
        self.assertIsNone(result['sha256'])
        self.assertEqual(result['prefix_sha256'], hashlib.sha256(raw.encode()).hexdigest())
        self.assertFalse(result['coverage']['complete'])
        operation = next(n for n in result['evidence'] if n['kind'] == 'operation')
        self.assertFalse(operation['complete'])
        self.assertIsNone(operation['timing']['duration_seconds'])

    def test_buildkit_reported_durations_leave_missing_offsets_unknown(self):
        result = self.parse('#1 [internal] load metadata for secret/image\n#1 DONE 4.7s\n')
        node = next(n for n in result['evidence'] if n['kind'] == 'operation')
        self.assertEqual(node['code'], 'base_image')
        self.assertEqual(node['timing']['duration_seconds'], 4.7)
        self.assertIsNone(node['timing']['start_seconds'])
        self.assertIsNone(node['timing']['end_seconds'])
        self.assertEqual(node['timing']['origin'], 'buildkit_reported')

    def test_push_coverage_is_conservative(self):
        result = self.parse('#1 exporting to image\n#1 pushing layers 2.0s done\n#1 DONE 3s\n')
        self.assertEqual(result['evidence'][0]['push_coverage'], 'included')
        unknown = self.parse('#1 [1/1] RUN secret\n#1 DONE 3s\n')
        self.assertEqual(unknown['evidence'][0]['push_coverage'], 'unknown')

    def test_repeated_session_banner_does_not_duplicate_an_active_image(self):
        result = self.parse('#0 building with "secret" instance using docker driver\n'
                            '#1 [1/1] RUN secret\n'
                            '#0 building with "secret" instance using docker driver\n'
                            '#1 [1/1] RUN secret\n#1 DONE 3s\n')
        self.assertEqual(len([n for n in result['evidence'] if n['kind'] == 'image']), 1)
        self.assertEqual(len([n for n in result['evidence'] if n['kind'] == 'operation']), 1)

    def test_banner_redraw_after_internal_step_does_not_end_build(self):
        result=self.parse('#0 building with "default" instance using docker driver\n'
                          '#1 [internal] load build definition from Dockerfile\n#1 DONE 0.1s\n'
                          '#0 building with "default" instance using docker driver\n'
                          '#2 [1/1] FROM example/base\n#2 DONE 1s\n'
                          '#3 exporting to image\n#3 naming to example/service:tag done\n#3 DONE 2s\n')
        self.assertEqual(len([n for n in result['evidence'] if n['kind']=='image']),1)
        self.assertEqual(result['state'],'available')

    def test_banner_after_export_with_other_active_work_is_still_a_redraw(self):
        result=self.parse('#0 building with "default" instance using docker driver\n'
                          '#1 [1/1] RUN command\n#2 exporting to image\n#2 DONE 2s\n'
                          '#0 building with "default" instance using docker driver\n#1 DONE 3s\n')
        self.assertEqual(len([n for n in result['evidence'] if n['kind']=='image']),1)

    def test_timestamped_image_span_is_inferred_without_summing_parallel_steps(self):
        result = self.parse('2026-10-04T00:00:00.000Z 00O #0 building with "secret" instance using docker driver\n'
                            '2026-10-04T00:00:00.100Z 00O #1 [1/1] RUN secret\n'
                            '2026-10-04T00:00:00.200Z 00O #2 [1/1] RUN secret\n'
                            '2026-10-04T00:00:02.100Z 00O #1 DONE 2.0s\n'
                            '2026-10-04T00:00:02.200Z 00O #2 DONE 2.0s\n')
        timing = result['evidence'][0]['timing']
        self.assertEqual(timing['duration_seconds'], 2.2)
        self.assertEqual(timing['quality'], 'inferred')
        self.assertEqual(timing['origin'], 'inferred')

    def test_ambiguous_id_reuse_is_separate_partial_evidence(self):
        result = self.parse('#1 [1/1] RUN first_secret\n#1 DONE 3s\n'
                            '#1 [1/1] RUN second_secret\n#1 DONE 4s\n')
        self.assertEqual(result['state'], 'partial')
        self.assertEqual(len([n for n in result['evidence'] if n['kind'] == 'image']), 2)
        self.assertTrue(all(n['timing']['start_seconds'] is None for n in result['evidence']))

    def test_unrepresentable_numeric_values_never_emit_infinity(self):
        huge = '9' * 400
        result = self.parse(f'#1 [1/1] RUN secret\n#1 DONE {huge}s\n')
        operation = next(n for n in result['evidence'] if n['kind'] == 'operation')
        self.assertIsNone(operation['timing']['duration_seconds'])
        json.dumps(result, allow_nan=False)

    def test_unknown_section_end_cannot_claim_supported_evidence(self):
        result = self.parse('section_end:100:secret_section\r\n')
        self.assertEqual(result['state'], 'unsupported')
        self.assertEqual(result['evidence'], [])

    def test_image_with_one_timestamp_has_no_fabricated_zero_interval(self):
        result = self.parse('2026-10-04T00:00:00Z #1 [1/1] RUN secret\n')
        self.assertIsNone(result['evidence'][0]['timing']['duration_seconds'])

    def test_large_evidence_is_bounded_without_losing_whole_source_hash(self):
        raw = ''.join(f'section_start:{100+i*2}:step_script\nsection_end:{101+i*2}:step_script\n'
                      for i in range(2000))
        result = self.parse(raw)
        self.assertLess(len(json.dumps(result, indent=2).encode()), 128 * 1024)
        self.assertEqual(result['state'], 'partial')
        self.assertEqual(result['reason_code'], 'evidence_limit')
        self.assertFalse(result['coverage']['truncated'])
        self.assertFalse(result['coverage']['complete'])
        self.assertEqual(result['sha256'], hashlib.sha256(raw.encode()).hexdigest())

    def test_timestamp_wrapper_does_not_invalidate_coarse_section_epoch(self):
        result = self.parse('1970-01-01T00:01:40.125Z 00O section_start:100:step_script\r\n'
                            '1970-01-01T00:01:42.500Z 00O section_end:102:step_script\r\n')
        self.assertEqual(result['state'], 'available')
        self.assertEqual(result['evidence'][0]['timing']['start_seconds'], 0)
        self.assertEqual(result['evidence'][0]['timing']['duration_seconds'], 2)

    def test_reported_operation_duration_infers_positions_from_done_timestamp(self):
        result = self.parse('2026-10-04T00:00:00Z #0 building with "secret" instance using docker driver\n'
                            '2026-10-04T00:00:01Z #1 [1/1] COPY secret .\n'
                            '2026-10-04T00:00:04Z #1 DONE 3.0s\n')
        timing = result['evidence'][1]['timing']
        self.assertEqual((timing['start_seconds'], timing['end_seconds']), (1, 4))
        self.assertEqual(timing['duration_seconds'], 3)
        self.assertEqual(timing['origin'], 'buildkit_reported')
        self.assertEqual(timing['quality'], 'inferred')
        self.assertEqual(timing['precision_seconds'], .1)

    def test_nested_part_positions_stay_within_completed_parent(self):
        result = self.parse('2026-10-04T00:00:00Z #0 building with "secret" instance using docker driver\n'
                            '2026-10-04T00:00:01Z #1 exporting to docker image\n'
                            '2026-10-04T00:00:03Z #1 exporting layers 2.0s done\n'
                            '2026-10-04T00:00:04Z #1 unpacking to secret 1.0s done\n'
                            '2026-10-04T00:00:04Z #1 DONE 3.0s\n')
        nodes = result['evidence']
        self.assertEqual([(n['timing']['start_seconds'], n['timing']['end_seconds'])
                          for n in nodes if n['kind']=='part'], [(1,3),(3,4)])

    def test_impossible_operation_offsets_are_unknown_without_clamping(self):
        result = self.parse('2026-10-04T00:00:00Z #1 [1/1] COPY secret .\n'
                            '2026-10-04T00:00:01Z #1 DONE 2.0s\n')
        timing = result['evidence'][1]['timing']
        self.assertIsNone(timing['start_seconds'])
        self.assertIsNone(timing['end_seconds'])
        self.assertEqual(timing['duration_seconds'], 2)

    def test_repeated_done_frames_keep_first_defensible_interval(self):
        result = self.parse('2026-10-04T00:00:00Z #1 [1/1] COPY secret .\n'
                            '2026-10-04T00:00:03Z #1 DONE 3.0s\n'
                            '2026-10-04T00:00:07Z #1 DONE 3.0s\n')
        timing = result['evidence'][1]['timing']
        self.assertEqual((timing['start_seconds'], timing['end_seconds']), (0,3))
        self.assertEqual(result['evidence'][0]['timing']['duration_seconds'], 3)

    def test_completed_export_cached_and_bare_done_redraws_keep_image_envelope(self):
        def frame(second, body):
            return f'2026-10-04T00:00:{second:02d}Z {body}\n'
        original=''.join(frame(s,b) for s,b in [
            (0,'#0 building with "default" instance using docker driver'),
            (0,'#1 [1/1] COPY app /app'),(0,'#1 CACHED'),
            (0,'#2 [1/1] RUN command'),(0,'#2 DONE'),
            (0,'#16 exporting to image'),(2,'#16 exporting layers 2s done'),
            (3,'#16 exporting manifest sha256:example done'),
            (3,'#16 naming to example/service:tag done'),
            (4,'#16 unpacking to example/service:tag 1s done'),(5,'#16 DONE 5s')])
        redraw=''.join(frame(s,b) for s,b in [
            (10,'#16 exporting layers 2s done'),(11,'#16 exporting manifest sha256:example done'),
            (11,'#16 naming to example/service:tag done'),
            (12,'#16 unpacking to example/service:tag 1s done'),(13,'#16 DONE 5s'),
            (14,'#1 CACHED'),(15,'#2 DONE')])
        result=self.parse(original+redraw)
        self.assertEqual(result['state'],'available')
        self.assertEqual(result['evidence'][0]['timing']['duration_seconds'],5)
        self.assertEqual(len([n for n in result['evidence'] if n['kind']=='image']),1)
        self.assertEqual(result['evidence'][0]['identity']['lines'],{'start':9,'end':14})

    def test_maximum_named_summary_stays_under_serialized_byte_budget(self):
        name='a'*128
        build=('#0 building with "default" instance using docker driver\n'
               '#2147483647 exporting to image\n'
               f'#2147483647 naming to example/{name}:tag done\n#2147483647 DONE 3.14159265s\n')
        result=self.parse(build*(parser.MAX_EVIDENCE_NODES//2))
        self.assertEqual(len(result['evidence']), parser.MAX_EVIDENCE_NODES)
        self.assertEqual(result['state'],'available')
        self.assertLess(len(contract.encoded(result)),128*1024)
        limited=self.parse(build*(parser.MAX_EVIDENCE_NODES//2+1))
        self.assertEqual(limited['reason_code'],'evidence_limit')
        self.assertLess(len(contract.encoded(limited)),128*1024)

    def test_part_without_known_parent_bounds_keeps_unknown_positions(self):
        result = self.parse('2026-10-04T00:00:00Z #1 exporting to docker image\n'
                            '2026-10-04T00:00:03Z #1 exporting layers 2.0s done\n'
                            '#1 DONE 3.0s\n')
        part = next(n for n in result['evidence'] if n['kind']=='part')
        self.assertIsNone(part['timing']['start_seconds'])
        self.assertIsNone(part['timing']['end_seconds'])

    def test_parser_and_calculator_produce_known_category_costs(self):
        sys.path.insert(0, str(PATH.parent))
        import report_calculate
        from fixture_v2 import sample
        source = sample(4)
        raw = ('2026-10-04T00:00:00Z #0 building with "secret" instance using docker driver\n'
               '2026-10-04T00:00:01Z #1 [1/1] COPY secret .\n'
               '2026-10-04T00:00:04Z #1 DONE 3.0s\n'
               '2026-10-04T00:00:04Z #2 exporting to docker image\n'
               '2026-10-04T00:00:06Z #2 exporting layers 2.0s done\n'
               '2026-10-04T00:00:07Z #2 DONE 3.0s\n')
        source['traces'] = [parser.parse_trace(j['id'], raw.encode(), fetched_at=AT, analyzed_at=AT)
                            for j in source['jobs']]
        report = report_calculate.build_report(source, generated_at=AT)
        categories = {c['code']:c for c in report['windows'][0]['findings']['categories']}
        self.assertEqual(categories['context_application_copy']['median_seconds'], 3)
        self.assertEqual(categories['export_local_unpack']['median_seconds'], 3)
        self.assertEqual(categories['export_local_unpack']['known'], 4)

    def test_docker_instruction_classification_never_scans_arguments(self):
        for header, expected in [('[internal] load build definition from Dockerfile','other_operation'),
                                 ('[1/1] RUN python -c "from pathlib import Path"','dependencies_builder_setup'),
                                 ('[1/1] RUN cp /cache/copy /out','dependencies_builder_setup')]:
            with self.subTest(header=header):
                result = self.parse(f'#1 {header}\n#1 DONE 3.0s\n')
                node = next(n for n in result['evidence'] if n['kind']=='operation')
                self.assertEqual(node['code'], expected)

    def test_part_outside_parent_bounds_has_unknown_positions(self):
        result = self.parse('2026-10-04T00:00:00Z #0 building with "secret" instance using docker driver\n'
                            '2026-10-04T00:00:01Z #1 exporting to docker image\n'
                            '2026-10-04T00:00:03Z #1 exporting layers 3.0s done\n'
                            '2026-10-04T00:00:04Z #1 DONE 3.0s\n')
        part = next(n for n in result['evidence'] if n['kind']=='part')
        self.assertIsNone(part['timing']['start_seconds'])
        self.assertIsNone(part['timing']['end_seconds'])
        self.assertEqual(part['timing']['duration_seconds'], 3)

    def test_inferred_operation_start_extends_buffered_image_envelope(self):
        result = self.parse('section_start:1791072000:step_script\nsection_end:1791072001:step_script\n'
                            '2026-10-04T00:00:05Z #1 [1/1] COPY secret .\n'
                            '2026-10-04T00:00:08Z #1 DONE 5.0s\n')
        image = next(n for n in result['evidence'] if n['kind']=='image')
        operation = next(n for n in result['evidence'] if n['kind']=='operation')
        self.assertEqual(operation['timing']['start_seconds'], 3)
        self.assertEqual(image['timing']['start_seconds'], 3)

    def test_cached_operation_cannot_gain_duration_from_a_repeated_done_frame(self):
        result = self.parse('2026-10-04T00:00:00Z #1 [1/1] COPY secret .\n'
                            '2026-10-04T00:00:01Z #1 CACHED\n'
                            '2026-10-04T00:00:02Z #1 DONE 0.0s\n')
        operation = next(n for n in result['evidence'] if n['kind']=='operation')
        self.assertIsNone(operation['timing']['duration_seconds'])
        self.assertTrue(operation['cached'])


if __name__ == '__main__':
    unittest.main()
