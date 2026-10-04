import copy
import importlib.util
import json
import hashlib
import subprocess
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/gitlab-ci-performance/scripts'
sys.path.insert(0, str(SCRIPTS))
import collection


def fixture(count=1):
    jobs = []
    for i in range(1, count + 1):
        jobs.append(dict(id=i, pipeline_id=i, name='build', stage='test', ref='main',
                         status='success', allow_failure=False, created_at='2026-10-01T00:00:00Z',
                         started_at='2026-10-01T00:00:01Z', finished_at='2026-10-01T00:01:00Z',
                         duration_seconds=59, queued_seconds=1, failure_reason=None, runner=None,
                         web_url=f'https://gitlab.example/jobs/{i}'))
    return dict(schema_version='1.0.0', kind='jobs', timezone='UTC',
                collected_at='2026-10-01T00:02:00Z', project=dict(id=42, host='gitlab.example', path='a/b'),
                source=dict(complete_available_history=True), jobs=jobs, pipelines=[])


def api_job(job):
    raw = copy.deepcopy(job)
    raw['pipeline'] = {'id': raw.pop('pipeline_id')}
    raw['duration'] = raw.pop('duration_seconds')
    raw['queued_duration'] = raw.pop('queued_seconds')
    raw.update(commit={'id': 'abcdef', 'message': 'SECRET'}, user={'email': 'SECRET'}, variables=['SECRET'])
    return raw


