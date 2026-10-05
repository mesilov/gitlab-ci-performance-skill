# README clarity verification — issue #24

Date: 2026-10-05. Initial base: `331dcb7c015e712df72cf3dde9c58d08d3e49c6a`.
Integrated main: `83b50e77f9a068201d25aa29b716c9a926492328` (issue #23).
The rewrite preserves its upstream provenance and execution-mode instructions.
Branch: `codex/issue-24-readme` in a separate managed worktree.

## Result

README.md and README.ru.md now share ten sections, the same shell examples and
localized Mermaid diagrams. They explain the main task before the implementation,
define six terms, distinguish both CLI routes and workflow mode, and link detailed
contracts. Existing synthetic HTML examples and screenshots remain available.

The writing uses the user's supplied Karpathy recommendations, with ASD-STE100
as a clarity reference, not a formal compliance target. See the
[official description](https://www.asd-ste100.org/about_STE.html). Russian applies
plain-language principles rather than an English controlled dictionary.
No new website, video, parser, schema, calculation or report UI was introduced.

## Before and after — English

| Before | After |
| --- | --- |
| Reusable agent skill: safe GitLab metadata → bounded trace evidence → reproducible calculations → standalone offline report. | Find where GitLab CI jobs spend time. This agent skill compares runs, separates runner waiting time from execution, and helps you inspect slow build steps. |
| Every output is new/immutable. | Each command creates new output files; choose a new directory for another run. |
| Mixed-ref history is exploratory, not proof of a regression or cause. | Comparisons across refs are exploratory and do not prove a regression. |

## Before and after — Russian

| До | После |
| --- | --- |
| Переиспользуемый скилл: безопасные метаданные GitLab → ограниченный анализ логов → воспроизводимые расчёты → автономный HTML-отчёт. | Узнайте, на что уходит время в GitLab CI. Этот скилл для агента сравнивает запуски, отделяет ожидание runner от выполнения и помогает изучить медленные шаги сборки. |
| Каждый output новый; существующие артефакты не перезаписываются. | Каждая команда создаёт новые файлы; для следующего запуска выберите новый каталог. |
| Неизвестное не становится нулём; пересечения и подшаги не суммируются как обещанная экономия. | Неизвестное время не равно нулю. Параллельные шаги и вложенные операции пересекаются; их длительности не складываются в обещанную экономию. |

## Checks performed

- 48 local Markdown links/images resolve, including the collection-budget anchor.
- Fences are balanced. All 10 shell blocks pass `sh -n`.
- Eight distinct CLI/subcommand help checks confirm documented shell-example flags.
  These checks do not contact GitLab.
- Both README files have ten matching sections. Shell blocks are identical after
  normalizing the intentionally localized `render --language en|ru` argument.
- Synthetic canonical generation, report calculation, overview export and rendering
  in English/Russian all succeed. Reviewed report calculation from checked-in
  synthetic source/details and rendering in both languages also succeed.
- The Python check environment uses the declared `jsonschema==4.25.1` dependency.
- Independent read-only review checked both languages against contract-v2.md,
  methodology.md, trace-analysis.md, workflows.md, release-history.md, CLI parsing
  and CI configuration. It reported no actionable findings.
- `git diff --check` passes. Changes are documentation only.

The exact offline commands used a temporary Python environment instead of the
README's `.venv/bin/python`. Output paths were also replaced with fresh temporary
paths. No live collection was performed; collect flags were checked against the
CLI help and implementation. The full local unit/browser suite was not run for
this documentation-only change. Remote CI is a separate delivery check.

Offline command sequence, from the repository root:

```sh
python examples/generate_v2.py --output-dir <new>/canonical-source
python skills/gitlab-ci-performance/scripts/report_cli.py report --snapshot <new>/canonical-source/jobs.json --output <new>/canonical/report.json
python skills/gitlab-ci-performance/scripts/report_cli.py export --report <new>/canonical/report.json --scope overview --output <new>/canonical/overview.json
python skills/gitlab-ci-performance/scripts/report_cli.py render --report <new>/canonical/report.json --language en --output <new>/canonical/report-en.html
python skills/gitlab-ci-performance/scripts/report_cli.py render --report <new>/canonical/report.json --language ru --output <new>/canonical/report-ru.html
python skills/gitlab-ci-performance/scripts/ci_report.py report --snapshot examples/reviewed/jobs.json --details examples/reviewed --output <new>/reviewed/report.json
python skills/gitlab-ci-performance/scripts/ci_report.py render --report <new>/reviewed/report.json --language en --output <new>/reviewed/report-en.html
python skills/gitlab-ci-performance/scripts/ci_report.py render --report <new>/reviewed/report.json --language ru --output <new>/reviewed/report-ru.html
```

The `<new>` notation records the replaced temporary output root; it is not a
copy-and-run shell example. Every command returned exit code 0.

## Size and scope

Whitespace-separated words include code, diagrams and tables:

| File | Before | After | Lines before → after |
| --- | ---: | ---: | --- |
| README.md | 1,438 | 1,469 | 232 → 222 |
| README.ru.md | 1,458 | 1,389 | 256 → 231 |

Counts compare with integrated main, including issue #23. The rewrite adds the
missing English canonical command sequence, term definitions and route comparison.
It simplifies reading rather than targeting fewer words at the expense of meaning.
Dense internal contract details are linked through the existing references.

The two README files are the product change. The accompanying design, plan and
this verification record document the accepted scope and checks.
