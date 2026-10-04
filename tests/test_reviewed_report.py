import copy
import importlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/gitlab-ci-performance/scripts'))
try:
    history = importlib.import_module('history')
    priorities = importlib.import_module('priorities')
except ModuleNotFoundError:
    history = priorities = None


def job(i, status='success', duration=100, queue=5, ref='main', name='compile', stage='build', pipeline=None):
    return {'id': i, 'pipeline_id': pipeline or i, 'name': name, 'stage': stage,
            'ref': ref, 'status': status, 'duration_seconds': duration,
            'queued_seconds': queue, 'started_at': '2026-10-01T00:00:00Z',
            'created_at': '2026-10-01T00:00:00Z', 'finished_at': '2026-10-01T00:05:00Z'}


def evidence(i, start, end, category='export_unpack', cached=False, duration=None):
    return {'id': str(i), 'label': category, 'category': category,
            'start_seconds': start, 'end_seconds': end,
            'duration_seconds': end-start if duration is None else duration,
            'first_line': 1, 'last_line': 2, 'cached': cached, 'complete': True,
            'timing_source': 'buildkit_reported', 'position_source': 'log_timestamps', 'substeps': []}


class ReviewedCalculations(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(history, 'Reviewed history module is not shipped')
        self.assertIsNotNone(priorities, 'Priority calculation module is not shipped')

    def test_retention_counts_attempts_and_keeps_newest64_per_type(self):
        jobs = [job(i, pipeline=1) for i in range(1, 81)] + [job(99, name='publish', stage='release')]
        types = history.retain_jobs(jobs)
        self.assertEqual(types[0]['source_count'], 80)
        self.assertEqual(types[0]['retained_ids'], list(range(80, 16, -1)))
        self.assertEqual(types[1]['retained_ids'], [99])

    def test_baseline_precedes_latest_and_is_independent_of_visible_window(self):
        jobs = [job(i) for i in range(1, 90)]
        jobs += [job(100, 'failed', 1000), job(101, 'success', 200, 20)]
        pipelines = [{'id': j['pipeline_id'], 'status': 'success'} for j in jobs]
        c = history.comparison(jobs, pipelines, jobs[-1])
        self.assertEqual(c['sample_ids'], list(range(89, 79, -1)))
        self.assertEqual(c['baseline_seconds'], 105)
        self.assertEqual(c['delta_seconds'], 115)
        self.assertTrue(c['eligible_increase'])

    def test_baseline_excludes_missing_canceled_failed_and_coalesces_pipeline_reruns(self):
        jobs = [job(1), job(2, pipeline=1), job(3, duration=None), job(4,'canceled'), job(5), job(6), job(7, duration=200)]
        c = history.comparison(jobs, [{'id':i,'status':'success'} for i in range(1,8)], jobs[-1])
        self.assertEqual(c['sample_ids'], [6,5,2])
        self.assertEqual(c['known'], 3)
        self.assertGreater(c['missing'], 0)

    def test_zero_baseline_percentage_and_sparse_sample_are_explicit(self):
        jobs = [job(i, duration=0, queue=0) for i in range(1,4)] + [job(4, duration=100)]
        c = history.comparison(jobs,[{'id':i,'status':'success'} for i in range(1,5)],jobs[-1])
        self.assertIsNone(c['delta_percent'])
        self.assertTrue(c['eligible_increase'])
        c = history.comparison(jobs[-2:],[{'id':i,'status':'success'} for i in range(1,5)],jobs[-1])
        self.assertFalse(c['eligible_increase'])

    def test_windows_32_64_actual_counts_and_strict_unit_boundary(self):
        jobs = [job(i, duration=295, queue=5) for i in range(1,41)]
        windows = history.windows(jobs, [])
        self.assertEqual([(w['size'],w['offset'],w['count']) for w in windows], [(32,0,32),(32,32,8),(64,0,40)])
        self.assertTrue(all(w['unit']=='seconds' for w in windows))
        jobs[-1]['duration_seconds'] = 295.001
        self.assertEqual(history.windows(jobs,[])[0]['unit'], 'minutes')
        jobs[-1]['status']='failed'
        self.assertEqual(history.windows(jobs,[])[0]['total']['known'],31)

    def test_not_run_and_missing_are_not_measured_zero(self):
        j = job(1,'skipped',0,0);j['started_at']=None
        self.assertIsNone(history.total(j))
        self.assertIsNone(history.total(job(2,duration=None)))
        self.assertEqual(history.total(job(3,duration=0,queue=0)),0)

    def test_queue_spike_documented_rule_in_newest_displayed_attempt(self):
        jobs=[job(i) for i in range(1,4)] + [job(4,queue=31)]
        w=history.windows(jobs,[])[0]
        self.assertTrue(w['queue_spike']['detected'])
        jobs[-1]['queued_seconds']=30
        self.assertFalse(history.windows(jobs,[])[0]['queue_spike']['detected'])

    def test_current_pipeline_rerun_does_not_supply_independent_baseline(self):
        jobs=[job(1),job(2),job(3,pipeline=3),job(4,pipeline=3,duration=500)]
        c=history.comparison(jobs,[{'id':i,'status':'success'} for i in range(1,4)],jobs[-1])
        self.assertEqual(c['sample_ids'],[2,1])
        self.assertFalse(c['eligible_increase'])

    def test_window_exports_successful_total_and_queue_sample_ids(self):
        jobs=[job(1),job(2,duration=None),job(3,'failed'),job(4)]
        w=history.windows(jobs,[])[0]
        self.assertEqual(w['successful_total_ids'],[4,1])
        self.assertEqual(w['queue_spike']['sample_ids'],[2,1])

    def test_union_overlap_parent_child_and_representative_never_overwrites_total(self):
        parent=evidence('export',0,100)
        parent['substeps']=[evidence('child',10,20)]
        ops=[parent,evidence('short',90,110)]
        detail={'job_id':1,'phases':[],'commands':[],'builds':[{'id':'b1','operations':ops}]}
        p=priorities.rank([job(1,queue=None)],[detail])[0]
        self.assertEqual(p['median_cost_seconds'],110)
        self.assertIn(p['evidence']['duration_seconds'],[20,100])
        self.assertNotEqual(p['median_cost_seconds'],p['evidence']['duration_seconds'])

    def test_rankings_exclude_cached_unknown_failed_canceled(self):
        records=[]
        jobs=[job(1),job(2,'failed'),job(3,'canceled'),job(4)]
        for i in range(1,5):
            op=evidence('op',0,50,cached=(i==4))
            records.append({'job_id':i,'phases':[],'commands':[],'builds':[{'id':'b1','operations':[op]}]})
        p=next(p for p in priorities.rank(jobs,records) if p['category']=='export_unpack')
        self.assertEqual((p['known'],p['missing']),(1,1))
        self.assertEqual(p['evidence']['job_id'],1)

    def test_partial_coverage_counts_runs_rather_than_operations(self):
        ops=[evidence('known',0,50),evidence('x',0,5),evidence('y',0,8)]
        for op in ops[1:]:op['start_seconds']=op['end_seconds']=None
        detail={'job_id':1,'phases':[],'commands':[],'builds':[{'id':'b1','operations':ops}]}
        p=priorities.rank([job(1,queue=None)],[detail])[0]
        self.assertEqual(p['partial'],1)
        self.assertEqual(priorities.union_seconds([(None,None),(0,2),(1,3)]),3)

    def test_null_duration_in_incomplete_operation_marks_partial_run(self):
        incomplete=evidence('incomplete',50,60)
        incomplete.update(end_seconds=None,duration_seconds=None,complete=False)
        detail={'job_id':1,'phases':[],'commands':[],'builds':[{'id':'b1','operations':[evidence('known',0,50),incomplete]}]}
        p=priorities.rank([job(1,queue=None)],[detail])[0]
        self.assertEqual((p['median_cost_seconds'],p['known'],p['missing'],p['partial']),(50,1,0,1))


if __name__=='__main__':
    unittest.main()
