#!/usr/bin/env python3
"""Write the example: synthetic data.json, report.html and report-ru.html.

No real project data. Run from anywhere: python3 examples/make_demo.py
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'skills/gitlab-ci-performance/scripts'))
import ci_report  # noqa: E402

BASE = 'https://gitlab.example.com/example/shop'
rng = random.Random(7)
ids = iter(range(5001, 9999))


def iso(moment):
    return moment.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def job(name, stage, ready, wait, run, status='success'):
    """A job that became ready at `ready`, waited for a runner, then ran."""
    started = ready + timedelta(seconds=wait)
    number = next(ids)
    return {'id': number, 'name': name, 'stage': stage, 'status': status,
            'started_at': iso(started), 'finished_at': iso(started + timedelta(seconds=run)),
            'duration': run, 'queued_duration': wait, 'web_url': f'{BASE}/-/jobs/{number}'}


def skipped(name, stage):
    number = next(ids)
    return {'id': number, 'name': name, 'stage': stage, 'status': 'skipped', 'started_at': None,
            'finished_at': None, 'duration': None, 'queued_duration': None,
            'web_url': f'{BASE}/-/jobs/{number}'}


def end(*jobs):
    return max(datetime.strptime(item['finished_at'], '%Y-%m-%dT%H:%M:%S.%f%z') for item in jobs)


def pipeline(number, created):
    jobs = [job('composer-install', 'build', created, rng.uniform(4, 9), rng.uniform(90, 104))]
    ready = end(jobs[0])
    status = 'success'
    tests = [job('phpstan', 'test', ready, rng.uniform(5, 10), rng.uniform(62, 78))]
    if number == 11:   # someone canceled this pipeline while the tests were running
        tests.append(job('phpunit', 'test', ready, 7, 100, 'canceled'))
        return 'canceled', jobs + tests + [skipped('build-image', 'package'), skipped('deploy-staging', 'deploy')]
    slow_tests = number >= 20   # phpunit became slower after pipeline 20
    tests.append(job('phpunit', 'test', ready, rng.uniform(5, 12),
                     rng.uniform(345, 372) if slow_tests else rng.uniform(236, 262)))
    wait = 150 if number % 5 == 3 else rng.uniform(40, 70)   # e2e needs a busy runner
    if number in (4, 9, 13, 17, 22, 26):   # e2e is unstable
        tests.append(job('e2e', 'test', ready, wait, rng.uniform(180, 230), 'failed'))
        if number in (9, 17):
            status = 'failed'
        else:
            tests.append(job('e2e', 'test', end(tests[-1]), rng.uniform(40, 70), rng.uniform(290, 330)))
    else:
        tests.append(job('e2e', 'test', ready, wait, rng.uniform(290, 330)))
    jobs += tests
    if status == 'failed':
        return status, jobs + [skipped('build-image', 'package'), skipped('deploy-staging', 'deploy')]
    image = job('build-image', 'package', end(*tests), rng.uniform(6, 12), rng.uniform(380, 420))
    deploy = job('deploy-staging', 'deploy', end(image), rng.uniform(4, 8), rng.uniform(35, 45))
    return status, jobs + [image, deploy]


class Log:
    """Builds raw job log bytes the way a runner writes them."""

    def __init__(self, started):
        self.now = datetime.strptime(started, '%Y-%m-%dT%H:%M:%S.%f%z')
        self.out = []

    def line(self, text):
        self.out.append(f'{self.now.strftime("%Y-%m-%dT%H:%M:%S.%f")}Z 00O {text}\n')

    def section(self, name, seconds, body=()):
        self.line(f'\x1b[0Ksection_start:{int(self.now.timestamp())}:{name}\r\x1b[0K\x1b[36;1m{name}\x1b[0;m')
        for text, took in body:
            self.line(text)
            self.now += timedelta(seconds=took)
        self.now += timedelta(seconds=seconds - sum(took for _, took in body))
        self.line(f'\x1b[0Ksection_end:{int(self.now.timestamp())}:{name}\r\x1b[0K')

    def raw(self):
        return ''.join(self.out).encode()


def command(text):
    return f'\x1b[32;1m$ {text}\x1b[0;m'


SCRIPTS = {
    'build-image': [
        (command('docker buildx build --push --tag registry.example.com/shop:$CI_COMMIT_SHORT_SHA .'), 0),
        ('#1 [internal] load build definition from Dockerfile', 0), ('#1 DONE 0.1s', 0),
        ('#2 [internal] load metadata for docker.io/library/php:8.3-fpm', 1), ('#2 DONE 1.4s', 0),
        ('#3 [internal] load build context', 6), ('#3 transferring context: 184.21MB 6.1s done', 0),
        ('#3 DONE 6.2s', 0),
        ('#4 [1/6] FROM docker.io/library/php:8.3-fpm', 0), ('#4 CACHED', 0),
        ('#5 [2/6] RUN apt-get update && apt-get install -y libicu-dev libzip-dev', 48), ('#5 DONE 48.3s', 0),
        ('#6 [3/6] RUN docker-php-ext-install intl zip opcache pdo_mysql', 93), ('#6 DONE 92.7s', 0),
        ('#7 [4/6] COPY composer.json composer.lock ./', 0), ('#7 DONE 0.4s', 0),
        ('#8 [5/6] RUN composer install --no-dev --optimize-autoloader', 72), ('#8 DONE 71.9s', 0),
        ('#9 [6/6] COPY . .', 12), ('#9 DONE 11.8s', 0),
        ('#10 exporting to image', 0), ('#10 exporting layers 38.2s done', 38),
        ('#10 pushing layers 64.0s done', 64), ('#10 DONE 118.6s', 16),
    ],
    'phpunit': [
        (command('composer install --no-interaction --prefer-dist'), 41),
        (command('php bin/console doctrine:migrations:migrate --no-interaction --env=test'), 38),
        (command('php vendor/bin/phpunit --testsuite unit'), 64),
        (command('php vendor/bin/phpunit --testsuite integration'), 196),
    ],
    'e2e': [
        (command('npm ci'), 52),
        (command('npx playwright install --with-deps chromium'), 47),
        (command('npx playwright test'), 190),
    ],
    'composer-install': [
        (command('composer install --no-interaction --prefer-dist'), 78),
        (command('composer dump-autoload --optimize'), 6),
    ],
    'phpstan': [
        (command('php vendor/bin/phpstan analyse --memory-limit=1G'), 58),
    ],
}


def log_for(run):
    log = Log(run['started_at'])
    script = SCRIPTS[run['name']]
    around = {'prepare_executor': 6, 'prepare_script': 2, 'get_sources': 9, 'restore_cache': 7}
    after = {'archive_cache': 5, 'upload_artifacts_on_success': 3, 'cleanup_file_variables': 1}
    for name, seconds in around.items():
        log.section(name, seconds)
    room = run['duration'] - sum(around.values()) - sum(after.values())
    scale = room / sum(took for _, took in script)   # stretch the commands to fill the script phase
    log.section('step_script', room, [(text, took * scale) for text, took in script])
    for name, seconds in after.items():
        log.section(name, seconds)
    return log.raw()


def main():
    first = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)
    pipelines = []
    for number in range(30):
        created = first + timedelta(hours=24 * number, minutes=rng.randint(0, 50))
        status, jobs = pipeline(number, created)
        pipelines.append({'id': 800 + number, 'status': status, 'source': 'push', 'ref': 'main',
                          'created_at': iso(created), 'web_url': f'{BASE}/-/pipelines/{800 + number}',
                          'jobs': jobs})
    data = {'host': 'gitlab.example.com', 'project': 'example/shop', 'project_url': BASE, 'ref': 'main',
            'source': None, 'collected_at': '2026-11-13T10:00:00Z', 'pipelines': pipelines[::-1], 'logs': {}}
    for row in ci_report.analyze(data)['jobs'][:5]:
        data['logs'][str(row['sample']['id'])] = dict(ci_report.parse_log(log_for(row['sample'])), cut=False)
    (HERE / 'data.json').write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    os.environ['TZ'] = 'UTC'   # the same example on every machine
    time.tzset()
    for lang, name in (('en', 'report.html'), ('ru', 'report-ru.html')):
        page = ci_report.render_html(data, ci_report.analyze(data), ci_report.T[lang], lang)
        (HERE / name).write_text(page, encoding='utf-8')
    print(ci_report.render_text(data, ci_report.analyze(data), ci_report.T['en']))


if __name__ == '__main__':
    main()
