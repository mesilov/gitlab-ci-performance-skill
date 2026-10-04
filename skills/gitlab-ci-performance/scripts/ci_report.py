#!/usr/bin/env python3
"""Read-only GitLab CI snapshots, deterministic comparisons and offline HTML."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
POLICY = {"relative_growth_percent": 20.0, "absolute_growth_seconds": 30.0,
          "minimum_baseline_observations": 3, "minimum_current_observations": 1}
ACTIVE = {"created", "pending", "preparing", "running", "waiting_for_resource"}


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def load(path):
    def reject(value):
        raise ValueError("Non-finite JSON value")
    return json.loads(Path(path).read_text(), parse_constant=reject)


def validate(value, kind):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        raise ValueError("Установите requirements.txt в локальную venv проекта") from None
    schema = load(ROOT / "schemas" / f"{kind}.schema.json")
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        error = errors[0]
        raise ValueError(f"JSON Schema: {'.'.join(map(str, error.path)) or 'root'}: {error.validator}")
    jobs = value["jobs"]
    pipelines = value["pipelines"]
    if len({j["id"] for j in jobs}) != len(jobs):
        raise ValueError("Повторяющийся job_id")
    pmap = {p["id"]: p for p in pipelines}
    if len(pmap) != len(pipelines):
        raise ValueError("Повторяющийся pipeline_id")
    for item in jobs + pipelines:
        for key in ("duration_seconds", "queued_seconds"):
            x = item[key]
            if x is not None and not math.isfinite(x):
                raise ValueError("Non-finite timing")
        for key in ("created_at", "started_at", "finished_at"):
            if item[key] is not None and timestamp(item[key]).utcoffset() is None:
                raise ValueError("Date must have timezone")
    for job in jobs:
        if job["pipeline_id"] not in pmap or pmap[job["pipeline_id"]]["ref"] != job["ref"]:
            raise ValueError("Job/pipeline relation mismatch")


def save(path, value, kind=None):
    if kind:
        validate(value, kind)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"Файл уже существует: {path}; выберите новый output")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write(encoded(value))
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def request(host, endpoint):
    result = subprocess.run(["glab", "api", "--hostname", host, "--method", "GET",
                             "--include", endpoint], capture_output=True, text=True,
                            timeout=60)
    if result.returncode:
        # Do not expose arbitrary stderr/body or credentials from the transport.
        raise ValueError(f"glab GET failed: {endpoint.split('?')[0]} (exit {result.returncode})")
    headers, separator, body = result.stdout.replace("\r\n", "\n").partition("\n\n")
    if not separator:
        raise ValueError("glab response has no HTTP header boundary")
    try:
        return headers, json.loads(body)
    except json.JSONDecodeError:
        raise ValueError("glab returned invalid JSON") from None


def next_page(headers, host, project_id):
    match = re.search(r'<([^>]+)>;\s*rel="next"', headers, re.I)
    if not match:
        return None
    u = urlsplit(match.group(1))
    if (u.scheme != "https" or u.netloc != host or u.username or u.password or
            u.path != f"/api/v4/projects/{project_id}/jobs" or u.fragment or
            re.search(r"token|authorization", u.query, re.I)):
        raise ValueError("Небезопасный pagination target")
    return u.path.removeprefix("/api/v4/") + ("?" + u.query if u.query else "")


def project_job(j):
    runner = j.get("runner")
    return {"id": j["id"], "pipeline_id": j["pipeline"]["id"], "name": j["name"],
            "stage": j["stage"], "ref": j["ref"], "status": j["status"],
            "allow_failure": bool(j.get("allow_failure", False)),
            "created_at": j["created_at"], "started_at": j.get("started_at"),
            "finished_at": j.get("finished_at"), "duration_seconds": j.get("duration"),
            "queued_seconds": j.get("queued_duration"), "failure_reason": j.get("failure_reason"),
            "runner": None if not runner else {"id": runner["id"], "description": runner.get("description") or ""},
            "web_url": j["web_url"]}


def project_pipeline(p):
    return {"id": p["id"], "ref": p["ref"], "sha": p["sha"], "status": p["status"],
            "source": p.get("source") or "unknown", "created_at": p["created_at"],
            "started_at": p.get("started_at"), "finished_at": p.get("finished_at"),
            "duration_seconds": p.get("duration"), "queued_seconds": p.get("queued_duration"),
            "web_url": p["web_url"]}


def collect(host, project_path, display_timezone, max_pages=100):
    if not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]+)?", host):
        raise ValueError("Некорректный hostname")
    ZoneInfo(display_timezone)
    started = now()
    _, p = request(host, "projects/" + quote(project_path, safe=""))
    _, version = request(host, "version")
    project = {"id": p["id"], "path": p["path_with_namespace"], "host": host,
               "web_url": p["web_url"], "default_branch": p["default_branch"]}
    endpoint = f"projects/{p['id']}/jobs?per_page=100&pagination=keyset&order_by=id&sort=desc"
    seen, visited, jobs = set(), set(), []
    anchor, pages = None, 0
    while endpoint:
        if pages >= max_pages or endpoint in visited:
            raise ValueError("Pagination limit/cycle: неполная выгрузка не сохраняется")
        visited.add(endpoint)
        headers, batch = request(host, endpoint)
        if not isinstance(batch, list):
            raise ValueError("Jobs API returned non-array")
        if anchor is None and batch:
            anchor = max(j["id"] for j in batch)
        for j in batch:
            if anchor is not None and j["id"] > anchor:
                continue
            if j["id"] in seen:
                raise ValueError("Jobs API returned duplicate ID")
            seen.add(j["id"])
            jobs.append(project_job(j))
        pages += 1
        print(f"Jobs: {len(jobs)}; pages: {pages}", flush=True)
        endpoint = next_page(headers, host, p["id"])
    ids = sorted({j["pipeline_id"] for j in jobs}, reverse=True)

    def fetch_pipeline(pid):
        _, raw = request(host, f"projects/{p['id']}/pipelines/{pid}")
        return project_pipeline(raw)

    with ThreadPoolExecutor(max_workers=4) as executor:
        pipelines = list(executor.map(fetch_pipeline, ids))
    glab = subprocess.run(["glab", "version"], capture_output=True, text=True, timeout=10)
    result = {"schema_version": VERSION, "kind": "jobs", "collection_started_at": started,
              "collected_at": now(), "timezone": display_timezone, "project": project,
              "source": {"transport": "glab", "glab_version": glab.stdout.splitlines()[0] if glab.stdout else "unknown",
                         "gitlab_version": version["version"], "anchor_max_job_id": anchor, "pages": pages,
                         "complete_available_history": True,
                         "limitations": ["Deleted jobs cannot be recovered", "API collection is not an atomic transaction",
                                         "Bridge/trigger jobs are outside project Jobs API"]},
              "jobs": sorted(jobs, key=lambda x: x["id"], reverse=True), "pipelines": pipelines}
    validate(result, "jobs")
    return result


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def metric(values):
    known = [v for v in values if v is not None]
    return {"known": len(known), "missing": len(values) - len(known),
            "sum_seconds": sum(known) if known else None,
            "p50_seconds": percentile(known, .5), "p95_seconds": percentile(known, .95),
            "max_seconds": max(known) if known else None}


def cohort(jobs):
    successful = [j for j in jobs if j["status"] == "success"]
    runs = Counter(j["pipeline_id"] for j in jobs)
    lifecycle = [(timestamp(j["finished_at"]) - timestamp(j["created_at"])).total_seconds()
                 if j["finished_at"] else None for j in successful]
    return {"attempts": len(jobs), "rerun_attempts": sum(max(0, n - 1) for n in runs.values()),
            "successful_attempts": len(successful), "status_counts": dict(Counter(j["status"] for j in jobs)),
            "execution": metric([j["duration_seconds"] for j in successful]),
            "queue": metric([j["queued_seconds"] for j in successful]), "lifecycle": metric(lifecycle)}


def compare(current, baseline, policy, overlap=False):
    c, b = current["p50_seconds"], baseline["p50_seconds"]
    delta = c - b if c is not None and b is not None else None
    relative = delta / b * 100 if delta is not None and b > 0 else None
    if overlap:
        status = "overlap"
    elif (current["known"] < policy["minimum_current_observations"] or
          baseline["known"] < policy["minimum_baseline_observations"]):
        status = "insufficient_data"
    elif delta > 0 and delta >= policy["absolute_growth_seconds"] and (b == 0 or relative >= policy["relative_growth_percent"]):
        status = "regressed"
    elif delta < 0 and -delta >= policy["absolute_growth_seconds"] and (b == 0 or -relative >= policy["relative_growth_percent"]):
        status = "improved"
    else:
        status = "stable"
    return {"status": status, "current_seconds": c, "baseline_seconds": b,
            "delta_seconds": delta, "delta_percent": relative}


def period(pipelines, jobs):
    times = [p["created_at"] for p in pipelines]
    return {"pipeline_ids": [p["id"] for p in pipelines],
            "from": min(times, key=timestamp) if times else None,
            "to": max(times, key=timestamp) if times else None, "attempts": len(jobs)}


def build_report(snapshot, baseline=None, windows=(1, 10), baseline_window=10, policy=None, catalog=None):
    validate(snapshot, "jobs")
    if baseline:
        validate(baseline, "jobs")
        for key in ("host", "id", "path"):
            if baseline["project"][key] != snapshot["project"][key]:
                raise ValueError("Baseline belongs to different host/project")
        if timestamp(baseline["collected_at"]) > timestamp(snapshot["collected_at"]):
            raise ValueError("Baseline is newer than current snapshot")
    if baseline_window < 1 or not windows or any(w < 1 for w in windows):
        raise ValueError("Размер окна должен быть положительным")
    policy = dict(POLICY if policy is None else policy)
    catalog = catalog or {}
    descriptions = catalog.get("jobs", {}) if catalog.get("project") == snapshot["project"]["path"] else {}
    views = []
    refs = sorted({p["ref"] for p in snapshot["pipelines"]}) or [snapshot["project"]["default_branch"] or ""]
    for ref_name in refs:
        all_p = sorted([p for p in snapshot["pipelines"] if p["ref"] == ref_name], key=lambda p: p["id"], reverse=True)
        successes = [p for p in all_p if p["status"] == "success"]
        for window in sorted(set(windows)):
            current_p = successes[:window]
            if baseline:
                baseline_p = sorted([p for p in baseline["pipelines"] if p["ref"] == ref_name and p["status"] == "success"],
                                    key=lambda p: p["id"], reverse=True)[:baseline_window]
            else:
                baseline_p = successes[window:window + baseline_window]
            current_ids, baseline_ids = {p["id"] for p in current_p}, {p["id"] for p in baseline_p}
            overlap = sorted(current_ids & baseline_ids)
            current_jobs = [j for j in snapshot["jobs"] if j["pipeline_id"] in current_ids]
            baseline_jobs = [j for j in (baseline or snapshot)["jobs"] if j["pipeline_id"] in baseline_ids]
            keys = sorted({(j["stage"], j["name"]) for j in current_jobs + baseline_jobs})
            groups = []
            for stage, name in keys:
                cj = [j for j in current_jobs if j["name"] == name and j["stage"] == stage]
                bj = [j for j in baseline_jobs if j["name"] == name and j["stage"] == stage]
                c, b = cohort(cj), cohort(bj)
                execution = compare(c["execution"], b["execution"], policy, bool(overlap))
                queue = compare(c["queue"], b["queue"], policy, bool(overlap))
                if not overlap and (not cj or not bj):
                    for change in (execution, queue):
                        change["status"] = "new_job" if cj else "missing_job"
                purpose = descriptions.get(name, {"description": "Назначение не описано в проверенном каталоге.",
                                                   "source_url": None, "verified_at": None})
                groups.append({"name": name, "stage": stage, "ref": ref_name, "purpose": purpose,
                               "current": c, "baseline": b, "execution_change": execution, "queue_change": queue,
                               "drivers": [key for key, result in [("execution", execution), ("queue", queue)] if result["status"] == "regressed"],
                               "latest_attempt_id": max((j["id"] for j in cj), default=None)})
            regressions = sum(bool(g["drivers"]) for g in groups)
            insufficient = sum(any(g[k]["status"] in {"insufficient_data", "new_job", "missing_job", "overlap"}
                                   for k in ("execution_change", "queue_change")) for g in groups)
            views.append({"ref": ref_name, "window": window, "baseline_window": baseline_window,
                          "current_period": period(current_p, current_jobs), "baseline_period": period(baseline_p, baseline_jobs),
                          "overlap_pipeline_ids": overlap, "latest_pipeline": all_p[0] if all_p else None,
                          "groups": groups, "regression_count": regressions, "insufficient_count": insufficient,
                          "situation": "attention" if regressions else "insufficient_data" if insufficient or not groups else "no_regression"})
    result = {"schema_version": VERSION, "calculation_version": VERSION, "kind": "report", "generated_at": now(),
              "timezone": snapshot["timezone"], "project": snapshot["project"],
              "inputs": {"snapshot_sha256": digest(snapshot), "baseline_sha256": digest(baseline) if baseline else None,
                         "snapshot_collected_at": snapshot["collected_at"], "baseline_collected_at": baseline["collected_at"] if baseline else None,
                         "comparison_mode": "snapshot" if baseline else "historical_windows"},
              "method": {"timing_job_status": "success", "timing_pipeline_status": "success",
                         "percentile": "linear-interpolation-(n-1)*p", "group_key": "project+ref+stage+job_name", "policy": policy},
              "snapshot_summary": {"attempts": len(snapshot["jobs"]), "pipelines": len(snapshot["pipelines"]),
                                   "status_counts": dict(Counter(j["status"] for j in snapshot["jobs"])),
                                   "active_attempts": sum(j["status"] in ACTIVE for j in snapshot["jobs"])},
              "views": views, "jobs": snapshot["jobs"], "pipelines": snapshot["pipelines"]}
    validate(result, "report")
    return result


def render(report, output):
    validate(report, "report")
    payload = json.dumps(report, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = (ROOT / "assets" / "report.html").read_text()
    html = template.replace("__REPORT_DATA__", payload)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("HTML output уже существует")
    with output.open("x") as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description="GitLab CI: snapshots → comparison JSON → offline HTML")
    commands = parser.add_subparsers(dest="command", required=True)
    collect_p = commands.add_parser("collect")
    collect_p.add_argument("--host", required=True)
    collect_p.add_argument("--project", required=True)
    collect_p.add_argument("--timezone", default="UTC")
    collect_p.add_argument("--max-pages", type=int, default=100)
    collect_p.add_argument("--output", type=Path, required=True)
    report_p = commands.add_parser("report")
    report_p.add_argument("--snapshot", type=Path, required=True)
    report_p.add_argument("--baseline", type=Path)
    report_p.add_argument("--windows", type=int, nargs="+", default=[1, 10])
    report_p.add_argument("--baseline-window", type=int, default=10)
    report_p.add_argument("--growth-percent", type=float, default=POLICY["relative_growth_percent"])
    report_p.add_argument("--growth-seconds", type=float, default=POLICY["absolute_growth_seconds"])
    report_p.add_argument("--min-baseline", type=int, default=POLICY["minimum_baseline_observations"])
    report_p.add_argument("--min-current", type=int, default=POLICY["minimum_current_observations"])
    report_p.add_argument("--catalog", type=Path)
    report_p.add_argument("--output", type=Path, required=True)
    render_p = commands.add_parser("render")
    render_p.add_argument("--report", type=Path, required=True)
    render_p.add_argument("--output", type=Path, required=True)
    validate_p = commands.add_parser("validate")
    validate_p.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "collect":
        save(args.output, collect(args.host, args.project, args.timezone, args.max_pages), "jobs")
    elif args.command == "report":
        policy = {"relative_growth_percent": args.growth_percent, "absolute_growth_seconds": args.growth_seconds,
                  "minimum_baseline_observations": args.min_baseline, "minimum_current_observations": args.min_current}
        result = build_report(load(args.snapshot), load(args.baseline) if args.baseline else None,
                              args.windows, args.baseline_window, policy, load(args.catalog) if args.catalog else None)
        save(args.output, result, "report")
    elif args.command == "render":
        render(load(args.report), args.output)
    else:
        data = load(args.path)
        if data.get("kind") not in {"jobs", "report"}:
            raise ValueError("Unknown artifact kind")
        validate(data, data["kind"])
        print("JSON Schema и связи IDs: OK")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)
