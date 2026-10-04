"""Bounded read-only detail collection. Raw logs never enter public artifacts."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import tempfile
import time

VERSION = '2.0.0'
TERMINAL = {'success', 'failed', 'canceled', 'skipped'}
NOT_RUN = {'created', 'pending', 'manual', 'scheduled', 'skipped', 'waiting_for_resource', 'preparing', 'canceled'}
ACTIVE = {'running', 'canceling', 'preparing'}
BASE_KEYS = ('id', 'pipeline_id', 'name', 'stage', 'ref', 'status', 'allow_failure',
             'created_at', 'started_at', 'finished_at', 'duration_seconds', 'queued_seconds',
             'failure_reason', 'web_url')


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def _project_job(raw, source=False):
    if source:
        job = {key: raw.get(key) for key in BASE_KEYS}
    else:
        job = {key: raw.get(key) for key in BASE_KEYS}
        job.update(pipeline_id=raw['pipeline']['id'], duration_seconds=raw.get('duration'),
                   queued_seconds=raw.get('queued_duration'))
    runner = raw.get('runner')
    job['runner'] = None if not runner else {'id': runner['id'], 'description': runner.get('description') or ''}
    commit = raw.get('commit') or {}
    manager = raw.get('runner_manager') or {}
    job.update(commit_sha=raw.get('commit_sha') if source else commit.get('id'),
               erased_at=raw.get('erased_at'),
               runner_version=raw.get('runner_version') if source else manager.get('version'))
    if not job.get('started_at') and job.get('status') in NOT_RUN:
        job['duration_seconds'] = None
    return job


def _request_json(host, endpoint):
    result = subprocess.run(['glab', 'api', '--hostname', host, '--method', 'GET', endpoint],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    if result.returncode:
        raise ValueError('metadata_request_failed')
    return json.loads(result.stdout)


def _request_trace(host, endpoint, max_trace_bytes):
    """Stream at most cap+1 bytes; deadline also bounds a stalled stdout pipe."""
    proc = subprocess.Popen(['glab', 'api', '--hostname', host, '--method', 'GET', endpoint],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    chunks = []
    received = 0
    deadline = time.monotonic() + 60
    selector = selectors.DefaultSelector()
    try:
        selector.register(proc.stdout, selectors.EVENT_READ)
        while received < max_trace_bytes + 1:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('trace_timeout')
            if not selector.select(remaining):
                raise TimeoutError('trace_timeout')
            chunk = os.read(proc.stdout.fileno(), min(65536, max_trace_bytes + 1 - received))
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
        if received > max_trace_bytes:
            proc.kill()
        else:
            proc.wait(timeout=max(.001, deadline - time.monotonic()))
            if proc.returncode:
                raise ValueError('trace_request_failed')
        return b''.join(chunks)
    finally:
        selector.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()


def _bounded_trace(response, cap):
    status = 200
    if isinstance(response, tuple) and len(response) == 2 and isinstance(response[0], int):
        status, response = response
    if status != 200:
        return status, b''
    if isinstance(response, (bytes, bytearray)):
        return status, bytes(response[:cap + 1])
    chunks = []
    total = 0
    try:
        for chunk in response:
            if not isinstance(chunk, (bytes, bytearray)):
                raise ValueError('trace_invalid_response')
            part = bytes(chunk[:cap + 1 - total])
            chunks.append(part)
            total += len(part)
            if total >= cap + 1:
                break
    finally:
        close = getattr(response, 'close', None)
        if close:
            close()
    return status, b''.join(chunks)


def _summary(job_id, status, analyzed_at, limitation):
    return dict(job_id=job_id, trace_status=status, trace_sha256=None, trace_bytes=0,
                processed_bytes=0, trace_lines=0, timestamp_lines=0, analyzed_at=analyzed_at,
                parser_version=VERSION, phases=[], builds=[], commands=[], limitations=[limitation])


def _cache_directory(root, project):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('Unsafe trace cache directory')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    identity = digest({'host': project['host'], 'project_id': project['id'], 'project_path': project['path']})
    directory = root / identity
    if directory.is_symlink():
        raise ValueError('Unsafe trace cache directory')
    directory.mkdir(exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    return directory


def _manifest(job, project, fetched_at, raw, complete):
    return {'host': project['host'], 'project_id': project['id'], 'project_path': project['path'],
            'job_id': job['id'], 'status': job['status'], 'finished_at': job['finished_at'],
            'fetched_at': fetched_at, 'trace_sha256': hashlib.sha256(raw).hexdigest(),
            'trace_bytes': len(raw), 'complete': complete}


def _cache_load(directory, project, job, cap):
    if job['status'] not in TERMINAL or not job['finished_at']:
        return None
    manifest_path = directory / f"{job['id']}.json"
    trace_path = directory / f"{job['id']}.trace"
    try:
        for path in (manifest_path, trace_path):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                return None
        if manifest_path.stat().st_size > 65536 or trace_path.stat().st_size > cap:
            return None
        manifest = json.loads(manifest_path.read_bytes())
        raw = trace_path.read_bytes()
        stamp = datetime.fromisoformat(manifest['fetched_at'].replace('Z', '+00:00'))
        if stamp.utcoffset() is None or stamp > datetime.now(timezone.utc):
            return None
        expected = _manifest(job, project, manifest['fetched_at'], raw, True)
        if manifest != expected:
            return None
        return raw, manifest['fetched_at']
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _private_save(path, raw):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(raw)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _cache_save(directory, project, job, fetched_at, raw, complete):
    _private_save(directory / f"{job['id']}.trace", raw)
    _private_save(directory / f"{job['id']}.json", encoded(_manifest(job, project, fetched_at, raw, complete)))


def collect_details(snapshot, workers=4, job_names=None, stages=None, trace_cache=None,
                    reuse_cache=False, no_traces=False, max_trace_bytes=32*1024*1024,
                    request_json=None, request_trace=None):
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError('workers must be an integer between 1 and 8')
    if type(max_trace_bytes) is not int or max_trace_bytes <= 0:
        raise ValueError('max_trace_bytes must be a positive integer')
    project = dict(snapshot['project'])
    if not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]+)?', project['host']):
        raise ValueError('Invalid hostname')
    if type(project['id']) is not int or project['id'] <= 0:
        raise ValueError('Invalid project ID')
    started = now()
    groups = defaultdict(list)
    names = None if job_names is None else set(job_names)
    stage_set = None if stages is None else set(stages)
    seen = set()
    for job in snapshot['jobs']:
        if type(job['id']) is not int or job['id'] <= 0 or job['id'] in seen:
            raise ValueError('Invalid or duplicate job ID')
        seen.add(job['id'])
        if (names is None or job['name'] in names) and (stage_set is None or job['stage'] in stage_set):
            groups[(job['stage'], job['name'])].append(job)
    types = []
    retained = []
    for index, ((stage, name), jobs) in enumerate(sorted(groups.items()), 1):
        jobs = sorted(jobs, key=lambda j:j['id'], reverse=True)
        retained.extend(jobs[:64])
        types.append(dict(id=f't{index}', name=name, stage=stage, source_count=len(jobs),
                          retained_ids=[j['id'] for j in jobs[:64]]))
    retained.sort(key=lambda j:j['id'], reverse=True)
    metadata_request = request_json or _request_json
    trace_request = request_trace or _request_trace
    cache_directory = _cache_directory(trace_cache, project) if trace_cache is not None and not no_traces else None
    from trace_parser import parse_trace

    def fetch(source):
        job = _project_job(source, source=True)
        stamp = snapshot['collected_at']
        metadata_error = None
        metadata_status = 'fresh'
        try:
            raw = metadata_request(project['host'], f"projects/{project['id']}/jobs/{job['id']}")
            if isinstance(raw, tuple):
                raw = raw[1]
            if (raw.get('id'), raw.get('name'), raw.get('stage'), raw.get('ref'),
                (raw.get('pipeline') or {}).get('id')) != (job['id'],job['name'],job['stage'],job['ref'],job['pipeline_id']):
                metadata_error = 'metadata_identity_mismatch'
                metadata_status = 'stale'
            else:
                refreshed = _project_job(raw)
                # Ensure adapters cannot bypass the JSON-only transport contract.
                encoded(refreshed)
                job = refreshed
                stamp = now()
        except Exception:
            metadata_error = 'metadata_request_failed'
            metadata_status = 'stale'
        entry = dict(job_id=job['id'], job=job, metadata_status=metadata_status,
                     metadata_collected_at=stamp, trace_status=None, trace_source='none',
                     trace_collected_at=None, metadata_error=metadata_error)
        requests = 0
        received = 0
        analysis_stamp = now()
        if no_traces:
            detail = _summary(job['id'],'disabled',analysis_stamp,'trace_disabled')
        elif not job['started_at'] and job['status'] in NOT_RUN:
            detail = _summary(job['id'],'not_run',analysis_stamp,'job_not_run')
        elif job['erased_at']:
            detail = _summary(job['id'],'erased',analysis_stamp,'trace_erased')
        else:
            cached = _cache_load(cache_directory,project,job,max_trace_bytes) if cache_directory and reuse_cache and metadata_status == 'fresh' else None
            if cached:
                raw, fetched_at = cached
                entry.update(trace_source='cache', trace_collected_at=fetched_at)
                detail = parse_trace(raw,job,analysis_stamp)
            else:
                requests = 1
                try:
                    response = trace_request(project['host'], f"projects/{project['id']}/jobs/{job['id']}/trace",max_trace_bytes)
                    status, raw = _bounded_trace(response,max_trace_bytes)
                    if status != 200:
                        detail = _summary(job['id'],'unavailable',analysis_stamp,
                                          'trace_forbidden' if status == 403 else 'trace_unavailable')
                    else:
                        received = len(raw)
                        truncated = received > max_trace_bytes
                        processed = raw[:max_trace_bytes]
                        entry.update(trace_source='live',trace_collected_at=now())
                        detail = parse_trace(processed,job,analysis_stamp,truncated=truncated)
                        if job['status'] in ACTIVE:
                            detail['trace_status'] = 'partial'
                            detail['limitations'] = sorted(set(detail['limitations']+['active_trace']))
                        if received > max_trace_bytes:
                            detail['trace_bytes'] = received
                            detail['limitations'] = sorted(set(detail['limitations']+['trace_byte_limit']))
                        if cache_directory:
                            try:
                                _cache_save(cache_directory,project,job,entry['trace_collected_at'],processed,
                                            not truncated and detail['trace_status'] in {'available','empty'})
                            except OSError:
                                detail['limitations'] = sorted(set(detail['limitations']+['trace_cache_write_failed']))
                except Exception as exc:
                    detail = _summary(job['id'],'unavailable',analysis_stamp,
                                      'trace_timeout' if isinstance(exc,(TimeoutError,subprocess.TimeoutExpired)) else 'trace_request_failed')
        entry['trace_status'] = detail['trace_status']
        return entry,detail,requests,received

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(fetch,retained))
    jobs = [item[0] for item in results]
    details = [item[1] for item in results]
    metadata = dict(kind='metadata',schema_version=VERSION,collection_started_at=started,collected_at=now(),
                    timezone=snapshot['timezone'],project=project,
                    source=dict(snapshot_sha256=digest(snapshot),source_attempts=len(snapshot['jobs']),
                                source_complete_available_history=bool(snapshot['source']['complete_available_history'])),
                    types=types,jobs=jobs,
                    coverage=dict(retained_attempts=len(retained),metadata_requests=len(retained),
                                  metadata_fresh=sum(j['metadata_status']=='fresh' for j in jobs),
                                  trace_requests=sum(item[2] for item in results),
                                  trace_status_counts=dict(sorted(Counter(j['trace_status'] for j in jobs).items())),
                                  workers=workers,max_trace_bytes=max_trace_bytes,
                                  trace_bytes_received=sum(item[3] for item in results)),
                    limitations=['collection_not_atomic','details_retained_64_per_type','traces_may_be_unavailable'])
    timings = dict(kind='timings',schema_version=VERSION,parser_version=VERSION,analyzed_at=now(),
                   timezone=snapshot['timezone'],project=project,
                   source=dict(snapshot_sha256=digest(snapshot),metadata_sha256=digest(metadata)),details=details)
    return metadata,timings
