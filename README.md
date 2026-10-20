# Alfa Hack 2026 — Умный кредитный кабинет предпринимателя

Прототип кредитного конвейера для малого и микробизнеса. Сейчас реализован
**инфраструктурный каркас**; подбор продукта, заявки, скоринг и авторизация
подключаются в следующих ветках. Все демонстрационные данные должны быть
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

Нужны только Docker Engine/Desktop с Docker Compose и свободные порты 8000, 5432.

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

Swagger: http://127.0.0.1:8000/docs

Логи: `docker compose logs -f app`.
Остановка без удаления данных: `docker compose down`.
**Внимание:** `docker compose down -v` удаляет volume PostgreSQL и данные.

Если на хосте заняты порты, поменяйте `APP_PORT` или `DB_PORT` в `.env`.
При изменении `APP_PORT` поменяйте порт в URL для проверки.

## Разработка в PyCharm: FastAPI на хосте, БД в Docker

Для Python 3.12:

```bash
cp .env.example .env
docker compose up -d db
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`.env` читается локально через pydantic-settings; `DB_HOST=127.0.0.1`.
При запуске через Compose `DB_HOST` автоматически заменяется на `db`,
так как приложение и БД находятся в одной Docker-сети.

Остановите локальный Uvicorn перед `docker compose up -d app`, иначе
оба процесса будут пытаться занять порт 8000.

## Тесты

```bash
python -m pytest tests/test_infra.py -q
```

Smoke-тесты не требуют работающей БД. Ручная проверка `/ready` при
запущенном Compose проверяет реальное соединение с PostgreSQL.
Этот этап пока не создаёт таблицы и не выполняет миграции.

## Развёртывание на VPS

На VPS можно использовать тот же Compose; пример:

```bash
cp .env.example .env
# Измените DB_PASSWORD на сильный пароль и настройте доступ к серверу.
docker compose up --build -d
```

По умолчанию порты **FastAPI и PostgreSQL привязаны к 127.0.0.1**
и не выставляются в интернет. Чтобы открыть сайт извне, настройте
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
