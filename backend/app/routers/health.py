from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import check_db_connection
from app.schemas import DbHealthResponse, HealthResponse

router = APIRouter(tags=["health"])
VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    s = get_settings()
    return HealthResponse(status="ok", app=s.app_name, environment=s.environment, version=VERSION)


@router.get("/health/db", response_model=DbHealthResponse)
def health_db():
    ok, error = check_db_connection()
    body = DbHealthResponse(status="ok" if ok else "error", database="up" if ok else "down", error=error)
    return body if ok else JSONResponse(status_code=503, content=body.model_dump())
