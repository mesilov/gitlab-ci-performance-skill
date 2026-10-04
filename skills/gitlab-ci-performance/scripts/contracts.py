"""Local v2 schema and cross-record checks without network resolution."""
from collections import Counter
from pathlib import Path
import json
import math
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]


def unique(items,key,what):
    ids=[item[key] for item in items]
    if len(ids)!=len(set(ids)):
        raise ValueError(f'Duplicate {what}')
    return set(ids)


def evidence_items(detail):
    result=list(detail['phases'])+list(detail['commands'])
    for build in detail['builds']:
        result+=build['operations']
    def visit(items):
        for item in items:
            yield item
            yield from visit(item['substeps'])
    return list(visit(result))


def validate_v2(value,kind):
    from jsonschema import Draft202012Validator,FormatChecker
    if kind not in {'metadata','timings','report'} or value.get('schema_version')!='2.0.0':
        raise ValueError('Unsupported artifact version; use a compatible skill or re-analyze into new outputs')
    schema=json.loads((ROOT/'schemas'/f'{kind}-v2.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    errors=list(Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(value))
    if errors:
        error=errors[0]
        raise ValueError(f"JSON Schema: {'.'.join(map(str,error.path)) or 'root'}: {error.validator}")
    def finite(data):
        if isinstance(data,float) and not math.isfinite(data):raise ValueError('Non-finite timing')
        if isinstance(data,dict):
            for v in data.values():finite(v)
        elif isinstance(data,list):
            for v in data:finite(v)
    finite(value);ZoneInfo(value['timezone'])
    if kind=='metadata':
        ids=unique(value['jobs'],'job_id','metadata job ID');unique(value['types'],'id','type ID')
        retained=[];jmap={r['job_id']:r['job'] for r in value['jobs']}
        for r in value['jobs']:
            if r['job_id']!=r['job']['id']:raise ValueError('Metadata job identity mismatch')
        for t in value['types']:
            if t['retained_ids']!=sorted(t['retained_ids'],reverse=True) or len(t['retained_ids'])>t['source_count']:
                raise ValueError('Invalid retained/source coverage')
            for i in t['retained_ids']:
                if i not in jmap or (jmap[i]['stage'],jmap[i]['name'])!=(t['stage'],t['name']):
                    raise ValueError('Retained type membership mismatch')
            retained+=t['retained_ids']
        if len(retained)!=len(set(retained)) or set(retained)!=ids:raise ValueError('Retained metadata coverage mismatch')
        c=value['coverage']
        if c['retained_attempts']!=len(ids) or c['metadata_requests']!=len(ids) or c['trace_requests']>len(ids):
            raise ValueError('Bounded collection request count mismatch')
        if c['metadata_fresh']!=sum(r['metadata_status']=='fresh' for r in value['jobs']):raise ValueError('Fresh metadata coverage mismatch')
        if c['trace_status_counts']!=dict(Counter(r['trace_status'] for r in value['jobs'])):raise ValueError('Trace coverage mismatch')
        return
    details=value['details'];detail_ids=unique(details,'job_id','detail job ID')
    for d in details:
        if d['processed_bytes']>d['trace_bytes'] or d['timestamp_lines']>d['trace_lines']:raise ValueError('Trace processing coverage mismatch')
        unique(d['builds'],'id','build ID');unique(d['phases'],'id','phase ID');unique(d['commands'],'id','command ID')
        for b in d['builds']:unique(b['operations'],'id','operation ID')
        for item in evidence_items(d):
            if item['last_line']<item['first_line'] or item['last_line']>d['trace_lines']:raise ValueError('Invalid evidence source line range')
            if item['start_seconds'] is not None and item['end_seconds'] is not None and item['end_seconds']<item['start_seconds']:raise ValueError('Invalid evidence interval')
            if item['cached'] and item['duration_seconds'] is not None:raise ValueError('Cached operations must not have measured runtime')
    if kind=='timings':return
    from history import default_selection,windows,executed,total,metric
    job_ids=unique(value['jobs'],'id','job ID');unique(value['pipelines'],'id','pipeline ID')
    pmap={p['id']:p for p in value['pipelines']};jmap={j['id']:j for j in value['jobs']}
    for j in value['jobs']:
        if j['pipeline_id'] not in pmap or pmap[j['pipeline_id']]['ref']!=j['ref']:raise ValueError('Job/pipeline relation mismatch')
        if j['executed']!=executed(j) or j['total_seconds']!=total(j) or j['execution_seconds']!=(j['duration_seconds'] if executed(j) else None):raise ValueError('Job timing semantics mismatch')
    if job_ids!=detail_ids:raise ValueError('Every retained attempt requires detail availability')
    unique(value['types'],'id','type ID');retained=[]
    for t in value['types']:
        if t['retained_ids']!=sorted(t['retained_ids'],reverse=True) or t['source_count']<len(t['retained_ids']):raise ValueError('Invalid retained/source coverage')
        group=[]
        for i in t['retained_ids']:
            if i not in jmap or (jmap[i]['stage'],jmap[i]['name'])!=(t['stage'],t['name']):raise ValueError('Retained type membership mismatch')
            group.append(jmap[i])
        retained+=t['retained_ids']
        if t['latest_attempt_id']!=max(t['retained_ids'],default=None) or t['status_counts']!=dict(Counter(j['status'] for j in group)):raise ValueError('Type latest/outcome mismatch')
        if t['windows']!=windows(group,details):raise ValueError('Window statistics, priorities or evidence mismatch')
        for c,expected_scope in [(t['comparison'],'exploratory_cross_ref'),(t['same_ref_comparison'],'same_ref_history')]:
            if c['scope']!=expected_scope:raise ValueError('Comparison scope mismatch')
            if c['known']!=len(c['sample_ids']) or any(i>=t['latest_attempt_id'] for i in c['sample_ids']):raise ValueError('Baseline sample eligibility mismatch')
            latest=jmap[t['latest_attempt_id']] if t['latest_attempt_id'] is not None else None
            if c['sample_ids']!=[s['id'] for s in c['samples']] or c['latest_seconds']!=(total(latest) if latest else None):
                raise ValueError('Comparison latest/sample identity mismatch')
            unique(c['samples'],'pipeline_id','independent baseline pipeline')
            for s in c['samples']:
                if s['pipeline_id']==latest['pipeline_id'] or s['total_seconds']!=s['execution_seconds']+s['queue_seconds']:
                    raise ValueError('Baseline observation semantics mismatch')
                if c['scope']=='same_ref_history' and s['ref']!=latest['ref']:
                    raise ValueError('Same-ref baseline membership mismatch')
                if s['id'] in jmap:
                    j=jmap[s['id']]
                    if (j['stage'],j['name'])!=(t['stage'],t['name']) or s!={'id':j['id'],'pipeline_id':j['pipeline_id'],'ref':j['ref'],'status':j['status'],'pipeline_status':pmap[j['pipeline_id']]['status'],'execution_seconds':j['duration_seconds'],'queue_seconds':j['queued_seconds'],'total_seconds':total(j)} or j['status']!='success' or pmap[j['pipeline_id']]['status']!='success':
                        raise ValueError('Baseline observation is not eligible')
            if c['baseline_seconds']!=metric([s['total_seconds'] for s in c['samples']])['p50_seconds']:
                raise ValueError('Baseline median mismatch')
            delta=c['latest_seconds']-c['baseline_seconds'] if c['latest_seconds'] is not None and c['baseline_seconds'] is not None else None
            percent=delta/c['baseline_seconds']*100 if delta is not None and c['baseline_seconds']>0 else None
            if c['delta_seconds']!=delta or c['delta_percent']!=percent or c['eligible_increase']!=(c['known']>=3 and delta is not None and delta>0):raise ValueError('Comparison calculation mismatch')
    if set(retained)!=job_ids or len(retained)!=len(set(retained)):raise ValueError('Retained attempt coverage mismatch')
    if (value['default_type_id'],value['attention_type_id'])!=default_selection(value['types']):raise ValueError('Default selection mismatch')
    if value['coverage']['retained_attempts']<len(job_ids) or value['coverage']['detail_attempts']!=len(detail_ids):raise ValueError('Report coverage mismatch')
