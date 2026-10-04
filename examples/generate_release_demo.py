"""Generate a generic multi-tag fixture without GitLab access."""
import argparse
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/gitlab-ci-performance/scripts'))
import ci_report as ci


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'reports/release-demo')
    out = parser.parse_args().output_dir
    snapshot = ci.load(ROOT / 'examples/jobs.json')
    snapshot['jobs'], snapshot['pipelines'] = [], []
    snapshot['source']['limitations'] = ['Synthetic multi-tag demonstration; not collected from GitLab']
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    project = snapshot['project']
    for i in range(70):
        pid, ref = 201 + i, f'v1.{i}'
        created = base + timedelta(days=i)
        status = 'failed' if i == 5 else 'canceled' if i == 7 else 'success'
        snapshot['pipelines'].append({'id': pid, 'ref': ref, 'sha': f'{pid:040x}', 'status': status,
            'source': 'web' if i == 69 else 'push', 'created_at': created.isoformat(),
            'started_at': (created + timedelta(seconds=5)).isoformat(),
            'finished_at': (created + timedelta(minutes=5)).isoformat(),
            'duration_seconds': 200, 'queued_seconds': 5,
            'web_url': project['web_url'] + f'/-/pipelines/{pid}'})
        for n, name in enumerate(['build', 'publish']):
            duration = (200 if i == 69 else 120 + i % 5) if n == 0 else 20
            job_status = status if n == 0 else 'skipped' if i == 6 else 'success'
            start = created + timedelta(seconds=5 + n * 220)
            job = {'id': pid * 10 + n, 'pipeline_id': pid, 'name': name,
                'stage': 'build' if n == 0 else 'release', 'ref': ref, 'status': job_status,
                'allow_failure': False, 'created_at': created.isoformat(), 'started_at': start.isoformat(),
                'finished_at': (start + timedelta(seconds=duration)).isoformat(),
                'duration_seconds': None if i == 8 and n == 0 else 0 if i == 10 and n == 0 else duration,
                'queued_seconds': None if i == 9 and n == 0 else 40 if i == 69 and n == 0 else 2,
                'failure_reason': None, 'runner': {'id': 2 if i == 69 else 1, 'description': 'synthetic-runner'},
                'web_url': project['web_url'] + f'/-/jobs/{pid * 10 + n}'}
            snapshot['jobs'].append(job)
            if i == 11 and n == 0:
                snapshot['jobs'].append({**job, 'id': pid * 10 + 2, 'status': 'failed', 'duration_seconds': 35,
                                         'web_url': project['web_url'] + f'/-/jobs/{pid * 10 + 2}'})
    snapshot['source']['anchor_max_job_id'] = max(j['id'] for j in snapshot['jobs'])
    ci.save(out/'jobs.json', snapshot, 'jobs')
    report = ci.build_report(snapshot, release_refs=[p['ref'] for p in snapshot['pipelines']])
    ci.save(out/'report.json', report, 'report')
    ci.render(report, out/'report.html')


if __name__ == '__main__':
    main()
