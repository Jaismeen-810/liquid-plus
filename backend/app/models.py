from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import BatchStatus, Book, Role
from app.db import Base

JsonType = JSON().with_variant(JSONB, "postgresql")
Money = Numeric(20, 2)
Rate = Numeric(9, 4)


def enum(cls: type[StrEnum]) -> Enum:
    return Enum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role = 'SUPPORT' OR location IS NOT NULL", name="branch_user_has_location"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum(Role))
    location: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = created_at()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[dict | None] = mapped_column(JsonType)
    created_at: Mapped[datetime] = created_at()


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    book: Mapped[Book] = mapped_column(enum(Book))
    file_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
    run_date: Mapped[date] = mapped_column(Date, index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[BatchStatus] = mapped_column(enum(BatchStatus), default=BatchStatus.PROCESSING)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = created_at()


class RowValidationError(Base):
    __tablename__ = "validation_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    transaction_id: Mapped[str | None] = mapped_column(String(32))
    column_name: Mapped[str] = mapped_column(String(64))
    rule: Mapped[str] = mapped_column(String(64))
    value: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)


class _LiveBook:
    """Columns shared by the asset and liability books. One copy of the book is kept per run date."""

    id: Mapped[int] = mapped_column(primary_key=True)
    run_date: Mapped[date] = mapped_column(Date)
    transaction_id: Mapped[str] = mapped_column(String(32))
    entity: Mapped[str] = mapped_column(String(32))
    location: Mapped[str] = mapped_column(String(32))
    customer_id: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    transaction_date: Mapped[date] = mapped_column(Date)
    maturity_date: Mapped[date] = mapped_column(Date)
    interest_rate_pct: Mapped[Decimal] = mapped_column(Rate)
    market_interest_rate_pct: Mapped[Decimal] = mapped_column(Rate)
    customer_segment: Mapped[str] = mapped_column(String(16))
    client_rating: Mapped[int] = mapped_column(SmallInteger)
    interest_amount: Mapped[Decimal] = mapped_column(Money)
    maturity_cashflow: Mapped[Decimal] = mapped_column(Money)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = created_at()


class AssetBook(_LiveBook, Base):
    __tablename__ = "asset_book"
    __table_args__ = (
        UniqueConstraint("run_date", "transaction_id", name="uq_asset_book_run_txn"),
        Index("ix_asset_book_scope", "run_date", "location", "currency"),
    )

    loan_amount: Mapped[Decimal] = mapped_column(Money)
    loan_type: Mapped[str] = mapped_column(String(16))


class LiabilityBook(_LiveBook, Base):
    __tablename__ = "liability_book"
    __table_args__ = (
        UniqueConstraint("run_date", "transaction_id", name="uq_liability_book_run_txn"),
        Index("ix_liability_book_scope", "run_date", "location", "currency"),
    )

    amount: Mapped[Decimal] = mapped_column(Money)
    product_type: Mapped[str] = mapped_column(String(16))


class HistoricalLog(Base):
    __tablename__ = "historical_log"
    __table_args__ = (Index("ix_historical_scope", "location", "type", "product_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[str] = mapped_column(String(32), unique=True)
    entity: Mapped[str] = mapped_column(String(32))
    type: Mapped[str] = mapped_column(String(16))
    location: Mapped[str] = mapped_column(String(32))
    transaction_date: Mapped[date] = mapped_column(Date)
    customer_id: Mapped[str] = mapped_column(String(32))
    customer_segment: Mapped[str] = mapped_column(String(16))
    client_rating: Mapped[int] = mapped_column(SmallInteger)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    interest_rate_pct: Mapped[Decimal] = mapped_column(Rate)
    market_interest_rate_pct: Mapped[Decimal] = mapped_column(Rate)
    product_type: Mapped[str] = mapped_column(String(16))
    contractual_maturity_date: Mapped[date] = mapped_column(Date)
    actual_closure_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = created_at()


class Prediction(Base):
    """Behavioral model output for one live transaction on one run date."""

    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("run_date", "book", "transaction_id", name="uq_prediction_run_txn"),
        Index("ix_prediction_scope", "run_date", "location", "currency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_date: Mapped[date] = mapped_column(Date)
    book: Mapped[Book] = mapped_column(enum(Book))
    transaction_id: Mapped[str] = mapped_column(String(32))
    location: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    p_early: Mapped[Decimal] = mapped_column(Numeric(6, 5))
    predicted_early: Mapped[bool] = mapped_column(Boolean)
    risk_level: Mapped[str] = mapped_column(String(8))
    expected_shift_days: Mapped[int] = mapped_column(Integer)
    contractual_maturity: Mapped[date] = mapped_column(Date)
    adjusted_maturity: Mapped[date] = mapped_column(Date)
    drivers: Mapped[list | None] = mapped_column(JsonType)
    created_at: Mapped[datetime] = created_at()
