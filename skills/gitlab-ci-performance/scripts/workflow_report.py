"""Versioned workflow models, bounded pipeline collection and interval calculations.

No project names are built into this module. Definitions are verified by the
agent; the helper validates/applies them and never infers CI dependencies.
"""
import copy
import hashlib
import math
from pathlib import Path
import re
from urllib.parse import quote, urlsplit, parse_qs
from zoneinfo import ZoneInfo

import ci_report as ci

VERSION = '2.0.0'
TERMINAL = {'success', 'failed', 'canceled', 'skipped'}
ACTIVE = ci.ACTIVE | {'scheduled', 'canceling', 'waiting_for_callback'}
METRICS = ('elapsed_seconds', 'active_seconds')


def unique(values, label):
    if len(set(values)) != len(values):
        raise ValueError(f'Duplicate {label}')


def validate_definitions(document):
    unique([e['id'] for e in document['evidence']], 'evidence ID')
    evidence = {e['id'] for e in document['evidence']}
    unique([w['id'] for w in document['workflows']], 'workflow ID')
    for workflow in document['workflows']:
        unique([v['version'] for v in workflow['versions']], 'definition version')
        for version in workflow['versions']:
            if not set(version['evidence_ids']) <= evidence:
                raise ValueError('Unknown evidence ID')
            rules = version['jobs']
            unique([j['id'] for j in rules], 'operation ID')
            unique([(j['name'], j['stage']) for j in rules], 'job selector')
            ids = {j['id'] for j in rules}
            if workflow['type'] == 'chain' and not any(j['required'] for j in rules):
                raise ValueError('Chain must have a required job')
            for rule in rules:
                if not set(rule['needs']) <= ids or rule['id'] in rule['needs']:
                    raise ValueError('Unknown/self dependency')
                if workflow['type'] == 'independent' and (rule['needs'] or rule['parallel_group']):
                    raise ValueError('Independent operations cannot declare dependencies/parallel groups')
            graph = {j['id']: j['needs'] for j in rules}
            done, visiting = set(), set()

            def visit(node):
                if node in visiting:
                    raise ValueError('Dependency cycle')
                if node in done:
                    return
                visiting.add(node)
                for parent in graph[node]:
                    visit(parent)
                visiting.remove(node)
                done.add(node)
            for node in graph:
                visit(node)


def validate_artifact(value, kind):
    from jsonschema import Draft202012Validator, FormatChecker
    schema = ci.load(ci.ROOT / 'schemas' / f'{kind}.schema.json')
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        error = errors[0]
        raise ValueError(f"JSON Schema: {'.'.join(map(str, error.path)) or 'root'}: {error.validator}")
    # jsonschema comparisons alone do not reject NaN.
    ci.encoded(value)
    if kind == 'workflows':
        validate_definitions(value)
    elif kind in {'workflow-jobs', 'workflow-report'}:
        unique([p['id'] for p in value['pipelines']], 'pipeline ID')
        unique([j['id'] for j in value['jobs']], 'attempt ID')
        pmap = {p['id']: p for p in value['pipelines']}
        if set(value['source']['pipelines']) != {str(p) for p in pmap}:
            raise ValueError('Pipeline coverage relation mismatch')
        for job in value['jobs']:
            if job['pipeline_id'] not in pmap or job['ref'] != pmap[job['pipeline_id']]['ref']:
                raise ValueError('Job/pipeline relation mismatch')
        if kind == 'workflow-report':
            validate_artifact(value['definitions'], 'workflows')
            validate_views(value)
    elif kind == 'workflow-llm':
        validate_artifact(value['definitions'], 'workflows')


