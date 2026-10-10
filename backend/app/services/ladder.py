import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Date, Integer, Numeric, String, and_, case, cast, func, literal, null, or_, select, type_coerce, union_all
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import Book, Bucket, LadderView, ShiftDirection, ShiftUnit
from app.errors import NotFoundError
from app.models import AssetBook, LiabilityBook, Prediction
from app.schemas import BucketValue, LadderResponse, LadderSeries, TenorShift, TransactionRow
from app.services.cashflow import bucket_bounds

logger = logging.getLogger(__name__)

BOOKS = (
    (Book.ASSET, AssetBook, AssetBook.loan_amount, AssetBook.loan_type),
    (Book.LIABILITY, LiabilityBook, LiabilityBook.amount, LiabilityBook.product_type),
)
BUCKET_ORDER = [b for b in Bucket]
SORTABLE = {"maturity_cashflow", "principal", "contractual_maturity", "effective_maturity", "p_early", "transaction_id"}


@dataclass(frozen=True)
class Scope:
    locations: tuple[str, ...]
    currency: str | None = None
    location: str | None = None


def _shifted(col, shift: TenorShift, run_date: date):
    sign = -1 if shift.direction == ShiftDirection.EARLIER else 1
    months = sign * shift.value if shift.unit == ShiftUnit.MONTHS else 0
    weeks = sign * shift.value if shift.unit == ShiftUnit.WEEKS else 0
    days = sign * shift.value if shift.unit == ShiftUnit.DAYS else 0
    moved = cast(col + func.make_interval(0, months, weeks, days), Date)
    return func.greatest(moved, run_date)


def flows_subquery(
    run_date: date,
    view: LadderView,
    asset_shift: TenorShift | None = None,
    liability_shift: TenorShift | None = None,
):
    basis = get_settings().day_count_basis
    parts = []
    for book, model, principal, product in BOOKS:
        p_early = cast(null(), Numeric(6, 5))
        risk = cast(null(), String(8))
        maturity = model.maturity_date
        if view == LadderView.AI:
            maturity = Prediction.adjusted_maturity
            p_early, risk = Prediction.p_early, Prediction.risk_level
        elif view == LadderView.SCENARIO:
            shift = asset_shift if book == Book.ASSET else liability_shift
            if shift and shift.value:
                maturity = _shifted(model.maturity_date, shift, run_date)

        if view == LadderView.DETERMINISTIC:
            interest, cashflow = model.interest_amount, model.maturity_cashflow
        else:
            days = func.greatest(type_coerce(maturity - model.transaction_date, Integer), 0)
            interest = func.round(principal * model.interest_rate_pct / 100 * days / basis, 2)
            cashflow = principal + interest

        stmt = select(
            literal(book.value).label("book"),
            model.transaction_id,
            model.entity,
            model.location,
            model.customer_id,
            model.customer_segment,
            model.client_rating,
            model.currency,
            principal.label("principal"),
            interest.label("interest_amount"),
            cashflow.label("maturity_cashflow"),
            model.interest_rate_pct,
            model.market_interest_rate_pct,
            product.label("product_type"),
            model.transaction_date,
            model.maturity_date.label("contractual_maturity"),
            cast(maturity, Date).label("effective_maturity"),
            p_early.label("p_early"),
            risk.label("risk_level"),
        ).where(model.run_date == run_date, model.maturity_date >= run_date)

        if view == LadderView.AI:
            stmt = stmt.join(
                Prediction,
                and_(
                    Prediction.run_date == model.run_date,
                    Prediction.book == book,
                    Prediction.transaction_id == model.transaction_id,
                ),
            )
        parts.append(stmt)

    flows = union_all(*parts).subquery("flows")
    whens = [(flows.c.effective_maturity <= upper, bucket.value) for bucket, upper in bucket_bounds(run_date) if upper]
    bucket = case(*whens, else_=Bucket.Y5_PLUS.value)
    return select(flows, bucket.label("bucket")).subquery("bucketed")


def _apply_scope(stmt, sub, scope: Scope):
    stmt = stmt.where(sub.c.location.in_(scope.locations))
    if scope.currency:
        stmt = stmt.where(sub.c.currency == scope.currency)
    return stmt


def compute_cells(db: Session, sub, scope: Scope | None = None) -> list[dict]:
    is_asset = sub.c.book == Book.ASSET.value
    stmt = select(
        sub.c.currency,
        sub.c.location,
        sub.c.bucket,
        func.coalesce(func.sum(case((is_asset, sub.c.maturity_cashflow), else_=0)), 0).label("assets"),
        func.coalesce(func.sum(case((~is_asset, sub.c.maturity_cashflow), else_=0)), 0).label("liabilities"),
        func.count(case((is_asset, 1))).label("asset_count"),
        func.count(case((~is_asset, 1))).label("liability_count"),
    ).group_by(sub.c.currency, sub.c.location, sub.c.bucket)
    if scope:
        stmt = _apply_scope(stmt, sub, scope)

    found = {(r.currency, r.location, r.bucket): r for r in db.execute(stmt)}
    pairs = sorted({(c, l) for c, l, _ in found})
    cells = []
    for currency, location in pairs:
        for bucket in BUCKET_ORDER:
            r = found.get((currency, location, bucket.value))
            assets = float(r.assets) if r else 0.0
            liabilities = float(r.liabilities) if r else 0.0
            cells.append({
                "currency": currency,
                "location": location,
                "bucket": bucket,
                "assets": round(assets, 2),
                "liabilities": round(liabilities, 2),
                "net_gap": round(assets - liabilities, 2),
                "asset_count": r.asset_count if r else 0,
                "liability_count": r.liability_count if r else 0,
            })
    return cells


