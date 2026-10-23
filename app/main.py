"""ASGI entrypoint. Product routers will be included here as they are built."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine
from app.api.applications import router as applications_router
from app.api.products import router as products_router
from app.frontend import FrontendFiles
from app.api.auth import router as auth_router
from app.api.assistant import router as assistant_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Alfa Hack - Smart Credit Cabinet",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(assistant_router)


@app.middleware("http")
async def private_api_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


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


app.include_router(products_router)
app.include_router(applications_router)


# Keep this mount after API routes so /health, /ready and future routers win.
# HTML mode serves index.html at /; relative CSS and module URLs stay valid.
app.mount(
    "/",
    FrontendFiles(directory=Path(__file__).resolve().parent / "static", html=True),
    name="frontend",
)
