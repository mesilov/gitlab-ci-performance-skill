import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/gitlab-ci-performance/scripts'
sys.path.insert(0, str(SCRIPTS))
import ci_report as ci


def fixture(count=4):
    project = dict(id=42, path='example/service', host='gitlab.example.com',
                   web_url='https://gitlab.example.com/example/service', default_branch='main')
    stamp = '2026-10-04T00:00:00Z'
    definitions = dict(kind='workflows', schema_version='2.0.0',
        project=dict(host=project['host'], path=project['path']), cross_pipeline_policy='unsupported',
        unknowns=[], evidence=[dict(id='resolved', source_url=project['web_url']+'/-/blob/demo/.gitlab-ci.yml',
            commit='demo', ref='main', config_sha256='a'*64, verified_at=stamp,
            pipeline_ids=list(range(1, count+1)), pipeline_shas=[])], workflows=[dict(
        id='delivery', purpose='Build and verify a package', type='chain', versions=[dict(
            version='1', evidence_ids=['resolved'], selection=dict(refs=['main'], sources=['push']),
            completion='all_required_terminal', success='required_success', unknown_membership=[], jobs=[
                dict(id='compile', name='compile', stage='build', required=True, manual=False, needs=[], parallel_group=None),
                dict(id='test', name='test', stage='test', required=True, manual=False, needs=['compile'], parallel_group=None),
                dict(id='publish', name='publish', stage='publish', required=False, manual=True, needs=['test'], parallel_group=None)
            ])])])
    snapshot = dict(schema_version='2.0.0', kind='workflow-jobs', collection_started_at=stamp,
        collected_at=stamp, timezone='UTC', project=project, source=dict(
            transport='glab', glab_version='fixture', gitlab_version='fixture', requested_window=64,
            anchor_pipeline_id=count, pipeline_pages=1, max_pages=10, pipeline_list_complete=True,
            pipeline_history_exhausted=False,
            pipelines={}, limitations=['Cross-pipeline scenarios are unsupported', 'No traces collected']),
        pipelines=[], jobs=[])
    for pid in range(1, count+1):
        start = datetime(2026, 10, 1, tzinfo=timezone.utc)+timedelta(hours=pid)
        iso = lambda n: (start+timedelta(seconds=n)).isoformat()
        snapshot['pipelines'].append(dict(id=pid, ref='main', sha='demo', source='push', status='success',
            created_at=iso(0), started_at=iso(10), finished_at=iso(80), duration_seconds=70,
            queued_seconds=10, web_url=f'https://gitlab.example.com/pipelines/{pid}'))
        snapshot['source']['pipelines'][str(pid)] = dict(metadata_complete=True, jobs_complete=True,
            pages=1, anchor_job_id=pid*100+3, error=None)
        for offset, name, stage, begin, end, status in [(1,'compile','build',10,30,'success'),
                  (2,'test','test',40,80,'success'), (3,'publish','publish',None,None,'manual')]:
            snapshot['jobs'].append(dict(id=pid*100+offset, pipeline_id=pid, name=name, stage=stage,
                ref='main', status=status, allow_failure=False, created_at=iso(0),
                started_at=iso(begin) if begin is not None else None,
                finished_at=iso(end) if end is not None else None,
                duration_seconds=end-begin if end is not None else None,
                queued_seconds=2 if begin is not None else None, failure_reason=None, runner=None,
                web_url=f'https://gitlab.example.com/jobs/{pid*100+offset}'))
    return snapshot, definitions


def build(snapshot, definitions):
    assert hasattr(ci, 'workflow_build'), 'workflow calculation route is missing'
    return ci.workflow_build(snapshot, definitions)


