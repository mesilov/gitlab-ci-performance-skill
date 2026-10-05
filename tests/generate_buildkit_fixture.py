"""Synthetic offline browser evidence: known/unknown/redacted/long image names."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/gitlab-ci-performance/scripts'))
from fixture_v2 import sample, AT
from report_trace import parse_trace
from report_contract import save, encoded
from report_calculate import build_report
from report_cli import render


def generate(output):
    source = sample(4)
    lines = []

    def add(second, body):
        lines.append(f'2026-10-04T00:00:{second:02d}Z {body}')

    cases = [(0, 16, 'example/service:tag'), (8, 25, None),
             (16, 50, 'example/SECRET_TOKEN:tag'), (24, 99, 'example/'+'a'*128+':tag')]
    for start, step, target in cases:
        add(start, '#0 building with "default" instance using docker driver')
        add(start, '#1 [internal] load build definition from Dockerfile')
        add(start, '#1 DONE 0.1s')
        add(start, '#8 [internal] load build context')
        add(start, '#8 DONE 0.2s')
        add(start, f'#{step-2} [private-stage 1/2] RUN <img src=x onerror=alert(1)> PRIVATE_TOKEN=hunter2')
        add(start, f'#{step-2} DONE 0.3s')
        add(start, f'#{step-1} [1/1] COPY app /app')
        add(start, f'#{step-1} CACHED')
        add(start, f'#{step} exporting to image')
        add(start+2, f'#{step} exporting layers 2s done')
        if target:
            add(start+3, f'#{step} naming to {target} done')
        add(start+4, f'#{step} DONE 4s')
    raw = ('\n'.join(lines)+'\n').encode()
    source['traces'] = [parse_trace(j['id'], raw, fetched_at=AT, analyzed_at=AT) for j in source['jobs']]
    assert b'SECRET_TOKEN' not in encoded(source)
    assert b'PRIVATE_TOKEN' not in encoded(source)
    assert b'<img' not in encoded(source)
    save(output/'jobs.json', source)
    report = build_report(source, generated_at=AT)
    save(output/'report.json', report)
    for language in ('en', 'ru'):
        render(report, output/f'report-{language}.html', language)


if __name__ == '__main__':
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--output-dir', type=Path, required=True)
    generate(arguments.parse_args().output_dir)
