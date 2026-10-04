"""Attempt retention and explicitly exploratory history calculations."""
from collections import Counter
import math

NOT_RUN = {'created', 'pending', 'manual', 'scheduled', 'skipped', 'waiting_for_resource'}


def executed(job):
    return bool(job.get('started_at')) and job['status'] not in NOT_RUN


def total(job):
    duration, queue = job.get('duration_seconds'), job.get('queued_seconds')
    return duration + queue if executed(job) and duration is not None and queue is not None else None


def metric(values):
    known = sorted(v for v in values if v is not None)
    def percentile(p):
        if not known:
            return None
        index = (len(known)-1)*p
        lo, hi = math.floor(index), math.ceil(index)
        return known[lo] + (known[hi]-known[lo])*(index-lo)
    return {'known':len(known), 'missing':len(values)-len(known),
            'sum_seconds':math.fsum(known) if known else None, 'p50_seconds':percentile(.5),
            'p95_seconds':percentile(.95), 'max_seconds':max(known) if known else None}


def retain_jobs(jobs, job_names=None, stages=None):
    keys = sorted({(j['stage'],j['name']) for j in jobs
                   if (not job_names or j['name'] in job_names) and (not stages or j['stage'] in stages)})
    return [{'id':f't{i}', 'stage':stage, 'name':name,
             'source_count':sum((j['stage'],j['name'])==(stage,name) for j in jobs),
             'retained_ids':sorted((j['id'] for j in jobs if (j['stage'],j['name'])==(stage,name)),reverse=True)[:64]}
            for i,(stage,name) in enumerate(keys,1)]


def comparison(jobs, pipelines, latest, scope='exploratory_cross_ref', limit=10):
    statuses = {p['id']:p['status'] for p in pipelines}
    candidates = sorted((j for j in jobs if j['id']<latest['id'] and
                         j['pipeline_id']!=latest['pipeline_id'] and
                         (j['stage'],j['name'])==(latest['stage'],latest['name']) and
                         (scope!='same_ref_history' or j['ref']==latest['ref']) and
                         j['status']=='success' and statuses.get(j['pipeline_id'])=='success'),
                        key=lambda j:j['id'],reverse=True)
    seen, selected, missing = set(), [], 0
    for j in candidates:
        if j['pipeline_id'] in seen:
            continue
        # The latest successful attempt is the observation for this pipeline.
        # Missing totals cannot be replaced by an older rerun's known total.
        seen.add(j['pipeline_id'])
        if total(j) is None:
            missing += 1
            continue
        selected.append(j)
        if len(selected)==limit:
            break
    baseline = metric([total(j) for j in selected])['p50_seconds']
    current = total(latest)
    delta = current-baseline if current is not None and baseline is not None else None
    samples=[{'id':j['id'],'pipeline_id':j['pipeline_id'],'ref':j['ref'],'status':'success','pipeline_status':'success',
              'execution_seconds':j['duration_seconds'],'queue_seconds':j['queued_seconds'],'total_seconds':total(j)} for j in selected]
    return {'scope':scope, 'sample_ids':[j['id'] for j in selected], 'samples':samples, 'known':len(selected),
            'missing':missing, 'latest_seconds':current, 'baseline_seconds':baseline,
            'delta_seconds':delta, 'delta_percent':delta/baseline*100 if delta is not None and baseline>0 else None,
            'eligible_increase':len(selected)>=3 and delta is not None and delta>0}


def default_selection(types):
    increased = [t for t in types if t['comparison']['eligible_increase']]
    if increased:
        selected = sorted(increased,key=lambda t:(-t['comparison']['delta_seconds'],t['stage'],t['name']))[0]['id']
        return selected, selected
    known = [t for t in types if t['comparison']['latest_seconds'] is not None]
    selected = sorted(known,key=lambda t:(-t['comparison']['latest_seconds'],t['stage'],t['name']))[0] if known else (types[0] if types else None)
    return selected['id'] if selected else None, None


def windows(jobs, details):
    from priorities import rank
    ordered = sorted(jobs,key=lambda j:j['id'],reverse=True)[:64]
    result=[]
    for size in (32,64):
        for offset in range(0,max(1,len(ordered)),size):
            current=ordered[offset:offset+size]
            successful=[j for j in current if j['status']=='success' and executed(j)]
            totals=[total(j) for j in current if total(j) is not None]
            dates=[j['created_at'] for j in current]
            # ISO dates may contain different UTC offsets: sort actual timestamps.
            from datetime import datetime
            datekey=lambda value:datetime.fromisoformat(value.replace('Z','+00:00'))
            previous_jobs=[j for j in current[1:] if j['status']=='success' and executed(j) and j.get('queued_seconds') is not None]
            previous=[j['queued_seconds'] for j in previous_jobs]
            typical=metric(previous)['p50_seconds']
            threshold=max(30,3*typical) if typical is not None and len(previous)>=3 else None
            latest_wait=current[0].get('queued_seconds') if current and executed(current[0]) else None
            result.append({'size':size,'offset':offset,'count':len(current),'attempt_ids':[j['id'] for j in current],
                           'from':min(dates,key=datekey) if dates else None,'to':max(dates,key=datekey) if dates else None,
                           'unit':'minutes' if totals and max(totals)>300 else 'seconds', 'successful_n':len(successful),
                           'successful_total_ids':[j['id'] for j in successful if total(j) is not None],
                           'execution':metric([j.get('duration_seconds') for j in successful]),
                           'queue':metric([j.get('queued_seconds') for j in successful]),
                           'total':metric([total(j) for j in successful]),
                           'queue_spike':{'detected':threshold is not None and latest_wait is not None and latest_wait>threshold,
                                          'known':len(previous),'baseline_seconds':typical,'latest_seconds':latest_wait,
                                          'sample_ids':[j['id'] for j in previous_jobs],
                                          'threshold_seconds':threshold,'rule':'wait>max(30,3*median);previous-success-N>=3'},
                           'priorities':rank(current,details)})
    return result