def ladder_cells(db: Session, run_date: date, view: LadderView, scope: Scope | None = None) -> list[dict]:
    """Assets, liabilities and net gap per currency x location x bucket (one SQL aggregation)."""
    cells = compute_cells(db, flows_subquery(run_date, view), scope)
    if not cells and scope is None:
        raise NotFoundError(f"No live asset or liability data for run date {run_date}")
    return cells


def filter_cells(cells: list[dict], scope: Scope) -> list[dict]:
    allowed = set(scope.locations)
    return [c for c in cells if c["location"] in allowed and (not scope.currency or c["currency"] == scope.currency)]


def build_response(run_date: date, view: LadderView, cells: list[dict]) -> LadderResponse:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    totals: dict[str, dict[Bucket, dict]] = defaultdict(dict)
    for c in cells:
        grouped[(c["currency"], c["location"])].append(c)
        t = totals[c["currency"]].setdefault(
            c["bucket"], {"bucket": c["bucket"], "assets": 0.0, "liabilities": 0.0, "net_gap": 0.0, "asset_count": 0, "liability_count": 0}
        )
        for k in ("assets", "liabilities", "net_gap", "asset_count", "liability_count"):
            t[k] += c[k]

    order = {b: i for i, b in enumerate(BUCKET_ORDER)}
    series = [
        LadderSeries(
            currency=currency,
            location=location,
            buckets=[BucketValue(**{k: v for k, v in c.items() if k not in ("currency", "location")})
                     for c in sorted(items, key=lambda c: order[c["bucket"]])],
        )
        for (currency, location), items in sorted(grouped.items())
    ]
    totals_out = {
        currency: [BucketValue(**{**v, "assets": round(v["assets"], 2), "liabilities": round(v["liabilities"], 2),
                                  "net_gap": round(v["net_gap"], 2)}) for b, v in sorted(by_bucket.items(), key=lambda x: order[x[0]])]
        for currency, by_bucket in sorted(totals.items())
    }
    return LadderResponse(run_date=run_date, view=view, series=series, totals_by_currency=totals_out)


def drilldown(
    db: Session,
    run_date: date,
    view: LadderView,
    bucket: Bucket,
    scope: Scope,
    book: Book | None = None,
    search: str | None = None,
    sort_by: str = "maturity_cashflow",
    sort_desc: bool = True,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[TransactionRow], int]:
    sub = flows_subquery(run_date, view)
    base = _apply_scope(select(sub).where(sub.c.bucket == bucket.value), sub, scope)
    if book:
        base = base.where(sub.c.book == book.value)
    if search:
        like = f"%{search.strip()}%"
        base = base.where(or_(sub.c.transaction_id.ilike(like), sub.c.customer_id.ilike(like)))

    total = db.scalar(select(func.count()).select_from(base.subquery()))
    sort_col = sub.c[sort_by if sort_by in SORTABLE else "maturity_cashflow"]
    order = sort_col.desc().nulls_last() if sort_desc else sort_col.asc().nulls_last()
    rows = db.execute(base.order_by(order, sub.c.transaction_id).offset((page - 1) * page_size).limit(page_size)).mappings()

    items = []
    for r in rows:
        is_ai = view == LadderView.AI
        items.append(TransactionRow(
            transaction_id=r["transaction_id"],
            book=Book(r["book"]),
            entity=r["entity"],
            location=r["location"],
            customer_id=r["customer_id"],
            customer_segment=r["customer_segment"],
            client_rating=r["client_rating"],
            currency=r["currency"],
            principal=float(r["principal"]),
            interest_amount=float(r["interest_amount"]),
            maturity_cashflow=float(r["maturity_cashflow"]),
            interest_rate_pct=float(r["interest_rate_pct"]),
            market_interest_rate_pct=float(r["market_interest_rate_pct"]),
            product_type=r["product_type"],
            transaction_date=r["transaction_date"],
            contractual_maturity=r["contractual_maturity"],
            adjusted_maturity=r["effective_maturity"] if is_ai else None,
            p_early=float(r["p_early"]) if is_ai and r["p_early"] is not None else None,
            risk_level=r["risk_level"] if is_ai else None,
            days_pulled_forward=(r["contractual_maturity"] - r["effective_maturity"]).days if is_ai else None,
            bucket=Bucket(r["bucket"]),
        ))
    return items, total or 0
