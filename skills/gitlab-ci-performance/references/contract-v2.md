# Report contract 2.0.0

This contract implements issue #4. Full reviewed visual acceptance (#3), complete
interface translation (#2), and the current-official-documentation investigation
workflow (#5) remain separate. `--language en|ru` sets report language metadata and
localized shell/title; raw names, evidence codes, calculation keys and seconds do
not change. English is the default. Some explanatory evidence codes remain machine
codes pending the complete interface translation.

## Artifacts and validation

| Artifact | Kind | Schema |
|---|---|---|
| Safe metadata and compact trace summaries | `gitlab_job_performance_source` | `jobs.schema.json` |
| Individual trace summary | parser `1.0.0` | `trace.schema.json` |
| Canonical report | `gitlab_job_performance_report` | `report.schema.json` |
| LLM selection | `gitlab_job_performance_compact` | `compact.schema.json` |

Entry schemas reference `common.schema.json` using reusable Draft 2020-12
`$defs`. The helper registers that bundled document locally; schema validation
never resolves URLs over the network. Every structural property listed in a
schema's `required` array is mandatory. Closed objects reject unknown properties.
Nullable fields contain JSON null when unknown; omitted timing is not supported.

`report_contract.validate` supplements schemas with unique IDs, source/pipeline
relations, source counts and anchors, per-type retention, timestamps/HTTPS URLs,
trace availability, cache/partial semantics, parent acyclicity/containment, timing
origins and eligibility, window reference closure, source hashes, source equality,
and recomputed sample aggregates/category unions/ranks. Run `ci_report.py validate
<artifact.json>` before consuming untrusted artifacts. `report`, `export` and
`render` also validate their inputs and outputs; writes reject existing paths.

## Envelope and source provenance

The report stores schema/calculation/skill versions `2.0.0`, parser `1.0.0`, and a
stable report kind. These versions are independent; the local prototype's version
is unrelated. `report_id` hashes input provenance and policies, excluding generated
presentation time and language. UTF-8 canonical serialization uses sorted keys,
indent=2, unescaped Unicode, finite numbers and a final newline. The compact
export also records `canonical_report_sha256`, the hash of the complete saved report.

`generated_at` is report calculation time. `collected_at` is the original source
collection completion time; `source.collection_started_at` remains distinct.
`metadata_analyzed_at` and `trace_analyzed_at` record the latest analysis/refresh
coverage, including the original times for reused trace summaries. Rendering does
not change any of these timestamps. Dates are machine-readable timestamps with
an offset; `timezone` is an IANA display zone. The HTML title formats `generated_at`
in that zone as `GitLab Job performance report <timestamp>` (or a Russian heading).

The canonical report contains the original safe source projection and optional
baseline source, their hashes, project identity, catalog/guidance hashes, policy
records and `coverage` including collection limits, selection configuration,
request counters, observed counts and stop/cursor state. Catalog purposes retain
source URL/verification time; missing configuration provenance stays an empty
`source_configuration` list rather than becoming an invented reference.

Job type IDs hash host/project ID/stage/raw job name. Job IDs distinguish reruns.
Evidence IDs are scoped by attempt/session. Window IDs include type/mode/refs/size/
page/anchor. Finding IDs include window/category. No ID depends on UI language.

## Collection, coverage and budgets

Default limits: 10 keyset pages × 100 jobs, 16 analyzed types, 64 retained attempts
per type, up to 10 baseline-only metadata candidates/type, concurrency 4, request
60 s, trace 4 MiB/50,000 physical lines. Page budget may be explicitly increased;
concurrency/type/trace caps cannot exceed these ceilings. Positive limits and
selector types are checked before collection. The report/export payload cap is
16 MiB, individual trace summary 128 KiB. The parser stops adding evidence at
120 nodes (a frame can add a parent+child and reach 121), while preserving source
hash/size/line counts and recording `partial/evidence_limit`. Schema ceiling is
512 nodes, allowing explicit future parser evolution without uncapped runtime work.

Let P be metadata pages, R retained attempts and B extra baseline candidates. Per
invocation, requests are bounded by `2 + P + 2*(R+B) + R`: project/version, pages,
job/pipeline metadata (pipelines deduplicated), retained traces. Not-run/erased jobs
and eligible cached summaries reduce trace requests. Actual counters are recorded.
No trace requests are made for baseline-only or other historical metadata. The
transport reads trace stdout incrementally and kills the subprocess at byte/line
limits; it never captures an unlimited trace and then slices it.

Enumeration preserves all safely projected metadata within the page budget. The
retained set is the newest 64 by descending job ID per stage/name across outcomes
and refs. Metadata refresh requests cover every retained attempt, plus bounded
baseline-only candidates. Pipeline status is refreshed independently. Failed
refresh preserves enumeration evidence with `metadata_fresh=false` and a safe error
code, never a fabricated fresh status. All-outcome visible history is distinct
from timing eligibility.

A fixed maximum-job-ID anchor excludes new arrivals during collection. EOF gives
`count_kind=exact` for the available anchored Jobs API history; page-budget stops
give a lower bound, not the complete archive. Deleted/bridge jobs are not recoverable.
Type-budget stops preserve counts of ignored types. `--job-config selectors.json`
accepts an array of `{stage,name}` objects; use it for names containing `/`.
`--job stage/name` is convenient for simpler names.

`--resume source.json` resumes from its validated safe cursor/anchor with a new
per-invocation page budget. Request/page counters are cumulative; budgets describe
the current invocation. Already-seen IDs are deduplicated across resume snapshots;
duplicates/cycles within a new invocation are errors. Fresh job/pipeline checks are
repeated. `resumed_from_sha256` records the previous snapshot.

`--cache source.json` reuses only validated summaries for unchanged freshly checked
terminal jobs, same parser, within recorded `cache_max_age_seconds` (default 86400)
and current input limits. Status/commit/start/finish/duration/erasure changes invalidate
reuse. Active jobs are re-read. Raw traces are never cached or exported. Cached
summaries retain original fetch/analysis times and set `cached=true`. `report`,
`export` and `render` have no transport calls; source availability cannot trigger GETs.

## Windows, baselines and timings

Only history sizes 32/64 exist. Per selected job/ref mode the report materializes
newest 32, preceding 32 when available, and newest 64. Older/Newer operate between
32 pages within retained history; Latest returns to the newest page. Size64 has
no older page inside the64 retained set. Actual IDs, count, dates, anchor, page and
navigation flags are stored; small histories are not padded.

Same-ref is the default. Latest attempt of any outcome anchors its ref. Cross-ref
requires `--comparison-mode cross_ref --ref REF` (repeat); original refs remain
visible and comparison classifications have an `exploratory_` prefix. For collection
and report use the same explicit ref selection when collecting baseline-only data.

The inferential baseline uses up to 10 preceding, freshly known successful jobs in
freshly successful pipelines on permitted refs. It is independent of the displayed
32/64 window, excludes the latest ID, and can use metadata outside retained history.
External source baselines must belong to the same project and cannot be newer.
Overlapping IDs use current metadata and cannot duplicate the latest observation.
An incomplete search records actual membership/coverage. Descriptive window metrics
use successful jobs separately, including successful jobs in failed pipelines;
that cohort is never silently substituted for the inferential baseline/findings.

Overview highlighting requires >=3 complete baseline totals and chooses largest
positive absolute latest-minus-baseline total. Fallback is longest known latest
total, then stable first type with insufficient_data. Stable type IDs break ties.

Every machine-readable timing is seconds with original precision. Queue/execution
are separate API fields; complete total requires both. Lifecycle is creation→finish.
Pre-start residual is start−creation−API queue; negative residual is null/inconsistent,
not clamped to zero. Partial stacks may display their known component but complete
total remains null. Sample metrics keep known/missing N; no values means null.

One `display_unit` applies to the selected view's statistics/history/details/findings.
Only maximum displayed stack **strictly >300 s** chooses minutes; exactly 300 uses
seconds. This affects presentation only. API/derived timings include origin,
quality and eligibility. Section boundaries have whole-second precision; command
intervals from timestamped echoes are inferred logged intervals, not profiled runtimes.

## Trace states and evidence

Every retained attempt has a summary state: available, not_run, empty, unavailable,
erased, permission_denied, unsupported or partial. not_run requires job metadata
compatible with no start; erased requires explicit erasure metadata. Trace404 is
unavailable because the API cannot distinguish absent job from absent log. Fetch
failures never establish that execution did not occur. A successful empty trace has
size0 and the empty-byte hash. Unsupported nonempty traces retain hash/counts without
inventing evidence. Failed/canceled runs can still have valid trace evidence.

Whole-byte `sha256` exists only for whole inputs; byte/line-limited prefixes use
`prefix_sha256`, whole hash=null and partial state. Parser evidence limits preserve
the whole-byte hash while marking incomplete analysis. Physical source line ranges
refer to raw log positions. IDs link through safe metadata URLs to the original job;
GitLab may not support direct line-range deep links.

Allowlisted nodes cover phases, image sessions, operations, nested parts and command
intervals. Arbitrary section labels, command strings, arguments, output/environment
and credentials are omitted; only fixed semantic codes and numerical evidence survive.
BuildKit instruction matching is anchored, so keywords inside RUN arguments cannot
misclassify COPY/FROM. Repeated frames deduplicate within a session; repeated step
IDs across explicit sessions remain separate. Ambiguous changed headers split partial
sessions. Identical reused IDs/headers without any observable boundary cannot be
reliably distinguished and remain a documented parser limitation.

BuildKit durations remain `origin=buildkit_reported`. With a timestamped DONE,
defensible positions can be inferred from completion time minus reported duration:
`quality=inferred`, with buffering uncertainty recorded in findings. Invalid negative
positions remain unknown; they are never clamped. Image spans use inferred logged
bounds and explicit push coverage included/excluded/unknown. Parts are nested under
operations and positioned only inside known parent bounds. CACHED is unknown duration,
not measured zero. Bare/missing timestamps retain reported duration but no fabricated
positions. Phase-only evidence remains usable.

## Improvement findings and recommendation provenance

Each materialized window records scope/date/IDs, eligible successful N, trace/timing
coverage, execution/queue/total metrics and category samples. The queue spike uses
the newest displayed attempt, not the newest attempt outside an older window:
queue > median+30 s AND >2×median, with >= 3 known successful queues. Zero median
uses the absolute rule. Missing/insufficient data has an explicit state.

Categories: export/local unpack, context/application copies, base-image work,
dependencies/builder setup, runner phases, queue. Within a run/category merge usable
intervals, then take the median across eligible successful runs. Parent parts are not
added twice. Cached/unknown/incomplete nodes and failed/canceled attempts do not enter
successful-cost aggregates. Duration without positions remains evidence but has null
category cost. Timestamp-positioned BuildKit durations are admitted under recorded
`timing_evidence_policy`, with `inferred_position` uncertainty. Unknown absence is null,
not a fabricated zero. Costs are not additive across categories.

Category totals and known/missing N remain separate from representative duration.
Representative references contain attempt/evidence/URL/lines; selecting a step cannot
change the category's median. Top 3 priorities sort observed medians descending, tie by
category code. Queue representatives point to API metadata without a fake log line.

Findings separate observed fact, unknown causal hypothesis, concrete investigation,
applicability, next measurement and uncertainty. `estimated_savings_seconds` is null:
measured cost is not guaranteed savings. Missing guidance is explicitly represented
by the uncertainty code `guidance_unavailable`, never a invented verification.

Optional `--guidance guidance.json` has `{categories:{CATEGORY:[RECORD]}}`. Each record
requires `url`, `page_title`, `section_title`, `verified_at` (YYYY-MM-DD or null),
`status` (verified/unverified/unavailable), `applicable_versions` and
`configuration_constraints` arrays. Verified needs a verification date. Official
HTTPS GitLab/Docker documentation and moby/buildkit sources are accepted. The caller
must actually verify applicability; offline generation cannot claim it checked a URL.

## LLM exports and offline parity

```bash
python scripts/ci_report.py export --report report.json --scope overview --output overview.json
python scripts/ci_report.py export --report report.json --job-type JOB_TYPE_ID --window-id WINDOW_ID --output window.json
python scripts/ci_report.py export --report report.json --attempt-ids 123 124 --output attempts.json
```

Overview contains all overviews/materialized findings and safe timing metadata, omitting
trace nodes. Window exports contain one selected window/type with baseline/latest
metadata needed to interpret it, omitting unrelated traces. Attempt exports contain
selected metadata/trace details and parent nodes. Selection order is deterministic;
unknown IDs or incompatible selectors fail before writes. Compact kinds have schemas,
original envelope/coverage/policies and canonical report ID/hash. Omitted navigation/
overview trace references explicitly name their canonical report in
`external_references`; they are not undocumented dangling IDs. A compact export does
not claim to independently validate omitted canonical trace bytes; retrieve the linked
canonical report when investigating those references.

The same numerical window/findings objects appear unchanged in full JSON, compact
exports and HTML. JavaScript only selects/escapes/formats/layouts them. No client-side
cohort selection, median, union or ranking implementation exists. HTML embeds the full
canonical report and works as one relocated offline file. Reanalysis needs the saved
source/evidence and recorded calculation policy, never HTML scraping/browser execution.

## Evolution, legacy and installed verification

Breaking fields/semantics need a major schema bump. Calculation/parser changes need
independent version bumps; unknown versions/fields reject with actionable help. No
silent reinterpretation of v1. Frozen schemas/templates validate/render existing v1
artifacts; v1 generation is explicit `report --legacy`. New v2 report generation from
v1 source fails with recollection/legacy instructions because freshness/trace evidence
cannot be invented. The original v1 demo remains a legacy fixture.

After updating/copying the skill directory, install its pinned requirements in a venv
and run documented commands using the copied helper. Unit tests copy the complete skill
outside the checkout and verify canonical bytes/HTML round trips. CLI modules import
only bundled siblings/schemas/templates. Release publication and installed-release
verification follow integration; a local copy smoke does not establish a published tag.
