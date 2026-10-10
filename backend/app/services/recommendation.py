from datetime import date

from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import Bucket, GapType, LadderView
from app.ml.behavior import ensure_predictions
from app.schemas import RecommendationOut
from app.services.ladder import Scope, ladder_cells

SHORTFALL_ACTIONS = {
    Bucket.M0_1: "Raise short-term funding (interbank / repo)",
    Bucket.M1_3: "Issue 3M certificates of deposit or extend maturing deposits",
    Bucket.M3_12: "Secure 6–12M term funding",
    Bucket.Y1_5: "Arrange medium-term borrowing or bond issuance",
    Bucket.Y5_PLUS: "Lock in long-term funding",
}
SURPLUS_ACTIONS = {
    Bucket.M0_1: "Place surplus in overnight / money-market deposits",
    Bucket.M1_3: "Invest surplus in 3M Treasury bills",
    Bucket.M3_12: "Invest surplus in 6M Treasury",
    Bucket.Y1_5: "Invest surplus in 2–5Y government bonds",
    Bucket.Y5_PLUS: "Deploy surplus into long-term lending or investment",
}


def format_amount(currency: str, value: float) -> str:
    v = abs(value)
    if v >= 1e9:
        return f"{currency} {v / 1e9:.2f}B"
    if v >= 1e6:
        return f"{currency} {v / 1e6:.1f}M"
    return f"{currency} {v / 1e3:.0f}K"


def signed(currency: str, value: float) -> str:
    return f"{'−' if value < 0 else '+'}{format_amount(currency, value)}"


def _severity(ratio: float) -> str:
    return "high" if ratio >= 0.5 else "medium" if ratio >= 0.2 else "low"


def build_recommendations(det_cells: list[dict], ai_cells: list[dict]) -> list[RecommendationOut]:
    """One action per currency x location x bucket whose AI-adjusted gap is material."""
    threshold = get_settings().materiality_threshold_pct / 100
    det = {(c["currency"], c["location"], c["bucket"]): c["net_gap"] for c in det_cells}
    out = []
    for c in ai_cells:
        gap = c["net_gap"]
        scale = max(c["assets"], c["liabilities"])
        if gap == 0 or scale == 0 or abs(gap) < scale * threshold:
            continue
        action = (SHORTFALL_ACTIONS if gap < 0 else SURPLUS_ACTIONS)[c["bucket"]]
        det_gap = det.get((c["currency"], c["location"], c["bucket"]), 0.0)
        shift = gap - det_gap
        rationale = f"AI-adjusted gap {signed(c['currency'], gap)} vs deterministic {signed(c['currency'], det_gap)}. " + (
            "Customer behavior barely changes this bucket."
            if abs(shift) < max(1000.0, abs(gap) * 0.005)
            else f"Customer behavior {'worsens' if shift < 0 else 'improves'} the position by {format_amount(c['currency'], shift)}."
        )
        out.append(RecommendationOut(
            id=f"{c['currency']}|{c['location']}|{c['bucket'].value}",
            currency=c["currency"],
            location=c["location"],
            bucket=c["bucket"],
            gap_type=GapType.SHORTFALL if gap < 0 else GapType.SURPLUS,
            deterministic_gap=det_gap,
            ai_gap=gap,
            severity=_severity(abs(gap) / scale),
            action_text=f"{action} – {format_amount(c['currency'], gap)} ({c['location']}, {c['bucket'].value})",
            rationale=rationale,
        ))
    rank = {"high": 0, "medium": 1, "low": 2}
    order = {b: i for i, b in enumerate(Bucket)}
    return sorted(out, key=lambda r: (rank[r.severity], order[r.bucket], -abs(r.ai_gap)))


def both_ladders(db: Session, run_date: date, scope: Scope) -> tuple[list[dict], list[dict]]:
    ensure_predictions(db, run_date)
    return (ladder_cells(db, run_date, LadderView.DETERMINISTIC, scope), ladder_cells(db, run_date, LadderView.AI, scope))


def list_recommendations(db: Session, run_date: date, scope: Scope, bucket: Bucket | None = None) -> list[RecommendationOut]:
    recs = build_recommendations(*both_ladders(db, run_date, scope))
    return [r for r in recs if bucket is None or r.bucket == bucket]
