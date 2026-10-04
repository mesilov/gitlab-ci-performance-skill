[English](README.md) | [Русский](README.ru.md)

# GitLab CI Performance Analyzer

Версия **2.0.1** переиспользуемого скилла: безопасные метаданные GitLab →
ограниченный анализ логов → воспроизводимые расчёты → автономный HTML-отчёт.

![Синтетический отчёт](docs/report.png)

[Пример на русском](examples/reviewed/report-ru.html) и
[на английском](examples/reviewed/report.html) содержат только синтетические данные.
Скачайте HTML и откройте локально: сервер и соседние JSON для просмотра не нужны.

## Возможности

- Карточки jobs с проверенным назначением, последним полным временем, независимой
  успешной базой сравнения и явным охватом исходов. Автовыбор наибольшего роста.
- Ниже — только выбранная job: приоритеты, статистика, график и детали.
- **32/64 попытки**, по умолчанию 32; Older/Newer/Latest внутри последних 64 на тип
  job. Перезапуски имеют отдельные job ID; ошибки и отмены видны в истории.
- Серое ожидание сверху, выполнение ниже, цвет исхода отдельной job, медиана
  полных успешных значений. При максимуме строго больше 300 с — минуты.
- Метаданные и явное состояние лога каждой удержанной попытки; секции runner,
  оценочные интервалы команд, BuildKit → образы → операции → подшаги/строки лога.
- «Что улучшить сначала»: наблюдаемая стоимость объединённых интервалов успешных
  запусков, измеренный N, переход к доказательствам и ссылки на документацию.
- ru/en, светлая/тёмная тема, ширина 320 px, клавиатура, работа без сети и токенов
  браузера. Сырые команды и логи в отчёт не попадают.

История разных refs — исследовательское наблюдение, не доказательство регрессии
или причины. Сравнение одной ref сохранено отдельно. Неизвестное не становится
нулём; пересечения и подшаги не суммируются как обещанная экономия.

## Установка и обновление

Нужны Python 3.10+, `glab` с существующей авторизованной учётной записью GitLab
и зависимости из requirements.txt. Устанавливайте опубликованный тег:

```sh
git clone --branch v2.0.1 --depth 1 \
  https://github.com/mesilov/gitlab-ci-performance-skill.git /tmp/ci-skill-v2
mkdir -p .agents/skills .codex/skills .claude/skills
cp -R /tmp/ci-skill-v2/skills/gitlab-ci-performance .agents/skills/
ln -s ../../.agents/skills/gitlab-ci-performance .codex/skills/gitlab-ci-performance
ln -s ../../.agents/skills/gitlab-ci-performance .claude/skills/gitlab-ci-performance
```

При обновлении сначала переместите старый каталог `.agents/skills/gitlab-ci-performance`
в свободное место резервной копии, затем скопируйте новый на его место. Ссылки
продолжат работать. Сохраните отчёты, приватные кэши и локальные изменения;
не накладывайте старые модули поверх новой версии. В установленном VERSION должно
быть 2.0.1. Архив исходников релиза включает тесты, документацию и fixtures вместе
с полным каталогом распространяемого скилла.

Вызов: `$gitlab-ci-performance` в Codex или `/gitlab-ci-performance` в Claude
Code. Следуйте правилам проекта и используйте разрешённый доступ GitLab.

## Полный цикл CLI

Из репозитория либо с реальным путём установленного helper:

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

Каждый output новый; существующие артефакты не перезаписываются. По умолчанию UTC
и английский (`--language en`). Рендер сохранённых JSON работает полностью офлайн.
`report --catalog catalog.json` добавляет назначения jobs: [пример](examples/reviewed/catalog.json).
URL, дата, ref и hash конфигурации описывают проверенный текущий CI, а не все
исторические конфигурации.

`collect` собирает доступные метаданные с пагинацией, без логов/переменных.
`collect-details` обновляет метаданные последних 64 попыток на `(stage,name)` и
анализирует только их логи. Повторяемые `--job NAME`/`--stage STAGE` ограничивают
типы до запросов. Не более R запросов метаданных + R логов для R попыток;
workers 1–8, по умолчанию 4, timeout 60 с, лимит 32 MiB (`--max-trace-bytes`). Ошибки,
устаревшие метаданные, not-run, пустые, стёртые, частичные и недоступные логи
различаются. `--no-traces` явно отключает анализ логов.

`--trace-cache DIR --reuse-cache` явно разрешает повторное использование полного
лога завершённой совпадающей попытки. Активные, частичные, устаревшие и стёртые
логи не переиспользуются. Кэш с правами только владельца нельзя публиковать.
Безопасные метаданные отчёта всё равно содержат имена проекта/jobs и URL:
выбирайте место хранения и публикации самостоятельно.

## Данные и совместимость

- jobs.json: неизменяемый источник schema 1.0.
- details/metadata.json: ограниченные обновлённые метаданные и охват schema 2.0.
- details/timings.json: компактные доказательства schema/parser 2.0.
- report.json: окна, samples baseline, приоритеты и hashes schema/calculation 2.0.1.
- report.html: автономный HTML с встроенными данными без сырого лога.

`ci_report.py validate artifact.json` проверяет схемы, ID и расчёты.
Отчёты 1.0/1.1 рендерятся по сохранённой методике. `report --legacy` создаёт 1.1;
`--release-refs REF...` сохраняет маршрут точного выбора refs из#1.
`--baseline older/jobs.json` задаёт внешний baseline одной ref с проверкой
пересечения выборок. Неизвестные версии требуют совместимого helper либо явного
повторного анализа в новые outputs; скрытой смены методики нет.

