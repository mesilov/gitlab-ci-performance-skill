#!/usr/bin/env python3
"""GitLab CI performance report: where pipeline time goes, in one HTML file.

Reads the last finished pipelines of one ref through `glab api` (GET only),
then writes data.json (what was read) and report.html (what it means).
Standard library only. Usage and reading guide: ../SKILL.md
"""
from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

# The only tuning knobs. They are printed in the report under "How this is counted".
CHANGE_PERCENT, CHANGE_SECONDS = 20, 30   # a change is notable above both
WAIT_SECONDS = 30                         # a runner wait worth a mention
FAIL_PERCENT, FAIL_COUNT = 10, 2          # a job is unstable above both
LOG_BYTES = 8 * 1024 * 1024               # read at most this much of one log

PIPELINE_KEYS = ('id', 'status', 'source', 'ref', 'created_at', 'web_url')
JOB_KEYS = ('id', 'name', 'stage', 'status', 'started_at', 'finished_at',
            'duration', 'queued_duration', 'web_url')


# ---------------------------------------------------------------- GitLab ----

class ApiError(Exception):
    pass


def glab(host, endpoint):
    """GET one API endpoint with the user's existing glab login. Returns bytes."""
    command = ['glab', 'api', '--hostname', host, '--method', 'GET', endpoint]
    try:
        done = subprocess.run(command, capture_output=True, timeout=120)
    except FileNotFoundError:
        raise SystemExit('glab is not installed. Install it, then run: '
                         f'glab auth login --hostname {host}')
    except subprocess.TimeoutExpired:
        raise ApiError(f'timeout: {endpoint}')
    if done.returncode:
        reason = (done.stderr or done.stdout).decode('utf-8', 'replace').strip()
        raise ApiError(f'{endpoint}: {reason[:300] or "request failed"}')
    return done.stdout


def api(host, endpoint):
    try:
        return json.loads(glab(host, endpoint))
    except ValueError:
        raise ApiError(f'{endpoint}: the answer is not JSON (check glab auth status)')


def all_pages(host, endpoint):
    items = []
    for page in range(1, 21):
        chunk = api(host, f'{endpoint}&per_page=100&page={page}')
        items += chunk
        if len(chunk) < 100:
            break
    return items


def parse_remote(url):
    """Host and project path from an SSH or HTTPS remote URL, or (None, None)."""
    found = re.match(r'(?:\w+://)?(?:[^@/]+@)?([^:/]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$', url)
    return (found[1], found[2]) if found else (None, None)


def git_remote():
    try:
        return parse_remote(subprocess.run(['git', 'remote', 'get-url', 'origin'],
                                           capture_output=True, text=True).stdout.strip())
    except OSError:
        return None, None


def collect(host, project, ref, source, count, logs, note=lambda text: None):
    """Read pipelines, their jobs and a few logs. Returns the data.json content."""
    base = 'projects/' + quote(project, safe='')
    info = api(host, base)
    if ref is None:
        ref = info['default_branch']
    query = f'{base}/pipelines?scope=finished&per_page={count}'
    if source:
        query += '&source=' + quote(source, safe='')
    pipelines = api(host, query + '&ref=' + quote(ref, safe='') if ref else query)
    if ref and len(pipelines) < count:
        everywhere = len(api(host, query))
        if everywhere > len(pipelines):
            note(f'Only {len(pipelines)} of the last {everywhere} finished pipelines ran on "{ref}". '
                 'If CI runs on tags, other branches or merge requests, add --any-ref.')
    note(f'{len(pipelines)} pipelines found, reading their jobs')

    def jobs_of(pipeline):
        found = all_pages(host, f'{base}/pipelines/{pipeline["id"]}/jobs?include_retried=true')
        return [{key: job.get(key) for key in JOB_KEYS} for job in found]

    with ThreadPoolExecutor(6) as pool:
        jobs = list(pool.map(jobs_of, pipelines))
    data = {
        'host': host, 'project': info['path_with_namespace'], 'project_url': info['web_url'],
        'ref': ref, 'source': source,
        'collected_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'pipelines': [dict({key: p.get(key) for key in PIPELINE_KEYS}, jobs=j)
                      for p, j in zip(pipelines, jobs)],
        'logs': {},
    }
    samples = [row['sample'] for row in analyze(data)['jobs'] if row['sample']][:logs]
    note(f'reading {len(samples)} job logs')

    def log_of(job):
        try:
            raw = glab(host, f'{base}/jobs/{job["id"]}/trace')
        except ApiError:
            return None
        return dict(parse_log(raw[:LOG_BYTES]), cut=len(raw) > LOG_BYTES)

    with ThreadPoolExecutor(6) as pool:
        for job, log in zip(samples, pool.map(log_of, samples)):
            if log:
                data['logs'][str(job['id'])] = log
    return data


# ------------------------------------------------------------- Job logs ----

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
STAMP = re.compile(r'^\[?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d))\]?'
                   r'\s*(?:[0-9a-f]{2}[OE][ +]?)?')
SECTION = re.compile(r'section_(start|end):(\d+):([\w.-]+)')
BUILD_STEP = re.compile(r'^#(\d+) (.+)$')
BUILD_DONE = re.compile(r'^DONE (\d+(?:\.\d+)?)s$')
BUILD_OUTPUT = re.compile(r'^\d+(?:\.\d+)?(?: |$)')
BUILD_PART = re.compile(r'^(.+?) (\d+(?:\.\d+)?)s done$')
SCRIPT_SECTIONS = {'step_script', 'build_script', 'after_script'}


