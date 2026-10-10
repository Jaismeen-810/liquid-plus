from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

from app.constants import BUCKET_UPPER_MONTHS, Bucket

CENT = Decimal("0.01")


def simple_interest(principal: Decimal, rate_pct: Decimal, start: date, end: date, basis: int) -> Decimal:
    days = max((end - start).days, 0)
    return (principal * rate_pct / Decimal(100) * Decimal(days) / Decimal(basis)).quantize(CENT, ROUND_HALF_UP)


def bucket_bounds(run_date: date) -> list[tuple[Bucket, date | None]]:
    return [(bucket, run_date + relativedelta(months=months) if months else None) for bucket, months in BUCKET_UPPER_MONTHS]


def bucket_for(run_date: date, maturity: date) -> Bucket | None:
    if maturity < run_date:
        return None
    for bucket, upper in bucket_bounds(run_date):
        if upper is None or maturity <= upper:
            return bucket
    return None
