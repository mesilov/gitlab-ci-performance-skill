import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/gitlab-ci-performance/scripts'))
from test_ci_report import ci, sample
from reviewed_report import build
from collection import collect_details

ROOT=Path(__file__).resolve().parents[1]
CLI=ROOT/'skills/gitlab-ci-performance/scripts/ci_report.py'


class ReviewedContracts(unittest.TestCase):
    def test_cli_accepts_verified_configuration_ref_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'jobs.json';source.write_bytes(ci.encoded(sample()))
            catalog=Path(directory)/'catalog.json'
            catalog.write_text(json.dumps({'project':'example/service','jobs':{'build':{
                'description':'Build images','source_url':'https://gitlab.example.com/config','verified_at':'2026-10-04T00:00:00Z',
                'source_ref':'main','configuration_sha256':'a'*64}}}))
            output=Path(directory)/'report.json'
            result=subprocess.run([sys.executable,str(CLI),'report','--snapshot',str(source),'--catalog',str(catalog),'--output',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(output.read_text())['types'][0]['purpose']['configuration_sha256'],'a'*64)
    def test_saved_inputs_round_trip_and_deterministic_offline_render(self):
        s=sample()
        metadata,timings=collect_details(s,no_traces=True,request_json=lambda *args: (_ for _ in ()).throw(ValueError('fixture')))
        report=build(s,metadata,timings,legacy=ci.build_report(s))
        ci.validate(metadata,'metadata');ci.validate(timings,'timings');ci.validate(report,'report')
        with tempfile.TemporaryDirectory() as directory:
            a,b=Path(directory)/'a.html',Path(directory)/'b.html'
            ci.render(report,a,'ru');ci.render(report,b,'ru')
            self.assertEqual(a.read_bytes(),b.read_bytes())
            self.assertIn('Что улучшить',a.read_text())
            self.assertNotIn('__REPORT_DATA__',a.read_text())

    def test_unknown_versions_duplicate_details_and_outside_evidence_are_rejected(self):
        s=sample();r=build(s,legacy=ci.build_report(s))
        r['schema_version']='9.0.0'
        with self.assertRaisesRegex(ValueError,'version|Version'):
            ci.validate(r,'report')
        r=build(s,legacy=ci.build_report(s));r['details'].append(copy.deepcopy(r['details'][0]))
        with self.assertRaises(ValueError):ci.validate(r,'report')
        r=build(s,legacy=ci.build_report(s));r['types'][0]['windows'][0]['priorities'][0]['evidence']['job_id']=999
        with self.assertRaises(ValueError):ci.validate(r,'report')

    def test_source_hash_mismatch_rejects_detail_inputs(self):
        s=sample();m,t=collect_details(s,no_traces=True,request_json=lambda *args: (_ for _ in ()).throw(ValueError('fixture')))
        m['source']['snapshot_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source snapshot'):build(s,m,t)

    def test_detail_project_timezone_and_full_membership_must_match(self):
        s=sample();m,t=collect_details(s,no_traces=True,request_json=lambda *args: (_ for _ in ()).throw(ValueError('fixture')))
        for modify in ('project','timezone','extra_detail'):
            mm,tt=copy.deepcopy(m),copy.deepcopy(t)
            if modify=='project':mm['project']['id']=123;tt['project']['id']=456
            elif modify=='timezone':mm['timezone']=tt['timezone']='Asia/Bishkek'
            else:tt['details'].append(dict(tt['details'][0],job_id=999))
            tt['source']['metadata_sha256']=ci.digest(mm)
            with self.assertRaises(ValueError):build(s,mm,tt)

    def test_render_rejects_forged_baseline_and_latest_values(self):
        s=sample();r=build(s,legacy=ci.build_report(s))
        c=r['types'][0]['comparison'];c.update(latest_seconds=9999,baseline_seconds=1,delta_seconds=9998,delta_percent=999800,eligible_increase=True)
        with self.assertRaises(ValueError):ci.validate(r,'report')

    def test_retained_baseline_requires_full_identity_and_fixed_scope(self):
        report=build(sample(),legacy=ci.build_report(sample()))
        for field,value in [('pipeline_id',99999),('ref','forged'),('execution_seconds',99),('queue_seconds',99)]:
            r=copy.deepcopy(report)
            r['types'][0]['comparison']['samples'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):ci.validate(r,'report')
        for key,scope in [('comparison','same_ref_history'),('same_ref_comparison','exploratory_cross_ref')]:
            r=copy.deepcopy(report);r['types'][0][key]['scope']=scope
            with self.subTest(key=key),self.assertRaises(ValueError):ci.validate(r,'report')

    def test_cli_default_generates_v2_and_legacy_is_explicit(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'jobs.json';source.write_bytes(ci.encoded(sample()))
            report=Path(directory)/'report.json'
            result=subprocess.run([sys.executable,str(CLI),'report','--snapshot',str(source),'--output',str(report)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(report.read_text())['schema_version'],'2.0.0')
            help_result=subprocess.run([sys.executable,str(CLI),'collect-details','--help'],capture_output=True,text=True)
            self.assertEqual(help_result.returncode,0,help_result.stderr)
            self.assertIn('--reuse-cache',help_result.stdout)


if __name__=='__main__':unittest.main()