def validate_views(report):
    jobs = {j['id']: j for j in report['jobs']}
    pipelines = {p['id']: p for p in report['pipelines']}
    for view in report['views']:
        unique(view['pipeline_ids'], 'view pipeline ID')
        ids = set(view['pipeline_ids'])
        if not ids <= pipelines.keys() or len(ids) > view['window']:
            raise ValueError('Invalid pipeline window')
        if set(view['job_attempt_ids']) != {j['id'] for j in jobs.values() if j['pipeline_id'] in ids}:
            raise ValueError('View does not contain every retained attempt')
        for series in view['series']:
            unique([r['pipeline_id'] for r in series['runs']], 'series run')
            if {r['pipeline_id'] for r in series['runs']} != ids:
                raise ValueError('Series/window mismatch')
            for run in series['runs']:
                for aid in run['attempt_ids']:
                    if aid not in jobs or jobs[aid]['pipeline_id'] != run['pipeline_id']:
                        raise ValueError('Invalid run attempt reference')
                if run['eligible_success'] and (run['state'] != 'completed' or not run['coverage']['elapsed_exact']):
                    raise ValueError('Ineligible successful measurement')
                for member in run['members']:
                    if not set(member['attempt_ids']) <= set(run['attempt_ids']):
                        raise ValueError('Invalid member attempt reference')
                    if member['latest_attempt_id'] != max(member['attempt_ids'], default=None):
                        raise ValueError('Outcome does not reference latest retained attempt')
            for comparison in series['comparisons'].values():
                if comparison['n'] != len(comparison['sample_pipeline_ids']):
                    raise ValueError('Comparison sample count mismatch')


def stamp_definitions(model, config, evidence_id, source_url, commit, ref, verified_at, pipeline_ids, pipeline_shas):
    result = copy.deepcopy(model)
    result.update(kind='workflows', schema_version=VERSION)
    record = dict(id=evidence_id, source_url=source_url, commit=commit, ref=ref,
                  config_sha256=hashlib.sha256(Path(config).read_bytes()).hexdigest(),
                  verified_at=verified_at, pipeline_ids=pipeline_ids, pipeline_shas=pipeline_shas)
    result['evidence'] = [e for e in result.get('evidence', []) if e['id'] != evidence_id] + [record]
    validate_artifact(result, 'workflows')
    return result


def safe_time(value):
    try:
        parsed = ci.timestamp(value)
        return parsed if parsed.utcoffset() is not None else None
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def next_endpoint(headers, host, path, required_query=None):
    match = re.search(r'<([^>]+)>;\s*rel="next"', headers, re.I)
    if not match:
        return None
    url = urlsplit(match.group(1))
    query = parse_qs(url.query)
    if (url.scheme != 'https' or url.netloc != host or url.username or url.password or
            url.path != '/api/v4/' + path or url.fragment or
            re.search(r'token|authorization', url.query, re.I) or
            any(query.get(k) != [v] for k, v in (required_query or {}).items())):
        raise ValueError('Unsafe workflow pagination target')
    return path + ('?' + url.query if url.query else '')


