import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from fixture_v2 import sample, AT

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/gitlab-ci-performance'
CLI=SKILL/'scripts/report_cli.py'
sys.path.insert(0,str(SKILL/'scripts'))

class CLIV2Tests(unittest.TestCase):
    def run_cli(self,*args,path=CLI,ok=True):
        p=subprocess.run([sys.executable,str(path),*map(str,args)],capture_output=True,text=True)
        if ok:self.assertEqual(p.returncode,0,p.stderr)
        else:self.assertNotEqual(p.returncode,0)
        return p
    def test_offline_round_trip_installed_and_compact(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);source=d/'source.json';source.write_text(json.dumps(sample()))
            self.run_cli('report','--snapshot',source,'--generated-at',AT,'--output',d/'report.json')
            report=json.loads((d/'report.json').read_text());self.assertEqual(report['schema_version'],'3.0.0')
            self.assertEqual(report['skill_version'],(SKILL/'VERSION').read_text().strip())
            self.run_cli('export','--report',d/'report.json','--scope','overview','--output',d/'compact.json')
            self.run_cli('validate',d/'compact.json')
            self.run_cli('render','--report',d/'report.json','--output',d/'report.html')
            html=(d/'report.html').read_text();data=html.split('<script id="report-data" type="application/json">')[1].split('</script>')[0]
            self.assertEqual(json.loads(data),report)
            installed=d/'installed';shutil.copytree(SKILL,installed)
            self.run_cli('render','--report',d/'report.json','--output',d/'installed.html',path=installed/'scripts/report_cli.py')
            self.assertEqual((d/'installed.html').read_bytes(),(d/'report.html').read_bytes())
            self.run_cli('report','--snapshot',source,'--generated-at',AT,'--output',d/'repeat.json')
            self.assertEqual((d/'repeat.json').read_bytes(),(d/'report.json').read_bytes())
    def test_language_timestamps_and_escape(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);s=sample();s['timezone']='Asia/Bishkek';source=d/'source.json';source.write_text(json.dumps(s))
            self.run_cli('report','--snapshot',source,'--language','ru','--generated-at',AT,'--output',d/'report.json')
            self.run_cli('render','--report',d/'report.json','--output',d/'report.html')
            html=(d/'report.html').read_text();self.assertIn('2026-10-04 06:00:00',html);self.assertIn('lang="ru"',html)
            self.assertIn('Asia/Bishkek',html)
            self.run_cli('report','--snapshot',source,'--language','de','--output',d/'bad.json',ok=False)
            self.assertFalse((d/'bad.json').exists())
    def test_old_artifacts_and_legacy_flags_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            self.run_cli('report','--snapshot',ROOT/'examples/jobs.json','--output',directory/'bad.json',ok=False)
            self.run_cli('report','--legacy','--snapshot',ROOT/'examples/jobs.json','--output',directory/'old.json',ok=False)
            self.run_cli('render','--report',ROOT/'examples/report.json','--output',directory/'old.html',ok=False)
            self.run_cli('validate',ROOT/'examples/report.json',ok=False)
            self.assertEqual(list(directory.iterdir()),[])

class MainCompatibilityTests(unittest.TestCase):
    run_cli=CLIV2Tests.run_cli
    def test_published_and_canonical_entrypoints_coexist_in_installed_skill(self):
        import re
        from test_ci_report import sample as published_sample
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);installed=directory/'skill';shutil.copytree(SKILL,installed)
            canonical_cli=installed/'scripts/report_cli.py';published_cli=installed/'scripts/ci_report.py'
            old=directory/'old.json';old.write_text(json.dumps(published_sample()))
            source=directory/'source.json';source.write_text(json.dumps(sample()))
            original=source.read_bytes()
            self.run_cli('report','--snapshot',old,'--output',directory/'published.json',path=published_cli)
            published=json.loads((directory/'published.json').read_text())
            self.assertEqual((published['kind'],published['schema_version']),('report','2.0.1'))
            self.run_cli('render','--report',directory/'published.json','--language','ru','--output',directory/'published.html',path=published_cli)
            self.run_cli('report','--snapshot',source,'--generated-at',AT,'--output',directory/'canonical.json',path=canonical_cli)
            canonical=json.loads((directory/'canonical.json').read_text())
            self.assertEqual((canonical['kind'],canonical['schema_version']),('gitlab_job_performance_report','3.0.0'))
            self.assertEqual(canonical['skill_version'],(installed/'VERSION').read_text().strip())
            self.run_cli('export','--report',directory/'canonical.json','--scope','overview','--output',directory/'compact.json',path=canonical_cli)
            self.run_cli('validate',directory/'compact.json',path=canonical_cli)
            self.run_cli('render','--report',directory/'canonical.json','--language','ru','--output',directory/'canonical.html',path=canonical_cli)
            self.assertEqual(source.read_bytes(),original)
            for helper,file,name in [(published_cli,'canonical.json','wrong-published'),(canonical_cli,'published.json','wrong-canonical')]:
                self.run_cli('render','--report',directory/file,'--output',directory/(name+'.html'),path=helper,ok=False)
                self.assertFalse((directory/(name+'.html')).exists())

    def test_standalone_release_demo_resolves_installed_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,str(ROOT/'examples/generate_release_demo.py'),'--output-dir',directory],
                                  cwd=directory,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.run_cli('validate',Path(directory)/'report.json',path=SKILL/'scripts/ci_report.py')
            self.assertTrue((Path(directory)/'report.html').is_file())

    def test_language_override_keeps_canonical_json_in_installed_skill(self):
        import re
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);installed=root/'installed';shutil.copytree(SKILL,installed)
            installed_cli=installed/'scripts/report_cli.py'
            source=root/'source.json';source.write_text(json.dumps(sample()))
            self.run_cli('report','--snapshot',source,'--language','ru','--generated-at',AT,'--output',root/'v2.json')
            saved=json.loads((root/'v2.json').read_text())
            self.run_cli('render','--report',root/'v2.json','--language','en','--output',root/'v2.html',path=installed_cli)
            rendered=(root/'v2.html').read_text();self.assertIn('lang="en"',rendered)
            self.assertEqual(json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',rendered,re.S)[1]),saved)
            self.run_cli('validate',root/'v2.json',path=installed_cli)
            self.run_cli('report','--snapshot',source,'--windows','32','--output',root/'invalid.json',ok=False)
            self.assertFalse((root/'invalid.json').exists())

class AtomicHTMLTests(unittest.TestCase):
    def test_link_failure_does_not_leave_partial_destination(self):
        from report_calculate import build_report
        from report_cli import render
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'report.html'
            with patch('report_contract.os.link',side_effect=OSError('synthetic disk failure')):
                with self.assertRaises(OSError):render(build_report(sample()),p)
            self.assertFalse(p.exists());self.assertEqual(list(Path(d).iterdir()),[])
