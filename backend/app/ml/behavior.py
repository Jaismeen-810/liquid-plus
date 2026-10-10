"""Behavioral model: predicts early exit (deposits) / pre-closure (loans) and the adjusted maturity date.

Uses the two logistic-regression pipelines from the ML project (`ml_models/{asset,liability}_model.joblib`):

* p_early          = model probability for the live transaction
* expected shift   = median days-before-maturity that similar historical contracts closed early
                     (by type + product + segment, falling back to segment, type, then all history)
* adjusted maturity = contractual maturity - p_early x expected shift, never before the run date
"""
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import Book
from app.errors import ForbiddenError, ModelNotReadyError, NotFoundError
from app.ml.features import ALL_FEATURES, CATEGORICAL_FEATURES, FEATURE_TO_GROUP, create_features
from app.models import AssetBook, HistoricalLog, LiabilityBook, Prediction
from app.schemas import FeatureDriver, ModelInfo, PredictionRationale

logger = logging.getLogger(__name__)

LIVE_BOOKS = {
    Book.ASSET: (AssetBook, AssetBook.loan_amount, AssetBook.loan_type),
    Book.LIABILITY: (LiabilityBook, LiabilityBook.amount, LiabilityBook.product_type),
}
MIN_CALIBRATION_CASES = 10
CHUNK = 2000


# ---------------------------------------------------------------- model files

@dataclass
class LoadedModel:
    pipeline: object
    threshold: float
    meta: dict


def model_paths(book: Book):
    folder = get_settings().model_dir
    return folder / f"{book.value}_model.joblib", folder / f"{book.value}_threshold.json"


@lru_cache(maxsize=2)
def load_model(book: Book) -> LoadedModel:
    model_path, meta_path = model_paths(book)
    if not model_path.exists():
        raise ModelNotReadyError(f"Behavioral model file not found: {model_path.name}. Train it or copy it into {model_path.parent}")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return LoadedModel(joblib.load(model_path), float(meta.get("threshold", 0.5)), meta)


def reset_model_cache() -> None:
    load_model.cache_clear()


def model_info() -> list[ModelInfo]:
    out = []
    for book in (Book.ASSET, Book.LIABILITY):
        model_path, meta_path = model_paths(book)
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        out.append(ModelInfo(
            book=book, algorithm="logistic_regression", available=model_path.exists(), threshold=meta.get("threshold"),
            trained_at=meta.get("trained_at"), training_rows=meta.get("training_rows"), metrics=meta.get("metrics"),
        ))
    return out


def risk_level(p: float) -> str:
    return "HIGH" if p >= 0.75 else "MEDIUM" if p >= 0.5 else "LOW"


# ---------------------------------------------------------------- calibration from history

def historical_frame(db: Session) -> pd.DataFrame:
    rows = db.execute(select(
        HistoricalLog.transaction_id, HistoricalLog.entity, HistoricalLog.type, HistoricalLog.location,
        HistoricalLog.transaction_date, HistoricalLog.customer_id, HistoricalLog.customer_segment, HistoricalLog.client_rating,
        HistoricalLog.amount, HistoricalLog.currency, HistoricalLog.interest_rate_pct, HistoricalLog.market_interest_rate_pct,
        HistoricalLog.product_type, HistoricalLog.contractual_maturity_date, HistoricalLog.actual_closure_date,
    )).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["type"] = df["type"].str.lower()
        for col in ("amount", "interest_rate_pct", "market_interest_rate_pct"):
            df[col] = df[col].astype(float)
    return df


def shift_calibration(hist: pd.DataFrame) -> dict:
    """Median early-shift days observed in history, at several levels of detail."""
    if hist.empty:
        return {}
    closure = pd.to_datetime(hist["actual_closure_date"])
    maturity = pd.to_datetime(hist["contractual_maturity_date"])
    shift = (maturity - closure).dt.days
    early = hist.assign(shift=shift)[closure.notna() & (shift > 0)]
    if early.empty:
        return {}

    def medians(keys):
        g = early.groupby(keys)["shift"].agg(["median", "count"])
        return {k: m for k, (m, n) in g.iterrows() if n >= MIN_CALIBRATION_CASES}

    return {
        "detail": medians(["type", "product_type", "customer_segment"]),
        "segment": medians(["type", "customer_segment"]),
        "type": early.groupby("type")["shift"].median().to_dict(),
        "global": float(early["shift"].median()),
    }


