# EnsixD / Делора: проверка по исходникам и сценариям

Аудит26.10.2026. EnsixD main зафиксирован на `1a22e191868e106290758274540630a76543f3eb`; исходники прочитаны через GitHub API, проект конкурента не запускался. Делора до этой работы: `cad2514` после безопасного fast-forward собственной ветки (Auth, PDF, ручной workflow, Qwen transport и offline ML adapter уже существовали). Корневой LICENSE EnsixD через API не обнаружен. Код, изображения и стили оттуда не копировались.

Ссылки ниже относятся к неизменяемому snapshot. «Есть» для EnsixD означает наличие реализации в прочитанном коде, а не пройденную нами браузерную приёмку чужого продукта.

| Функция | EnsixD: источник | Делора: реализация и доказательство |
|---|---|---|
| Клиент, организация, заявки | [models.py](https://github.com/EnsixD/alfa-smart-credit-cabinet/blob/1a22e191868e106290758274540630a76543f3eb/backend/app/models.py), routers/applications.py | Исходная Auth сохранена; HttpOnly/SameSite/CSRF, Argon2. tests/test_auth.py, E2E A–G |
| Фоновый конвейер | [pipeline.py](https://github.com/EnsixD/alfa-smart-credit-cabinet/blob/1a22e191868e106290758274540630a76543f3eb/backend/app/pipeline.py), [worker.py](https://github.com/EnsixD/alfa-smart-credit-cabinet/blob/1a22e191868e106290758274540630a76543f3eb/backend/app/worker.py) | services/jobs.py, app/worker.py: stages, short transactions, SKIP LOCKED, lease/fencing; expired/stale/parallel tests и настоящий kill/recovery |
| Live tracker | [applications.py:253](https://github.com/EnsixD/alfa-smart-credit-cabinet/blob/1a22e191868e106290758274540630a76543f3eb/backend/app/routers/applications.py#L253) | api/live.py: cookie-auth, DB lease/лимит3, revocation, Last-Event-ID; E2E A/B без ручного reload, stream401/404/429 tests |
| UNDERWRITER/APPROVER, назначение, эскалация | [bank.py](https://github.com/EnsixD/alfa-smart-credit-cabinet/blob/1a22e191868e106290758274540630a76543f3eb/backend/app/routers/bank.py) | api/analyst.py, services/pipeline.py, operations API; E2E D, матрица ролей и ожидаемая версия решения |
| Сотрудник без подписи | models.py / User.can_sign | Hash-only одноразовое приглашение по email, нет входа по одному ИНН; E2E F и negative access tests |
| Авто-решения и правила | [credit.py:109](https://github.com/EnsixD/alfa-smart-credit-cabinet/blob/1a22e191868e106290758274540630a76543f3eb/backend/app/credit.py#L109), pipeline.py | policy_rules.py: версии в БД, snapshot при начале, cash buffer/age/burden/limits; E2E A–D, version-freeze test |
| Встречное предложение | routers/bank.py | Продукт/сумма/срок/ставка/причина/expiry/revoke, immutable offer versions; E2E B, expired/stale offer tests |
| Задачи и повторная подача | pipeline.py, routers/applications.py | Типизированные документы и info, required, ответы/даты; E2E C, задачи закрываются только совместимым документом |
| Чат и уведомления | models.py, routers/common.py, routers/bank.py | Сохраняемые сообщения/request_id/read receipts, notifications/dedupe/archive; E2E C, XSS literal и IDOR tests |
| Сбои источников | [integrations.py](https://github.com/EnsixD/alfa-smart-credit-cabinet/blob/1a22e191868e106290758274540630a76543f3eb/backend/app/integrations.py) | 6 независимых DB-настроек, bounded timeout/retry, сохраняемый circuit breaker; E2E E, source retry/fallback tests |
| Финансовый подбор | credit.py, routers/common.py | Финансы/обязательства/возраст/лимиты/причины/доступная сумма/платёж; E2E A. Балл не называется шансом одобрения |
| Кредит, график, CSV | [credit.py:34](https://github.com/EnsixD/alfa-smart-credit-cabinet/blob/1a22e191868e106290758274540630a76543f3eb/backend/app/credit.py#L34) | Decimal/календарные месяцы/точные копейки и последний остаток, интерактивный месяц; E2E A и leap-year/reconciliation tests |
| Подпись кодом | [applications.py:207](https://github.com/EnsixD/alfa-smart-credit-cabinet/blob/1a22e191868e106290758274540630a76543f3eb/backend/app/routers/applications.py#L207) | HMAC-only, expiry,5попыток, cooldown, user+offer binding, contractSHA; E2E A/B/F, OTP tests |
| Банковские метрики | routers/bank.py | DB/events, уникальные заявки в исторической воронке, queue/source errors, export; metrics tests, E2E G UI QA |
| Обученный ML | credit.py:109–145 — rule-based scorecard | Проверенные native LightGBM450деревьев/24признака, schema/hash/provenance/contributions; test_imported_model.py, E2E G. Score и кредитная политика разделены |
| Qwen | routers/common.py | Qwen2.5:1.5b, три этапа защиты, opt-in own-application context; actual CPU E2E H + policy/context/transport tests |
| UI и новости | Прочитаны исходники трекера, карточки банка, графиков и уведомлений | Сохранены наша графитовая палитра, красные акценты и изображения. E2E QA1440/1024/390/320. Новости исключены по запросу |

## Подтверждённые технические отличия

- В прочитанном worker EnsixD claim выбирает только PENDING (строка43), RUNNING выставляется на49; автоматического поиска истёкшего lease в этом файле нет. Делора проверяет lease и fencing token перед каждой фиксацией; проверяются одновременно несколько worker, устаревший token и реальный kill процесса.
- EnsixD SSE использует `user_from_query_token` (applications.py:254). Делора использует существующую HttpOnly session, повторно проверяет отзыв и ограничивает подключение через БД; токен не попадает в URL.
- В EnsixD signing JSON содержит открытый code (209) и сравнивается с ним (231). Делора сохраняет только keyed hash, привязывает challenge к человеку и предложению, ограничивает срок и попытки.
- EnsixD circuit breaker находится в `_breakers` dict процесса (integrations.py:44). Делора хранит состояние и настройки в PostgreSQL, а события сохраняют отказы для аналитики.
- В EnsixD schedule использует float/round и `timedelta(days=30*i)` (credit.py:34–52). Делора использует Decimal HALF_UP и календарные месяцы; сумма principal точно равна выдаче, проверены31января/29февраля и balloon overdraft.
- В EnsixD credit.score складывает points из YAML (credit.py:109–145). Делора дополнительно выполняет реальный импортированный LightGBM, проверяет его hash и вклады. Это преимущество проверяемости интеграции, не доказательство качества модели или лучших кредитных решений.

Полная матрица фактических прогонов и ограничений — [acceptance.md](acceptance.md). Сравнение не утверждает абсолютного превосходства, промышленной готовности или результатов не проводившегося нагрузочного теста.
