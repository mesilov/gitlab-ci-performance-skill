# Workflow methodology 2.0.0

Use this route for a working scenario: a release chain, verification flow or
independent maintenance operation. The agent verifies the scenario against
resolved CI configuration; the helper validates/applies the model. It never
infers dependencies from names, stages, timestamps or tag/commit proximity.

## Verified definitions

Inspect configuration resolved for the relevant execution: includes, extends,
rules, needs, stage ordering, manual actions and parallel/matrix jobs. Author
JSON matching [workflows.schema.json](../schemas/workflows.schema.json), initially
with an empty `evidence` array. `define-workflows` stamps one evidence entry and
validates the finished document. The model's `evidence_ids` reference that entry.
The configuration hash covers the exact supplied bytes; the helper does not
independently verify that YAML was resolved by GitLab or that the agent's claims
are true.

Each workflow has a stable ID, purpose, `chain` or `independent` type, and semantic
versions. Each version contains exact `(name, stage)` selectors with stable
operation IDs, required/optional/manual roles, dependency IDs, parallel groups,
selection context, completion/success policies and evidence IDs. Enumerate actual
matrix names; put ambiguous membership in `unknown_membership`. Dependency IDs
must form a DAG. Independent operations cannot have dependencies/parallel groups
and produce separate histories. Empty `refs`/`sources` selection lists allow all
contexts, but baselines still isolate exact ref/source.

Evidence retains source URL, commit, ref, configuration SHA-256 and verification
time. `pipeline_ids`/`pipeline_shas` enumerate historical configurations actually
verified. A current ref/date never implies historical coverage. An unchanged
repository SHA alone cannot prove unchanged remote includes or configuration
variables: use explicit pipeline IDs when resolution may vary. No applicable
version or multiple matching versions produces unknown/incomplete. Unknown
membership blocks exact totals and successful baseline eligibility. Several
proofs can support one semantic version through `evidence_ids`; change version
when membership/selection/outcome policy changes. Global `unknowns` remain visible
investigation limitations, without invalidating every verified version.

Cross-pipeline scenarios are unsupported. Never join separate pipelines by SHA,
tag or nearby dates. Use [the model example](../assets/workflow-model.json) as a
structural starting point, replacing its generic selectors and coverage with
verified facts from the target repository.

```bash
python <skill-dir>/scripts/ci_report.py define-workflows \
  --model model.json --config resolved-ci.yml --evidence-id resolved \
  --source-url https://gitlab.example.com/group/project/-/blob/COMMIT/.gitlab-ci.yml \
  --commit COMMIT --ref main --verified-at 2026-10-04T00:00:00Z \
  --pipeline-ids 101 102 103 104 --output reports/new/workflows.json
```

To add evidence, use the prior document as `--model`, a new evidence ID, and update
relevant `evidence_ids`. Reusing an ID replaces that entry in a new output document;
existing files are never overwritten.

## Bounded pipeline collection

```bash
python <skill-dir>/scripts/ci_report.py collect \
  --host gitlab.example.com --project group/project --workflow-window \
  --max-pages 10 --output reports/new/jobs.json
python <skill-dir>/scripts/ci_report.py report \
  --snapshot reports/new/jobs.json --workflows reports/new/workflows.json \
  --output reports/new/report.json
python <skill-dir>/scripts/ci_report.py render \
  --report reports/new/report.json --output reports/new/report.html
python <skill-dir>/scripts/ci_report.py export-llm \
  --report reports/new/report.json --output reports/new/llm.json
```

`--workflow-window` enables workflow mode, default **32 pipeline runs**;
`--workflow-window 64` requests 64. These are pipeline windows, not per-job attempt
limits. Each view retains every attempt in its selected pipeline window. Selecting
64 on a snapshot limited to 32 shows actual retained count and partial window
coverage, unless the API proved the available history exhausted. Collect 64 to
obtain the larger window. Baselines use only the selected visible window, with
`extends_visible_window: false`; extra history is not requested.

