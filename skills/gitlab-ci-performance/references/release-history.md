# Release history — calculation version 1.1.0

Use `report --legacy --release-refs REF [REF ...]` with a 1.0 source snapshot for an explicit exploratory selection
from the current snapshot. Ref values are exact, case-sensitive strings, with
no wildcard expansion or automatic tag inference. Empty/duplicate selections
and refs absent from pipeline metadata are errors. A single selected ref is
allowed, but has no cross-ref evidence by itself. Branches and tags share the
API ref field; this mode does not infer ref type from names.

The v2 workflow uses `--comparison-mode cross_ref --ref REF` with v2 sources;
see [contract-v2.md](contract-v2.md) for its independent 32/64 attempt windows
and baseline policy. The method below remains the legacy 1.1 behavior.

## Selection and grouping

The optional `release_history` section groups project + stage + job name across
the selected refs. Existing `views` still group project + ref + stage + job name.
Original jobs and pipelines, source hashes, refs and attempt IDs remain intact.
No additional GitLab API calls or logs are needed. Any collection coverage
limits of the source snapshot also apply to release history.

Every selected attempt is referenced by ID in `attempt_ids`. Order is pipeline
creation timestamp, then pipeline ID, then attempt ID, all ascending. This is a
release/pipeline time axis, not job start time: manual jobs may execute later.
The browser's 32/64 attempt window selects the tail of these IDs for display.
These windows do not truncate the snapshot or change the comparison baseline.

## Successful samples and comparisons

For each group, choose the latest successful pipeline containing a successful
attempt of that job, and up to `--baseline-window` preceding eligible pipelines
(default 10). Preserve all attempts within those pipelines. `current_attempt_ids`
and `baseline_attempt_ids` include failed reruns; the cohort's metrics include
only successful attempts. Multiple successful reruns contribute separate
measurements, as in same-ref analysis; N counts attempts, not pipelines.
The period fields give exact pipeline IDs and actual pipeline counts.

The default policy requires at least three distinct baseline pipelines with a
known successful measurement, as well as its measured-attempt minimum. Reruns
of one pipeline cannot supply independent baseline observations. Execution and
queue eligibility are calculated separately. Null remains missing; zero is a
known measurement. Relative change against zero is null.

Thresholds use the existing P50 policy (both +20% and +30 seconds by default).
Statuses are `observed_increase`, `observed_decrease`, `no_observed_change`, or
`insufficient_data`. They never assert a confirmed regression. A failed/latest
attempt remains visible even when an earlier successful pipeline supplies the
current timing sample. Pipeline and job outcomes remain distinct.

An external `--baseline` affects only same-ref `views`. Release history always
uses the explicitly selected refs from the current snapshot; its `source` records
`current_snapshot`. Comparison IDs may extend outside the visible 32/64 window.

## Context and uncertainty

For both samples, record refs, pipeline sources, commit SHAs, runner IDs and
missing runner metadata. Flag differing refs, sources or runners. A runner ID
does not prove unchanged hardware/load; source identity does not prove identical
job scripts, images, caches or environment. Always record configuration coverage
as unverified and avoid attributing a duration change to any specific cause.
The purpose catalog describes verified configuration, not every historic version.

## Rendering and compatibility

The offline chart separates API job execution from runner queue time, with queue
above execution. Its stack is execution + queue, not pipeline wall time or total
lifecycle. Missing components show `?` and no fabricated segment. Failed/canceled
attempts remain selectable and are labelled ineligible for successful cohorts.
All machine values stay in seconds. Chart/selected comparison values use minutes
when the visible stack or compared P50 is strictly above 300 seconds; otherwise
seconds. Keyboard Enter/Space selects attempts, with original ref and links.

New report and calculation versions are 1.1.0. `release_history` is required and
null unless explicitly requested. Jobs snapshots remain 1.0.0. The current report
schema and renderer accept legacy report/calculation 1.0.0 without this field.
The old 1.0.0 helper cannot read new 1.1.0 reports. Update the installed skill as
a whole, keeping helper, schema and template together. Recalculate a jobs snapshot
to create a new report; never relabel an old report's version in place.