def collect(host, project_path, display_timezone='UTC', window=32, max_pages=10, api=None):
    if window not in (32, 64) or max_pages < 1:
        raise ValueError('Workflow window must be 32/64 and max-pages positive')
    if not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]+)?', host):
        raise ValueError('Invalid hostname')
    ZoneInfo(display_timezone)
    api = api or ci.request
    started = ci.now()
    _, raw_project = api(host, 'projects/' + quote(project_path, safe=''))
    _, version = api(host, 'version')
    project = dict(id=raw_project['id'], path=raw_project['path_with_namespace'], host=host,
                   web_url=raw_project['web_url'], default_branch=raw_project['default_branch'])
    path = f"projects/{project['id']}/pipelines"
    endpoint = path + '?per_page=100&order_by=id&sort=desc'
    retained, seen, pages, anchor, listing_complete = [], set(), 0, None, True
    history_exhausted = False
    while endpoint and len(retained) < window:
        if pages >= max_pages or endpoint in seen:
            listing_complete = False
            break
        seen.add(endpoint)
        try:
            headers, batch = api(host, endpoint)
        except (ValueError, OSError, ci.subprocess.TimeoutExpired):
            listing_complete = False
            break
        if not isinstance(batch, list):
            raise ValueError('Pipelines API returned non-array')
        pages += 1
        if anchor is None and batch:
            anchor = max(p['id'] for p in batch)
        remaining = window - len(retained)
        eligible_batch = [p for p in batch if p['id'] <= anchor] if anchor is not None else batch
        for raw in batch:
            if anchor is not None and raw['id'] > anchor:
                continue
            if any(p['id'] == raw['id'] for p in retained):
                raise ValueError('Duplicate pipeline ID')
            retained.append(raw)
            if len(retained) == window:
                break
        following = next_endpoint(headers, host, path, {'order_by':'id', 'sort':'desc'})
        history_exhausted = following is None and len(eligible_batch) <= remaining
        endpoint = following if len(retained) < window else None
    pipelines, jobs, coverage = [], [], {}
    for raw in retained:
        pid = raw['id']
        state = dict(metadata_complete=True, jobs_complete=True, pages=0, anchor_job_id=None, error=None)
        try:
            _, detail = api(host, f'{path}/{pid}')
            pipeline = ci.project_pipeline(detail)
            if pipeline['id'] != pid:
                raise ValueError('Pipeline detail identity mismatch')
            if pipeline['source'] == 'unknown' or any(not safe_time(pipeline[k]) for k in ['created_at']):
                state['metadata_complete'] = False
                state['error'] = 'missing_pipeline_metadata'
        except (ValueError, OSError, KeyError, ci.subprocess.TimeoutExpired):
            state.update(metadata_complete=False, error='pipeline_metadata_unavailable')
            pipeline = dict(id=pid, ref=raw.get('ref','unknown'), sha=raw.get('sha','unknown'),
                            status=raw.get('status','unknown'), source=raw.get('source','unknown'),
                            created_at=raw.get('created_at'), started_at=None, finished_at=None,
                            duration_seconds=None, queued_seconds=None,
                            web_url=raw.get('web_url',project['web_url']+f'/-/pipelines/{pid}'))
        pipelines.append(pipeline)
        job_path = f'{path}/{pid}/jobs'
        endpoint = job_path + '?per_page=100&include_retried=true'
        visited, job_ids = set(), set()
        while endpoint:
            if state['pages'] >= max_pages or endpoint in visited:
                state.update(jobs_complete=False, error='job_pagination_limit_or_cycle')
                break
            visited.add(endpoint)
            try:
                headers, batch = api(host, endpoint)
            except (ValueError, OSError, ci.subprocess.TimeoutExpired):
                state.update(jobs_complete=False, error='jobs_api_unavailable')
                break
            if not isinstance(batch, list):
                raise ValueError('Pipeline jobs API returned non-array')
            state['pages'] += 1
            if state['anchor_job_id'] is None and batch:
                state['anchor_job_id'] = max(j['id'] for j in batch)
            for raw_job in batch:
                if raw_job['id'] > state['anchor_job_id']:
                    state.update(jobs_complete=False, error='attempt_created_after_anchor')
                    continue
                if raw_job['id'] in job_ids:
                    raise ValueError('Duplicate attempt ID')
                job_ids.add(raw_job['id'])
                job = ci.project_job(raw_job)
                if job['pipeline_id'] != pid:
                    raise ValueError('Job belongs to unrelated pipeline')
                jobs.append(job)
            endpoint = next_endpoint(headers, host, job_path, {'include_retried':'true'})
        coverage[str(pid)] = state
    result = dict(kind='workflow-jobs', schema_version=VERSION, collection_started_at=started,
        collected_at=ci.now(), timezone=display_timezone, project=project, pipelines=pipelines,
        jobs=sorted(jobs,key=lambda j:j['id']), source=dict(transport='glab',glab_version='glab API transport',
            gitlab_version=version['version'],requested_window=window,anchor_pipeline_id=anchor,
            pipeline_pages=pages,max_pages=max_pages,pipeline_list_complete=listing_complete,
            pipeline_history_exhausted=history_exhausted,
            pipelines=coverage,limitations=['API collection is not atomic; deleted jobs cannot be recovered',
                'Bridge/trigger and child pipelines are not collected; cross-pipeline scenarios are unsupported',
                'No traces or variables are collected; history is bounded by pipeline count and page limit']))
    validate_artifact(result, 'workflow-jobs')
    return result


