"""Generate generic workflow artifacts and unit-boundary browser fixtures offline."""
import argparse
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'skills/gitlab-ci-performance/scripts'))
import ci_report as ci


def synthetic(count=64):
    stamp='2026-10-04T00:00:00Z'
    project=dict(id=42,path='example/service',host='gitlab.example.com',
                 web_url='https://gitlab.example.com/example/service',default_branch='main')
    def rule(name,stage,required=True,manual=False,needs=(),parallel=None):
        return dict(id=name,name=name,stage=stage,required=required,manual=manual,
                    needs=list(needs),parallel_group=parallel)
    def version(jobs):
        return dict(version='1',evidence_ids=['resolved'],selection=dict(refs=['main'],sources=['push']),
                    completion='all_required_terminal',success='required_success',unknown_membership=[],jobs=jobs)
    model=dict(project=dict(host=project['host'],path=project['path']),cross_pipeline_policy='unsupported',
        unknowns=['Synthetic example; earliest four pipelines deliberately lack verified configuration'],evidence=[],
        workflows=[dict(id='delivery',purpose='Build and verify a package',type='chain',versions=[version([
            rule('compile','build'),rule('test','test',needs=['compile'],parallel='checks'),
            rule('integration','test',needs=['compile'],parallel='checks'),
            rule('publish','publish',False,True,['test','integration'])])]),
            dict(id='maintenance',purpose='Independent maintenance tools',type='independent',versions=[version([
                rule('lint','tools',manual=True),rule('audit','tools',manual=True)])])])
    snapshot=dict(schema_version='2.0.0',kind='workflow-jobs',collection_started_at=stamp,collected_at=stamp,
        timezone='UTC',project=project,source=dict(transport='glab',glab_version='synthetic-demo',
            gitlab_version='synthetic-demo',requested_window=64,anchor_pipeline_id=count,
            pipeline_pages=1,max_pages=10,pipeline_list_complete=True,pipelines={},
            pipeline_history_exhausted=True,
            limitations=['Synthetic demonstration; not collected from GitLab','Cross-pipeline scenarios unsupported','No traces collected']),
        pipelines=[],jobs=[])
    for pid in range(1,count+1):
        start=datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(hours=pid*8)
        iso=lambda seconds:(start+timedelta(seconds=seconds)).isoformat()
        snapshot['pipelines'].append(dict(id=pid,ref='main',sha='synthetic',source='push',status='success',
            created_at=iso(0),started_at=iso(10),finished_at=iso(400 if pid==count else 80),
            duration_seconds=390 if pid==count else 70,queued_seconds=10,
            web_url=f'https://gitlab.example.com/pipelines/{pid}'))
        snapshot['source']['pipelines'][str(pid)]=dict(metadata_complete=True,jobs_complete=True,pages=1,
            anchor_job_id=pid*100+6,error=None)
        for offset,name,stage,begin,end,status in [
            (1,'compile','build',10,30,'success'),(2,'test','test',40,400 if pid==count else 80,'success'),
            (3,'publish','publish',None,None,'manual'),(4,'integration','test',40,80,'success'),
            (5,'lint','tools',15,55,'failed' if pid==count-1 else 'success'),
            (6,'audit','tools',None if pid==count-2 else 90,None if pid==count-2 else 120,
                'manual' if pid==count-2 else 'success')]:
            snapshot['jobs'].append(dict(id=pid*100+offset,pipeline_id=pid,name=name,stage=stage,ref='main',
                status=status,allow_failure=False,created_at=iso(0),started_at=iso(begin) if begin is not None else None,
                finished_at=iso(end) if end is not None else None,duration_seconds=end-begin if end is not None else None,
                queued_seconds=2 if begin is not None else None,failure_reason=None,runner=None,
                web_url=f'https://gitlab.example.com/jobs/{pid*100+offset}'))
    retry=copy.deepcopy(next(j for j in snapshot['jobs'] if j['id']==(count-1)*100+1))
    retry['status']='failed';retry['id']=(count-1)*100
    snapshot['jobs'].append(retry)
    return snapshot,model


# Fully resolved demonstration configuration, without includes or private sources.
CONFIG='''stages: [build, test, publish, tools]
compile:
  stage: build
  script: echo synthetic
test:
  stage: test
  needs: [compile]
  script: echo synthetic
integration:
  stage: test
  needs: [compile]
  script: echo synthetic
publish:
  stage: publish
  needs: [test, integration]
  when: manual
  allow_failure: true
  script: echo synthetic
lint:
  stage: tools
  needs: []
  when: manual
  script: echo synthetic
audit:
  stage: tools
  needs: []
  when: manual
  script: echo synthetic
'''


def write_report(out,snapshot,definitions):
    ci.save(out/'jobs.json',snapshot,'workflow-jobs')
    ci.save(out/'workflows.json',definitions,'workflows')
    report=ci.workflow_build(snapshot,definitions)
    ci.save(out/'report.json',report,'workflow-report')
    ci.save(out/'llm.json',ci.workflow_export(report),'workflow-llm')
    ci.render(report,out/'report.html')
    ci.render(report,out/'report-ru.html','ru')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'reports/workflows')
    out=parser.parse_args().output_dir
    snapshot,model=synthetic()
    out.mkdir(parents=True,exist_ok=True)
    config=out/'resolved.yml'
    with config.open('x') as f:f.write(CONFIG)
    ci.save(out/'model.json',model)
    from workflow_report import stamp_definitions
    definitions=stamp_definitions(model,config,'resolved','https://gitlab.example.com/example/service/-/blob/synthetic/.gitlab-ci.yml',
        'synthetic','main','2026-10-04T00:00:00Z',list(range(5,65)),[])
    write_report(out,snapshot,definitions)
    for seconds in [300,301]:
        boundary=copy.deepcopy(snapshot)
        last=next(j for j in boundary['jobs'] if j['id']==6402)
        start=next(j['started_at'] for j in boundary['jobs'] if j['id']==6401)
        last['finished_at']=(ci.timestamp(start)+timedelta(seconds=seconds)).isoformat()
        last['duration_seconds']=(ci.timestamp(last['finished_at'])-ci.timestamp(last['started_at'])).total_seconds()
        write_report(out/f'boundary-{seconds}',boundary,definitions)


if __name__=='__main__':main()