def expected_shift(cal: dict, side: str, product: str, segment: str, remaining_days: int) -> int:
    if not cal:
        return remaining_days  # no history: assume an early exit could happen any time before maturity
    days = (
        cal["detail"].get((side, product, segment))
        or cal["segment"].get((side, segment))
        or cal["type"].get(side)
        or cal["global"]
    )
    return int(round(min(days, remaining_days)))


# ---------------------------------------------------------------- explanations

def _feature_groups(pipeline) -> list[str]:
    """Map every column produced by the preprocessor back to a readable driver group."""
    names = pipeline.named_steps["preprocessor"].get_feature_names_out()
    groups = []
    for name in names:
        raw = name.split("__", 1)[-1]
        if raw in FEATURE_TO_GROUP:
            groups.append(FEATURE_TO_GROUP[raw])
            continue
        # one-hot column "<feature>_<category>": pick the longest categorical feature name that prefixes it
        owner = max((c for c in CATEGORICAL_FEATURES if raw.startswith(c + "_")), key=len)
        groups.append(FEATURE_TO_GROUP[owner])
    return groups


def _display(group: str, row: dict) -> str:
    if group == "Tenor":
        return f"{int(row['tenor_days']):,} days"
    if group == "Market rate":
        return f"{row['market_interest_rate']:.2f}%"
    if group == "Interest rate difference":
        return f"contract {row['interest_rate']:.2f}% vs market {row['market_interest_rate']:.2f}%"
    if group == "Amount":
        return f"{row['amount']:,.0f} {row['currency']}"
    if group == "Client rating":
        return str(int(row["client_rating"]))
    if group == "Product and segment":
        return f"{row['product_type']}, {row['customer_segment']}"
    if group == "Location and currency":
        return f"{row['location']}, {row['currency']}"
    return f"booked {row['transaction_date']:%b %Y}, matures {row['contractual_maturity_date']:%b %Y}"


def _drivers(pipeline, X: pd.DataFrame, p: np.ndarray, feats: pd.DataFrame) -> list[list[dict]]:
    """Per-transaction drivers: how much each factor moves the probability vs. an average value.

    Logistic regression: logit = intercept + sum(coef x scaled feature). Removing a group's terms
    from the logit and re-applying the sigmoid gives that group's effect in probability points.
    """
    transformed = pipeline.named_steps["preprocessor"].transform(X)
    transformed = transformed.toarray() if hasattr(transformed, "toarray") else np.asarray(transformed)
    contrib = transformed * pipeline.named_steps["model"].coef_[0]
    groups = _feature_groups(pipeline)
    names = list(dict.fromkeys(groups))
    by_group = np.column_stack([contrib[:, [i for i, g in enumerate(groups) if g == name]].sum(axis=1) for name in names])

    logit = np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1))
    effect = p[:, None] - 1 / (1 + np.exp(-(logit[:, None] - by_group)))

    records = feats.to_dict("records")
    out = []
    for i, row in enumerate(records):
        order = np.argsort(-np.abs(effect[i]))  # every factor, strongest first
        out.append([
            {
                "feature": names[j],
                "value": _display(names[j], row),
                "contribution": round(float(effect[i, j]), 4),
                "effect": "raises exit risk" if effect[i, j] > 0 else "lowers exit risk",
            }
            for j in order
        ])
    return out


# ---------------------------------------------------------------- predictions

def live_frame(db: Session, run_date: date, book: Book) -> pd.DataFrame:
    model, principal, product = LIVE_BOOKS[book]
    rows = db.execute(select(
        model.transaction_id, model.entity, model.location, model.currency, model.customer_segment, model.client_rating,
        model.transaction_date, model.maturity_date.label("contractual_maturity_date"), principal.label("amount"),
        model.interest_rate_pct, model.market_interest_rate_pct, product.label("product_type"),
    ).where(model.run_date == run_date, model.maturity_date >= run_date)).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        for col in ("amount", "interest_rate_pct", "market_interest_rate_pct"):
            df[col] = df[col].astype(float)
        df["client_rating"] = df["client_rating"].astype(int)
    return df


