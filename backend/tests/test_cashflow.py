from datetime import date
from decimal import Decimal

from app.constants import Bucket
from app.services.cashflow import bucket_for, simple_interest

RUN = date(2026, 10, 10)


def test_simple_interest_actual_365():
    assert simple_interest(Decimal("1000000"), Decimal("5"), date(2026, 1, 1), date(2027, 1, 1), 365) == Decimal("50000.00")


def test_interest_zero_when_same_day():
    assert simple_interest(Decimal("1000"), Decimal("5"), RUN, RUN, 365) == Decimal("0.00")


def test_bucket_boundaries_fall_in_earlier_bucket():
    assert bucket_for(RUN, RUN) == Bucket.M0_1
    assert bucket_for(RUN, date(2026, 11, 10)) == Bucket.M0_1
    assert bucket_for(RUN, date(2026, 11, 11)) == Bucket.M1_3
    assert bucket_for(RUN, date(2027, 10, 10)) == Bucket.M3_12
    assert bucket_for(RUN, date(2031, 10, 10)) == Bucket.Y1_5
    assert bucket_for(RUN, date(2031, 10, 11)) == Bucket.Y5_PLUS


def test_matured_deals_have_no_bucket():
    assert bucket_for(RUN, date(2026, 10, 9)) is None
