"""Retrain the asset and liability behavioral models from the historical log in the database.

Same approach as the ML project (ML/train.py): logistic regression, a small search over regularisation
settings, then a probability threshold tuned for accuracy. Overwrites ml_models/{book}_model.joblib.
"""
import json
import logging
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy.orm import Session

from app.constants import Book
from app.errors import ModelNotReadyError
from app.ml import behavior
from app.ml.features import ALL_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES, create_features, create_target

logger = logging.getLogger(__name__)

MIN_ROWS = 200
CONFIGURATIONS = [{"C": c, "class_weight": None} for c in (0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0)] + [
    {"C": c, "class_weight": "balanced"} for c in (0.1, 0.2, 0.5)
]


def _pipeline(C: float, class_weight) -> Pipeline:
    preprocessor = ColumnTransformer([
        ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), NUMERIC_FEATURES),
        ("categorical", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")),
                                  ("onehot", OneHotEncoder(handle_unknown="ignore"))]), CATEGORICAL_FEATURES),
    ])
    model = LogisticRegression(C=C, class_weight=class_weight, max_iter=3000, random_state=42)
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def _best_threshold(y, p) -> float:
    candidates = np.round(np.arange(0.30, 0.71, 0.01), 2)
    scores = [accuracy_score(y, p >= t) for t in candidates]
    return float(candidates[int(np.argmax(scores))])


def train_book(hist, book: Book) -> dict:
    df = create_target(create_features(hist[hist["type"] == book.value]))
    if len(df) < MIN_ROWS or df["early_exit"].nunique() < 2:
        raise ModelNotReadyError(f"Need at least {MIN_ROWS} closed {book.value} contracts with both outcomes, found {len(df)}")

    X, y = df[ALL_FEATURES], df["early_exit"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    best, best_acc, best_cfg = None, -1.0, None
    for cfg in CONFIGURATIONS:
        candidate = _pipeline(**cfg).fit(X_train, y_train)
        acc = accuracy_score(y_test, candidate.predict_proba(X_test)[:, 1] >= 0.5)
        if acc > best_acc:
            best, best_acc, best_cfg = candidate, acc, cfg

    p = best.predict_proba(X_test)[:, 1]
    threshold = _best_threshold(y_test, p)
    pred = p >= threshold
    meta = {
        "threshold": threshold,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training_rows": int(len(X_train)),
        "config": {"C": best_cfg["C"], "class_weight": best_cfg["class_weight"]},
        "metrics": {
            "accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "precision": round(float(precision_score(y_test, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, pred, zero_division=0)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, p)), 4),
            "early_rate": round(float(y.mean()), 4),
            "test_rows": int(len(X_test)),
        },
    }
    model_path, meta_path = behavior.model_paths(book)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best, model_path)
    meta_path.write_text(json.dumps(meta, indent=2))
    logger.info("Trained %s model: %s", book.value, meta["metrics"])
    return meta


def train_models(db: Session) -> list:
    hist = behavior.historical_frame(db)
    if hist.empty:
        raise ModelNotReadyError("Upload the historical log before training")
    for book in (Book.ASSET, Book.LIABILITY):
        train_book(hist, book)
    behavior.reset_model_cache()
    behavior.predict_all_runs(db)
    return behavior.model_info()
