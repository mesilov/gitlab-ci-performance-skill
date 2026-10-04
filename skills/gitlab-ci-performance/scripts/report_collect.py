"""Bounded, read-only GitLab metadata and safe trace-summary collection."""
from report_contract import SKILL_VERSION, VERSION, PARSER_VERSION
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import copy
import json
import os
import re
import selectors
import subprocess
import time
from urllib.parse import quote, urlsplit, parse_qs
from zoneinfo import ZoneInfo

from report_trace import parse_trace, empty_trace
from report_contract import now, digest, type_id, validate

TERMINAL = {'success', 'failed', 'canceled', 'skipped'}
ERRORS = {'unavailable', 'permission_denied', 'timeout', 'invalid_response', 'transport_error'}
LIMITATIONS = ['Deleted jobs cannot be recovered', 'API collection is not an atomic transaction',
               'Bridge/trigger jobs are outside project Jobs API']


class TransportError(ValueError):
    """Only allowlisted transport states, never stderr or response text."""
    def __init__(self, code='transport_error'):
        self.code = code if code in ERRORS else 'transport_error'
        super().__init__(self.code)


def _response(raw):
    boundary = re.search(br'\r?\n\r?\n', raw)
    if not boundary:
        raise TransportError('invalid_response')
    header = raw[:boundary.start()].replace(b'\r\n', b'\n').decode('ascii', errors='replace')
    body = raw[boundary.end():]
    match = re.search(r'^HTTP/\S+\s+(\d{3})\b', header)
    if not match:
        raise TransportError('invalid_response')
    status = int(match.group(1))
    if status in (401, 403):
        raise TransportError('permission_denied')
    if status < 200 or status >= 300:
        raise TransportError('unavailable')
    return header, body


class GlabTransport:
    """Mockable glab GET transport. Trace stdout is streamed into bounded memory."""
    def __init__(self, host):
        self.host = host

    def _command(self, endpoint):
        return ['glab', 'api', '--hostname', self.host, '--method', 'GET', '--include', endpoint]

    def json(self, endpoint):
        try:
            result = subprocess.run(self._command(endpoint), stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=60)
        except subprocess.TimeoutExpired:
            raise TransportError('timeout') from None
        except OSError:
            raise TransportError() from None
        headers, raw = _response(result.stdout)
        if result.returncode:
            raise TransportError()
        try:
            return headers, json.loads(raw)
        except (ValueError, UnicodeError):
            raise TransportError('invalid_response') from None

    def version(self):
        try:
            result = subprocess.run(['glab', 'version'], stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=10)
            match = re.search(rb'\bglab\s+(?:version\s+)?v?([0-9]+(?:\.[0-9]+){1,3})\b', result.stdout)
            return 'glab ' + match.group(1).decode() if match else 'unknown'
        except (OSError, subprocess.TimeoutExpired):
            return 'unknown'

    def trace(self, endpoint, max_bytes, max_lines):
        try:
            process = subprocess.Popen(self._command(endpoint), stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL)
        except OSError:
            raise TransportError() from None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        header_buffer, body, headers = bytearray(), bytearray(), None
        deadline, truncated = time.monotonic() + 60, False
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TransportError('timeout')
                ready = selector.select(min(remaining, 1))
                if not ready:
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                if headers is None:
                    header_buffer.extend(chunk)
                    match = re.search(br'\r?\n\r?\n', header_buffer)
                    if not match:
                        if len(header_buffer) > 65536:
                            raise TransportError('invalid_response')
                        continue
                    headers, chunk = _response(bytes(header_buffer))
                    header_buffer.clear()
                available = max_bytes - len(body)
                body.extend(chunk[:available])
                if len(chunk) > available:
                    truncated = True
                # Preserve at most max_lines physical lines, including a final partial line.
                line_ends = [m.end() for m in re.finditer(b'\n', body)]
                if len(line_ends) >= max_lines:
                    limit = line_ends[max_lines - 1]
                    if len(body) > limit:
                        del body[limit:]
                        truncated = True
                if truncated:
                    break
            if headers is None:
                raise TransportError('invalid_response')
            if not truncated and process.wait(timeout=max(.01, deadline - time.monotonic())):
                raise TransportError()
            return bytes(body), truncated
        except subprocess.TimeoutExpired:
            raise TransportError('timeout') from None
        finally:
            selector.close()
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()


