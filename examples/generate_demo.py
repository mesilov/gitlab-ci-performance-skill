"""Build a fictional project and its report; no network or GitLab account."""
import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_report', ROOT / 'skills/gitlab-ci-performance/scripts/ci_report.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def iso(value):
    return value.isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'reports/demo')
    out = parser.parse_args().output_dir
    project = {'id': 42, 'path': 'example/demo-service', 'host': 'gitlab.example.com',
               'web_url': 'https://gitlab.example.com/example/demo-service', 'default_branch': 'main'}
    jobs, pipelines = [], []
    names = ['build', 'unit_tests', 'lint', 'integration_tests', 'security_scan']
    base = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    for index in range(8):
        pid = 101 + index
        created = base + timedelta(days=index)
        latest = index == 7
        durations = [120 + index, 900 if latest else 210 + index * 3, 25 + index, 310 + index * 2, 40 + index]
        queues = [180 if latest else 5 + index, 5 + index, 2, 10, 3]
        offsets = [0] + [queues[0] + durations[0]] * 4
        pipeline_jobs = []
        for number, name in enumerate(names):
            jid = pid * 10 + number
            job_created = created
            started = created + timedelta(seconds=offsets[number] + queues[number])
            pipeline_jobs.append({'id': jid, 'pipeline_id': pid, 'name': name,
                         'stage': 'build' if name == 'build' else 'test', 'ref': 'main', 'status': 'success',
                         'allow_failure': False, 'created_at': iso(job_created), 'started_at': iso(started),
                         'finished_at': iso(started + timedelta(seconds=durations[number])),
                         'duration_seconds': durations[number], 'queued_seconds': queues[number],
                         'failure_reason': None, 'runner': {'id': 1, 'description': 'demo-runner'},
                         'web_url': project['web_url'] + f'/-/jobs/{jid}'})
        intervals = sorted((ci.timestamp(j['started_at']), ci.timestamp(j['finished_at'])) for j in pipeline_jobs)
        merged = []
        for start, finish in intervals:
            if merged and start <= merged[-1][1]: merged[-1][1] = max(finish, merged[-1][1])
            else: merged.append([start, finish])
        execution = sum((finish-start).total_seconds() for start, finish in merged)
        pipelines.append({'id': pid, 'ref': 'main', 'sha': f'{pid:040x}', 'status': 'success', 'source': 'push',
                          'created_at': iso(created), 'started_at': iso(intervals[0][0]),
                          'finished_at': iso(max(finish for start, finish in intervals)),
                          'duration_seconds': execution, 'queued_seconds': queues[0],
                          'web_url': project['web_url'] + f'/-/pipelines/{pid}'})
        jobs.extend(pipeline_jobs)
    collected = iso(base + timedelta(days=8))
    snapshot = {'schema_version': '1.0.0', 'kind': 'jobs', 'collection_started_at': collected,
                'collected_at': collected, 'timezone': 'UTC', 'project': project,
                'source': {'transport': 'glab', 'glab_version': 'synthetic-demo', 'gitlab_version': 'synthetic-demo',
                           'anchor_max_job_id': max(j['id'] for j in jobs), 'pages': 1,
                           'complete_available_history': True, 'limitations': ['Synthetic demonstration data; not collected from GitLab']},
                'jobs': list(reversed(jobs)), 'pipelines': list(reversed(pipelines))}
    descriptions = {'build': 'Собирает образ приложения.', 'unit_tests': 'Проверяет приложение unit-тестами.',
                    'lint': 'Проверяет стиль и статические ошибки кода.', 'integration_tests': 'Проверяет взаимодействие компонентов.',
                    'security_scan': 'Проверяет зависимости на известные уязвимости.'}
    catalog = {'project': project['path'], 'jobs': {name: {'description': text,
               'source_url': project['web_url'] + '/-/blob/main/.gitlab-ci.yml', 'verified_at': collected}
               for name, text in descriptions.items()}}
    ci.save(out/'jobs.json', snapshot, 'jobs')
    ci.save(out/'catalog.json', catalog)
    report = ci.build_report(snapshot, catalog=catalog)
    ci.save(out/'report.json', report, 'report')
    ci.render(report, out/'report.html')


if __name__ == '__main__':
    main()