class CollectionTests(unittest.TestCase):
    def collect(self, s, **kwargs):
        jobs = {j['id']: j for j in s['jobs']}
        kwargs.setdefault('request_json', lambda host, endpoint: api_job(jobs[int(endpoint.split('/')[-1])]))
        kwargs.setdefault('request_trace', lambda host, endpoint, limit: b'Job succeeded\n')
        return collection.collect_details(s, **kwargs)

    def test_scope_before_requests_and_newest64(self):
        s = fixture(100)
        other = copy.deepcopy(s['jobs'][0]); other.update(id=101, name='other')
        s['jobs'].append(other)
        calls = []
        def metadata(host, endpoint):
            calls.append(int(endpoint.split('/')[-1])); return api_job(s['jobs'][calls[-1]-1])
        m, t = self.collect(s, job_names=['build'], request_json=metadata, no_traces=True)
        self.assertEqual(sorted(calls), list(range(37, 101)))
        self.assertEqual(m['types'][0]['retained_ids'], list(range(100, 36, -1)))
        self.assertEqual(m['types'][0]['source_count'], 100)
        self.assertEqual(len(t['details']), 64)
        self.assertEqual(m['coverage']['trace_requests'], 0)

    def test_metadata_failure_keeps_safe_stale_job(self):
        s = fixture(); s['jobs'][0]['user'] = {'email': 'SECRET'}
        def failed(*args): raise RuntimeError('SECRET token')
        m, t = self.collect(s, request_json=failed)
        self.assertEqual(m['jobs'][0]['metadata_status'], 'stale')
        self.assertEqual(m['jobs'][0]['metadata_error'], 'metadata_request_failed')
        self.assertNotIn('SECRET', json.dumps((m,t)))
        self.assertEqual(m['coverage']['metadata_fresh'], 0)

    def test_identity_mismatch_rejected(self):
        s = fixture(); raw = api_job(s['jobs'][0]); raw['ref'] = 'different'
        m, _ = self.collect(s, request_json=lambda *args: raw)
        self.assertEqual(m['jobs'][0]['metadata_error'], 'metadata_identity_mismatch')
        self.assertEqual(m['jobs'][0]['job']['ref'], 'main')

    def test_trace_states_and_zero_not_run(self):
        for status, code in [('skipped','not_run'), ('manual','not_run')]:
            s=fixture(); s['jobs'][0].update(status=status, started_at=None, duration_seconds=0)
            m,t=self.collect(s)
            self.assertEqual(m['jobs'][0]['trace_status'],code)
            self.assertIsNone(m['jobs'][0]['job']['duration_seconds'])
            self.assertEqual(m['coverage']['trace_requests'],0)
        for response, code in [(b'', 'empty'), ((403,b'SECRET'), 'unavailable'), ((404,b'SECRET'), 'unavailable')]:
            m,t=self.collect(fixture(), request_trace=lambda *args: response)
            self.assertEqual(t['details'][0]['trace_status'],code)
            self.assertNotIn('SECRET',json.dumps((m,t)))
        s=fixture(); raw=api_job(s['jobs'][0]);raw['erased_at']='2026-10-02T00:00:00Z'
        m,t=self.collect(s,request_json=lambda *args:raw)
        self.assertEqual(t['details'][0]['trace_status'],'erased')
        self.assertEqual(m['coverage']['trace_requests'],0)

    def test_stream_byte_cap(self):
        chunks = iter([b'x'*10, b'x'*10, b'x'*10])
        m,t=self.collect(fixture(),max_trace_bytes=12,request_trace=lambda *args:chunks)
        self.assertEqual(m['coverage']['trace_bytes_received'],13)
        self.assertEqual(t['details'][0]['processed_bytes'],12)
        self.assertEqual(t['details'][0]['trace_status'],'partial')

    def test_active_is_partial_without_byte_truncation(self):
        s=fixture();s['jobs'][0].update(status='running',finished_at=None)
        m,t=self.collect(s)
        detail=t['details'][0]
        self.assertEqual(detail['trace_status'],'partial')
        self.assertIn('active_trace',detail['limitations'])
        self.assertNotIn('truncated_trace',detail['limitations'])
        self.assertEqual(detail['trace_sha256'],hashlib.sha256(b'Job succeeded\n').hexdigest())

    def test_timeout_has_fixed_safe_error_and_one_request(self):
        def timeout(*args):raise TimeoutError('SECRET transport payload')
        m,t=self.collect(fixture(),request_trace=timeout)
        self.assertEqual(m['coverage']['trace_requests'],1)
        self.assertEqual(t['details'][0]['limitations'],['trace_timeout'])
        self.assertNotIn('SECRET',json.dumps((m,t)))

    def test_default_transport_reads_only_cap_plus_one(self):
        real_popen=subprocess.Popen
        processes=[]
        def local_process(*args,**kwargs):
            process=real_popen([sys.executable,'-c',"import sys; sys.stdout.buffer.write(b'x'*1000000)"],**kwargs)
            processes.append(process)
            return process
        with patch.object(collection.subprocess,'Popen',side_effect=local_process):
            raw=collection._request_trace('gitlab.example','projects/42/jobs/1/trace',12)
        self.assertEqual(raw,b'x'*13)
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdout.closed)

    def test_cache_is_not_reused_without_explicit_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def trace(*args):calls.append(1);return b'Job succeeded\n'
            self.collect(fixture(),trace_cache=tmp,request_trace=trace)
            self.collect(fixture(),trace_cache=tmp,request_trace=trace)
            self.assertEqual(len(calls),2)

    def test_worker_and_byte_bounds(self):
        for workers in [0,9,True,1.5]:
            with self.assertRaises(ValueError): self.collect(fixture(),workers=workers)
        for cap in [0,-1,True,1.5]:
            with self.assertRaises(ValueError):self.collect(fixture(),max_trace_bytes=cap)
        lock=threading.Lock();active=0;peak=0
        def metadata(host, endpoint):
            nonlocal active,peak
            with lock:active+=1;peak=max(active,peak)
            time.sleep(.01)
            with lock:active-=1
            return api_job(fixture(8)['jobs'][int(endpoint.split('/')[-1])-1])
        m,_=self.collect(fixture(8),workers=2,request_json=metadata,no_traces=True)
        self.assertEqual(peak,2)
        self.assertEqual([x['job_id'] for x in m['jobs']],list(range(8,0,-1)))

    def test_cache_private_reuse_and_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)/'cache';calls=[]
            def trace(*args):calls.append(1);return b'Job succeeded\n'
            self.collect(fixture(),trace_cache=cache,request_trace=trace)
            m,_=self.collect(fixture(),trace_cache=cache,reuse_cache=True,request_trace=trace)
            self.assertEqual(len(calls),1)
            self.assertEqual(m['jobs'][0]['trace_source'],'cache')
            self.assertEqual(os.stat(cache).st_mode & 0o777,0o700)
            for p in cache.rglob('*'):
                self.assertEqual(os.stat(p).st_mode & 0o777,0o700 if p.is_dir() else 0o600)
            s=fixture();s['project']['id']=43
            self.collect(s,trace_cache=cache,reuse_cache=True,request_trace=trace)
            self.assertEqual(len(calls),2)
            s=fixture();s['jobs'][0]['finished_at']='2026-10-02T00:00:00Z'
            self.collect(s,trace_cache=cache,reuse_cache=True,request_trace=trace)
            self.assertEqual(len(calls),3)

    def test_running_partial_and_corrupt_cache_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)/'cache';calls=[]
            def trace(*args):calls.append(1);return b'x'*20
            self.collect(fixture(),trace_cache=cache,max_trace_bytes=10,request_trace=trace)
            self.collect(fixture(),trace_cache=cache,reuse_cache=True,request_trace=trace)
            self.assertEqual(len(calls),2)
            for p in cache.rglob('*.trace'):p.write_bytes(b'corrupt')
            self.collect(fixture(),trace_cache=cache,reuse_cache=True,request_trace=trace)
            self.assertEqual(len(calls),3)
            s=fixture();s['jobs'][0].update(status='running',finished_at=None)
            self.collect(s,trace_cache=cache,reuse_cache=True,request_trace=trace)
            self.collect(s,trace_cache=cache,reuse_cache=True,request_trace=trace)
            self.assertEqual(len(calls),5)

if __name__=='__main__':unittest.main()
