# Changelog

Changes awaiting release are recorded under Unreleased.

## Unreleased

### Added

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

- New report/calculation version 1.1.0 with a validated optional release-history
  payload; jobs stay 1.0.0. The updated renderer accepts legacy 1.0.0 reports.

- Translated the agent skill instructions, including the skill description, and
  the required methodology reference into English. Commands, paths, schema and
  calculation versions, regression thresholds, and operational safeguards are
  preserved.

Tracked in [issue #7](https://github.com/mesilov/gitlab-ci-performance-skill/issues/7)
and [PR #8](https://github.com/mesilov/gitlab-ci-performance-skill/pull/8).
