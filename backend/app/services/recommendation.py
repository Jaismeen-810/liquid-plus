from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import Bucket, GapType, LadderView, RecommendationRule
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


def _rationale(currency: str, gap: float, det_gap: float) -> str:
    shift = gap - det_gap
    text = f"AI-adjusted gap {signed(currency, gap)} vs deterministic {signed(currency, det_gap)}. "
    if abs(shift) < max(1000.0, abs(gap) * 0.005):
        return text + "Customer behavior barely changes this bucket."
    return text + f"Customer behavior {'worsens' if shift < 0 else 'improves'} the position by {format_amount(currency, shift)}."


def build_recommendations(det_cells: list[dict], ai_cells: list[dict]) -> list[RecommendationOut]:
    """Treasury actions per currency x location x bucket, from the AI-adjusted ladder.

    A material gap is at least MATERIALITY_THRESHOLD_PCT of the larger side (assets or liabilities).
      Rule A  material shortfall                              -> raise funding
      Rule B  material surplus, no shortfall later            -> invest it, keeping LIQUIDITY_BUFFER_PCT back
      Rule D  material surplus, material shortfall later on   -> keep enough to cover that shortfall, invest the rest
      Rule C  behaviour worsens the gap by a material amount  -> review buffers (in addition to A/B/D)
    """
    settings = get_settings()
    threshold = settings.materiality_threshold_pct / 100
    buffer_pct = settings.liquidity_buffer_pct / 100
    det = {(c["currency"], c["location"], c["bucket"]): c["net_gap"] for c in det_cells}
    ladders: dict[tuple[str, str], dict[Bucket, dict]] = defaultdict(dict)
    for c in ai_cells:
        ladders[(c["currency"], c["location"])][c["bucket"]] = c

    def material(value: float, cell: dict) -> bool:
        scale = max(cell["assets"], cell["liabilities"])
        return value != 0 and scale > 0 and abs(value) >= scale * threshold

    buckets = list(Bucket)
    out = []
    for (cur, loc), cells in ladders.items():
        for i, bucket in enumerate(buckets):
            c = cells.get(bucket)
            if c is None:
                continue
            gap = c["net_gap"]
            det_gap = det.get((cur, loc, bucket), 0.0)
            scale = max(c["assets"], c["liabilities"])
            where = f"({loc}, {bucket.value})"
            common = dict(currency=cur, location=loc, bucket=bucket, deterministic_gap=round(det_gap, 2),
                          ai_gap=round(gap, 2), gap_difference=round(gap - det_gap, 2))

            def add(rule: RecommendationRule, **fields):
                out.append(RecommendationOut(id=f"{rule.value}|{cur}|{loc}|{bucket.value}", rule_code=rule, **common, **fields))

            if material(gap, c) and gap < 0:
                add(RecommendationRule.RAISE_FUNDING, category="Funding required", gap_type=GapType.SHORTFALL,
                    severity=_severity(abs(gap) / scale), amount=round(abs(gap), 2),
                    action_text=f"{SHORTFALL_ACTIONS[bucket]} – {format_amount(cur, gap)} {where}",
                    detailed_action=f"Arrange funding to cover the projected {bucket.value} shortfall before it falls due.",
                    reason="AI-adjusted liabilities exceed assets in this bucket.",
                    rationale=_rationale(cur, gap, det_gap))

            elif material(gap, c) and gap > 0:
                later = next((b for b in buckets[i + 1:] if b in cells and cells[b]["net_gap"] < 0
                              and material(cells[b]["net_gap"], cells[b])), None)
                if later:
                    shortfall = abs(cells[later]["net_gap"])
                    reserved = min(gap, shortfall)
                    buffer = (gap - reserved) * buffer_pct
                    investable = gap - reserved - buffer
                    add(RecommendationRule.PRESERVE, category="Preserve liquidity", gap_type=GapType.PRESERVE,
                        severity="medium", amount=round(reserved, 2), reserved_amount=round(reserved, 2),
                        investable_surplus=round(investable, 2), required_buffer=round(buffer, 2),
                        action_text=f"Preserve {format_amount(cur, reserved)} for upcoming {later.value} obligations {where}",
                        detailed_action=(f"Keep {format_amount(cur, reserved)} of this surplus for the {later.value} shortfall; "
                                         f"invest only the remaining {format_amount(cur, investable)}."),
                        reason=f"A shortfall in {later.value} follows this {bucket.value} surplus.",
                        rationale=(f"Surplus of {signed(cur, gap)} in {bucket.value} precedes a projected shortfall of "
                                   f"{signed(cur, -shortfall)} in {later.value}. Keeping it avoids emergency borrowing later."))
                else:
                    buffer = gap * buffer_pct
                    investable = gap - buffer
                    add(RecommendationRule.DEPLOY_SURPLUS, category="Potential investment", gap_type=GapType.SURPLUS,
                        severity="surplus", amount=round(investable, 2), investable_surplus=round(investable, 2),
                        required_buffer=round(buffer, 2),
                        action_text=f"{SURPLUS_ACTIONS[bucket]} – {format_amount(cur, investable)} {where}",
                        detailed_action=(f"Invest {format_amount(cur, investable)} after keeping a "
                                         f"{settings.liquidity_buffer_pct:g}% liquidity buffer ({format_amount(cur, buffer)})."),
                        reason="AI-adjusted assets exceed liabilities and no shortfall follows.",
                        rationale=_rationale(cur, gap, det_gap))

            behaviour = gap - det_gap
            if behaviour < 0 and material(behaviour, c):
                add(RecommendationRule.BEHAVIOURAL_RISK, category="Behavioural risk alert", gap_type=GapType.RISK_ALERT,
                    severity="monitor", amount=round(abs(behaviour), 2), reserved_amount=round(abs(behaviour), 2),
                    action_text=f"Review liquidity buffer & contingency funding – {format_amount(cur, behaviour)} {where}",
                    detailed_action="Review reserves: the behavioural model expects early withdrawals or prepayments in this bucket.",
                    reason="Predicted customer behaviour makes this bucket worse than the contracts show.",
                    rationale=(f"Contractual gap {signed(cur, det_gap)}, AI-adjusted {signed(cur, gap)}: behaviour moves "
                               f"{format_amount(cur, behaviour)} of net outflow into this bucket."))

    rank = {"high": 0, "monitor": 1, "medium": 2, "surplus": 3, "low": 4}
    order = {b: i for i, b in enumerate(Bucket)}
    return sorted(out, key=lambda r: (rank[r.severity], order[r.bucket], -r.amount))


def both_ladders(db: Session, run_date: date, scope: Scope) -> tuple[list[dict], list[dict]]:
    ensure_predictions(db)
    return (ladder_cells(db, run_date, LadderView.DETERMINISTIC, scope), ladder_cells(db, run_date, LadderView.AI, scope))


def list_recommendations(db: Session, run_date: date, scope: Scope, bucket: Bucket | None = None) -> list[RecommendationOut]:
    recs = build_recommendations(*both_ladders(db, run_date, scope))
    return [r for r in recs if bucket is None or r.bucket == bucket]
