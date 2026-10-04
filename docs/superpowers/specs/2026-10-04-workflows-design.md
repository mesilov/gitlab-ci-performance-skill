# Workflow analysis (issue #6)

The issue authorizes implementation and a reviewable PR. Preserve v1 job-only
artifacts. Introduce v2 workflow definitions, bounded pipeline snapshots and
reports as separate artifact kinds; do not reinterpret saved v1 calculations.

Definitions are supplied by the agent after inspecting resolved configuration.
The helper stamps configuration byte hashes and validates stable IDs, exact
name/stage selectors, dependency DAGs, required/manual policy, parallel groups
and explicit historical pipeline/commit coverage. Current configuration never
implicitly covers old runs. Independent operations produce separate series.
Cross-pipeline relationships remain unsupported and are reported explicitly.

Collect 32 or 64 pipelines, with all constituent attempts including retries,
bounded pagination, immutable anchors and per-pipeline partial coverage. No
trace requests are needed. Report calculations use latest attempts for outcomes
and all retained execution intervals for timing. Missing data stays nullable;
known partial unions and queue sums carry counts and exactness flags.

Canonical JSON contains definitions, source hashes, selected-window job view,
run/attempt membership, outcomes, interval unions, histories and comparable
baselines. Cohorts isolate definition version, selection policy, ref and pipeline
source. Compare the latest complete successful measurement to at most ten earlier
eligible measurements, requiring three. Export sample IDs and undefined zero
baseline percentages. Compact LLM export and HTML consume these same results.

The offline HTML uses the existing neutral execution, gray queue, red failure
and blue selection palette. Workflow/operation selection leads to dependency
diagram, separate elapsed/active history, pipeline, job and attempt details.
32/64 controls select pipeline windows, charts fit mobile, unavailable values
have explicit markers, and English/Russian display is selectable. Display units
switch to minutes only when a value in the selected series exceeds 300 seconds;
JSON stays in seconds.

Validate with synthetic sequential/parallel/manual/retry/failure/unknown/version
fixtures, mocked bounded API collection, schema and canonical export checks,
offline desktop/mobile keyboard browser checks and a copied-install CLI smoke
test. Package the complete skill as release 2.0.0, documenting v1 compatibility.
