import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.errors import register_error_handlers
from app.logs import setup_logging
from app.routers import auth, health, ingest, ladder, ml, reports

settings = get_settings()
setup_logging()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("%s started (%s)", settings.app_name, settings.environment)
    yield


app = FastAPI(lifespan=lifespan, title=settings.app_name, version=health.VERSION, description="Liquidity gap forecasting: deterministic and behavioral ladders")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
register_error_handlers(app)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    logger.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000)
    return response


app.include_router(health.router)
for module in (auth, ingest, ladder, ml, reports):
    app.include_router(module.router, prefix=settings.api_prefix)
