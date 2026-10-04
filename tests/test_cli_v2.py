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
CLI=SKILL/'scripts/ci_report.py'
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
            report=json.loads((d/'report.json').read_text());self.assertEqual(report['schema_version'],'2.0.0')
            self.run_cli('export','--report',d/'report.json','--scope','overview','--output',d/'compact.json')
            self.run_cli('validate',d/'compact.json')
            self.run_cli('render','--report',d/'report.json','--output',d/'report.html')
            html=(d/'report.html').read_text();data=html.split('<script id="report-data" type="application/json">')[1].split('</script>')[0]
            self.assertEqual(json.loads(data),report)
            installed=d/'installed';shutil.copytree(SKILL,installed)
            self.run_cli('render','--report',d/'report.json','--output',d/'installed.html',path=installed/'scripts/ci_report.py')
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
    def test_v1_requires_explicit_legacy_generation_but_renders(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            p=self.run_cli('report','--snapshot',ROOT/'examples/jobs.json','--output',d/'bad.json',ok=False)
            self.assertIn('--legacy',p.stderr);self.assertFalse((d/'bad.json').exists())
            self.run_cli('report','--legacy','--snapshot',ROOT/'examples/jobs.json','--output',d/'old.json')
            self.run_cli('render','--report',d/'old.json','--output',d/'old.html')
            self.run_cli('validate',ROOT/'examples/report.json')

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