def applicable_versions(workflow, pipeline, evidence):
    matches = []
    for version in workflow['versions']:
        selection = version['selection']
        if selection['refs'] and pipeline['ref'] not in selection['refs']:
            continue
        if selection['sources'] and pipeline['source'] not in selection['sources']:
            continue
        proofs = [evidence[e] for e in version['evidence_ids']]
        if any(pipeline['id'] in e['pipeline_ids'] or pipeline['sha'] in e['pipeline_shas'] for e in proofs):
            matches.append(version)
    return matches


def union_seconds(intervals):
    if not intervals:
        return None
    ordered = sorted(intervals)
    begin, end = ordered[0]
    total = 0.0
    for left, right in ordered[1:]:
        if left <= end:
            end = max(end, right)
        else:
            total += (end-begin).total_seconds()
            begin, end = left, right
    return total + (end-begin).total_seconds()


def calculate_run(workflow, operation, pipeline, jobs, source_coverage, matches, evidence):
    version = matches[0] if len(matches) == 1 else None
    config_verified = version is not None and not version['unknown_membership']
    source_complete = source_coverage['jobs_complete'] and source_coverage['metadata_complete']
    reasons, members, retained = [], [], []
    if not version:
        reasons.append('historical_configuration_unknown' if not matches else 'ambiguous_definition_versions')
    elif version['unknown_membership']:
        reasons.append('unknown_membership')
    if not source_complete:
        reasons.append('partial_source_coverage')
    rules = [r for r in version['jobs'] if operation is None or r['id']==operation] if version else []
    if version and not rules:
        config_verified = False
        reasons.append('operation_not_in_definition_version')
    for rule in rules:
        attempts = sorted([j for j in jobs if (j['name'],j['stage'])==(rule['name'],rule['stage'])], key=lambda j:j['id'])
        latest = attempts[-1] if attempts else None
        retained.extend(attempts)
        members.append(dict(job_id=rule['id'],required=rule['required'] or operation is not None,
            manual=rule['manual'], attempt_ids=[j['id'] for j in attempts],
            latest_attempt_id=latest['id'] if latest else None, outcome=latest['status'] if latest else 'missing'))
    required = [m for m in members if m['required']]
    # An unstarted optional manual/skipped operation does not hold the chain open.
    relevant = [m for m in members if m['required'] or any(
        j['started_at'] is not None or j['status'] not in {'manual','skipped','created'}
        for j in retained if j['id'] in m['attempt_ids'])]
    statuses = [m['outcome'] for m in relevant]
    required_terminal = bool(required) and all(m['outcome'] in TERMINAL for m in required)
    all_terminal = required_terminal and all(x in TERMINAL for x in statuses)
    if not config_verified or not source_complete or any(m['outcome']=='missing' for m in required):
        state = 'unknown/incomplete'
    elif any(x in ACTIVE for x in statuses):
        state = 'active'
    elif 'manual' in statuses:
        state = 'waiting-manual'
    elif any(m['outcome']=='failed' for m in required):
        state = 'failed'
    elif any(m['outcome']=='canceled' for m in required):
        state = 'canceled'
    elif required and all(m['outcome']=='success' for m in required) and all_terminal:
        state = 'completed'
    else:
        state = 'unknown/incomplete'
    execution = [j for j in retained if j['started_at'] is not None or j['finished_at'] is not None or
                 j['status'] not in {'manual','skipped','created'}]
    intervals = []
    for job in execution:
        start, finish = safe_time(job['started_at']), safe_time(job['finished_at'])
        if start is not None and finish is not None and finish >= start:
            intervals.append((start,finish))
    missing = len(execution)-len(intervals)
    if missing:
        reasons.append('missing_malformed_or_open_execution_intervals')
    queue = [j['queued_seconds'] for j in retained if j['queued_seconds'] is not None]
    active = union_seconds(intervals)
    active_exact = source_complete and config_verified and missing == 0 and bool(intervals)
    elapsed_exact = active_exact and all_terminal and state in {'completed','failed','canceled'}
    first = min((x[0] for x in intervals),default=None)
    last = max((x[1] for x in intervals),default=None)
    elapsed = (last-first).total_seconds() if elapsed_exact else None
    cohort = ci.digest(dict(workflow_id=workflow['id'], operation_id=operation, version=version['version'],
        rules=version['jobs'], selection=version['selection'], completion=version['completion'],
        success=version['success'],ref=pipeline['ref'],source=pipeline['source'])) if version else None
    applied_evidence = [e for e in version['evidence_ids'] if pipeline['id'] in evidence[e]['pipeline_ids'] or
                        pipeline['sha'] in evidence[e]['pipeline_shas']] if version else []
    return dict(pipeline_id=pipeline['id'],workflow_id=workflow['id'],operation_id=operation,
        definition_version=version['version'] if version else None,cohort_key=cohort,
        axis_at=pipeline['created_at'] if safe_time(pipeline['created_at']) else None,
        execution_started_at=first.isoformat() if first else None,
        execution_finished_at=last.isoformat() if last else None,
        state=state,eligible_success=state=='completed' and elapsed_exact,
        attempt_ids=sorted(j['id'] for j in retained),members=members,evidence_ids=applied_evidence,
        metrics=dict(elapsed_seconds=elapsed,active_seconds=active,queue_sum_seconds=sum(queue) if queue else None,
                     gap_seconds=elapsed-active if elapsed is not None else None),
        coverage=dict(source_complete=source_complete,configuration_verified=config_verified,
            interval_known=len(intervals),interval_missing=missing,queue_known=len(queue),
            queue_missing=len(retained)-len(queue),active_exact=active_exact,
            queue_exact=source_complete and config_verified and len(queue)==len(retained) and bool(retained),
            elapsed_exact=elapsed_exact,reasons=reasons))


