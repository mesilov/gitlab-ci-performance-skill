"""Offline v2 calculation; every supported view is materialized here."""
from report_contract import SKILL_VERSION, VERSION, PARSER_VERSION
from collections import Counter
from copy import deepcopy
from statistics import median
from urllib.parse import urlsplit
import math
import re

from report_contract import digest, now, timestamp, type_id, validate

CATEGORIES = ('export_local_unpack', 'context_application_copy', 'base_image',
              'dependencies_builder_setup', 'runner_phase', 'queue')
METRICS = ('queue', 'execution', 'total')
INVESTIGATIONS = {
    'export_local_unpack': {
        'proposed_action': 'Compare image size, exported layers and local unpack time; inspect the configured image output and push coverage.',
        'applicability': 'Applies to recognized image export or local unpack intervals; push coverage must be checked separately.',
        'next_measurement': 'Measure layer bytes, export and local unpack intervals on another comparable successful run.'},
    'context_application_copy': {
        'proposed_action': 'Inspect build context size, ignore rules and COPY ordering; compare transferred files and cache reuse.',
        'applicability': 'Applies to recognized build context transfer or application COPY intervals.',
        'next_measurement': 'Measure context bytes, COPY intervals and cache hits with the same input revision.'},
    'base_image': {
        'proposed_action': 'Inspect base image size, registry latency and image cache availability on the selected runner.',
        'applicability': 'Applies to recognized base image metadata resolution, pull or extraction intervals.',
        'next_measurement': 'Compare registry resolution and base image transfer times on warm and cold runner caches.'},
    'dependencies_builder_setup': {
        'proposed_action': 'Inspect dependency installation and builder setup; compare lockfiles and configured reusable caches.',
        'applicability': 'Applies to recognized dependency or builder setup operations with usable timing.',
        'next_measurement': 'Measure dependency fetch, installation and builder preparation separately for equivalent inputs.'},
    'runner_phase': {
        'proposed_action': 'Inspect the representative runner phase and compare checkout, cache and artifact transfer behavior.',
        'applicability': 'Applies to allowlisted runner section intervals; phase and nested build costs are not additive.',
        'next_measurement': 'Record runner section times and transfer volumes for another successful attempt on the same runner configuration.'},
    'queue': {
        'proposed_action': 'Inspect runner availability, matching tags, concurrency and resource locks at the representative job time.',
        'applicability': 'Applies to GitLab API queued duration; queue delay does not establish an execution bottleneck.',
        'next_measurement': 'Compare queue timing with runner utilization, active jobs and resource lock waits at matching timestamps.'}
}


def _percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    position = (len(values)-1)*fraction
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi]-values[lo])*(position-lo)


def _metric(values):
    known = [v for v in values if v is not None]
    return {'known': len(known), 'missing': len(values)-len(known),
            'median_seconds': median(known) if known else None,
            'p95_seconds': _percentile(known, .95),
            'max_seconds': max(known) if known else None}


def _metrics(attempts):
    return {key: _metric([a['timing'][key]['value_seconds'] for a in attempts])
            for key in METRICS}


def _timing(value, origin, eligible, quality=None):
    if value is not None and (not math.isfinite(value) or value < 0):
        raise ValueError('Invalid negative or non-finite timing')
    quality = quality or ('known' if value is not None else 'missing')
    return {'value_seconds': value, 'origin': origin, 'quality': quality,
            'eligible': bool(eligible and quality == 'known')}


