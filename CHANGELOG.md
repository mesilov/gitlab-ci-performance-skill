# Changelog

Changes awaiting release are recorded under Unreleased.

## Unreleased

### Added

- English and Russian HTML report generation through `render --language en|ru`,
  retaining English as the default. Includes localized controls, charts,
  tooltips, status explanations, dates, numbers and time units while preserving
  source data and catalog descriptions. Unsupported languages are rejected.
- Optional `purpose_from_catalog` provenance in comparison groups to distinguish
  generated fallback text from catalog descriptions. Legacy reports remain
  renderable and preserve saved descriptions verbatim.
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
  accessibility labels, tooltips, time formatting and preserved source data.
- Translated the agent skill instructions, including the skill description, and
  the required methodology reference into English. Commands, paths, schema and
  calculation versions, regression thresholds, and operational safeguards are
  preserved.

Tracked in [issue #7](https://github.com/mesilov/gitlab-ci-performance-skill/issues/7)
and [PR #8](https://github.com/mesilov/gitlab-ci-performance-skill/pull/8).

Report localization is tracked in
[issue #2](https://github.com/mesilov/gitlab-ci-performance-skill/issues/2) and
[PR #9](https://github.com/mesilov/gitlab-ci-performance-skill/pull/9).
