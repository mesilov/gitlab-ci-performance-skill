# Report JSON v2 verification — 2026-10-04

Issue: [#4](https://github.com/mesilov/gitlab-ci-performance-skill/issues/4).
Approved [design](../specs/2026-10-04-report-json-v2-design.md) and
[implementation plan](../plans/2026-10-04-report-json-v2.md).

## Local automated evidence

- `.venv/bin/python -m unittest discover -s tests -q`: **120 tests, OK**
  (18.519 seconds, Python 3.14.7). Includes schema/semantic rejection,
  bounded mock API transport/cache/resume, parser→calculation overlap regressions,
  independent baselines, canonical/compact parity and installed CLI round trips.
- Both legacy versions **1.0/1.1** validate/render. Installed legacy generation
  retains configurable windows/thresholds and explicit release refs.
- Language override keeps canonical embedded JSON unchanged. Unsupported languages
  and v2 use of legacy window/threshold options fail before output creation.
- Standalone `examples/generate_release_demo.py` runs outside the checkout.
  A new subprocess regression reproduced the missing-helper import before correction.
- Source/full/compact synthetic examples validate through the maintained entrypoint.
- `git diff --check`: no whitespace errors.

The metadata transport is exercised with mock API responses, not a live GitLab
project. No private source or trace fixture is published. The documentation route
from #5 remains intact; no recommendation is newly marked as source-verified.

## Offline browser evidence

`tests/browser_v2.cjs` was run in headless Chrome/Playwright with an offline browser
context against both HTML languages. Each run passed:

- 2 job types, 6 materialized windows, 128 retained attempts.
- Every job/window/attempt selection, JSON numeric parity and evidence references.
- Representative links preserve category cost and select their documented evidence.
- No horizontal page overflow at 320px, light/dark screenshots, moved standalone file.
- No JavaScript errors or external network requests.

Synthetic runner queue and BuildKit inferred-position uncertainty remain explicit.
Browser screenshots were inspected at desktop/mobile widths. Full v2 translation
and reviewed visual acceptance remain owned by #2/#3.

## Payload and installed package

The full 128-attempt synthetic source is **699,607 bytes**, canonical report
**2,119,021 bytes**, overview **846,286 bytes**. The checked-in 8-attempt source,
full report, overview and HTML total **539,948 bytes**. Runtime JSON payload cap
is 16 MiB; documented collection/evidence bounds apply independently.

A local `gitlab-ci-performance-2.0.0.tar.gz` candidate contains only the installed
skill (without Python caches), **81,425 bytes**, SHA-256:
`c03a2691781a1fa4cabc48a77ba4e2a7be8de66871b4e63dbaef63a6a3466f0d`.
It was extracted to a temporary directory outside the checkout. Ten installed
CLI commands passed: help, source/full/compact validation, v2 generation/export,
Russian rendering, legacy 1.0 validation and legacy 1.1 generation/Russian rendering.
Regenerated canonical v2 JSON matched the checked-in example byte for byte.
Only synthetic saved sources were used; no network request was made by this smoke.

Local reports/package/status artifacts remain in ignored `reports/`.
The archive is a **local candidate**, not a published release. Publishing v2.0.0
and merging follow the approval gate in the design. Remote PR/CI results are
recorded at delivery; neither a local smoke nor this document closes that gate.

## Remote delivery

[Draft PR #14](https://github.com/mesilov/gitlab-ci-performance-skill/pull/14)
was created and attached to the Codex chat. GitHub reports it as mergeable.
For implementation commit `643a634109d989fe3ab10feb56dc7a272af4b1b9`, both
[push CI](https://github.com/mesilov/gitlab-ci-performance-skill/actions/runs/37214110241)
and [PR CI](https://github.com/mesilov/gitlab-ci-performance-skill/actions/runs/37214129444)
passed on Python 3.10 and 3.12. The matrix includes the full unit suite, legacy
validation/generation and localized rendering, bounded v2 demo generation,
canonical/compact validation and Russian v2 generation/rendering.
This delivery record changes documentation only; final head CI is checked before
handoff. The issue remains open pending authorized integration and publication.