def parse_log(raw):
    """Timed parts of one job log.

    sections: runner phases between section_start/section_end markers.
    steps:    script commands ("$ ..." lines, timed only when the log has
              timestamps) and Docker BuildKit steps ("#7 DONE 12.3s").
    A step that is explained by its own parts is left out: a command that wraps
    BuildKit steps, and "exporting to image" with timed layers and unpacking.
    """
    sections, steps = [], []
    opened, command = {}, None   # command: [text, started, wraps build steps, its sections]
    builds, titles, finished, parts = 0, {}, {}, {}   # BuildKit state of the current "docker build"

    def close_command(now):
        nonlocal command
        if command and not command[2] and None not in (command[1], now) and now >= command[1]:
            steps.append({'name': '$ ' + command[0][:160], 'seconds': round(now - command[1], 1)})
        command = None

    def build_step(key, name, seconds, known):
        """BuildKit repeats DONE with a growing total: keep one entry with the last total."""
        if key in known:
            steps[known[key]]['seconds'] = max(steps[known[key]]['seconds'], seconds)
        else:
            known[key] = len(steps)
            steps.append({'name': name[:160], 'seconds': seconds, 'build': builds})
        if command:
            command[2] = True

    for line in raw.decode('utf-8', 'replace').split('\n'):
        now = None
        for part in ANSI.sub('', line).split('\r'):
            part = part.strip()
            stamp = STAMP.match(part)
            if stamp:
                now, part = ts(stamp[1]), part[stamp.end():].strip()
            mark = SECTION.search(part)
            if mark:
                kind, at, name = mark[1], int(mark[2]), mark[3]
                if kind == 'start':
                    opened[name] = at
                elif name in opened:
                    if command and name in command[3]:   # a command ends with the phase it ran in
                        close_command(at)
                    sections.append({'name': name, 'seconds': at - opened.pop(name)})
            elif part.startswith('$ '):
                close_command(now)
                command = [part[2:], now, False, set(opened)]
            elif BUILD_STEP.match(part):
                number, body = BUILD_STEP.match(part).groups()
                done, timed = BUILD_DONE.match(body), BUILD_PART.match(body)
                if done:
                    if not any(key[0] == number for key in parts):
                        build_step(number, titles.get(number, '#' + number), float(done[1]), finished)
                elif body == 'CACHED' or body.startswith(('ERROR', 'CANCELED')) or BUILD_OUTPUT.match(body):
                    pass
                elif number == '1' and '1' in finished:   # numbering starts again: the next "docker build"
                    builds, titles, finished, parts = builds + 1, {'1': body}, {}, {}
                elif number not in titles:
                    titles[number] = body
                elif timed and titles[number].startswith('exporting to') and float(timed[2]) >= 1:
                    build_step((number, timed[1]), timed[1], float(timed[2]), parts)
    for step in steps:   # several images in one job: say which build a step belongs to
        build = step.pop('build', None)
        if builds and build is not None:
            step['name'] = f'build {build + 1}: {step["name"]}'[:160]
    return {'sections': sections, 'steps': steps}


# ------------------------------------------------------------- Analysis ----

def ts(value):
    """ISO time to epoch seconds; None stays None."""
    if not value:
        return None
    value = re.sub(r'\.(\d{1,6})\d*', lambda m: '.' + m[1].ljust(6, '0'), value.replace('Z', '+00:00'))
    return datetime.fromisoformat(value).timestamp()


def median(values):
    values = [value for value in values if value is not None]
    return statistics.median(values) if values else None


def squeeze(spans):
    """Merge overlapping (start, end) spans.

    Returns the total busy time and a function that maps a clock time to busy
    time, so idle gaps (a manual job started hours later) take no room.
    """
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return (sum(end - start for start, end in merged),
            lambda t: sum(min(t, end) - start for start, end in merged if t > start))