def next_page(headers, host, project_id):
    match = re.search(r'<([^>]+)>;\s*rel="next"', headers, re.I)
    if not match:
        return None
    target = urlsplit(match.group(1))
    query = parse_qs(target.query, keep_blank_values=True)
    allowed = {'per_page', 'pagination', 'order_by', 'sort', 'id_before', 'id_after', 'page', 'cursor', 'id'}
    if (target.scheme != 'https' or target.netloc != host or target.username or target.password or
            target.path != f'/api/v4/projects/{project_id}/jobs' or target.fragment or
            not set(query) <= allowed or any(len(v) != 1 for v in query.values()) or
            ('id' in query and query['id'] != [str(project_id)]) or
            ('per_page' in query and (not query['per_page'][0].isdigit() or int(query['per_page'][0]) > 100))):
        raise ValueError('Unsafe pagination target')
    return target.path.removeprefix('/api/v4/') + ('?' + target.query if target.query else '')


def _pipeline(raw, fresh=False, at=None, error='not_requested'):
    return {'id': raw['id'], 'ref': raw.get('ref') or '', 'sha': raw.get('sha'),
            'status': raw.get('status') or 'unknown', 'source': raw.get('source') or 'unknown',
            'created_at': raw.get('created_at'), 'started_at': raw.get('started_at'),
            'finished_at': raw.get('finished_at'), 'duration_seconds': raw.get('duration'),
            'queued_seconds': raw.get('queued_duration'), 'web_url': raw.get('web_url'),
            'metadata_checked_at': at, 'metadata_fresh': fresh, 'metadata_error': error}


def _job(raw, fresh=False, at=None, error='not_requested'):
    runner = raw.get('runner')
    return {'id': raw['id'], 'pipeline_id': raw['pipeline']['id'], 'name': raw['name'],
            'stage': raw['stage'], 'ref': raw['ref'], 'status': raw['status'],
            'allow_failure': bool(raw.get('allow_failure', False)), 'created_at': raw['created_at'],
            'started_at': raw.get('started_at'), 'finished_at': raw.get('finished_at'),
            'duration_seconds': raw.get('duration'), 'queued_seconds': raw.get('queued_duration'),
            'failure_reason': raw.get('failure_reason'),
            'runner': None if not runner else {'id': runner['id'], 'description': runner.get('description') or ''},
            'web_url': raw['web_url'], 'sha': raw.get('commit', {}).get('id') or raw['pipeline'].get('sha'),
            'erased_at': raw.get('erased_at'), 'metadata_checked_at': at,
            'metadata_fresh': fresh, 'metadata_error': error}


def _input_snapshot(value, host, project):
    if value is None:
        return
    validate(value, 'jobs')
    if (value.get('schema_version') != VERSION or value.get('kind') != 'gitlab_job_performance_source' or
            any(value.get('project', {}).get(k) != project[k] for k in ('host', 'id', 'path'))):
        raise ValueError('Resume/cache requires a 2.1.0 source for the same host/project')
    if len({j['id'] for j in value['jobs']}) != len(value['jobs']):
        raise ValueError('Resume/cache has duplicate job IDs')


def _cache_trace(job, previous_jobs, previous_traces, at, max_age, max_bytes, max_lines):
    old, trace = previous_jobs.get(job['id']), previous_traces.get(job['id'])
    if not old or not trace or not job['metadata_fresh'] or job['status'] not in TERMINAL or job['erased_at']:
        return None
    keys = ('id', 'pipeline_id', 'sha', 'status', 'erased_at', 'started_at', 'finished_at', 'duration_seconds')
    if any(old.get(k) != job.get(k) for k in keys) or trace['state'] not in {'available', 'empty', 'unsupported', 'partial'}:
        return None
    if (trace['parser_version'] != PARSER_VERSION or trace['bytes_read'] > max_bytes or
            trace['line_count'] > max_lines):
        return None
    try:
        age = (datetime.fromisoformat(at.replace('Z', '+00:00')) -
               datetime.fromisoformat(trace['fetched_at'].replace('Z', '+00:00'))).total_seconds()
    except (ValueError, TypeError, AttributeError):
        return None
    if not 0 <= age <= max_age:
        return None
    result = copy.deepcopy(trace)
    result['cached'] = True
    return result