Подробности: [методика](skills/gitlab-ci-performance/references/methodology.md),
[точность/кэш логов](skills/gitlab-ci-performance/references/trace-analysis.md),
[история изменений](CHANGELOG.md).

## Workflow-анализ (не выпущен)

![Синтетический workflow-отчёт](docs/workflow-report.png)

Workflow-режим добавляет отдельные контракты **2.0.0**, сохраняя reviewed-отчёты
и артефакты v1. Режим пока не выпущен; опубликованный тег v2.0.1 его не содержит. Правила и CLI — в [методике workflow](skills/gitlab-ci-performance/references/workflows.md),
структура модели — в [установленном примере](skills/gitlab-ci-performance/assets/workflow-model.json).
Агент проверяет разрешённую CI-конфигурацию, явно указывает историческое покрытие
и сохраняет подтверждения через `define-workflows`. `--workflow-window` выбирает
32 pipeline по умолчанию; `--workflow-window 64` выбирает 64. Все сохранённые
попытки jobs этих pipeline входят в то же выбранное окно.

```bash
# Сначала подготовьте проверенный workflows.json по references/workflows.md:
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

Схема/расчёт workflow 2.0.0 экспортируют nullable elapsed/active/gap/queue,
покрытие, членство попыток, подтверждения определения и точные ID baseline.
Параллельное время считается объединением интервалов. Последняя попытка задаёт
исход, а все сохранённые попытки входят во время. Независимые операции имеют
отдельные истории. Отсутствие исторической конфигурации явно отмечается;
цепочки между pipeline не поддерживаются. Baseline требует минимум три
предшествующих сопоставимых успешных полных измерения, максимум десять.
Ошибочные/частичные измерения исключены. JSON и LLM-export используют одинаковые
секунды; HTML переходит к минутам строго выше 300 секунд в выбранной серии/метрике
и позволяет выбрать русский/английский интерфейс. Для v1-снимков нужен новый сбор.

Автономный синтетический пример, включая фикстуры границы единиц:

```bash
.venv/bin/python examples/generate_workflow_demo.py --output-dir reports/workflow-demo
```

Новые контракты: [workflows](skills/gitlab-ci-performance/schemas/workflows.schema.json),
[workflow-jobs](skills/gitlab-ci-performance/schemas/workflow-jobs.schema.json),
[workflow-report](skills/gitlab-ci-performance/schemas/workflow-report.schema.json),
[workflow-llm](skills/gitlab-ci-performance/schemas/workflow-llm.schema.json).
Установленная копия содержит необходимые модули, шаблоны, схемы и модель; папки tests/examples
исходного репозитория ей не нужны.

## Разработка

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/generate_reviewed.py --output-dir reports/new-demo
node tests/browser_reviewed.cjs file:///absolute/path/reports/new-demo/report.html reports/browser
```

Для браузерной проверки нужен Playwright; при необходимости задайте
CI_REPORT_PLAYWRIGHT. Локально используется Chrome, для bundled Chromium в CI —
CI_REPORT_BROWSER_CHANNEL=chromium. Проверяются ru/en,32/64, исходы/перезапуски,
доказательства, 320/375/1280 px, обе темы, клавиатура, перенос HTML и запрет сети.
`tests/test_installed_skill.py` проверяет чистую установку/обновление через
синтетический glab, ограничения запросов/размера и отсутствие сырого содержимого.

`tests/workflow_browser_check.cjs` проверяет автономный workflow-отчёт: окна 32/64 pipeline, попытки, en/ru, мобильную вёрстку и границу 300 секунд.

## Канонический отчёт и compact JSON для LLM (#4)

Опубликованный workflow `ci_report.py` выше сохраняет совместимость с отчётами
2.0.0/2.0.1 и принятый UI. Дополнительный установленный `report_cli.py` реализует
отдельный канонический контракт [issue #4](https://github.com/mesilov/gitlab-ci-performance-skill/issues/4):

```sh
.venv/bin/python skills/gitlab-ci-performance/scripts/report_cli.py collect --host gitlab.example.com --project group/service --output reports/contract/jobs.json
.venv/bin/python skills/gitlab-ci-performance/scripts/report_cli.py report --snapshot reports/contract/jobs.json --output reports/contract/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/report_cli.py export --report reports/contract/report.json --scope overview --output reports/contract/overview.json
.venv/bin/python skills/gitlab-ci-performance/scripts/report_cli.py render --report reports/contract/report.json --language ru --output reports/contract/report.html
```

Он сохраняет не более 64 попыток/тип, обновляет метаданные всех исходов, экспортирует
безопасные summaries ограниченных traces и заранее рассчитывает findings всех окон
32/64. Полный JSON, overview, выбранное окно и попытки используют те же измерения,
что offline HTML. [Контракт](skills/gitlab-ci-performance/references/contract-v2.md)
описывает selectors, бюджеты, baseline/интервалы, provenance рекомендаций и legacy.
`examples/generate_v2.py` генерирует публичный синтетический пример. Отдельные kinds
`gitlab_job_performance_*` отличают этот формат от опубликованного; CLI отклоняет
чужой формат, не преобразуя его незаметно. Дополнение находится в main до следующего
релиза и не заменяет опубликованный v2.0.1.

MIT — [лицензия](LICENSE).