def _attempt(job, pipeline, trace, project):
    eligible = (job['status'] == 'success' and job['metadata_fresh'] and
                pipeline['status'] == 'success' and pipeline['metadata_fresh'] and
                pipeline['ref'] == job['ref'])
    queue, execution = job['queued_seconds'], job['duration_seconds']
    total = queue + execution if queue is not None and execution is not None else None
    lifecycle = None
    if job['finished_at']:
        lifecycle = (timestamp(job['finished_at'])-timestamp(job['created_at'])).total_seconds()
    prestart = None
    prestart_quality = 'missing'
    if job['started_at'] and queue is not None:
        residual = (timestamp(job['started_at'])-timestamp(job['created_at'])).total_seconds()-queue
        if residual >= 0:
            prestart, prestart_quality = residual, 'known'
        else:
            prestart_quality = 'inconsistent'
    timing = {'queue': _timing(queue, 'api_queue', eligible),
              'execution': _timing(execution, 'api_execution', eligible),
              'total': _timing(total, 'derived_total', eligible,
                               'partial' if total is None and (queue is not None or execution is not None) else None),
              'lifecycle': _timing(lifecycle, 'lifecycle', eligible),
              'prestart': _timing(prestart, 'prestart', eligible, prestart_quality)}
    return {'id': job['id'], 'type_id': type_id(project, job['stage'], job['name']),
            'metadata': deepcopy(job), 'pipeline': deepcopy(pipeline), 'trace': deepcopy(trace),
            'timing': timing, 'baseline_eligible': bool(eligible)}


def _delta(current, baseline, mode):
    center = baseline['median_seconds']
    difference = current-center if current is not None and center is not None else None
    relative = difference/center*100 if difference is not None and center > 0 else None
    if difference is None or baseline['known'] < 3:
        classification = 'insufficient_data'
    else:
        classification = 'increase' if difference > 0 else 'decrease' if difference < 0 else 'unchanged'
        if mode == 'cross_ref':
            classification = 'exploratory_'+classification
    return {'current_seconds': current, 'baseline_seconds': center,
            'delta_seconds': difference, 'delta_percent': relative,
            'classification': classification}


def _bounds(attempts):
    dates = [a['metadata']['created_at'] for a in attempts]
    return (min(dates, key=timestamp), max(dates, key=timestamp)) if dates else (None, None)


def _union(intervals):
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return result


def _category_nodes(trace, category):
    if not trace:
        return []
    return [node for node in trace['evidence']
            if (category == 'runner_phase' and node['kind'] == 'phase') or
               (category != 'runner_phase' and node['kind'] in {'operation', 'part'} and node['code'] == category)]


def _category_sample(attempt, category):
    if category == 'queue':
        value = attempt['timing']['queue']['value_seconds']
        return {'attempt_id': attempt['id'], 'value_seconds': value, 'interval_ids': [],
                'intervals': [], 'complete': value is not None}, []
    nodes = _category_nodes(attempt['trace'], category)
    usable = []
    for node in nodes:
        timing = node['timing']
        if (node['cached'] or not node['complete'] or timing['duration_seconds'] is None or
                timing['start_seconds'] is None or timing['end_seconds'] is None or
                timing['origin'] not in {'section', 'log_interval', 'buildkit_reported'} or
                not (timing['quality'] == 'exact' or
                     (timing['origin'] == 'buildkit_reported' and timing['quality'] == 'inferred'))):
            continue
        usable.append(node)
    ids = {node['id'] for node in usable}
    all_nodes = {node['id']: node for node in (attempt['trace'] or {}).get('evidence', [])}
    included = []
    for node in usable:
        parent, ancestor_included = node['parent_id'], False
        visited = set()
        while parent and parent not in visited:
            visited.add(parent)
            if parent in ids:
                ancestor_included = True
                break
            parent = all_nodes.get(parent, {}).get('parent_id')
        if not ancestor_included:
            included.append(node)
    intervals = _union([[node['timing']['start_seconds'],node['timing']['end_seconds']] for node in included])
    cost = sum(end-start for start,end in intervals) if included else None
    # No recognized category evidence is unknown absence, never a fabricated zero.
    complete = bool(nodes and len(usable)+sum(n['cached'] for n in nodes) == len(nodes)
                    and attempt['trace']['coverage']['complete'])
    return {'attempt_id': attempt['id'], 'value_seconds': cost,
            'interval_ids': [n['id'] for n in included], 'intervals': intervals,
            'complete': complete}, included