def collect(host, project_path, display_timezone='UTC', *, max_pages=10, max_job_types=16,
            concurrency=4, job_selectors=None, resume=None, cache=None, cache_max_age_seconds=86400,
            trace_bytes=4194304, trace_lines=50000, comparison_mode='same_ref', refs=None):
    """Collect an immutable v2 source. All limits bound this invocation; resume counts accumulate."""
    if not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]+)?', host):
        raise ValueError('Invalid hostname')
    ZoneInfo(display_timezone)
    for name, value in [('max_pages', max_pages), ('max_job_types', max_job_types), ('concurrency', concurrency),
                        ('trace_bytes', trace_bytes), ('trace_lines', trace_lines)]:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f'{name} must be a positive bounded integer')
    if trace_bytes > 4194304 or trace_lines > 50000:
        raise ValueError('Trace limits exceed supported 4 MiB/50000 line bounds')
    if (concurrency > 4 or max_job_types > 16 or isinstance(cache_max_age_seconds, bool) or
            not isinstance(cache_max_age_seconds, int) or cache_max_age_seconds < 0):
        raise ValueError('Concurrency/type limits or cache age exceed supported bounds')
    if comparison_mode not in ('same_ref', 'cross_ref') or (comparison_mode == 'cross_ref' and
            (not isinstance(refs, (list, tuple)) or not refs or not all(isinstance(x, str) and x for x in refs))):
        raise ValueError('cross_ref requires explicit nonempty refs')
    if comparison_mode == 'same_ref' and refs:
        raise ValueError('Explicit refs require cross_ref comparison mode')
    selectors_set = None
    if job_selectors is not None:
        if not isinstance(job_selectors, list) or not all(isinstance(x, dict) and set(x) == {'stage', 'name'} and
                all(isinstance(v, str) for v in x.values()) for x in job_selectors):
            raise ValueError('Job selectors must be structured stage/name pairs')
        selectors_set = {(x['stage'], x['name']) for x in job_selectors}
        if len(selectors_set) > max_job_types:
            raise ValueError('Job selection exceeds max_job_types')
    for previous in (resume, cache):
        if previous is not None:
            validate(previous, 'jobs')
    started = now()
    transport = GlabTransport(host)
    _, raw_project = transport.json('projects/' + quote(project_path, safe=''))
    _, version = transport.json('version')
    project = {'id': raw_project['id'], 'path': raw_project['path_with_namespace'], 'host': host,
               'web_url': raw_project['web_url'], 'default_branch': raw_project.get('default_branch')}
    _input_snapshot(resume, host, project)
    _input_snapshot(cache, host, project)
    requests = dict(project=1, version=1, pages=0, metadata=0, pipelines=0, traces=0)
    jobs = {j['id']: copy.deepcopy(j) for j in resume['jobs']} if resume else {}
    pipelines = {p['id']: copy.deepcopy(p) for p in resume['pipelines']} if resume else {}
    if resume:
        requests = {key: requests[key] + resume['source']['requests'][key] for key in requests}
        started = resume['collection_started_at']
    first_endpoint = f"projects/{project['id']}/jobs?per_page=100&pagination=keyset&order_by=id&sort=desc"
    endpoint = resume['source']['cursor'] if resume else first_endpoint
    if endpoint is not None and next_page(f'Link: <https://{host}/api/v4/{endpoint}>; rel="next"', host, project['id']) != endpoint:
        raise ValueError('Unsafe resume cursor')
    anchor = resume['source']['anchor_max_job_id'] if resume else None
    visited, new_seen, invocation_pages = set(), set(), 0
    while endpoint and invocation_pages < max_pages:
        if endpoint in visited:
            raise ValueError('Pagination cycle')
        visited.add(endpoint)
        headers, batch = transport.json(endpoint)
        requests['pages'] += 1
        invocation_pages += 1
        if not isinstance(batch, list) or len(batch) > 100:
            raise ValueError('Jobs API requires an array of at most 100 entries')
        if anchor is None and batch:
            anchor = max(j['id'] for j in batch)
        for raw in batch:
            jid = raw['id']
            if jid in new_seen:
                raise ValueError('Jobs API returned duplicate ID')
            new_seen.add(jid)
            if anchor is not None and jid > anchor:
                continue
            if jid in jobs:
                continue  # IDs already present in a prior bounded invocation.
            jobs[jid] = _job(raw)
            embedded = dict(raw['pipeline'], ref=raw['ref'])
            embedded.setdefault('web_url', f"{project['web_url']}/-/pipelines/{embedded['id']}")
            pipelines.setdefault(embedded['id'], _pipeline(embedded))
        endpoint = next_page(headers, host, project['id'])
        if endpoint in visited:
            raise ValueError('Pagination cycle')
    complete = endpoint is None
    groups = defaultdict(list)
    for job in sorted(jobs.values(), key=lambda x: x['id'], reverse=True):
        groups[(job['stage'], job['name'])].append(job)
    selected = [key for key in groups if selectors_set is None or key in selectors_set][:max_job_types]
    retained = sorted({j['id'] for key in selected for j in groups[key][:64]}, reverse=True)
    baseline = []

    def refresh_job(jid):
        at = now()
        try:
            _, raw = transport.json(f"projects/{project['id']}/jobs/{jid}")
            projected = _job(raw, True, at, None)
            if (projected['id'] != jid or projected['pipeline_id'] != jobs[jid]['pipeline_id'] or
                    (projected['stage'], projected['name'], projected['ref']) !=
                    (jobs[jid]['stage'], jobs[jid]['name'], jobs[jid]['ref'])):
                raise TransportError('invalid_response')
            return projected
        except (TransportError, KeyError, TypeError, ValueError) as exc:
            preserved = copy.deepcopy(jobs[jid])
            preserved.update(metadata_checked_at=at, metadata_fresh=False,
                             metadata_error=exc.code if isinstance(exc, TransportError) else 'invalid_response')
            return preserved


    def refresh_pipeline(pid):
        at = now()
        try:
            _, raw = transport.json(f"projects/{project['id']}/pipelines/{pid}")
            projected = _pipeline(raw, True, at, None)
            if projected['id'] != pid or projected['ref'] != pipelines[pid]['ref']:
                raise TransportError('invalid_response')
            return projected
        except (TransportError, KeyError, TypeError, ValueError) as exc:
            preserved = copy.deepcopy(pipelines[pid])
            preserved.update(metadata_checked_at=at, metadata_fresh=False,
                             metadata_error=exc.code if isinstance(exc, TransportError) else 'invalid_response')
            return preserved

    refreshed_pipeline_ids = set()

    def refresh_metadata(job_ids):
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            refreshed = list(pool.map(refresh_job, job_ids))
        requests['metadata'] += len(job_ids)
        jobs.update((j['id'], j) for j in refreshed)
        pipeline_ids = sorted({jobs[jid]['pipeline_id'] for jid in job_ids} - refreshed_pipeline_ids, reverse=True)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            refreshed_pipelines = list(pool.map(refresh_pipeline, pipeline_ids))
        requests['pipelines'] += len(pipeline_ids)
        pipelines.update((p['id'], p) for p in refreshed_pipelines)
        refreshed_pipeline_ids.update(pipeline_ids)

    refresh_metadata(retained)
    for key in selected:
        history = [jobs[j['id']] for j in groups[key]]
        anchors = [j for j in history[:64] if comparison_mode == 'same_ref' or j['ref'] in refs]
        if not anchors:
            continue
        latest = anchors[0]
        def matches_ref(j):
            return j['ref'] == latest['ref'] if comparison_mode == 'same_ref' else j['ref'] in refs
        known_retained = [j for j in history[:64] if j['id'] < latest['id'] and
                          j['metadata_fresh'] and j['status'] == 'success' and
                          pipelines[j['pipeline_id']]['metadata_fresh'] and
                          pipelines[j['pipeline_id']]['status'] == 'success' and matches_ref(j)]
        missing = max(0, 10 - len(known_retained))
        candidates = [j for j in history[64:] if j['id'] < latest['id'] and j['status'] == 'success' and
                      pipelines[j['pipeline_id']]['status'] == 'success' and matches_ref(j)]
        baseline.extend(j['id'] for j in candidates[:missing])
    refresh_metadata(sorted(baseline, reverse=True))
    previous = cache if cache is not None else resume
    previous_jobs = {j['id']: j for j in previous['jobs']} if previous else {}
    previous_traces = {t['job_id']: t for t in previous['traces']} if previous else {}

    def fetch_trace(jid):
        job, at = jobs[jid], now()
        if job['metadata_fresh'] and job['erased_at'] is not None:
            return empty_trace(jid, 'erased', 'metadata_erased', at), False
        if (job['metadata_fresh'] and job['started_at'] is None and
                job['status'] in {'created', 'pending', 'waiting_for_resource', 'manual', 'skipped'}):
            return empty_trace(jid, 'not_run', 'metadata_not_run', at), False
        reused = _cache_trace(job, previous_jobs, previous_traces, at, cache_max_age_seconds, trace_bytes, trace_lines)
        if reused is not None:
            return reused, False
        try:
            raw, truncated = transport.trace(f"projects/{project['id']}/jobs/{jid}/trace", trace_bytes, trace_lines)
            return parse_trace(jid, raw, fetched_at=at, analyzed_at=now(), truncated=truncated), True
        except TransportError as exc:
            state = 'permission_denied' if exc.code == 'permission_denied' else 'unavailable'
            return empty_trace(jid, state, exc.code, at), True

    retained = sorted(set(retained), reverse=True)
    baseline = sorted(set(baseline), reverse=True)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        trace_results = list(pool.map(fetch_trace, retained))
    requests['traces'] += sum(requested for _, requested in trace_results)
    type_limited = selectors_set is None and len(groups) > max_job_types
    stop_reason = 'page_budget' if not complete else 'type_budget' if type_limited else 'eof'
    result = {'schema_version': VERSION, 'kind': 'gitlab_job_performance_source', 'skill_version': SKILL_VERSION,
              'collection_started_at': started, 'collected_at': now(), 'timezone': display_timezone,
              'project': project, 'source': {'transport': 'glab', 'glab_version': transport.version(),
              'gitlab_version': str(version['version']), 'anchor_max_job_id': anchor,
              'pages': invocation_pages + (resume['source']['pages'] if resume else 0), 'cursor': endpoint,
              'complete_available_history': complete, 'stop_reason': stop_reason,
              'resumed_from_sha256': digest(resume) if resume else None, 'requests': requests,
              'budgets': {'max_pages': max_pages, 'max_job_types': max_job_types, 'retained_per_type': 64,
                          'baseline_per_type': 10, 'concurrency': concurrency, 'trace_bytes': trace_bytes,
                          'trace_lines': trace_lines, 'timeout_seconds': 60},
              'observed_counts': [{'type_id': type_id(project, stage, name), 'stage': stage, 'name': name,
                                   'available_count': len(history), 'count_kind': 'exact' if complete else 'lower_bound'}
                                  for (stage, name), history in groups.items()],
              'selection_policy': {'comparison_mode': comparison_mode, 'refs': sorted(set(refs or [])),
                                   'job_selectors': sorted(job_selectors or [], key=lambda x: (x['stage'], x['name'])),
                                   'cache_max_age_seconds': cache_max_age_seconds},
              'limitations': LIMITATIONS[:]},
              'jobs': sorted(jobs.values(), key=lambda x: x['id'], reverse=True),
              'pipelines': sorted(pipelines.values(), key=lambda x: x['id'], reverse=True),
              'retained_job_ids': retained, 'baseline_job_ids': baseline,
              'traces': [trace for trace, _ in trace_results]}
    validate(result, 'jobs')
    return result
