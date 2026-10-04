import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ci_report", ROOT / "skills/gitlab-ci-performance/scripts/ci_report.py")
ci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci)


def sample(durations=(100, 100, 100, 150), queues=(5, 5, 5, 50)):
    project = {"id": 42, "path": "example/service", "host": "gitlab.example.com",
               "web_url": "https://gitlab.example.com/example/service", "default_branch": "main"}
    result = {"schema_version": "1.0.0", "kind": "jobs", "collection_started_at": "2026-10-01T00:00:00Z",
              "collected_at": "2026-10-04T00:00:00Z", "timezone": "UTC", "project": project,
              "source": {"transport": "glab", "glab_version": "fixture", "gitlab_version": "fixture",
                         "anchor_max_job_id": len(durations) or None, "pages": 1, "complete_available_history": True,
                         "limitations": []}, "jobs": [], "pipelines": []}
    for i, (duration, queue) in enumerate(zip(durations, queues), 1):
        result["pipelines"].append({"id": i, "ref": "main", "sha": "abc", "status": "success", "source": "push",
                                     "created_at": f"2026-10-01T0{i}:00:00Z", "started_at": f"2026-10-01T0{i}:00:01Z",
                                     "finished_at": f"2026-10-01T0{i}:05:00Z", "duration_seconds": duration,
                                     "queued_seconds": queue, "web_url": f"https://gitlab.example.com/pipelines/{i}"})
        result["jobs"].append({"id": i, "pipeline_id": i, "name": "build", "stage": "test", "ref": "main",
                               "status": "success", "allow_failure": False, "created_at": f"2026-10-01T0{i}:00:00Z",
                               "started_at": f"2026-10-01T0{i}:01:00Z", "finished_at": f"2026-10-01T0{i}:05:00Z",
                               "duration_seconds": duration, "queued_seconds": queue, "failure_reason": None,
                               "runner": None, "web_url": f"https://gitlab.example.com/jobs/{i}"})
    return result


class MetricsTests(unittest.TestCase):
    def test_percentiles_interpolate_and_nulls_are_not_zero(self):
        m = ci.metric([10, None, 20, 30, 40])
        self.assertEqual((m["known"], m["missing"], m["sum_seconds"]), (4, 1, 100))
        self.assertEqual(m["p50_seconds"], 25)
        self.assertEqual(m["p95_seconds"], 38.5)
        self.assertIsNone(ci.metric([None])["sum_seconds"])

    def test_queue_and_execution_regressions_are_separate(self):
        snapshot = sample(durations=(100, 100, 100, 100))
        g = ci.build_report(snapshot, windows=(1,))["views"][0]["groups"][0]
        self.assertEqual(g["drivers"], ["queue"])
        self.assertEqual(g["execution_change"]["status"], "stable")

    def test_both_thresholds_are_required(self):
        self.assertEqual(ci.compare(ci.metric([121]), ci.metric([100]*3), ci.POLICY)["status"], "stable")
        self.assertEqual(ci.compare(ci.metric([1150]), ci.metric([1000]*3), ci.POLICY)["status"], "stable")
        self.assertEqual(ci.compare(ci.metric([150]), ci.metric([100]*3), ci.POLICY)["status"], "regressed")

    def test_zero_threshold_does_not_flag_unchanged_time(self):
        policy = dict(ci.POLICY, absolute_growth_seconds=0, relative_growth_percent=0)
        self.assertEqual(ci.compare(ci.metric([100]), ci.metric([100]*3), policy)["status"], "stable")

    def test_sparse_baseline_and_zero_are_explicit(self):
        self.assertEqual(ci.compare(ci.metric([500]), ci.metric([100]), ci.POLICY)["status"], "insufficient_data")
        c = ci.compare(ci.metric([40]), ci.metric([0]*3), ci.POLICY)
        self.assertEqual(c["status"], "regressed")
        self.assertIsNone(c["delta_percent"])

    def test_null_measurements_do_not_mean_missing_job(self):
        snapshot = sample(durations=(100, 100, 100, None))
        g = ci.build_report(snapshot, windows=(1,))["views"][0]["groups"][0]
        self.assertEqual(g["execution_change"]["status"], "insufficient_data")
        self.assertEqual(g["current"]["execution"]["missing"], 1)

    def test_failed_attempts_and_reruns_are_preserved(self):
        s = sample()
        retry = copy.deepcopy(s["jobs"][-1]);retry["id"] = 5;retry["status"] = "failed";retry["duration_seconds"] = 999
        s["jobs"].append(retry)
        g = ci.build_report(s, windows=(1,))["views"][0]["groups"][0]
        self.assertEqual(g["current"]["rerun_attempts"], 1)
        self.assertEqual(g["current"]["status_counts"], {"success": 1, "failed": 1})
        self.assertEqual(g["current"]["execution"]["p50_seconds"], 150)

    def test_failed_pipeline_is_latest_but_not_timing_cohort(self):
        s = sample();s["pipelines"][-1]["status"] = "failed"
        v = ci.build_report(s, windows=(1,))["views"][0]
        self.assertEqual(v["latest_pipeline"]["id"], 4)
        self.assertEqual(v["current_period"]["pipeline_ids"], [3])

    def test_ref_and_stage_do_not_mix(self):
        s = sample();s["pipelines"][-1]["ref"] = "dev";s["jobs"][-1]["ref"] = "dev"
        report = ci.build_report(s, windows=(1,))
        for v in report["views"]:
            self.assertTrue(all(g["ref"] == v["ref"] for g in v["groups"]))
        s["jobs"][-2]["stage"] = "deploy"
        self.assertEqual(len(ci.build_report(s, windows=(10,))["views"][1]["groups"]), 2)

    def test_snapshot_overlap_prevents_regression(self):
        s = sample();v = ci.build_report(s, baseline=s, windows=(1,))["views"][0]
        self.assertEqual(v["overlap_pipeline_ids"], [4])
        self.assertEqual(v["regression_count"], 0)
        self.assertEqual(v["groups"][0]["queue_change"]["status"], "overlap")

    def test_different_project_and_newer_baseline_are_rejected(self):
        s = sample();b = copy.deepcopy(s);b["project"]["id"] = 99
        with self.assertRaisesRegex(ValueError, "different host/project"):ci.build_report(s, b)
        b = copy.deepcopy(s);b["collected_at"] = "2026-10-05T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "newer"):ci.build_report(s, b)

    def test_disjoint_saved_snapshots_compare(self):
        s = sample();b = copy.deepcopy(s);b["jobs"] = b["jobs"][:-1];b["pipelines"] = b["pipelines"][:-1]
        v = ci.build_report(s, baseline=b, windows=(1,))["views"][0]
        self.assertEqual(v["regression_count"], 1)
        self.assertEqual(v["overlap_pipeline_ids"], [])

    def test_empty_snapshot_and_unknown_purpose(self):
        s = sample((), ());report = ci.build_report(s)
        self.assertEqual(report["views"][0]["situation"], "insufficient_data")
        self.assertIn("not documented", ci.build_report(sample())["views"][0]["groups"][0]["purpose"]["description"])


