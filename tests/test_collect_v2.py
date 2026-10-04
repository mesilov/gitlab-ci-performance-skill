import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/gitlab-ci-performance/scripts'
sys.path.insert(0, str(SCRIPTS))
try:
    import report_collect as collector
except ImportError:
    collector = None

HOST = 'gitlab.example.com'
AT = '2026-10-04T00:00:00+00:00'
PROJECT = {'id': 42, 'path_with_namespace': 'example/service', 'web_url': 'https://gitlab.example.com/example/service', 'default_branch': 'main'}
FIRST = 'projects/42/jobs?per_page=100&pagination=keyset&order_by=id&sort=desc'
SECOND = 'projects/42/jobs?per_page=100&id_before=10'

def job(i, status='success', name='build', stage='test', ref='main'):
    return {'id': i, 'pipeline': {'id': i, 'sha': 'abc', 'ref': ref, 'status': 'success', 'web_url': f'https://{HOST}/pipelines/{i}'}, 'commit': {'id': 'abc'}, 'name': name, 'stage': stage, 'ref': ref, 'status': status, 'created_at': AT, 'started_at': AT if status != 'skipped' else None, 'finished_at': AT, 'duration': 1.5, 'queued_duration': 0.5, 'web_url': f'https://{HOST}/jobs/{i}'}

class FakeTransport:
    def __init__(self, pages, fresh=None, errors=None, traces=None):
        self.pages = pages
        self.fresh = fresh or {}
        self.errors = errors or {}
        self.traces = traces or {}
        self.calls = []
        self.alljobs = {j['id']: j for _, batch in pages.values() for j in batch}
    def json(self, endpoint):
        self.calls.append(endpoint)
        if endpoint in self.errors:
            raise collector.TransportError(self.errors[endpoint])
        if endpoint.startswith('projects/example'):
            return '', PROJECT
        if endpoint == 'version':
            return '', {'version': '18.0.0'}
        if endpoint in self.pages:
            return copy.deepcopy(self.pages[endpoint])
        jid = int(endpoint.rsplit('/', 1)[-1])
        if '/jobs/' in endpoint:
            return '', copy.deepcopy(self.fresh.get(jid, self.alljobs[jid]))
        raw = copy.deepcopy(self.alljobs[jid]['pipeline'])
        raw.update(created_at=AT, started_at=AT, finished_at=AT, duration=1.5, queued_duration=.5)
        return '', raw
    def trace(self, endpoint, max_bytes, max_lines):
        self.calls.append(endpoint)
        if endpoint in self.errors:
            raise collector.TransportError(self.errors[endpoint])
        return self.traces.get(int(endpoint.split('/')[-2]), (b'', False))
    def version(self):
        return 'glab 1.0'


def next_header(endpoint):
    return f'Link: <https://{HOST}/api/v4/{endpoint}>; rel="next"'

