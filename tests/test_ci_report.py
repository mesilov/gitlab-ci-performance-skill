"""Tests for skills/gitlab-ci-performance. Standard library only:

    python3 -m unittest tests.test_ci_report -v
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/gitlab-ci-performance/scripts'))
import ci_report  # noqa: E402

DEMO = ROOT / 'examples/data.json'

LOG = (
    b'2026-10-14T09:00:00.000000Z 00O \x1b[0Ksection_start:1791968400:get_sources\r\x1b[0K\x1b[36;1mGetting source\x1b[0;m\n'
    b'2026-10-14T09:00:09.000000Z 00O \x1b[0Ksection_end:1791968409:get_sources\r\x1b[0K'
    b'\x1b[0Ksection_start:1791968409:step_script\r\x1b[0K\x1b[36;1mExecuting "step_script"\x1b[0;m\n'
    b'2026-10-14T09:00:09.500000Z 00O \x1b[32;1m$ composer install\x1b[0;m\n'
    b'2026-10-14T09:00:50.500000Z 00O \x1b[32;1m$ docker buildx build .\x1b[0;m\n'
    b'2026-10-14T09:00:51.000000Z 00O #1 [internal] load build definition\n'
    b'2026-10-14T09:00:51.100000Z 00O #1 DONE 0.1s\n'
    b'2026-10-14T09:00:51.200000Z 00O #2 [1/3] FROM docker.io/library/php:8.3\n'
    b'2026-10-14T09:00:51.300000Z 00O #2 CACHED\n'
    b'2026-10-14T09:00:51.400000Z 00O #3 [2/3] RUN composer install --no-dev\n'
    b'2026-10-14T09:00:52.000000Z 00O #3 0.412 Installing dependencies\n'
    b'2026-10-14T09:02:03.000000Z 00O #3 DONE 71.9s\n'
    b'2026-10-14T09:02:04.000000Z 00O \x1b[32;1m$ echo done\x1b[0;m\n'
    b'2026-10-14T09:02:10.000000Z 00O \x1b[0Ksection_end:1791968530:step_script\r\x1b[0K\n'
)


def job(number, name, status='success', run=60, wait=5, start='2026-10-14T09:00:00Z', stage='test'):
    began = ci_report.ts(start)
    stamp = ci_report.datetime.fromtimestamp
    utc = ci_report.timezone.utc
    return {'id': number, 'name': name, 'stage': stage, 'status': status, 'duration': run,
            'queued_duration': wait, 'web_url': f'https://gitlab.example.com/x/-/jobs/{number}',
            'started_at': stamp(began, utc).isoformat(), 'finished_at': stamp(began + run, utc).isoformat()}


def data_with(pipelines, logs=None):
    return {'host': 'gitlab.example.com', 'project': 'group/x', 'project_url': 'https://gitlab.example.com/group/x',
            'ref': 'main', 'source': None, 'collected_at': '2026-11-13T10:00:00Z',
            'pipelines': [{'id': number, 'status': status, 'source': 'push', 'ref': 'main',
                           'created_at': '2026-10-14T09:00:00Z',
                           'web_url': f'https://gitlab.example.com/x/-/pipelines/{number}', 'jobs': jobs}
                          for number, (status, jobs) in enumerate(pipelines, 1)],
            'logs': logs or {}}


class LogTest(unittest.TestCase):
    def test_sections_commands_and_build_steps(self):
        log = ci_report.parse_log(LOG)
        self.assertEqual(log['sections'], [{'name': 'get_sources', 'seconds': 9},
                                           {'name': 'step_script', 'seconds': 121}])
        self.assertEqual(log['steps'], [
            {'name': '$ composer install', 'seconds': 41.0},
            {'name': '[internal] load build definition', 'seconds': 0.1},
            {'name': '[2/3] RUN composer install --no-dev', 'seconds': 71.9},
            {'name': '$ echo done', 'seconds': 6.0},   # ends with its section
        ])

    def test_command_that_wraps_build_steps_is_left_out(self):
        names = [step['name'] for step in ci_report.parse_log(LOG)['steps']]
        self.assertNotIn('$ docker buildx build .', names)

    def test_command_ends_with_its_phase(self):
        # Seen on gitlab.com: a runner hook prints "$ git remote set-url" inside get_sources,
        # then the cache restores for minutes. That time is not the command's.
        log = ci_report.parse_log(
            b'2026-10-14T09:00:00.0Z 00O section_start:1791968400:get_sources\r\x1b[0K\n'
            b'2026-10-14T09:00:01.0Z 01O \x1b[32;1m$ git remote set-url origin "$URL"\x1b[0;m\n'
            b'2026-10-14T09:00:03.0Z 00O section_end:1791968403:get_sources\r\x1b[0K\n'
            b'2026-10-14T09:00:03.0Z 00O section_start:1791968403:restore_cache\r\x1b[0K\n'
            b'2026-10-14T09:05:50.0Z 00O section_end:1791968750:restore_cache\r\x1b[0K\n'
            b'2026-10-14T09:05:50.0Z 00O section_start:1791968750:step_script\r\x1b[0K\n'
            b'2026-10-14T09:05:51.0Z 01O \x1b[32;1m$ make test\x1b[0;m\n'
            b'2026-10-14T09:07:00.0Z 00O section_end:1791968820:step_script\r\x1b[0K\n')
        self.assertEqual(log['steps'], [{'name': '$ git remote set-url origin "$URL"', 'seconds': 2.0},
                                        {'name': '$ make test', 'seconds': 69.0}])
        row = {'sample': {'id': 1}}
        self.assertEqual(ci_report.longest_step(row, {'1': log}), {'name': 'restore_cache', 'seconds': 347})

    def test_docker_build_details_from_a_real_log(self):
        # A job that builds two images in a loop. BuildKit repeats the header and DONE of one
        # step with a growing total, starts numbering again for the next build, and splits
        # "exporting to image" into timed parts.
        log = ci_report.parse_log(b'\n'.join([
            b'#1 [internal] load build definition from Dockerfile', b'#1 DONE 0.1s',
            b'#7 [1/8] FROM registry.example.com/php:8.4', b'#7 resolve registry.example.com/php:8.4 done',
            b'#7 DONE 2.6s',
            b'#7 [1/8] FROM registry.example.com/php:8.4', b'#7 sha256:7a1e 93B / 93B 0.1s done', b'#7 DONE 5.5s',
            b'#7 [1/8] FROM registry.example.com/php:8.4', b'#7 DONE 14.2s',
            b'#16 exporting to image', b'#16 exporting layers', b'#16 exporting layers 271.6s done',
            b'#16 exporting manifest sha256:e8fa 0.0s done', b'#16 unpacking to registry.example.com/app/php:1',
            b'#16 unpacking to registry.example.com/app/php:1 248.3s done', b'#16 DONE 520.1s',
            b'#1 [internal] load build definition from Dockerfile', b'#1 DONE 0.2s',
            b'#7 [internal] load build context', b'#7 [internal] load build context', b'#7 DONE 282.6s',
        ]))
        self.assertEqual(log['steps'], [
            {'name': 'build 1: [internal] load build definition from Dockerfile', 'seconds': 0.1},
            {'name': 'build 1: [1/8] FROM registry.example.com/php:8.4', 'seconds': 14.2},
            {'name': 'build 1: exporting layers', 'seconds': 271.6},
            {'name': 'build 1: unpacking to registry.example.com/app/php:1', 'seconds': 248.3},
            {'name': 'build 2: [internal] load build definition from Dockerfile', 'seconds': 0.2},
            {'name': 'build 2: [internal] load build context', 'seconds': 282.6},
        ])

    def test_without_timestamps_commands_are_not_timed(self):
        plain = b'\n'.join(line.split(b' 00O ', 1)[1] for line in LOG.split(b'\n') if line) + b'\n'
        log = ci_report.parse_log(plain)
        self.assertEqual([part['name'] for part in log['sections']], ['get_sources', 'step_script'])
        self.assertEqual([step['seconds'] for step in log['steps']], [0.1, 71.9])

    def test_garbage_is_not_an_error(self):
        self.assertEqual(ci_report.parse_log(b'\xff\xfe section_end:5:never_opened\n#x y\n'),
                         {'sections': [], 'steps': []})


class MathTest(unittest.TestCase):
    def test_squeeze_counts_overlap_once_and_drops_gaps(self):
        total, at = ci_report.squeeze([(0, 10), (5, 20), (1000, 1010)])
        self.assertEqual(total, 30)
        self.assertEqual([at(0), at(20), at(500), at(1005)], [0, 20, 20, 25])

    def test_change_needs_three_runs_on_each_side(self):
        self.assertIsNone(ci_report.change([100] * 5))
        self.assertEqual(ci_report.change([100] * 6)['recent'], 3)

    def test_change_is_notable_only_above_both_thresholds(self):
        self.assertTrue(ci_report.change([100] * 3 + [150] * 3)['notable'])    # +50 s, +50%
        self.assertFalse(ci_report.change([100] * 3 + [125] * 3)['notable'])   # +25%, but under 30 s
        self.assertFalse(ci_report.change([1000] * 3 + [1100] * 3)['notable'])  # +100 s, but under 20%
        self.assertTrue(ci_report.change([150] * 3 + [100] * 3)['notable'])    # faster counts too

    def test_durations_read_naturally(self):
        L = ci_report.T['en']
        self.assertEqual([ci_report.dur(value, L) for value in (None, 0, 0.4, 59.6, 90, 600, 3660)],
                         ['—', '0 s', '<1 s', '1 min', '1 min 30 s', '10 min', '1 h 1 min'])

    def test_remote_urls(self):
        for url in ('git@gitlab.example.com:group/sub/x.git', 'https://gitlab.example.com/group/sub/x.git',
                    'ssh://git@gitlab.example.com:2222/group/sub/x.git',
                    'https://user:secret@gitlab.example.com/group/sub/x'):
            self.assertEqual(ci_report.parse_remote(url), ('gitlab.example.com', 'group/sub/x'), url)
        self.assertEqual(ci_report.parse_remote(''), (None, None))


class AnalyzeTest(unittest.TestCase):
    def test_pipeline_time_is_the_union_of_running_jobs(self):
        jobs = [job(1, 'a', run=60), job(2, 'b', run=100), job(3, 'c', run=30, start='2026-10-14T12:00:00Z'),
                dict(job(4, 'manual'), status='manual', started_at=None, finished_at=None, duration=None)]
        result = ci_report.analyze(data_with([('success', jobs)]))
        self.assertEqual(result['typical'], 130)   # a and b overlap; the 3-hour pause is not counted
        self.assertEqual([row['name'] for row in result['jobs']], ['b', 'a', 'c'])   # slowest first, no "manual"

    def test_medians_ignore_failed_runs(self):
        pipelines = [('success', [job(n, 'unit', run=100)]) for n in range(1, 6)]
        pipelines.append(('failed', [job(9, 'unit', 'failed', run=5)]))
        result = ci_report.analyze(data_with(pipelines))
        self.assertEqual((result['typical'], result['ok'], result['total']), (100, 5, 6))
        self.assertEqual((result['jobs'][0]['run'], result['jobs'][0]['failed']), (100, 1))

    def test_demo_points_at_the_right_jobs(self):
        data = json.loads(DEMO.read_text(encoding='utf-8'))
        first = {what: row['name'] for what, row, _ in ci_report.analyze(data)['first']}
        self.assertEqual(first, {'slow': 'build-image', 'grew': 'phpunit', 'wait': 'e2e', 'fail': 'e2e'})

    def test_quiet_project_has_one_finding(self):
        pipelines = [('success', [job(n, 'unit', run=100)]) for n in range(1, 9)]
        self.assertEqual([what for what, _, _ in ci_report.analyze(data_with(pipelines))['first']], ['slow'])


class ReportTest(unittest.TestCase):
    def render(self, data, lang='en'):
        return ci_report.render_html(data, ci_report.analyze(data), ci_report.T[lang], lang)

    def test_demo_report_in_both_languages(self):
        data = json.loads(DEMO.read_text(encoding='utf-8'))
        for lang, words in (('en', ('Where to look first', 'got slower')), ('ru', ('С чего начать', 'стала дольше'))):
            page = self.render(data, lang)
            for word in words + ('build-image', 'RUN composer install'):
                self.assertIn(word, page)
            for junk in ('None', 'nan', '{', '<script'):
                self.assertNotIn(junk, page.split('</style>')[1], f'{junk!r} leaked into the {lang} report')

    def test_names_from_gitlab_are_escaped(self):
        evil = '<img src=x onerror=alert(1)>'
        runs = [('success', [job(n, evil, stage=evil)]) for n in range(1, 4)]
        logs = {'3': {'sections': [{'name': evil, 'seconds': 9}], 'steps': [{'name': '$ ' + evil, 'seconds': 9}]}}
        data = data_with(runs, logs)
        data['project'] = data['ref'] = evil
        page = self.render(data)
        self.assertNotIn('<img', page)
        self.assertIn('&lt;img', page)

    def test_no_successful_pipeline_still_renders(self):
        page = self.render(data_with([('failed', [job(1, 'unit', 'failed')])]))
        self.assertIn('no typical run time', page)

    def test_cli_rebuilds_report_from_saved_data(self):
        with tempfile.TemporaryDirectory() as out, redirect_stdout(io.StringIO()) as printed:
            ci_report.main(['--from', str(DEMO), '--out', out, '--lang', 'ru'])
            self.assertTrue((Path(out) / 'report.html').stat().st_size > 10_000)
            self.assertFalse((Path(out) / 'data.json').exists())   # the source file is not copied
        self.assertIn('С чего начать', printed.getvalue())


class CollectTest(unittest.TestCase):
    def test_reads_pipelines_jobs_and_the_slowest_logs(self):
        asked = []

        def fake_glab(host, endpoint):
            asked.append(endpoint)
            if endpoint == 'projects/group%2Fx':
                return json.dumps({'default_branch': 'main', 'path_with_namespace': 'group/x',
                                   'web_url': 'https://gitlab.example.com/group/x'}).encode()
            if '/pipelines?' in endpoint:
                return json.dumps([{'id': 7, 'status': 'success', 'source': 'push', 'ref': 'main',
                                    'created_at': '2026-10-14T09:00:00Z', 'web_url': 'u', 'yaml_errors': None}]).encode()
            if endpoint.endswith('/trace'):
                return LOG
            return json.dumps([dict(job(1, 'slow', run=121), secret='x'), job(2, 'fast', run=5)]).encode()

        with mock.patch.object(ci_report, 'glab', fake_glab):
            data = ci_report.collect('gitlab.example.com', 'group/x', None, 'push', 30, logs=1)
        self.assertEqual(asked, [
            'projects/group%2Fx',
            'projects/group%2Fx/pipelines?scope=finished&per_page=30&source=push&ref=main',
            'projects/group%2Fx/pipelines?scope=finished&per_page=30&source=push',   # is CI on other refs?
            'projects/group%2Fx/pipelines/7/jobs?include_retried=true&per_page=100&page=1',
            'projects/group%2Fx/jobs/1/trace',
        ])
        self.assertEqual(list(data['logs']), ['1'])
        self.assertNotIn('secret', data['pipelines'][0]['jobs'][0])
        self.assertNotIn('yaml_errors', data['pipelines'][0])
        json.dumps(data)   # data.json must be plain JSON

    def test_says_when_ci_runs_on_other_refs(self):
        # Seen on a project that builds on release tags: the default branch had almost nothing.
        notes = []
        one = {'id': 7, 'status': 'success', 'source': 'push', 'ref': 'main',
               'created_at': '2026-10-14T09:00:00Z', 'web_url': 'u'}

        def fake_glab(host, endpoint):
            if endpoint == 'projects/group%2Fx':
                return json.dumps({'default_branch': 'main', 'path_with_namespace': 'group/x', 'web_url': 'u'}).encode()
            if '/pipelines?' in endpoint:
                return json.dumps([one] if 'ref=main' in endpoint else [one] * 30).encode()
            return json.dumps([job(1, 'unit')]).encode()

        with mock.patch.object(ci_report, 'glab', fake_glab):
            ci_report.collect('gitlab.example.com', 'group/x', None, None, 30, logs=0, note=notes.append)
            self.assertTrue(any('Only 1 of the last 30' in text and '--any-ref' in text for text in notes), notes)
            notes.clear()
            ci_report.collect('gitlab.example.com', 'group/x', '', None, 30, logs=0, note=notes.append)
            self.assertFalse(any('--any-ref' in text for text in notes))   # already reading every ref


if __name__ == '__main__':
    unittest.main()
