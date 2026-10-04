# Changelog

Released changes are grouped by skill version.

## Unreleased

### Workflow contracts 2.0.0

- Added versioned agent-verified workflow definitions, configuration evidence,
  explicit historical coverage, required/manual policies and validated dependency DAGs.
- Added bounded 32/64 pipeline-first collection with all retained retries,
  pagination anchors/limits and partial metadata/job coverage; no trace requests.
- Deduplicate overlapping job pages after concurrent retries and mark affected
  pipelines partial instead of aborting collection.
- Added deterministic elapsed, interval-union active, known queue sums and gaps,
  latest-attempt outcomes, independent operation series and comparable medians with
  exact sample IDs, eligibility and zero-baseline null percentages.
- Added v2 workflow snapshot/report/LLM schemas and offline bilingual workflow HTML
  with synchronized pipeline/job/attempt drill-down, responsive charts and strict
  300-second display-unit scope. v1 job-only artifacts keep their original semantics.
- Included a generic model in the installable skill, synthetic demo/boundary
  generators, workflow methodology, CLI examples, installed-package smoke checks
  and offline browser QA.

Tracked in [issue #6](https://github.com/mesilov/gitlab-ci-performance-skill/issues/6).

## 2.0.1 — 2026-10-04

- Validates every baseline observation against a compact source projection,
  including samples older than the retained 64-attempt history. Rejects changed
  pipeline/ref/type/timing values and incomplete source coverage before rendering.
- Bumps report/calculation contracts to 2.0.1; metadata/timings/parser stay 2.0.0.
  Existing 1.0/1.1/2.0.0 reports keep their rendering; stricter source checks require
  explicit re-analysis into new outputs. No extra trace GETs are introduced.
- Adds outside-history corruption and old-2.0 compatibility regressions.

## 2.0.0 — 2026-10-04

- Ships the reviewed selected-job report with 32/64 attempt windows, gray queue
  above outcome-colored execution, adaptive units, keyboard navigation and en/ru.
- Adds bounded fresh metadata and safe trace parsing for every retained attempt,
  private explicit cache reuse, availability/partial states and source provenance.
- Adds runner/command/BuildKit evidence, overlap-safe successful cost priorities
  and independent representative evidence; excludes cached/failed/missing costs.
- Introduces schema/calculation/parser 2.0 contracts, deterministic offline render
  and preserved 1.0/1.1 compatibility, integrating history #1 and language #2.
- Adds synthetic parser/transport/calculation/browser and clean installed-skill
  update coverage; no private source data is distributed.

Tracked in [issue #3](https://github.com/mesilov/gitlab-ci-performance-skill/issues/3).


### Integrated prior changes

- English and Russian HTML report generation through `render --language en|ru`,
  retaining English as the default, including the optional release-history panel.
  Includes localized controls, charts,
  tooltips, status explanations, dates, numbers and time units while preserving
  source data and catalog descriptions. Unsupported languages are rejected.
- Optional `purpose_from_catalog` provenance in comparison and release-history groups to distinguish
  generated fallback text from catalog descriptions. Legacy reports remain
  renderable and preserve saved descriptions verbatim.
- Official optimization documentation route in the skill, with measured-symptom
  starting points for GitLab and Docker/BuildKit. Recommendations require current
  source reads, version/configuration applicability, evidence, and a validation
  plan; unavailable sources and uncertain causes remain explicit. Tracked in
  [issue #5](https://github.com/mesilov/gitlab-ci-performance-skill/issues/5).
- Installation/update guidance for retaining the versioned optimization reference.
- Optional per-job execution and runner queue history across explicitly selected
  refs/tags (`report --release-refs`). Original refs, sample IDs, counts and context
  remain visible; cross-ref changes are exploratory observations. Includes an
  offline interactive chart, 32/64 visible attempt windows and a generic demo.
  Tracked in [issue #1](https://github.com/mesilov/gitlab-ci-performance-skill/issues/1).

- Russian documentation in `README.ru.md`, with reciprocal English / Русский
  links at the top of both README files. `README.md` remains the default English
  documentation.
- This changelog, linked from both README versions.

### Changed

- Documented report language selection, defaults, source-data preservation and
  legacy-report compatibility in CLI help, skill instructions and both README
  versions.
- CI smoke generation now renders both English and Russian reports. Offline
  browser checks cover both languages, including desktop/mobile layouts,
  accessibility labels, tooltips, time formatting, release history and preserved source data.
- Preserved report/calculation version 1.1.0 with a validated optional release-history
  payload; jobs stay 1.0.0. The updated renderer accepts legacy 1.0.0 reports.

- Translated the agent skill instructions, including the skill description, and
  the required methodology reference into English. Commands, paths, schema and
  calculation versions, regression thresholds, and operational safeguards are
  preserved.

Tracked in [issue #7](https://github.com/mesilov/gitlab-ci-performance-skill/issues/7)
and [PR #8](https://github.com/mesilov/gitlab-ci-performance-skill/pull/8).

Report localization is tracked in
[issue #2](https://github.com/mesilov/gitlab-ci-performance-skill/issues/2) and
[PR #9](https://github.com/mesilov/gitlab-ci-performance-skill/pull/9).