def comparison(runs, key, visible_ids):
    eligible = [r for r in runs if r['eligible_success'] and r['metrics'][key] is not None]
    current = eligible[-1] if eligible else None
    earlier = [r for r in eligible[:-1] if r['cohort_key']==current['cohort_key']][-10:] if current else []
    median = ci.percentile([r['metrics'][key] for r in earlier],.5)
    value = current['metrics'][key] if current else None
    sufficient = len(earlier) >= 3
    delta = value-median if sufficient else None
    return dict(metric=key,current_pipeline_id=current['pipeline_id'] if current else None,
        current_seconds=value,sample_pipeline_ids=[r['pipeline_id'] for r in earlier],
        sample_run_ids=[f"{r['workflow_id']}/{r['operation_id'] or 'chain'}/{r['pipeline_id']}" for r in earlier],
        n=len(earlier),median_seconds=median,delta_seconds=delta,
        delta_percent=delta/median*100 if delta is not None and median > 0 else None,
        eligible=sufficient,reason='comparable_successes' if sufficient else 'minimum_three_preceding_successes_required',
        cohort_key=current['cohort_key'] if current else None,
        extends_visible_window=bool(current and (current['pipeline_id'] not in visible_ids or
                                   any(r['pipeline_id'] not in visible_ids for r in earlier))))


