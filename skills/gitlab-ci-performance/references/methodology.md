# Методика версии 1.0.0

JSON Schema 2020-12; schema_version/calculation_version 1.0.0. Источники:
[Jobs API](https://docs.gitlab.com/api/jobs/),
[Pipelines API](https://docs.gitlab.com/api/pipelines/),
[glab api](https://docs.gitlab.com/cli/api/),
[JSON Schema](https://json-schema.org/draft/2020-12).

## История и фильтры

Сбор сохраняет доступную project Jobs API history, уникальные job IDs и
pipeline details. Keyset pagination ограничена 100 pages по умолчанию;
достижение лимита вызывает ошибку, а не успешный неполный отчёт. Anchor max
ID исключает более новые jobs, появившиеся во время collection. Статусы
могут изменяться во время сбора: это не атомарная транзакция. Deleted jobs,
bridge/trigger jobs не восстанавливаются. Инкрементального cache в v1 нет:
повторный GET-прогон обновляет текущие статусы и создаёт новый snapshot.

Timing сравнивается только между SUCCESS jobs внутри SUCCESS pipelines
одной ref. Внутри pipeline сохраняются все attempts/statuses, включая
дополнительные попытки одной job. Дополнительная попытка — не доказательство
автоматического retry или flaky test. Все статусы snapshot и самый свежий
pipeline видны отдельно. Job grouping: host/project/ref/stage/name.

Режим 1: последний successful pipeline против до 10 предыдущих successful
pipelines. Режим 10: до 10 последних против до 10 предыдущих. При внешнем
baseline его latest successful pipelines берутся независимо: пересечение
IDs помечает сравнение overlap и запрещает вывод о регрессии. Host/project
и версия schema обязаны совпадать. Окна определяются pipeline IDs в порядке
убывания; report сохраняет фактические IDs, from/to и N.

## Времена

- execution = API job duration; queue = API queued_duration.
- lifecycle = job finished_at - created_at, только при известном finish.
- execution+queue не обязано равняться lifecycle.
- started_at-created_at-queued_duration — остаток до старта; причины
  (stages/needs/manual/resource locks/прочее) из метаданных не установлены.
- pipeline duration — собственное API-поле pipeline, не сумма durations jobs.
- Верхний стековый график: pipeline duration + pipeline queued_duration для
  последних 20 успешных pipelines выбранной ref. Null не рисуется как известный
  ноль; подпись сообщает об отсутствующих компонентах. Это не полное lifecycle.
  Pipeline queued_duration — ожидание до первого старта, а не сумма очередей
  отдельных jobs. Семантика проверена по [модели pipeline GitLab](https://gitlab.com/gitlab-org/gitlab/-/blob/master/app/models/ci/pipeline.rb)
  и [расчёту duration](https://gitlab.com/gitlab-org/gitlab/-/blob/master/lib/gitlab/ci/pipeline/duration.rb);
  версии GitLab могут различаться, исходные API-поля сохраняются без подмены.

Null исключается из агрегата, сохраняя missing N. При отсутствии известных
значений sum/P50/P95/max = null. Sum отражает расход job-времени, а не
календарное ожидание разработчика. P50/P95: отсортированные значения,
линейная интерполяция по индексу `(n-1)*p`. Несколько attempts учитываются
отдельно; N attempt counts и pipeline counts могут отличаться.

## Ухудшение и неопределённость

По умолчанию ухудшение P50 требует одновременно роста >=20% и >=30 секунд,
baseline known N>=3, current known N>=1. Пороги управляются CLI и записаны
в report; это начальная configurable policy, не принятый SLO. При нулевой
базе percent=null; положительный рост проверяется абсолютным порогом.
Improved использует симметричную проверку, но UI не окрашивает улучшения.
P95 показывается для проверки хвостов, policy v1 классифицирует P50.

При N=1 это наблюдение конкретного pipeline, не устойчивый тренд. Sparse,
new/missing jobs и overlap остаются явными. Длительные queue показывают
симптом, но не доказывают недостаток CPU/RAM или конкретную runner-причину.
Смена pipeline source, job script/image/cache/runner может влиять на сравнение;
causal attribution требует отдельного изучения. Ref совпадает автоматически;
остальные контексты сохраняются в snapshot и доступны при разборе.

## Хранение и просмотр

`jobs.json` — safe source projection, `report.json` — производные метрики и
разницы с hashes источников. Каждый прогон — новый каталог. JSON сериализация
для hashes: UTF-8, ensure_ascii=false, sort_keys=true, indent=2, newline.
Report сравнивается повторно helper той же calculation_version; изменение
методики требует bump и пересчёта обоих snapshots. HTML имеет embedded JSON,
CSS/JS/SVG, работает offline и не содержит token/CDN/аналитику.
Открывай report.html непосредственно через file://; сервер не нужен.
Отдельные JSON нужны для повторного расчёта, а не для загрузки страницы.
Skill сам не создаёт расписание; будущий scheduled запуск должен работать
независимо от контролируемой CI-очереди и сообщать о stale collection.
