"""Generate public, synthetic v2 examples through the maintained workflow."""
import argparse
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/gitlab-ci-performance/scripts'))
from report_contract import save,type_id,SKILL_VERSION
from report_trace import parse_trace,empty_trace
from report_calculate import build_report
from report_export import export_report
from report_cli import render

AT='2026-10-04T00:00:00+00:00'

def synthetic_source(count=70):
    project={'id':42,'path':'example/demo-service','host':'gitlab.example.com','web_url':'https://gitlab.example.com/example/demo-service','default_branch':'main'}
    jobs,pipelines,traces,retained,counts=[],[],[],[],[]
    for offset,stage,name in [(0,'build','image_build'),(100,'release','release')]:
        for i in range(1,count+1):
            jid=offset+i;created=datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(hours=i)
            queue=90 if i==70 and offset==0 else 5;execution=330 if offset==0 else 35
            status='failed' if i==69 else 'canceled' if i==68 else 'skipped' if i==67 else 'manual' if i==66 else 'success'
            started=None if status in {'skipped','manual'} else created+timedelta(seconds=queue)
            finished=started+timedelta(seconds=execution) if started else None
            j={'id':jid,'pipeline_id':jid,'name':name,'stage':stage,'ref':'main','status':status,'allow_failure':False,'created_at':created.isoformat(),'started_at':started.isoformat() if started else None,'finished_at':finished.isoformat() if finished else None,'duration_seconds':execution if started else None,'queued_seconds':queue if started else None,'failure_reason':'script_failure' if status=='failed' else None,'runner':{'id':1,'description':'synthetic-runner'},'web_url':project['web_url']+f'/-/jobs/{jid}','sha':f'{jid:040x}','erased_at':AT if i==65 else None,'metadata_checked_at':AT,'metadata_fresh':True,'metadata_error':None}
            jobs.append(j);pipelines.append({'id':jid,'ref':'main','sha':j['sha'],'status':'failed' if i==69 else 'success','source':'push','created_at':j['created_at'],'started_at':j['started_at'],'finished_at':j['finished_at'],'duration_seconds':j['duration_seconds'],'queued_seconds':j['queued_seconds'],'web_url':project['web_url']+f'/-/pipelines/{jid}','metadata_checked_at':AT,'metadata_fresh':True,'metadata_error':None})
            if i<=count-64:continue
            retained.append(jid)
            if j['erased_at']:t=empty_trace(jid,'erased','metadata_erased',AT)
            elif not started:t=empty_trace(jid,'not_run','metadata_not_run',AT)
            elif i==64:t=empty_trace(jid,'permission_denied','permission_denied',AT)
            elif i==63:t=parse_trace(jid,b'',fetched_at=AT,analyzed_at=AT)
            elif i==62:t=empty_trace(jid,'unavailable','unavailable',AT)
            else:
                epoch=int(started.timestamp())
                def stamp(seconds):return (started+timedelta(seconds=seconds)).isoformat()
                lines=[f'section_start:{epoch}:get_sources\r',f'section_end:{epoch+4}:get_sources\r',f'section_start:{epoch+5}:step_script\r']
                if offset==0:
                    lines += [f'{stamp(10)} #1 [internal] load metadata for base',f'{stamp(13)} #1 DONE 3.0s',f'{stamp(14)} #2 [1/2] COPY application /app',f'{stamp(20)} #2 DONE 6.0s',f'{stamp(21)} #3 [2/2] RUN install-dependencies',f'{stamp(29)} #3 DONE 8.0s',f'{stamp(30)} #4 exporting to docker image',f'{stamp(36)} #4 exporting layers 6.0s done',f'{stamp(40)} #4 unpacking to local 4.0s done',f'{stamp(40)} #4 DONE 10.0s']
                else:lines += [f'{stamp(10)} $ perform-release',f'{stamp(25)} $ verify-release']
                lines += [f'section_end:{epoch+execution}:step_script\r']
                if i==61:lines.pop()  # supported partial trace
                t=parse_trace(jid,('\n'.join(lines)+'\n').encode(),fetched_at=AT,analyzed_at=AT)
            traces.append(t)
        counts.append({'type_id':type_id(project,stage,name),'stage':stage,'name':name,'available_count':count,'count_kind':'exact'})
    return {'schema_version':'2.0.0','skill_version':SKILL_VERSION,'kind':'gitlab_job_performance_source','collection_started_at':AT,'collected_at':AT,'timezone':'UTC','project':project,'source':{'transport':'glab','glab_version':'synthetic','gitlab_version':'synthetic','anchor_max_job_id':100+count,'pages':2,'cursor':None,'complete_available_history':True,'stop_reason':'eof','resumed_from_sha256':None,'requests':{'project':0,'version':0,'pages':0,'metadata':0,'pipelines':0,'traces':0},'budgets':{'max_pages':10,'max_job_types':16,'retained_per_type':64,'baseline_per_type':10,'concurrency':4,'trace_bytes':4194304,'trace_lines':50000,'timeout_seconds':60},'observed_counts':counts,'selection_policy':{'comparison_mode':'same_ref','refs':[],'job_selectors':[],'cache_max_age_seconds':86400},'limitations':['Synthetic sources; no GitLab requests were made']},'jobs':sorted(jobs,key=lambda x:x['id'],reverse=True),'pipelines':sorted(pipelines,key=lambda x:x['id'],reverse=True),'retained_job_ids':sorted(retained,reverse=True),'baseline_job_ids':[],'traces':sorted(traces,key=lambda x:x['job_id'],reverse=True)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--attempts-per-type',type=int,default=70,choices=range(1,71));args=parser.parse_args();out=args.output_dir
    source=synthetic_source(args.attempts_per_type);save(out/'jobs.json',source)
    report=build_report(source,generated_at=AT);save(out/'report.json',report)
    save(out/'overview.json',export_report(report,scope='overview'));render(report,out/'report.html')

if __name__=='__main__':main()
