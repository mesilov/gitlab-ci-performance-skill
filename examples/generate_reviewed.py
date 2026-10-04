"""Synthetic sources using the maintained collector/parser/report workflow."""
import argparse
import copy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/gitlab-ci-performance/scripts'))
import ci_report as ci
from collection import collect_details
from reviewed_report import build

SENTINEL='DO_NOT_EXPORT_TRACE_SENTINEL'


def fixture():
    base=datetime(2026,9,1,tzinfo=timezone.utc)
    project={'id':42,'path':'example/service','host':'gitlab.example.com','web_url':'https://gitlab.example.com/example/service','default_branch':'main'}
    snapshot={'schema_version':'1.0.0','kind':'jobs','collection_started_at':'2026-10-04T00:00:00Z','collected_at':'2026-10-04T00:01:00Z','timezone':'UTC','project':project,
              'source':{'transport':'glab','glab_version':'synthetic','gitlab_version':'synthetic','anchor_max_job_id':1006,'pages':2,'complete_available_history':True,'limitations':['Synthetic fixture; no real project data']},'jobs':[],'pipelines':[]}
    pmap={}
    def add(i,name,stage,index,duration,queue,status):
        pid=i-1 if index>1 and index%9==0 else i
        ref=pmap[pid]['ref'] if pid in pmap else ('main' if index%3==0 else f'release/{index}')
        start=base+timedelta(hours=i%200)
        created=(start-timedelta(seconds=10)).isoformat();started=start.isoformat()
        notrun=status in {'skipped','manual','pending','created','scheduled','waiting_for_resource'}
        active=status in {'running','preparing','canceling'}
        finished=(start+timedelta(seconds=duration or 0)).isoformat() if not notrun and not active else None
        if pid not in pmap:
            pmap[pid]={'id':pid,'ref':ref,'sha':f'{pid:040x}','status':'failed' if index%12==0 else 'success','source':'push',
                       'created_at':created,'started_at':started,'finished_at':finished,
                       'duration_seconds':duration,'queued_seconds':queue,'web_url':project['web_url']+f'/-/pipelines/{pid}'}
        snapshot['jobs'].append({'id':i,'pipeline_id':pid,'name':name,'stage':stage,'ref':ref,'status':status,'allow_failure':False,
                                 'created_at':created,'started_at':None if notrun else started,'finished_at':finished,
                                 'duration_seconds':0 if notrun else duration,'queued_seconds':queue,'failure_reason':None,
                                 'runner':{'id':2,'description':'Synthetic runner'},'web_url':project['web_url']+f'/-/jobs/{i}'})
    states=['failed','canceled','skipped','manual','pending','created','scheduled','waiting_for_resource','running','preparing','canceling']
    for n in range(1,81):
        status=states[(n-17)%len(states)] if 17<=n<=27 else 'failed' if n%19==0 else 'success'
        add(n,'container-build','build',n,420 if n==80 else 300+n/10,45 if n==80 else 5,status)
    for n in range(1,41):add(100+n,'package-release','release',n,25,3,'failed' if n==37 else 'success')
    for n in range(1,7):add(1000+n,'quick-check','test',n,295,5,'success')
    snapshot['jobs'].sort(key=lambda j:j['id'],reverse=True)
    snapshot['pipelines']=sorted(pmap.values(),key=lambda p:p['id'],reverse=True)
    ci.validate(snapshot,'jobs')
    return snapshot


def api_job(job):
    raw=copy.deepcopy(job)
    raw['pipeline']={'id':job['pipeline_id']};raw['duration']=raw.pop('duration_seconds');raw['queued_duration']=raw.pop('queued_seconds')
    raw['commit']={'id':f"{job['pipeline_id']:040x}",'message':SENTINEL};raw['variables']=[{'value':SENTINEL}]
    raw['runner_manager']={'version':'synthetic'}
    raw['erased_at']='2026-10-03T00:00:00Z' if job['id']%13==0 else None
    return raw


def trace(job):
    if job['id']%17==0:return (404,b'')
    if job['id']%11==0:return b''
    origin=datetime.fromisoformat(job['started_at'])
    stamp=lambda s:(origin+timedelta(seconds=s)).isoformat().replace('+00:00','Z')
    epoch=int(origin.timestamp())
    lines=[f'section_start:{epoch}:step_script\r\x1b[0K',f'{stamp(0)} 00O $ echo {SENTINEL}']
    if job['stage']=='build':
        lines += [f'{stamp(0)} 00O #1 [internal] load build definition from private.Dockerfile',f'{stamp(1)} 00O #1 DONE 1.0s',
                  f'{stamp(1)} 00O #2 [stage 1/2] COPY private-source /app',f'{stamp(31)} 00O #2 DONE 30.0s',
                  f'{stamp(30)} 00O #3 exporting to image',f'{stamp(110)} 00O #3 exporting layers 80.0s done',
                  f'{stamp(130)} 00O #3 DONE 100.0s',f'{stamp(130)} 00O #3 DONE 100.0s',
                  f'{stamp(50)} 00O #4 exporting to image',f'{stamp(150)} 00O #4 DONE 100.0s',
                  f'{stamp(160)} 00O #1 [internal] load build definition from other.Dockerfile',f'{stamp(161)} 00O #1 DONE 1.0s',
                  f'{stamp(161)} 00O #2 [stage 1/1] RUN npm ci --private={SENTINEL}',f'{stamp(191)} 00O #2 DONE 30.0s',
                  f'{stamp(191)} 00O #3 exporting to image',f'{stamp(201)} 00O #3 DONE 10.0s']
        end=220
    else:
        lines += [f'{stamp(10)} 00O $ curl --data {SENTINEL} https://example.invalid/private']
        end=20
    if job['status'] not in {'running','preparing','canceling'}:lines.append(f'section_end:{epoch+end}:step_script\r\x1b[0K')
    return ('\n'.join(lines)+'\n').encode()


def artifacts(snapshot):
    byid={j['id']:j for j in snapshot['jobs']}
    def metadata(host,endpoint):return api_job(byid[int(endpoint.rsplit('/',1)[1])])
    def logs(host,endpoint,cap):return trace(byid[int(endpoint.split('/')[-2])])
    return collect_details(snapshot,request_json=metadata,request_trace=logs)


def generate(directory):
    directory=Path(directory)
    snapshot=fixture();metadata,timings=artifacts(snapshot)
    catalog={'project':snapshot['project']['path'],'jobs':{'container-build':{'description':'Build and publish application container images.','source_url':'https://gitlab.example.com/example/service/-/blob/main/.gitlab-ci.yml','verified_at':'2026-10-04T00:00:00Z','source_ref':'main','configuration_sha256':'a'*64}}}
    report=build(snapshot,metadata,timings,ci.build_report(snapshot),catalog)
    ci.save(directory/'jobs.json',snapshot,'jobs');ci.save(directory/'metadata.json',metadata,'metadata');ci.save(directory/'timings.json',timings,'timings')
    ci.save(directory/'report.json',report,'report');ci.save(directory/'catalog.json',catalog)
    ci.render(report,directory/'report.html','en');ci.render(report,directory/'report-ru.html','ru')
    for path in directory.iterdir():
        if SENTINEL in path.read_text():raise AssertionError('Raw trace content leaked')
    print(f"Synthetic: {len(snapshot['jobs'])} source attempts; {len(report['jobs'])} retained; {len(report['details'])} detail states")


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True)
    generate(parser.parse_args().output_dir)
