import copy
import importlib
import sys
from pathlib import Path
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/gitlab-ci-performance/scripts'
sys.path.insert(0, str(SCRIPTS))
try:
    calc = importlib.import_module('report_calculate')
    exporter = importlib.import_module('report_export')
except ModuleNotFoundError:
    calc = exporter = None

AT = '2026-10-04T00:00:00Z'


def source(count=4):
    from fixture_v2 import sample as make_source
    s = make_source(count)
    for j in s['jobs']:
        j['duration_seconds'] = 100
        j['queued_seconds'] = 5
    return s


def node(identifier, start, end, code='export_local_unpack', parent=None, cached=False):
    return {'id': identifier, 'kind': 'operation', 'code': code, 'parent_id': parent,
            'timing': {'duration_seconds': None if cached else end-start, 'start_seconds': start,
                       'end_seconds': end, 'origin': 'buildkit_reported', 'quality': 'exact',
                       'precision_seconds': .001}, 'cached': cached, 'complete': True,
            'lines': {'start': 1, 'end': 2}, 'push_coverage': 'unknown',
            'buildkit': None, 'identity': None}


def trace(job_id, evidence):
    return {'job_id': job_id, 'state': 'available', 'reason_code': 'recognized',
            'sha256': 'a'*64, 'prefix_sha256': None, 'bytes_read': 100,
            'line_count': 10, 'parser_version': '1.1.0', 'fetched_at': AT,
            'analyzed_at': AT, 'cached': False,
            'coverage': {'recognized_lines': 10, 'total_lines': 10,
                         'truncated': False, 'complete': True}, 'evidence': evidence}


class CalculationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(calc, 'calculation and export modules must exist')

    def report(self, s, **kwargs):
        return calc.build_report(s, generated_at=AT, **kwargs)

    def test_baseline_is_independent_of_window_and_pipeline_status(self):
        s = source(45)
        latest = max(s['jobs'], key=lambda j:j['id'])
        latest['status'] = 'failed'
        latest['duration_seconds'] = 200
        s['pipelines'][0]['status'] = 'failed'
        r = self.report(s)
        typ = r['job_types'][0]
        self.assertEqual(typ['latest_attempt_id'], latest['id'])
        self.assertNotIn(s['jobs'][0]['id'], typ['baseline']['attempt_ids'])
        self.assertEqual(len(typ['baseline']['attempt_ids']), 10)
        self.assertEqual([(w['size'],w['page'],len(w['attempt_ids'])) for w in r['windows']],
                         [(32,0,32),(32,1,13),(64,0,45)])
        self.assertEqual(typ['baseline']['metrics']['total']['median_seconds'], 105)
        self.assertEqual(typ['baseline']['deltas']['total']['delta_seconds'], 100)

    def test_missing_totals_and_display_threshold_are_explicit(self):
        s = source()
        latest = max(s['jobs'],key=lambda j:j['id'])
        latest['duration_seconds'] = 300
        latest['queued_seconds'] = None
        r = self.report(s)
        self.assertIsNone(next(a for a in r['attempts'] if a['id']==latest['id'])['timing']['total']['value_seconds'])
        self.assertEqual(r['windows'][0]['display_unit'],'seconds')
        latest['duration_seconds'] = 300.001
        self.assertEqual(self.report(s)['windows'][0]['display_unit'],'minutes')

    def test_same_ref_and_explicit_cross_ref_are_separate(self):
        s = source()
        latest = max(s['jobs'],key=lambda j:j['id'])
        latest['ref'] = 'dev'
        next(p for p in s['pipelines'] if p['id']==latest['pipeline_id'])['ref']='dev'
        r = self.report(s)
        self.assertEqual(r['windows'][0]['attempt_ids'],[latest['id']])
        with self.assertRaisesRegex(ValueError,'refs'):
            self.report(s,comparison_mode='cross_ref')
        cross = self.report(s,comparison_mode='cross_ref',refs=['main','dev'])
        self.assertEqual(len(cross['windows'][0]['attempt_ids']),4)
        self.assertTrue(cross['job_types'][0]['baseline']['deltas']['total']['classification'].startswith('exploratory'))

    def test_interval_union_excludes_failed_cached_and_child_double_count(self):
        s = source()
        for j in s['jobs']:
            s['traces'] = [t for t in s['traces'] if t['job_id'] != j['id']]
            s['traces'].append(trace(j['id'], [node(f"{j['id']}-parent",0,10),
                node(f"{j['id']}-child",2,8,parent=f"{j['id']}-parent"),
                node(f"{j['id']}-overlap",8,15),node(f"{j['id']}-cached",15,100,cached=True)]))
        s['jobs'][0]['status']='failed'
        r = self.report(s)
        cat = next(c for c in r['windows'][0]['findings']['categories'] if c['code']=='export_local_unpack')
        self.assertEqual(cat['median_seconds'],15)
        self.assertEqual(cat['known'],3)
        self.assertEqual(cat['samples'][0]['intervals'],[[0,15]])
        self.assertNotEqual(cat['representative']['duration_seconds'],cat['median_seconds'])

    def test_queue_spike_and_stable_id_language_identity(self):
        s = source(5)
        max(s['jobs'],key=lambda j:j['id'])['queued_seconds']=60
        en = self.report(s)
        ru = self.report(s,language='ru')
        self.assertEqual(en['windows'][0]['findings']['queue_spike']['state'],'spike')
        self.assertEqual(en['report_id'],ru['report_id'])
        self.assertEqual(en['windows'],ru['windows'])
        later = calc.build_report(s,generated_at='2026-10-05T00:00:00Z')
        self.assertEqual(en['report_id'],later['report_id'])

    def test_baseline_only_sources_and_stale_metadata(self):
        s = source(40)
        s['retained_job_ids'] = sorted(s['retained_job_ids'],reverse=True)[:2]
        s['baseline_job_ids'] = [j['id'] for j in s['jobs'] if j['id'] not in s['retained_job_ids']][:10]
        s['traces'] = [t for t in s['traces'] if t['job_id'] in s['retained_job_ids']]
        s['jobs'][0]['metadata_fresh'] = False
        s['jobs'][0]['metadata_error'] = 'transport_error'
        r = self.report(s)
        self.assertEqual(len(r['windows'][0]['attempt_ids']),2)
        self.assertEqual(len(r['job_types'][0]['baseline']['attempt_ids']),10)
        baseline_ids = set(r['job_types'][0]['baseline']['attempt_ids'])-set(s['retained_job_ids'])
        self.assertTrue(all(a['trace'] is None for a in r['attempts'] if a['id'] in baseline_ids))

    def test_reported_duration_without_offsets_has_unknown_category_cost(self):
        s = source()
        for j in s['jobs']:
            evidence = node(str(j['id']),0,50)
            evidence['timing'].update(start_seconds=None,end_seconds=None)
            s['traces'] = [t for t in s['traces'] if t['job_id'] != j['id']]
            s['traces'].append(trace(j['id'],[evidence]))
        r = self.report(s)
        category = r['windows'][0]['findings']['categories'][0]
        self.assertIsNone(category['median_seconds'])
        self.assertEqual((category['known'],category['missing']),(0,4))
        self.assertEqual(r['windows'][0]['findings']['priority_codes'],['queue'])

    def test_stale_pipeline_and_failed_pipeline_have_descriptive_only_statistics(self):
        s = source()
        s['pipelines'][1]['status']='failed'
        s['pipelines'][2].update(metadata_fresh=False,metadata_error='transport_error')
        r = self.report(s)
        w = r['windows'][0]
        self.assertEqual(len(w['descriptive']['attempt_ids']),4)
        self.assertEqual(len(w['inferential']['attempt_ids']),2)
        self.assertEqual(r['job_types'][0]['baseline']['metrics']['total']['known'],1)
        self.assertFalse(r['job_types'][0]['baseline']['complete'])

    def test_cross_ref_requires_a_list_not_a_string(self):
        with self.assertRaisesRegex(ValueError,'refs'):
            self.report(source(),comparison_mode='cross_ref',refs='main')

    def test_empty_history_and_source_mutation_are_safe(self):
        s = source(0)
        before = copy.deepcopy(s)
        r = self.report(s)
        self.assertEqual(r['selection'],{'job_type_id':None,'reason_code':'insufficient_data'})
        self.assertEqual(r['windows'],[])
        self.assertEqual(s,before)
        self.assertEqual(exporter.export_report(r)['attempts'],[])

    def test_queue_zero_median_and_exact_thresholds(self):
        s = source(5)
        for j in s['jobs']:j['queued_seconds']=0
        latest=s['jobs'][0]
        latest['queued_seconds']=30
        self.assertEqual(self.report(s)['windows'][0]['findings']['queue_spike']['state'],'normal')
        latest['queued_seconds']=30.001
        self.assertEqual(self.report(s)['windows'][0]['findings']['queue_spike']['state'],'spike')

    def test_guidance_provenance_preserves_unverified_states(self):
        record={'url':'https://docs.docker.com/build/cache/', 'page_title':'Build cache',
                'section_title':'Cache', 'verified_at':None,'status':'unverified',
                'applicable_versions':[],'configuration_constraints':[]}
        r=self.report(source(),guidance={'categories':{'export_local_unpack':[record]}})
        finding=r['windows'][0]['findings']['categories'][0]['finding']
        self.assertEqual(finding['guidance'],[record])
        self.assertIsNone(finding['estimated_savings_seconds'])
        record['status']='verified'
        with self.assertRaisesRegex(ValueError,'verification date'):
            self.report(source(),guidance={'categories':{'export_local_unpack':[record]}})
        record.update(status='unverified',url='https://example.com/arbitrary')
        with self.assertRaisesRegex(ValueError,'official'):
            self.report(source(),guidance={'categories':{'export_local_unpack':[record]}})

    def test_overview_external_trace_references_preserve_numeric_evidence(self):
        s=source()
        for t in s['traces']:
            t.update(trace(t['job_id'],[node(str(t['job_id']),0,10)]))
        report=self.report(s)
        self.assertEqual(report['coverage']['source'],s['source'])
        category=report['windows'][0]['findings']['categories'][0]
        self.assertTrue(category['id'].startswith('finding-'))
        compact=exporter.export_report(report)
        self.assertEqual(compact['windows'],report['windows'])
        self.assertEqual(compact['envelope']['coverage'],report['coverage'])
        self.assertTrue(all(a['trace'] is None for a in compact['attempts']))
        external={(ref['collection'],ref['id']) for ref in compact['external_references']}
        self.assertTrue(all(('traces',str(a['id'])) in external for a in report['attempts']))

    def test_external_baseline_overlaps_use_current_metadata_and_exclude_latest(self):
        s=source(5)
        b=copy.deepcopy(s)
        s['pipelines'][1]['status']='failed'
        r=self.report(s,baseline=b)
        ids=r['job_types'][0]['baseline']['attempt_ids']
        self.assertNotIn(s['jobs'][0]['id'],ids)
        self.assertNotIn(s['jobs'][1]['id'],ids)
        self.assertEqual(len(ids),3)
        b['collected_at']='2026-10-05T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'newer'):
            self.report(s,baseline=b)
        b=copy.deepcopy(s)
        b['project']['id']=99
        b['source']['observed_counts'][0]['type_id']=calc.type_id(b['project'],'build','build')
        with self.assertRaisesRegex(ValueError,'different host/project'):
            self.report(s,baseline=b)

    def test_highlight_uses_positive_absolute_growth_before_longest_total(self):
        s=source()
        for j in s['jobs']:j['duration_seconds']=10
        s['jobs'][0]['duration_seconds']=100
        jobs=copy.deepcopy(s['jobs'])
        pipes=copy.deepcopy(s['pipelines'])
        traces=copy.deepcopy(s['traces'])
        for j in jobs:
            j.update(id=j['id']+100,pipeline_id=j['pipeline_id']+100,name='long-build',duration_seconds=1000)
        jobs[0]['duration_seconds']=1050
        for p in pipes:p['id']+=100
        for t in traces:t['job_id']+=100
        s['jobs']=sorted(s['jobs']+jobs,key=lambda j:j['id'],reverse=True)
        s['pipelines']+=pipes
        s['traces']+=traces
        s['retained_job_ids']=sorted([j['id'] for j in s['jobs']],reverse=True)
        s['source']['anchor_max_job_id']=104
        tid=calc.type_id(s['project'],'build','long-build')
        s['source']['observed_counts'].append({'type_id':tid,'stage':'build','name':'long-build',
                                             'available_count':4,'count_kind':'exact'})
        r=self.report(s)
        short=next(t for t in r['job_types'] if t['name']=='build')
        self.assertEqual(r['selection'],{'job_type_id':short['id'],'reason_code':'largest_positive_total_growth'})
        for j in s['jobs']:
            if j['name']=='build':j['duration_seconds']=100
            else:j['duration_seconds']=1050
        r=self.report(s)
        self.assertEqual(r['selection']['job_type_id'],tid)
        self.assertEqual(r['selection']['reason_code'],'longest_known_total')
        for j in s['jobs']:j['duration_seconds']=100
        r=self.report(s)
        self.assertEqual(r['selection']['job_type_id'],min(t['id'] for t in r['job_types']))

    def test_timestamped_parser_output_drives_build_category_costs(self):
        from report_trace import parse_trace
        raw=(
            '2026-10-04T00:00:00.000Z #0 building with "safe" instance using docker driver\n'
            '2026-10-04T00:00:01.000Z #1 [internal] load metadata for safe/image\n'
            '2026-10-04T00:00:04.000Z #1 DONE 3.0s\n'
            '2026-10-04T00:00:04.000Z #2 [build 1/4] COPY app .\n'
            '2026-10-04T00:00:06.000Z #3 [build 2/4] COPY config .\n'
            '2026-10-04T00:00:08.000Z #2 DONE 4.0s\n'
            '2026-10-04T00:00:10.000Z #3 DONE 4.0s\n'
            '2026-10-04T00:00:10.000Z #4 exporting to docker image\n'
            '2026-10-04T00:00:15.000Z #4 unpacking to safe/image 2.0s done\n'
            '2026-10-04T00:00:15.000Z #4 DONE 5.0s\n'
            '2026-10-04T00:00:17.000Z #5 [build 3/4] RUN install dependencies\n'
            '2026-10-04T00:00:20.000Z #5 DONE 3.0s\n').encode()
        s=source()
        s['traces']=[parse_trace(j['id'],raw,fetched_at=AT,analyzed_at=AT) for j in s['jobs']]
        r=self.report(s)
        categories={c['code']:c for c in r['windows'][0]['findings']['categories']}
        self.assertEqual(r['policies'].get('timing_evidence_policy'),
                         'reported-duration-with-inferred-positions-allowed')
        self.assertEqual(categories['context_application_copy']['median_seconds'],6.0)
        self.assertEqual(categories['export_local_unpack']['median_seconds'],5.0)
        self.assertEqual(categories['base_image']['median_seconds'],3.0)
        self.assertEqual(categories['dependencies_builder_setup']['median_seconds'],3.0)
        self.assertIsNone(categories['runner_phase']['median_seconds'])
        self.assertIn('inferred_position',categories['export_local_unpack']['finding']['uncertainty'])
        sample=categories['export_local_unpack']['samples'][0]
        self.assertEqual(sample['intervals'],[[10.0,15.0]])
        self.assertEqual(len(sample['interval_ids']),1)
        compact=exporter.export_report(r,window_id=r['windows'][0]['id'])
        self.assertEqual(compact['windows'][0]['findings'],r['windows'][0]['findings'])

    def test_queue_representative_and_investigation_directions_are_specific(self):
        r=self.report(source())
        categories=r['windows'][0]['findings']['categories']
        queue=next(c for c in categories if c['code']=='queue')
        self.assertIsNotNone(queue['representative'])
        self.assertEqual(queue['representative']['attempt_id'],1)
        self.assertIsNone(queue['representative']['evidence_id'])
        self.assertIsNone(queue['representative']['lines'])
        self.assertEqual(queue['representative']['duration_seconds'],5)
        self.assertEqual(len({c['finding']['proposed_action'] for c in categories}),6)
        self.assertEqual(len({c['finding']['applicability'] for c in categories}),6)
        self.assertTrue(all('unknown' in c['finding']['causal_hypothesis'] for c in categories))
        self.assertTrue(all(c['finding']['estimated_savings_seconds'] is None for c in categories))

    def test_older_window_queue_uses_its_own_latest_anchor(self):
        s=source(45)
        s['jobs'][0]['queued_seconds']=100
        next(j for j in s['jobs'] if j['id']==13)['queued_seconds']=7
        r=self.report(s)
        older=r['windows'][1]
        self.assertEqual(older['anchor_attempt_id'],13)
        self.assertEqual(older['findings']['queue_spike']['latest_seconds'],7)
        self.assertEqual(older['findings']['queue_spike']['state'],'normal')

    def test_compact_preserves_results_and_closes_window_references(self):
        r = self.report(source(40))
        window = r['windows'][0]
        c = exporter.export_report(r,job_type=r['job_types'][0]['id'],window_id=window['id'])
        self.assertEqual(c['windows'],[window])
        self.assertTrue(set(window['attempt_ids']).issubset({a['id'] for a in c['attempts']}))
        self.assertEqual(c['canonical_report_id'],r['report_id'])
        self.assertEqual(exporter.export_report(r),exporter.export_report(r,scope='overview'))
        for kwargs in ({'attempt_ids':[999999]}, {'window_id':'unknown'},
                       {'attempt_ids':[1],'scope':'overview'}, {'job_type':'unknown'}):
            with self.assertRaises(ValueError):exporter.export_report(r,**kwargs)

if __name__ == '__main__':
    unittest.main()
