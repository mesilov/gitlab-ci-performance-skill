[English](README.md) | [Русский](README.ru.md)

# GitLab CI Performance Analyzer

An agent skill for analyzing GitLab CI job durations, runner queues, and timing
regressions using `glab`. Save versioned JSON snapshots, compare runs, and open
a standalone HTML report directly in your browser.

![Synthetic GitLab CI performance report](docs/report.png)

The screenshot and [example report](examples/report.html) use **synthetic data**.
Download the HTML and open it locally; no server or external assets are required.

## What it does

- Analyzes verified workflow chains and independent operations over 32/64 pipeline windows.
- Separates job execution time from runner queue time.
- Compares the latest successful pipeline, or a window of pipelines, against a baseline.
- Highlights P50 timing regressions and exposes P95, sample sizes, retries, and job history.
- Preserves JSON snapshots with strict schemas and source hashes for later comparisons.
- Shows a stacked pipeline chart and job descriptions from an optional verified catalog.

Collection uses read-only GitLab API requests through your existing `glab`
authentication. It does not fetch job logs or variables. Reports can still
contain project names, job names, runner descriptions, and URLs: choose where
you store and share your own reports.

## Install the skill in a project

Clone this repository. From the project where you want to use the skill:

```bash
mkdir -p .agents/skills .codex/skills .claude/skills
cp -R /path/to/gitlab-ci-performance-skill/skills/gitlab-ci-performance .agents/skills/
ln -s ../../.agents/skills/gitlab-ci-performance .codex/skills/gitlab-ci-performance
ln -s ../../.agents/skills/gitlab-ci-performance .claude/skills/gitlab-ci-performance
```

Invoke `$gitlab-ci-performance` in Codex or `/gitlab-ci-performance` in Claude
Code. Ask it to analyze a project URL or compare two saved snapshots. Follow
your agent's project instructions and use an authorized GitLab account.

The job report UI, agent instructions, and methodology are in English.
Workflow reports have English/Russian interface selection.
Russian documentation is available in [README.ru.md](README.ru.md).

## Run the CLI directly

Requirements: Python 3.10+, `glab`, and its existing authentication for your GitLab host.
From this repository:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r skills/gitlab-ci-performance/requirements.txt
glab auth login --hostname gitlab.example.com

.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py collect \
  --host gitlab.example.com --project group/project \
  --timezone UTC --output reports/run-001/jobs.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot reports/run-001/jobs.json --output reports/run-001/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/run-001/report.json --output reports/run-001/report.html
```

Open `reports/run-001/report.html` directly in a browser. Each run needs a new
output path; existing artifacts are not overwritten. UTC is the default;
`--timezone` accepts an IANA timezone.

For a saved baseline, add `--baseline reports/run-000/jobs.json` to `report`.
Overlapping pipeline cohorts are explicitly marked and do not produce a
regression claim.

Try the synthetic sample without a GitLab account:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot examples/jobs.json --catalog examples/catalog.json \
  --output reports/demo/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/demo/report.json --output reports/demo/report.html
```

## Artifacts and interpretation

![Synthetic workflow performance report](docs/workflow-report.png)

Workflow mode is available in skill release **2.0.0**, alongside original v1
job-only artifacts. Read the [workflow methodology and CLI examples](skills/gitlab-ci-performance/references/workflows.md)
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

Workflow schema/calculation 2.0.0 exports nullable elapsed/active/gap/queue values,
coverage, membership, evidence and exact baseline sample IDs. Parallel time is an
interval union. Latest attempts determine outcomes; all retained attempts contribute
timing. Independent operations keep separate histories. Missing historical
configuration is explicit; cross-pipeline chains are unsupported. Baselines need
at least three preceding comparable complete successes, up to ten. Failed/partial
measurements are excluded. Canonical JSON and compact LLM exports share seconds.
HTML switches to minutes strictly above 300 seconds in the selected series/metric
and offers English/Russian selection. v1 snapshots require recollection for workflows.

Generate the offline synthetic workflow demo with unit-boundary fixtures:

```bash
.venv/bin/python examples/generate_workflow_demo.py --output-dir reports/workflow-demo
```

Additional contracts: [workflows](skills/gitlab-ci-performance/schemas/workflows.schema.json),
[workflow-jobs](skills/gitlab-ci-performance/schemas/workflow-jobs.schema.json),
[workflow-report](skills/gitlab-ci-performance/schemas/workflow-report.schema.json),
[workflow-llm](skills/gitlab-ci-performance/schemas/workflow-llm.schema.json).
A clean installed skill contains both modules, templates, schemas and the model;
it does not depend on this repository's tests/examples.

The following describes the original job-only mode:

- [`jobs.schema.json`](skills/gitlab-ci-performance/schemas/jobs.schema.json): source projection of job attempts and pipeline metadata.
- [`report.schema.json`](skills/gitlab-ci-performance/schemas/report.schema.json): derived metrics, comparison policy, cohorts, and input hashes.
- `report.html`: self-contained report with embedded data. It also works if moved without the sidecar JSON files.

By default, a regression requires P50 growth of **at least 20% and 30 seconds**,
with at least three baseline observations. These thresholds are configurable;
one current run is an observation, not an established trend. Timing comparisons
use successful job attempts in successful pipelines of the same ref.

Pipeline queue time is the wait before its first start; individual job queue
times are shown separately. The stack is not a complete lifecycle measurement.
Missing times remain missing instead of becoming zero. API collection is not an
atomic transaction and cannot recover deleted jobs or bridge/trigger jobs.
There is no automatic schedule or resource-level profiler.

See the [methodology](skills/gitlab-ci-performance/references/methodology.md)
and [optional catalog example](examples/catalog.json) for details.

## Development

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Generate another synthetic demo with `examples/generate_demo.py --output-dir
reports/new-demo` using the same Python environment and a new output path. `tests/browser_check.cjs` is an optional Playwright/Chrome
check of local-file viewing with the network disabled. Install Playwright in a
development environment and pass a file URL and screenshot output directory.

`tests/workflow_browser_check.cjs` checks workflow parity, windows, selection,
attempts, language, mobile layout and the 300-second boundary with offline Playwright.
Pass the workflow demo file URL and a QA output directory.
`CI_REPORT_BROWSER_CHANNEL=chromium` selects bundled Chromium; Chrome is the default.
CI also builds/extracts the 2.0.0 skill package and runs its CLI from a clean install.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the change history.

## License

MIT — see [LICENSE](LICENSE).