class WorkflowTimingTests(unittest.TestCase):
    def run_for(self, s, d, pid=4, operation=None):
        return next(r for r in build(s,d)['views'][0]['series'][0]['runs']
                    if r['pipeline_id']==pid and r['operation_id']==operation)

    def test_sequential_optional_manual_union_and_baseline(self):
        s,d=fixture(); r=self.run_for(s,d)
        self.assertEqual(r['state'], 'completed')
        self.assertEqual([r['metrics'][k] for k in ('elapsed_seconds','active_seconds','gap_seconds','queue_sum_seconds')], [70,60,10,4])
        self.assertEqual(r['coverage']['interval_missing'],0)
        comparison=build(s,d)['views'][0]['series'][0]['comparisons']['elapsed_seconds']
        self.assertEqual(comparison['sample_pipeline_ids'],[1,2,3])
        self.assertEqual((comparison['n'],comparison['median_seconds'],comparison['delta_seconds']), (3,70,0))
        self.assertTrue(comparison['eligible'])

    def test_parallel_intervals_and_retry_timing_latest_outcome(self):
        s,d=fixture(); first=s['jobs'][-3]; second=s['jobs'][-2]
        second.update(started_at=first['started_at'])
        old=copy.deepcopy(first); old.update(id=399, status='failed'); s['jobs'].append(old)
        r=self.run_for(s,d)
        self.assertEqual(r['state'],'completed')
        self.assertEqual(r['metrics']['active_seconds'],70)
        self.assertEqual(r['metrics']['queue_sum_seconds'],6)
        self.assertIn(399,r['attempt_ids'])
        self.assertEqual(r['members'][0]['latest_attempt_id'],401)

    def test_unfinished_failed_canceled_and_manual_are_distinct(self):
        for status, state in [('running','active'),('manual','waiting-manual'),('failed','failed'),('canceled','canceled')]:
            s,d=fixture(); s['jobs'][-2]['status']=status
            if status in ('running','manual'):s['jobs'][-2]['finished_at']=None
            r=self.run_for(s,d)
            self.assertEqual(r['state'],state)
            self.assertFalse(r['eligible_success'])
            if status in ('running','manual'):self.assertIsNone(r['metrics']['elapsed_seconds'])

    def test_missing_required_and_partial_pagination_are_unknown(self):
        s,d=fixture(); s['jobs'].pop(-2)
        self.assertEqual(self.run_for(s,d)['state'],'unknown/incomplete')
        s,d=fixture();s['source']['pipelines']['4']['jobs_complete']=False
        r=self.run_for(s,d)
        self.assertFalse(r['eligible_success']); self.assertIsNone(r['metrics']['elapsed_seconds'])

    def test_malformed_reversed_or_missing_interval_never_becomes_exact(self):
        for value in [None,'bad','2026-09-01T00:00:00Z']:
            s,d=fixture();s['jobs'][-2]['finished_at']=value
            r=self.run_for(s,d)
            self.assertEqual(r['coverage']['interval_missing'],1)
            self.assertFalse(r['coverage']['active_exact'])
            self.assertIsNone(r['metrics']['elapsed_seconds'])
            self.assertEqual(r['metrics']['active_seconds'],20)
            self.assertIsNone(r['metrics']['gap_seconds'])

    def test_zero_baseline_and_minimum_samples(self):
        s,d=fixture()
        for j in s['jobs']:j['finished_at']=j['started_at']
        for j in s['jobs']:
            if j['name']=='test': j['started_at']=next(x['started_at'] for x in s['jobs'] if x['pipeline_id']==j['pipeline_id'] and x['name']=='compile');j['finished_at']=j['started_at']
        c=build(s,d)['views'][0]['series'][0]['comparisons']['elapsed_seconds']
        self.assertEqual(c['median_seconds'],0);self.assertIsNone(c['delta_percent'])
        s,d=fixture(3);c=build(s,d)['views'][0]['series'][0]['comparisons']['elapsed_seconds']
        self.assertFalse(c['eligible']);self.assertEqual(c['n'],2)

    def test_configuration_coverage_versions_context_and_ambiguity(self):
        s,d=fixture();d['evidence'][0]['pipeline_ids']=[4]
        self.assertEqual(self.run_for(s,d,pid=3)['state'],'unknown/incomplete')
        self.assertFalse(build(s,d)['views'][0]['series'][0]['comparisons']['elapsed_seconds']['eligible'])
        s,d=fixture(); v=copy.deepcopy(d['workflows'][0]['versions'][0]);v['version']='2'
        d['workflows'][0]['versions'].append(v)
        self.assertEqual(self.run_for(s,d)['state'],'unknown/incomplete')
        s,d=fixture();s['pipelines'][0]['source']='schedule'
        c=build(s,d)['views'][0]['series'][0]['comparisons']['elapsed_seconds']
        self.assertFalse(c['eligible']);self.assertEqual(c['n'],2)

    def test_independent_operations_have_separate_series(self):
        s,d=fixture();d['workflows'][0]['type']='independent'
        for j in d['workflows'][0]['versions'][0]['jobs']:j['needs']=[]
        series=build(s,d)['views'][0]['series']
        self.assertEqual([x['operation_id'] for x in series],['compile','test','publish'])
        self.assertEqual(series[0]['runs'][-1]['metrics']['elapsed_seconds'],20)
        self.assertEqual(series[1]['runs'][-1]['metrics']['elapsed_seconds'],40)
        self.assertIsNone(series[2]['runs'][-1]['metrics']['elapsed_seconds'])

    def test_pipeline_windows_include_all_attempts_without_job_truncation(self):
        s,d=fixture(70);report=build(s,d)
        for view,window in zip(report['views'],[32,64]):
            self.assertEqual(view['window'],window)
            self.assertEqual(len(view['pipeline_ids']),window)
            self.assertEqual(len(view['job_attempt_ids']),window*3)
            self.assertEqual(len(view['series'][0]['runs']),window)
            self.assertFalse(view['series'][0]['comparisons']['elapsed_seconds']['extends_visible_window'])

    def test_larger_window_cannot_claim_complete_coverage_from_a_smaller_collection(self):
        s,d=fixture(40);ids=set(range(9,41))
        s['pipelines']=[p for p in s['pipelines'] if p['id'] in ids]
        s['jobs']=[j for j in s['jobs'] if j['pipeline_id'] in ids]
        s['source']['pipelines']={k:v for k,v in s['source']['pipelines'].items() if int(k) in ids}
        s['source']['requested_window']=32
        report=build(s,d)
        self.assertTrue(report['views'][0]['source_window_complete'])
        self.assertFalse(report['views'][1]['source_window_complete'])

    def test_definition_cycles_duplicate_ids_and_independent_dependencies_rejected(self):
        s,d=fixture()
        for change in ('cycle','duplicate','independent'):
            bad=copy.deepcopy(d)
            if change=='cycle':bad['workflows'][0]['versions'][0]['jobs'][0]['needs']=['test']
            elif change=='duplicate':bad['workflows'][0]['versions'][0]['jobs'][1]['id']='compile'
            else:bad['workflows'][0]['type']='independent'
            with self.assertRaises(ValueError):build(s,bad)

    def test_export_and_render_consume_canonical_values_and_are_deterministic(self):
        s,d=fixture();report=build(s,d)
        compact=ci.workflow_export(report)
        self.assertEqual(compact['views'],report['views'])
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a.html',Path(tmp)/'b.html'
            ci.render(report,a);ci.render(report,b)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            self.assertIn('workflow-select',a.read_text())

    def test_render_rejects_source_definitions_and_compact_exports(self):
        s,d=fixture();compact=ci.workflow_export(build(s,d))
        with tempfile.TemporaryDirectory() as tmp:
            for i,data in enumerate([s,d,compact]):
                with self.assertRaises(ValueError):ci.render(data,Path(tmp)/f'{i}.html')

    def test_workflow_renderer_honors_shared_cli_language_without_mutating_data(self):
        import re
        s,d=fixture();s['jobs'][0]['name']='__LANGUAGE__</script>'
        report=build(s,d)
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'ru.html';ci.render(report,output,'ru')
            html=output.read_text()
            self.assertIn('<html lang="ru">',html)
            payload=re.search(r'<script id="report-data" type="application/json">(.*?)</script>',html,re.S)[1]
            self.assertEqual(json.loads(payload),report)
            with self.assertRaises(ValueError):ci.render(report,Path(tmp)/'unsupported.html','fr')

    def test_changed_definition_version_is_not_a_baseline_and_queue_partial_is_explicit(self):
        s,d=fixture();v=copy.deepcopy(d['workflows'][0]['versions'][0]);v['version']='2'
        v['evidence_ids']=['new'];d['workflows'][0]['versions'].append(v)
        d['evidence'].append(dict(d['evidence'][0],id='new',pipeline_ids=[4]))
        d['evidence'][0]['pipeline_ids']=[1,2,3]
        s['jobs'][-2]['queued_seconds']=None
        r=self.run_for(s,d)
        self.assertEqual(r['metrics']['queue_sum_seconds'],2)
        self.assertEqual((r['coverage']['queue_known'],r['coverage']['queue_missing']),(1,2))
        self.assertFalse(r['coverage']['queue_exact'])
        self.assertFalse(build(s,d)['views'][0]['series'][0]['comparisons']['elapsed_seconds']['eligible'])

    def test_distinct_pipelines_with_same_sha_remain_distinct_and_unknown_is_not_zero(self):
        s,d=fixture();s['jobs']=[j for j in s['jobs'] if j['pipeline_id']!=4]
        report=build(s,d);runs=report['views'][0]['series'][0]['runs']
        self.assertEqual([r['pipeline_id'] for r in runs],[1,2,3,4])
        self.assertIsNone(runs[-1]['metrics']['active_seconds'])
        self.assertIsNone(runs[-1]['metrics']['elapsed_seconds'])

    def test_every_known_retained_queue_measurement_is_included(self):
        s,d=fixture();s['jobs'][-1]['queued_seconds']=7
        r=self.run_for(s,d)
        self.assertEqual(r['metrics']['queue_sum_seconds'],11)
        self.assertEqual((r['coverage']['queue_known'],r['coverage']['queue_missing']),(3,0))

    def test_v1_source_and_future_versions_are_rejected_in_workflow_route(self):
        s,d=fixture()
        for artifact in [s,d]:
            bad=copy.deepcopy(artifact);bad['schema_version']='99.0.0'
            with self.assertRaises(ValueError):build(bad,d) if artifact is s else build(s,bad)
        s['kind']='jobs';s['schema_version']='1.0.0'
        with self.assertRaises(ValueError):build(s,d)

    def test_clean_installed_cli_stamps_hash_and_exports_all_contracts(self):
        import hashlib
        import shutil
        s,d=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); installed=root/'installed'
            shutil.copytree(SCRIPTS.parent,installed,ignore=shutil.ignore_patterns('__pycache__'))
            helper=installed/'scripts/ci_report.py'
            model=root/'model.json';model.write_bytes(ci.encoded(dict(d,evidence=[])))
            config=root/'resolved.yml';config.write_text('compile:\n  stage: build\n  script: echo synthetic\n')
            jobs=root/'jobs.json';jobs.write_bytes(ci.encoded(s))
            defs=root/'workflows.json';out=root/'report.json';html=root/'report.html';compact=root/'llm.json'
            def run(*args):subprocess.run([sys.executable,str(helper),*map(str,args)],check=True,capture_output=True)
            run('define-workflows','--model',model,'--config',config,'--evidence-id','resolved',
                '--source-url','https://gitlab.example.com/resolved','--commit','demo','--ref','main',
                '--verified-at','2026-10-04T00:00:00Z','--pipeline-ids',1,2,3,4,'--output',defs)
            self.assertEqual(ci.load(defs)['evidence'][0]['config_sha256'],hashlib.sha256(config.read_bytes()).hexdigest())
            run('report','--snapshot',jobs,'--workflows',defs,'--output',out)
            run('render','--report',out,'--output',html)
            run('export-llm','--report',out,'--output',compact)
            for path in [jobs,defs,out,compact]:run('validate',path)
            self.assertEqual(ci.load(out)['views'],ci.load(compact)['views'])
            self.assertIn('workflow-select',html.read_text())


