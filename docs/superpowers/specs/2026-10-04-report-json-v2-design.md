# Issue #4: reviewed report JSON contract v2

Date: 2026-10-04 (Asia/Bishkek)
Status: approved by owner in chat; implementation in progress.
Issue: https://github.com/mesilov/gitlab-ci-performance-skill/issues/4
Inspected base: `7185372` on `origin/main`.

## Goal and boundary

Implement a versioned, validated, reusable contract for bounded job history,
safe trace summaries, derived priorities and independent LLM exports. The same
saved canonical JSON must drive the offline HTML and CLI exports. No consumer
reimplements baseline selection, timing aggregation or ranking.

Issue #4 owns the data workflow and minimal renderer integration needed to prove
parity. The complete reviewed visual experience remains in #3; complete ru/en
interface translation remains in #2. #4 includes language metadata, stable codes,
localized report title support and language-independent measurements. The live
official-documentation research workflow remains in #5; #4 implements its input
contract and explicit unverified/unavailable states.

No prototype or private fixtures were supplied or copied. Only synthetic examples
will be committed. No CI/runner configuration changes are part of this work.

## Current evidence

- The maintained helper has one 384-line module, strict Draft 2020-12 jobs/report
  schemas with version `1.0.0`, and an offline HTML template.
- Collection currently enumerates the available Jobs API history before retrieving
  pipeline details. Its 100-page cap aborts instead of preserving partial coverage.
- Source projection omits job commit, erasure, per-attempt refresh provenance and
  trace availability. There is no trace parser or compact export command.
- Report windows currently count 1/10 successful pipelines, with same-ref
  comparisons. The browser selects historical attempts and computes lifecycle and
  pre-start values; it does not yet have improvement priorities.
- On this base, all 22 unit tests pass and both checked-in example JSON artifacts
  validate. This is baseline evidence, not acceptance evidence for v2.
- Local branches for #1 and #2 exist. They must be reconciled when implementing
  the new helper options; their mere existence does not establish accepted behavior.

## Alternatives and decision

1. **Recommended: canonical full report plus materialized supported views.**
   Calculate the bounded navigation views once in Python, embed them in HTML,
   and expose them through a schema-backed compact export command. This makes
   offline parity straightforward and needs no browser or server to obtain findings.
2. **Query-only report.** Store normalized evidence and calculate every selected
   view on demand in a Python query command. Smaller report, but offline HTML would
   need either a second implementation or all query results embedded anyway.
3. **Extend the v1 shape in place.** Lower initial migration effort, but existing
   clients would silently misread changed cohorts, retention and timing semantics.

Use alternative 1 with an explicit major version boundary. Preserve strict v1
validation/rendering through frozen legacy schemas/template/helper behavior.
New calculation and collection use v2; conversion never occurs implicitly.

## Modules and workflow

Keep `scripts/ci_report.py` as the installed CLI entrypoint. Move the new bounded
collector, trace parser, contract validation and report calculations into focused
sibling modules. Keep existing v1 functionality in an explicit legacy module.
Use local schema references through a bundled registry, without network resolution.

Workflow:

1. `collect` saves immutable v2 safe metadata and compact trace summaries.
2. `report` calculates overview, baseline, supported window statistics and findings,
   validates schema and semantics, then writes canonical `report.json`.
3. `export` selects an overview, job/window or attempt detail closure, validates it,
   and writes a documented compact artifact without any network access.
4. `render` validates and embeds the original canonical report. It does not refresh
   timestamps or sources and performs no new measurements or network requests.

Every save uses exclusive creation and atomic linking, as the current helper does.
An existing output path remains an error. Validation precedes artifact writes.

## Versions, IDs and provenance

Proposed initial versions: schema `2.0.0`, calculation `2.0.0`, trace parser `1.0.0`
(a new component with no maintained predecessor), skill release `2.0.0`.
The prototype's numeric version has no relationship to these versions.

