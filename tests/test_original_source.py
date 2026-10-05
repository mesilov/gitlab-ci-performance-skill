"""Acceptance tests for the lossless canonical trace contract."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'skills/gitlab-ci-performance/scripts'))
from report_trace import parse_trace, MAX_EVIDENCE_NODES
import report_contract as contract
from report_calculate import build_report
from report_export import export_report
from report_cli import render
from fixture_v2 import sample, AT

REFERENCE = 'registry.example.com:5050/team/private-token/php:Release@sha256:' + 'a'*64
HEADER = '[php-builder 2/4] RUN  echo  "<script>globalThis.executed=1</script>" && TOKEN=synthetic-password command  '
RAW = ('\x1b[32m#0 building with "default" instance using docker driver\x1b[0m\r\n'
       '\r#1 [php-builder 1/4] FROM '+REFERENCE+'\n\r#1 DONE 1s\n'
       '#2 '+HEADER+'\n#2 0.5 output\rprogress\n#2 DONE 2s\n'
       '#3 [php-builder 3/4] COPY  ./private.pem  /app/private.pem\n#3 DONE 1s\n'
       '#4 exporting to image\n#4 naming to '+REFERENCE+' done\n'
       '#4 unpacking to '+REFERENCE+' 1s done\n#4 DONE 3s\n').encode()

class OriginalSourceTests(unittest.TestCase):
    def parse(self, raw=RAW, **kwargs):
        return parse_trace(1, raw, fetched_at=AT, analyzed_at=AT, **kwargs)

    def test_complete_headers_references_and_lossless_physical_source(self):
        t=self.parse();ops={n['buildkit']['step_id']:n for n in t['evidence'] if n['kind']=='operation'}
        self.assertEqual(ops[2]['source_label']['text'], HEADER)
        self.assertEqual(ops[2]['source_label']['state'], 'original')
        self.assertEqual(ops[2]['source_label']['lines'], {'start':4,'end':4})
        identity=next(n['identity'] for n in t['evidence'] if n['kind']=='image')
        self.assertEqual(identity['reference'], REFERENCE)
        self.assertEqual(identity['name'], 'php')
        self.assertEqual(base64.b64decode(t['source']['raw_base64']), RAW)
        self.assertEqual(t['sha256'], hashlib.sha256(RAW).hexdigest())
        self.assertEqual(t['line_count'],12)
        self.assertNotIn('[redacted]', json.dumps(t))
        contract.validate(t,'trace')

    def test_long_titles_and_non_utf8_source_are_not_discarded(self):
        header='[named-stage 1/1] RUN  '+('ю ' * 4096)
        raw=('#1 '+header+'\n#1 DONE 1s\n').encode()+b'invalid:\xff\x00\n'
        t=self.parse(raw);op=next(n for n in t['evidence'] if n['kind']=='operation')
        self.assertEqual(op['source_label']['text'],header)
        self.assertEqual(base64.b64decode(t['source']['raw_base64']),raw)
        contract.validate(t,'trace')

    def test_partial_and_node_limit_keep_raw_and_explicit_boundary(self):
        raw=b''.join(f'section_start:{i*2}:step_script\nsection_end:{i*2+1}:step_script\n'.encode() for i in range(MAX_EVIDENCE_NODES+5))
        t=self.parse(raw)
        self.assertEqual(base64.b64decode(t['source']['raw_base64']),raw)
        self.assertEqual(t['state'],'partial')
        self.assertEqual(t['coverage']['evidence_limit']['reason'],'node_limit')
        self.assertGreater(t['coverage']['evidence_limit']['first_omitted_line'],0)
        prefix=self.parse(RAW[:-9],truncated=True)
        self.assertIsNone(prefix['sha256']);self.assertEqual(prefix['prefix_sha256'],hashlib.sha256(RAW[:-9]).hexdigest())

    def test_summary_limit_boundary_includes_removed_ancestors(self):
        import report_trace
        raw=b'#1 [builder 1/2] RUN echo original\n#1 DONE 1s\n#2 [builder 2/2] RUN echo second\n#2 DONE 2s\n'
        with patch.object(report_trace,'MAX_SUMMARY_BYTES',2500):
            t=self.parse(raw)
        self.assertEqual(t['evidence'],[])
        self.assertEqual(t['coverage']['evidence_limit'],{'reason':'summary_bytes','first_omitted_line':1})
        self.assertEqual(base64.b64decode(t['source']['raw_base64']),raw)

    def test_source_report_attempt_export_and_html_preserve_source(self):
        s=sample(1);s['traces']=[self.parse()]
        report=build_report(s,generated_at=AT)
        compact=export_report(report,attempt_ids=[1])
        for t in [report['source']['traces'][0],report['attempts'][0]['trace'],compact['attempts'][0]['trace']]:
            self.assertEqual(base64.b64decode(t['source']['raw_base64']),RAW)
            self.assertIn(HEADER,[n['source_label']['text'] for n in t['evidence'] if n['source_label']])
        with tempfile.TemporaryDirectory() as d:
            for lang in ['ru','en']:
                out=Path(d)/(lang+'.html');render(report,out,lang)
                html=out.read_text();embedded=json.loads(html.split('<script id="report-data" type="application/json">')[1].split('</script>')[0])
                self.assertEqual(embedded,report)
                self.assertNotIn('<script>globalThis.executed',html)
                self.assertIn('source-fragment',html)

    def test_source_titles_and_references_must_match_received_bytes(self):
        for mutate in ('label', 'reference'):
            t=self.parse()
            if mutate=='label':
                next(n for n in t['evidence'] if n['kind']=='operation')['source_label']['text']='invented title'
            else:
                next(n for n in t['evidence'] if n['kind']=='image')['identity']['reference']='invented.example/php:latest'
            with self.subTest(mutate=mutate),self.assertRaisesRegex(ValueError,'physical|reference'):
                contract.validate(t,'trace')

    def test_size_constant_and_load_boundary_use_utf8_bytes(self):
        self.assertEqual(contract.MAX_PAYLOAD_BYTES,67108864)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'input.json'
            # Four UTF-8 bytes per emoji, including JSON framing and newline.
            raw=contract.encoded({'text':'ю'*100})
            path.write_bytes(raw)
            with patch.object(contract,'MAX_PAYLOAD_BYTES',len(raw)):
                self.assertEqual(contract.load(path),{'text':'ю'*100})
            with patch.object(contract,'MAX_PAYLOAD_BYTES',len(raw)-1):
                with self.assertRaisesRegex(ValueError,'UTF-8|bytes|MiB'):contract.load(path)

    def test_exact_real_64_mib_json_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'boundary.json'
            overhead=len(contract.encoded({'text':''}))
            raw=contract.encoded({'text':'x'*(67108864-overhead)})
            self.assertEqual(len(raw),67108864)
            path.write_bytes(raw);self.assertEqual(len(contract.load(path)['text']),67108864-overhead)
            with path.open('ab') as handle:handle.write(b' ')
            with self.assertRaisesRegex(ValueError,'64 MiB'):contract.load(path)

    def test_large_report_single_artifact_offline_route(self):
        s=sample(3)
        # Three different job types, source > 8 MiB; report duplicates traces and exceeds 16 MiB.
        for job in s['jobs']:job['name']=f'build-{job["id"]}'
        s['source']['observed_counts']=[{'type_id':contract.type_id(s['project'],j['stage'],j['name']),'stage':j['stage'],'name':j['name'],'available_count':1,'count_kind':'exact'} for j in s['jobs']]
        s['traces']=[parse_trace(j['id'],b'plain output '+b'x'*2200000+b'\n',fetched_at=AT,analyzed_at=AT) for j in s['jobs']]
        report=build_report(s,generated_at=AT)
        self.assertGreater(len(contract.encoded(report)),16*1024*1024)
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);contract.save(d/'source.json',s);contract.save(d/'report.json',report)
            compact=export_report(contract.load(d/'report.json'),attempt_ids=[1,2,3]);contract.save(d/'export.json',compact)
            render(contract.load(d/'report.json'),d/'report.html')
            self.assertGreater((d/'report.html').stat().st_size,16*1024*1024)

if __name__=='__main__':unittest.main()