def build_report(snapshot, definitions):
    validate_artifact(snapshot, 'workflow-jobs')
    validate_artifact(definitions, 'workflows')
    for key in ('host','path'):
        if definitions['project'][key] != snapshot['project'][key]:
            raise ValueError('Workflow definitions belong to different host/project')
    ZoneInfo(snapshot['timezone'])
    evidence = {e['id']:e for e in definitions['evidence']}
    # Windows are selected by explicit pipeline identity; the axis is creation time.
    pipelines = sorted(snapshot['pipelines'],key=lambda p:p['id'],reverse=True)
    views = []
    for window in (32,64):
        selected = pipelines[:window]
        ids = {p['id'] for p in selected}
        visible_jobs = [j for j in snapshot['jobs'] if j['pipeline_id'] in ids]
        series = []
        for workflow in definitions['workflows']:
            operations = list(dict.fromkeys(j['id'] for v in workflow['versions'] for j in v['jobs'])) if workflow['type']=='independent' else [None]
            for operation in operations:
                runs = []
                for pipeline in reversed(selected):
                    jobs = [j for j in visible_jobs if j['pipeline_id']==pipeline['id']]
                    matches = applicable_versions(workflow,pipeline,evidence)
                    runs.append(calculate_run(workflow,operation,pipeline,jobs,
                        snapshot['source']['pipelines'][str(pipeline['id'])],matches,evidence))
                series.append(dict(id=workflow['id']+('/'+operation if operation else ''),
                    workflow_id=workflow['id'],operation_id=operation,purpose=workflow['purpose'],type=workflow['type'],
                    runs=runs,successful_samples=sum(r['eligible_success'] for r in runs),
                    comparisons={key:comparison(runs,key,ids) for key in METRICS}))
        assigned = {aid for item in series for run in item['runs'] for aid in run['attempt_ids']}
        axis = [p['created_at'] for p in selected if safe_time(p['created_at'])]
        views.append(dict(window=window,window_unit='pipeline_runs',pipeline_ids=[p['id'] for p in selected],
            job_attempt_ids=sorted(j['id'] for j in visible_jobs),
            unassigned_attempt_ids=sorted(j['id'] for j in visible_jobs if j['id'] not in assigned),
            actual_from=min(axis,key=ci.timestamp) if axis else None,actual_to=max(axis,key=ci.timestamp) if axis else None,
            source_window_complete=snapshot['source']['pipeline_list_complete'] and
                (window <= snapshot['source']['requested_window'] or snapshot['source']['pipeline_history_exhausted']) and
                all(snapshot['source']['pipelines'][str(p['id'])]['jobs_complete'] and
                    snapshot['source']['pipelines'][str(p['id'])]['metadata_complete'] for p in selected),series=series))
    result = dict(kind='workflow-report',schema_version=VERSION,calculation_version=VERSION,
        generated_at=ci.now(),timezone=snapshot['timezone'],project=snapshot['project'],
        inputs=dict(snapshot_sha256=ci.digest(snapshot),definitions_sha256=ci.digest(definitions)),
        method=dict(time_axis='pipeline.created_at',comparison_limit=10,minimum_baseline=3,units='seconds',
            display_unit_scope='selected-series-and-metric',cross_pipeline_policy='unsupported',
            timing_provenance='API started_at/finished_at interval union; API queued_duration sum'),
        definitions=copy.deepcopy(definitions),source=copy.deepcopy(snapshot['source']),views=views,
        jobs=copy.deepcopy(snapshot['jobs']),pipelines=copy.deepcopy(snapshot['pipelines']))
    validate_artifact(result,'workflow-report')
    return result


def compact_export(report):
    validate_artifact(report,'workflow-report')
    result = {k:copy.deepcopy(v) for k,v in report.items() if k not in {'jobs','pipelines'}}
    result.update(kind='workflow-llm',report_sha256=ci.digest(report))
    validate_artifact(result,'workflow-llm')
    return result
