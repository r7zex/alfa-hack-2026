# Alfa Hack 2026 — Умный кредитный кабинет предпринимателя

Прототип кредитного конвейера для малого и микробизнеса. Реализованы
инфраструктурный каркас и демонстрационный фронтенд, доступный через FastAPI.
Продуктовые API, серверная авторизация и скоринг подключаются в следующих
ветках. Все демонстрационные данные должны быть
синтетическими. Проект не выполняет реальную выдачу кредита.

## Архитектура MVP

- Python 3.12, FastAPI, Uvicorn, SQLAlchemy AsyncSession, psycopg 3.
- PostgreSQL 16 с Docker volume для сохранения данных.
- Один backend-контейнер + один контейнер базы данных в Docker Compose.
- `/health` — liveness; `/ready` — проверка связи с PostgreSQL;
  `/docs` — Swagger UI.
- Общая точка подключения к БД — `app/db/session.py`.
- Дополнительные Redis, Celery и отдельный ML-сервис пока не требуются.

## Проверка жюри: полностью в Docker

Нужны Docker Engine/Desktop с Docker Compose и свободный порт 8000. PostgreSQL не публикуется на хост.

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

Ожидаемый ответ `/health`: `{"status":"ok"}`.
Ожидаемый ответ `/ready`:
`{"status":"ready","database":"connected"}`.

Сайт: http://127.0.0.1:8000/. Swagger: http://127.0.0.1:8000/docs.

Фронтенд использует демонстрационные данные в браузере. Подробности:
[docs/frontend.md](docs/frontend.md).

Логи: `docker compose logs -f app`.
Остановка без удаления данных: `docker compose down`.
**Внимание:** `docker compose down -v` удаляет volume PostgreSQL и данные.

Если на хосте занят порт FastAPI, поменяйте `APP_PORT` в `.env`.
При изменении `APP_PORT` поменяйте порт в URL для проверки.

## Разработка в PyCharm: FastAPI локально, PostgreSQL в Docker

Локально можно использовать уже установленный Python 3.13. Однако в образе
для жюри используется Python 3.12; итоговый код и ML-модели обязательно
проверяем также в контейнере на Python 3.12.

### 1. Настройка интерпретатора и зависимостей

В PyCharm: Settings → Python → Interpreter → Add Interpreter →
Add Local Interpreter → Virtualenv. Выберите Python 3.13 и путь
`.venv` в корне репозитория. В терминале проекта:

```bash
source .venv/bin/activate
python --version
python -m pip install -r requirements-dev.txt
```

Вместо PyCharm можно создать `.venv` командой `python3.13 -m venv .venv`.
Не устанавливайте зависимости в системный Python.

### 2. Запуск PostgreSQL

Если `.env` отсутствует: `cp .env.example .env`.
Не перезаписывайте свой существующий `.env`. Для локального режима
убедитесь, что в нём `DB_HOST=127.0.0.1` и `DB_PORT=15432`.
Если порт 15432 занят, выберите свободный порт, изменив `DB_PORT` в `.env`.
Проверьте занятость порта, например командой:

```bash
lsof -nP -iTCP:15432 -sTCP:LISTEN
```

Если ранее запускали FastAPI в Docker, сначала освободите порт 8000:

```bash
docker compose stop app
```

Запустите только базу с dev override:

```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d db
docker compose -f compose.yaml -f compose.dev.yaml ps
```

В этом режиме PostgreSQL открывает *только* `127.0.0.1:15432`
(или выбранный в `.env` порт). Контейнерный порт остаётся 5432.
На VPS и для жюри **не используем** `compose.dev.yaml`: в основном
Compose PostgreSQL вообще не имеет опубликованного порта.

### 3. Запуск FastAPI без Docker

В активированном виртуальном окружении:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Открыть сайт: http://127.0.0.1:8000/. Главная страница, CSS и JavaScript
раздаются этим же сервером. Для просмотра демо не требуется работающая БД,
но .env должен быть настроен. Проверка /ready требует PostgreSQL.

Либо настройте PyCharm → Run → Edit Configurations → Add New → Python:

- Interpreter: `.venv/bin/python`.
- Run: `Module name` → `uvicorn`.
- Parameters: `app.main:app --reload --host 127.0.0.1 --port 8000`.
- Working directory: корень `alfa-hack-2026`.

Сам FastAPI читает `.env` через pydantic-settings. При изменении Python-кода
Uvicorn автоматически перезапускает приложение без пересборки Docker.
Для стабильной работы брейкпоинтов при Debug можно убрать `--reload`.

Проверка:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

Чтобы вернуться к полностью контейнерному запуску, остановите локальный
Uvicorn и выполните `docker compose up --build -d` **без dev override**.

## Тесты

```bash
python -m pytest tests/test_infra.py tests/test_frontend_serving.py -q
```

Smoke-тесты не требуют работающей БД. Ручная проверка `/ready` при
запущенном Compose проверяет реальное соединение с PostgreSQL.
Таблицы создаются отдельно через Alembic.

## Миграции базы данных

Модели находятся в `app/models/user.py` и `app/models/business.py`.
Пакет `app.models` импортирует все модели в общую `Base.metadata`,
которую использует `alembic/env.py`.

После настройки `.env` и запуска PostgreSQL выполните из корня проекта:

```bash
python -m alembic upgrade head
python -m alembic check
```

В Docker миграции запускаются в контейнере приложения:

```bash
docker compose exec app python -m alembic upgrade head
```

При переносе моделей структура таблиц и ID существующей миграции
`1bd2be57b412` сохранены. Уже примененную миграцию повторно создавать
не нужно. Откат этой миграции удаляет таблицы и их данные.

## Развёртывание на VPS

На VPS можно использовать тот же Compose; пример:

```bash
cp .env.example .env
# Измените DB_PASSWORD на сильный пароль и настройте доступ к серверу.
docker compose up --build -d
```

По умолчанию **FastAPI привязан к 127.0.0.1**, а PostgreSQL
вообще не публикуется на хост. Чтобы открыть сайт извне, настройте
на VPS HTTPS reverse proxy (например, Caddy или Nginx), который
проксирует запросы к `127.0.0.1:8000`. Не публикуйте порт БД.
Используйте firewall, защищённые секреты и резервное копирование volume.
Конфигурацию proxy и домен добавим при реальном развёртывании.

## Командная разработка

- Инфраструктура: `feat/backend-bootstrap`.
- Авторизация: отдельная ветка `auth`.
- Backend использует единые `app/db/base.py` и `app/db/session.py`.
  Сервисные роутеры подключаются в `app/main.py`.
- `.env` не коммитим; пример `.env.example` содержит только
  демонстрационные значения, которые надо заменить для VPS.
- Изменения объединяем через Pull Request, не пушим напрямую в `main`.

Всю спецификацию кредитного процесса, тестовые аккаунты, правила
решения и комплект документации дополним в следующих итерациях.