Envelope fields:

- Stable kind `gitlab_job_performance_report`; four component versions.
- `report_id`: SHA-256 of normalized inputs and calculation policies, excluding
  report generation time, selected language and human-facing formatting.
- `generated_at`, original `collection_started_at` / `collected_at`, independent
  metadata refresh and trace analysis timestamps; IANA `timezone`, `language` en/ru.
- Project host/id/path/URL; source configuration/catalog references and hashes.
- Input hashes and source/retained/refreshed/trace counts, actual request counts,
  explicit configured budgets, stop reason and partial coverage.
- Recorded grouping, baseline, ranking, queue-spike, parser and unit policies.

Immutable source metadata remains a safe projection, rather than being replaced
with rounded, localized or derived values. Hashes cover deterministic canonical
serialization; trace hashes cover original bytes actually read. If a trace is
truncated, record prefix size/hash separately and leave the full-trace hash null.

Job type ID hashes host/project/stage/raw name; attempt ID is the GitLab job ID.
Phase/image/operation IDs are scoped by attempt and image-session ordinal.
Window IDs encode job type, comparison mode/ref selection, size and anchor job ID.
Finding IDs include window/category. User-visible text cannot change these IDs.

All stable structural fields are required. Unknown values are explicitly nullable
where the schema permits them. Optional fields are limited to documented extension
points, such as additional guidance evidence, not missing timing or coverage.
Unknown versions/fields are rejected with supported versions and next-action help.
Breaking semantics or fields require a major schema bump; calculation/parser changes
require their own version bumps. Recalculation always records the active versions.

## Bounded collection and freshness

Default hard budgets: 10 Jobs API pages of 100 entries, 16 analyzed job types,
64 retained attempts/type, 4 concurrent requests, 60-second request timeout,
4 MiB trace input/attempt and 50,000 physical lines/attempt. CLI users may lower
these limits; raising them requires an explicit bounded configuration recorded in
the snapshot. The 64-attempt retention ceiling cannot be raised.

Project/version lookups cost 2 requests. Metadata enumeration costs at most P
requests. For R retained attempts and B additional baseline-only attempts, metadata
refresh costs R+B, pipeline detail requests cost at most R+B unique pipelines,
and trace requests cost at most R. Baseline-only metadata does not cause trace fetches.
Thus the default single-pass maximum is `2 + P + 2*(R+B) + R`, with request counters
recorded separately by endpoint. Resume uses a fresh budget per invocation and
records cumulative counts; no automatic unbounded retries.

Retain newest attempts by descending unique job ID, grouping across refs/outcomes.
Reruns remain independent IDs. A fixed maximum-ID anchor excludes arrivals after
collection begins; validate pagination host/project and reject cycles/duplicates.
Job types are explicitly selected with repeated `--job stage/name` where needed;
automatic discovery is bounded and reports truncation rather than hiding excess
types. Name selection needs a structured JSON configuration if separators collide.

Refresh every retained attempt via the individual job endpoint; refresh failure
preserves the enumerated safe projection with `fresh=false`, error code and time.
Refresh relevant pipeline status independently. Never label a failed refresh fresh.
All counts identify whether they cover enumerated, retained or freshly known data.
Available source count is a lower bound unless enumeration reached EOF; report
`count_kind=exact|lower_bound`. Stop at a page/request budget with a valid partial
snapshot, cursor and explicit reason. Do not claim complete GitLab history.

Resume cache keys include host/project/job ID and parser version. Cache only
allowlisted summaries and hashes by default, never raw traces. Refresh metadata
on every new collection. Reuse trace summaries only for unchanged terminal jobs
under an explicit cache-age policy; running/erased/status-changed jobs require
re-evaluation. Cache reuse preserves original fetch/analysis timestamps and is
explicit in coverage. Offline report/export/render do not refresh cached data.

## Baselines, overview and navigation

