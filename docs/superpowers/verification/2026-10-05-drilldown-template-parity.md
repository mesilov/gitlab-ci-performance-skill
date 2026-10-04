# Reference priority panel and attempt drilldown

The canonical template now uses the supplied reference's framed vertical
action-priority list and two-level compact timing rows. Priority category costs
and representative durations remain separate saved values. Technical coverage is
collapsed, while missing guidance stays explicit rather than becoming a link to
an unverified source.

## Regressions and fixes

- The initial browser check failed because the reference-style drilldown did not
  exist. It now supports group selection, relative operation axes, source lines,
  nested measurements, keyboard focus and unknown/cached durations.
- The priority-panel regression failed on the missing lead and three-column
  layout. It now checks the gray surface, vertical action rows, inline links,
  right-aligned medians and visible known/missing sample counts against JSON.
- Review exposed inaccessible group-level source/quality/push metadata, an
  incorrect API-start claim for log-relative offsets, loss of root-operation
  compatibility, and focus loss when navigating deeper operation trees. These
  were fixed and covered by browser checks.
- `examples/generate_v2.py --root-operations` authors public synthetic saved
  evidence with root → operation → operation → part. Hosted browser CI runs it.

## Validation

- 214 unit/CLI checks passed after the final changes.
- The offline browser suite visited every retained attempt and supported window
  in the local saved sample. It checked numeric parity, evidence IDs/parents,
  priority targets, keyboard behavior, mobile overflow, light/dark presentation,
  relocation and absence of external requests or JavaScript errors.
- Dedicated drilldown checks visited known, cached and unknown intervals, group
  provenance and nested substeps. The public root-operation fixture passed.
- A fresh copy containing only the installed skill rendered the unchanged public
  canonical JSON; its browser checks passed.
- Embedded JSON in the regenerated local report is deeply identical to the saved
  input. Re-rendering does not mutate calculation/parser/schema metadata or
  original artifacts. Private data and screenshots remain local.

## Presentation limits

The canonical closed evidence vocabulary omits image names and original BuildKit
step numbers. Ambiguous sessions and evidence budgets can produce fragmented or
partial measurements. The renderer labels those saved fragments honestly; it does
not merge them into complete images, borrow measurements from the reference, or
claim that differently computed priority costs are visual differences.
