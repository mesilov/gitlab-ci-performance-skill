# Detailed attempt timeline parity

The supplied reference uses compact selectable timelines rather than an expanded
tree of evidence cards. The renderer must support the same interaction sequence:
select a build group, select an operation, inspect its measurement source.

1. Capture the reference and current renderer at matching desktop widths; compare
   structure, axes, selection and measurement provenance.
2. Reproduce missing drilldown structure with a failing browser regression.
3. Replace evidence cards in the canonical HTML template with group/operation
   timelines, collapsed phase/metadata panels and selected evidence/substeps.
4. Preserve saved evidence IDs, parents, numeric values and partial/cache/unknown
   semantics; test all attempts and priority-navigation targets.
5. Re-render saved inputs through the installed CLI into a new file, validate a
   clean skill-only installation, and update the existing template-fix PR.

The user also supplied a direct comparison of the priority panel. Match its gray
framed surface, short lead, vertical numbered action rows, right-aligned per-run
median and inline evidence/guidance links. Put detailed coverage and uncertainty
in a collapsed subsection, preserving their saved values and availability states.

The canonical contract intentionally omits image names and original BuildKit step
numbers. Existing parser sessions can be ambiguous or bounded. Presentation must
not reconstruct missing names, merge fragments, copy measurements from a different
contract, or disguise fragments as distinct complete image builds. Parser changes
are separate from this template correction.
