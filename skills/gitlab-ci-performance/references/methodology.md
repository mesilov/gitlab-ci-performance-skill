# Methodology 2.0.0

Source metadata remains schema 1.0.0. Bounded metadata/timings and the reviewed
report are schema 2.0.0; calculation/parser versions are 2.0.0. Historical
1.0/1.1 report rendering and same-ref calculations remain available. See
[methodology-v1.md](methodology-v1.md) for the original same-ref method.

## Retention, cohorts and coverage

Source collection preserves the available Jobs API history and pipeline metadata
with anchored keyset pagination. Deleted/bridge jobs cannot be recovered and API
collection is not atomic. Detail collection selects newest 64 job IDs per
(stage, name), across refs/outcomes, before individual metadata/trace GETs.
Explicit job/stage filters apply before those requests. At most R metadata and R
trace requests are made for R retained attempts; workers default 4, bounded 1–8.
Requests do not silently remove unavailable attempts.

32/64 visible windows count attempts, default 32. Pages are newest-first groups
of 32 within retained history (an older page may have fewer attempts); chart
presentation is chronological. Display/retained/source counts and dates differ.
Outcome counts on cards cover retained attempts. Source coverage and fresh/stale
metadata and trace availability are visible separately. A rerun has a different
job ID even inside one pipeline.

The independent exploratory overview baseline uses up to 10 preceding complete
successful jobs in successful pipelines, selecting the latest successful attempt
per pipeline/type and excluding the current attempt's pipeline. Missing totals
are excluded, counted, and not substituted from an older rerun in that pipeline.
Baseline can extend beyond visible/retained history without fetching those logs.
Export exact IDs, observation values and known/missing N. Latest attempt may have
any outcome; it requires an executed complete total for a numerical comparison.

Auto-select the largest positive absolute total delta with baseline N≥3. Break
ties by stage/name. Otherwise select the longest known latest total and make no
increase claim. This attention rule is distinct from the legacy same-ref
regression threshold (P 50 ≥20% and ≥30 s, baseline N≥3). Cross-ref observations
cannot prove comparable regression or cause. Context/CI/runner changes need a
separate investigation. An external same-ref baseline retains overlap checks.

## Timing and units

Queue is API queued_duration; execution is API job duration. Known total requires
both and actual execution. A skipped/manual/unstarted job is not a measured zero
execution even if an API field is zero. Known zero on an executed job stays zero.
Lifecycle is finished-created; remaining pre-start delay is started-created-queue,
with unknown cause. Queue is not every delay since job creation. Whole-job
execution is not a particular build command's duration. Original seconds remain
in JSON, including fractional precision.

In each visible window, complete successful job totals supply total median and
explicit sample IDs. Execution/queue medians have their own known/missing counts.
P 50/P 95 interpolate at (n-1)*p. Null is excluded; no known values means null,
not zero. Active/failed/canceled/not-run outcomes do not enter successful medians.

Largest complete displayed stack >300 s selects minutes; exactly 300 s uses seconds.
This unit applies to selected charts, summaries, tooltips, history, attempt and
all drill timings; overview cards show explicit units independently. A stack
shows wait above execution; gray wait is independent of individual job outcome.
The current pipeline's status does not color the job.

Queue spike: newest displayed executed attempt wait >max(30 s,3× median previous
successful known waits in that window), with at least 3 previous observations.
Export the rule, sample IDs, N, threshold and values. This detects a symptom,
not runner capacity or hardware causes.

## Evidence and priorities

See [trace-analysis.md](trace-analysis.md) for precision and availability.
Priorities use successful executed attempts only. For each category/run, union
complete known noncached intervals; overlapping ranges count once. Exclude
missing positions/durations and retain partial coverage counts per run. Parent
BuildKit operations are costs; children explain them and are never added again.
Runner script wall time is not ranked as an additional specific build category.

Rank up to 3 categories by median recorded elapsed cost, with measured/missing N.
Choose representative run closest to the category median, deterministically;
store its evidence IDs and duration separately from category median. A selected
20 s step must not replace a 100 s category cost. Different categories can overlap,
so their costs are not additive savings. Links/directions propose investigations;
no optimizer, causal proof or promised saving is inferred from a duration.

## Storage, validation and compatibility

Immutable jobs.json, metadata.json and timings.json reference source hashes and
project/timezone. Safe refreshed metadata is separate from parsed timing details.
A report validates their identities/full retained scope before filtering. Strict
schemas reject unknown fields, invalid versions, nonfinite/negative times and
broken IDs. Rendering verifies window/statistic/priority calculations and
baseline/latest values; JSON is escaped and source strings are rendered as text.

Hashes use UTF-8 JSON, ensure_ascii=false, sort_keys=true, indent 2 and newline.
Rendering from saved inputs/language is deterministic and makes no API requests.
Standalone HTML works through file:// when moved without sidecars, with no CDN,
server, analytics or token. JSON sidecars are needed for recalculation only.

1.0/1.1 reports use their preserved renderer; `report --legacy` retains 1.1
calculation. `--release-refs` selects the legacy exact-ref history route. Default
report generation makes explicit 2.0 results from schema 1 sources without changing
those sources. Unsupported calculation/parser versions require a compatible skill
or explicit re-analysis into new outputs, never silent semantic replacement.

Sources checked 2026-10-04: [Jobs API](https://docs.gitlab.com/api/jobs/),
[job logs](https://docs.gitlab.com/ci/jobs/job_logs/),
[BuildKit](https://docs.docker.com/build/buildkit/),
[cache guidance](https://docs.docker.com/build/cache/optimize/).
