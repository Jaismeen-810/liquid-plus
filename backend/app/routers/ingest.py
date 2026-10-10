from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import Book
from app.db import get_db
from app.deps import get_current_user, require_support
from app.errors import NotFoundError
from app.models import RowValidationError, UploadBatch
from app.schemas import BatchOut, CurrentUser, Page, RowError, RunDateOut, UploadResult
from app.services.ingestion import available_run_dates, ingest_file

router = APIRouter(prefix="/ingest", tags=["ingestion"])

BOOK_PATHS = {"assets": Book.ASSET, "liabilities": Book.LIABILITY, "historical": Book.HISTORICAL}
PREVIEW_ERRORS = 50


@router.post("/{book_path}", response_model=UploadResult)
async def upload(
    book_path: str,
    file: UploadFile = File(...),
    run_date: date | None = Form(None),
    user: CurrentUser = Depends(require_support),
    db: Session = Depends(get_db),
):
    if book_path not in BOOK_PATHS:
        raise NotFoundError(f"Unknown book '{book_path}'. Use one of {', '.join(BOOK_PATHS)}")
    book = BOOK_PATHS[book_path]
    batch, predictions = ingest_file(db, book, await file.read(), file.filename or "upload", user, run_date)
    errors = db.scalars(
        select(RowValidationError).where(RowValidationError.batch_id == batch.id).order_by(RowValidationError.row_number).limit(PREVIEW_ERRORS)
    ).all()
    message = f"{batch.rows_accepted} of {batch.rows_total} rows accepted"
    if batch.rows_rejected:
        message += f", {batch.rows_rejected} rejected"
    return UploadResult(batch=BatchOut.model_validate(batch), errors_preview=[RowError.model_validate(e) for e in errors],
                        message=message, predictions=predictions)


@router.get("/run-dates", response_model=list[RunDateOut])
def run_dates(_: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return available_run_dates(db)


@router.get("/batches", response_model=list[BatchOut])
def batches(limit: int = Query(20, ge=1, le=200), _: CurrentUser = Depends(require_support), db: Session = Depends(get_db)):
    return db.scalars(select(UploadBatch).order_by(UploadBatch.id.desc()).limit(limit)).all()


@router.get("/batches/{batch_id}/errors", response_model=Page[RowError])
def batch_errors(
    batch_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    _: CurrentUser = Depends(require_support),
    db: Session = Depends(get_db),
):
    if db.get(UploadBatch, batch_id) is None:
        raise NotFoundError(f"Upload batch {batch_id} not found")
    stmt = select(RowValidationError).where(RowValidationError.batch_id == batch_id)
    total = db.scalar(select(func.count()).where(RowValidationError.batch_id == batch_id))
    rows = db.scalars(stmt.order_by(RowValidationError.row_number).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[RowError.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)
