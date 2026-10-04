# Changelog

Changes awaiting release are recorded under Unreleased.

## Unreleased

### Added

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
- New report/calculation version 1.1.0 with a validated optional release-history
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
