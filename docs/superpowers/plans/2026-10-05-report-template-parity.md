# Report template parity implementation plan

**Goal:** Fix #16 by applying the reviewed report's visual hierarchy to the canonical renderer.

**Architecture:** Keep the two JSON contracts and their calculations separate. Change the installed canonical HTML template, selecting and formatting only saved values. Reuse the reviewed template's white/dark palette, Helvetica typography, 1136px content width, thin dividers, compact cards and three-column priorities.

**Tech stack:** Standalone HTML/CSS/JavaScript, Python CLI, unittest, Playwright.

- [x] Compare supplied local reports and trace each renderer to its shipped template. Publish a technical issue without private report data.
- [x] Add browser assertions to `tests/browser_v2.cjs`; run against the original synthetic render and observe failure at the localized heading.
- [x] Change `assets/report-v2.html`: concise localized heading, scope/context, baseline/outcome cards, priority coverage/caution, collapsed history, latest-attempt metadata and structured evidence. Preserve IDs, saved numeric values and precomputed selections.
- [x] Extend browser checks across all selections, en/ru, 320/375/1280px light/dark, keyboard focus, boundary/empty cases and standalone offline relocation.
- [x] Run `.venv/bin/python -m unittest discover -s tests -v`, generate synthetic examples, run canonical and reviewed browser suites, and render from a clean skill-only installation.
- [x] Regenerate public synthetic canonical previews, document contract/UI separation and record verification. Review the diff and fix both mobile readability/evidence-navigation findings.

Delivery: commit and push `codex/report-template-parity`, then open the requested fixing PR linked to #16 after the final verification passes.

No private source snapshots or screenshots belong in the published change. Legacy/reviewed/workflow templates retain their own saved-data semantics. Numeric differences between independently collected reports are outside this UI fix.
