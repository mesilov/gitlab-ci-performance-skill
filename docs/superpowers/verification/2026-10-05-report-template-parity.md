# Report template parity verification

Issue: [#16](https://github.com/mesilov/gitlab-ci-performance-skill/issues/16).

## Reproduction and scope

The canonical renderer used a distinct rounded-panel layout, technical dated
heading, always-expanded history and no initially selected attempt. The reviewed
renderer already supplied the requested visual reference. A new browser assertion
failed before implementation at `How CI is performing`: the original renderer
returned its dated technical heading.

The fix changes the installed canonical template and its synthetic HTML example.
It preserves the saved JSON, calculation/parser versions, window membership,
selection, baseline samples and category medians. Reviewed, workflow and v1
templates are unchanged. Shared presentation does not merge their evidence or
queue-spike policies. Private comparison reports stay local.

## Review corrections

Independent review reproduced two additional issues: a fixed SVG viewBox reduced
mobile axis text to 3.24px, and Inspect selected evidence without moving the
viewport/focus. The template now measures its chart width, matches mobile height,
and redraws on resize. Inspect focuses its evidence button (or detail heading)
and moves the destination into view. Browser regressions enforce readable text
and a focused visible destination on all tested widths. A second independent
review confirmed 11px chart text after resizing and visible focused evidence in
both languages, with no remaining blockers.

## Checks on 2026-10-05

- `.venv/bin/python -m unittest discover -s tests -v`: **212 tests passed**.
  This includes copied-skill CLI round trips and immutable payload validation.
- Generate a fresh canonical demo with `examples/generate_v2.py`; run
  `tests/browser_v2.cjs` in en/ru: **128 retained attempts, 6 windows, 2 job types**.
  Check every attempt/window, numeric findings, priority evidence IDs, nested
  parents, latest selection, keyboard activation and consistent detail units.
- Generate a reviewed demo with `examples/generate_reviewed.py`; run
  `tests/browser_reviewed.cjs` in en/ru: **both passed**.
- Public canonical example and a clean skill-only copied renderer: **both browser
  suites passed**, 8 retained attempts and 4 windows; copied-skill Russian HTML
  was byte-identical to the repository renderer's output.
- All browser suites: **320/375/1280px, light/dark, no page overflow**, including
  expanded history; relocated standalone HTML; safe HTTPS links; **no HTTP requests,
  browser errors or console warnings**. The template uses the reviewed layout.
- Extra synthetic CLI renders: **empty history**, exactly **300 seconds → seconds**,
  **300.01 seconds → minutes**, matching detail units, and 320/1280px checked in
  offline Chrome without errors.
- `git diff --check`: **passed**.

Browser: local headless Chrome through bundled Playwright. These are local
measurements; hosted CI status is reported separately by the pull request.

## Reproduce the maintained browser checks

```sh
.venv/bin/python examples/generate_v2.py --output-dir reports/template-demo
.venv/bin/python skills/gitlab-ci-performance/scripts/report_cli.py render \
  --report reports/template-demo/report.json --language ru \
  --output reports/template-demo/report-ru.html
node tests/browser_v2.cjs "file://$PWD/reports/template-demo/report.html" reports/qa-en
node tests/browser_v2.cjs "file://$PWD/reports/template-demo/report-ru.html" reports/qa-ru
```

Set `CI_REPORT_PLAYWRIGHT` to the installed Playwright module path if required.
Hosted CI runs the same canonical and reviewed browser checks automatically.
