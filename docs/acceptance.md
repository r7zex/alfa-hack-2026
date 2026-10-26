# Фактическая приёмка · 26.10.2026

Тестируется только `feat/integrated-credit-pipeline`. Рабочая БД сохранена. Использованы отдельные `delora-final-qa` и `delora-final-clean` Compose-проекты/volumes и отдельные PostgreSQL databases для тестов и миграций.

## Backend и инструменты

| Проверка | Результат |
|---|---|
| Python полный прогон | 178 passed,3 skipped; 248.81с |
| PostgreSQL auth/pipeline/analyst/product | 46 passed; 285.83с, включая конкурентные решения/выдачу/claim |
| JavaScript | 16 passed, включая delayed restore и смену двух demo-компаний |
| Статический анализ | Ruff E9/F63/F7/F82 passed; node --check JS modules passed |
| Upgrade существующей PostgreSQL схемы | Отдельный тест passed: сохранены account/password hash/session/draft при upgrade c001001→head |
| Fresh PostgreSQL + Alembic | Docker fresh volume запущен; head c002002; alembic check без расхождений |
| Seed дважды на fresh volume | Одинаково:16users,12applications,23PDF,12jobs,10ML,1loan,1contract |
| Restart PostgreSQL + API | 1 passed: та же cookie-сессия, byte-identical PDF, workflow/договор/выдача сохранены |
| Secret-shaped scan | Финальная проверка tracked source; не заменяет аудит всех секретов/зависимостей |

Пропуски полного SQLite-прогона: два PostgreSQL concurrency теста выполняются в отдельном PG-прогоне; отдельный PG migration test требует пустую migration-БД и запускался отдельно. Предупреждения Pydantic alias metadata не приводят к падению API/тестов; OpenAPI и реальные camelCase payload проверяются интеграцией.

## Browser E2E

`tests/e2e_product.py` выполняет изменения через реальные формы, загрузки PDF и банковские экраны, без mutation API-shortcuts. Браузер — Chromium/Playwright1.64.1. H включается только при E2E_QWEN=1 и живом endpoint.

| Сценарий | Проверяемый результат |
|---|---|
| A | Финансовый подбор → новый wizard/PDF → worker auto → accept → server code → sign → issue → loan/table/chart/CSV/reload |
| B | Manual → underwriter assignment → product/amount/months/rate/expiry counter → client accept/sign/issue |
| C | Банк создаёт документную задачу → PDF → DONE → повторная подача → решение; настоящий bank chat и уведомления |
| D |10млн → underwriter → escalation → approver decision |
| E | Admin BKI unavailable →3attempts/error → success → retry → ровно одно предложение/ML |
| F | Employee готовит заявку без права принятия/подписи → другой signatory завершает сделку |
| G |24синтетических признака → настоящий native score → сохранение/reload/contributions; UI QA1440/1024/390/320 без overflow/pageerror |
| H | Реальный CPU Qwen2.5:1.5b отвечает о кредите и отказывает в погоде;1passed,178.05с |

A–G на итоговом Docker-образе: **7passed,1skipped за106.11с**. Пропущен H, который запускался отдельно с реальной моделью. Worker/API/db healthy после исправления healthcheck. H фактически выполнен ранее в этой же задаче на native Ollama0.13.5 CPU (не mock, не утверждение о запуске optional Ollama-контейнера). Рабочее окружение затем перезапускалось; повторная загрузка весов для основного Docker-теста не требовалась. Код Qwen после успешного H не менялся.

`tests/e2e_worker_recovery.py`: **настоящий kill/recovery1passed за50.07с**, задача завершилась со2попытки, ровно1ML и1offer. Тест дополнительно проверяет восстановление по lease; запуск требует явных флагов одноразового проекта. Перезапуск app/DB проверен отдельным тестом. Скриншоты и локальные логи находятся вне git в `/workspace/delora-verification`.

## Что найдено и исправлено при приёмке

Восстановление offer из identity map после освобождения блокировки могло ломать конкурентную выдачу; latest_offer теперь перечитывается. Незавершённые frontend-запросы могли возвращать старую компанию/статус; введены уникальные server identities и guards поколений/порядка ответов. Фоновые обновления могли сбрасывать набираемое сообщение, выбранный source mode и согласия wizard; формы сохраняются по точной идентичности, завершившаяся загрузка не перерисовывает шаг согласий. Форма банковского решения теперь требует reviewed expectedVersion и не переназначает старую мотивировку новой версии. Health worker не загружает ML-библиотеки и использует Core-запрос, не требующий конфигурации всех ORM mappers.

## Границы доказательств

- Реальные банковские/государственные API, деньги и УКЭП не интегрированы; все source fixtures и issuance синтетические.
- Реальный imported inference проверен только на явно синтетических профилях, не на подтверждённых финансовых отчётах. Target mapping, training units, calibration, threshold и holdout неизвестны. Исходный CV PR-AUC — метаданные, не воспроизведённый holdout.
- Binary-log-loss training path протестирован на тестовом наборе. Исходный обучающий датасет не предоставлен; новые реальные AP/ROC-AUC/F1/F2 не заявляются.
- Qwen H — реальная проверка двух сценариев на CPU; не доказательство качества всех ответов. На слабом CPU возможны минуты ожидания. При недоступной модели остальные функции работают.
- PDF/CMS offline проверка не доказывает подлинность ФНС и актуальный отзыв сертификата.
- Firefox/Safari, массовая нагрузка, production TLS/backup/HA не проверялись.
- GitHub Actions настроен; локально выполнены соответствующие проверки. Статус GitHub run проверяется отдельно после push.
