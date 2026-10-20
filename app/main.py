"""ASGI entrypoint. Product routers will be included here as they are built."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine


@asynccontextmanager
async def lifespan(application: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Alfa Hack — Smart Credit Cabinet",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["Infrastructure"])
async def health() -> dict[str, str]:
    """Liveness check: no external dependencies."""
    return {"status": "ok"}


@app.get("/ready", tags=["Infrastructure"])
async def ready() -> dict[str, str]:
    """Readiness check: confirm that PostgreSQL accepts queries."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail="Database is unavailable"
        ) from exc
    return {"status": "ready", "database": "connected"}