class CollectTests(unittest.TestCase):
    def run_collect(self, transport, **kwargs):
        self.assertIsNotNone(collector, 'bounded v2 collector has not been implemented')
        with patch.object(collector, 'GlabTransport', return_value=transport), patch.object(collector, 'now', return_value=AT):
            return collector.collect(HOST, 'example/service', **kwargs)

    def test_retains_newest64_all_outcomes_refreshes_baseline_and_counts(self):
        batch = [job(i, 'failed' if i > 6 else 'success') for i in range(70, 0, -1)]
        transport = FakeTransport({FIRST: ('', batch)})
        s = self.run_collect(transport)
        self.assertEqual(s['retained_job_ids'], list(range(70, 6, -1)))
        self.assertEqual(s['baseline_job_ids'], list(range(6, 0, -1)))
        self.assertEqual(len(s['jobs']), 70)
        self.assertTrue(all(j['metadata_fresh'] for j in s['jobs']))
        self.assertEqual(s['source']['observed_counts'][0]['available_count'], 70)
        self.assertEqual(s['source']['observed_counts'][0]['count_kind'], 'exact')
        self.assertEqual(s['source']['requests'], dict(project=1, version=1, pages=1, metadata=70, pipelines=70, traces=64))
        self.assertEqual({t['job_id'] for t in s['traces']}, set(range(7, 71)))

    def test_fresh_outcome_change_searches_beyond_retention_for_baseline(self):
        rows = [job(i) for i in range(70, 0, -1)]
        t = FakeTransport({FIRST: ('', rows)}, fresh={i: job(i, 'failed') for i in range(7, 71)})
        s = self.run_collect(t)
        self.assertEqual(s['baseline_job_ids'], list(range(6, 0, -1)))
        self.assertTrue(all(j['metadata_fresh'] for j in s['jobs']))
        self.assertEqual(s['source']['requests']['metadata'], 70)

    def test_crossref_baseline_anchor_uses_latest_allowed_retained_attempt(self):
        rows = [job(i, 'success' if i >= 65 or i <= 11 else 'failed', ref='dev' if i < 75 else 'main')
                for i in range(75, 0, -1)]
        s = self.run_collect(FakeTransport({FIRST: ('', rows)}), comparison_mode='cross_ref', refs=['dev'])
        self.assertEqual(s['retained_job_ids'], list(range(75, 11, -1)))
        self.assertEqual(s['baseline_job_ids'], [11])
        self.assertEqual(s['source']['requests']['metadata'], 65)
        self.assertFalse(next(j for j in s['jobs'] if j['id'] == 10)['metadata_fresh'])

    def test_partial_budget_resume_preserves_anchor_counts_and_new_budget(self):
        t = FakeTransport({FIRST: (next_header(SECOND), [job(12), job(11)]), SECOND: ('', [job(11), job(10)])})
        first = self.run_collect(t, max_pages=1)
        self.assertEqual(first['source']['stop_reason'], 'page_budget')
        self.assertFalse(first['source']['complete_available_history'])
        self.assertEqual(first['source']['cursor'], SECOND)
        self.assertEqual(first['source']['observed_counts'][0]['count_kind'], 'lower_bound')
        resumed = self.run_collect(t, max_pages=1, resume=first)
        self.assertEqual([j['id'] for j in resumed['jobs']], [12, 11, 10])
        self.assertEqual(resumed['source']['anchor_max_job_id'], 12)
        self.assertEqual(resumed['source']['pages'], 2)
        self.assertEqual(resumed['source']['requests']['pages'], 2)
        self.assertTrue(resumed['source']['complete_available_history'])
        self.assertIsNotNone(resumed['source']['resumed_from_sha256'])

    def test_new_page_duplicates_and_cycles_reject(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.run_collect(FakeTransport({FIRST: ('', [job(2), job(2)])}))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.run_collect(FakeTransport({FIRST: (next_header(FIRST), [job(2)])}))

    def test_type_limit_preserves_ignored_projection_and_counts(self):
        t = FakeTransport({FIRST: ('', [job(3, name='a'), job(2, name='b'), job(1, name='b')])})
        s = self.run_collect(t, max_job_types=1)
        self.assertEqual(s['retained_job_ids'], [3])
        self.assertEqual(len(s['jobs']), 3)
        self.assertEqual(len(s['source']['observed_counts']), 2)
        self.assertEqual(s['jobs'][1]['metadata_error'], 'not_requested')
        self.assertEqual(len(s['pipelines']), 3)
        self.assertEqual(s['source']['stop_reason'], 'type_budget')

    def test_refresh_failures_and_metadata_trace_states(self):
        rows = [job(4), job(3, 'skipped'), job(2), job(1)]
        erased = job(2); erased['erased_at'] = AT
        t = FakeTransport({FIRST: ('', rows)}, fresh={2: erased}, errors={'projects/42/jobs/4': 'permission_denied', 'projects/42/jobs/1/trace': 'unavailable'})
        s = self.run_collect(t)
        states = {x['job_id']: x['state'] for x in s['traces']}
        self.assertEqual(states, {4: 'empty', 3: 'not_run', 2: 'erased', 1: 'unavailable'})
        self.assertEqual(s['source']['requests']['metadata'], 4)
        self.assertEqual(s['source']['requests']['traces'], 2)
        self.assertFalse(s['jobs'][0]['metadata_fresh'])
        self.assertEqual(s['jobs'][0]['metadata_error'], 'permission_denied')
        self.assertFalse(any(x.endswith('/2/trace') or x.endswith('/3/trace') for x in t.calls))

    def test_cache_reuses_only_unchanged_terminal_trace_after_fresh_metadata(self):
        t = FakeTransport({FIRST: ('', [job(1)])})
        old = self.run_collect(t)
        second = self.run_collect(t, cache=old)
        self.assertTrue(second['traces'][0]['cached'])
        self.assertEqual(second['source']['requests']['traces'], 0)
        self.assertEqual(second['source']['requests']['metadata'], 1)
        changed = FakeTransport({FIRST: ('', [job(1)])}, fresh={1: job(1, 'running')})
        third = self.run_collect(changed, cache=old)
        self.assertFalse(third['traces'][0]['cached'])
        self.assertEqual(third['source']['requests']['traces'], 1)

    def test_cache_age_erasure_and_smaller_trace_budgets_invalidate_reuse(self):
        old = self.run_collect(FakeTransport({FIRST: ('', [job(1)])}, traces={1: (b'unknown log', False)}))
        smaller = self.run_collect(FakeTransport({FIRST: ('', [job(1)])}, traces={1: (b'u', True)}), cache=old, trace_bytes=1)
        self.assertFalse(smaller['traces'][0]['cached'])
        self.assertEqual(smaller['traces'][0]['bytes_read'], 1)
        stale = copy.deepcopy(old)
        stale['traces'][0]['fetched_at'] = stale['traces'][0]['analyzed_at'] = '2026-10-01T00:00:00Z'
        updated = self.run_collect(FakeTransport({FIRST: ('', [job(1)])}), cache=stale)
        self.assertFalse(updated['traces'][0]['cached'])
        erased = job(1); erased['erased_at'] = AT
        updated = self.run_collect(FakeTransport({FIRST: ('', [job(1)])}, fresh={1: erased}), cache=old)
        self.assertEqual(updated['traces'][0]['state'], 'erased')
        self.assertEqual(updated['source']['requests']['traces'], 0)

    def test_pipeline_failure_keeps_projection_and_reruns_share_one_pipeline_request(self):
        rows = [job(2, 'failed'), job(1)]
        rows[1]['pipeline']['id'] = 2
        t = FakeTransport({FIRST: ('', rows)}, errors={'projects/42/pipelines/2': 'timeout'})
        s = self.run_collect(t)
        self.assertEqual(s['source']['requests']['pipelines'], 1)
        self.assertFalse(s['pipelines'][0]['metadata_fresh'])
        self.assertEqual(s['pipelines'][0]['metadata_error'], 'timeout')
        self.assertEqual(s['retained_job_ids'], [2, 1])

    def test_cache_with_unallowlisted_raw_data_is_rejected(self):
        old = self.run_collect(FakeTransport({FIRST: ('', [job(1)])}))
        old['traces'][0]['raw_log'] = 'private token'
        with self.assertRaises(ValueError):
            self.run_collect(FakeTransport({FIRST: ('', [job(1)])}), cache=old)

    def test_trace_caps_and_concurrency_reject_before_any_network_request(self):
        for options in ({'trace_bytes': 4194305}, {'trace_lines': 50001}, {'concurrency': 5}):
            t = FakeTransport({FIRST: ('', [])})
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    self.run_collect(t, **options)
                self.assertEqual(t.calls, [])

    def test_crossref_requires_explicit_selection_and_selector_raw_names(self):
        with self.assertRaises(ValueError):
            self.run_collect(FakeTransport({FIRST: ('', [])}), comparison_mode='cross_ref')
        rows = [job(3, name='build/foo', stage='test/bar'), job(2), job(1, name='build/foo', stage='test/bar')]
        s = self.run_collect(FakeTransport({FIRST: ('', rows)}), job_selectors=[{'stage': 'test/bar', 'name': 'build/foo'}])
        self.assertEqual(s['retained_job_ids'], [3, 1])

class TransportTests(unittest.TestCase):
    def test_original_crlf_body_is_preserved_for_hashes(self):
        self.assertIsNotNone(collector)
        headers, body = collector._response(b'HTTP/2.0 200 OK\r\nContent-Type: text/plain\r\n\r\na\r\nb\r\n')
        self.assertEqual(body, b'a\r\nb\r\n')

    def test_trace_stdout_is_capped_by_bytes_and_physical_lines(self):
        self.assertIsNotNone(collector)
        transport = collector.GlabTransport(HOST)
        script = "import sys; sys.stdout.buffer.write(b'HTTP/1.1 200 OK\\r\\n\\r\\n' + b'a\\r\\n' * 1000000)"
        with patch.object(transport, '_command', return_value=[sys.executable, '-c', script]):
            raw, truncated = transport.trace('trace', 100, 2)
        self.assertEqual(raw, b'a\r\na\r\n')
        self.assertTrue(truncated)
        with patch.object(transport, '_command', return_value=[sys.executable, '-c', script]):
            raw, truncated = transport.trace('trace', 4, 50)
        self.assertEqual(raw, b'a\r\na')
        self.assertTrue(truncated)

    def test_status_errors_never_expose_body(self):
        self.assertIsNotNone(collector)
        for status, code in [(404, 'unavailable'), (403, 'permission_denied')]:
            with self.assertRaises(collector.TransportError) as caught:
                collector._response(f'HTTP/1.1 {status} Error\n\nsecret token'.encode())
            self.assertEqual(str(caught.exception), code)

if __name__ == '__main__':
    unittest.main()
