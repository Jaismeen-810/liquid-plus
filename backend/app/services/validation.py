import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import pandas as pd

from app import constants as C
from app.constants import Book
from app.errors import FileValidationError

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[ T]00:00:00(?:\.0+)?)?$")

Check = Callable[[str], tuple[Any, str | None]]


def _pattern(regex: re.Pattern, label: str) -> Check:
    return lambda v: (v, None) if regex.match(v) else (None, f"must match pattern {label}")


def _choice(options: frozenset[str], label: str | None = None, case_insensitive: bool = False) -> Check:
    lookup = {o.lower(): o for o in options} if case_insensitive else {o: o for o in options}

    def check(v: str):
        key = v.lower() if case_insensitive else v
        if key in lookup:
            return lookup[key], None
        return None, f"must be one of {label or ', '.join(sorted(options))}"

    return check


def _decimal(v: str) -> Decimal | None:
    try:
        d = Decimal(v)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _positive_amount(v: str):
    d = _decimal(v)
    if d is None:
        return None, "must be numeric"
    return (d, None) if d > 0 else (None, "must be greater than 0")


def _rate(v: str):
    d = _decimal(v)
    if d is None:
        return None, "must be numeric"
    low, high = C.RATE_RANGE
    return (d, None) if low <= d <= high else (None, f"must be between {low:g} and {high:g}")


def _rating(v: str):
    d = _decimal(v)
    if d is None or d != d.to_integral_value():
        return None, "must be an integer"
    low, high = C.CLIENT_RATING_RANGE
    return (int(d), None) if low <= d <= high else (None, f"must be between {low} and {high}")


def parse_date(v: str) -> date | None:
    m = DATE_RE.match(v)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), C.DATE_FORMAT).date()
    except ValueError:
        return None


def _date(v: str):
    d = parse_date(v)
    return (d, None) if d else (None, "must be a valid date in YYYY-MM-DD format")


@dataclass(frozen=True)
class Column:
    header: str
    key: str
    check: Check
    optional: bool = False


ENTITY = Column("Entity", "entity", _choice(C.ENTITIES))
LOCATION = Column("Location", "location", _choice(C.LOCATIONS))
CUSTOMER = Column("Customer_ID", "customer_id", _pattern(C.CUSTOMER_ID_PATTERN, "CUS-<number>"))
CURRENCY = Column("Currency", "currency", _choice(C.CURRENCIES))
TXN_DATE = Column("Transaction_Date", "transaction_date", _date)
RATE = Column("Interest_Rate_Pct", "interest_rate_pct", _rate)
MARKET = Column("Market_Interest_Rate_Pct", "market_interest_rate_pct", _rate)
SEGMENT = Column("Customer_Segment", "customer_segment", _choice(C.CUSTOMER_SEGMENTS))
RATING = Column("Client_Rating", "client_rating", _rating)

SCHEMAS: dict[Book, list[Column]] = {
    Book.ASSET: [
        Column("Transaction_ID", "transaction_id", _pattern(C.ASSET_ID_PATTERN, "AST-<number>")),
        ENTITY, LOCATION, CUSTOMER,
        Column("Loan_Amount", "loan_amount", _positive_amount),
        CURRENCY, TXN_DATE,
        Column("Maturity_Date", "maturity_date", _date),
        RATE, MARKET,
        Column("Loan_Type", "loan_type", _choice(C.LOAN_TYPES)),
        SEGMENT, RATING,
    ],
    Book.LIABILITY: [
        Column("Transaction_ID", "transaction_id", _pattern(C.LIABILITY_ID_PATTERN, "LIA-<number>")),
        ENTITY, LOCATION, CUSTOMER,
        Column("Amount", "amount", _positive_amount),
        CURRENCY, TXN_DATE,
        Column("Maturity_Date", "maturity_date", _date),
        RATE, MARKET,
        Column("Product_Type", "product_type", _choice(C.PRODUCT_TYPES)),
        SEGMENT, RATING,
    ],
    Book.HISTORICAL: [
        Column("Transaction_ID", "transaction_id", _pattern(C.HISTORICAL_ID_PATTERN, "AST-<number> or LIA-<number>")),
        ENTITY,
        Column("Type", "type", _choice(frozenset({"Asset", "Liability"}), "Asset, Liability", case_insensitive=True)),
        LOCATION, TXN_DATE, CUSTOMER, SEGMENT, RATING,
        Column("Amount", "amount", _positive_amount),
        CURRENCY, RATE, MARKET,
        Column("Product_Type", "product_type", _choice(C.HISTORICAL_PRODUCT_TYPES, "Loan-Type-A..E or Product-A..E")),
        Column("Contractual_Maturity_Date", "contractual_maturity_date", _date),
        Column("Actual_Closure_Date", "actual_closure_date", _date, optional=True),
    ],
}

