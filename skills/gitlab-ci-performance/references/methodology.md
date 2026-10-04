# Methodology version 1.1.0

JSON Schema 2020-12; report schema_version/calculation_version 1.1.0; jobs 1.0.0. Sources:
[Jobs API](https://docs.gitlab.com/api/jobs/),
[Pipelines API](https://docs.gitlab.com/api/pipelines/),
[glab api](https://docs.gitlab.com/cli/api/),
[JSON Schema](https://json-schema.org/draft/2020-12).

## History and filters

Collection preserves the available project Jobs API history, unique job IDs,
and pipeline details. Keyset pagination is limited to 100 pages by default;
reaching the limit causes an error rather than a successful but incomplete report.
An anchor maximum ID excludes newer jobs that appear during collection. Statuses
may change during collection: this is not an atomic transaction. Deleted jobs and
bridge/trigger jobs cannot be recovered. There is no incremental cache in v1:
a repeated GET run refreshes current statuses and creates a new snapshot.

Timing comparisons use only SUCCESS jobs within SUCCESS pipelines of the same
ref. All attempts/statuses within a pipeline are preserved, including additional
attempts of the same job. An additional attempt is not proof of an automatic retry
or a flaky test. All snapshot statuses and the latest pipeline are shown separately.
Job grouping: host/project/ref/stage/name.

Mode 1: the latest successful pipeline versus up to 10 previous successful
pipelines. Mode 10: up to 10 latest pipelines versus up to 10 previous ones.
With an external baseline, its latest successful pipelines are selected independently:
intersecting IDs mark the comparison as overlap and prohibit a regression conclusion.
Host/project and schema version must match. Windows are determined by pipeline IDs
in descending order; the report preserves actual IDs, from/to, and N.

## Timings

- execution = API job duration; queue = API queued_duration.
- lifecycle = job finished_at - created_at, only when finish is known.
- execution+queue does not necessarily equal lifecycle.
- started_at-created_at-queued_duration is the remaining delay before start;
  its causes (stages/needs/manual/resource locks/other) cannot be established from metadata.
- Pipeline duration is the pipeline's own API field, not the sum of job durations.
- The top stacked chart shows pipeline duration + pipeline queued_duration for
  the latest 20 successful pipelines of the selected ref. Null is not plotted as a known
  zero; a label indicates missing components. This is not the full lifecycle.
  Pipeline queued_duration is the wait before the first start, not the sum of
  individual job queues. These semantics were checked against the
  [GitLab pipeline model](https://gitlab.com/gitlab-org/gitlab/-/blob/master/app/models/ci/pipeline.rb)
  and [duration calculation](https://gitlab.com/gitlab-org/gitlab/-/blob/master/lib/gitlab/ci/pipeline/duration.rb);
  GitLab versions may differ, and original API fields are preserved without substitution.

Null is excluded from aggregates while retaining missing N. When no values are known,
sum/P50/P95/max = null. Sum reflects job time consumed, not the developer's elapsed
wait. P50/P95 use sorted values with linear interpolation at index `(n-1)*p`.
Multiple attempts are counted separately; N attempt counts and pipeline counts may differ.

## Regressions and uncertainty

By default, a P50 regression requires both growth >=20% and >=30 seconds,
baseline known N>=3, and current known N>=1. Thresholds are controlled through the
CLI and recorded in the report; this is an initial configurable policy, not an
accepted SLO. With a zero baseline, percent=null; positive growth is checked against
the absolute threshold. Improved uses a symmetric check, but the UI does not color
improvements. P95 is shown for checking tails; policy v1 classifies P50.

With N=1, this is an observation of a specific pipeline, not an established trend.
Sparse samples, new/missing jobs, and overlap remain explicit. Long queues show a
symptom but do not prove insufficient CPU/RAM or a specific runner cause.
Changes to pipeline source, job script/image/cache/runner may affect the comparison;
causal attribution requires a separate investigation. Ref matches automatically;
other contexts are preserved in the snapshot and available for analysis.

## Storage and viewing

`jobs.json` is a safe source projection; `report.json` contains derived metrics and
differences with source hashes. Each run uses a new directory. JSON serialization
for hashes: UTF-8, ensure_ascii=false, sort_keys=true, indent=2, newline.
Reports are recalculated with a helper of the same calculation_version; a methodology
change requires a version bump and recalculation of both snapshots. The HTML embeds
JSON, CSS/JS/SVG, works offline, and contains no token/CDN/analytics.
Open report.html directly through file://; no server is needed.
Separate JSON files are needed for recalculation, not for loading the page.
The skill does not create a schedule itself; a future scheduled run must operate
independently of the CI queue being monitored and report stale collection.

## History across refs

The optional `--release-refs` mode is documented in [release-history.md](release-history.md).
Same-ref comparison remains the default; changes across selected releases are
exploratory observations. Legacy 1.0.0 reports remain renderable.
