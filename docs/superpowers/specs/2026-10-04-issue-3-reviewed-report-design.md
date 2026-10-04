# Issue #3: reviewed report and versioned skill delivery

Status: proposed implementation design; implementation and release are pending.
Date: 2026-10-04. Target: skill release `v2.0.0`.
Source of requirements: [issue #3](https://github.com/mesilov/gitlab-ci-performance-skill/issues/3).

## Goal and scope

An installed skill generates the reviewed job-focused report through maintained
commands: safe source collection → bounded detail collection → derived report →
standalone HTML. It requires no repository-specific Python/JavaScript scripts or
manual HTML patches. The final issue requirements supersede earlier prototypes.

Deliver all requirements of #3, including integration with #1 (cross-ref history)
and #2 (English/Russian). Workflow analysis and LLM exports from other issues are
outside this change. Private prototype snapshots, identifiers, traces and logs
are evidence for local investigation only and are not distributed.

## Current state and implementation choice

The current helper combines collection, calculations and rendering in
`skills/gitlab-ci-performance/scripts/ci_report.py`. Source/report schemas are
version 1.0.0. The existing report compares successful pipelines within one ref,
does not collect traces, and shows a pipeline-level stack. There is no existing
GitHub release or version tag at the time of this investigation.

Three approaches were considered:

1. **Extend the CLI with focused modules and preserve legacy rendering
   (recommended).** Reuse authentication, projections, hashing and immutable
   writes. Separate trace parsing and reviewed-report calculation from v1 cohort
   calculation. This adds a small compatibility surface but avoids changing old
   snapshot semantics.
2. Replace the helper and old schema entirely. A smaller long-term code surface,
   but forces users to migrate existing snapshots and risks losing same-ref
   comparisons during the rewrite.
3. Package the local prototype scripts. Fast initial visual parity, but retains
   project assumptions and browser-only calculations; does not meet reproducible
   generic collection, validation or release acceptance.

The issue fixes the visual behavior already; no new visual direction is needed.

## Maintained files and boundaries

All runtime resources live inside the distributed skill directory.

| File | Responsibility |
| --- | --- |
| `scripts/ci_report.py` | CLI, version dispatch, immutable artifact I/O and render orchestration |
| `scripts/collection.py` | Existing safe source collection plus bounded metadata/trace requests |
| `scripts/trace_parser.py` | Pure allowlisted parser: bytes + attempt metadata → compact timing evidence |
| `scripts/history.py` | Retention, attempt identity, baseline eligibility and default selection |
| `scripts/priorities.py` | Interval unions, successful cost rankings and representative evidence |
| `scripts/reviewed_report.py` | Versioned report assembly, window summaries and provenance |
| `assets/report.html` | Reviewed interface consuming validated derived values |
| `assets/report-v1.html` | Preserved rendering for existing 1.0.0 reports |
| `schemas/*` | Versioned source, bounded metadata, trace-detail and report contracts |
| `references/methodology.md` | Retention, baseline, availability, timing and priority policies |
| `references/trace-analysis.md` | Parser provenance, supported log formats, cache and limitations |

Schema reuse uses local references resolved inside the installed skill. Validation
must not fetch remote schemas or require the repository checkout.

## CLI and artifacts

The documented complete workflow is:

```sh
python ci_report.py collect --host gitlab.example.com --project group/service \
  --timezone UTC --output run/jobs.json
python ci_report.py collect-details --snapshot run/jobs.json \
  --output-dir run/details --workers 4
python ci_report.py report --snapshot run/jobs.json \
  --details run/details --catalog catalog.json --output run/report.json
python ci_report.py render --report run/report.json \
  --language en --output run/report.html
```

Paths in these examples are relative to the caller; `ci_report.py` is invoked at
its installed location. UTC remains the explicit documented timezone default;
English remains the report-language default. `--language ru` translates interface
text, units, statuses, help and empty states while preserving original source
strings. Language selection changes presentation, not calculated values.

`--job` and `--stage` can restrict analyzed job types explicitly. Absence means
all discovered `(stage, name)` types. No implicit release-tag regex or fixed job
names. A catalog records purpose, configuration URL/ref/hash and verification
date; unverified purposes remain unknown.

Source `jobs.json` remains immutable. `details/metadata.json` contains fresh safe
metadata and collection states for every retained ID. `details/timings.json`
contains compact derived trace evidence separately. Both reference the source
hash, project identity, selected types and retained IDs. `report.json` references
all input hashes and carries the summaries consumed by the interface. No raw
trace text enters these artifacts.

`collect-details` defaults to reading traces for its bounded retained scope,
which is stated explicitly in SKILL.md. `--no-traces` records `disabled` states
instead of pretending logs were unavailable. Optional `--trace-cache <dir>`
stores raw traces privately with owner-only permissions and a host/project/job
identity manifest; `--reuse-cache` must be explicit. Running/partial cached traces
are refreshed. Cache use, original fetch time, current analysis time, source hash
and parser version remain visible. No cache is packaged or published.

## Retention, coverage and request bounds

- Use job IDs as attempt identity. Select newest 64 IDs per `(stage, name)` across
  refs and outcomes before making trace requests. Reruns remain distinct.
- Refresh safe metadata for every selected ID. Refresh failure retains the
  snapshot projection with an explicit stale/unavailable state and safe error
  class; it is never presented as fresh metadata.
- Fetch traces only for those IDs with execution and no confirmed erasure.
  Bound workers to 1–8, default 4; use request timeouts and record failures per
  attempt. Do not print transport bodies or stderr containing private material.
- Without cache, detail requests are at most `R` metadata plus `R` trace GETs,
  where `R <= 64 * analyzed_job_types`; requests skipped for not-run/erased
  attempts reduce that count. Record actual attempted/succeeded counts and bytes.
- Preserve source coverage separately from retained and displayed coverage.
  Existing anchored, paginated source collection remains available. No claim that
  deleted/unfetched jobs never existed. Detail failures do not silently remove IDs.
- Distinguish `not_run`, `empty`, `erased`, `unavailable`, `partial`, `available`
  and explicitly `disabled`. Partial section/log recording is separate from job
  outcome: failure does not automatically mean the retrieved log is truncated.
- Bound trace processing with a configurable byte limit, default 32 MiB per job.
  Exceeding the limit records partial coverage and processed/source byte counts.
  Stream to the limit rather than buffering unbounded output. Report compact
  evidence counts, truncation and payload bytes without silently dropping data.

## History and baseline calculations

Offer only 32/64 attempts, with 32 default. Older/Newer/Latest navigate within
retained attempts; clamp to actual data and show dates and counts. The chosen
window identifies explicit attempt IDs so every panel uses the same scope.

Keep the established same-ref workflow separately accessible. Its successful
job/successful pipeline eligibility and cohort-overlap safeguards remain intact.
Mixed-ref history is labeled exploratory; it is not evidence of a comparable
regression. Export exact baseline IDs, eligibility and missing counts.

For overview attention, compare the latest attempt's complete total with up to
10 preceding eligible complete successful observations, independently of the
displayed window. Select the largest positive absolute delta with baseline N≥3.
The exploratory cohort uses the latest successful attempt per pipeline/type;
failed, canceled, not-run and incomplete totals are ineligible. Preserve source
observations outside the retained 64 for this baseline without fetching their
traces. If no increase qualifies, select the longest known latest total and
claim no increase. Resolve ties deterministically by `(stage, name)`.

Execution is the job API duration; queue is the job API queued duration. A known
total requires both and an executed attempt. Not-run states never become measured
zero execution, even if a source field contains zero. Keep lifecycle and remaining
pre-start delays separate. Commit SHA comes from safe job/pipeline metadata.

For each displayed window, compute successful complete-total median and sample
IDs. Execution/queue medians use successful runs with independently known values,
with separate known/missing N. Queue spike rule for the newest displayed attempt:
at least 3 preceding successful known queue observations in that window, and wait
strictly greater than `max(30 seconds, 3 × preceding queue median)`. Label it a
queue observation, never proof of capacity limits. Publish the rule and sample.

## Trace evidence and timing precision

Parse runner section markers, ISO timestamps, BuildKit plain progress and CR/ANSI
progress redraws. Use fixed labels for section/command/operation types; do not
serialize arbitrary command arguments, output or Dockerfile instructions.
Unknown operations retain IDs/line references and a generic label.

Build boundaries must distinguish a new build from a repeated `#1` progress
frame. Keep step IDs local to build IDs. Deduplicate repeated progress records
and export/unpack substeps, including missing timestamps and incomplete sections.
When a boundary cannot be established reliably, mark ambiguous coverage rather
than merge independent builds into false precision.

Record durations and positions separately:

- Runner section duration: recorded marker timestamps, whole-second precision.
- BuildKit duration: reported floating-point duration; position inferred from
  timestamped completion when available, with that positional provenance stated.
- Command interval: estimated interval between successive timestamped command
  records or a known script end; no claim of independently profiled runtime.
- Missing endpoints, cached operations and partial operations retain null
  duration/coverage. Cached is not a measured zero-cost operation.

Image builds have generic stable labels unless an explicitly verified image
catalog maps evidence safely. Show known span bounds, whether push is covered,
and unknown push coverage. A build's span/operation costs are not job wall time.
Parallel operations overlap. Children explain their parent's cost and are not
added to it. Preserve trace hash, original line numbers, parser version and source
job/log links for evidence navigation.

## What to improve first

Place the summary above overview cards; update it on job/window change. Show
scope, dates, successful sample N, execution/queue medians and the queue spike.
Rank at most three categories using successful attempts with known noncached
intervals: export/unpack, context/copy, base image, dependencies, builder startup,
runner phases and queue as evidence permits.

For each category/run, compute elapsed cost as a union of its recorded intervals,
counting overlap once. Missing positions do not become exact union costs. Mark
partial coverage and known/missing N. Categories are separate observations and
must not be summed as promised savings. Fixed investigation directions link to
authoritative guidance and distinguish measurements from proposed optimizations.

Store `median_cost_seconds` independently of the representative operation's
duration. Pick evidence from a measured run closest to the category median,
with deterministic ID tie-breaking. Evidence contains attempt/build/operation or
phase IDs; Inspect run changes selection and focuses that evidence. A cost of
100 seconds must remain 100 even if its representative step lasts 20 seconds.
Show insufficient-data states when no measured successful category exists.

## Interface

Repository overview cards show verified purpose, latest total, baseline/delta and
outcome counts with explicit retained/source scope. Only the selected job appears
below. Job changes reset/clamp attempt and evidence selection consistently.

One SVG stacked bar per attempt: gray queue above execution. Execution is green
for success, red for failure and gray for canceled; other states have explicit
text and legend. Executed bars have no decorative circles. Not-run attempts have
a hollow marker. Partial measured components are shown honestly without an
invented full stack. Median line is dashed and successful-complete-only.

Units depend on the largest known complete stack in the displayed window:
exactly 300 seconds uses seconds; strictly greater uses minutes. Apply the unit
to all selected summaries, charts, tooltips, history, detail and drill-down
timings, including runner phases. Overview card values have their own explicit
units. JSON always preserves original seconds and precision.

Bars adapt to chart width with sparse X labels; no horizontal chart scrolling
at 320 px or larger. History tables may scroll independently. Use native buttons
or accessible SVG selection controls with keyboard activation and visible focus.
Keep job, attempt and image/operation selection states distinct. Blue highlights
drill selection; overview attention has its own indicator.

Drill-down shows identity, ref, outcome, dates, SHA, runner, queue/execution/total,
GitLab links, sections, image operations and estimated command intervals. Include
responsive interval timelines, substeps, line ranges, precision/provenance,
cached/unknown states and honest availability messages.

## Contracts, reproducibility and version compatibility

Introduce schema/calculation/parser version 2.0.0 for the new semantics; pin them
in artifacts and distributed metadata. Add strict contracts with nullability,
finite nonnegative timing checks, unique IDs, referential integrity, retention
bounds, evidence membership and allowed label categories. Validate before saving
and rendering; reject unsupported versions with an actionable message.

Preserve 1.0.0 schemas and renderer. Existing 1.0.0 reports render with their
original semantics. New calculations from old jobs snapshots are explicitly
2.0.0 results, with original hash/version recorded; no rewriting old snapshots.
Recalculating v2 timing data with a different parser/calculation version requires
an explicit migration/re-analysis and a new output path.

Rendering consumes only validated saved data and performs no API calls. Same
inputs/language produce byte-identical HTML. Generation time belongs to saved
artifacts, not the render clock. Embed compact JSON with safe script-boundary
escaping; use text nodes/escaped strings and allow only safe HTTP(S) links.
The moved standalone HTML works through file:// with all network requests denied.

## Integration and release gate

Integrate #1 and #2 through their reviewed PRs or explicitly reconcile their
changes before release. Do not edit other active worktrees. Keep CLI/language
contracts aligned and rerun their regressions after integration. A release is
blocked while required dependencies remain incomplete.

Update SKILL.md, both READMEs, methodology, synthetic examples, changelog and
CLI help together. Replace the no-logs claim with the bounded trace contract.
Document installing a pinned tag and replacing the installed skill from that
same tag while preserving user snapshots.

Publish `v2.0.0` only from the validated integrated commit. Package the complete
skill, including helper modules, templates, schemas and references; distribute
tests/docs with the release source. The release smoke test copies only the skill
directory into a fresh temp project, installs its declared requirements, then
runs mocked synthetic collection → details → report → render. A real raw-log
fixture is never needed. Test updating an installed v1 copy from the pinned
release artifact, including a saved v1 rendering check.

No issue closure, release acceptance claim or private example publication before
the gates below pass. A draft PR may expose reviewable progress earlier.

## Acceptance map and validation

| Issue acceptance area | Required evidence |
| --- | --- |
| Overview, purposes and auto-selection | Synthetic jobs with positive deltas, sparse/zero baselines, ties and fallback; isolated selected view |
| 32/64 windows and navigation | >64 attempts per type, smaller history, dates/counts, reruns in the same pipeline |
| Fresh metadata and bounded logs | Mocked transport records exact ID scope/count, cache provenance, failed refresh and every availability state |
| Stack/color/unit rules | Browser assertions for queue above execution, job-vs-pipeline outcome, 300/300.001 s and independent blue selection |
| Every attempt drill-down | Select every retained synthetic ID and rerun; missing logs, phase/image/operation evidence navigation |
| Priorities and accounting | Overlap unions, parent/child exclusion, known N, failed/canceled/cached exclusions and category-total regression fixture |
| Parser edge cases | Redrawn progress, repeated step numbers across builds, absent timestamps, CR/ANSI, partial sections and unknown commands |
| Responsive/a11y | Desktop plus 320/375 px, light/dark, keyboard/focus, chart overflow and console checks |
| Safe compact payload | Secret sentinels in raw fixtures absent from all published artifacts; source hashes/line references retained; payload/request bounds |
| Deterministic offline/version paths | Saved-artifact CLI round trip, identical render bytes, moved HTML with network denied, v1 legacy render and invalid-version errors |
| Language and installation | en/ru interface coverage, original strings unchanged, clean skill-only install and installed-v1 update smoke |
| Release delivery | Green integrated CI, published version tag/release, packaged contents and pinned-artifact smoke |

Initial local test attempt used a Python without `jsonschema`, so its failures
were environmental. Establish a passing baseline using the declared dependency
in a local venv before writing feature regressions. No code defect is inferred
from that first run.

## Authoritative references

- [GitLab Jobs API](https://docs.gitlab.com/api/jobs/): individual job metadata,
  project job ordering, trace endpoint and erased logs.
- [GitLab job logs](https://docs.gitlab.com/ci/jobs/job_logs/): section markers,
  timestamps and log limitations.
- [Docker BuildKit](https://docs.docker.com/build/buildkit/): concurrent build
  operations and cache behavior.
- [Docker cache optimization](https://docs.docker.com/build/cache/optimize/):
  investigation directions for context and dependencies, without causal claims.

References checked on 2026-10-04. Raw sources are not copied into the skill.
