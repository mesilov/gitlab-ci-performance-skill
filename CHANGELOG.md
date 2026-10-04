# Changelog

Changes awaiting release are recorded under Unreleased.

## Unreleased

### Report contract 2.0.0 (release candidate; not yet published)

- Introduce strict reusable source, trace, full-report and compact schemas, semantic
  source/cohort/aggregate checks and independent schema/calculation/parser/skill versions.
- Bound history to 64 attempts/type and materialize 32/64 windows; refresh retained
  all-outcome job/pipeline metadata, bounded baseline-only metadata, trace summaries,
  safe cache/resume and actual source/request coverage.
- Parse allowlisted phases, command intervals and session-scoped BuildKit operations/
  nested parts without exporting raw logs; retain unknown/cache/partial and inferred
  position uncertainty. Calculate category interval unions and priorities in Python.
- Add canonical and compact LLM JSON exports and an offline renderer using the same
  materialized measurements. Preserve original collection/analysis dates and seconds.
- Preserve v1 validation/rendering and require explicit `report --legacy` generation.
  New v2 report generation cannot silently upgrade missing v1 evidence.
- Add language metadata/title/presentation shell, synthetic integration/browser checks
  and copied-install smoke. Complete visual/language/research workflows remain #3/#2/#5.

Tracked in [issue #4](https://github.com/mesilov/gitlab-ci-performance-skill/issues/4).


### Added

- Russian documentation in `README.ru.md`, with reciprocal English / Русский
  links at the top of both README files. `README.md` remains the default English
  documentation.
- This changelog, linked from both README versions.

### Changed

- Translated the agent skill instructions, including the skill description, and
  the required methodology reference into English. Commands, paths, schema and
  calculation versions, regression thresholds, and operational safeguards are
  preserved.

Tracked in [issue #7](https://github.com/mesilov/gitlab-ci-performance-skill/issues/7)
and [PR #8](https://github.com/mesilov/gitlab-ci-performance-skill/pull/8).
