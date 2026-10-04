"""Local Draft 2020-12 contracts, semantic checks and exclusive artifact writes."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2.0.0'
SKILL_VERSION = (ROOT/'VERSION').read_text(encoding='utf-8').strip()
PARSER_VERSION = '1.0.0'
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
KINDS = {'gitlab_job_performance_source':'jobs','gitlab_job_performance_report':'report',
         'gitlab_job_performance_compact':'compact'}


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Timestamp requires timezone')
    return result


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def type_id(project, stage, name):
    return 'jobtype-'+digest([project['host'],project['id'],stage,name])[:20]


def load(path):
    def reject(value):
        raise ValueError('Non-finite JSON value')
    return json.loads(Path(path).read_text(encoding='utf-8'),parse_constant=reject)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(items, key='id'):
    result = {i[key]:i for i in items}
    require(len(result)==len(items),'Duplicate '+key)
    return result


def safe_url(value, host=None):
    u = urlsplit(value)
    require(u.scheme=='https' and u.netloc and not u.username and not u.password
            and (host is None or u.netloc==host),'Unsafe source URL')
    require(not any(x in u.query.lower() for x in ('token','authorization','password')),'Unsafe source URL query')


def check_dates(item):
    dates = [timestamp(item[k]) for k in ('created_at','started_at','finished_at') if item.get(k)]
    require(dates==sorted(dates),'Reversed metadata timestamps')
    if item.get('metadata_fresh'):
        require(item['metadata_checked_at'] is not None and item['metadata_error'] is None,'Contradictory metadata freshness')


def check_trace(t):
    c=t['coverage'];nodes=unique(t['evidence'])
    require(c['recognized_lines']<=c['total_lines']==t['line_count'],'Contradictory trace line coverage')
    if t['state'] in {'unavailable','erased','permission_denied','not_run'}:
        require(t['bytes_read']==0 and not nodes and t['sha256'] is None and t['prefix_sha256'] is None,
                'Unavailable trace contains evidence')
    elif t['state']=='empty':
        require(t['bytes_read']==0 and t['line_count']==0 and not nodes and
                t['sha256']==hashlib.sha256(b'').hexdigest(),'Contradictory empty trace')
    else:
        require(t['bytes_read']>0,'Nonempty trace state requires source bytes')
        if c['truncated']:
            require(t['sha256'] is None and t['prefix_sha256'] is not None and t['state']=='partial',
                    'Truncated trace requires prefix hash and partial state')
        else:
            require(t['sha256'] is not None and t['prefix_sha256'] is None,'Whole trace hash missing')
    require(not (c['complete'] and (c['truncated'] or t['state'] in {'partial','unavailable','erased','permission_denied','not_run'})),'Partial/unavailable trace marked complete')
    require(t['state']!='available' or c['complete'],'Available trace marked incomplete')
    require(t['state']!='unsupported' or not nodes,'Unsupported trace contains supported evidence')
    require(timestamp(t['fetched_at'])<=timestamp(t['analyzed_at']),'Analysis precedes trace collection')
    allowed={'phase':{'prepare_executor','prepare_script','get_sources','restore_cache','download_artifacts','step_script','after_script','archive_cache','upload_artifacts','cleanup_file_variables','unknown_phase'},'image':{'image_build'},'command':{'script_command'},'operation':{'export_local_unpack','context_application_copy','base_image','dependencies_builder_setup','other_operation'},'part':{'export_local_unpack','context_application_copy','base_image','dependencies_builder_setup','other_operation'}}
    for n in nodes.values():
        require(n['code'] in allowed[n['kind']],'Evidence kind/code mismatch')
        lines=n['lines'];require(1<=lines['start']<=lines['end']<=t['line_count'],'Invalid evidence lines')
        v=n['timing'];start,end,dur=v['start_seconds'],v['end_seconds'],v['duration_seconds']
        require(not n['cached'] or dur is None,'Cached duration must remain unknown')
        if start is not None and end is not None:
            require(end>=start,'Impossible evidence interval')
            if (v['origin'] in {'section','log_interval','inferred'} or (v['origin']=='buildkit_reported' and v['quality']=='inferred')) and dur is not None:
                require(math.isclose(end-start,dur,abs_tol=1e-6),'Duration contradicts interval')
        if v['origin']=='unknown':
            require(dur is None and v['quality']=='unknown','Unknown timing origin has known duration')
        if v['origin']=='buildkit_reported':
            require(n['kind'] in {'operation','part'},'Malformed BuildKit timing origin')
        if v['origin']=='inferred':
            require(v['quality'] in {'inferred','partial'},'Inferred position lacks uncertainty')
        if v['origin']=='section':
            require(n['kind']=='phase' and v['precision_seconds']==1,'Malformed section timing origin')
        if v['origin']=='log_interval':
            require(n['kind']=='command' and v['quality'] in {'inferred','partial'},'Malformed command interval origin')
        parent=n['parent_id'];visited={n['id']}
        if parent is not None:
            require(parent in nodes,'Unresolved evidence parent')
            p=nodes[parent]
            if n['kind']=='part':require(p['kind']=='operation','Part parent must be an operation')
            for k,cmp in [('start_seconds',lambda a,b:a>=b),('end_seconds',lambda a,b:a<=b)]:
                if v[k] is not None and p['timing'][k] is not None:
                    require(cmp(v[k],p['timing'][k]),'Child interval exceeds parent')
        while parent is not None:
            require(parent in nodes and parent not in visited,'Cyclic/unresolved evidence parent')
            visited.add(parent);parent=nodes[parent]['parent_id']


def check_source(s):
    ZoneInfo(s['timezone']);require(timestamp(s['collection_started_at'])<=timestamp(s['collected_at']),'Collection dates reversed')
    host=s['project']['host'];safe_url(s['project']['web_url'],host)
    jobs=unique(s['jobs']);pipes=unique(s['pipelines']);traces=unique(s['traces'],'job_id')
    for p in pipes.values():check_dates(p);safe_url(p['web_url'],host)
    for j in jobs.values():
        require(j['pipeline_id'] in pipes and pipes[j['pipeline_id']]['ref']==j['ref'],'Job/pipeline relation mismatch')
        check_dates(j);safe_url(j['web_url'],host)
    for field in ('retained_job_ids','baseline_job_ids'):
        ids=s[field];require(len(ids)==len(set(ids)) and set(ids)<=jobs.keys(),'Invalid '+field)
        require(ids==sorted(ids,reverse=True),'Attempt IDs must be ordered descending')
    retained=s['retained_job_ids'];baseline=s['baseline_job_ids']
    require(not set(retained)&set(baseline),'Baseline-only membership overlaps history')
    require(set(traces)==set(retained),'Trace availability must cover every retained attempt')
    counts={}
    for jid in retained:
        j=jobs[jid];key=type_id(s['project'],j['stage'],j['name']);counts[key]=counts.get(key,0)+1
    require(all(n<=64 for n in counts.values()),'History exceeds 64 attempts per job type')
    require(len(counts)<=min(16,s['source']['budgets']['max_job_types']),'Analyzed job type budget exceeded')
    bcounts={}
    for jid in baseline:
        j=jobs[jid];key=type_id(s['project'],j['stage'],j['name']);bcounts[key]=bcounts.get(key,0)+1
    require(all(n<=10 for n in bcounts.values()),'Baseline-only metadata exceeds 10 per type')
    info=s['source'];unique(info['observed_counts'],'type_id')
    groups={(j['stage'],j['name']) for j in jobs.values()}
    require(groups=={(c['stage'],c['name']) for c in info['observed_counts']},'Missing source count groups')
    require(not jobs or (info['anchor_max_job_id'] is not None and max(jobs)<=info['anchor_max_job_id']),'Source anchor excludes saved jobs')
    for count in info['observed_counts']:
        require(count['type_id']==type_id(s['project'],count['stage'],count['name']),'Job type identity mismatch')
        actual=sum(j['stage']==count['stage'] and j['name']==count['name'] for j in jobs.values())
        require(count['available_count']==actual,'Source count does not match safe projection')
        require(count['count_kind']==('exact' if info['complete_available_history'] else 'lower_bound'),'Source count completeness mismatch')
    for jid,t in traces.items():
        check_trace(t);j=jobs[jid]
        if t['state']=='erased':require(j['erased_at'] is not None,'Erased state lacks metadata evidence')
        if t['state']=='not_run':require(j['started_at'] is None and j['status'] in {'created','pending','manual','skipped','waiting_for_resource'},'Not-run state contradicts job metadata')
        require(t['bytes_read']<=info['budgets']['trace_bytes'] and t['line_count']<=info['budgets']['trace_lines'],'Trace input budget exceeded')
        require(len(encoded(t))<=128*1024,'Trace summary exceeds 128 KiB; lower evidence budget')


def check_attempt(a, host):
    require(a['id']==a['metadata']['id'] and a['pipeline']['id']==a['metadata']['pipeline_id'],'Attempt identity mismatch')
    check_dates(a['metadata']);check_dates(a['pipeline']);safe_url(a['metadata']['web_url'],host)
    j=a['metadata'];q=j['queued_seconds'];run=j['duration_seconds']
    expected={'queue':q,'execution':run,'total':q+run if q is not None and run is not None else None,
              'lifecycle':(timestamp(j['finished_at'])-timestamp(j['created_at'])).total_seconds() if j['finished_at'] else None}
    pre=(timestamp(j['started_at'])-timestamp(j['created_at'])).total_seconds()-q if j['started_at'] and q is not None else None
    expected['prestart']=pre if pre is None or pre>=0 else None
    origins={'queue':'api_queue','execution':'api_execution','total':'derived_total','lifecycle':'lifecycle','prestart':'prestart'}
    for key,v in expected.items():
        actual=a['timing'][key];require(actual['origin']==origins[key],'Malformed API timing origin')
        require(actual['value_seconds']==v,'Derived timing differs from source projection')
        require(v is not None or not actual['eligible'],'Missing timing marked eligible')
    if a['trace'] is not None:
        require(a['trace']['job_id']==a['id'],'Attempt trace identity mismatch');check_trace(a['trace'])


def check_derived(value, compact=False):
    env=value['envelope'] if compact else value
    ZoneInfo(env['timezone']);host=env['project']['host'];safe_url(env['project']['web_url'],host)
    attempts=unique(value['attempts']);types=unique(value['job_types']);windows=unique(value['windows'])
    external={(r['collection'],r['id']) for r in value.get('external_references',[])}
    def resolves(collection,key,items):
        require(key in items or (collection,str(key)) in external,'Unresolved '+collection+' reference')
    for a in attempts.values():
        check_attempt(a,host)
        require(a['type_id']==type_id(env['project'],a['metadata']['stage'],a['metadata']['name']),'Attempt type mismatch')
    for jt in types.values():
        require(jt['id']==type_id(env['project'],jt['stage'],jt['name']),'Job type mismatch')
        for jid in jt['retained_attempt_ids']+jt['baseline']['attempt_ids']:
            resolves('attempts',jid,attempts)
        if jt['latest_attempt_id'] is not None:resolves('attempts',jt['latest_attempt_id'],attempts)
        for wid in jt['window_ids']:resolves('windows',wid,windows)
        if jt['purpose']['status']=='verified':
            require(jt['purpose']['source_url'] is not None and jt['purpose']['verified_at'] is not None,'Verified purpose requires evidence')
        if jt['purpose']['source_url'] is not None:safe_url(jt['purpose']['source_url'],host)
    for w in windows.values():
        resolves('job_types',w['type_id'],types)
        require(len(w['attempt_ids'])<=w['size'] and len(set(w['attempt_ids']))==len(w['attempt_ids']),'Invalid window membership')
        require(w['attempt_ids']==sorted(w['attempt_ids'],reverse=True),'Window ordering mismatch')
        for jid in w['attempt_ids']+w['descriptive']['attempt_ids']+w['inferential']['attempt_ids']:resolves('attempts',jid,attempts)
        require(set(w['descriptive']['attempt_ids'])<=set(w['attempt_ids']) and set(w['inferential']['attempt_ids'])<=set(w['attempt_ids']),'Cohort exceeds window')
        require(w['findings']['scope']['attempt_ids']==w['attempt_ids'] and w['findings']['scope']['window_id']==w['id'],'Finding scope mismatch')
        for direction in ('older','newer'):
            wid=w[direction+'_window_id'];require(w['has_'+direction]==(wid is not None),'Navigation flag mismatch')
            if wid is not None:resolves('windows',wid,windows)
        stacks=[sum(x for x in (attempts[j]['timing']['queue']['value_seconds'],attempts[j]['timing']['execution']['value_seconds']) if x is not None) for j in w['attempt_ids'] if j in attempts]
        if len(stacks)==len(w['attempt_ids']):require(w['display_unit']==('minutes' if max(stacks,default=0)>300 else 'seconds'),'Display unit contradicts recorded policy')
        for category in w['findings']['categories']:
            for sample in category['samples']:
                resolves('attempts',sample['attempt_id'],attempts)
                require(all(end>=start for start,end in sample['intervals']),'Invalid category interval')
                if sample['attempt_id'] in attempts:
                    t=attempts[sample['attempt_id']]['trace']
                    nodeids={n['id'] for n in t['evidence']} if t else set()
                    for eid in sample['interval_ids']:require(eid in nodeids or (compact and ('traces',str(sample['attempt_id'])) in external),'Unresolved category evidence')
            r=category['representative']
            if r:
                resolves('attempts',r['attempt_id'],attempts);safe_url(r['job_url'],host)
                if r['evidence_id'] and r['attempt_id'] in attempts:
                    t=attempts[r['attempt_id']]['trace'];require((t and any(n['id']==r['evidence_id'] for n in t['evidence'])) or (compact and ('traces',str(r['attempt_id'])) in external),'Unresolved representative evidence')
            for g in category['finding']['guidance']:
                safe_url(g['url']);u=urlsplit(g['url']);require(u.hostname in {'docs.gitlab.com','docs.docker.com','gitlab.com'} or (u.hostname=='github.com' and u.path.startswith('/moby/buildkit/')),'Guidance must use an official source')
                if g['status']=='verified':require(g['verified_at'] is not None,'Verified guidance requires verification date')
    selected=env['selection']['job_type_id']
    if selected is not None:resolves('job_types',selected,types)
    check_measurements(value,env,attempts,types,windows,external,compact)
    if compact:
        require(env['report_id']==value['canonical_report_id'],'Compact canonical identity mismatch')
        require(all(r['report_id']==value['canonical_report_id'] for r in value['external_references']),'External reference targets wrong report')
        require(len(external)==len(value['external_references']),'Duplicate external references')
        scope=value['scope']
        if scope['kind']=='attempts':
            require(set(scope['attempt_ids'])==set(attempts) and len(scope['attempt_ids'])==len(attempts),'Compact attempt scope mismatch')
            require(not windows and scope['job_type_id'] is None and scope['window_id'] is None,'Compact attempt selectors conflict')
            require(set(types)<={a['type_id'] for a in attempts.values()},'Compact contains unrelated job types')
            for a in attempts.values():resolves('job_types',a['type_id'],types)
        elif scope['kind']=='window':
            require(len(windows)==1 and scope['window_id'] in windows,'Compact window scope mismatch')
            w=windows[scope['window_id']];require(set(types)=={w['type_id']} and scope['job_type_id']==w['type_id'],'Compact job/window mismatch')
            jt=types[w['type_id']];require(set(attempts)==set(w['attempt_ids'])|set(jt['baseline']['attempt_ids'])|{jt['latest_attempt_id']},'Compact window attempt closure mismatch')
            require(not scope['attempt_ids'],'Compact window selectors conflict')
        else:
            require(scope['job_type_id'] is None and scope['window_id'] is None and not scope['attempt_ids'],'Overview selectors conflict')
            require(all(a['trace'] is None for a in attempts.values()),'Overview must omit trace details')
    else:
        check_source(value['source']);require(digest(value['source'])==env['provenance']['snapshot_sha256'],'Source hash mismatch')
        require(env['coverage']['source']==value['source']['source'],'Report source coverage mismatch')
        require(env['collected_at']==value['source']['collected_at'],'Collection time was changed during calculation')
        if value['baseline_source'] is not None:
            check_source(value['baseline_source']);require(digest(value['baseline_source'])==env['provenance']['baseline_sha256'],'Baseline hash mismatch')


def check_measurements(value,env,attempts,types,windows,external,compact):
    from report_calculate import _metrics, _metric, _delta, _category_sample, _union
    require(env['report_id']==digest({'provenance':env['provenance'],'policies':env['policies'],
                                    'calculation_version':env['calculation_version'],
                                    'trace_parser_version':env['trace_parser_version']}),'Report ID disagrees with inputs/policies')
    if not compact:
        require(env['project']==value['source']['project'],'Report project differs from source')
        require(timestamp(env['generated_at'])>=timestamp(env['collected_at']),'Generation precedes original collection')
        current={j['id']:j for j in value['source']['jobs']}
        original=dict(current)
        old=value['baseline_source']
        if old:
            for j in old['jobs']:original.setdefault(j['id'],j)
        for aid,a in attempts.items():
            require(aid in original and a['metadata']==original[aid],'Attempt metadata differs from immutable source')
            projection=value['source'] if aid in current else old
            pmap={p['id']:p for p in projection['pipelines']}
            require(a['pipeline']==pmap[a['metadata']['pipeline_id']],'Attempt pipeline differs from immutable source')
            traces={t['job_id']:t for t in value['source']['traces']}
            require(a['trace']==traces.get(aid),'Attempt trace differs from immutable source')
        require(set(value['source']['retained_job_ids'])<=set(attempts),'Retained attempt missing from report')
        require(len(types)<=16,'Report exceeds 16 job types')
    for a in attempts.values():
        j,p=a['metadata'],a['pipeline']
        eligible=j['status']=='success' and j['metadata_fresh'] and p['status']=='success' and p['metadata_fresh'] and j['ref']==p['ref']
        require(a['baseline_eligible']==eligible,'Baseline eligibility differs from metadata')
        for t in a['timing'].values():require(t['eligible']==bool(eligible and t['quality']=='known'),'Timing eligibility contradicts cohort')
    for jt in types.values():
        bs=jt['baseline']['attempt_ids'];known=[attempts[i] for i in bs if i in attempts]
        if len(known)==len(bs):
            require(all(a['baseline_eligible'] and a['type_id']==jt['id'] and a['id']<jt['latest_attempt_id'] for a in known),'Invalid baseline membership')
            require(jt['baseline']['metrics']==_metrics(known),'Baseline aggregates disagree with samples')
            if jt['latest_attempt_id'] in attempts:
                latest=attempts[jt['latest_attempt_id']]
                expected={k:_delta(latest['timing'][k]['value_seconds'],jt['baseline']['metrics'][k],env['policies']['comparison_mode']) for k in ('queue','execution','total')}
                require(jt['baseline']['deltas']==expected,'Baseline deltas disagree with samples')
        if not compact:
            candidates=[a for a in attempts.values() if a['type_id']==jt['id'] and a['id'] in value['source']['retained_job_ids']]
            if env['policies']['comparison_mode']=='cross_ref':candidates=[a for a in candidates if a['metadata']['ref'] in env['policies']['refs']]
            expected=sorted((a['id'] for a in candidates),reverse=True)
            require(jt['retained_attempt_ids']==expected and jt['latest_attempt_id']==(expected[0] if expected else None),'Retained/latest selection mismatch')
    for w in windows.values():
        members=[attempts[i] for i in w['attempt_ids'] if i in attempts]
        if len(members)!=len(w['attempt_ids']):continue
        successful=[a for a in members if a['metadata']['status']=='success']
        eligible=[a for a in members if a['baseline_eligible']]
        require(w['descriptive']=={'attempt_ids':[a['id'] for a in successful],'metrics':_metrics(successful)},'Descriptive cohort/aggregates mismatch')
        require(w['inferential']=={'attempt_ids':[a['id'] for a in eligible],'metrics':_metrics(eligible)},'Inferential cohort/aggregates mismatch')
        f=w['findings'];require(f['metrics']==_metrics(eligible) and f['eligible_successful_n']==len(eligible),'Finding sample statistics mismatch')
        require(f['trace_known_n']+f['trace_missing_n']==len(eligible),'Finding trace coverage mismatch')
        if w['type_id'] in types:
            jt=types[w['type_id']]
            ids=[i for i in jt['retained_attempt_ids'] if i in attempts and attempts[i]['metadata']['ref'] in w['refs']]
            require(w['attempt_ids']==ids[w['page']*32:w['page']*32+w['size']],'Window bounds differ from retained selection')
        for c in f['categories']:
            require(c['id']=='finding-'+digest([w['id'],c['code']])[:20],'Category ID mismatch')
            require([s['attempt_id'] for s in c['samples']]==[a['id'] for a in eligible],'Category sample membership mismatch')
            metric=_metric([s['value_seconds'] for s in c['samples']])
            require((c['known'],c['missing'],c['median_seconds'])==(metric['known'],metric['missing'],metric['median_seconds']),'Category aggregate mismatch')
            for sample,a in zip(c['samples'],eligible):
                trace_external=('traces',str(a['id'])) in external
                if not trace_external:
                    require(sample==_category_sample(a,c['code'])[0],'Category inputs/cost disagree with evidence')
                elif sample['intervals']:
                    union=_union(sample['intervals'])
                    require(union==sample['intervals'] and sample['value_seconds']==sum(e-s for s,e in union),'Compact interval union mismatch')
        ranked=sorted([c for c in f['categories'] if c['median_seconds'] is not None],key=lambda c:(-c['median_seconds'],c['code']))
        require(f['priority_codes']==[c['code'] for c in ranked[:3]],'Priority ordering mismatch')
        for index,c in enumerate(ranked,1):require(c['rank']==index,'Category rank mismatch')
        for c in f['categories']:
            if c['median_seconds'] is None:require(c['rank'] is None,'Unknown category has rank')


def validate(value, kind=None):
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    if kind != 'trace':
        require(value.get('schema_version')==VERSION,'Unsupported schema version; v2 requires fresh v2 collection, use --legacy for v1 report generation/rendering')
    artifact=KINDS.get(value.get('kind'))
    if kind=='trace':artifact='trace'
    require(artifact is not None,'Unknown artifact kind')
    data=encoded(value);require(len(data)<=MAX_PAYLOAD_BYTES,'Payload exceeds 16 MiB; narrow job selection')
    schema_name={'jobs':'source-contract-v2','report':'report-contract-v2'}.get(artifact,artifact)
    schema=load(ROOT/'schemas'/f'{schema_name}.schema.json');common=load(ROOT/'schemas/common.schema.json')
    Draft202012Validator.check_schema(common)
    registry=Registry().with_resource(common['$id'],Resource.from_contents(common))
    errors=Draft202012Validator(schema,registry=registry,format_checker=FormatChecker()).iter_errors(value)
    error=next(errors,None)
    if error is not None:raise ValueError('JSON Schema: '+'.'.join(map(str,error.path))+': '+error.validator)
    if artifact=='jobs':check_source(value)
    elif artifact in {'report','compact'}:check_derived(value,compact=artifact=='compact')
    else:check_trace(value)


def save(path, value, kind=None):
    validate(value,kind)
    write_bytes(path,encoded(value))


def write_bytes(path, data):
    """Atomic exclusive artifact creation; failed writes leave no final artifact."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    require(not path.exists(),'Output already exists; choose a new output path')
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix=path.name+'.',delete=False) as f:
            temporary=Path(f.name);f.write(data)
        os.link(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