def _guidance(guidance):
    if guidance is None:
        return {}
    if set(guidance) != {'categories'} or not isinstance(guidance['categories'], dict):
        raise ValueError('Guidance requires categories mapping')
    required = {'url','page_title','section_title','verified_at','status',
                'applicable_versions','configuration_constraints'}
    for category, records in guidance['categories'].items():
        if category not in CATEGORIES or not isinstance(records, list):
            raise ValueError('Unknown guidance category')
        for record in records:
            if not isinstance(record,dict) or set(record) != required:
                raise ValueError('Guidance fields do not match supported contract')
            url = urlsplit(record['url'])
            official = (url.hostname in {'docs.gitlab.com','docs.docker.com','gitlab.com'} or
                        (url.hostname == 'github.com' and url.path.startswith('/moby/buildkit')))
            if url.scheme != 'https' or not official or url.username or url.password:
                raise ValueError('Guidance URL must be an official HTTPS source')
            if record['status'] not in {'verified','unverified','unavailable'}:
                raise ValueError('Unknown guidance status')
            date = record['verified_at']
            if record['status'] == 'verified' and date is None:
                raise ValueError('Verified guidance requires verification date')
            if date is not None and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
                raise ValueError('Guidance verified_at requires YYYY-MM-DD')
    return guidance['categories']


def _findings(window, attempts, latest, guidance):
    eligible = [a for a in attempts if a['baseline_eligible']]
    metrics = _metrics(eligible)
    queue_values = metrics['queue']
    latest_queue = latest['timing']['queue']['value_seconds']
    center = queue_values['median_seconds']
    if latest_queue is None:
        spike = 'missing'
    elif queue_values['known'] < 3:
        spike = 'insufficient_data'
    elif latest_queue-center > 30 and (center == 0 or latest_queue > 2*center):
        spike = 'spike'
    else:
        spike = 'normal'
    categories = []
    for category in CATEGORIES:
        pairs = [_category_sample(a, category) for a in eligible]
        samples = [p[0] for p in pairs]
        known = [p for p in pairs if p[0]['value_seconds'] is not None]
        center = median([p[0]['value_seconds'] for p in known]) if known else None
        representative = None
        if known:
            chosen = min(known, key=lambda p:(abs(p[0]['value_seconds']-center), p[0]['attempt_id']))
            attempt = next(a for a in eligible if a['id']==chosen[0]['attempt_id'])
            if category == 'queue':
                representative = {'attempt_id': attempt['id'], 'evidence_id': None,
                                  'duration_seconds': chosen[0]['value_seconds'],
                                  'lines': None, 'job_url': attempt['metadata']['web_url']}
            else:
                node = sorted(chosen[1],key=lambda n:(-n['timing']['duration_seconds'],n['id']))[0]
                representative = {'attempt_id': attempt['id'], 'evidence_id': node['id'],
                                  'duration_seconds': node['timing']['duration_seconds'],
                                  'lines': deepcopy(node['lines']), 'job_url': attempt['metadata']['web_url']}
        uncertainty = ['coverage_limited']
        if any(node['timing']['quality'] == 'inferred' for pair in known for node in pair[1]):
            uncertainty.append('inferred_position')
        if not guidance.get(category):
            uncertainty.append('guidance_unavailable')
        observed_fact = ('no_usable_category_timing' if center is None else
                         'api_queue_cost' if category == 'queue' else category+'_interval_union_cost')
        finding = {'observed_fact': observed_fact, 'causal_hypothesis': 'cause_unknown',
                   **INVESTIGATIONS[category], 'uncertainty': ';'.join(uncertainty),
                   'estimated_savings_seconds': None, 'guidance': deepcopy(guidance.get(category,[]))}
        categories.append({'id':'finding-'+digest([window['id'],category])[:20], 'code': category,
                           'known': len(known), 'missing': len(samples)-len(known),
                           'median_seconds': center, 'samples': samples, 'representative': representative,
                           'rank': None, 'finding': finding})
    ranked = sorted([c for c in categories if c['median_seconds'] is not None],
                    key=lambda c:(-c['median_seconds'],c['code']))
    for index, item in enumerate(ranked,1):
        item['rank'] = index
    trace_known = sum(a['trace'] is not None and a['trace']['state'] in {'available','partial','empty'} for a in eligible)
    return {'id': 'finding-'+digest([window['id'],'summary'])[:20],
            'scope': {'type_id': window['type_id'], 'window_id': window['id'],
                      'attempt_ids': window['attempt_ids'][:], 'from': window['from'], 'to': window['to']},
            'eligible_successful_n': len(eligible), 'trace_known_n': trace_known,
            'trace_missing_n': len(eligible)-trace_known, 'metrics': metrics,
            'queue_spike': {'state': spike, 'latest_seconds': latest_queue,
                            'median_seconds': queue_values['median_seconds'], 'known_n': queue_values['known'],
                            'absolute_threshold_seconds': 30, 'relative_multiplier': 2},
            'categories': categories, 'priority_codes': [c['code'] for c in ranked[:3]]}


