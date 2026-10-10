import io
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import RUN_DATE_IN_FILENAME, BatchStatus, Book
from app.errors import FileValidationError
from app.errors import AppError
from app.ml import behavior
from app.models import AssetBook, HistoricalLog, LiabilityBook, Prediction, RowValidationError, UploadBatch
from app.schemas import CurrentUser
from app.services import audit
from app.services.cashflow import simple_interest
from app.services.validation import validate_frame

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = {".csv", ".xlsx"}
CHUNK = 2000
LIVE_MODELS = {Book.ASSET: (AssetBook, "loan_amount"), Book.LIABILITY: (LiabilityBook, "amount")}


def run_date_from_filename(file_name: str) -> date | None:
    for token in RUN_DATE_IN_FILENAME.findall(file_name):
        for fmt in ("%d%m%Y", "%Y%m%d"):
            try:
                return datetime.strptime(token, fmt).date()
            except ValueError:
                continue
    return None


def read_table(content: bytes, file_name: str) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise FileValidationError(f"Unsupported file type '{suffix}'. Upload a .csv or .xlsx file")
    try:
        if suffix == ".csv":
            return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
        return pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)
    except Exception as exc:
        raise FileValidationError("File could not be read. Check that it is a valid CSV or Excel file") from exc


def _store_raw(content: bytes, book: Book, file_name: str) -> Path:
    folder = get_settings().upload_dir / book.value
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now():%Y%m%d%H%M%S}_{Path(file_name).name}"
    path.write_bytes(content)
    return path


def _enrich_live(records: list[dict], book: Book, run_date: date, batch_id: int) -> list[dict]:
    basis = get_settings().day_count_basis
    principal_key = LIVE_MODELS[book][1]
    for r in records:
        interest = simple_interest(r[principal_key], r["interest_rate_pct"], r["transaction_date"], r["maturity_date"], basis)
        r.update(run_date=run_date, batch_id=batch_id, interest_amount=interest, maturity_cashflow=r[principal_key] + interest)
    return records


def _save_live(db: Session, book: Book, records: list[dict], run_date: date, batch_id: int) -> None:
    model = LIVE_MODELS[book][0]
    db.execute(delete(model).where(model.run_date == run_date))
    db.execute(delete(Prediction).where(Prediction.run_date == run_date, Prediction.book == book))
    rows = _enrich_live(records, book, run_date, batch_id)
    for i in range(0, len(rows), CHUNK):
        db.execute(insert(model), rows[i:i + CHUNK])


def _save_historical(db: Session, records: list[dict], batch_id: int) -> None:
    for r in records:
        r["batch_id"] = batch_id
    update_cols = [c for c in records[0] if c != "transaction_id"] if records else []
    for i in range(0, len(records), CHUNK):
        stmt = pg_insert(HistoricalLog).values(records[i:i + CHUNK])
        stmt = stmt.on_conflict_do_update(
            index_elements=[HistoricalLog.transaction_id], set_={c: stmt.excluded[c] for c in update_cols}
        )
        db.execute(stmt)


def refresh_predictions(db: Session, book: Book, run_date: date) -> str:
    """Step 4 of ingestion: score the new positions with the behavioral model.

    A failure here never undoes the upload; predictions are rebuilt on the next AI-ladder request.
    """
    try:
        if book == Book.HISTORICAL:
            runs = behavior.predict_all_runs(db)
            return f"Behavioral calibration refreshed for {runs} run date(s)"
        count = behavior.predict_book(db, run_date, book)
        return f"{count} live {book.value} transactions scored by the behavioral model"
    except AppError as exc:
        db.rollback()
        logger.warning("Predictions skipped after %s upload: %s", book, exc.message)
        return f"Predictions pending: {exc.message}"


def ingest_file(
    db: Session, book: Book, content: bytes, file_name: str, user: CurrentUser, run_date: date | None = None
) -> tuple[UploadBatch, str | None]:
    """Data injection flow: read file -> validate rows -> store accepted rows -> score with the model."""
    settings = get_settings()
    if not content:
        raise FileValidationError("Uploaded file is empty")
    if len(content) > settings.max_upload_size_bytes:
        raise FileValidationError(f"File exceeds the {settings.max_upload_size_mb} MB limit")

    resolved_date = run_date or run_date_from_filename(file_name)
    if resolved_date is None:
        if book == Book.HISTORICAL:
            resolved_date = date.today()
        else:
            raise FileValidationError("Run date not found. Add it to the file name (DDMMYYYY) or pass run_date")

    frame = read_table(content, file_name)
    outcome = validate_frame(frame, book)
    stored = _store_raw(content, book, file_name)

    batch = UploadBatch(
        book=book,
        file_name=file_name,
        stored_path=str(stored),
        run_date=resolved_date,
        uploaded_by=user.id,
        rows_total=outcome.rows_total,
        rows_accepted=len(outcome.records),
        rows_rejected=outcome.rows_rejected,
    )
    db.add(batch)
    db.flush()

    try:
        if outcome.records:
            if book == Book.HISTORICAL:
                _save_historical(db, outcome.records, batch.id)
            else:
                _save_live(db, book, outcome.records, resolved_date, batch.id)
        if outcome.errors:
            db.execute(insert(RowValidationError), [{**e, "batch_id": batch.id} for e in outcome.errors])
        if not outcome.records:
            batch.status = BatchStatus.FAILED
        elif outcome.errors:
            batch.status = BatchStatus.COMPLETED_WITH_ERRORS
        else:
            batch.status = BatchStatus.COMPLETED
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Ingestion failed for %s", file_name)
        raise

    db.refresh(batch)
    logger.info("Ingested %s (%s): %d accepted, %d rejected", file_name, book, batch.rows_accepted, batch.rows_rejected)
    audit.record(db, user, "ingest", book=book.value, file=file_name, run_date=resolved_date.isoformat(),
                 accepted=batch.rows_accepted, rejected=batch.rows_rejected)
    predictions = refresh_predictions(db, book, resolved_date) if batch.rows_accepted else None
    return batch, predictions


def available_run_dates(db: Session) -> list[dict]:
    assets = set(db.scalars(select(AssetBook.run_date).distinct()))
    liabilities = set(db.scalars(select(LiabilityBook.run_date).distinct()))
    predicted = set(db.scalars(select(Prediction.run_date).distinct()))
    return [
        {"run_date": d, "has_assets": d in assets, "has_liabilities": d in liabilities, "has_predictions": d in predicted}
        for d in sorted(assets | liabilities, reverse=True)
    ]


def latest_run_date(db: Session) -> date | None:
    dates = [db.scalar(select(func.max(m.run_date))) for m in (AssetBook, LiabilityBook)]
    return max((d for d in dates if d), default=None)
