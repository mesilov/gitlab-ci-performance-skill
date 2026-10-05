import copy
import importlib
import importlib.util
import sys
from pathlib import Path
import tempfile
import unittest
from fixture_v2 import sample
SCRIPTS=Path(__file__).resolve().parents[1]/'skills/gitlab-ci-performance/scripts'
sys.path.insert(0,str(SCRIPTS))

class ContractV2Tests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('report_contract'),'v2 contract module is missing')
        self.c=importlib.import_module('report_contract')
    def test_source_and_unknown_versions(self):
        self.c.validate(sample())
        s=sample();s['schema_version']='9.0.0'
        with self.assertRaisesRegex(ValueError,'version'):self.c.validate(s)
    def test_negative_nonfinite_and_unknown_fields(self):
        for mutate in [lambda s:s['jobs'][0].update(duration_seconds=-1),lambda s:s['jobs'][0].update(duration_seconds=float('nan')),lambda s:s.update(raw_log='secret')]:
            s=sample();mutate(s)
            with self.assertRaises(ValueError):self.c.validate(s)
    def test_invalid_references_availability_and_dates(self):
        for mutate in [lambda s:s['jobs'][0].update(pipeline_id=999),lambda s:s['traces'][0].update(state='empty',bytes_read=2),lambda s:s['jobs'][0].update(finished_at='2020-01-01T00:00:00Z'),lambda s:s['jobs'][0].update(web_url='https://evil.example/job')]:
            s=sample();mutate(s)
            with self.assertRaises(ValueError):self.c.validate(s)
    def test_impossible_evidence_intervals_and_parents(self):
        s=sample();t=s['traces'][0];t.update(state='available',reason_code='parsed',sha256='a'*64,bytes_read=10,line_count=2)
        t['coverage'].update(recognized_lines=2,total_lines=2,complete=True)
        n={'id':'phase-1','kind':'phase','code':'step_script','parent_id':None,'timing':{'duration_seconds':1,'start_seconds':0,'end_seconds':1,'origin':'section','quality':'exact','precision_seconds':1},'cached':False,'complete':True,'lines':{'start':1,'end':2},'push_coverage':'unknown','buildkit':None,'identity':None}
        t['evidence']=[n];self.c.validate(s)
        for mutate in [lambda n:n['timing'].update(end_seconds=-1),lambda n:n.update(parent_id='missing'),lambda n:n['timing'].update(origin='api_execution'),lambda n:n.update(parent_id='phase-1')]:
            bad=copy.deepcopy(s);mutate(bad['traces'][0]['evidence'][0])
            with self.assertRaises(ValueError):self.c.validate(bad)
    def test_atomic_write_and_precision(self):
        s=sample();s['jobs'][0]['duration_seconds']=100.123456
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'source.json';self.c.save(p,s)
            self.assertEqual(self.c.load(p),s)
            with self.assertRaises(ValueError):self.c.save(p,s)

class DerivedIntegrityTests(unittest.TestCase):
    def setUp(self):
        from report_calculate import build_report
        import report_contract
        self.c=report_contract;self.r=build_report(sample())
    def test_rejects_aggregate_and_cohort_tampering(self):
        mutations=[lambda r:r['job_types'][0]['baseline']['metrics']['total'].update(median_seconds=99999),lambda r:r['windows'][0]['findings']['categories'][-1].update(known=99),lambda r:r['windows'][0]['findings']['categories'][-1]['samples'][0].update(value_seconds=99999),lambda r:r['attempts'][0].update(baseline_eligible=False),lambda r:r['attempts'][0]['metadata'].update(name='different'),lambda r:r['windows'][0]['findings'].update(eligible_successful_n=999),lambda r:r.update(report_id='a'*64)]
        for mutate in mutations:
            r=copy.deepcopy(self.r);mutate(r)
            with self.assertRaises(ValueError):self.c.validate(r)
    def test_rejects_incomplete_source_counts_and_bad_anchor(self):
        for mutate in [lambda s:s['source'].update(observed_counts=[]),lambda s:s['source'].update(anchor_max_job_id=1),lambda s:s['source']['budgets'].update(max_job_types=0)]:
            s=sample();mutate(s)
            with self.assertRaises(ValueError):self.c.validate(s)

class ReviewRegressionTests(unittest.TestCase):
    def test_compact_scope_rejects_unrelated_attempt(self):
        from report_calculate import build_report
        from report_export import export_report
        from report_contract import validate
        r=build_report(sample());c=export_report(r,attempt_ids=[1]);c['attempts'].append(copy.deepcopy(r['attempts'][0]))
        with self.assertRaises(ValueError):validate(c)
    def test_buildkit_inferred_width_matches_reported_duration(self):
        from report_contract import check_trace
        t=sample()['traces'][0];t.update(state='available',sha256='a'*64,bytes_read=10,line_count=2)
        t['coverage'].update(recognized_lines=2,total_lines=2,complete=True)
        t['evidence']=[{'id':'op','kind':'operation','code':'export_local_unpack','parent_id':None,'timing':{'duration_seconds':100,'start_seconds':0,'end_seconds':2,'origin':'buildkit_reported','quality':'inferred','precision_seconds':1},'cached':False,'complete':True,'lines':{'start':1,'end':2},'push_coverage':'unknown','buildkit':{'step_id':1},'identity':None}]
        with self.assertRaises(ValueError):check_trace(t)
    def test_filtered_canonical_attempt_can_export_with_external_type(self):
        from report_calculate import build_report
        from report_export import export_report
        from report_contract import type_id,validate
        s=sample(2);s['jobs'][0]['name']='lint';s['jobs'][1]['ref']='dev';s['pipelines'][1]['ref']='dev'
        s['source']['observed_counts']=[{'type_id':type_id(s['project'],j['stage'],j['name']),'stage':j['stage'],'name':j['name'],'available_count':1,'count_kind':'exact'} for j in s['jobs']]
        r=build_report(s,comparison_mode='cross_ref',refs=['dev']);c=export_report(r,attempt_ids=[2]);validate(c)
        self.assertEqual([a['id'] for a in c['attempts']],[2]);self.assertEqual(c['job_types'],[])
        self.assertTrue(any(x['collection']=='job_types' for x in c['external_references']))

class BudgetAndInputTests(unittest.TestCase):
    def test_payload_cap_rejects_before_write(self):
        from report_contract import save,MAX_PAYLOAD_BYTES
        s=sample();s['jobs'][0]['name']='x'*MAX_PAYLOAD_BYTES
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'too-large.json'
            with self.assertRaisesRegex(ValueError,'16 MiB'):save(p,s)
            self.assertFalse(p.exists())
    def test_cross_ref_input_rejects_before_transport(self):
        from report_collect import collect
        from unittest.mock import patch
        for mode,refs in [('cross_ref','dev'),('same_ref',['dev'])]:
            with patch('report_collect.GlabTransport') as transport:
                with self.assertRaises(ValueError):collect('gitlab.example.com','example/service',comparison_mode=mode,refs=refs)
                transport.assert_not_called()
