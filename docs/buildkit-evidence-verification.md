# BuildKit evidence repair — 2026-10-05

## Original operation titles

The operation-title repair started from freshly fetched `origin/main` at
`c5efce665c20168d807b79b95a5bbed09640ab99`; release tags and `VERSION` were not
used to select sources. Parser 1.2.0 stores a separate safe `source_label` with
original/redacted/unavailable state, BuildKit header/progress origin and physical
line range. Fixed safe titles such as `[internal] load build context` and
`exporting to image` remain exact. Dockerfile instruction arguments, destinations,
stage names and other variable text are not exported; the safe structural form
uses `[redacted]`. The category code remains unchanged for calculations and is
shown separately in the localized UI. English/Russian rendering does not alter
the source title.

Verification for this change:

- `python -m unittest discover -s tests -p 'test_*.py' -v`: 251 tests passed.
  The first RED run failed because `source_label` was absent; regressions now
  cover exact headers, same-category distinctions, nested export operations,
  ANSI/timestamp redraws, reused IDs, unsafe/long input, contracts and unchanged
  category calculations.
- The locally available trace for job 252624 has SHA-256
  `9f9de41f9b9f03b023aff4283e90f72c38cab2980d745c884b85bf52cd5234e5`,
  matching the saved report. Lines 105, 221 and 497 produce the exact accepted
  labels for steps 1, 8 and 16. The result remains 8 named complete image builds,
  126 evidence nodes, 99,449 serialized bytes and no evidence-limit truncation.
- Full report and selected-attempt compact JSON validate under schema 2.2.0;
  RU/EN HTML embed identical source data. Offline Chrome passed for both languages
  at 320/375/1236 px in light/dark mode, including 8 real groups, 88 operations,
  6 cached operations, keyboard navigation, no external requests and no JS errors.

Implementation started from freshly fetched `origin/main` at
`082313a4cd1352cddd6f0eac6d4e6039a03401da`, on
`codex/buildkit-log-identity`. No release, tag or VERSION selected the source.

## Cause and resulting behavior

`report_trace.py` classified every `exporting ...` frame as a new header. A
different manifest/config header for the same step triggered `new_image()`.
The closed evidence contract also dropped image identity and source step IDs,
so HTML could only show anonymous ordinal fragments.

Only `exporting to ...` starts an export now. Manifest/config/layers/naming/unpack
stay under their original operation, preserving physical source ranges. Explicit
identical banners after a completed export with all admitted operations complete,
or failure/cancellation, separate invocations; early/active redraws do not.
Genuine changed headers without a clear boundary remain separate partial evidence.
Supported FROM layer progress updates a cumulative DONE checkpoint without sums;
unsupported contradictory measurements remain partial. Completed redraws retain
source lines without extending image timing.

Canonical schema/calculation is 2.2.0, parser is 1.2.0. `buildkit.step_id` retains
the source number; image `identity` records a safe basename, naming/unpack origin,
source step and physical range. Registry/path/tag/digest are discarded. Unsupported,
conflicting and sensitive-looking identity stays explicit. Commands, credentials,
environment and raw trace text are absent from exports.
The canonical CLI supports only this new contract; old routes/artifacts are rejected.

## Verification

- Baseline: 214 tests passed. The supplied minimal log failed with 3 images;
  after the fix it gives 1 image, 2 operations and nested export measurements.
- Final: `python -m unittest discover -s tests -v` — 244 passed in 33.247 seconds.
  Regressions cover identical banners/IDs, early redraw, active parallel work,
  cumulative FROM, repeated completed export/CACHED/bare DONE, conflicting names,
  provenance resolution, secret sentinels, failed/canceled/partial logs and limits.
- Runtime admission is capped at 152 nodes. Maximum-length timestamped identity
  and title fixture: 128,837 bytes, below the unchanged 128 KiB summary cap. Excess nodes
  mark `partial/evidence_limit`; known nodes still receive closures and identity.
  Input remains 4 MiB/50,000 lines, full/compact payloads remain 16 MiB.
- Referenced real job was re-fetched through existing glab authentication in
  bounded memory. Hash matched the saved report. Before: 16 anonymous fragments,
  120 nodes, `evidence_limit`. After: 8 named complete builds, 126 nodes, 77,383
  summary bytes; one export step retains its original 9-line range. No raw trace
  was saved or committed. Local private verification artifacts remain outside Git.
- That real trace remains explicitly partial for its early `prepare_executor`
  phase, whose offsets cannot be resolved by the current section parser. All 8
  BuildKit image nodes are complete; no evidence budget truncation remains.
- Full JSON, selected-attempt/window exports and RU/EN embedded HTML retained
  exactly equal evidence; overview external references validated.
- Offline Chrome: all 8 real groups and 88 operations, including 6 cached steps;
  identity/source-number/source-line parity, keyboard navigation, 320/375px mobile,
  1236/1280px desktop, light/dark, standalone relocation, no network/JS errors.
  RU/EN synthetic identity cases also passed: known, unknown, redacted, 128-character
  basename. Their generator and browser assertions are included in CI.
- Independent review found two timing/boundary regressions; both were reproduced
  with failing tests and fixed. Final review reported no actionable findings.

Display example: `Build fragment 1 / 1. Export ...` becomes
`service / #16 Export ...`, with identity provenance and original source lines.
An unconfirmed identity displays `Unknown image N` / `Неизвестный образ N`.
Durations of parent/child or overlapping operations are never added.

Operation-title example: `#8 Контекст сборки / копирование` now appears as
`#8 [internal] load build context` in both UI languages. The localized
`Контекст сборки / копирование` / `Build context / copy` category remains in the
evidence explanation and calculation data. `#16 exporting layers` is preserved
as a nested measurement; `unpacking to <destination>` is saved and displayed as
`#16 unpacking to [redacted]`.

Identical IDs/headers without an export/failure or other observable boundary
cannot reliably establish another invocation. No project-specific parsing rules
were added. The checked-in canonical synthetic example was regenerated through
the current generator, rather than converted from a saved old report.
