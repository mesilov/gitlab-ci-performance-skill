[English](README.md) | [Русский](README.ru.md)

# GitLab CI Performance Analyzer

Reusable agent skill: safe GitLab metadata → bounded trace evidence →
reproducible calculations → standalone offline report.

![Synthetic reviewed report](docs/report.png)

The [English example](examples/reviewed/report.html) and
[Russian example](examples/reviewed/report-ru.html) contain synthetic data only.
Download an HTML file and open it locally; it works without sidecars or a server.

## Report experience

- Repository job cards with verified purpose, latest total, independent successful
  baseline and explicit outcome coverage; auto-select the largest observed increase.
- Only the selected job's statistics, priorities and stacked attempt history.
- **32/64 attempts**, default 32, with Older/Newer/Latest within newest 64 per type.
  Reruns are distinct job IDs; all outcomes remain visible.
- Gray runner wait above execution, individual-job outcome colors, successful
  complete-total median and consistent seconds/minutes (strictly above 300 s).
- Every retained attempt has fresh/stale metadata and explicit trace availability;
  phases, safe logged intervals, BuildKit builds/operations/substeps and source lines.
- What to improve first: successful measured interval-union costs, known N,
  independent evidence navigation and authoritative investigation links.
- English/Russian interface, responsive 320 px light/dark layout, keyboard controls,
  no raw logs, external assets, browser tokens or API requests in the report.

Mixed-ref history is exploratory, not proof of a regression or cause. The
established same-ref workflow is separately accessible. Unknown is not zero;
parallel or child timings are not added as promised savings.

## Install or update

Requirements: Python 3.10+, `glab` with existing authorized GitLab authentication,
plus the declared Python requirements. Clone the repository:

```sh
git clone --depth 1 \
  https://github.com/mesilov/gitlab-ci-performance-skill.git /tmp/ci-skill
mkdir -p .agents/skills .codex/skills .claude/skills
cp -R /tmp/ci-skill/skills/gitlab-ci-performance .agents/skills/
ln -s ../../.agents/skills/gitlab-ci-performance .codex/skills/gitlab-ci-performance
ln -s ../../.agents/skills/gitlab-ci-performance .claude/skills/gitlab-ci-performance
```

For an update, first move the old `.agents/skills/gitlab-ci-performance` directory
to an unused backup location, then copy the new directory into its place.
Existing links still point at that path. Preserve reports/private caches and any
customizations in the backup; do not copy old modules over the new skill. The
repository contains tests, documentation and fixtures as well as the complete
distributable skill directory.

Invoke `$gitlab-ci-performance` in Codex or `/gitlab-ci-performance` in Claude
Code. Follow the project's instructions and use an authorized account.

## Complete CLI workflow

From the repository (or substitute the installed helper path):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r skills/gitlab-ci-performance/requirements.txt
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py collect \
  --host gitlab.example.com --project group/service --timezone UTC \
  --output reports/run-001/jobs.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py collect-details \
  --snapshot reports/run-001/jobs.json --output-dir reports/run-001/details --workers 4
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot reports/run-001/jobs.json --details reports/run-001/details \
  --output reports/run-001/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/run-001/report.json --language ru --output reports/run-001/report.html
```

Every output is new/immutable. Defaults: UTC and `--language en`. Re-render saved
JSON entirely offline. An optional `--catalog catalog.json` verifies job purpose;
see [example](examples/reviewed/catalog.json). Catalog source URL/date/ref/hash
record current configuration provenance, not every historical configuration.

`collect` reads paginated available job metadata (not logs/variables).
`collect-details` refreshes newest 64 attempts per (stage,name), then analyzes
only their logs. Restrict scope before requests with repeated `--job NAME` and
`--stage STAGE`. At most R metadata plus R trace GETs for R retained attempts;
workers 1–8, default 4, 60 s timeout, 32 MiB default trace cap (`--max-trace-bytes`).
Failures/stale metadata, not-run, empty, erased, partial and unavailable logs are
explicit. `--no-traces` records disabled analysis, not an unavailable-log claim.

Optional private `--trace-cache DIR --reuse-cache` explicitly reuses matching
complete terminal logs. Active/partial/stale/erased entries are not reused.
Raw caches have owner-only permissions and must not be published. Safe report
metadata still contains project/job names and URLs; choose its sharing location.

## Data contracts

- `jobs.json`: immutable source projection.
- `details/metadata.json`: bounded safe refreshed metadata and coverage.
- `details/timings.json`: compact allowlisted timing evidence.
- `report.json`: precomputed windows, baseline samples,
  priorities and hashes; validated before rendering.
- `report.html`: standalone embedded compact data, no raw trace text.

Run `ci_report.py validate artifact.json` for schema/ID/calculation checks.
`--release-refs REF...` selects exact refs for exploratory history.
`--baseline older/jobs.json` provides external same-ref comparison with overlap
safeguards.

See [methodology](skills/gitlab-ci-performance/references/methodology.md),
[trace precision/cache rules](skills/gitlab-ci-performance/references/trace-analysis.md)
and [changelog](CHANGELOG.md).

## Workflow analysis

![Synthetic workflow performance report](docs/workflow-report.png)

Workflow mode analyzes pipeline runs and their jobs using separate contracts.
Read the [workflow methodology and CLI examples](skills/gitlab-ci-performance/references/workflows.md)
and use the installed [generic model](skills/gitlab-ci-performance/assets/workflow-model.json).
The agent verifies resolved CI configuration, records explicit historical coverage
and stamps it with `define-workflows`. `--workflow-window` defaults to 32 pipeline
runs; `--workflow-window 64` requests 64. Every retained attempt in those pipelines
stays in the selected job view.

```bash
# After creating verified workflows.json as documented in references/workflows.md:
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py collect \
  --host gitlab.example.com --project group/project --workflow-window 64 \
  --output reports/workflow-run/jobs.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot reports/workflow-run/jobs.json --workflows workflows.json \
  --output reports/workflow-run/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/workflow-run/report.json --output reports/workflow-run/report.html
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py export-llm \
  --report reports/workflow-run/report.json --output reports/workflow-run/llm.json
