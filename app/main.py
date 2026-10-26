"""ASGI entrypoint. Product routers will be included here as they are built."""

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from time import monotonic
import json
import logging

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logging.basicConfig(level=logging.INFO,format="%(message)s")

from app.db.session import engine
from app.api.applications import router as applications_router
from app.api.products import router as products_router
from app.frontend import FrontendFiles
from app.api.auth import router as auth_router


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


@app.middleware("http")
async def private_api_responses(request, call_next):
    started=monotonic()
    supplied=request.headers.get('x-request-id','')
    request_id=supplied if len(supplied)<=64 and supplied.replace('-','').isalnum() else str(uuid4())
    response = await call_next(request)
    response.headers['X-Request-ID']=request_id
    logging.getLogger('requests').info(json.dumps({'event':'http_request','request_id':request_id,
        'method':request.method,'path':request.url.path,'status':response.status_code,
        'duration_ms':round((monotonic()-started)*1000,2)}))
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


from app.api import analyst, documents, scoring, assistant, pipeline, operations, analytics, live, demo

app.include_router(demo.router)
app.include_router(operations.router)
app.include_router(analytics.router)
app.include_router(live.router)
app.include_router(analyst.router)
app.include_router(documents.router)
app.include_router(scoring.router)
app.include_router(assistant.router)
app.include_router(pipeline.router)
app.include_router(products_router)
app.include_router(applications_router)


# Keep this mount after API routes so /health, /ready and future routers win.
# HTML mode serves index.html at /; relative CSS and module URLs stay valid.
app.mount(
    "/",
    FrontendFiles(directory=Path(__file__).resolve().parent / "static", html=True),
    name="frontend",
)