class WorkflowCollectionTests(unittest.TestCase):
    def fake_api(self, count, calls, detail_failure=False, late_attempt=False):
        s,_=fixture(count)
        def request(host,endpoint):
            calls.append(endpoint)
            if endpoint=='version':return '',{'version':'fixture'}
            if endpoint.startswith('projects/example%2Fservice'):return '',dict(id=42,path_with_namespace='example/service',web_url=s['project']['web_url'],default_branch='main')
            if endpoint.startswith('projects/42/pipelines?'):
                return '',sorted(s['pipelines'],key=lambda p:p['id'],reverse=True)
            import re
            pid=int(re.search(r'/pipelines/(\d+)',endpoint).group(1))
            if '/jobs?' in endpoint:
                jobs=[j for j in s['jobs'] if j['pipeline_id']==pid]
                def raw(j):return dict(j,pipeline={'id':pid},duration=j['duration_seconds'],queued_duration=j['queued_seconds'])
                if 'page=2' in endpoint:
                    old=dict(raw(jobs[0]),id=pid*100,status='failed')
                    if late_attempt:return '',[dict(old,id=pid*100+99)]
                    return '',[old]
                link=f'<https://gitlab.example.com/api/v4/projects/42/pipelines/{pid}/jobs?include_retried=true&page=2>; rel="next"'
                return link,[raw(j) for j in reversed(jobs)]
            if detail_failure:raise ValueError('transport failed')
            return '',next(p for p in s['pipelines'] if p['id']==pid)
        return request

    def test_both_windows_keep_every_page_and_retry_without_global_job_slices(self):
        for window in [32,64]:
            calls=[]
            with patch.object(ci,'request',side_effect=self.fake_api(70,calls)):
                s=ci.workflow_collect('gitlab.example.com','example/service','UTC',window,2)
            self.assertEqual(len(s['pipelines']),window)
            self.assertEqual(len(s['jobs']),window*4)
            self.assertEqual(len(calls),3+window*3)
            self.assertFalse(s['source']['pipeline_history_exhausted'])
            self.assertTrue(all(c['jobs_complete'] for c in s['source']['pipelines'].values()))
            self.assertTrue(all(j['pipeline_id']>70-window for j in s['jobs']))

    def test_missing_details_and_post_anchor_attempts_expose_partial_coverage(self):
        for detail_failure,late_attempt,key in [(True,False,'metadata_complete'),(False,True,'jobs_complete')]:
            with patch.object(ci,'request',side_effect=self.fake_api(1,[],detail_failure,late_attempt)):
                s=ci.workflow_collect('gitlab.example.com','example/service','UTC',32,2)
            self.assertFalse(s['source']['pipelines']['1'][key])
            self.assertTrue(s['source']['pipeline_history_exhausted'])
            self.assertEqual(len(s['jobs']),3 if late_attempt else 4)

    def overlapping_api(self, calls, unrelated_duplicate=False):
        s,_=fixture(2)
        base=self.fake_api(2,calls)
        template=s['jobs'][0]
        attempts=[dict(template,id=i,pipeline={'id':1},duration=20,queued_duration=2)
                  for i in range(100,0,-1)]
        attempts=[dict(j,pipeline={'id':1},duration=j['duration_seconds'],
                       queued_duration=j['queued_seconds']) for j in reversed(s['jobs'][:3])]+attempts
        def request(host,endpoint):
            if '/pipelines/1/jobs?' not in endpoint:return base(host,endpoint)
            calls.append(endpoint)
            if 'page=2' in endpoint:
                # ID 104 is inserted after page 1: offset 100 repeats ID 4,
                # even though the new attempt itself never appears on page 2.
                repeated=dict(attempts[99],status='failed')
                if unrelated_duplicate:repeated['pipeline']={'id':2}
                return '',[repeated]+attempts[100:]
            link='<https://gitlab.example.com/api/v4/projects/42/pipelines/1/jobs?include_retried=true&page=2>; rel="next"'
            return link,attempts[:100]
        return request

    def test_offset_overlap_keeps_unique_attempts_and_marks_only_affected_pipeline_partial(self):
        calls=[]
        with patch.object(ci,'request',side_effect=self.overlapping_api(calls)):
            s=ci.workflow_collect('gitlab.example.com','example/service','UTC',32,2)
        self.assertEqual(len(calls),9)
        self.assertEqual(len(s['jobs']),107)
        self.assertEqual(len({j['id'] for j in s['jobs']}),107)
        self.assertEqual(next(j for j in s['jobs'] if j['id']==4)['status'],'success')
        coverage=s['source']['pipelines']['1']
        self.assertEqual(coverage['anchor_job_id'],103)
        self.assertEqual(coverage['pages'],2)
        self.assertFalse(coverage['jobs_complete'])
        self.assertEqual(coverage['error'],'job_pagination_duplicate_id')
        self.assertTrue(s['source']['pipelines']['2']['jobs_complete'])
        _,d=fixture(2)
        series=build(s,d)['views'][0]['series'][0]
        runs=series['runs']
        partial=next(r for r in runs if r['pipeline_id']==1)
        self.assertFalse(partial['eligible_success'])
        self.assertIsNone(partial['metrics']['elapsed_seconds'])
        self.assertFalse(partial['coverage']['active_exact'])
        self.assertTrue(next(r for r in runs if r['pipeline_id']==2)['eligible_success'])
        self.assertNotIn(1,series['comparisons']['elapsed_seconds']['sample_pipeline_ids'])

    def test_duplicate_does_not_hide_unrelated_pipeline_identity(self):
        with patch.object(ci,'request',side_effect=self.overlapping_api([],True)):
            with self.assertRaisesRegex(ValueError,'Job belongs to unrelated pipeline'):
                ci.workflow_collect('gitlab.example.com','example/service','UTC',32,2)

    def test_pagination_cannot_change_scope_or_leak_transport_urls(self):
        from workflow_report import next_endpoint
        path='projects/42/pipelines/1/jobs'
        valid=f'<https://gitlab.example.com/api/v4/{path}?include_retried=true&page=2>; rel="next"'
        self.assertIn('page=2',next_endpoint(valid,'gitlab.example.com',path,{'include_retried':'true'}))
        for unsafe in [valid.replace('include_retried=true','include_retried=false'),valid.replace('/42/','/99/'),
                       valid.replace('gitlab.example.com','evil.example.com'),valid.replace('page=2','token=secret')]:
            with self.assertRaises(ValueError):next_endpoint(unsafe,'gitlab.example.com',path,{'include_retried':'true'})

    def test_pipeline_api_retains_retries_and_limits_requests_without_traces(self):
        s,_=fixture(1); calls=[]
        raw=copy.deepcopy(s['jobs'][0]);raw['pipeline']={'id':1};raw['duration']=20;raw['queued_duration']=2
        def request(host,endpoint):
            calls.append(endpoint)
            if endpoint=='version':return '',{'version':'fixture'}
            if endpoint.startswith('projects/example%2Fservice'):return '',dict(id=42,path_with_namespace='example/service',web_url=s['project']['web_url'],default_branch='main')
            if '/jobs?' in endpoint:return '<https://gitlab.example.com/api/v4/projects/42/pipelines/1/jobs?include_retried=true&page=2>; rel="next"',[raw]
            if endpoint.startswith('projects/42/pipelines?'):return '',[s['pipelines'][0]]
            return '',s['pipelines'][0]
        self.assertTrue(hasattr(ci,'workflow_collect'),'pipeline collection route is missing')
        with patch.object(ci,'request',side_effect=request):out=ci.workflow_collect('gitlab.example.com','example/service','UTC',32,1)
        self.assertEqual(len(out['jobs']),1)
        self.assertFalse(out['source']['pipelines']['1']['jobs_complete'])
        self.assertEqual(len(calls),5)
        self.assertTrue(any('include_retried=true' in x for x in calls))
        self.assertFalse(any('trace' in x for x in calls))


if __name__=='__main__':unittest.main()
