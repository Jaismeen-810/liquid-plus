from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.constants import LOCATIONS
from app.db import get_db
from app.deps import get_current_user, require_support, resolve_run_date
from app.ml import behavior, train
from app.schemas import CurrentUser, ModelInfo, PredictionRationale, PredictResponse
from app.services import audit

router = APIRouter(prefix="/ml", tags=["behavioral model"])


@router.get("/models", response_model=list[ModelInfo])
def models(_: CurrentUser = Depends(get_current_user)):
    return behavior.model_info()


@router.post("/train", response_model=list[ModelInfo])
def retrain(user: CurrentUser = Depends(require_support), db: Session = Depends(get_db)):
    """Retrain both models from the historical log, then re-score every run date."""
    result = train.train_models(db)
    audit.record(db, user, "model_train", models=[m.model_dump(mode="json") for m in result])
    return result


@router.post("/predict", response_model=PredictResponse)
def predict(run_date: date = Depends(resolve_run_date), user: CurrentUser = Depends(require_support), db: Session = Depends(get_db)):
    summary = behavior.predict_run(db, run_date)
    audit.record(db, user, "predict", run_date=run_date.isoformat(), predicted=summary["predicted"])
    return summary


@router.get("/predictions/{transaction_id}", response_model=PredictionRationale)
def prediction_rationale(
    transaction_id: str,
    run_date: date = Depends(resolve_run_date),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return behavior.rationale(db, run_date, transaction_id, user.allowed_locations(LOCATIONS))
