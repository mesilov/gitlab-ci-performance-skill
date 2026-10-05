# Changelog

## Unreleased — canonical contract 3.0.0 / parser 2.0.0

- Separate routine report generation, ready upstream installation/update and
  skill development/diagnosis; retain built-in validation without automatically
  rerunning the full repository test/browser QA suite for each report (#23).
- Complete install/update-only requests with a local installed-helper `--help`
  check; require the report route only when a report is also requested (PR #25 review).
- Raise canonical serialized UTF-8 JSON to 64 MiB inclusive; HTML has no JSON cap.
- Materialize all 16/32 pages (default 16) within retention 64 and independent baseline 10.
- Preserve original log bytes/titles/stages/arguments/references and provenance.
- Add inert offline source viewing, copying and lossless byte downloads.
- Expose admission/coverage boundaries and reject older masked canonical artifacts.


## 0.1.0 — Unreleased

The initial milestone is in development. The changes below are grouped by
capability and do not represent separate published releases. Artifact
schema/calculation/parser versions are independent of the skill release version.

### Fixed

- Preserve safe original BuildKit operation/suboperation titles separately from
  localized category codes. Record title availability, redaction, source kind and
  physical lines; render `#step title` unchanged in English and Russian while
  keeping sensitive arguments and destinations out of saved artifacts (#20).
- Accept GitLab keyset links that repeat the project `id` in the query, requiring
  an exact match with the requested project and rejecting duplicate/empty IDs.
- Align canonical `report-v2.html` with the reviewed report presentation (#16):
  localized concise heading, white/dark palette, thin dividers, a gray framed
  priority panel with vertical action rows, baseline/outcome cards, collapsed
  history and latest-attempt details.
- Replace expanded evidence cards with compact two-level timelines: collapsed
  runner phases/technical metadata, selected-fragment operations, relative time
  axes, source lines and nested substeps. Preserve unknown/cache/partial states
  and label anonymous build fragments without inventing image names or BuildKit
  step IDs. Canonical JSON, calculations and legacy/reviewed renderers are unchanged.
- Keep chart text readable on mobile with responsive SVG geometry; Inspect run
  moves focus and viewport to the selected evidence.
- Extend offline browser regression checks for layout, numeric baseline parity,
  evidence parents, keyboard selection, drilldown navigation and desktop/mobile
  light/dark views. Run the new drilldown checks in hosted CI for both languages.


### Job performance reports

- Selected-job reports with 32/64 attempt windows, runner queue above
  outcome-colored execution, adaptive time units and keyboard navigation.
- Bounded fresh metadata and safe trace parsing for every retained attempt,
  explicit private cache reuse, log availability/partial states and provenance.
- Runner, command and BuildKit evidence with overlap-safe successful cost
  priorities and independent representative evidence. Cached, failed and missing
  costs are excluded.
- Baseline validation against compact source projections, including samples
  older than the retained 64-attempt history. Changed pipeline/ref/type/timing
  values and incomplete source coverage are rejected before rendering.
- Optional job execution and queue history across explicitly selected refs/tags
  (`report --release-refs`), with original refs, sample IDs, counts and context.
  Cross-ref changes remain exploratory observations.
- Optional `purpose_from_catalog` provenance distinguishes catalog descriptions
  from generated fallback text. Supported legacy reports retain their saved
  descriptions and rendering semantics; re-analysis creates new outputs.

Tracked in [issue #1](https://github.com/mesilov/gitlab-ci-performance-skill/issues/1)
and [issue #3](https://github.com/mesilov/gitlab-ci-performance-skill/issues/3).

### Workflow analysis

- Agent-verified workflow definitions, configuration evidence, explicit
  historical coverage, required/manual policies and validated dependency DAGs.
- Bounded 32/64 pipeline-first collection with all retained retries, pagination
  anchors/limits and partial metadata/job coverage; no trace requests.
- Deduplication of overlapping job pages after concurrent retries, marking
  affected pipelines partial instead of aborting collection.
- Deterministic elapsed time, interval-union active time, known queue sums and
  gaps, latest-attempt outcomes, independent operation series and comparable
  medians with exact sample IDs, eligibility and null zero-baseline percentages.
- Workflow snapshot/report/LLM contracts and offline bilingual HTML with
  synchronized pipeline/job/attempt drill-down, responsive charts and a strict
  300-second display-unit boundary.
- Generic workflow model in the installable skill, synthetic demo and boundary
  generators, methodology and CLI examples.

Tracked in [issue #6](https://github.com/mesilov/gitlab-ci-performance-skill/issues/6).

### Canonical reports and LLM exports

- Namespaced source/trace/findings/compact contracts through the installed
  `report_cli.py` entrypoint, with strict semantic validation, bounded safe
  collection, independent baselines and interval-union costs.
- Reproducible LLM projections and JSON/HTML parity for full reports, overview,
  selected windows and selected attempts.
- Separate artifact kinds for the `report_cli.py` and `ci_report.py` workflows;
  incompatible inputs are rejected rather than silently migrated.
- Canonical provenance records the installed skill `VERSION` independently of
  schema/calculation/parser versions.

Tracked in [issue #4](https://github.com/mesilov/gitlab-ci-performance-skill/issues/4).

### Localization and documentation

- English and Russian HTML generation through `render --language en|ru`, with
  English as the default. Controls, charts, tooltips, statuses, dates, numbers and
  time units are localized while source data and catalog descriptions are preserved.
- English skill instructions and methodology, plus English and Russian README
  files with reciprocal language links and installation/update guidance.
- Official GitLab and Docker/BuildKit optimization documentation, organized by
  measured symptoms. Recommendations require current source reads, applicable
  versions/configuration, evidence and a validation plan; uncertainty stays explicit.
- README and changelog aligned with the unreleased 0.1.0 milestone.

Tracked in [issue #2](https://github.com/mesilov/gitlab-ci-performance-skill/issues/2),
[issue #5](https://github.com/mesilov/gitlab-ci-performance-skill/issues/5) and
[issue #7](https://github.com/mesilov/gitlab-ci-performance-skill/issues/7).
Related documentation/localization changes:
[PR #8](https://github.com/mesilov/gitlab-ci-performance-skill/pull/8) and
[PR #9](https://github.com/mesilov/gitlab-ci-performance-skill/pull/9).

### Validation

- Synthetic parser, transport, calculation and baseline-corruption checks,
  including samples outside the retained history and supported legacy artifacts.
- Clean skill-only installation/update checks, request/payload limits and privacy
  sentinels; no private source data is distributed.
- Combined installed-entrypoint and offline browser CI coverage for both languages,
  32/64 windows, retained retries/outcomes, evidence, desktop/mobile layouts,
  light/dark themes, keyboard/focus, safe links, moved HTML and denied network.
- Workflow browser checks for pipeline/job/attempt parity and display-unit boundaries.
