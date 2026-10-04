[English](README.md) | [Русский](README.ru.md)

# Анализатор производительности GitLab CI

Скилл для агента, который анализирует длительность джоб GitLab CI, очереди
раннеров и ухудшение времени выполнения через `glab`. Сохраняйте JSON-снимки
с версиями, сравнивайте запуски и открывайте автономный HTML-отчёт прямо в браузере.

![Синтетический отчёт о производительности GitLab CI](docs/report.png)

Скриншот и [пример отчёта](examples/report.html) используют **синтетические данные**.
Скачайте HTML и откройте его локально; сервер и внешние ресурсы не нужны.

## Возможности

- Анализирует проверенные цепочки workflow и независимые операции в окнах 32/64 pipeline.
- Отделяет время выполнения джоб от ожидания в очереди раннера.
- Сравнивает последний успешный pipeline или окно pipelines с базовой выборкой.
- Выделяет ухудшение P50 и показывает P95, размеры выборок, повторные попытки и историю джоб.
- Сохраняет JSON-снимки со строгими схемами и хешами источников для последующих сравнений.
- Показывает стековый график pipelines и описания джоб из необязательного проверенного каталога.

Сбор выполняет только запросы чтения к GitLab API через существующую авторизацию
`glab`. Логи и переменные джоб не запрашиваются. При этом отчёты могут содержать
названия проектов и джоб, описания раннеров и URL: выбирайте, где хранить свои
отчёты и кому их передавать.

## Установка скилла в проект

Клонируйте этот репозиторий. Из проекта, в котором хотите использовать скилл:

```bash
mkdir -p .agents/skills .codex/skills .claude/skills
cp -R /path/to/gitlab-ci-performance-skill/skills/gitlab-ci-performance .agents/skills/
ln -s ../../.agents/skills/gitlab-ci-performance .codex/skills/gitlab-ci-performance
ln -s ../../.agents/skills/gitlab-ci-performance .claude/skills/gitlab-ci-performance
```

Вызовите `$gitlab-ci-performance` в Codex или `/gitlab-ci-performance` в Claude
Code. Попросите проанализировать URL проекта или сравнить два сохранённых снимка.
Следуйте инструкциям проекта для агента и используйте учётную запись с разрешённым
доступом к GitLab.

Интерфейс отчёта поддерживает английский (по умолчанию) и русский.
Инструкции скилла для агента и методика написаны на английском.
Английская документация доступна в [README.md](README.md).

Рекомендации по оптимизации используют
[маршрут официальных источников](skills/gitlab-ci-performance/references/optimization-sources.md):
агент читает актуальную документацию и для каждого предложения фиксирует
измеренные данные, применимость, проверку источника и план замеров до и после.

Для воспроизводимой установки или обновления выберите опубликованный тег релиза
в исходном клоне и скопируйте **весь** каталог `skills/gitlab-ci-performance`,
включая `references`, в `.agents/skills/gitlab-ci-performance`. Перед обновлением
проверьте локальные доработки. Не копируйте только `SKILL.md`: справочник входит в
ту же версию скилла. Существующие симлинки Codex/Claude продолжают указывать на
этот установленный каталог.

После установки или обновления проверьте, что ссылка Optimization recommendations
в установленном `SKILL.md` ведёт к `references/optimization-sources.md`, а оба файла
совпадают с выбранным релизом. Проверка локальной копии не подтверждает публикацию
релиза в upstream.

## Запуск CLI напрямую

Требования: Python 3.10+, `glab` и существующая авторизация для вашего GitLab-хоста.
Из этого репозитория:

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

Откройте `reports/run-001/report.html` прямо в браузере. Для каждого запуска нужен
новый путь вывода; существующие артефакты не перезаписываются. По умолчанию
используется UTC; `--timezone` принимает часовой пояс IANA.

Язык HTML выбирается параметром `render --language en|ru`:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/run-001/report.json --language ru \
  --output reports/run-001/report-ru.html
