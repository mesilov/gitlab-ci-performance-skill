# Report JSON v2 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for sequential execution in this worktree. Owner approved the design in this chat.

**Goal:** Implement issue #4 with bounded source/evidence contracts and identical offline JSON/HTML findings.

**Architecture:** Keep v1 library/schema/template behavior explicit. Introduce contract, collection, trace, calculation and CLI modules shipped inside the skill. Materialize supported views once and export documented projections with provenance and declared external references.

**Tech Stack:** Python 3.10+, jsonschema Draft 2020-12, glab GET transport, vanilla offline HTML.

## 1. Contracts and validation

Files: `scripts/report_contract.py`, `schemas/{jobs,trace,report,compact}.schema.json`, `schemas/legacy/*.json`, `tests/test_contract_v2.py` inside the existing skill/test directories.

- [x] Write synthetic source fixture and tests for version rejection, timing/availability contradictions and ID/parent relations. Run `.venv/bin/python -m unittest discover -s tests -p test_contract_v2.py -v`; expect missing v2 module failure.
- [x] Implement local-only schema registry, finite timings, URL/date checks, reference and interval checks, canonical encoding and no-overwrite writes. Freeze v1 schemas and keep old helper tests working.
- [x] Run existing and v2 unit suites; record output and commit tested contract work.

## 2. Bounded source collection

Files: `scripts/report_collect.py`, `tests/test_collect_v2.py`.

- [x] Mock transport at the API boundary; assert 64 retention, all-outcome refresh, trace IDs restricted to retained attempts, prefix/EOF coverage and budget/cursor states. Verify failure before implementation.
- [x] Implement safe job/pipeline projection, fixed anchor pagination, explicit type/ref selection, refresh coverage, bounded byte/line input and allowlisted summary cache. No automatic retries or raw trace cache.
- [x] Run collector tests and commit verified request-bound behavior.

## 3. Trace parsing

Files: `scripts/report_trace.py`, `tests/test_trace_v2.py`.

- [x] Write synthetic section/BuildKit frames with session ID reuse, overlapping operations, export parts, missing timestamps and secret-bearing command text. Assert only fixed labels and line ranges survive. Verify failing tests.
- [x] Implement safe phase/command/session/operation summaries and parser provenance; retain unknown/cached/partial distinctions and conservative push coverage.
- [x] Run parser tests and commit tested parser work.

## 4. Calculation and compact exports

Files: `scripts/report_calculate.py`, `scripts/report_export.py`, `tests/test_calculate_v2.py`.

- [x] Test independent baseline membership, job/pipeline outcome differences, reruns, short windows, queue spike, interval union and category-total/representative duration distinction. Verify failures first.
- [x] Calculate three supported navigation views per type/ref mode, timing origins, latest selection, baseline/deltas, window units, category costs/ranks and evidence closure.
- [x] Test compact overview/window/attempt selectors, missing IDs, determinism and language-independent numeric results. Implement exports with original canonical report ID/hash and explicit external references.
- [x] Run focused and legacy suites; commit tested calculations/exports.

## 5. CLI and offline rendering

Files: `scripts/report_cli.py`, `scripts/ci_report.py`, `assets/report-v2.html`, `tests/test_cli_v2.py`, `tests/browser_v2.cjs`.

- [x] Test collect/report/export/validate/render round trips through the actual entrypoint, legacy rejection/help and copied installed skill without checkout imports. Verify failures.
- [x] Dispatch v2 CLI, retaining explicit `--legacy` generation and automatic validated v1 rendering. Embed unchanged canonical JSON and select precomputed views in HTML.
- [x] Browser test selected windows/jobs/evidence with network disabled; compare displayed values/IDs with JSON, units at 300/>300 and report title timestamp/timezone.
- [x] Verify installed CLI and render parity, then commit integration.

## 6. Documentation and delivery

Files: `SKILL.md`, `references/methodology.md`, `references/contract-v2.md`, both READMEs, CHANGELOG.md, `examples/v2/*`, `.github/workflows/check.yml`.

- [x] Document exact schemas, required/nullable values, parser/aggregation exclusions, bounded requests/cache, compact selectors and legacy path. Keep #2/#3/#5 ownership clear.
- [x] Generate synthetic canonical/compact/HTML examples through maintained CLI. Run unit tests and copied-install smoke, verify size/secret boundaries and staged diff.
- [x] Open and attach a reviewable PR linking #4; verify remote CI and report checks. [Draft PR #14](https://github.com/mesilov/gitlab-ci-performance-skill/pull/14) is mergeable; Python 3.10/3.12 checks passed.
- [ ] Merge and publish v2.0.0 after integration/release approval. The local release candidate has been packaged and smoke-tested from an extracted installation.

## Coverage checks

All eight acceptance checklist items in #4 map to tasks 1–6: schemas/semantic validation (1), source bounds/status cases (2), parser edge cases (3), interval and baseline regressions (4), numeric parity/units/determinism/legacy (4–5), documented budgets/provenance/installed verification (6). Full visual and translation acceptance remain in #3/#2.

## Execution notes

Implementation was committed as one tested integration change (`74eeca4`) after focused module checks and review, rather than separate commits per module. The latest `main` (`ec247f7`) was merged before delivery; existing 1.0/1.1 report localization and release history remain supported under the explicit legacy path. See [verification evidence](../verification/2026-10-04-report-json-v2.md).