def predict_book(db: Session, run_date: date, book: Book, calibration: dict | None = None) -> int:
    """Score every live transaction of one book for one run date and store the result."""
    raw = live_frame(db, run_date, book)
    db.execute(delete(Prediction).where(Prediction.run_date == run_date, Prediction.book == book))
    if raw.empty:
        db.commit()
        return 0

    model = load_model(book)
    cal = shift_calibration(historical_frame(db)) if calibration is None else calibration
    feats = create_features(raw)
    X = feats[ALL_FEATURES]
    p = np.clip(model.pipeline.predict_proba(X)[:, 1], 0.0, 1.0)
    drivers = _drivers(model.pipeline, X, p, feats)

    records = []
    for i, r in enumerate(raw.to_dict("records")):
        remaining = (r["contractual_maturity_date"] - run_date).days
        shift = expected_shift(cal, book.value, r["product_type"], r["customer_segment"], remaining)
        pulled = int(round(p[i] * shift))
        records.append({
            "run_date": run_date,
            "book": book,
            "transaction_id": r["transaction_id"],
            "location": r["location"],
            "currency": r["currency"],
            "p_early": round(float(p[i]), 5),
            "predicted_early": bool(p[i] >= model.threshold),
            "risk_level": risk_level(float(p[i])),
            "expected_shift_days": shift,
            "contractual_maturity": r["contractual_maturity_date"],
            "adjusted_maturity": r["contractual_maturity_date"] - timedelta(days=pulled),
            "drivers": drivers[i],
        })
    for i in range(0, len(records), CHUNK):
        db.execute(insert(Prediction), records[i:i + CHUNK])
    db.commit()
    logger.info("Predicted %d %s transactions for %s (mean p_early %.3f)", len(records), book, run_date, p.mean())
    return len(records)


def predict_run(db: Session, run_date: date) -> dict:
    cal = shift_calibration(historical_frame(db))
    counts = {book: predict_book(db, run_date, book, cal) for book in LIVE_BOOKS}
    if not any(counts.values()):
        raise NotFoundError(f"No live transactions found for run date {run_date}")
    avg = dict(db.execute(
        select(Prediction.book, func.avg(Prediction.p_early)).where(Prediction.run_date == run_date).group_by(Prediction.book)
    ).all())
    return {
        "run_date": run_date,
        "predicted": sum(counts.values()),
        "avg_p_early_assets": round(float(avg.get(Book.ASSET, 0) or 0), 4),
        "avg_p_early_liabilities": round(float(avg.get(Book.LIABILITY, 0) or 0), 4),
    }


def predict_all_runs(db: Session) -> int:
    run_dates = set(db.scalars(select(AssetBook.run_date).distinct())) | set(db.scalars(select(LiabilityBook.run_date).distinct()))
    for run_date in sorted(run_dates):
        predict_run(db, run_date)
    return len(run_dates)


def ensure_predictions(db: Session, run_date: date) -> None:
    """Predictions are made at upload time; this re-creates them if they are missing (e.g. model added later)."""
    for book, (model, _, _) in LIVE_BOOKS.items():
        has_live = db.scalar(select(model.id).where(model.run_date == run_date, model.maturity_date >= run_date).limit(1))
        has_pred = db.scalar(select(Prediction.id).where(Prediction.run_date == run_date, Prediction.book == book).limit(1))
        if has_live and not has_pred:
            predict_book(db, run_date, book)


# ---------------------------------------------------------------- rationale

def _summary(row: Prediction, drivers: list[dict], pulled: int) -> str:
    event = "pre-close this loan" if row.book == Book.ASSET else "withdraw this deposit early"
    up = [d for d in drivers if d["contribution"] >= 0.005][:2]
    text = f"{float(row.p_early):.1%} probability the customer will {event} ({row.risk_level.lower()} risk)."
    if up:
        text += " Main factors pushing it up: " + ", ".join(f"{d['feature'].lower()} ({d['value']})" for d in up) + "."
    if pulled > 0:
        text += (f" Similar contracts closed about {row.expected_shift_days} days before maturity, so the expected "
                 f"maturity moves {pulled} days earlier.")
    return text


def rationale(db: Session, run_date: date, transaction_id: str, allowed_locations) -> PredictionRationale:
    ensure_predictions(db, run_date)
    row = db.scalar(select(Prediction).where(Prediction.run_date == run_date, Prediction.transaction_id == transaction_id))
    if row is None:
        raise NotFoundError(f"No prediction for {transaction_id} on {run_date}")
    if row.location not in allowed_locations:
        raise ForbiddenError("You do not have access to this location's data")

    pulled = (row.contractual_maturity - row.adjusted_maturity).days
    drivers = row.drivers or []
    return PredictionRationale(
        transaction_id=row.transaction_id,
        book=row.book,
        p_early=float(row.p_early),
        predicted_early=row.predicted_early,
        risk_level=row.risk_level,
        threshold=load_model(row.book).threshold,
        expected_shift_days=row.expected_shift_days,
        contractual_maturity=row.contractual_maturity,
        adjusted_maturity=row.adjusted_maturity,
        days_pulled_forward=pulled,
        drivers=[FeatureDriver(**d) for d in drivers],
        summary=_summary(row, drivers, pulled),
    )
