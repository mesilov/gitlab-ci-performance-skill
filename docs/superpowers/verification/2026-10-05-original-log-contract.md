# Проверка ТЗ: исходные логи, JSON 64 MiB, окна 16/32

Дата: 2026-10-05 (Asia/Bishkek).
Исходный origin/main, полученный git fetch origin main: 70761551beb0f589aa221d078002187faa872c64.
Рабочая ветка: codex/original-logs-windows-16-32.
Целевой маршрут: report_cli.py collect → report → export → render.
Канонический schema/calculation 3.0.0, parser 2.0.0. Старые masked snapshots
(включая schema2.2.0/parser1.2.0) отклоняются до transport/render/export;
нужны полученные заново или отдельно сохранённые оригинальные байты.

## Реализовано

- JSON до 67 108 864 сериализованных UTF-8 байтов включительно: чтение cap+1,
  дополнительная проверка canonical encoding, validate/save/calculation/export/render.
  HTML не получает этот размерный предел. Проверены кириллица и точная граница.
- Все страницы 16/32, default16, при retention64 на тип; page*size, соседние
  Older/Newer и Latest/page0. Ошибки/отмены/повторы входят в число попыток.
  Baseline до10 подходящих предыдущих успешных наблюдений независим.
- Оригинальные headers/stages/instructions/arguments/references сохраняются без
  маскирования. Base64 хранит полученные байты lossless; physical LF lines,
  job ID, hash/prefix hash, image/operation/part связи задают provenance.
- textContent и JSON script escaping показывают markup как текст; ru/en source
  одинаков. Полный source доступен даже для unsupported/partial. Copy и
  byte-download не требуют внешней сети. Fallback copy устанавливает исходный
  clipboard text через copy event, сохраняя CR/LF. Длинные строки визуально
  свёрнуты/прокручиваются, весь текст остаётся в DOM/JSON/export и копируется.
- Лимиты приёмки evidence:4096 nodes,16 MiB сериализованного trace включая source,
  транспорт4 MiB/50 000 LF lines. Точная причина/первая пропущенная строка явны;
  поступившие исходные байты не отбрасываются. ANSI CSI/outer CR удаляются только
  из отдельного читаемого вида/recognition probe. Невалидный UTF-8 заменяется только
  в текстовых видах с пояснением; raw download/base64 остаются lossless.

## До / после (синтетический пример)

Исходная строка (Python repr):
    '#1 [php-builder 1/1] RUN  echo "hello" && install --flag=value  '

Ранее source_label.text:
    '[stage 1/1] RUN [redacted]'

Теперь source_label.text:
    '[php-builder 1/1] RUN  echo "hello" && install --flag=value  '

Сохранены исходное имя стадии, двойные и завершающие пробелы, полные аргументы.
Полная исходная строка с номером BuildKit доступна в raw source/fragment.

## Проверки

- Test-first: исходные headers/raw source/64MiB boundaries и16/32 pages сначала
  воспроизведены на main как FAIL; после реализации GREEN.
- Полный unittest/CLI/installed-skill набор:267 tests PASS (53.766s).
- Финальный installed collect→report→export→render test генерирует единый JSON
  >16 MiB по трём типам jobs и переносимый HTML; source остаётся неизменяемым.
- Проверено ровно64 MiB и превышение на2 UTF-8 байта валидного canonical source.
- Histories0/1/16/17/32/33/64: все страницы, порядок, reciprocal links, отсутствие
  пропусков/дубликатов, страничные статистики/findings и независимый baseline.
- Дополнительные regressions: ведущий CR в source association; earliest omitted
  line при удалении родительской группы; исходный reference совпадает с log line.
- Offline browser: canonical parity/navigation/keyboard/mobile320/375/1280px,
  light/dark, standalone/no-network; source full long title/RU-EN/copy/fallback/
  original-byte download/injection; known/unknown/cached identities и root/parts.
- CI masking assertions исправлены. Новая original-source QA включена в check.yml
  и уважает CI_REPORT_BROWSER_CHANNEL=chromium. Удалённые CI jobs здесь не запускались.
- Независимые spec и quality review: approved; найденные конкретные дефекты исправлены.
  git diff --check PASS.

## Реальная свежая проверка

Проект gitlab.rarus.ru / web-dr/indigo/indigo-bitrix24-src, ID2967.
Контрольная job252624: повторно получено154 289 байт; SHA-256
9f9de41f9b9f03b023aff4283e90f72c38cab2980d745c884b85bf52cd5234e5.

Подтверждены восемь сборок в прежнем порядке:
php, nginx, percona, redis, sphinx, push, backup, pmm-client.
Старый main и новый parser на тех же полученных байтах дают126 evidence nodes
с одинаковыми категориями, длительностями, позициями, вложенностью и complete
флагами nodes. Префиксы/аргументы теперь оригинальные. Физических строк1739,
распознано930: source parsing явно partial,100% покрытия не заявляется.

Свежая collection:64 build-images +64 open-release-mr +15 cleanup-runner,
всего143 сохранённых attempts. Дополнительные метаданные API сохранены отдельно
от retained selection. Отчёт same_ref сохраняет прежнюю фильтрацию latest ref.
Для просмотра всей сохранённой истории построен явный exploratory cross_ref с
108 разрешёнными refs из snapshot:14 окон, build-images/open-release-mr имеют
четыре страницы16 и две32; cleanup-runner одну страницу каждого размера.
Исследовательское сравнение разных refs не доказывает регрессию/причину.
Состояния trace:128 partial,8 empty,7 not_run. Числовые измерения не выдумываются.

## Локальные артефакты

- /Users/mesilov/.codex/worktrees/6974/gitlab-ci-performance-skill/reports/original-logs/jobs.json: 21,608,147 байт (20.61 MiB).
- /Users/mesilov/.codex/worktrees/6974/gitlab-ci-performance-skill/reports/original-logs/report-allrefs.json: 45,821,939 байт (43.70 MiB).
- /Users/mesilov/.codex/worktrees/6974/gitlab-ci-performance-skill/reports/original-logs/report-verified.html: 45,903,194 байт (43.78 MiB).
- /Users/mesilov/.codex/worktrees/6974/gitlab-ci-performance-skill/reports/original-logs/attempt-252624.json: 361,946 байт (0.35 MiB).

Все реальные source/report файлы остаются локально в ignored reports/. Доступ к
каталогу original-logs ограничен владельцем. Публичный examples/v2 заново
сгенерирован из синтетики, без ручного редактирования HTML.

Воспроизведение синтетической проверки:
    .venv/bin/python -m unittest discover -s tests -v
    .venv/bin/python examples/generate_v2.py --output-dir reports/new-synthetic
    .venv/bin/python tests/generate_original_fixture.py --output-dir reports/new-source
    CI_REPORT_PLAYWRIGHT=/path/to/playwright node tests/browser_original_source.cjs file:///absolute/path/reports/new-source/report.html reports/new-source/qa

При повторной генерации всегда выбирайте новые output пути.