```

Workflow contracts export nullable elapsed/active/gap/queue values,
coverage, membership, evidence and exact baseline sample IDs. Parallel time is an
interval union. Latest attempts determine outcomes; all retained attempts contribute
timing. Independent operations keep separate histories. Missing historical
configuration is explicit; cross-pipeline chains are unsupported. Baselines need
at least three preceding comparable complete successes, up to ten. Failed/partial
measurements are excluded. Canonical JSON and compact LLM exports share seconds.
HTML switches to minutes strictly above 300 seconds in the selected series/metric
and offers English/Russian selection.

Generate the offline synthetic workflow demo with unit-boundary fixtures:

```bash
.venv/bin/python examples/generate_workflow_demo.py --output-dir reports/workflow-demo
```

Additional contracts: [workflows](skills/gitlab-ci-performance/schemas/workflows.schema.json),
[workflow-jobs](skills/gitlab-ci-performance/schemas/workflow-jobs.schema.json),
[workflow-report](skills/gitlab-ci-performance/schemas/workflow-report.schema.json),
[workflow-llm](skills/gitlab-ci-performance/schemas/workflow-llm.schema.json).
A clean installed skill contains the required modules, templates, schemas and the model;
it does not depend on this repository's tests/examples.

## Development and evidence

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/generate_reviewed.py --output-dir reports/new-demo
node tests/browser_reviewed.cjs file:///absolute/path/reports/new-demo/report.html reports/browser
```

Browser QA requires Playwright (resolve with `CI_REPORT_PLAYWRIGHT` if needed).
Local Chrome is default; `CI_REPORT_BROWSER_CHANNEL=chromium` uses Playwright's
bundled browser in CI. Checks cover en/ru, 32/64, all retained attempts, evidence,
320/375/1280 px light/dark, keyboard/focus, safe links, moved HTML and denied network.
`tests/test_installed_skill.py` tests a clean skill-only installation/update with
a synthetic standalone glab transport, request/payload limits and privacy sentinels.

`tests/workflow_browser_check.cjs` checks offline workflow parity, 32/64 pipeline windows, attempts, en/ru, mobile layout and the 300-second boundary.

## Canonical report and compact LLM exports (#4)

The `ci_report.py` workflow above supports reviewed job reports. The additional
installed `report_cli.py` produces the namespaced
canonical contract from [issue #4](https://github.com/mesilov/gitlab-ci-performance-skill/issues/4):

```sh
.venv/bin/python skills/gitlab-ci-performance/scripts/report_cli.py collect --host gitlab.example.com --project group/service --output reports/contract/jobs.json
.venv/bin/python skills/gitlab-ci-performance/scripts/report_cli.py report --snapshot reports/contract/jobs.json --output reports/contract/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/report_cli.py export --report reports/contract/report.json --scope overview --output reports/contract/overview.json
.venv/bin/python skills/gitlab-ci-performance/scripts/report_cli.py render --report reports/contract/report.json --language ru --output reports/contract/report.html
```

This workflow retains at most 64 attempts/type, refreshes all outcomes, exports
allowlisted bounded evidence and precomputes all supported 32/64 findings. Full,
overview, selected-window and selected-attempt JSON use the same measurements as
the offline HTML. Read the [canonical contract](skills/gitlab-ci-performance/references/contract-v2.md)
for selectors, budgets, sample/interval policies and unavailable guidance.
Generate its public synthetic example with the [demo generator](examples/generate_v2.py).
The canonical HTML now follows the reviewed report layout: compact job cards with
baseline/outcome context, a framed vertical list of action priorities, collapsed history and a compact
two-level attempt timeline. Select a saved build fragment, then an operation to see
its source lines and nested substeps. Runner phases and technical metadata are
collapsed. The canonical parser does not retain image names or original BuildKit
step numbers; anonymous fragments are labeled honestly rather than merged into
invented images. See the [synthetic preview](examples/v2/report.html). Calculation and
queue-spike policies remain specific to each contract.
Its `gitlab_job_performance_*` kinds distinguish it from the `ci_report.py` workflow;
entrypoints reject incompatible artifacts rather than silently converting them.

MIT — [license](LICENSE).
