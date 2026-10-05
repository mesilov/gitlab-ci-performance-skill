# Original-log contract implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the isolated windows task and review. Follow test-first steps; shared contract and template edits are coordinated by the parent.

**Goal:** Implement the supplied 64 MiB / 16–32 windows / original log specification on verified main.

**Architecture:** Keep collection, calculation and rendering separate. Add lossless trace source storage with physical line references, bump incompatible canonical versions, preserve calculation policies.

**Tech Stack:** Python 3.10+, jsonschema, static HTML/JS, unittest, offline Playwright.

- [x] Windows: add failing count/navigation/cohort tests in tests/test_original_windows.py; run `python3 -m unittest discover -s tests -p test_original_windows.py`; implement materialized 16/32 pages in report_calculate.py, semantic page bounds in report_contract.py, size selector/default in report-v2.html, schema window enum/page bounds. Preserve retention/baseline; run window and calculation tests.
- [x] Source/size: add failing lossless source, long header, full identity, multibyte/exact boundary and CLI tests in tests/test_original_source.py; run those tests before editing parser. Implement canonical 3.0.0/parser 2.0.0, 64 MiB load/validate/save, trace raw_base64 and explicit evidence-limit provenance, original labels and full identity references; update schemas/fixtures and verify parser/contract tests.
- [x] UI: add offline browser assertions for source/copy/injection and 16/32 navigation. Render original source through textContent, selectable preformatted text and copy controls, no automatic text omission. Run browser tests in both languages/themes and mobile/keyboard/offline mode.
- [x] Delivery: update canonical docs/SKILL/examples, record starting SHA and compatibility, run complete tests and installed-skill checks, inspect spec compliance then code quality with reviewer subagents. Freshly collect real GitLab when available and report verified limits/artifact paths. Never edit generated HTML manually.
