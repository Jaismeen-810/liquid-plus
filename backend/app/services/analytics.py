from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import HistoricalLog
from app.schemas import AnomalyPoint, AnomalyResponse, ExitTrendPoint, ExitTrendResponse
from app.services.ladder import Scope

GROUPS = {"product_type": HistoricalLog.product_type, "customer_segment": HistoricalLog.customer_segment, "type": HistoricalLog.type}


def _history(db: Session, scope: Scope, as_of: date, extra=()) -> pd.DataFrame:
    """Closed historical contracts in scope, as known on the run date (closures after it are excluded)."""
    stmt = select(
        HistoricalLog.type, HistoricalLog.amount, HistoricalLog.currency, HistoricalLog.location,
        HistoricalLog.contractual_maturity_date, HistoricalLog.actual_closure_date, *extra,
    ).where(
        HistoricalLog.location.in_(scope.locations),
        HistoricalLog.actual_closure_date.is_not(None),
        HistoricalLog.actual_closure_date <= as_of,
    )
    if scope.currency:
        stmt = stmt.where(HistoricalLog.currency == scope.currency)
    return pd.DataFrame(db.execute(stmt).mappings().all())


def exit_trends(db: Session, scope: Scope, group_by: str, as_of: date, months: int | None = None) -> ExitTrendResponse:
    """Monthly early-exit rate for closures up to the run date; `months` limits it to the last N months."""
    col = GROUPS[group_by]
    df = _history(db, scope, as_of, (col.label("grp"),) if group_by != "type" else ())
    if months and not df.empty:
        start = (as_of - relativedelta(months=months - 1)).replace(day=1)
        df = df[pd.to_datetime(df["actual_closure_date"]) >= pd.Timestamp(start)]
    if df.empty:
        return ExitTrendResponse(group_by=group_by, points=[])
    if group_by == "type":
        df["grp"] = df["type"]
    closure = pd.to_datetime(df["actual_closure_date"])
    df["early"] = closure < pd.to_datetime(df["contractual_maturity_date"])
    df["period"] = closure.dt.to_period("M").astype(str)
    agg = df.groupby(["period", "grp"]).agg(total=("early", "size"), early_exits=("early", "sum")).reset_index()
    points = [
        ExitTrendPoint(period=r.period, group=r.grp, total=int(r.total), early_exits=int(r.early_exits),
                       early_exit_rate=round(r.early_exits / r.total, 4))
        for r in agg.itertuples()
    ]
    return ExitTrendResponse(group_by=group_by, points=points)


def outflow_anomalies(db: Session, scope: Scope, as_of: date, days: int = 365) -> AnomalyResponse:
    settings = get_settings()
    window, multiplier = settings.anomaly_window_days, settings.anomaly_multiplier
    df = _history(db, scope, as_of)
    empty = AnomalyResponse(window_days=window, multiplier=multiplier, currency=scope.currency,
                            location=scope.location, points=[], anomaly_count=0)
    if df.empty:
        return empty
    df = df[df["type"].str.lower() == "liability"]
    if df.empty:
        return empty

    df["closure"] = pd.to_datetime(df["actual_closure_date"])
    daily = df.groupby("closure")["amount"].sum().astype(float)
    # timeline ends on the run date, so quiet days right before it still count towards the average
    daily = daily.reindex(pd.date_range(daily.index.min(), pd.Timestamp(as_of), freq="D"), fill_value=0.0)
    rolling = daily.shift(1).rolling(window, min_periods=min(30, window)).mean()
    ratio = daily / rolling

    start = daily.index.max() - timedelta(days=days - 1)
    points, count = [], 0
    for ts in daily.index[daily.index >= start]:
        r = ratio.get(ts)
        avg = rolling.get(ts)
        is_anomaly = bool(pd.notna(r) and r >= multiplier and daily[ts] > 0)
        count += is_anomaly
        points.append(AnomalyPoint(
            date=ts.date(),
            outflow=round(float(daily[ts]), 2),
            rolling_avg=None if pd.isna(avg) else round(float(avg), 2),
            ratio=None if pd.isna(r) or r == float("inf") else round(float(r), 2),
            is_anomaly=is_anomaly,
            message=f"Deposit outflow {r:.1f}x higher than {window}-day average" if is_anomaly else None,
        ))
    return AnomalyResponse(window_days=window, multiplier=multiplier, currency=scope.currency,
                           location=scope.location, points=points, anomaly_count=count)
