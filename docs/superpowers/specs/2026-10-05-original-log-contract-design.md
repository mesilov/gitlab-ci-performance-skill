# Canonical original-log contract

User-supplied specification: JSON 64 MiB, attempt windows 16/32, original logs without masking. Starting origin/main: `70761551beb0f589aa221d078002187faa872c64`. Scope: report_cli.py collect → report → export → render only; legacy ci_report.py behavior remains separate.

## Design

Canonical schema/calculation 3.0.0 and trace parser 2.0.0 explicitly reject earlier masked artifacts. Retain allowlisted metadata projections and unchanged timing/category inference. Store received log bytes once per trace as base64 (lossless for control sequences and invalid UTF-8), with physical line indexing. Evidence source fragments refer to those lines rather than duplicating full logs per node; operations carry their original complete headers. Image identities carry complete references and a short display name. Full source survives source/report/attempt export and offline HTML; rendering uses textContent, JSON script escaping, selectable preformatted text and copy controls. Display parsing removes ANSI/outer CR and transport timestamps only for recognition; original bytes remain available and physical lines remain based on LF.

Size checks use actual canonical serialized UTF-8 bytes, allowing exactly 67,108,864. Raw file reads are bounded before decoding; HTML byte writes have no JSON-size cap. Replace the old 128 KiB summary ceiling with an explicit 16 MiB per-trace ceiling, raise evidence admission to 4096 nodes, and expose the first omitted physical line and reason. Preserve the complete received source even when evidence admission reaches its cap; no long-title truncation. Input transport bounds remain 4 MiB / 50,000 physical lines with prefix hashes on truncation.

Materialize all pages for sizes 16 and 32 from retained history up to 64 attempts. Links only connect equal-size adjacent pages; size switching selects page zero. No baseline changes.

## Acceptance

Tests first: exact payload byte boundaries including Cyrillic; greater-than-16-MiB complete CLI report/export/render; window counts 0/1/16/17/32/33/64; full argument/reference/header/raw fragment preservation; injection escaped; previous image session/redraw/numeric behavior retained. Run unit/CLI, installed skill and offline desktop/mobile keyboard browser checks. If GitLab access exists, freshly collect project 2967 and verify job 252624 has eight image builds; otherwise provide synthetic reproduction. Reports from real logs stay local.
