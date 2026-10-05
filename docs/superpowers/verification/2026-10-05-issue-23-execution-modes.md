# Issue #23: execution-mode instruction verification

Date: 2026-10-05 (Asia/Bishkek).
Base: `331dcb7c015e712df72cf3dde9c58d08d3e49c6a`.
Scope: instructions/documentation only; no runtime, schema, template or CI changes.

## Baseline

A fresh read-only agent read the original SKILL.md, contract-v2.md and README.md
and planned successful report, upstream-update and offline-render scenarios.
It did not execute reports or repository tests.

For a ready upstream update, it chose:

> Treat the update as a change: run **unit/CLI checks, synthetic desktop/mobile browser QA and skill-only install/update smoke** before completing the updated workflow.

The agent identified the ambiguous rule:

> “After changes” does not expressly distinguish authored changes from installing an upstream change.

For saved untrusted input, it also read the standalone `validate` instruction
as mandatory even when the consuming render command validates that input.
These decisions reproduce the redundant-check paths described in issue #23.

## Revised-instruction scenarios

A separate fresh read-only agent read the revised SKILL.md, contract-v2.md,
workflows.md and both READMEs. It planned these scenarios without running tests
or generating reports:

| Scenario | Observed decision |
|---|---|
| A: new logs, successful commands, urgency/accuracy pressure, browser tools available | Documented route and report link; no extra test/QA campaign or duplicate validation. |
| B: ready official upstream commit with new schema, large successful report, historically quick tests | Verify commit provenance, replacement and dependencies; installed route and link; no automatic test/QA campaign. |
| C: compatible saved report, successful offline render, link-only request | Offline render and link; no collection or duplicate validation. |
| D: independently loaded artifact consumed without equivalent validation | Standalone validation at that boundary; no full suite. |
| E: semantic validation failure on a trace edge case | Minimal reproduction, repository regression for the new case and affected-workflow verification; preserve validation. |
| F: authored parser and HTML template changes | Affected unit/CLI/regression, packaging smoke and renderer browser QA as relevant. |
| G: explicit full acceptance request | Execute requested full acceptance scope; no ceremonial duplicate validation. |

Result: all seven instruction scenarios selected the intended check scope.
The agent found no conflicting requirements in the revised execution/check policy.
This is evidence of instruction interpretation, not an end-to-end runtime test
or a guarantee of every future agent's behavior.

## Local checks

- `git diff --check`: passed.
- Newly added relative Markdown links and heading anchors: five checked, all resolve.
- Diff scope reviewed: only Markdown files; built-in validators and CI unchanged.
- Full local unit/CLI, install/update and browser suites were not rerun for this
  documentation-only change. The existing repository CI remains configured.
