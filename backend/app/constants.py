import re
from enum import StrEnum


class Role(StrEnum):
    BRANCH = "BRANCH"    # location-based user: sees only their own location
    SUPPORT = "SUPPORT"  # support user: sees every location, uploads data, retrains the model


class Book(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    HISTORICAL = "historical"


class BatchStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class Bucket(StrEnum):
    M0_1 = "0-1M"
    M1_3 = "1-3M"
    M3_12 = "3-12M"
    Y1_5 = "1-5Y"
    Y5_PLUS = ">5Y"


class LadderView(StrEnum):
    DETERMINISTIC = "deterministic"
    AI = "ai"
    SCENARIO = "scenario"


class GapType(StrEnum):
    SHORTFALL = "shortfall"    # Rule A
    SURPLUS = "surplus"        # Rule B
    RISK_ALERT = "risk_alert"  # Rule C
    PRESERVE = "preserve"      # Rule D


class RecommendationRule(StrEnum):
    RAISE_FUNDING = "RULE_A"     # AI-adjusted shortfall
    DEPLOY_SURPLUS = "RULE_B"    # AI-adjusted surplus, after a liquidity buffer
    BEHAVIOURAL_RISK = "RULE_C"  # behaviour makes the gap materially worse than the contract says
    PRESERVE = "RULE_D"          # surplus now, shortfall in a later bucket: keep the cash


class ShiftUnit(StrEnum):
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


class ShiftDirection(StrEnum):
    EARLIER = "earlier"
    LATER = "later"


# Upper edge of each bucket in months from the run date; None = open-ended.
BUCKET_UPPER_MONTHS: list[tuple[Bucket, int | None]] = [
    (Bucket.M0_1, 1),
    (Bucket.M1_3, 3),
    (Bucket.M3_12, 12),
    (Bucket.Y1_5, 60),
    (Bucket.Y5_PLUS, None),
]

ENTITY_LOCATION = {
    "IBC HongKong": "Hong Kong",
    "IBC USA": "New York",
    "IBC UK": "London",
    "IBC Singapore": "Singapore",
    "IBC SA": "Paris",
}
ENTITIES = frozenset(ENTITY_LOCATION)
LOCATIONS = frozenset(ENTITY_LOCATION.values())
CURRENCIES = frozenset({"USD", "EUR", "GBP", "SGD", "HKD"})
CUSTOMER_SEGMENTS = frozenset({"Retail", "Corporate", "SME", "Institutional"})
LOAN_TYPES = frozenset(f"Loan-Type-{c}" for c in "ABCDE")
PRODUCT_TYPES = frozenset(f"Product-{c}" for c in "ABCDE")
HISTORICAL_PRODUCT_TYPES = LOAN_TYPES | PRODUCT_TYPES

ASSET_ID_PATTERN = re.compile(r"^AST-\d+$")
LIABILITY_ID_PATTERN = re.compile(r"^LIA-\d+$")
HISTORICAL_ID_PATTERN = re.compile(r"^(AST|LIA)-\d+$")
CUSTOMER_ID_PATTERN = re.compile(r"^CUS-\d+$")

RATE_RANGE = (0, 100)
CLIENT_RATING_RANGE = (1, 5)
DATE_FORMAT = "%Y-%m-%d"

# Run date embedded in an upload's file name, e.g. "asset_book - 10102026.xlsx" (DDMMYYYY or YYYYMMDD).
RUN_DATE_IN_FILENAME = re.compile(r"(?<!\d)(\d{8})(?!\d)")
