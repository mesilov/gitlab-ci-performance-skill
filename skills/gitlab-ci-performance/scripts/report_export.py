"""Deterministic compact selections from a saved canonical report."""
from copy import deepcopy
from report_contract import digest, validate


def export_report(report, *, scope=None, job_type=None, window_id=None, attempt_ids=None):
    validate(report, 'report')
    if attempt_ids is not None:
        if scope not in {None,'attempts'} or job_type is not None or window_id is not None:
            raise ValueError('Attempt selectors cannot be mixed with overview/window selectors')
        if not attempt_ids:
            raise ValueError('Select at least one attempt ID')
        kind = 'attempts'
    elif job_type is not None or window_id is not None:
        if scope not in {None,'window'}:
            raise ValueError('Window selectors cannot be mixed with another scope')
        kind = 'window'
    else:
        kind = scope or 'overview'
        if kind != 'overview':
            raise ValueError('Select a job type/window or attempt IDs for that scope')
    amap = {a['id']:a for a in report['attempts']}
    tmap = {t['id']:t for t in report['job_types']}
    wmap = {w['id']:w for w in report['windows']}
    if job_type is not None and job_type not in tmap:
        raise ValueError('Unknown job type ID; inspect canonical job_types')
    if window_id is not None and window_id not in wmap:
        raise ValueError('Unknown window ID; inspect canonical windows')
    if kind == 'window':
        if window_id is None:
            window_id = tmap[job_type]['window_ids'][0]
        window = wmap[window_id]
        if job_type is not None and window['type_id'] != job_type:
            raise ValueError('Window belongs to another job type')
        job_type = window['type_id']
        types = [tmap[job_type]]
        windows = [window]
        ids = set(window['attempt_ids']) | set(types[0]['baseline']['attempt_ids'])
        ids.add(types[0]['latest_attempt_id'])
    elif kind == 'attempts':
        ids = set(attempt_ids)
        unknown = ids-set(amap)
        if unknown:
            raise ValueError('Unknown attempt ID; inspect canonical attempts')
        types = [t for t in report['job_types'] if t['id'] in {amap[i]['type_id'] for i in ids}]
        windows = []
    else:
        types = report['job_types']
        windows = report['windows']
        ids = set(amap)
    attempts = [deepcopy(a) for a in report['attempts'] if a['id'] in ids]
    external = []
    if kind == 'overview':
        for attempt in attempts:
            if attempt['trace'] is not None:
                external.append({'collection':'traces','id':str(attempt['id']),'report_id':report['report_id']})
                attempt['trace'] = None
    # Navigation and type-level pointers deliberately remain canonical. Declare
    # every target omitted by the selected closure rather than silently dangling.
    present_attempts = {a['id'] for a in attempts}
    present_windows = {w['id'] for w in windows}
    present_types = {t['id'] for t in types}
    referenced_attempts = set()
    referenced_windows = set()
    for typ in types:
        referenced_attempts.update(typ['retained_attempt_ids'])
        referenced_attempts.update(typ['baseline']['attempt_ids'])
        referenced_attempts.add(typ['latest_attempt_id'])
        referenced_windows.update(typ['window_ids'])
    for window in windows:
        referenced_attempts.update(window['attempt_ids'])
        referenced_windows.update(i for i in (window['older_window_id'],window['newer_window_id']) if i)
    for collection, omitted in [('attempts',referenced_attempts-present_attempts),
                                ('windows',referenced_windows-present_windows),
                                ('job_types',{a['type_id'] for a in attempts}-present_types)]:
        external.extend({'collection':collection,'id':str(identifier),'report_id':report['report_id']}
                        for identifier in sorted(omitted,key=str))
    envelope = {k:deepcopy(v) for k,v in report.items()
                if k not in {'source','baseline_source','attempts','job_types','windows'}}
    if envelope['selection']['job_type_id'] and envelope['selection']['job_type_id'] not in present_types:
        external.append({'collection':'job_types','id':envelope['selection']['job_type_id'],'report_id':report['report_id']})
    result = {'schema_version':report['schema_version'],'kind':'gitlab_job_performance_compact',
              'canonical_report_id':report['report_id'],'canonical_report_sha256':digest(report),
              'envelope':envelope,
              'scope':{'kind':kind,'job_type_id':job_type,'window_id':window_id,
                       'attempt_ids':sorted(ids,reverse=True) if kind == 'attempts' else []},
              'job_types':deepcopy(types),'windows':deepcopy(windows),'attempts':attempts,
              'external_references':sorted(external,key=lambda ref:(ref['collection'],ref['id']))}
    validate(result,'compact')
    return result
