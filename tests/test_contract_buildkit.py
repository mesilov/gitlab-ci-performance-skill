"""The canonical BuildKit contract retains original source text with bounded evidence."""
import base64
import hashlib
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fixture_v2 import sample, AT

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/gitlab-ci-performance/scripts'
sys.path.insert(0, str(SCRIPTS))
from report_contract import validate, encoded
from report_calculate import build_report
from report_collect import collect, _cache_trace
from report_export import export_report
from report_cli import render


def current_source():
    value = sample(1)
    value['schema_version'] = '3.0.0'
    value['traces'][0]['parser_version'] = '2.0.0'
    return value


def set_raw_source(trace, raw):
    trace['source'] = {'encoding':'base64', 'raw_base64':base64.b64encode(raw).decode(),
                       'display_transform':'utf8-replacement-ansi-csi-strip-outer-cr'}
    trace.update(sha256=hashlib.sha256(raw).hexdigest(), bytes_read=len(raw),
                 line_count=len(raw.splitlines()))


def evidence_source():
    value = current_source()
    trace = value['traces'][0]
    trace.update(state='available', reason_code='parsed')
    set_raw_source(trace, (b'#0 building with default instance using docker driver\n'
                           b'#12 exporting to image\n#12 exporting layers 3s done\n'
                           b'#12 naming to example/safe-image:tag done\n'
                           b'#12 exporting manifest sha256:fixture done\n'
                           b'#12 exporting config sha256:fixture done\n'
                           b'#12 exporting attestation manifest sha256:fixture done\n#12 DONE 6s\n'))
    trace['coverage'].update(recognized_lines=8, total_lines=8, complete=True)
    timing = {'duration_seconds': 6, 'start_seconds': 0, 'end_seconds': 6,
              'origin': 'inferred', 'quality': 'inferred', 'precision_seconds': .001}
    image = {'id': 'image', 'kind': 'image', 'code': 'image_build', 'parent_id': None,
             'timing': timing, 'cached': False, 'complete': True,
             'lines': {'start': 1, 'end': 8}, 'push_coverage': 'excluded',
             'buildkit': None,
             'source_label': None,
             'identity': {'state': 'known', 'name': 'safe-image',
                          'origin': 'buildkit_naming', 'step_id': 12,
                          'lines': {'start': 4, 'end': 4},
                          'reference':'example/safe-image:tag'}}
    operation = copy.deepcopy(image)
    operation.update(id='export', kind='operation', code='export_local_unpack',
                     parent_id='image', lines={'start': 2, 'end': 8},
                     identity=None, buildkit={'step_id': 12},
                     source_label={'state':'original', 'text':'exporting to image',
                                   'origin':'buildkit_header',
                                   'lines':{'start':2, 'end':2}})
    operation['timing']['origin'] = 'buildkit_reported'
    part = copy.deepcopy(operation)
    part.update(id='layers', kind='part', parent_id='export',
                lines={'start': 3, 'end': 6},
                source_label={'state':'original', 'text':'exporting layers 3s done',
                              'origin':'buildkit_progress',
                              'lines':{'start':3, 'end':3}})
    part['timing'].update(duration_seconds=3, end_seconds=3)
    trace['evidence'] = [image, operation, part]
    return value