History contains at most 64 all-outcome attempts/type; selectable sizes are only
32 and 64, default 32. Supported navigation materializes newest 32, preceding 32,
and newest 64 after the selected ref filter, with actual short counts. Older/Newer
operate between the two 32 pages; Latest resets to the newest page. A 64 view has
no older page within the retained set. Window IDs and actual ordered attempt IDs,
date bounds, anchor, cursor and older/newer flags are included in JSON.

Same-ref is the default comparison policy. Latest attempt is selected independently
of outcome; its ref anchors the default baseline. Cross-ref exploration requires
an explicit ref allowlist/configuration; retain raw refs and record the selected
mode. UI/LLM language must not convert an exploratory delta into a causal regression.

The summary baseline takes up to 10 preceding eligible successful observations
before the latest attempt, independently of displayed-window bounds. In same-ref
mode require successful job AND successful pipeline on the same ref; cross-ref
eligibility uses only explicitly selected refs with the same outcome requirements.
Keep separate successful-job-only descriptive history statistics for #3; never
silently substitute them for the inferential same-ref cohort.

Search the bounded source projection beyond retained history when necessary for
baseline-only metadata, maximum 10 observations/type. If budgets prevent finding
10, retain actual membership and mark the baseline incomplete. It is not permission
to enumerate indefinitely. Baseline-only attempts are explicitly separate from the
retained history and need no drill-down trace.

Overview records verified purpose/configuration evidence, outcome counts/coverage,
latest attempt, wait/execution/complete total, baseline IDs and known/missing N,
median, absolute/relative delta and its comparison classification. Highlight the
largest positive latest-minus-baseline total with >=3 complete baseline totals;
otherwise select the largest known latest complete total. Ties use stable job type
ID ordering. Record a machine-readable selection reason and eligibility evidence.
If no latest total is known, use stable first-job selection and insufficient_data.

## Timing and trace contract

Durations/offsets remain numeric seconds at original precision. Null never becomes
zero. Complete wait+execution total requires both components. Lifecycle is a
separate created-to-finished measurement; pre-start residual has its own validity.
Each timing stores origin, precision/quality, known state and eligibility reason.
Impossible negative/reversed intervals are rejected, not clamped into measurements.

The selected window stores `display_unit`: minutes only when the maximum known
displayed stack (including known components of partial stacks) is strictly >300 s,
otherwise seconds. The same unit applies to selected history/statistics/drill-down/
findings. It changes formatting only; all JSON durations remain seconds.

Every retained attempt has trace availability: available, not_run, empty,
unavailable, erased, permission_denied, unsupported or partial. A 404/transport
error is unavailable, never not_run. not_run requires compatible metadata evidence.
Empty success response has size zero and the empty-byte hash. Erasure is based on
explicit metadata. Nonempty unsupported trace still has hash/size/coverage but no
fabricated evidence. Failed/canceled jobs may contain valid partial evidence.

Trace summary fields include source-byte hash/size, physical line count, parser
version, fetch/analysis time, parse coverage and completeness. Raw lines, shell
arguments, environment variables and secrets are forbidden in these schemas.
Classify only recognized patterns into fixed semantic codes/labels. Custom section
names and arbitrary command labels are not copied into presentation text.

Evidence covers runner phases, image sessions, BuildKit operations, nested parts
and safe script command intervals. Store measured/reported/inferred timing origins,
nullable offsets/durations, cache state, source line ranges, stable parent IDs and
explicit completeness. A source URL links to the original GitLab job/log; line
ranges remain machine-readable even if GitLab cannot deep-link individual lines.
Validate parent/child IDs, acyclicity and compatible bounds; overlapping siblings
remain valid. Inferred positions are marked as estimates, never promoted to measured.

