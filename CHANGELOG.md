# Changelog

## 0.1.0 — 2026-11-13

The first release.

- One command, `scripts/ci_report.py`, reads the last finished pipelines of one
  ref through `glab` and writes `report.html` and `data.json`. It takes the host
  and project from the `origin` remote and uses the default branch. It only
  reads GitLab data.
- The report is one static HTML file without JavaScript and network requests:
  summary, "Where to look first", pipeline history, the latest successful
  pipeline on one time axis, and a job table with runs and log steps.
  English and Russian, light and dark themes, phone width.
- The same findings are printed as text for the agent.
- Log steps for the slowest jobs: runner phases, script commands (from log
  timestamps) and Docker BuildKit steps. A job that builds several images marks
  the steps of each build.
- Options: `--ref`, `--any-ref`, `--source`, `--pipelines`, `--logs`, `--lang`,
  `--out`, and `--from data.json` to build the report again without GitLab.
- The script says when most pipelines run on other refs than the default branch.
- Python 3.9 or later, standard library only.