class ContractAndTransportTests(unittest.TestCase):
    def test_schema_rejects_wrong_version_unknown_fields_negative_and_duplicate(self):
        for mutate in (lambda s:s.update(schema_version="2"), lambda s:s.update(token="secret"),
                       lambda s:s["jobs"][0].update(duration_seconds=-1),
                       lambda s:s["jobs"].append(copy.deepcopy(s["jobs"][0]))):
            s = sample();mutate(s)
            with self.assertRaises(ValueError):ci.validate(s, "jobs")

    def test_schema_rejects_nonfinite_timing_and_wrong_relation(self):
        for val in [float('nan'), float('inf')]:
            s = sample();s['jobs'][0]['duration_seconds'] = val
            with self.assertRaises(ValueError):ci.validate(s, 'jobs')
        s = sample();s['jobs'][0]['pipeline_id'] = 99
        with self.assertRaises(ValueError):ci.validate(s, 'jobs')

    def test_projection_removes_secrets_and_user_data(self):
        raw = {"id": 1, "pipeline": {"id": 1}, "name": "job", "stage": "test", "ref": "main",
               "status": "success", "created_at": "2026-10-01T00:00:00Z", "web_url": "https://example.com/job",
               "user": {"email": "private"}, "variables": [{"value": "secret"}], "commit": {"message": "private"},
               "runner": {"id": 2, "description": "runner", "ip_address": "private"}}
        out = ci.project_job(raw)
        self.assertNotIn('private', json.dumps(out));self.assertNotIn('secret', json.dumps(out))

    def test_pagination_only_same_project_host_https_without_token(self):
        h = '<https://gitlab.example.com/api/v4/projects/42/jobs?id_before=100>; rel="next"'
        self.assertIn('id_before=100', ci.next_page(h, 'gitlab.example.com', 42))
        for change in [h.replace('gitlab.example.com', 'evil.com'), h.replace('/42/', '/99/'),
                       h.replace('https:', 'http:'), h.replace('id_before=100', 'private_token=x')]:
            with self.assertRaises(ValueError):ci.next_page(change, 'gitlab.example.com', 42)

    def test_collection_rejects_cycle_before_saving_partial_history(self):
        p = {"id": 42, "path_with_namespace": "example/service", "web_url": "https://gitlab.example.com/backend", "default_branch": "main"}
        cycle = '<https://gitlab.example.com/api/v4/projects/42/jobs?per_page=100&pagination=keyset&order_by=id&sort=desc>; rel="next"'
        with patch.object(ci, 'request', side_effect=[('', p), ('', {'version': 'test'}), (cycle, [])]):
            with self.assertRaisesRegex(ValueError, "limit/cycle"):
                ci.collect('gitlab.example.com', 'example/service', 'UTC')

    def test_collection_rejects_duplicate_across_pages(self):
        p = {"id": 42, "path_with_namespace": "example/service", "web_url": "https://gitlab.example.com/backend", "default_branch": "main"}
        j = {"id": 1, "pipeline": {"id": 1}, "name": "build", "stage": "test", "ref": "main", "status": "success", "created_at": "2026-10-01T00:00:00Z", "web_url": "https://gitlab.example.com/jobs/1"}
        link = '<https://gitlab.example.com/api/v4/projects/42/jobs?id_before=1>; rel="next"'
        with patch.object(ci, 'request', side_effect=[('', p), ('', {'version': 'test'}), (link, [j]), ('', [j])]):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                ci.collect('gitlab.example.com', 'example/service', 'UTC')

    def test_no_overwrite_and_html_script_boundary_escape(self):
        s = sample();s['jobs'][0]['name'] = '</script><img src=x onerror=alert(1)>'
        report = ci.build_report(s)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'jobs.json';ci.save(path,s,'jobs')
            with self.assertRaises(ValueError):ci.save(path,s,'jobs')
            html = Path(d)/'report.html';ci.render(report,html)
            self.assertNotIn('</script><img', html.read_text())
            self.assertIn('\\u003c/script', html.read_text())
            with self.assertRaises(ValueError):ci.render(report,html)

    def test_collection_cli_uses_utc_unless_timezone_is_explicit(self):
        import sys
        args = ['ci_report.py', 'collect', '--host', 'gitlab.example.com', '--project', 'example/service', '--output', 'ignored.json']
        for extra, expected in [([], 'UTC'), (['--timezone', 'Europe/Berlin'], 'Europe/Berlin')]:
            with patch.object(sys, 'argv', args + extra), patch.object(ci, 'collect', return_value=sample()) as collect, patch.object(ci, 'save'):
                ci.main()
                self.assertEqual(collect.call_args.args[2], expected)

    def test_raw_json_nan_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad.json';path.write_text('{"x": NaN}')
            with self.assertRaises(ValueError):ci.load(path)


