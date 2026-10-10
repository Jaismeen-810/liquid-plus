from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import Book, Bucket, LadderView
from app.db import get_db
from app.deps import get_scope, resolve_run_date
from app.errors import NotFoundError
from app.ml.behavior import ensure_predictions
from app.schemas import CompareBucket, CompareCurrency, CompareResponse, LadderResponse, Page, TransactionRow
from app.services.ladder import Scope, build_response, drilldown, ladder_cells
from app.services.recommendation import both_ladders, build_recommendations

router = APIRouter(prefix="/ladder", tags=["ladder"])
VIEWS = {"deterministic": LadderView.DETERMINISTIC, "ai": LadderView.AI}


def _view(view: str) -> LadderView:
    if view not in VIEWS:
        raise NotFoundError(f"Unknown ladder view '{view}'. Use deterministic or ai")
    return VIEWS[view]


@router.get("/compare", response_model=CompareResponse)
def compare(run_date: date = Depends(resolve_run_date), scope: Scope = Depends(get_scope), db: Session = Depends(get_db)):
    det_cells, ai_cells = both_ladders(db, run_date, scope)
    recs = defaultdict(int)
    for r in build_recommendations(det_cells, ai_cells):
        recs[(r.currency, r.bucket)] += 1

    totals: dict[str, dict[Bucket, list[float]]] = defaultdict(lambda: {b: [0.0, 0.0] for b in Bucket})
    for i, cells in enumerate((det_cells, ai_cells)):
        for c in cells:
            totals[c["currency"]][c["bucket"]][i] += c["net_gap"]

    return CompareResponse(run_date=run_date, currencies=[
        CompareCurrency(currency=cur, buckets=[
            CompareBucket(bucket=b, deterministic_gap=round(d, 2), ai_gap=round(a, 2), difference=round(a - d, 2),
                          recommendation_count=recs[(cur, b)])
            for b, (d, a) in by_bucket.items()
        ])
        for cur, by_bucket in sorted(totals.items())
    ])


@router.get("/{view}", response_model=LadderResponse)
def ladder(view: str, run_date: date = Depends(resolve_run_date), scope: Scope = Depends(get_scope), db: Session = Depends(get_db)):
    v = _view(view)
    if v == LadderView.AI:
        ensure_predictions(db, run_date)
    return build_response(run_date, v, ladder_cells(db, run_date, v, scope))


@router.get("/{view}/transactions", response_model=Page[TransactionRow])
def transactions(
    view: str,
    bucket: Bucket,
    book: Book | None = Query(None),
    search: str | None = Query(None, max_length=64),
    sort_by: str = Query("maturity_cashflow"),
    sort_desc: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1),
    run_date: date = Depends(resolve_run_date),
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
):
    v = _view(view)
    if v == LadderView.AI:
        ensure_predictions(db, run_date)
    page_size = min(page_size, get_settings().drilldown_max_page_size)
    items, total = drilldown(db, run_date, v, bucket, scope, book=book, search=search, sort_by=sort_by,
                             sort_desc=sort_desc, page=page, page_size=page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)