Deduplicate repeated progress frames within an image session; repeated step numbers
in different sessions remain separate. Detect session boundaries conservatively;
ambiguous sessions remain partial instead of merging unrelated operations. Export
layers/local unpack are nested parts of export. Image-span coverage states
push included/excluded/unknown. CACHED is distinct from measured zero seconds.
Phase-only traces are valid. Missing timestamps leave timing unknown.

## Derived findings and guidance

Materialize findings per supported job/window. Each summary contains scope, exact
IDs/date range, eligible successful N, trace/timing coverage, execution/queue medians
and queue-spike state. Proposed initial spike rule: latest queue is >30 s above
successful-window median AND >2x that median, with >=3 known queues; a zero median
uses the absolute threshold. Insufficient data and latest missing queue are explicit.

Fixed categories: export_local_unpack, context_application_copy, base_image,
dependencies_builder_setup, runner_phase and queue. Only recognized semantic
evidence contributes; job names do not determine recommendations.

Within each successful eligible run/category, take the union of usable intervals
before taking the cross-run median. Exclude cached/unknown durations and invalid
intervals. Child intervals cannot be added to an already included parent. For
reported durations without defensible positions, preserve evidence but omit them
from interval-union costs; report missing/incomplete coverage. Ranking is therefore
explicitly coverage-limited. Complete category absence can be zero only when the
parser has affirmative complete coverage for that category; unknown absence is null.

Store category cost independently from representative-step duration. Category costs
are not additive across categories. Rank the known medians descending, tie by code,
display at most three priorities and preserve all category measurements in JSON.
Sample inputs include per-run interval IDs/unions, known/missing N and supporting IDs.
Representative evidence uses the run closest to the median, stable job-ID tie-break,
with job/phase/image/step/line pointers. Selecting it cannot mutate aggregate costs.

Each finding separates observed fact, causal hypothesis and proposed action. Include
applicability, next measurement, uncertainty and nullable estimated_savings_seconds.
No unmeasured savings. Guidance contains official URL, page/section title,
verification date, version/configuration constraints and status verified/unverified/
unavailable. User-supplied verified guidance is validated and hashed as a source;
an offline exporter never invents verification dates or contacts documentation.

## Compact export and renderer parity

Proposed CLI selectors:

```text
ci_report.py export --report report.json --scope overview --output overview.json
ci_report.py export --report report.json --job-type TYPE_ID --window-id WINDOW_ID --output window.json
ci_report.py export --report report.json --attempt-ids 123 124 --output attempts.json
```

Compact kinds have explicit schemas, component versions, canonical report ID/hash,
scope, original coverage/provenance and reference closure. Overview omits trace
summaries but contains all overview findings and required baseline/timing evidence.
Selected-window export contains only that job's metadata/findings and referenced
details. Attempt export contains selected safe metadata/details and required parents.
Intentionally external references declare their canonical report target; otherwise
all evidence pointers resolve inside the compact export. Unknown IDs fail with an
actionable error, never an empty successful artifact. Mixed incompatible selectors
are rejected. Compact selection makes zero network requests.

Full report budget: 16 MiB serialized JSON, at most 16 job types and 64 retained
attempts/type; at most 128 KiB summary/attempt and 512 evidence nodes/attempt.
Per-attempt parser limits produce explicit partial coverage. The full-report cap
rejects writes with actionable narrower-selection instructions; it never silently
drops evidence. Compact outputs cannot exceed the canonical report budget. Payload
size and node/request budgets are tested with synthetic maximum-size sources.

Canonical serialization is sorted UTF-8 JSON with a trailing newline, finite numbers
only. Fixed saved source + fixed generation time + identical policies gives identical
JSON bytes. render/export preserve source and report times and produce deterministic
output. The HTML title is derived from generated_at in the recorded timezone:
`GitLab Job performance report <timestamp>` or its localized heading equivalent.