class BuildKitContractTests(unittest.TestCase):
    def test_current_versions_generate_render_and_export_without_mutating_input(self):
        source = evidence_source()
        original = encoded(source)
        validate(source)
        report = build_report(source, generated_at=AT)
        self.assertEqual((report['schema_version'], report['calculation_version'],
                          report['trace_parser_version']), ('3.0.0', '3.0.0', '2.0.0'))
        canonical = encoded(report)
        compact = export_report(report, attempt_ids=[1])
        self.assertEqual(compact['attempts'][0]['trace']['evidence'],
                         source['traces'][0]['evidence'])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.html'
            render(report, output)
            self.assertIn('"safe-image"', output.read_text())
        self.assertEqual(encoded(source), original)
        self.assertEqual(encoded(report), canonical)

    def test_old_source_requires_new_collection_for_calculation(self):
        for schema, parser in (('2.0.0','1.0.0'), ('2.1.0','1.1.0'), ('2.2.0','1.2.0')):
            source = current_source()
            source['schema_version'] = schema
            source['traces'][0]['parser_version'] = parser
            with self.subTest(schema=schema), self.assertRaisesRegex(ValueError, 'Unsupported schema version'):
                build_report(source)

    def test_old_reports_reject_render_and_export_without_writes(self):
        report = build_report(evidence_source(), generated_at=AT)
        for version in ('1.0.0', '1.1.0', '2.0.0', '2.1.0', '2.2.0'):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                old = copy.deepcopy(report)
                old['schema_version'] = version
                before = encoded(old)
                output = Path(directory) / 'old.html'
                with self.assertRaisesRegex(ValueError, 'Unsupported schema version'):
                    render(old, output)
                with self.assertRaisesRegex(ValueError, 'Unsupported schema version'):
                    export_report(old, attempt_ids=[1])
                self.assertFalse(output.exists())
                self.assertEqual(encoded(old), before)

    def test_current_report_rejects_incompatible_calculation_and_parser_versions(self):
        report = build_report(evidence_source(), generated_at=AT)
        for field, value in (('calculation_version', '2.0.0'), ('trace_parser_version', '1.0.0'), ('calculation_version', '2.2.0'), ('trace_parser_version', '1.2.0')):
            bad = copy.deepcopy(report)
            bad[field] = value
            with self.assertRaises(ValueError):
                validate(bad)

    def test_old_resume_and_cache_reject_before_transport(self):
        source = current_source()
        source['schema_version'] = '2.2.0'
        for key in ('resume', 'cache'):
            with self.subTest(key=key), patch('report_collect.GlabTransport') as transport:
                with self.assertRaisesRegex(ValueError, 'Unsupported schema version'):
                    collect('gitlab.example.com', 'example/service', **{key: source})
                transport.assert_not_called()

    def test_old_parser_is_never_reused(self):
        source = evidence_source()
        job = source['jobs'][0]
        trace = source['traces'][0]
        trace['parser_version'] = '1.2.0'
        self.assertIsNone(_cache_trace(job, {1: job}, {1: trace}, AT, 86400, 4194304, 50000))

    def test_current_schema_rejects_incompatible_trace_parser(self):
        source = current_source()
        source['traces'][0]['parser_version'] = '1.2.0'
        with self.assertRaises(ValueError):
            validate(source)

    def test_source_step_ids_are_bounded_and_closed(self):
        for step in (-1, 2147483648, 1.5, True):
            with self.subTest(step=step):
                source = evidence_source()
                source['traces'][0]['evidence'][1]['buildkit']['step_id'] = step
                with self.assertRaises(ValueError):
                    validate(source)
        for step in (0, 2147483647):
            source = evidence_source()
            for node in source['traces'][0]['evidence'][1:]:
                node['buildkit']['step_id'] = step
            source['traces'][0]['evidence'][0]['identity']['step_id'] = step
            raw=base64.b64decode(source['traces'][0]['source']['raw_base64']).replace(b'#12 ', f'#{step} '.encode())
            set_raw_source(source['traces'][0], raw)
            validate(source)
        source = evidence_source()
        source['traces'][0]['evidence'][1]['buildkit']['raw_header'] = 'arbitrary'
        with self.assertRaises(ValueError):
            validate(source)

    def test_part_cannot_change_or_drop_parent_source_step(self):
        for identity in ({'step_id': 13}, None):
            source = evidence_source()
            source['traces'][0]['evidence'][2]['buildkit'] = identity
            with self.assertRaisesRegex(ValueError, 'source step'):
                validate(source)

    def test_source_labels_are_closed_and_match_physical_lines(self):
        allowed = evidence_source()
        validate(allowed)
        mutations = [
            {'state':'original', 'text':'RUN echo $SECRET', 'origin':'buildkit_header',
             'lines':{'start':2, 'end':2}},
            {'state':'original', 'text':'#12 exporting to image', 'origin':'buildkit_header',
             'lines':{'start':2, 'end':2}},
            {'state':'redacted', 'text':'[stage] RUN hunter2', 'origin':'buildkit_header',
             'lines':{'start':2, 'end':2}},
            {'state':'original', 'text':'exporting to image\nsecret', 'origin':'buildkit_header',
             'lines':{'start':2, 'end':2}},
            {'state':'original', 'text':'exporting to image', 'origin':'buildkit_header',
             'lines':{'start':1, 'end':1}},
        ]
        for label in mutations:
            with self.subTest(label=label):
                source = evidence_source()
                source['traces'][0]['evidence'][1]['source_label'] = label
                with self.assertRaises(ValueError):
                    validate(source)

    def test_unavailable_source_label_has_no_invented_text_or_provenance(self):
        unavailable = {'state':'unavailable', 'text':None, 'origin':'unknown', 'lines':None}
        source = evidence_source()
        for node in source['traces'][0]['evidence'][1:]:
            node['source_label'] = copy.deepcopy(unavailable)
        validate(source)
        for field, value in (('text', 'other'), ('origin', 'buildkit_header'),
                             ('lines', {'start':2, 'end':2})):
            bad = copy.deepcopy(source)
            bad['traces'][0]['evidence'][1]['source_label'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(bad)

    def test_authored_operations_without_buildkit_source_ids_remain_valid(self):
        source = evidence_source()
        for node in source['traces'][0]['evidence'][1:]:
            node['buildkit'] = None
            node['source_label'] = {
                'state':'unavailable', 'text':None, 'origin':'unknown', 'lines':None}
        source['traces'][0]['evidence'][0]['identity'] = {
            'state': 'unknown', 'name': None, 'origin': 'unknown',
            'step_id': None, 'lines': None, 'reference': None}
        validate(source)

    def test_identity_source_step_resolves_to_direct_image_operation(self):
        for change in ('unknown_step', 'outside_operation', 'not_direct_child'):
            with self.subTest(change=change):
                source = evidence_source()
                image, operation, _ = source['traces'][0]['evidence']
                if change == 'unknown_step':
                    image['identity']['step_id'] = 13
                elif change == 'outside_operation':
                    image['identity']['lines'] = {'start': 1, 'end': 1}
                else:
                    operation['parent_id'] = None
                with self.assertRaisesRegex(ValueError, 'identity source'):
                    validate(source)

    def test_part_source_lines_stay_inside_parent_operation(self):
        source = evidence_source()
        source['traces'][0]['evidence'][2]['lines']['start'] = 1
        with self.assertRaisesRegex(ValueError, 'Part source lines'):
            validate(source)

    def test_identity_is_image_only_and_buildkit_is_operation_or_part_only(self):
        for index, field, value in ((1, 'identity', evidence_source()['traces'][0]['evidence'][0]['identity']),
                                    (0, 'buildkit', {'step_id': 12})):
            source = evidence_source()
            source['traces'][0]['evidence'][index][field] = value
            with self.assertRaises(ValueError):
                validate(source)

    def test_known_identity_preserves_literal_name_and_requires_provenance(self):
        from report_trace import parse_trace
        for name in ('UpperCase', 'a' * 200, '$ENV', 'image?token=abc'):
            with self.subTest(name=name):
                source = current_source()
                raw = f'#12 exporting to image\n#12 naming to example/{name}:tag done\n#12 DONE 1s\n'.encode()
                source['traces'] = [parse_trace(1, raw, fetched_at=AT, analyzed_at=AT)]
                validate(source)
                self.assertEqual(source['traces'][0]['evidence'][0]['identity']['name'], name)
                self.assertEqual(source['traces'][0]['evidence'][0]['identity']['reference'], f'example/{name}:tag')
        for changes in ({'origin':'unknown'}, {'step_id':None}, {'lines':None},
                        {'name':None}, {'reference':None}):
            source = evidence_source()
            source['traces'][0]['evidence'][0]['identity'].update(changes)
            with self.assertRaises(ValueError):
                validate(source)

    def test_unknown_identity_has_no_invented_provenance(self):
        source = evidence_source()
        identity = {'state': 'unknown', 'name': None, 'origin': 'unknown',
                    'step_id': None, 'lines': None, 'reference': None}
        source['traces'][0]['evidence'][0]['identity'] = identity
        validate(source)
        for field, value in (('name', 'safe-image'), ('origin', 'buildkit_naming'),
                             ('step_id', 12), ('lines', {'start': 4, 'end': 4})):
            bad = copy.deepcopy(source)
            bad['traces'][0]['evidence'][0]['identity'][field] = value
            with self.assertRaises(ValueError):
                validate(bad)

    def test_conflicting_names_remain_null_and_redacted_state_is_rejected(self):
        for state in ('conflicting',):
            source = evidence_source()
            identity = source['traces'][0]['evidence'][0]['identity']
            identity.update(state=state, name=None)
            validate(source)
            identity['name'] = 'safe-image'
            with self.assertRaises(ValueError):
                validate(source)
        source = evidence_source()
        source['traces'][0]['evidence'][0]['identity'].update(state='redacted', name=None)
        with self.assertRaises(ValueError):
            validate(source)

    def test_identity_lines_stay_within_image_source_lines(self):
        for lines in ({'start': 0, 'end': 4}, {'start': 4, 'end': 3},
                      {'start': 8, 'end': 9}):
            source = evidence_source()
            source['traces'][0]['evidence'][0]['identity']['lines'] = lines
            with self.assertRaises(ValueError):
                validate(source)


if __name__ == '__main__':
    unittest.main()
