---
name: gitlab-ci-performance
license: MIT
metadata:
  version: "0.1.0"
description: Use when a GitLab CI pipeline or job is slow, became slower, waits for runners or fails often, and the user wants to know where the time goes or what to speed up first. Also use when asked for a CI speed, duration or performance report of a GitLab project.
---

# GitLab CI performance

One command reads the recent pipelines of one branch and writes one HTML report:
how long a pipeline runs, which jobs take the time, what changed, and which steps
inside the slowest jobs are long. It only reads. It never changes CI, runners or
the repository.

## Run

Needs `python3` 3.9+ (no packages) and `glab` logged in to the GitLab host.

```sh
python3 <skill-dir>/scripts/ci_report.py --lang ru
```

Run it inside the project checkout: host and project come from the `origin`
remote, the branch is the default branch. Anything else is an option:

| Option | Meaning | Default |
|---|---|---|
| `--host`, `--project` | GitLab host and `group/project` path | `origin` remote |
| `--ref` | branch or tag | default branch |
| `--any-ref` | do not filter by ref | off |
| `--source` | one pipeline source: `push`, `schedule`, `merge_request_event`… | all |
| `--pipelines N` | finished pipelines to read, 1–100 | 30 |
| `--logs N` | read the log of the N slowest jobs | 5 |
| `--lang en\|ru` | report language; use the user's language | `en` |
| `--out DIR` | output directory | `./ci-report` |
| `--from data.json` | rebuild the report from saved data, without GitLab | |

It writes `report.html` (one file, opens from disk, no network) and `data.json`
(what was read), and prints the same findings as text.

## Answer the user

1. Give the path to `report.html`.
2. Repeat the printed "Where to look first" items. They are measured facts.
3. If the user asks what to do: read `.gitlab-ci.yml`, connect each item to its
   job, and propose at most three changes, largest time first. Say which part is
   measured and which part is your assumption. The table shows where to look.
4. Change CI, runners or caches only when the user asks for that change.

| The report shows | Look at | Documentation |
|---|---|---|
| Long "Restore cache" or "Save cache" | cache key, paths and size; `policy: pull` in jobs that only read the cache | [Caching](https://docs.gitlab.com/ci/caching/) |
| Long "Get sources (git)" | clone depth and Git strategy | [Configuring runners](https://docs.gitlab.com/ci/runners/configure_runners/) |
| Long "Download artifacts" or "Upload artifacts" | artifact paths and size; jobs that download artifacts they do not use | [Pipeline efficiency](https://docs.gitlab.com/ci/pipelines/pipeline_efficiency/) |
| Long "Prepare executor" | image size and pull policy | [Speed up job execution](https://docs.gitlab.com/runner/configuration/speed_up_job_execution/) |
| Long dependency install (`composer install`, `npm ci`, `pip install`…) | package cache; an image with dependencies already inside | [Caching](https://docs.gitlab.com/ci/caching/) |
| Long `RUN`, `COPY` or "exporting" steps of a Docker build | layer order, `.dockerignore`, build cache between pipelines | [Docker cache](https://docs.docker.com/build/cache/optimize/), [Build context](https://docs.docker.com/build/concepts/context/) |
| Jobs wait for a runner | number of runners, `concurrent`, tags | [Runner configuration](https://docs.gitlab.com/runner/configuration/advanced-configuration/) |
| In the latest pipeline, a job starts late for no reason | `needs:` to start it earlier; split a long test job | [needs](https://docs.gitlab.com/ci/yaml/needs/) |
| A job fails often | unstable tests. `retry` hides the cost, it does not remove it | |

## What the numbers mean

- **Pipeline run time** is the time when at least one job was running. Retries
  count. Runner waits and pauses before manual jobs do not.
- **Medians** use successful runs only.
- **Change** compares the newest successful runs (up to 10) with the earlier
  ones. It is marked only above 20% and 30 seconds. It needs 6 successful runs.
- **Steps** come from the log of one run: the latest successful run of each of
  the slowest jobs. They are an example, not an average.
- A job that builds several Docker images marks its steps `build 1:`, `build 2:`…
  in the order of the builds.
- Commands (`$ …`) have a time only when the log has timestamps. That is the
  default in current GitLab; see `FF_TIMESTAMPS` in
  [Job logs](https://docs.gitlab.com/ci/jobs/job_logs/).

## Limits

- One ref per report, or all refs together with `--any-ref`. For release tags
  use `--any-ref --source push`. For merge request pipelines use
  `--any-ref --source merge_request_event`.
- Jobs of child and downstream pipelines are not read.
- The report contains job names, command lines and links from the project.
  Check it before sharing outside the team. Do not commit `ci-report/`.
- To compare before and after a change, write the second report to another
  `--out` directory.

## Problems

| Message | Fix |
|---|---|
| `glab is not installed`, `401`, "not JSON" | `glab auth login --hostname <host>`, then `glab auth status` |
| `No finished pipelines found` | wrong ref: pass `--ref`, or `--any-ref` |
| `Only N of the last M finished pipelines ran on …`, or the report has only a few short jobs | CI runs on tags, other branches or merge requests: run again with `--any-ref`, and `--source push` to leave out manual runs |
| A job has phases but no commands | its log has no timestamps, or the job only runs a Docker build |
| "The log of this job was not read" | raise `--logs` |