```

Без `--language` используется английский; неподдерживаемые значения отклоняются.
Заголовки, элементы управления, подписи графиков, подсказки, пояснения статусов,
даты, числа и единицы времени отображаются на выбранном языке. Часовой пояс
берётся из сохранённого снимка. Имена заданий, этапы, refs, URL и проверенные
описания каталога сохраняются дословно. JSON и встроенные исходные данные не
меняются: один JSON можно отобразить на обоих языках без повторного сбора.
Новые отчёты записывают `purpose_from_catalog`, чтобы переводить служебный текст
неизвестного назначения, сохраняя описания каталога. Старые отчёты без этого
необязательного признака сохраняют все описания дословно.

Для сохранённой базовой выборки добавьте `--baseline reports/run-000/jobs.json`
к `report`. Перекрывающиеся выборки pipelines явно отмечаются и не дают оснований
утверждать ухудшение.

Для уникальных релизных тегов явно выберите refs:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot reports/run-001/jobs.json --release-refs v1.0 v1.1 v1.2 v1.3 \
  --output reports/releases/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/releases/report.json --output reports/releases/report.html
```

Откройте **Release history across selected refs / tags** в HTML и выберите джобу
и попытку. В деталях показаны выполнение, очередь, исходный ref и контекст.
Изменения между refs — наблюдения с явными N и IDs базы; сравнение одного ref
остаётся по умолчанию. Окна 32/64 ограничивают только видимый график.
Подробнее — в [методике истории релизов](skills/gitlab-ci-performance/references/release-history.md).
Новые report schema/calculation используют 1.1.0; jobs остаются 1.0.0.
Старые отчёты 1.0.0 доступны для просмотра обновлённым скиллом.

Синтетический пример с несколькими тегами без доступа к GitLab:

```bash
.venv/bin/python examples/generate_release_demo.py --output-dir reports/release-demo
```

Попробуйте синтетический пример без учётной записи GitLab:

```bash
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py report \
  --snapshot examples/jobs.json --catalog examples/catalog.json \
  --output reports/demo/report.json
.venv/bin/python skills/gitlab-ci-performance/scripts/ci_report.py render \
  --report reports/demo/report.json --output reports/demo/report.html
```

## Артефакты и интерпретация

![Синтетический workflow-отчёт](docs/workflow-report.png)

В версии скилла **2.0.0** добавлен workflow-режим с сохранением исходных артефактов
v1. Правила и CLI — в [методике workflow](skills/gitlab-ci-performance/references/workflows.md),
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
Установленная копия содержит оба модуля, шаблоны, схемы и модель; папки tests/examples
исходного репозитория ей не нужны.

Следующая интерпретация относится к исходному job-only режиму:

- [`jobs.schema.json`](skills/gitlab-ci-performance/schemas/jobs.schema.json): исходная проекция попыток выполнения джоб и метаданных pipelines.
- [`report.schema.json`](skills/gitlab-ci-performance/schemas/report.schema.json): производные метрики, политика сравнения, выборки и хеши входных данных.
- `report.html`: автономный отчёт со встроенными данными. Работает и после переноса без отдельных JSON-файлов.

По умолчанию для ухудшения требуется рост P50 **не менее чем на 20% и 30 секунд**
при как минимум трёх наблюдениях в базовой выборке. Пороги настраиваются;
один текущий запуск — это наблюдение, а не установленный тренд. Для сравнения
времени используются успешные попытки выполнения джоб в успешных pipelines одной ref.

Время в очереди pipeline — это ожидание до первого старта; очереди отдельных
джоб показаны отдельно. Стековый график не измеряет полный жизненный цикл.
Отсутствующие значения времени остаются отсутствующими и не превращаются в нули.
Сбор через API не является атомарной транзакцией и не может восстановить удалённые
джобы или bridge/trigger jobs. Автоматического расписания и профилирования
на уровне ресурсов нет.

Подробности — в [методике](skills/gitlab-ci-performance/references/methodology.md)
и [примере необязательного каталога](examples/catalog.json).

## Разработка

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Создайте другой синтетический пример командой `examples/generate_demo.py --output-dir
reports/new-demo` в том же Python-окружении, указав новый путь вывода.
`tests/browser_check.cjs` — необязательная проверка Playwright/Chrome для просмотра
локального файла при отключённой сети. Установите Playwright в среде разработки
и передайте URL файла, каталог для скриншотов и необязательный ожидаемый язык
(`en` по умолчанию или `ru`). Выполните проверку обоих HTML-вариантов;
тест использует имена заданий и ID пайплайнов синтетического примера.
`tests/browser_release_check.cjs` принимает те же аргументы для примера релизов
и проверяет оба языка панели истории релизов.

## История изменений

История изменений — в [CHANGELOG.md](CHANGELOG.md).

## Лицензия

MIT — см. [LICENSE](LICENSE).
