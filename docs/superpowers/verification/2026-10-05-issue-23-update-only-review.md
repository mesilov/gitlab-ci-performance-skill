# PR #25 review: install/update-only completion

Date: 2026-10-05 (Asia/Bishkek).
Base: `83b50e77f9a068201d25aa29b716c9a926492328` (merged PR #25).
Review: <https://github.com/mesilov/gitlab-ci-performance-skill/pull/25#discussion_r4182774579>.
Scope: instruction/documentation correction; runtime, schemas, templates and CI unchanged.

## Baseline and correction

A fresh read-only agent planned an update-only request with verified upstream
commit, complete replacement and available dependencies, but no project or saved
report inputs. It concluded the report route was still mandatory, quoting the
installation table's unconditional “run the documented route using the installed
helper” and the equivalent contract instruction. It would need to obtain unrelated
inputs or collect from GitLab to finish the update.

The corrected table and installation prose require a local selected-entrypoint
`--help` check for install/update-only requests. Completion reports the installed
directory and resolved commit. The report route is conditional on a report request;
CLI startup is explicitly distinct from end-to-end report behavior. Both READMEs
and the canonical reference use the same condition.
README requirements also limit GitLab authentication to collection; local help
and offline commands need no GitLab authentication.
While preparing the correction, main advanced to `e43865e` with PR #27's README
rewrite and PR #28's keyboard navigation. The branch merged that main and retained
the new README structure while applying the same conditional installation checks.

## Revised-instruction scenarios

A separate fresh read-only agent reviewed SKILL.md, contract-v2.md and both
READMEs without executing reports/tests:

| Scenario | Observed decision |
|---|---|
| Install only; no project or saved inputs | Verify provenance/files/dependencies, installed-helper `--help`, directory and commit; no GitLab collection or extra inputs. |
| Update only; dependencies ready, no project or saved inputs | Same local completion; no mandatory report route or full test/QA suite. |
| Update plus canonical report; project supplied | Installed-helper report route with built-in validation and result link; collection is for the requested report. |
| Update plus offline render; compatible saved report supplied | Render offline through installed helper and return link; no fresh collection. |

No blocking contradiction in the installation/report conditions was found.
These are instruction-interpretation checks, not end-to-end runtime tests.

## Local entrypoint smoke

Copied only `skills/gitlab-ci-performance` into a temporary directory outside the
checkout, excluding Python bytecode. Ran each copied helper with `--help`, no
project and no saved inputs. A Python audit hook rejected network connection/DNS,
child-process, shell and posix-spawn events inside the helper process:

- `report_cli.py --help`: exit 0, usage output present.
- `ci_report.py --help`: exit 0, usage output present.

The initial runpy harness omitted the copied script directory from `sys.path` and
failed to resolve `report_contract`; correcting the harness to mirror direct-script
Python startup produced both successful results. No skill code was changed.

Whitespace and documentation-only diff scope were checked. Full local regression
and browser suites were not rerun for this documentation correction; repository
CI remains configured.