def _purpose(catalog, snapshot, stage, name):
    fallback = {'description': 'Purpose is not documented in the verified catalog.',
                'source_url': None, 'verified_at': None, 'status': 'unknown'}
    if not catalog or catalog.get('project') != snapshot['project']['path']:
        return fallback
    record = catalog.get('jobs', {}).get(stage+'/'+name, catalog.get('jobs', {}).get(name))
    if record is None:
        return fallback
    if set(record)-{'description','source_url','verified_at','status'}:
        raise ValueError('Unsupported catalog purpose fields')
    value = dict(fallback, **record)
    if 'status' not in record:
        value['status'] = 'verified' if value['source_url'] and value['verified_at'] else 'unverified'
    return value


def build_report(snapshot, baseline=None, *, catalog=None, guidance=None, language='en',
                 comparison_mode='same_ref', refs=None, generated_at=None):
    """Calculate bounded history and findings without any transport access."""
    validate(snapshot, 'source')
    if baseline is not None:
        validate(baseline, 'source')
        if any(baseline['project'][k] != snapshot['project'][k] for k in ('host','id','path')):
            raise ValueError('Baseline belongs to different host/project')
        if timestamp(baseline['collected_at']) > timestamp(snapshot['collected_at']):
            raise ValueError('Baseline is newer than current snapshot')
    if language not in {'en','ru'}:
        raise ValueError('Supported language: en or ru')
    if comparison_mode not in {'same_ref','cross_ref'}:
        raise ValueError('Supported comparison_mode: same_ref or cross_ref')
    if comparison_mode == 'cross_ref' and (not isinstance(refs,(list,tuple)) or not refs or any(not isinstance(r,str) or not r for r in refs)):
        raise ValueError('cross_ref requires explicit nonempty refs allowlist')
    if comparison_mode == 'same_ref' and refs:
        raise ValueError('Explicit refs require cross_ref comparison mode')
    selected_refs = sorted(set(refs or []))
    guide = _guidance(guidance)
    project = snapshot['project']
    pmap = {p['id']:p for p in snapshot['pipelines']}
    tmap = {t['job_id']:t for t in snapshot['traces']}
    all_attempts = {j['id']:_attempt(j,pmap[j['pipeline_id']],tmap.get(j['id']),project)
                    for j in snapshot['jobs'] if j['pipeline_id'] in pmap}
    if baseline is not None:
        bpmap = {p['id']:p for p in baseline['pipelines']}
        for job in baseline['jobs']:
            if job['id'] not in all_attempts and job['pipeline_id'] in bpmap:
                all_attempts[job['id']] = _attempt(job,bpmap[job['pipeline_id']],None,project)
    retained = [all_attempts[i] for i in snapshot['retained_job_ids']]
    keys = sorted({a['type_id'] for a in retained})
    job_types, windows, used_ids = [], [], set(snapshot['retained_job_ids'])
    for identifier in keys:
        history = sorted([a for a in retained if a['type_id']==identifier],key=lambda a:a['id'],reverse=True)
        if comparison_mode == 'cross_ref':
            history = [a for a in history if a['metadata']['ref'] in selected_refs]
        if not history:
            continue
        latest = history[0]
        stage, name = latest['metadata']['stage'], latest['metadata']['name']
        type_refs = selected_refs if comparison_mode == 'cross_ref' else [latest['metadata']['ref']]
        filtered = [a for a in history if a['metadata']['ref'] in type_refs]
        candidates = [a for a in all_attempts.values() if a['type_id']==identifier and a['id']<latest['id']
                      and a['metadata']['ref'] in type_refs and a['baseline_eligible']]
        if baseline is not None:
            baseline_ids = {j['id'] for j in baseline['jobs']}
            candidates = [a for a in candidates if a['id'] in baseline_ids]
        baselines = sorted(candidates,key=lambda a:a['id'],reverse=True)[:10]
        used_ids.update(a['id'] for a in baselines)
        baseline_metrics = _metrics(baselines)
        prior_metadata = [a for a in all_attempts.values() if a['type_id']==identifier
                          and a['id']<latest['id'] and a['metadata']['ref'] in type_refs]
        if baseline is not None:
            prior_metadata = [a for a in prior_metadata if a['id'] in baseline_ids]
        complete = (len(baselines)==10 or
                    ((baseline or snapshot)['source']['complete_available_history'] and
                     all(a['metadata']['metadata_fresh'] and a['pipeline']['metadata_fresh']
                         for a in prior_metadata)))
        source_jobs = [j for j in snapshot['jobs'] if j['stage']==stage and j['name']==name]
        observed = next((c for c in snapshot['source']['observed_counts'] if c['type_id']==identifier),None)
        typ = {'id': identifier, 'stage': stage, 'name': name,
               'refs': sorted({a['metadata']['ref'] for a in history}),
               'purpose': _purpose(catalog,snapshot,stage,name), 'latest_attempt_id': latest['id'],
               'retained_attempt_ids': [a['id'] for a in history],
               'baseline': {'attempt_ids': [a['id'] for a in baselines], 'maximum': 10,
                            'complete': complete, 'metrics': baseline_metrics,
                            'deltas': {k:_delta(latest['timing'][k]['value_seconds'],baseline_metrics[k],comparison_mode) for k in METRICS}},
               'overview': {'status_counts': dict(sorted(Counter(j['status'] for j in source_jobs).items())),
                            'available_count': observed['available_count'] if observed else len(source_jobs),
                            'count_kind': observed['count_kind'] if observed else 'lower_bound',
                            'retained_count': len(history), 'fresh_count': sum(a['metadata']['metadata_fresh'] for a in history),
                            'trace_count': sum(a['trace'] is not None and a['trace']['state'] in {'available','partial','empty'} for a in history)},
               'window_ids': []}
        specifications = [(32,0,filtered[:32])]
        if len(filtered)>32:
            specifications.append((32,1,filtered[32:64]))
        specifications.append((64,0,filtered[:64]))
        type_windows = []
        for size,page,members in specifications:
            date_from,date_to = _bounds(members)
            window_id = 'window-'+digest([identifier,comparison_mode,type_refs,size,page,members[0]['id'] if members else None])[:24]
            descriptive = [a for a in members if a['metadata']['status']=='success']
            inferential = [a for a in members if a['baseline_eligible']]
            stacks = [sum(a['timing'][k]['value_seconds'] or 0 for k in ('queue','execution')) for a in members]
            window = {'id': window_id, 'type_id': identifier, 'comparison_mode': comparison_mode,
                      'refs': type_refs[:], 'size': size, 'page': page,
                      'anchor_attempt_id': members[0]['id'] if members else None,
                      'attempt_ids': [a['id'] for a in members], 'from': date_from, 'to': date_to,
                      'older_window_id': None, 'newer_window_id': None,'has_older': False,'has_newer': False,
                      'display_unit': 'minutes' if max(stacks,default=0)>300 else 'seconds',
                      'descriptive': {'attempt_ids':[a['id'] for a in descriptive], 'metrics':_metrics(descriptive)},
                      'inferential': {'attempt_ids':[a['id'] for a in inferential], 'metrics':_metrics(inferential)}}
            window['findings'] = _findings(window,members,members[0] if members else latest,guide)
            type_windows.append(window)
        if len(type_windows)==3:
            type_windows[0].update(older_window_id=type_windows[1]['id'],has_older=True)
            type_windows[1].update(newer_window_id=type_windows[0]['id'],has_newer=True)
        typ['window_ids'] = [w['id'] for w in type_windows]
        job_types.append(typ)
        windows.extend(type_windows)
    attempts = sorted([a for i,a in all_attempts.items() if i in used_ids],key=lambda a:a['id'],reverse=True)
    retained_ids = set(snapshot['retained_job_ids'])
    for attempt in attempts:
        if attempt['id'] not in retained_ids:
            attempt['trace'] = None
    growth = [t for t in job_types if t['baseline']['metrics']['total']['known']>=3
              and t['baseline']['deltas']['total']['delta_seconds'] is not None
              and t['baseline']['deltas']['total']['delta_seconds']>0]
    if growth:
        selected = min(growth,key=lambda t:(-t['baseline']['deltas']['total']['delta_seconds'],t['id']))
        reason = 'largest_positive_total_growth'
    else:
        known = [t for t in job_types if t['baseline']['deltas']['total']['current_seconds'] is not None]
        selected = min(known,key=lambda t:(-t['baseline']['deltas']['total']['current_seconds'],t['id'])) if known else (job_types[0] if job_types else None)
        reason = 'longest_known_total' if known else 'insufficient_data'
    policies = {'group_key':'host+project+stage+name','comparison_mode':comparison_mode,'refs':selected_refs,
                'baseline_maximum':10,'highlight_minimum':3,
                'queue_spike':{'absolute_seconds':30,'relative_multiplier':2,'minimum_known':3},
                'timing_evidence_policy':'reported-duration-with-inferred-positions-allowed',
                'display_threshold_seconds':300,'aggregation':'per-run-interval-union-then-median','trace_parser':PARSER_VERSION}
    provenance = {'snapshot_sha256':digest(snapshot),'baseline_sha256':digest(baseline) if baseline is not None else None,
                  'catalog_sha256':digest(catalog) if catalog is not None else None,
                  'guidance_sha256':digest(guidance) if guidance is not None else None,'source_configuration':[]}
    metadata_times = [a['metadata']['metadata_checked_at'] for a in attempts if a['metadata']['metadata_checked_at']]
    metadata_times.extend(a['pipeline']['metadata_checked_at'] for a in attempts if a['pipeline']['metadata_checked_at'])
    trace_times = [a['trace']['analyzed_at'] for a in attempts if a['trace'] is not None and a['trace']['analyzed_at']]
    report = {'schema_version':VERSION,'calculation_version':VERSION,'trace_parser_version':PARSER_VERSION,'skill_version':SKILL_VERSION,
              'kind':'gitlab_job_performance_report','report_id':digest({'provenance':provenance,'policies':policies,
                     'calculation_version':VERSION,'trace_parser_version':PARSER_VERSION}),
              'generated_at':generated_at or now(),'collected_at':snapshot['collected_at'],
              'metadata_analyzed_at':max(metadata_times,key=timestamp) if metadata_times else None,
              'trace_analyzed_at':max(trace_times,key=timestamp) if trace_times else None,
              'timezone':snapshot['timezone'],'language':language,'project':deepcopy(project),
              'provenance':provenance,'policies':policies,
              'coverage':{'source':deepcopy(snapshot['source']),
                          'baseline_source':deepcopy(baseline['source']) if baseline is not None else None},
              'source':deepcopy(snapshot),
              'baseline_source':deepcopy(baseline),'attempts':attempts,'job_types':job_types,'windows':windows,
              'selection':{'job_type_id':selected['id'] if selected else None,'reason_code':reason}}
    validate(report,'report')
    return report
