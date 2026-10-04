"""Versioned report assembly from saved sources, without network access."""
from collections import Counter
import copy
import hashlib
import json
from history import retain_jobs, comparison, default_selection, windows, executed, total

VERSION='2.0.1'
PARSER_VERSION='2.0.0'


def digest(value):
    return hashlib.sha256((json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()).hexdigest()


def absent_detail(job_id,analyzed_at,status='unavailable'):
    return {'job_id':job_id,'trace_status':status,'trace_sha256':None,'trace_bytes':0,'processed_bytes':0,
            'trace_lines':0,'timestamp_lines':0,'analyzed_at':analyzed_at,'parser_version':PARSER_VERSION,
            'phases':[],'builds':[],'commands':[],'limitations':['details_not_collected']}


def build(snapshot, metadata=None, timings=None, legacy=None, catalog=None, job_names=None, stages=None):
    if (metadata is None)!=(timings is None):
        raise ValueError('Supply both metadata and timings artifacts')
    if metadata:
        if metadata['project']!=snapshot['project'] or timings['project']!=snapshot['project'] or metadata['timezone']!=snapshot['timezone'] or timings['timezone']!=snapshot['timezone']:
            raise ValueError('Detail project/timezone does not match source')
        if metadata['source']['snapshot_sha256']!=digest(snapshot):
            raise ValueError('Details do not belong to this source snapshot')
        if timings['source']['metadata_sha256']!=digest(metadata) or timings['source']['snapshot_sha256']!=digest(snapshot):
            raise ValueError('Timing inputs do not match metadata/source hashes')
        if any(d.get('parser_version')!=PARSER_VERSION for d in timings['details']):
            raise ValueError('Unsupported parser version; re-analyze into a new output directory')
        all_ids={r['job_id'] for r in metadata['jobs']}
        if {d['job_id'] for d in timings['details']}!=all_ids or len(timings['details'])!=len(all_ids):
            raise ValueError('Full timing availability scope must match collected metadata')
        original={j['id']:j for j in snapshot['jobs']}
        for r in metadata['jobs']:
            if r['job_id'] not in original or any(r['job'][k]!=original[r['job_id']][k] for k in ['id','pipeline_id','stage','name','ref']):
                raise ValueError('Detail metadata identity does not match immutable source')
        types=copy.deepcopy(metadata['types'])
        if job_names or stages:
            types=[t for t in types if (not job_names or t['name'] in job_names) and (not stages or t['stage'] in stages)]
    else:
        types=retain_jobs(snapshot['jobs'],job_names,stages)
    ids={i for t in types for i in t['retained_ids']}
    source_map={j['id']:j for j in snapshot['jobs']}
    if metadata:
        retained={r['job_id']:r['job'] for r in metadata['jobs']}
        if not ids<=set(retained) or not ids<=set(source_map):
            raise ValueError('Retained attempt metadata is missing or outside source')
    else:
        retained=source_map
    generated_at=timings['analyzed_at'] if timings else snapshot['collected_at']
    details=[copy.deepcopy(d) for d in timings['details'] if d['job_id'] in ids] if timings else [absent_detail(i,generated_at) for i in sorted(ids)]
    if {d['job_id'] for d in details}!=ids:
        raise ValueError('Each retained attempt needs a detail availability record')
    descriptions=(catalog or {}).get('jobs',{}) if (catalog or {}).get('project')==snapshot['project']['path'] else {}
    pmap={p['id']:p for p in snapshot['pipelines']}
    jobs=[]
    records={r['job_id']:r for r in metadata['jobs']} if metadata else {}
    for i in sorted(ids,reverse=True):
        j=copy.deepcopy(retained[i])
        j.setdefault('commit_sha',pmap[j['pipeline_id']]['sha'])
        if j['commit_sha'] is None:
            j['commit_sha']=pmap[j['pipeline_id']]['sha']
        j.setdefault('erased_at',None);j.setdefault('runner_version',None)
        record=records.get(i,{})
        j.update(metadata_status=record.get('metadata_status','source_snapshot'),
                 metadata_collected_at=record.get('metadata_collected_at',snapshot['collected_at']),
                 trace_source=record.get('trace_source','none'),trace_collected_at=record.get('trace_collected_at'),
                 metadata_error=record.get('metadata_error'))
        j.update(executed=executed(j),execution_seconds=j['duration_seconds'] if executed(j) else None,total_seconds=total(j))
        jobs.append(j)
    # Fresh retained projections update exploratory observations; older baseline
    # values remain explicitly source-snapshot observations without trace GETs.
    analysis_jobs=[retained.get(j['id'],j) for j in snapshot['jobs']]
    for t in types:
        current=[j for j in jobs if j['id'] in t['retained_ids']]
        latest=max(current,key=lambda j:j['id']) if current else None
        t['purpose']=copy.deepcopy(descriptions.get(t['name'],{'description':'','source_url':None,'verified_at':None}))
        t['latest_attempt_id']=latest['id'] if latest else None
        t['status_counts']=dict(Counter(j['status'] for j in current))
        t['comparison']=comparison(analysis_jobs,snapshot['pipelines'],latest) if latest else {
            'scope':'exploratory_cross_ref','sample_ids':[],'samples':[],'known':0,'missing':0,'latest_seconds':None,
            'baseline_seconds':None,'delta_seconds':None,'delta_percent':None,'eligible_increase':False}
        t['same_ref_comparison']=comparison(analysis_jobs,snapshot['pipelines'],latest,'same_ref_history') if latest else t['comparison'].copy()
        t['windows']=windows(current,details)
    # Preserve compact source projections for every exported baseline observation,
    # independently of the 64-attempt history/trace scope.
    baseline_ids={i for t in types for key in ['comparison','same_ref_comparison'] for i in t[key]['sample_ids']}
    analysis_map={j['id']:j for j in analysis_jobs}
    baseline_jobs=[]
    for i in sorted(baseline_ids,reverse=True):
        j=analysis_map[i]
        baseline_jobs.append({**{k:j[k] for k in ['id','pipeline_id','name','stage','ref','status','started_at','duration_seconds','queued_seconds']},
                              'pipeline_status':pmap[j['pipeline_id']]['status'],
                              'metadata_status':records.get(i,{}).get('metadata_status','source_snapshot')})
    selected,attention=default_selection(types)
    coverage=copy.deepcopy(metadata['coverage']) if metadata else {
        'retained_attempts':len(ids),'metadata_requests':0,'metadata_fresh':0,'trace_requests':0,
        'trace_status_counts':dict(Counter(d['trace_status'] for d in details)),
        'workers':0,'max_trace_bytes':0,'trace_bytes_received':0}
    coverage.update(source_attempts=len(snapshot['jobs']),source_complete_available_history=snapshot['source']['complete_available_history'],
                    displayed_types=len(types),detail_attempts=len(details),
                    metadata_collected_at=metadata['collected_at'] if metadata else None,
                    details_analyzed_at=timings['analyzed_at'] if timings else None)
    return {'schema_version':VERSION,'calculation_version':VERSION,'parser_version':PARSER_VERSION,'kind':'report',
            'generated_at':generated_at,'timezone':snapshot['timezone'],'project':copy.deepcopy(snapshot['project']),
            'inputs':{'snapshot_sha256':digest(snapshot),'metadata_sha256':digest(metadata) if metadata else None,
                      'timings_sha256':digest(timings) if timings else None,
                      'snapshot_collected_at':snapshot['collected_at'],'source_schema_version':snapshot['schema_version'],
                      'baseline_sha256':legacy['inputs']['baseline_sha256'] if legacy else None},
            'method':{'history_limit':64,'windows':[32,64],'default_window':32,'baseline_limit':10,'minimum_baseline':3,
                      'baseline_eligibility':'successful_complete_job_in_successful_pipeline_latest_success_per_pipeline',
                      'history_scope':'exploratory_cross_ref','category_cost':'union_of_recorded_intervals_per_successful_run',
                      'queue_spike_rule':'wait>max(30,3*median);previous-success-N>=3'},
            'snapshot_summary':{'attempts':len(snapshot['jobs']),'pipelines':len(snapshot['pipelines']),
                                'status_counts':dict(Counter(j['status'] for j in snapshot['jobs']))},
            'types':types,'default_type_id':selected,'attention_type_id':attention,'jobs':jobs,
            'pipelines':[copy.deepcopy(pmap[i]) for i in sorted({j['pipeline_id'] for j in jobs},reverse=True)],
            'baseline_jobs':baseline_jobs,'details':details,'same_ref_views':copy.deepcopy(legacy['views']) if legacy else [],'coverage':coverage}
