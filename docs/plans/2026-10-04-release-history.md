# Release job timing history — issue #1

Goal: explicitly select release refs and inspect per-job execution and runner
queues across them while keeping same-ref analysis as the default.

Design: add `report --release-refs REF [REF ...]`. Exact refs only, no automatic
tag inference. Keep source jobs/pipelines intact. A separate release_history
payload groups stage/name, includes every selected attempt, and compares the
latest eligible successful pipeline with up to ten preceding eligible pipelines.
Failed attempts remain visible but are excluded from successful timing cohorts.
Retain null measurements, reruns, sample IDs, sample sizes and available context.
Cross-ref threshold changes are observations, never confirmed regressions.

Report/calculation version becomes 1.1.0; jobs stay 1.0.0. Legacy 1.0.0 reports
remain renderable; new reports explicitly carry null or release_history.
The HTML adds a separate job selector, stacked execution/queue history and
keyboard-selectable attempts with original refs, status, SHA, source and runner.
Reuse existing CSS tokens and offline SVG rendering; no dependencies or logs.

- [x] Establish the original 22-test baseline in a local dependency environment.
- [x] Add failing release selection, timing, context and compatibility tests.
- [x] Implement deterministic payload, strict schema and CLI integration.
- [x] Add the optional HTML section and offline browser checks.
- [x] Document selection, eligibility, uncertainty and version compatibility.
- [x] Run unit tests, legacy/new CLI smoke, installed-copy smoke and desktop/mobile QA.
