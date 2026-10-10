"""What-if scenarios, recommendations, behavioral analytics and exports."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import Book, Bucket, LadderView
from app.db import get_db
from app.deps import build_scope, get_current_user, get_scope, resolve_run_date
from app.ml.behavior import ensure_predictions
from app.schemas import AnomalyResponse, CurrentUser, ExitTrendResponse, RecommendationOut, ScenarioRequest, ScenarioResponse
from app.services import analytics, audit, export
from app.services.ladder import Scope, build_response, drilldown, ladder_cells
from app.services.recommendation import list_recommendations
from app.services.scenario import run_scenario

router = APIRouter()


@router.post("/scenario/run", response_model=ScenarioResponse, tags=["what-if"])
def scenario(body: ScenarioRequest, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = build_scope(db, user, body.location, body.currency)
    result = run_scenario(db, body, scope)
    audit.record(db, user, "scenario_run", run_date=body.run_date.isoformat(), description=result.description)
    return result


@router.get("/recommendations", response_model=list[RecommendationOut], tags=["recommendations"])
def recommendations(
    bucket: Bucket | None = Query(None),
    run_date: date = Depends(resolve_run_date),
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
):
    return list_recommendations(db, run_date, scope, bucket)


@router.get("/analytics/exit-trends", response_model=ExitTrendResponse, tags=["analytics"])
def exit_trends(
    group_by: Literal["product_type", "customer_segment", "type"] = "customer_segment",
    months: int | None = Query(None, ge=1, le=240, description="Only the last N months up to the run date"),
    run_date: date = Depends(resolve_run_date),
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
):
    return analytics.exit_trends(db, scope, group_by, run_date, months)


@router.get("/analytics/anomalies", response_model=AnomalyResponse, tags=["analytics"])
def anomalies(
    days: int = Query(365, ge=7, le=3650),
    run_date: date = Depends(resolve_run_date),
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
):
    return analytics.outflow_anomalies(db, scope, run_date, days)


def _file(content: bytes, name: str, fmt: str) -> Response:
    media = export.PDF_MEDIA if fmt == "pdf" else export.XLSX_MEDIA
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}.{fmt}"'})


def _ladder_view(view: str) -> LadderView:
    return LadderView.AI if view == "ai" else LadderView.DETERMINISTIC


@router.get("/export/ladder", tags=["export"])
def export_ladder(
    view: Literal["deterministic", "ai"] = "deterministic",
    format: Literal["xlsx", "pdf"] = "xlsx",
    run_date: date = Depends(resolve_run_date),
    scope: Scope = Depends(get_scope),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    v = _ladder_view(view)
    if v == LadderView.AI:
        ensure_predictions(db, run_date)
    frame = export.ladder_frame(build_response(run_date, v, ladder_cells(db, run_date, v, scope)))
    title = f"{'AI-adjusted' if v == LadderView.AI else 'Deterministic'} gap ladder"
    content = export.to_pdf(title, run_date, {title: frame}) if format == "pdf" else export.to_xlsx({"Gap ladder": frame})
    audit.record(db, user, "export", report="ladder", view=view, format=format, run_date=run_date.isoformat())
    return _file(content, f"gap_ladder_{view}_{run_date}", format)


@router.get("/export/transactions", tags=["export"])
def export_transactions(
    bucket: Bucket,
    view: Literal["deterministic", "ai"] = "deterministic",
    book: Book | None = Query(None),
    run_date: date = Depends(resolve_run_date),
    scope: Scope = Depends(get_scope),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    v = _ladder_view(view)
    if v == LadderView.AI:
        ensure_predictions(db, run_date)
    rows, _ = drilldown(db, run_date, v, bucket, scope, book=book, page=1, page_size=get_settings().export_max_rows)
    audit.record(db, user, "export", report="transactions", view=view, bucket=bucket.value, rows=len(rows))
    return _file(export.to_xlsx({f"{bucket.value} transactions": export.transactions_frame(rows)}),
                 f"transactions_{view}_{bucket.value.replace('>', 'over')}_{run_date}", "xlsx")


@router.get("/export/recommendations", tags=["export"])
def export_recommendations(
    format: Literal["xlsx", "pdf"] = "xlsx",
    run_date: date = Depends(resolve_run_date),
    scope: Scope = Depends(get_scope),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    frame = export.recommendations_frame(list_recommendations(db, run_date, scope))
    content = export.to_pdf("Liquidity recommendations", run_date, {"Recommended actions": frame}) if format == "pdf" \
        else export.to_xlsx({"Recommendations": frame})
    audit.record(db, user, "export", report="recommendations", format=format, run_date=run_date.isoformat())
    return _file(content, f"recommendations_{run_date}", format)