MATURITY_KEY = {Book.ASSET: "maturity_date", Book.LIABILITY: "maturity_date", Book.HISTORICAL: None}


@dataclass
class ValidationOutcome:
    records: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    rows_total: int = 0

    @property
    def rows_rejected(self) -> int:
        return self.rows_total - len(self.records)


def _error(row_number: int, txn: str | None, column: str, rule: str, value: Any, message: str) -> dict:
    return {
        "row_number": row_number,
        "transaction_id": txn or None,
        "column_name": column,
        "rule": rule,
        "value": None if value is None else str(value)[:200],
        "message": message,
    }


def validate_frame(df: pd.DataFrame, book: Book) -> ValidationOutcome:
    columns = SCHEMAS[book]
    df = df.rename(columns=lambda c: str(c).strip())
    missing = [c.header for c in columns if c.header not in df.columns]
    if missing:
        raise FileValidationError(f"File is missing required columns for {book} book", {"missing_columns": missing})

    headers = [c.header for c in columns]
    frame = df[headers].fillna("").astype(str).apply(lambda s: s.str.strip())
    frame = frame[(frame != "").any(axis=1)]
    frame.index = frame.index + 2

    outcome = ValidationOutcome(rows_total=len(frame))
    full_dup = frame.duplicated(keep="first")
    id_dup = frame["Transaction_ID"].where(~full_dup).duplicated(keep="first") & ~full_dup & frame["Transaction_ID"].ne("")

    for row_number, row in zip(frame.index, frame.itertuples(index=False, name=None)):
        values = dict(zip(headers, row))
        txn = values["Transaction_ID"]
        if full_dup.loc[row_number]:
            outcome.errors.append(_error(row_number, txn, "*", "duplicate_row", None, "Row is a full duplicate of an earlier row"))
            continue

        row_errors, record = [], {}
        for col in columns:
            raw = values[col.header]
            if raw == "":
                if col.optional:
                    record[col.key] = None
                else:
                    row_errors.append(_error(row_number, txn, col.header, "required", raw, f"{col.header} is mandatory"))
                continue
            parsed, message = col.check(raw)
            if message:
                row_errors.append(_error(row_number, txn, col.header, "invalid_value", raw, f"{col.header} {message}"))
            else:
                record[col.key] = parsed

        if id_dup.loc[row_number]:
            row_errors.append(_error(row_number, txn, "Transaction_ID", "duplicate_id", txn, "Transaction_ID already used in this file"))

        entity, location = record.get("entity"), record.get("location")
        if entity and location and C.ENTITY_LOCATION[entity] != location:
            row_errors.append(
                _error(row_number, txn, "Location", "entity_location", location,
                       f"{entity} must be booked in {C.ENTITY_LOCATION[entity]}, not {location}")
            )

        maturity_key = MATURITY_KEY[book]
        if maturity_key and record.get(maturity_key) and record.get("transaction_date"):
            if record[maturity_key] < record["transaction_date"]:
                row_errors.append(
                    _error(row_number, txn, "Maturity_Date", "maturity_before_start", values["Maturity_Date"],
                           "Maturity_Date must be on or after Transaction_Date")
                )

        if row_errors:
            outcome.errors.extend(row_errors)
        else:
            outcome.records.append(record)
    return outcome
