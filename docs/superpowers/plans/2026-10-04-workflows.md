# Workflow Analysis Implementation Plan

**Goal:** Complete GitHub issue #6 and open a PR after verification.

**Architecture:** Keep the v1 helper route intact. Implement v2 workflow contracts,
collection and calculation in `scripts/workflow_report.py`, exposed through
`scripts/ci_report.py`. A maintained offline template consumes canonical values.

**Tech stack:** Python 3.10+, jsonschema, plain HTML/CSS/JavaScript, unittest,
Playwright with offline Chrome. Execute in the existing isolated worktree.

- [x] Add synthetic fixtures and failing calculation/collection contract tests
  in `tests/test_workflows.py`. Run `.venv/bin/python -m unittest discover -s tests -v`.
- [x] Implement definition validation and versioned schemas in `schemas/`;
  implement interval unions, outcomes, cohorts and exact sample comparisons in
  `scripts/workflow_report.py`. Run the focused suite until it passes.
- [x] Add pipeline-first collection with bounded per-pipeline pagination and
  recorded partial coverage. Wire definition creation, workflow report, render,
  validation and compact export into the installed CLI; test all routes.
- [x] Add `assets/workflow-report.html` with shared selection, offline charts,
  dependency diagram, attempt drill-down, units and language controls. Verify
  canonical parity, keyboard selection, 300-second boundary and mobile layout
  using `tests/workflow_browser_check.cjs`.
- [x] Publish generic examples, `references/workflows.md`, CLI guidance in the
  skill and both READMEs, release metadata and CI installed-package smoke checks.
- [ ] Run all tests, schema validation, demo/installation smoke, legacy and
  workflow browser QA, inspect screenshots, request independent code review,
  fix findings, commit, push and create/attach the PR linked to issue #6.
