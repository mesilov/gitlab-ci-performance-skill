[English](README.md) | [Русский](README.ru.md)

# GitLab CI Performance Analyzer

An agent skill for analyzing GitLab CI job durations, runner queues, and timing
regressions using `glab`. Save versioned JSON snapshots, compare runs, and open
a standalone HTML report directly in your browser.

![Synthetic GitLab CI performance report](docs/report.png)

The screenshot and [example report](examples/report.html) use **synthetic data**.
Download the HTML and open it locally; no server or external assets are required.

## What it does

- Separates job execution time from runner queue time.
- Optionally shows per-job timing history across explicitly selected release refs/tags.
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

The report UI, agent skill instructions, and methodology reference are in English.
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

For unique release tags, explicitly select the refs to inspect:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot reports/run-001/jobs.json --release-refs v1.0 v1.1 v1.2 v1.3 \
  --output reports/releases/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/releases/report.json --output reports/releases/report.html
```

Open **Release history across selected refs / tags** in the HTML. Select a job,
then an attempt to inspect execution, runner queue, original ref and context.
Cross-ref changes are exploratory observations with explicit N and sample IDs;
same-ref comparison remains the default. The 32/64 attempt controls affect the
visible chart, not collection or baseline selection. See the
[release-history methodology](skills/gitlab-ci-performance/references/release-history.md).
Reports now use schema/calculation 1.1.0; snapshots stay 1.0.0, and legacy 1.0.0
reports remain renderable with the updated skill.

Generate a fictional multi-tag report without GitLab access:

```bash
.venv/bin/python examples/generate_release_demo.py --output-dir reports/release-demo
```

Try the synthetic sample without a GitLab account:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot examples/jobs.json --catalog examples/catalog.json \
  --output reports/demo/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/demo/report.json --output reports/demo/report.html
```

## Artifacts and interpretation

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

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the change history.

Offline release-history browser QA: run `tests/browser_release_check.cjs` with a file URL
and an output directory, using Playwright and Chrome as for the existing browser check.

## License

MIT — see [LICENSE](LICENSE).
