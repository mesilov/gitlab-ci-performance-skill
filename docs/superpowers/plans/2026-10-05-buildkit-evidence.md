# BuildKit evidence repair

Base: current `origin/main`, `082313a4cd1352cddd6f0eac6d4e6039a03401da` (fetched before creating `codex/buildkit-log-identity`). No release, tag or VERSION selected the source.

For agentic workers: apply subagent-driven-development for the contract task and review; use test-driven-development and verification-before-completion throughout.

- [x] Establish baseline: 214 tests pass; add the supplied export regression in `tests/test_trace_v2.py` and observe 3 images instead of 1.
- [x] Repair `report_trace.py`: recognize only genuine headers, keep export progress under its source step, distinguish banner boundaries and redraws, preserve source IDs and safe image identity/provenance. Keep bounded evidence and explicit partial coverage.
- [x] Version the canonical contract as 2.1.0 / parser 1.1.0. Per explicit user instruction, support only the new contract; reject old sources/reports and remove canonical CLI legacy routes. Add closed schema fields `buildkit` (source step ID) and image-only `identity` (known/unknown/conflicting/redacted, safe basename, naming/unpack source and source line range). Update collector/calculator/examples/fixtures/docs and contract tests.
- [x] Render safe image names and original BuildKit IDs in `assets/report-v2.html`, with honest unknown/conflicting/redacted identity. Verify compact export parity.
- [x] Test consecutive identical-banner builds, progress redraws, cached/error/canceled/partial logs, limits, secret rejection and non-additive nested timing. Run `.venv/bin/python -m unittest discover -s tests -v`.
- [x] Re-fetch job 252624 in bounded memory, compare source hash and inspect safe output; save only structured evidence, never raw trace. Generate fresh JSON/compact/HTML and verify offline RU/EN desktop/mobile with existing browser checks and targeted identity assertions.
- [x] Review changes, run `git diff --check`, record measured results and before/after in documentation.

Delivery: publish the verified branch as a reviewable PR and attach it to this chat; do not merge it.
