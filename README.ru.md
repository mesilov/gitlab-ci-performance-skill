[English](README.md) | [Русский](README.ru.md)

# Анализатор производительности GitLab CI

Скилл собирает ограниченную историю метаданных jobs и безопасные данные о времени
из traces, рассчитывает версионированные findings, экспортирует JSON для LLM и
создаёт один автономный HTML. Контракт v2 подготовлен как кандидат на релиз по
[issue #4](https://github.com/mesilov/gitlab-ci-performance-skill/issues/4).

- Сохраняет последние 64 попытки на тип job, включая reruns и разные исходы; окна 32/64.
- Разделяет ожидание раннера, выполнение, полное время и lifecycle создания→завершения.
- Сохраняет same-ref baseline; cross-ref требует явного списка refs.
- Анализирует ограниченные traces через allowlist фаз/BuildKit/интервалов команд, без экспорта raw logs.
- Один слой Python рассчитывает baseline/delta и union интервалов категорий для JSON и HTML.
- Сохраняет даты исходного сбора/анализа, хеши, версии, N и фактическое покрытие.

Полная приёмка UI, перевод ru/en и workflow исследования официальной документации
остаются в #3/#2/#5. Сейчас `--language en|ru` задаёт метаданные, заголовок и оболочку
представления; имена jobs/refs, machine codes и секунды сохраняются. Измеренная
стоимость категории не равна гарантированной экономии.

## Установка

Клонируйте репозиторий. Из проекта, в котором нужен скилл:

```bash
mkdir -p .agents/skills .codex/skills .claude/skills
cp -R /path/to/gitlab-ci-performance-skill/skills/gitlab-ci-performance .agents/skills/
ln -s ../../.agents/skills/gitlab-ci-performance .codex/skills/gitlab-ci-performance
ln -s ../../.agents/skills/gitlab-ci-performance .claude/skills/gitlab-ci-performance
```

Вызовите `$gitlab-ci-performance` в Codex или `/gitlab-ci-performance` в Claude Code.
При обновлении замените установленный каталог скилла версией upstream, сохранив
каталоги reports; установите её закреплённые Python-зависимости и проверьте установленный
helper через `--help` и offline smoke. Копия локальной установки проверяется тестами;
публикация v2.0.0 остаётся отдельным условием доставки.

## CLI

Нужны Python 3.10+, `glab` и разрешённая авторизация GitLab. Из репозитория:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r skills/gitlab-ci-performance/requirements.txt
glab auth login --hostname gitlab.example.com

.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py collect \
  --host gitlab.example.com --project group/project --timezone UTC \
  --output reports/run-001/jobs.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot reports/run-001/jobs.json --language ru --output reports/run-001/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py export \
  --report reports/run-001/report.json --scope overview --output reports/run-001/overview.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/run-001/report.json --output reports/run-001/report.html
```

Открывайте HTML через file://. Вывод не перезаписывается: используйте новый каталог.
Сеть использует только collect. Метаданные могут содержать названия проекта/jobs/refs,
описания раннеров и URL; выбирайте место хранения и круг получателей своих отчётов.

Лимиты по умолчанию: 10 страниц метаданных × 100,16 типов, 64 попытки/тип, concurrency 4,
traces 4 MiB/50 000 строк. Ошибки и неполное покрытие остаются явными. `--job stage/name`
ограничивает типы; для имён с `/` используйте JSON-массив `{stage,name}` через
`--job-config`. `--resume` / `--cache` принимают валидированные sources v2; raw traces
и variables не сохраняются. Cross-ref: одинаковые `--comparison-mode cross_ref`
и повторяемые `--ref REF` для collect/report. При необходимости добавьте
`--baseline older-jobs.json` и проверенный `--catalog catalog.json`.

Выберите ID из canonical JSON для компактного анализа:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py export \
  --report reports/run-001/report.json --job-type JOB_TYPE_ID --window-id WINDOW_ID \
  --output reports/run-001/window.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py export \
  --report reports/run-001/report.json --attempt-ids 123 124 \
  --output reports/run-001/attempts.json
```

## Синтетический пример и контракты

Без GitLab-аккаунта:

```bash
.venv/bin/python examples/generate_v2.py --output-dir reports/v2-demo
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py validate reports/v2-demo/report.json
```

Генератор включает два типа jobs по 64 сохранённые попытки, разные исходы,
empty/erased/unavailable/partial traces и findings из реального parser. Приватных
данных в примере нет. [Контракт v2](skills/gitlab-ci-performance/references/contract-v2.md)
описывает схемы, обязательные/nullable поля, бюджеты запросов/payload, uncertainty,
provenance рекомендаций, ссылки compact export и воспроизводимость.

Исходный [пример HTML](examples/report.html) и screenshot показывают frozen v1.
V1 продолжает валидироваться и отображаться. Для явного старого расчёта:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report --legacy \
  --snapshot examples/jobs.json --catalog examples/catalog.json --output reports/legacy/report.json
```

V2 требует source v2: отсутствующие trace/freshness данные v1 не выдумываются.

## Разработка

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Тесты проверяют copied-install offline round trip, схемы/семантику, bounded mock API,
реальный parser→calculation и compact parity. `tests/browser_v2.cjs FILE_URL
OUTPUT_DIRECTORY` запускает Playwright/Chrome offline: все jobs/windows/attempts,
ссылки evidence, numeric parity, 320px/light/dark и перенос автономного файла.
`tests/browser_check.cjs` сохранён для v1.

[История изменений](CHANGELOG.md) · [Методика](skills/gitlab-ci-performance/references/methodology.md)
· MIT [Лицензия](LICENSE)
