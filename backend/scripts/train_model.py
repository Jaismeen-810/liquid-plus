"""Retrain the asset and liability behavioral models from the historical log already in the database,
then re-score every loaded run date. Same as POST /api/ml/train.

    python scripts/train_model.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal  # noqa: E402
from app.logs import setup_logging  # noqa: E402
from app.ml.train import train_models  # noqa: E402

if __name__ == "__main__":
    setup_logging()
    with SessionLocal() as db:
        for info in train_models(db):
            print(f"{info.book.value}: threshold {info.threshold}, metrics {json.dumps(info.metrics)}")
