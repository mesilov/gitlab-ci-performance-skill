"""The installed canonical collect/report/export/render route with >16 MiB data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/gitlab-ci-performance/scripts'))
sys.path.insert(0,str(ROOT/'tests'))
from fixture_v2 import sample, AT
from test_collect_v2 import job
from report_contract import encoded, load, validate

class OriginalCLITests(unittest.TestCase):
    def test_installed_full_route_large_single_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);skill=root/'installed'
            shutil.copytree(ROOT/'skills/gitlab-ci-performance',skill)
            rows=[job(i,name='job-'+str(i)) for i in range(1,4)]
            for row in rows:row['pipeline']['ref']=row['ref']
            (root/'rows.json').write_text(json.dumps(rows))
            fake=root/'glab';fake.write_text('#!'+sys.executable+'\n'+'''
import json,sys
from pathlib import Path
rows=json.loads(Path(__file__).with_name('rows.json').read_text())
if sys.argv[1]=='version':print('glab version 1.0.0');sys.exit(0)
e=sys.argv[-1]
print('HTTP/1.1 200 OK\\n')
if e=='projects/example%2Fservice':value={'id':42,'path_with_namespace':'example/service','web_url':'https://gitlab.example.com/example/service','default_branch':'main'}
elif e=='version':value={'version':'18.0.0'}
elif e.endswith('/trace'):
 print('#1 [builder-stage 1/1] RUN  '+('x'*2200000))
 print('#1 DONE 1s');sys.exit(0)
elif '/jobs?' in e:value=rows
elif '/jobs/' in e:value=next(r for r in rows if r['id']==int(e.rsplit('/',1)[-1]))
elif '/pipelines/' in e:
 r=next(r for r in rows if r['id']==int(e.rsplit('/',1)[-1]))
 value=dict(r['pipeline'],created_at=r['created_at'],started_at=r['started_at'],finished_at=r['finished_at'],duration=1.5,queued_duration=.5)
else:sys.exit(2)
print(json.dumps(value))
''');fake.chmod(0o700)
            env=dict(os.environ,PATH=str(root)+os.pathsep+os.environ['PATH'])
            cli=skill/'scripts/report_cli.py'
            def run(*args):
                p=subprocess.run([sys.executable,str(cli),*map(str,args)],env=env,capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr)
            run('collect','--host','gitlab.example.com','--project','example/service','--output',root/'source.json')
            original=(root/'source.json').read_bytes()
            run('report','--snapshot',root/'source.json','--output',root/'report.json')
            self.assertGreater((root/'report.json').stat().st_size,16*1024*1024)
            run('export','--report',root/'report.json','--attempt-ids',1,2,3,'--output',root/'attempts.json')
            run('render','--report',root/'report.json','--language','ru','--output',root/'report.html')
            run('validate',root/'attempts.json')
            self.assertEqual((root/'source.json').read_bytes(),original)
            self.assertGreater((root/'report.html').stat().st_size,16*1024*1024)
            report=load(root/'report.json');self.assertEqual(len(report['job_types']),3)
            for a in report['attempts']:
                op=next(n for n in a['trace']['evidence'] if n['kind']=='operation')
                self.assertTrue(op['source_label']['text']=='[builder-stage 1/1] RUN  '+'x'*2200000)

    def test_buildkit_browser_fixture_generator_preserves_source(self):
        import base64
        from generate_buildkit_fixture import generate
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);generate(root)
            source=load(root/'jobs.json')
            for trace in source['traces']:
                raw=base64.b64decode(trace['source']['raw_base64'])
                self.assertIn(b'PRIVATE_TOKEN=hunter2',raw)
                self.assertIn(b'<img src=x',raw)
                self.assertEqual(len([n for n in trace['evidence'] if n['kind']=='image']),4)
            self.assertNotIn('<img src=x', (root/'report-en.html').read_text())

    def test_actual_canonical_validation_exact_byte_limit(self):
        # Use a declared, non-source-text limitations field to pad a valid source.
        s=sample(0);s['source']['limitations']=['']
        overhead=len(encoded(s));s['source']['limitations']=['x'*(67108864-overhead)]
        self.assertEqual(len(encoded(s)),67108864);validate(s)
        s['source']['limitations'][0]+='ю'
        self.assertEqual(len(encoded(s)),67108866)
        with self.assertRaisesRegex(ValueError,'64 MiB'):validate(s)

if __name__=='__main__':unittest.main()
