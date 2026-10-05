"""Synthetic metadata only; no private projects or log content."""
from datetime import datetime, timedelta, timezone
import hashlib
import json

AT = '2026-10-04T00:00:00+00:00'

def sample(count=4, duration=100, queue=5):
    project = {'id':42,'path':'example/service','host':'gitlab.example.com','web_url':'https://gitlab.example.com/example/service','default_branch':'main'}
    jobs, pipelines, traces = [], [], []
    for i in range(1,count+1):
        created = datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(hours=i)
        started = created + timedelta(seconds=queue)
        finished = started + timedelta(seconds=duration)
        jobs.append({'id':i,'pipeline_id':i,'name':'build','stage':'build','ref':'main','status':'success','allow_failure':False,'created_at':created.isoformat(),'started_at':started.isoformat(),'finished_at':finished.isoformat(),'duration_seconds':duration,'queued_seconds':queue,'failure_reason':None,'runner':None,'web_url':project['web_url']+f'/-/jobs/{i}','sha':f'{i:040x}','erased_at':None,'metadata_checked_at':AT,'metadata_fresh':True,'metadata_error':None})
        pipelines.append({'id':i,'ref':'main','sha':f'{i:040x}','status':'success','source':'push','created_at':created.isoformat(),'started_at':started.isoformat(),'finished_at':finished.isoformat(),'duration_seconds':duration,'queued_seconds':queue,'web_url':project['web_url']+f'/-/pipelines/{i}','metadata_checked_at':AT,'metadata_fresh':True,'metadata_error':None})
        if i > count-64:
            traces.append({'job_id':i,'state':'unavailable','reason_code':'http_404','sha256':None,'prefix_sha256':None,'bytes_read':0,'line_count':0,'parser_version':'2.0.0','fetched_at':AT,'analyzed_at':AT,'cached':False,'coverage':{'recognized_lines':0,'total_lines':0,'truncated':False,'complete':False,'evidence_limit':None},'source':{'encoding':'base64','raw_base64':'','display_transform':'utf8-replacement-ansi-csi-strip-outer-cr'},'evidence':[]})
    encoded=(json.dumps([project['host'],project['id'],'build','build'],ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    tid='jobtype-'+hashlib.sha256(encoded).hexdigest()[:20]
    return {'schema_version':'3.0.0','skill_version':'2.0.1','kind':'gitlab_job_performance_source','collection_started_at':AT,'collected_at':AT,'timezone':'UTC','project':project,'source':{'transport':'glab','glab_version':'synthetic','gitlab_version':'synthetic','anchor_max_job_id':count or None,'pages':1,'cursor':None,'complete_available_history':True,'stop_reason':'eof','resumed_from_sha256':None,'requests':{'project':1,'version':1,'pages':1,'metadata':min(count,64),'pipelines':min(count,64),'traces':min(count,64)},'budgets':{'max_pages':10,'max_job_types':16,'retained_per_type':64,'baseline_per_type':10,'concurrency':4,'trace_bytes':4194304,'trace_lines':50000,'timeout_seconds':60},'observed_counts':[{'type_id':tid,'stage':'build','name':'build','available_count':count,'count_kind':'exact'}] if count else [],'limitations':['Synthetic fixture'],'selection_policy':{'comparison_mode':'same_ref','refs':[],'job_selectors':[],'cache_max_age_seconds':86400}},'jobs':list(reversed(jobs)),'pipelines':list(reversed(pipelines)),'retained_job_ids':list(range(count,max(0,count-64),-1)),'baseline_job_ids':[],'traces':list(reversed(traces))}
