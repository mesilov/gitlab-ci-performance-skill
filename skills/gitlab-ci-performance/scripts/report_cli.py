"""Installed v2 workflow; no transport access from report/export/render."""
import argparse
import html
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import ci_report as legacy
from report_contract import ROOT, encoded, load, save, timestamp, validate, write_bytes


def render(report, output, language=None):
    if report.get('schema_version') in {'1.0.0','1.1.0'}:
        legacy.render(report,output,language or 'en')
        return
    validate(report)
    language=language or report['language']
    if language not in {'en','ru'}:raise ValueError('Unsupported report language: choose en or ru')
    title=('GitLab Job performance report ' if language=='en' else 'Отчёт о производительности GitLab Job ')
    dt=timestamp(report['generated_at']).astimezone(ZoneInfo(report['timezone']))
    title+=dt.isoformat(sep=' ',timespec='seconds')+' ['+report['timezone']+']'
    payload=encoded(report).decode().replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=(ROOT/'assets/report-v2.html').read_text(encoding='utf-8')
    document=template.replace('__REPORT_TITLE__',html.escape(title)).replace('__REPORT_LANGUAGE__',language).replace('__REPORT_DATA__',payload)
    write_bytes(output,document.encode('utf-8'))


def main():
    parser=argparse.ArgumentParser(description='Bounded GitLab job metadata → validated JSON findings → compact export / offline HTML')
    subs=parser.add_subparsers(dest='command',required=True)
    collect=subs.add_parser('collect',help='Read bounded metadata and retained traces through glab')
    collect.add_argument('--host',required=True);collect.add_argument('--project',required=True)
    collect.add_argument('--timezone',default='UTC');collect.add_argument('--max-pages',type=int,default=10)
    collect.add_argument('--max-job-types',type=int,default=16);collect.add_argument('--concurrency',type=int,default=4)
    collect.add_argument('--job',action='append',help='stage/name; use --job-config for names containing /')
    collect.add_argument('--job-config',type=Path,help='JSON array of {stage,name}')
    collect.add_argument('--resume',type=Path);collect.add_argument('--cache',type=Path)
    collect.add_argument('--cache-max-age-seconds',type=int,default=86400)
    collect.add_argument('--trace-bytes',type=int,default=4194304);collect.add_argument('--trace-lines',type=int,default=50000)
    collect.add_argument('--comparison-mode',choices=['same_ref','cross_ref'],default='same_ref')
    collect.add_argument('--ref',action='append',help='Explicit cross-ref allowlist (repeat)')
    collect.add_argument('--output',type=Path,required=True)
    report=subs.add_parser('report',help='Calculate canonical report offline')
    report.add_argument('--snapshot',type=Path,required=True);report.add_argument('--baseline',type=Path)
    report.add_argument('--catalog',type=Path);report.add_argument('--guidance',type=Path)
    report.add_argument('--language',choices=['en','ru'],default='en');report.add_argument('--generated-at')
    report.add_argument('--comparison-mode',choices=['same_ref','cross_ref'],default='same_ref');report.add_argument('--ref',action='append')
    report.add_argument('--release-refs',nargs='+',help='Legacy exploratory release history; requires --legacy')
    report.add_argument('--legacy',action='store_true',help='Explicit frozen v1 calculation, no v2 semantics')
    report.add_argument('--windows',type=int,nargs='+',help='Legacy pipeline windows only; v2 history is 32/64')
    report.add_argument('--baseline-window',type=int,help='Legacy baseline pipeline count (default: 10)')
    report.add_argument('--growth-percent',type=float,help='Legacy relative growth threshold (default: 20)')
    report.add_argument('--growth-seconds',type=float,help='Legacy absolute growth threshold (default: 30)')
    report.add_argument('--min-baseline',type=int,help='Legacy minimum baseline observations (default: 3)')
    report.add_argument('--min-current',type=int,help='Legacy minimum current observations (default: 1)')
    report.add_argument('--output',type=Path,required=True)
    export=subs.add_parser('export',help='Export schema-backed LLM projection offline')
    export.add_argument('--report',type=Path,required=True);export.add_argument('--scope',choices=['overview'])
    export.add_argument('--job-type');export.add_argument('--window-id');export.add_argument('--attempt-ids',type=int,nargs='+')
    export.add_argument('--output',type=Path,required=True)
    render_p=subs.add_parser('render');render_p.add_argument('--report',type=Path,required=True);render_p.add_argument('--output',type=Path,required=True)
    render_p.add_argument('--language',choices=['en','ru'],help='HTML interface language (legacy default: en; v2 default: saved report language); source JSON is preserved')
    valid=subs.add_parser('validate');valid.add_argument('path',type=Path)
    args=parser.parse_args()
    if args.command=='collect':
        from report_collect import collect as gather
        selected=load(args.job_config) if args.job_config else []
        for item in args.job or []:
            if '/' not in item:raise ValueError('--job requires stage/name')
            stage,name=item.split('/',1);selected.append({'stage':stage,'name':name})
        result=gather(args.host,args.project,args.timezone,max_pages=args.max_pages,max_job_types=args.max_job_types,
                      concurrency=args.concurrency,job_selectors=selected or None,resume=load(args.resume) if args.resume else None,
                      cache=load(args.cache) if args.cache else None,cache_max_age_seconds=args.cache_max_age_seconds,
                      trace_bytes=args.trace_bytes,trace_lines=args.trace_lines,comparison_mode=args.comparison_mode,refs=args.ref)
        save(args.output,result)
    elif args.command=='report':
        snapshot=load(args.snapshot);baseline=load(args.baseline) if args.baseline else None;catalog=load(args.catalog) if args.catalog else None
        if args.legacy:
            if snapshot.get('schema_version')!='1.0.0':raise ValueError('--legacy requires v1 source')
            policy={key:getattr(args,arg) if getattr(args,arg) is not None else legacy.POLICY[key]
                    for key,arg in [('relative_growth_percent','growth_percent'),('absolute_growth_seconds','growth_seconds'),
                                    ('minimum_baseline_observations','min_baseline'),('minimum_current_observations','min_current')]}
            result=legacy.build_report(snapshot,baseline,windows=args.windows or [1,10],baseline_window=args.baseline_window if args.baseline_window is not None else 10,
                                       policy=policy,catalog=catalog,release_refs=args.release_refs)
            legacy.save(args.output,result,'report')
        else:
            if args.release_refs:raise ValueError('--release-refs requires --legacy; use --comparison-mode cross_ref --ref for v2')
            if any(getattr(args,key) is not None for key in ['windows','baseline_window','growth_percent','growth_seconds','min_baseline','min_current']):
                raise ValueError('Legacy window/threshold options require --legacy; v2 uses its versioned 32/64 and baseline policy')
            from report_calculate import build_report
            result=build_report(snapshot,baseline,catalog=catalog,guidance=load(args.guidance) if args.guidance else None,
                                language=args.language,comparison_mode=args.comparison_mode,refs=args.ref,generated_at=args.generated_at)
            save(args.output,result)
    elif args.command=='export':
        from report_export import export_report
        save(args.output,export_report(load(args.report),scope=args.scope,job_type=args.job_type,window_id=args.window_id,attempt_ids=args.attempt_ids))
    elif args.command=='render':render(load(args.report),args.output,args.language)
    else:
        value=load(args.path)
        if value.get('schema_version') in {'1.0.0','1.1.0'}:legacy.validate(value,value['kind'])
        else:validate(value)
        print('JSON Schema and semantic checks: OK')
