# Архитектура, состояния и ERD

```mermaid
flowchart LR
  UI[ES modules · сохранённый дизайн] -->|HttpOnly cookie + CSRF| API[FastAPI]
  API --> PG[(PostgreSQL)]
  API -->|SSE · cookie · Last-Event-ID| UI
  PG -->|SKIP LOCKED · lease · fencing| Worker[Python worker]
  Worker --> Sources[6 независимых mock-адаптеров]
  Worker --> Features[FinancialFeaturesProvider]
  Features --> Native[Проверенный native LightGBM]
  Worker --> Rules[Snapshot демо-правил]
  Worker --> PG
  API -->|опционально · три этапа проверки| Qwen[Qwen 2.5 1.5B / Ollama CPU]
```

API принимает submit без долгой обработки. Job хранит submission, stage, attempts, run_after, lease_token/until и snapshot правил/источников. Worker фиксирует snapshot, завершает транзакцию, вызывает адаптер/ML, затем повторно проверяет fencing token и сохраняет результат. Истёкший RUNNING lease подхватывается; максимальное число попыток ограничено. API и worker используют один runtime-образ; отдельный heartbeat проверяется внутри worker-контейнера. Redis/Celery не требуются.

```mermaid
stateDiagram-v2
  [*] --> draft
  draft --> submitted: согласия
  needs_info --> submitted: обязательные задачи закрыты
  submitted --> data_check
  data_check --> enrichment
  enrichment --> scoring
  scoring --> decision
  decision --> approved: auto / правила
  decision --> counter_offer: auto / меньшая сумма
  decision --> pending: специалист
  decision --> rejected: стоп-фактор
  data_check --> needs_info: нет документов
  decision --> needs_info: нет сведений
  enrichment --> processing_error: попытки исчерпаны
  scoring --> processing_error: технический отказ
  processing_error --> submitted: повтор
  pending --> approved
  pending --> counter_offer
  pending --> needs_info
  pending --> rejected
  pending --> escalated
  escalated --> approved: согласующий
  escalated --> counter_offer
  escalated --> rejected
  escalated --> needs_info
  escalated --> pending: вернуть аналитику
  approved --> offer_accepted
  counter_offer --> offer_accepted
  approved --> offer_declined
  counter_offer --> offer_declined
  approved --> pending: отзыв предложения
  counter_offer --> pending: отзыв предложения
  offer_accepted --> signed: одноразовый код и hash
  signed --> disbursed: mock-регистрация
  draft --> cancelled
  pending --> cancelled
```

Разрешённые переходы и дополнительные cancel-ветви проверяются в `services/pipeline.py`. Повторные accept/sign/disburse возвращают существующий результат. Истечение предложения проверяется сервером, не меняет задним числом условия; worker создаёт уведомления об истечении. Старые `processing`/`completed` сохранены для совместимости, completed без выдачи не создаёт LoanAccount.

```mermaid
erDiagram
  Business ||--o{ User : employees
  User ||--o{ AuthSession : sessions
  Business ||--o{ LoanApplication : applications
  LoanApplication ||--o{ ApplicationEvent : history
  LoanApplication ||--o{ PipelineJob : submissions
  LoanApplication ||--o{ ProcessingRun : assessment
  LoanApplication ||--o{ ModelPrediction : technical_scores
  Business ||--o| FinancialProfile : features
  PolicyVersion ||--o{ DecisionRecord : rules
  LoanApplication ||--o{ DecisionRecord : decisions
  LoanApplication ||--o{ CreditOffer : versions
  CreditOffer ||--o{ SigningChallenge : codes
  CreditOffer ||--o| DemoContract : signature
  LoanApplication ||--o| DemoDisbursement : issuance
  LoanApplication ||--o| LoanAccount : schedule
  LoanApplication ||--o{ ApplicationTask : tasks
  LoanApplication ||--o{ ApplicationMessage : bank_chat
  LoanApplication ||--o{ MessageRead : receipts
  LoanApplication ||--o{ Notification : events
  Business ||--o{ Document : pdf
  LoanApplication ||--o{ ApplicationDocument : links
  Document ||--o{ ApplicationDocument : reuse
  Business ||--o{ TeamInvitation : invitations
  User ||--o{ StreamLease : sse_limits
  User ||--o{ AdminAudit : changes
  SourceSetting ||--o{ PipelineJob : captured_modes
```

Связь SourceSetting→job на схеме логическая: режимы снимаются в snapshot/историю, FK нет. WorkerHeartbeat и SystemSetting — служебные записи. Договор, график и terms сохраняются неизменно; суммы графика — Decimal с округлением HALF_UP до копеек, JSON хранит десятичные строки.

Все модели регистрируются общей metadata. Миграции main не изменены; новые ревизии a2026c002001/002002 добавляют таблицы/роли/поля. PostgreSQL upgrade проверяет сохранность старой учётной записи, сессии и черновика. Данные чужих организаций скрываются 404, права операции — 403, конфликт версии/статуса — 409.