def change(values):
    """Newest successful runs against the earlier ones (values are oldest first)."""
    recent = min(10, len(values) // 2)
    if recent < 3:
        return None
    before, after = median(values[:-recent]), median(values[-recent:])
    delta = after - before
    percent = delta / before * 100 if before else 0
    return {'before': before, 'after': after, 'delta': delta, 'percent': percent,
            'recent': recent, 'earlier': len(values) - recent,
            'notable': abs(delta) >= CHANGE_SECONDS and abs(percent) >= CHANGE_PERCENT}


def ran(job):
    return bool(job.get('started_at') and job.get('finished_at') and job.get('duration') is not None)


def analyze(data):
    """Turn raw pipelines and jobs into the numbers the report shows."""
    pipelines, groups = [], {}
    for pipeline in sorted(data['pipelines'], key=lambda p: p['id']):
        runs = [job for job in pipeline['jobs'] if ran(job)]
        spans = [(ts(job['started_at']), ts(job['finished_at'])) for job in runs]
        pipelines.append(dict(pipeline, runs=runs, active=squeeze(spans)[0] if runs else None))
        for job in runs:
            groups.setdefault((job['stage'], job['name']), []).append(job)

    jobs = []
    for (stage, name), runs in groups.items():
        runs.sort(key=lambda job: job['id'])
        good = [job for job in runs if job['status'] == 'success']
        failed = [job for job in runs if job['status'] == 'failed']
        jobs.append({
            'name': name, 'stage': stage, 'runs': runs,
            'run': median(job['duration'] for job in good or runs),
            'wait': median(job.get('queued_duration') for job in runs),
            'change': change([job['duration'] for job in good]),
            'failed': len(failed), 'finished': len(good) + len(failed),
            'fail_cost': sum(job['duration'] for job in failed),
            'sample': good[-1] if good else None,   # the run whose log explains the job
        })
    jobs.sort(key=lambda row: -row['run'])
    for number, row in enumerate(jobs):
        row['index'] = number

    good = [p for p in pipelines if p['status'] == 'success' and p['active']]
    runs = [job for row in jobs for job in row['runs']]
    waited = sum(job.get('queued_duration') or 0 for job in runs)
    worked = sum(job['duration'] for job in runs)
    result = {
        'pipelines': pipelines, 'jobs': jobs,
        'typical': median(p['active'] for p in good), 'measured': len(good),
        'change': change([p['active'] for p in good]),
        'ok': sum(p['status'] == 'success' for p in pipelines), 'total': len(pipelines),
        'wait': median(job.get('queued_duration') for job in runs),
        'wait_share': waited / (waited + worked) * 100 if waited + worked else None,
        'sample': good[-1] if good else None,
    }
    result['first'] = first_look(jobs, data.get('logs', {}))
    return result


def first_look(jobs, logs):
    """At most one job per question: slowest, slower than before, waiting, failing."""
    found = []
    if jobs:
        found.append(('slow', jobs[0], longest_step(jobs[0], logs)))
    grew = [row for row in jobs if row['change'] and row['change']['notable'] and row['change']['delta'] > 0]
    if grew:
        found.append(('grew', max(grew, key=lambda row: row['change']['delta']), None))
    waits = [row for row in jobs if len(row['runs']) >= 3 and (row['wait'] or 0) >= WAIT_SECONDS]
    if waits:
        found.append(('wait', max(waits, key=lambda row: row['wait']), None))
    fails = [row for row in jobs if row['failed'] >= FAIL_COUNT
             and row['failed'] / row['finished'] * 100 >= FAIL_PERCENT]
    if fails:
        found.append(('fail', max(fails, key=lambda row: row['fail_cost']), None))
    return found


def longest_step(row, logs):
    log = logs.get(str(row['sample']['id'])) if row['sample'] else None
    if not log:
        return None
    parts = log['steps'] + [part for part in log['sections'] if part['name'] not in SCRIPT_SECTIONS]
    return max(parts, key=lambda part: part['seconds'], default=None)


# ---------------------------------------------------------------- Texts ----

T = {
    'en': {
        's': 's', 'min': 'min', 'h': 'h',
        'title': 'CI speed', 'collected': 'collected {when}', 'any_ref': 'any ref',
        'lead': 'A pipeline runs for about {time} (median of {ok} successful runs out of {total}).',
        'lead_none': 'None of the {total} pipelines finished successfully, so there is no typical run time.',
        'lead_up': 'The last {recent} are {delta} slower than the ones before ({percent}).',
        'lead_down': 'The last {recent} are {delta} faster than the ones before ({percent}).',
        'lead_flat': 'No notable change in the last {recent}.',
        'lead_few': 'Too few successful runs to tell whether it is changing.',
        'c_time': 'Pipeline run time', 'c_time_sub': 'median of successful runs',
        'c_change': 'Change', 'c_change_sub': 'last {recent} against {earlier} earlier',
        'c_change_few': 'needs 6 successful runs',
        'c_wait': 'Runner wait', 'c_wait_sub': 'median per job · {share} of job time',
        'c_ok': 'Successful pipelines', 'c_ok_sub': '{ok} of {total}',
        'h_first': 'Where to look first', 'h_history': 'Pipeline history',
        'h_sample': 'Latest successful pipeline', 'h_jobs': 'Jobs', 'h_how': 'How this is counted',
        'slow': 'Slowest job: {job} — {time} (median).',
        'slow_step': 'Longest step in its log: {step} — {time}.',
        'grew': '{job} got slower: {before} → {after} ({delta}, {percent}) over its last {recent} successful runs.',
        'wait': '{job} waits {time} for a runner (median). Waiting is {share} of all job time.',
        'fail': '{job} fails in {percent} of runs ({failed} of {finished}). The failed runs took {cost}.',
        'history_note': '{count} pipelines, {since} — {until}. One bar is one pipeline; open it with a click.',
        'sample_note': 'One row is one job. Pauses when nothing was running are removed.',
        'col_job': 'Job', 'col_run': 'Run', 'col_wait': 'Wait', 'col_change': 'Change',
        'col_failed': 'Failed', 'col_runs': 'Runs',
        'jobs_note': 'Sorted by run time. Open a job to see its runs and the steps from its log.',
        'runs_title': 'Runs, oldest to newest',
        'steps_title': 'Where the time went in run {id}', 'cut': 'the log was cut at 8 MB',
        'no_log': 'The log of this job was not read. Raise --logs to include it.',
        'no_steps': 'The log has no timed steps.',
        'k_success': 'successful', 'k_failed': 'failed', 'k_other': 'canceled',
        'k_wait': 'runner wait', 'k_median': 'median of successful',
        'tip_run': 'run {run} · wait {wait}',
        'how': [
            'Pipeline run time is the time when at least one job was running. Retries count; '
            'runner waits and pauses before manual jobs do not.',
            'Medians use successful runs only. Failed runs are drawn but do not move the median.',
            'Change compares the median of the newest successful runs with the earlier ones. '
            'It is marked only when it is above {percent}% and {seconds} s.',
            'Steps come from the log of one run, linked next to them. They are an example, not an average.',
        ],
        'phases': {
            'prepare_executor': 'Prepare executor', 'prepare_script': 'Prepare environment',
            'get_sources': 'Get sources (git)', 'restore_cache': 'Restore cache',
            'download_artifacts': 'Download artifacts', 'step_script': 'Script',
            'archive_cache': 'Save cache', 'upload_artifacts_on_success': 'Upload artifacts',
            'upload_artifacts_on_failure': 'Upload artifacts', 'cleanup_file_variables': 'Cleanup',
        },
        'out_jobs': 'Jobs (run · wait · change · failed · runs):', 'out_steps': 'Log of job {id} ({name}):',
        'out_report': 'Report: {path}', 'out_data': 'Data:   {path}',
    },
    'ru': {
        's': 'с', 'min': 'мин', 'h': 'ч',
        'title': 'Скорость CI', 'collected': 'собрано {when}', 'any_ref': 'любой ref',
        'lead': 'Pipeline работает около {time} (медиана по {ok} успешным запускам из {total}).',
        'lead_none': 'Ни один из {total} pipeline не завершился успешно, поэтому типичного времени нет.',
        'lead_up': 'Последние {recent} — на {delta} дольше, чем предыдущие ({percent}).',
        'lead_down': 'Последние {recent} — на {delta} быстрее, чем предыдущие ({percent}).',
        'lead_flat': 'В последних {recent} заметных изменений нет.',
        'lead_few': 'Успешных запусков мало, чтобы судить об изменениях.',
        'c_time': 'Время работы pipeline', 'c_time_sub': 'медиана успешных запусков',
        'c_change': 'Изменение', 'c_change_sub': 'последние {recent} против {earlier} прежних',
        'c_change_few': 'нужно 6 успешных запусков',
        'c_wait': 'Ожидание runner', 'c_wait_sub': 'медиана на job · {share} времени jobs',
        'c_ok': 'Успешные pipeline', 'c_ok_sub': '{ok} из {total}',
        'h_first': 'С чего начать', 'h_history': 'История pipeline',
        'h_sample': 'Последний успешный pipeline', 'h_jobs': 'Jobs', 'h_how': 'Как это посчитано',
        'slow': 'Самая долгая job: {job} — {time} (медиана).',
        'slow_step': 'Самый долгий шаг в её логе: {step} — {time}.',
        'grew': '{job} стала дольше: {before} → {after} ({delta}, {percent}) '
                'за последние {recent} успешных запусков.',
        'wait': '{job} ждёт runner {time} (медиана). Ожидание — {share} всего времени jobs.',
        'fail': '{job} падает в {percent} запусков ({failed} из {finished}). На упавшие запуски ушло {cost}.',
        'history_note': '{count} pipeline, {since} — {until}. Один столбец — один pipeline; клик открывает его.',
        'sample_note': 'Одна строка — одна job. Паузы, когда ничего не выполнялось, убраны.',
        'col_job': 'Job', 'col_run': 'Выполнение', 'col_wait': 'Ожидание', 'col_change': 'Изменение',
        'col_failed': 'Сбои', 'col_runs': 'Запусков',
        'jobs_note': 'Отсортировано по времени выполнения. Откройте job, чтобы увидеть запуски и шаги из лога.',
        'runs_title': 'Запуски, от старых к новым',
        'steps_title': 'Куда ушло время в запуске {id}', 'cut': 'лог обрезан на 8 МБ',
        'no_log': 'Лог этой job не читался. Увеличьте --logs, чтобы включить его.',
        'no_steps': 'В логе нет шагов с известным временем.',
        'k_success': 'успешно', 'k_failed': 'сбой', 'k_other': 'отменено',
        'k_wait': 'ожидание runner', 'k_median': 'медиана успешных',
        'tip_run': 'выполнение {run} · ожидание {wait}',
        'how': [
            'Время работы pipeline — время, когда выполнялась хотя бы одна job. Перезапуски входят; '
            'ожидание runner и паузы перед ручными jobs — нет.',
            'Медианы считаются только по успешным запускам. Упавшие видны на графиках, но медиану не сдвигают.',
            'Изменение — медиана последних успешных запусков против предыдущих. '
            'Оно выделяется, только если больше {percent}% и {seconds} с.',
            'Шаги взяты из лога одного запуска, ссылка на него рядом. Это пример, а не среднее.',
        ],
        'phases': {
            'prepare_executor': 'Подготовка исполнителя', 'prepare_script': 'Подготовка окружения',
            'get_sources': 'Получение исходников (git)', 'restore_cache': 'Восстановление кэша',
            'download_artifacts': 'Загрузка артефактов', 'step_script': 'Скрипт',
            'archive_cache': 'Сохранение кэша', 'upload_artifacts_on_success': 'Выгрузка артефактов',
            'upload_artifacts_on_failure': 'Выгрузка артефактов', 'cleanup_file_variables': 'Очистка',
        },
        'out_jobs': 'Jobs (выполнение · ожидание · изменение · сбои · запусков):',
        'out_steps': 'Лог job {id} ({name}):',
        'out_report': 'Отчёт:  {path}', 'out_data': 'Данные: {path}',
    },
}


def dur(seconds, L):
    if seconds is None:
        return '—'
    if 0 < seconds < 1:
        return f'<1 {L["s"]}'
    seconds = round(seconds)
    if seconds < 60:
        return f'{seconds} {L["s"]}'
    if seconds < 3600:
        minutes, rest = divmod(seconds, 60)
        return f'{minutes} {L["min"]}' + (f' {rest} {L["s"]}' if rest else '')
    hours, minutes = divmod(round(seconds / 60), 60)
    return f'{hours} {L["h"]}' + (f' {minutes} {L["min"]}' if minutes else '')


def signed(seconds, L):
    return ('+' if seconds >= 0 else '−') + dur(abs(seconds), L)


def percent(value, sign=False):
    return (f'{value:+.0f}%' if sign else f'{value:.0f}%').replace('-', '−')


def when(value):
    return datetime.fromtimestamp(ts(value)).strftime('%Y-%m-%d %H:%M') if value else '—'


def delta_text(found, L):
    if not found:
        return '—'
    if abs(found['delta']) < 1:
        return f'0 {L["s"]}'
    return f'{signed(found["delta"], L)} ({percent(found["percent"], True)})'


def delta_class(found):
    if not found or not found['notable']:
        return ' class="quiet"'
    return ' class="up"' if found['delta'] > 0 else ' class="down"'


def sentences(result, L, job=str, step=str):
    """The lead and the "look first" list. `job` and `step` decorate names (HTML or plain)."""
    found = result['change']
    if result['typical'] is None:
        lead = [L['lead_none'].format(total=result['total'])]
    else:
        lead = [L['lead'].format(time=dur(result['typical'], L), ok=result['measured'], total=result['total'])]
        if not found:
            lead.append(L['lead_few'])
        elif not found['notable']:
            lead.append(L['lead_flat'].format(recent=found['recent']))
        else:
            lead.append(L['lead_up' if found['delta'] > 0 else 'lead_down'].format(
                recent=found['recent'], delta=dur(abs(found['delta']), L),
                percent=percent(found['percent'], True)))
    first = []
    for what, row, part in result['first']:
        if what == 'slow':
            text = L['slow'].format(job=job(row), time=dur(row['run'], L))
            if part and part['seconds'] >= 5:
                text += ' ' + L['slow_step'].format(step=step(phase(part['name'], L)),
                                                    time=dur(part['seconds'], L))
        elif what == 'grew':
            found = row['change']
            text = L['grew'].format(job=job(row), before=dur(found['before'], L), after=dur(found['after'], L),
                                    delta=signed(found['delta'], L), percent=percent(found['percent'], True),
                                    recent=found['recent'])
        elif what == 'wait':
            text = L['wait'].format(job=job(row), time=dur(row['wait'], L),
                                    share=percent(result['wait_share']))
        else:
            text = L['fail'].format(job=job(row), percent=percent(row['failed'] / row['finished'] * 100),
                                    failed=row['failed'], finished=row['finished'],
                                    cost=dur(row['fail_cost'], L))
        first.append(text)
    return lead, first


def phase(name, L):
    return L['phases'].get(name, name)


# ----------------------------------------------------------------- HTML ----

CSS = """
:root{color-scheme:light dark;--bg:#f9f9f7;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--mute:#898781;
--line:#e1e0d9;--axis:#c3c2b7;--ok:#2a78d6;--bad:#d03b3b;--wait:#c3c2b7;--good:#006300}
@media(prefers-color-scheme:dark){:root{--bg:#0d0d0d;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--line:#2c2c2a;--axis:#383835;--ok:#3987e5;--bad:#e66767;--wait:#6b6a66;--good:#0ca30c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:960px;margin:0 auto;padding:28px 16px 56px}
a{color:inherit}
header{display:flex;flex-wrap:wrap;gap:4px 12px;justify-content:space-between;color:var(--ink2);font-size:13px}
h1{font-size:28px;line-height:1.2;margin:14px 0 6px}
h2{font-size:18px;margin:40px 0 10px}
h3{font-size:13px;font-weight:600;margin:18px 0 6px;color:var(--ink2)}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.92em}
.lead{font-size:17px;margin:0 0 20px;max-width:46em}
.note{color:var(--ink2);font-size:13px;margin:8px 0 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}
.card b{display:block;font-size:24px;font-weight:600;line-height:1.3}
.card span{display:block;font-size:13px}
.card small{color:var(--ink2);font-size:12px}
.up{color:var(--bad);font-weight:600}.down{color:var(--good);font-weight:600}.quiet{color:var(--mute)}
.first{margin:0;padding-left:22px}.first li{margin:6px 0;max-width:46em}
.chart{display:grid;grid-template-columns:auto minmax(0,1fr);gap:0 8px}
.axis{display:flex;flex-direction:column;justify-content:space-between;text-align:right;
font-size:12px;line-height:1;color:var(--mute);font-variant-numeric:tabular-nums}
.plot{position:relative;display:flex;gap:2px;border-bottom:1px solid var(--axis)}
.plot>i{position:absolute;left:0;right:0;border-top:1px solid var(--line);pointer-events:none}
.plot>i.median{border-top:1.5px dashed var(--ink2);z-index:1}
.bar{position:relative;flex:1 1 0;max-width:40px;min-width:1px;display:flex;flex-direction:column;
justify-content:flex-end;z-index:2}
.bar:hover,.bar:focus-visible{background:color-mix(in srgb,var(--ink) 8%,transparent);outline:0;z-index:3}
.bar b{display:block;min-height:1px}.bar b:first-child{border-radius:3px 3px 0 0}
.bar b.wait{margin-bottom:2px}
.success{background:var(--ok)}.failed{background:var(--bad)}.wait{background:var(--wait)}
.other{box-shadow:inset 0 0 0 1.5px var(--mute)}
[data-tip]:hover::after,[data-tip]:focus-visible::after{content:attr(data-tip);position:absolute;
bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);white-space:pre;background:var(--ink);
color:var(--bg);font:12px/1.45 system-ui,sans-serif;padding:6px 9px;border-radius:6px;z-index:9;
pointer-events:none}
.l[data-tip]::after{left:0;transform:none}.r[data-tip]::after{left:auto;right:0;transform:none}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;color:var(--ink2);font-size:12px;margin:10px 0 0}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
.legend i.median{width:16px;height:0;border-top:1.5px dashed var(--ink2);border-radius:0;vertical-align:middle}
.row{position:relative;display:grid;grid-template-columns:minmax(80px,230px) minmax(0,1fr) 88px;gap:10px;
align-items:center;padding:3px 0;text-decoration:none;font-size:13px}
a.row:hover,a.row:focus-visible{background:color-mix(in srgb,var(--ink) 6%,transparent);outline:0}
.name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{position:relative;height:12px}
.track i{position:absolute;top:0;bottom:0;min-width:2px;border-radius:3px}
.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.jobs{border-top:1px solid var(--line)}
.head,.job summary{display:grid;grid-template-columns:minmax(0,1fr) 104px 84px 168px 84px 72px;gap:12px;
align-items:baseline;padding:8px 6px}
.head{color:var(--ink2);font-size:12px}
.job{border-bottom:1px solid var(--line)}
.job summary{cursor:pointer;list-style:none}.job summary::-webkit-details-marker{display:none}
.job summary:hover{background:color-mix(in srgb,var(--ink) 5%,transparent)}
.job summary .name::before{content:"▸";display:inline-block;width:16px;color:var(--mute)}
.job[open] summary .name::before{content:"▾"}
.job small{color:var(--mute)}
.body{padding:2px 6px 18px 22px}
.steps .row{grid-template-columns:minmax(0,1fr) 160px 84px}
.steps .sub .name{padding-left:18px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
.how{color:var(--ink2);font-size:13px;padding-left:20px;max-width:56em}.how li{margin:4px 0}
@media(max-width:640px){.head,.job summary{grid-template-columns:minmax(0,1fr) 84px 104px;gap:8px}.s{display:none}
.job summary .num{white-space:normal}.row{grid-template-columns:minmax(70px,120px) minmax(0,1fr) 76px}
.steps .row{grid-template-columns:minmax(0,1fr) 48px 76px}.steps .name{white-space:normal;overflow-wrap:anywhere}}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def axis_top(value):
    """A round axis maximum at or above the value, in seconds."""
    for top in (10, 20, 30, 60, 120, 180, 240, 300, 360, 480, 600, 720, 900, 1200, 1440, 1800, 2400,
                3000, 3600, 4800, 6000, 7200):
        if value <= top:
            return top
    return (int(value) // 3600 + 1) * 3600


def status_class(status):
    return status if status in ('success', 'failed') else 'other'


def bars(items, L, line=None, height=130):
    """A column chart. items: dicts with run, wait, status, tip, url (oldest first)."""
    if not items:
        return ''
    top = axis_top(max(item['run'] + item['wait'] for item in items))
    columns = []
    for index, item in enumerate(items):
        side = ' l' if index < len(items) / 3 else ' r' if index >= len(items) * 2 / 3 else ''
        parts = ''
        if item['wait'] / top >= 0.01:
            parts += f'<b class="wait" style="height:{item["wait"] / top * 100:.1f}%"></b>'
        parts += f'<b class="{status_class(item["status"])}" style="height:{item["run"] / top * 100:.1f}%"></b>'
        tip = esc(item['tip'])
        columns.append(f'<a class="bar{side}" href="{esc(item["url"])}" data-tip="{tip}" aria-label="{tip}">{parts}</a>')
    median_line = f'<i class="median" style="bottom:{line / top * 100:.1f}%"></i>' if line else ''
    return (f'<div class="chart"><div class="axis"><span>{dur(top, L)}</span><span>{dur(top / 2, L)}</span>'
            f'<span>0</span></div><div class="plot" style="height:{height}px"><i style="bottom:50%"></i>'
            f'<i style="bottom:100%"></i>{median_line}{"".join(columns)}</div></div>')


def legend(keys, L):
    return '<p class="legend">' + ''.join(
        f'<span><i class="{key}"></i>{L["k_" + key]}</span>' for key in keys) + '</p>'


def job_tip(job, L):
    return (f'#{job["id"]} · {job["status"]}\n'
            + L['tip_run'].format(run=dur(job['duration'], L), wait=dur(job.get('queued_duration') or 0, L))
            + f'\n{when(job["started_at"])}')


def waterfall(pipeline, L):
    """Jobs of one pipeline on a shared time axis: grey wait, then the run."""
    runs = sorted(pipeline['runs'], key=lambda job: ts(job['started_at']) - (job.get('queued_duration') or 0))
    spans = [(ts(job['started_at']) - (job.get('queued_duration') or 0), ts(job['finished_at'])) for job in runs]
    total, at = squeeze(spans)
    total = total or 1
    rows = []
    for job, (queued, finished) in zip(runs[:60], spans):
        left, start, right = (at(point) / total * 100 for point in (queued, ts(job['started_at']), finished))
        rows.append(
            f'<a class="row" href="{esc(job["web_url"])}" data-tip="{esc(job_tip(job, L))}">'
            f'<span class="name">{esc(job["name"])}</span><span class="track">'
            f'<i class="wait" style="left:{left:.2f}%;width:{start - left:.2f}%"></i>'
            f'<i class="{status_class(job["status"])}" style="left:{start:.2f}%;width:{right - start:.2f}%"></i>'
            f'</span><span class="num">{dur(job["duration"], L)}</span></a>')
    return ''.join(rows)


def step_rows(log, L):
    """One list for one run: runner phases, with the script's own steps under the script."""
    def top(parts, count):
        return sorted((part for part in parts if part['seconds'] >= 1), key=lambda part: -part['seconds'])[:count]

    phases, steps = top(log['sections'], 12), top(log['steps'], 8)
    if not phases and not steps:
        return f'<p class="note">{L["no_steps"]}</p>'
    script = next((part for part in phases if part['name'] in SCRIPT_SECTIONS), None)
    rows = []
    for part in phases or [None]:
        if part:
            rows.append((part, ''))
        if part is script:
            rows += [(step, ' sub') for step in steps]
    longest = max(part['seconds'] for part, _ in rows)
    return ''.join(
        f'<div class="row{sub}"><span class="name" title="{esc(phase(part["name"], L))}">'
        f'{esc(phase(part["name"], L))}</span><span class="track"><i class="success" style="left:0;'
        f'width:{part["seconds"] / longest * 100:.1f}%"></i></span>'
        f'<span class="num">{dur(part["seconds"], L)}</span></div>' for part, sub in rows)


def job_block(row, logs, L):
    found = row['change']
    fails = f'{percent(row["failed"] / row["finished"] * 100)} <small>{row["failed"]}/{row["finished"]}</small>' \
        if row['failed'] else '—'
    items = [{'run': job['duration'], 'wait': job.get('queued_duration') or 0, 'status': job['status'],
              'tip': job_tip(job, L), 'url': job['web_url']} for job in row['runs']]
    log = logs.get(str(row['sample']['id'])) if row['sample'] else None
    if log:
        link = f'<a href="{esc(row["sample"]["web_url"])}">#{row["sample"]["id"]}</a>'
        cut = f' <small>· {L["cut"]}</small>' if log.get('cut') else ''
        detail = f'<h3>{L["steps_title"].format(id=link)}{cut}</h3><div class="steps">{step_rows(log, L)}</div>'
    else:
        detail = f'<p class="note">{L["no_log"]}</p>'
    return (
        f'<details class="job" id="job-{row["index"]}"><summary><span class="name">{esc(row["name"])} '
        f'<small>{esc(row["stage"])}</small></span><span class="num">{dur(row["run"], L)}</span>'
        f'<span class="num s">{dur(row["wait"], L)}</span><span class="num"><span{delta_class(found)}>'
        f'{delta_text(found, L)}</span></span><span class="num s">{fails}</span>'
        f'<span class="num s">{len(row["runs"])}</span></summary><div class="body">'
        f'<h3>{L["runs_title"]}</h3>{bars(items, L, row["run"], 90)}{detail}</div></details>')


def render_html(data, result, L, lang):
    logs = data.get('logs', {})
    lead, first = sentences(
        result, L,
        job=lambda row: f'<a href="#job-{row["index"]}"><b>{esc(row["name"])}</b></a>',
        step=lambda name: f'<code>{esc(name)}</code>')
    found = result['change']
    cards = [
        (dur(result['typical'], L), '', L['c_time'], L['c_time_sub']),
        (delta_text(found, L), delta_class(found) if found and found['notable'] else '', L['c_change'],
         L['c_change_sub'].format(**found) if found else L['c_change_few']),
        (dur(result['wait'], L), '', L['c_wait'],
         L['c_wait_sub'].format(share=percent(result['wait_share'] or 0))),
        (percent(result['ok'] / result['total'] * 100) if result['total'] else '—', '', L['c_ok'],
         L['c_ok_sub'].format(ok=result['ok'], total=result['total'])),
    ]
    drawn = [p for p in result['pipelines'] if p['active']]
    history = bars([{'run': p['active'], 'wait': 0, 'status': p['status'], 'url': p['web_url'],
                     'tip': f'#{p["id"]} · {p["status"]} · {p.get("source") or ""}\n{dur(p["active"], L)}\n'
                            f'{when(p["created_at"])}'} for p in drawn], L, result['typical'])
    out = [
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f'<title>{L["title"]} · {esc(data["project"])}</title><style>{CSS}</style></head><body><main>',
        f'<header><span><a href="{esc(data["project_url"])}">{esc(data["project"])}</a> · '
        f'<code>{esc(data["ref"] or L["any_ref"])}</code>'
        + (f' · {esc(data["source"])}' if data.get('source') else '') + '</span>'
        f'<span>{L["collected"].format(when=when(data["collected_at"]))}</span></header>',
        f'<h1>{L["title"]}</h1><p class="lead">{" ".join(lead)}</p><div class="cards">',
        ''.join(f'<div class="card"><b{cls}>{value}</b><span>{name}</span><small>{sub}</small></div>'
                for value, cls, name, sub in cards),
        '</div>',
    ]
    if first:
        out.append(f'<h2>{L["h_first"]}</h2><ol class="first">'
                   + ''.join(f'<li>{text}</li>' for text in first) + '</ol>')
    if drawn:
        out.append(f'<h2>{L["h_history"]}</h2>{history}{legend(("success", "failed", "other", "median"), L)}'
                   f'<p class="note">' + L['history_note'].format(
                       count=len(drawn), since=when(drawn[0]['created_at'])[:10],
                       until=when(drawn[-1]['created_at'])[:10]) + '</p>')
    sample = result['sample']
    if sample:
        out.append(f'<h2>{L["h_sample"]} <a href="{esc(sample["web_url"])}">#{sample["id"]}</a> · '
                   f'{dur(sample["active"], L)}</h2>{waterfall(sample, L)}'
                   f'{legend(("success", "failed", "other", "wait"), L)}<p class="note">{L["sample_note"]}</p>')
    if result['jobs']:
        out.append(
            f'<h2>{L["h_jobs"]}</h2><div class="jobs"><div class="head"><span>{L["col_job"]}</span>'
            f'<span class="num">{L["col_run"]}</span><span class="num s">{L["col_wait"]}</span>'
            f'<span class="num">{L["col_change"]}</span><span class="num s">{L["col_failed"]}</span>'
            f'<span class="num s">{L["col_runs"]}</span></div>'
            + ''.join(job_block(row, logs, L) for row in result['jobs'])
            + f'</div><p class="note">{L["jobs_note"]}</p>')
    out.append(f'<h2>{L["h_how"]}</h2><ul class="how">' + ''.join(
        f'<li>{line.format(percent=CHANGE_PERCENT, seconds=CHANGE_SECONDS)}</li>' for line in L['how'])
        + '</ul></main></body></html>')
    return '\n'.join(out)


def render_text(data, result, L):
    """The same findings as plain text, for the terminal and for the agent."""
    logs = data.get('logs', {})
    lead, first = sentences(result, L, job=lambda row: row['name'])
    lines = [f'{L["title"]} · {data["project"]} · {data["ref"] or L["any_ref"]}', ' '.join(lead),
             f'{L["c_wait"]}: {dur(result["wait"], L)} ({L["c_wait_sub"].format(share=percent(result["wait_share"] or 0))}). '
             f'{L["c_ok"]}: {L["c_ok_sub"].format(ok=result["ok"], total=result["total"])}.']
    if first:
        lines += ['', L['h_first'] + ':'] + [f'{number}. {text}' for number, text in enumerate(first, 1)]
    if result['jobs']:
        lines += ['', L['out_jobs']]
    for row in result['jobs'][:25]:
        lines.append(f'  {row["name"]} [{row["stage"]}]  {dur(row["run"], L)} · {dur(row["wait"], L)} · '
                     f'{delta_text(row["change"], L)} · {row["failed"]}/{row["finished"]} · {len(row["runs"])}')
    for row in result['jobs']:
        log = logs.get(str(row['sample']['id'])) if row['sample'] else None
        parts = (log or {}).get('sections', []) + (log or {}).get('steps', [])
        parts = sorted((part for part in parts if part['seconds'] >= 1), key=lambda part: -part['seconds'])[:8]
        if parts:
            lines += ['', L['out_steps'].format(id=row['sample']['id'], name=row['name'])]
            lines += [f'  {dur(part["seconds"], L):>12}  {phase(part["name"], L)}' for part in parts]
    return '\n'.join(lines)


# ------------------------------------------------------------------ CLI ----

def main(argv=None):
    parser = argparse.ArgumentParser(description='GitLab CI performance report: data.json + report.html')
    parser.add_argument('--project', help='group/project path (default: git remote "origin")')
    parser.add_argument('--host', help='GitLab host (default: git remote "origin")')
    parser.add_argument('--ref', help='branch or tag (default: the default branch)')
    parser.add_argument('--any-ref', action='store_true', help='do not filter pipelines by ref')
    parser.add_argument('--source', help='only pipelines from this source: push, schedule, merge_request_event…')
    parser.add_argument('--pipelines', type=int, default=30, help='finished pipelines to read, 1–100 (default 30)')
    parser.add_argument('--logs', type=int, default=5, help='read the log of the N slowest jobs (default 5)')
    parser.add_argument('--lang', choices=sorted(T), default='en', help='report language (default en)')
    parser.add_argument('--out', type=Path, default=Path('ci-report'), help='output directory (default ./ci-report)')
    parser.add_argument('--from', dest='saved', type=Path, metavar='DATA_JSON',
                        help='rebuild the report from a saved data.json, without GitLab')
    args = parser.parse_args(argv)
    L = T[args.lang]

    if args.saved:
        data = json.loads(args.saved.read_text(encoding='utf-8'))
    else:
        host, project = git_remote()
        host, project = args.host or host, args.project or project
        if not host or not project:
            parser.error('pass --host and --project (no GitLab "origin" remote found here)')
        if not 1 <= args.pipelines <= 100:
            parser.error('--pipelines must be between 1 and 100')
        try:
            data = collect(host, project, '' if args.any_ref else args.ref, args.source, args.pipelines,
                           max(args.logs, 0), note=lambda text: print(text, file=sys.stderr))
        except ApiError as error:
            raise SystemExit(f'GitLab request failed: {error}')
    if not data['pipelines']:
        raise SystemExit('No finished pipelines found for this ref. Try --ref, --any-ref or --source.')

    result = analyze(data)
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.saved:
        (args.out / 'data.json').write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    report = args.out / 'report.html'
    report.write_text(render_html(data, result, L, args.lang), encoding='utf-8')
    print(render_text(data, result, L))
    print()
    print(L['out_report'].format(path=report.resolve()))
    if not args.saved:
        print(L['out_data'].format(path=(args.out / 'data.json').resolve()))


if __name__ == '__main__':
    main()