class ReportLanguageTests(unittest.TestCase):
    def test_fallback_origin_does_not_depend_on_catalog_text_or_nullable_provenance(self):
        s = sample()
        fallback = {'description': 'Purpose is not documented in the verified catalog.',
                    'source_url': None, 'verified_at': None}
        catalog = {'project': s['project']['path'], 'jobs': {'build': fallback}}
        supplied = ci.build_report(s, catalog=catalog)['views'][0]['groups'][0]
        missing = ci.build_report(s)['views'][0]['groups'][0]
        self.assertTrue(supplied.get('purpose_from_catalog'))
        self.assertIs(missing.get('purpose_from_catalog'), False)
        self.assertEqual(supplied['purpose'], fallback)

    def test_render_defaults_to_english_and_localizes_russian_without_changing_data(self):
        s = sample()
        s['jobs'][0]['name'] = 'job __LANGUAGE__ __TEXT:execution_p50__ __REPORT_I18N__ </script><img src=x> русский'
        catalog = {'project': s['project']['path'], 'jobs': {
            'build': {'description': 'Verified original description', 'source_url': None, 'verified_at': None}}}
        report = ci.build_report(s, catalog=catalog)
        original = copy.deepcopy(report)
        with tempfile.TemporaryDirectory() as d:
            for language, title in [('en', 'How CI is performing'), ('ru', 'Как работает CI')]:
                path = Path(d) / f'{language}.html'
                if language == 'en':
                    ci.render(report, path)
                else:
                    ci.render(report, path, language=language)
                html = path.read_text()
                self.assertIn(f'<html lang="{language}">', html)
                self.assertIn(f'<h1>{title}</h1>', html)
                self.assertNotRegex(html.split('<script id="report-data"')[0], r'__TEXT:[a-z0-9_]+__')
                embedded = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.S)
                self.assertEqual(json.loads(embedded.group(1)), original)
                self.assertNotIn('</script><img', html)
        self.assertEqual(report, original)

    def test_render_rejects_unsupported_language_before_creating_output(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'nested' / 'report.html'
            with self.assertRaisesRegex(ValueError, 'language'):
                ci.render(ci.build_report(sample()), path, language='de')
            self.assertFalse(path.parent.exists())

    def test_render_cli_language_default_choices_and_help(self):
        script = str(ci.ROOT / 'scripts' / 'ci_report.py')
        with tempfile.TemporaryDirectory() as d:
            report = Path(d) / 'report.json'
            ci.save(report, ci.build_report(sample()), 'report')
            for extra, expected in [([], 'en'), (['--language', 'en'], 'en'), (['--language', 'ru'], 'ru')]:
                path = Path(d) / ('report-' + str(len(list(Path(d).glob('*.html')))) + '.html')
                result = subprocess.run([sys.executable, script, 'render', '--report', str(report),
                                         '--output', str(path)] + extra, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'<html lang="{expected}">', path.read_text())
            invalid = Path(d) / 'invalid.html'
            result = subprocess.run([sys.executable, script, 'render', '--report', str(report),
                                     '--output', str(invalid), '--language', 'de'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('invalid choice', result.stderr)
            self.assertFalse(invalid.exists())
        help_result = subprocess.run([sys.executable, script, 'render', '--help'], capture_output=True, text=True)
        self.assertIn('--language {en,ru}', help_result.stdout)
        self.assertIn('default: en', ' '.join(help_result.stdout.split()))


if __name__ == '__main__':unittest.main()
