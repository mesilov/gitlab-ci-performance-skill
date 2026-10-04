# Changelog

Changes awaiting release are recorded under Unreleased.

## Unreleased

### Workflow release 2.0.0

- Added versioned agent-verified workflow definitions, configuration evidence,
  explicit historical coverage, required/manual policies and validated dependency DAGs.
- Added bounded 32/64 pipeline-first collection with all retained retries,
  pagination anchors/limits and partial metadata/job coverage; no trace requests.
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