Use [project Pipelines API](https://docs.gitlab.com/api/pipelines/#list-project-pipelines)
ordered by descending ID, then details and
[pipeline Jobs API](https://docs.gitlab.com/api/jobs/#list-all-jobs-by-pipeline)
with `include_retried=true`. All attempts, not independent per-job slices, are
kept. Pagination targets must retain host/project/path and relevant query scope.
The initial pipeline anchor excludes newly created pipelines. Per-pipeline job
anchors exclude later-created attempts and mark coverage partial. Statuses may
change during collection; the snapshot is not atomic.

Default budget: 10 pages for the pipeline list and 10 for each retained pipeline's
jobs. Upper request bound is `2 + max_pages + W * (1 + max_pages)` for project,
version, pipeline pages, details and job pages, where W is 32 or 64. Read-only
requests use existing `glab` authentication. No traces, artifacts or variables
are requested. Limits/cycles/per-pipeline API failures preserve partial results
with sanitized coverage reasons; unsafe pagination or contradictory IDs fail.
A pipeline list failure marks the window incomplete. Source records include
requested size, actual IDs/date bounds, anchors, page counts, limits, metadata/job
coverage and listing exhaustion. Missing metadata is not proof of job absence.
Deleted/bridge/trigger jobs cannot be recovered; child pipelines are not joined.

## Deterministic outcomes and timing

One run belongs to one explicit pipeline ID. The largest retained attempt ID for
each selector determines its outcome; **all** retained attempts contribute timing,
including failed earlier attempts. IDs remain in run/member records and projected
API jobs stay available for drill-down and recalculation.

Policy: `completion: all_required_terminal`, `success: required_success`. Required
jobs must be terminal; every required job must succeed for success. Once an
optional operation starts, unfinished execution holds completion open. An
unstarted optional manual/skipped/created job does not. API `allow_failure` is
preserved source data, not a substitute for explicit required/optional policy.

States: `completed`, `failed`, `canceled`, `active`, `waiting-manual`,
`unknown/incomplete`. Active work takes precedence over terminal failure when the
scenario still executes. Missing required selectors or partial source/configuration
produce unknown/incomplete. Required skipped jobs do not satisfy success. An
unstarted independent manual operation is waiting-manual even if its selector
would be optional in a chain. Optional terminal failures do not fail a
required-success chain, but their intervals remain included.

| Value, always seconds in JSON | Calculation |
| --- | --- |
| `elapsed_seconds` | First retained start to last finish only for terminal complete measurements with full configuration/source/interval coverage. Excludes pre-start wait. |
| `active_seconds` | Union of known closed execution intervals, counting parallel overlap once. Missing/open/reversed/malformed intervals produce a labeled partial union. Null when no interval is known. |
| `queue_sum_seconds` | Sum of every known retained API `queued_duration`, including known zero on unstarted attempts, with known/missing counts. Never added to elapsed. |
| `gap_seconds` | Exact elapsed minus exact active union; otherwise null. Causes are unknown from timestamps alone. |

Unstarted manual/skipped/created attempts have no execution interval and do not
count as missing solely for that reason. Terminal successful/failed attempts with
missing timestamps do count as missing. Open intervals never get a guessed end.
Malformed raw timestamps remain in the snapshot; only timezone-aware nonnegative
closed intervals are measured. API `duration` remains source data and does not
substitute for interval timing. Partial queue does not invalidate exact elapsed/
active success: those measurements do not depend on queue. Failed/canceled runs
may have exact terminal measurements, but are excluded from successful baselines.

## Histories, cohorts and comparisons

Chains have separate elapsed/active charts. An independent collection produces
one series per operation, with no merged total or invented sequence. Time origin
is `pipeline.created_at`; actual execution start/finish are also exported. Invalid
axis timestamps are unavailable, with HTML empty markers positioned by ID order.
Windows/latest ordering use descending pipeline ID, not commit/tag grouping.

Compare the latest successful complete run to the median of up to ten preceding
eligible successful runs in its cohort, requiring at least three. Cohort hashes
include workflow/operation ID, semantic version, exact job/selection/completion/
success policies, ref and source. Mixed versions/contexts can appear as exploratory
observations in history, but never enter one comparable baseline or connect across
cohort changes. Runner/cache/environment changes can still affect results; duration
change alone does not establish its cause.

Export current ID/value, exact sample pipeline/run IDs, N, median, absolute delta,
percentage, cohort hash, eligibility/reason and extension beyond visible window.
Sparse samples retain a descriptive median but no comparative delta. Zero baseline
means `delta_percent: null`. Failed/canceled/unfinished/partial measurements are
ineligible for successful trends and baselines.

## Contracts and presentation

- `workflows`: [workflows.schema.json](../schemas/workflows.schema.json), verified model.
- `workflow-jobs`: [workflow-jobs.schema.json](../schemas/workflow-jobs.schema.json), bounded source.
- `workflow-report`: [workflow-report.schema.json](../schemas/workflow-report.schema.json), canonical definitions, provenance, membership, outcomes, timing, coverage, histories and comparisons.
- `workflow-llm`: [workflow-llm.schema.json](../schemas/workflow-llm.schema.json), omits repeated raw jobs/pipelines but preserves exact canonical views, definitions, coverage and original report SHA-256.

All use schema 2.0.0; derived calculations are 2.0.0. Validate with
`ci_report.py validate <artifact>`. Hash serialization: UTF-8, sorted keys, indent
2, final newline. Same saved report renders byte-identically. HTML embeds canonical
JSON, with no browser timing/baseline aggregation. Coordinates, formatting and
selection are presentation only. `render --language en|ru` chooses the initial
interface language; the HTML also provides an in-report language selector.
Language changes interface copy, not source names
or verified purposes. Schema/reference links require no remote schema downloads.

Unit scope: **selected series and metric over the selected pipeline window**.
Strictly above 300 seconds selects minutes; exactly 300 selects seconds. Elapsed
and gap share elapsed scope; active/API duration share active scope; queue uses
queue scope. JSON/`data-seconds` always remain seconds. Unknown values get explicit
markers instead of measured zero. Selection is shared across charts, pipeline
selector and job/attempt drill-down. Failed outcomes keep separate styling.

The release preserves v1 `jobs`/`report` contracts (including report 1.1.0 release history) and job-only CLI. v1 snapshots
lack proof of all-attempt bounded pipeline coverage and cannot silently convert to
workflow snapshots: recollect. Unknown/future versions are rejected. Offline HTML
works after moving without sidecars or a server.
