# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/alfa

COPY requirements.txt requirements-ml.txt ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    python -m pip install --no-cache-dir -r requirements.txt -r requirements-ml.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