Renderer JavaScript handles selection, escaping, SVG layout and localized formatting.
It selects precomputed window data; it does not choose eligibility, medians, deltas,
category unions or ranks. Embedded JSON is the canonical report, escaped at the
script boundary. The standalone file does not depend on sidecars, a server or CDN.
JSON and HTML tests compare numerical values, IDs/hashes, coverage and evidence
for every materialized window and selected job.

## Legacy artifacts and release

Frozen v1 jobs/report schemas and renderer keep existing examples readable. New
v2 report generation from v1 metadata is rejected with instructions to recollect
or explicitly use legacy rendering; v1 lacks freshness/trace coverage. Do not fill
those omissions with fabricated v2 values. No automatic in-place migration.

Update maintained SKILL.md, both READMEs, methodology, schemas, CLI examples,
synthetic examples and changelog together. Document `--language en|ru`, same-ref vs
explicit cross-ref, bounds/cache, null semantics and compact selectors. Distributed
skill must contain all runtime modules/schemas/templates/references.

Build and test a clean copied installation, from a directory outside this checkout,
using the documented CLI only. Add it to CI alongside Python 3.10/3.12. Delivery
is a reviewable branch/PR; publish tag/release `v2.0.0` after integration and release
authorization. Do not call a prepared changelog, local tag or smoke test a published
release. Issue acceptance remains open until the release exists and its installed
artifact passes the smoke test.

## Acceptance mapping and execution order

1. **Contracts and semantic validation:** strict reusable source/trace/findings/full/
   compact schemas; invalid IDs, contradictory availability, timing origins,
   impossible intervals, URL provenance and duplicate/cyclic relations tested.
2. **Bounded collection:** pagination anchors, metadata refresh for every retained
   outcome, baseline-only metadata, budget exhaustion, unavailable traces, safe
   cache/resume and actual coverage. Mock transport asserts trace IDs/request bounds.
3. **Trace parser:** synthetic repeated frames, session-scoped IDs, sections, partial
   traces, timestamp intervals, nested export/unpack, push coverage and secrets.
4. **Calculation:** independent baselines, reruns, mixed job/pipeline statuses,
   missing/partial totals, interval unions, failed/cached exclusions, per-category
   known/missing N, queue spike and representative-cost regression.
5. **Exports and renderer:** all window/job cases, short histories, unknown IDs,
   compact reference closure, exact 300/>300 boundary, en/ru stable measurements,
   canonical embedding and deterministic offline round trips.
6. **Documentation and delivery:** examples and changelog, installed-skill smoke,
   CLI/desktop/mobile parity verification, reviewable PR and authorized release.

Each stage produces its schema/module/test artifact and recorded verification.
Implementation tests start with a failing synthetic case for the relevant behavior.
Browser tests under #4 prove offline parity and interactions needed to select a
materialized view; the full visual acceptance checklist remains owned by #3.

## Official references checked for this design

Checked on 2026-10-04; these checks concern contract/API semantics, not verification
of optimization guidance for a real project.

- https://docs.gitlab.com/api/jobs/ — project-job descending ID/keyset pagination;
  individual-job metadata; trace endpoint and ambiguous 404 response semantics.
- https://docs.gitlab.com/ci/jobs/job_logs/ — section boundary format, whole-second
  Unix markers, version-dependent log timestamps. Do not assume all installations
  emit line timestamps: record Runner/version/configuration or unknown applicability.
- https://json-schema.org/draft/2020-12 — reusable Draft 2020-12 schema contract.

## Design review checklist

- Issue #4 checklist mapped to the six implementation stages above.
- Ref/pipeline inferential baseline is separate from descriptive successful-job
  window statistics; no ref or job-name hardcoding.
- Source counts may be lower bounds; no fabricated archive completeness or freshness.
- Baseline can extend beyond history without unbounded trace collection.
- Prefix hashes do not masquerade as whole-trace hashes.
- Missing/cached evidence cannot become zero-cost measured work.
- Compact external references declare their parent report rather than dangling.
- #2/#3/#5 acceptance and published release status remain separate from #4 work.
