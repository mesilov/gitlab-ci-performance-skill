"""Generate original-source injection/CR/long-title offline browser fixtures."""
import argparse
from pathlib import Path
from test_original_source import RAW, HEADER, AT, sample, parse_trace, build_report, render
from report_contract import save

def generate(output):
    source=sample(1)
    raw=RAW.replace(HEADER.encode(),(HEADER+'ю '*4096).encode())
    source['traces']=[parse_trace(1,raw,fetched_at=AT,analyzed_at=AT)]
    report=build_report(source,generated_at=AT)
    save(output/'jobs.json',source);save(output/'report.json',report)
    for lang in ('en','ru'):render(report,output/(lang+'.html'),lang)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True)
    generate(parser.parse_args().output_dir)
