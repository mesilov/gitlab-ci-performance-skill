"""Exercise a skill-only installation with a synthetic, standalone glab transport."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('demo_fixture',ROOT/'examples/generate_reviewed.py')
demo=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(demo)

FAKE_GLAB='''import json,os,sys
from pathlib import Path
f=Path(os.environ['CI_FIXTURE_DIR']);s=json.loads((f/'api.json').read_text());args=sys.argv[1:]
if args==['version']:print('glab fixture');sys.exit(0)
endpoint=args[-1]
with (f/'requests.jsonl').open('a') as log:log.write(json.dumps(endpoint)+'\\n')
headers='HTTP/1.1 200 OK'
if endpoint.startswith('projects/example%2Fservice'):data=s['project']
elif endpoint=='version':data={'version':'synthetic'}
elif '/jobs?' in endpoint:
 older='id_before=' in endpoint;data=s['jobs'][100:] if older else s['jobs'][:100]
 if not older:headers+='\\nLink: <https://gitlab.example.com/api/v4/projects/42/jobs?id_before='+str(data[-1]['id'])+'>; rel="next"'
elif '/pipelines/' in endpoint:data=s['pipelines'][endpoint.rsplit('/',1)[-1]]
elif endpoint.endswith('/trace'):
 record=s['traces'][endpoint.split('/')[-2]]
 if isinstance(record,list):sys.stderr.write('transport fixture failed');sys.exit(1)
 sys.stdout.write(record);sys.exit(0)
elif '/jobs/' in endpoint:data=s['job_by_id'][endpoint.rsplit('/',1)[-1]]
else:sys.exit(2)
if '--include' in args:print(headers+'\\n')
print(json.dumps(data))
'''


class InstallationTests(unittest.TestCase):
    def test_clean_installed_workflow_update_and_request_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);installed=root/'.agents/skills/gitlab-ci-performance'
            shutil.copytree(ROOT/'skills/gitlab-ci-performance',installed,ignore=shutil.ignore_patterns('__pycache__'))
            source=demo.fixture()
            raw=[demo.api_job(j) for j in source['jobs']]
            traces={}
            for j in source['jobs']:
                if j['started_at']:
                    value=demo.trace(j)
                    traces[str(j['id'])]=value.decode() if isinstance(value,bytes) else [value[0],'']
            api={'project':{'id':42,'path_with_namespace':'example/service','web_url':source['project']['web_url'],'default_branch':'main'},
                 'jobs':raw,'job_by_id':{str(j['id']):j for j in raw},'pipelines':{str(p['id']):dict(p,duration=p['duration_seconds'],queued_duration=p['queued_seconds']) for p in source['pipelines']},'traces':traces}
            (root/'api.json').write_text(json.dumps(api))
            bin_dir=root/'bin';bin_dir.mkdir();glab=bin_dir/'glab'
            glab.write_text('#!'+sys.executable+'\n'+FAKE_GLAB);glab.chmod(0o700)
            env=dict(os.environ,PATH=str(bin_dir)+os.pathsep+os.environ['PATH'],CI_FIXTURE_DIR=str(root))
            helper=installed/'scripts/ci_report.py'
            def run(*args,success=True):
                p=subprocess.run([sys.executable,str(helper),*map(str,args)],cwd=root,env=env,capture_output=True,text=True)
                if success:self.assertEqual(p.returncode,0,p.stderr)
                else:self.assertNotEqual(p.returncode,0)
                return p
            run('collect','--host','gitlab.example.com','--project','example/service','--output',root/'jobs.json')
            run('collect-details','--snapshot',root/'jobs.json','--output-dir',root/'details')
            run('report','--snapshot',root/'jobs.json','--details',root/'details','--output',root/'report.json')
            run('render','--report',root/'report.json','--language','ru','--output',root/'report.html')
            run('render','--report',root/'report.json','--language','ru','--output',root/'again.html')
            self.assertEqual((root/'report.html').read_bytes(),(root/'again.html').read_bytes())
            report=json.loads((root/'report.json').read_text());metadata=json.loads((root/'details/metadata.json').read_text())
            self.assertEqual(len(report['jobs']),110)
            for path in [root/'jobs.json',root/'report.json',root/'details/metadata.json',root/'details/timings.json',root/'report.html']:
                self.assertNotIn(demo.SENTINEL,path.read_text());run('validate',path) if path.suffix=='.json' else None
            endpoints=[json.loads(line) for line in (root/'requests.jsonl').read_text().splitlines()]
            trace_ids={int(e.split('/')[-2]) for e in endpoints if e.endswith('/trace')}
            retained={j['id'] for j in report['jobs']}
            self.assertTrue(trace_ids<=retained)
            self.assertLessEqual(metadata['coverage']['trace_requests'],len(retained))
            self.assertEqual(metadata['coverage']['metadata_requests'],len(retained))
            self.assertLess((root/'report.html').stat().st_size,2_000_000)
            # A repeated details output fails before contacting glab.
            count=len(endpoints)
            run('collect-details','--snapshot',root/'jobs.json','--output-dir',root/'details',success=False)
            self.assertEqual(len((root/'requests.jsonl').read_text().splitlines()),count)
            # Preserve a v1 report through replacing an installed skill directory.
            shutil.copy2(ROOT/'examples/report.json',root/'saved-v1.json')
            shutil.rmtree(installed)
            shutil.copytree(ROOT/'skills/gitlab-ci-performance',installed,ignore=shutil.ignore_patterns('__pycache__'))
            run('render','--report',root/'saved-v1.json','--language','en','--output',root/'legacy.html')
            self.assertIn('How CI', (root/'legacy.html').read_text())


if __name__=='__main__':unittest.main()
