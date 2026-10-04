"""Observed per-run interval costs; representative evidence is never a cost."""
from collections import defaultdict
import math
from history import executed, metric

GUIDANCE = {
    'export_unpack':'https://docs.docker.com/build/exporters/',
    'context_copy':'https://docs.docker.com/build/cache/optimize/',
    'base_image':'https://docs.docker.com/build/cache/',
    'dependencies':'https://docs.docker.com/build/cache/optimize/',
    'builder_startup':'https://docs.docker.com/build/builders/',
    'runner_prepare':'https://docs.gitlab.com/runner/configuration/advanced-configuration/',
    'runner_checkout':'https://docs.gitlab.com/ci/runners/configure_runners/#git-strategy',
    'runner_artifacts':'https://docs.gitlab.com/ci/jobs/job_artifacts/',
    'runner_cleanup':'https://docs.gitlab.com/runner/executors/',
    'queue':'https://docs.gitlab.com/ci/runners/configure_runners/',
}


def union_seconds(intervals):
    merged=[]
    for start,end in sorted((start,end) for start,end in intervals if start is not None and end is not None and end>=start):
        if merged and start<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:
            merged.append((start,end))
    return math.fsum(end-start for start,end in merged) if merged else None


def rank(jobs, details):
    successful=[j for j in jobs if j['status']=='success' and executed(j)]
    dmap={d['job_id']:d for d in details}
    observations=defaultdict(list)
    partial=defaultdict(int)
    for job in successful:
        partial_categories=set()
        evidence=defaultdict(list)
        detail=dmap.get(job['id'],{})
        def add(item,build_id=None,phase_id=None,command_id=None):
            category=item.get('category')
            if category not in GUIDANCE or item.get('cached'):
                return
            if not item.get('complete') or item.get('duration_seconds') is None or item.get('start_seconds') is None or item.get('end_seconds') is None:
                partial_categories.add(category)
                return
            evidence[category].append((item,{'job_id':job['id'],'build_id':build_id,
                                            'operation_id':item['id'] if build_id else None,
                                            'phase_id':phase_id,'command_id':command_id,
                                            'duration_seconds':item['duration_seconds']}))
        for build in detail.get('builds',[]):
            for op in build['operations']:
                # Substeps are explanatory and not additive measurements.
                add(op,build_id=build['id'])
        for phase in detail.get('phases',[]):
            add(phase,phase_id=phase['id'])
        for command in detail.get('commands',[]):
            add(command,command_id=command['id'])
        for category in partial_categories:
            partial[category]+=1
        wait=job.get('queued_seconds')
        if wait is not None:
            item={'id':'queue','duration_seconds':wait,'start_seconds':0,'end_seconds':wait}
            evidence['queue'].append((item,{'job_id':job['id'],'build_id':None,'operation_id':None,
                                           'phase_id':None,'command_id':None,'duration_seconds':wait}))
        for category,items in evidence.items():
            cost=union_seconds([(item['start_seconds'],item['end_seconds']) for item,_ in items])
            if cost is not None:
                # Evidence selection is independent of the measured union cost.
                representative=sorted(items,key=lambda pair:(-pair[0]['duration_seconds'],pair[0]['id']))[0][1]
                observations[category].append((cost,representative))
    result=[]
    for category,values in observations.items():
        median=metric([v[0] for v in values])['p50_seconds']
        representative=sorted(values,key=lambda v:(abs(v[0]-median),v[1]['job_id'],str(v[1]['operation_id'] or v[1]['phase_id'] or v[1]['command_id'] or 'queue')))[0][1]
        result.append({'category':category,'median_cost_seconds':median,'known':len(values),
                       'missing':len(successful)-len(values),'partial':partial[category],
                       'guidance_url':GUIDANCE[category],'direction':category,'evidence':representative})
    return sorted(result,key=lambda p:(-p['median_cost_seconds'],p['category']))[:3]
