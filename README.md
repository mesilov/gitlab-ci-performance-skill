[English](README.md) | [Русский](README.ru.md)

# GitLab CI Performance Analyzer

An agent skill that collects bounded GitLab job metadata and safe trace evidence,
calculates versioned findings, exports LLM-ready JSON and renders one offline HTML file.
The v2 contract is a release candidate for [issue #4](https://github.com/mesilov/gitlab-ci-performance-skill/issues/4).

- Retains newest 64 attempts per job type, including reruns and mixed outcomes; history windows are 32/64.
- Separates runner wait, execution, complete total and creation-to-completion lifecycle.
- Preserves same-ref baselines; cross-ref exploration requires an explicit allowlist.
- Parses bounded allowlisted phase/BuildKit/command timing evidence, without exporting raw logs.
- Calculates baseline/delta and overlap-safe improvement costs once in Python for JSON and HTML.
- Records original collection/analysis times, source hashes, versions, sample sizes and actual coverage.

Complete reviewed v2 UI acceptance and full v2 ru/en translation remain tracked in
issues #3 and #2. V2 `report --language en|ru` selects saved language metadata;
`render --language en|ru` optionally selects the HTML shell without changing saved JSON.
The legacy renderer retains full localization from #2. Raw names/codes/data stay
unchanged. Measured cost is not guaranteed savings. Read the maintained
[official optimization sources](skills/gitlab-ci-performance/references/optimization-sources.md)
from #5 when investigating a finding; guidance in JSON still records its own verification.

## Install

Clone this repository. From the project where you want the skill:

```bash
mkdir -p .agents/skills .codex/skills .claude/skills
cp -R /path/to/gitlab-ci-performance-skill/skills/gitlab-ci-performance .agents/skills/
ln -s ../../.agents/skills/gitlab-ci-performance .codex/skills/gitlab-ci-performance
ln -s ../../.agents/skills/gitlab-ci-performance .claude/skills/gitlab-ci-performance
```

Invoke `$gitlab-ci-performance` in Codex or `/gitlab-ci-performance` in Claude Code.
To update, replace the installed skill directory from the chosen upstream version,
preserving report directories; install that skill's pinned Python requirements and
run the installed helper's `--help` / saved-source smoke before using new artifacts.
A copied local installation is tested; a published v2.0.0 release remains a delivery gate.

## CLI workflow

Requirements: Python 3.10+, `glab`, existing authorized GitLab authentication.
From this repository:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r skills/gitlab-ci-performance/requirements.txt
glab auth login --hostname gitlab.example.com

.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py collect \
  --host gitlab.example.com --project group/project --timezone UTC \
  --output reports/run-001/jobs.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot reports/run-001/jobs.json --language en --output reports/run-001/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py export \
  --report reports/run-001/report.json --scope overview --output reports/run-001/overview.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/run-001/report.json --output reports/run-001/report.html
```

Open the HTML directly through file://. Outputs reject overwrites; use a new run path.
Only collect performs network requests. Reports can contain project/job/ref names,
runner descriptions and URLs; choose where to store/share your own metadata.

Defaults: 10 metadata pages × 100, 16 types, 64 attempts/type, concurrency 4, traces
4 MiB/50,000 lines. Metadata/trace failures remain explicit. `--job stage/name` narrows
collection; structured `--job-config` handles names containing `/`. `--resume` and
`--cache` accept validated v2 safe sources. Raw traces/variables are not persisted.
For cross-ref, repeat `--ref REF` with `--comparison-mode cross_ref` for both collect
and report. Use `--baseline older-jobs.json` or a verified `--catalog catalog.json`
when applicable. Unsupported language/version/IDs fail with actionable messages.

For focused LLM exports, select IDs from the canonical JSON:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py export \
  --report reports/run-001/report.json --job-type JOB_TYPE_ID --window-id WINDOW_ID \
  --output reports/run-001/window.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py export \
  --report reports/run-001/report.json --attempt-ids 123 124 \
  --output reports/run-001/attempts.json
```

## Synthetic demo and contracts

Generate public synthetic sources/reports without a GitLab account:

```bash
.venv/bin/python examples/generate_v2.py --output-dir reports/v2-demo
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py validate reports/v2-demo/report.json
```

The generator exercises two job types, 64 retained attempts each, mixed outcomes,
empty/erased/unavailable/partial traces and real parser-derived category findings.
No private project data is used. See the [v2 contract](skills/gitlab-ci-performance/references/contract-v2.md)
for schemas, required/nullable fields, request/payload budgets, interval uncertainty,
guidance provenance, compact reference closure and reproducibility. Entry schemas:
[jobs](skills/gitlab-ci-performance/schemas/jobs.schema.json),
[trace](skills/gitlab-ci-performance/schemas/trace.schema.json),
[report](skills/gitlab-ci-performance/schemas/report.schema.json),
[compact](skills/gitlab-ci-performance/schemas/compact.schema.json).

The original [example report](examples/report.html) / screenshot demonstrate frozen
legacy 1.0. Existing 1.0/1.1 artifacts still validate/render in English or Russian.
Explicit legacy generation retains the 1.1 release-history extension from #1:
[method and limits](skills/gitlab-ci-performance/references/release-history.md).
To recalculate that example explicitly:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report --legacy \
  --snapshot examples/jobs.json --catalog examples/catalog.json --output reports/legacy/report.json
```

Add `--release-refs REF [REF ...]` to `report --legacy` for the existing exploratory
release view, or run `examples/generate_release_demo.py` for its synthetic demo.
V2 cross-ref history uses `--comparison-mode cross_ref --ref REF` instead.

New v2 calculations require v2 sources; missing v1 trace/freshness evidence is never invented.

## Development

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests include copied-install offline CLI round trips, schema/semantic rejection,
bounded mock API collection, real parser→calculation regressions and compact parity.
`tests/browser_v2.cjs FILE_URL OUTPUT_DIRECTORY` uses Playwright/Chrome offline for
all job/window/attempt selections, evidence links, numeric parity, 320px/light/dark
and moved standalone HTML. `tests/browser_check.cjs` remains the v1 browser check.

[Changelog](CHANGELOG.md) · [Methodology](skills/gitlab-ci-performance/references/methodology.md)
· MIT [License](LICENSE)
