from app.constants import Bucket
from app.services.recommendation import build_recommendations

BUCKETS = list(Bucket)


def ladder(gaps: list[float], side: float = 100.0) -> list[dict]:
    """One currency/location ladder: each net gap built from `side` on the larger leg."""
    cells = []
    for bucket, gap in zip(BUCKETS, gaps):
        assets, liabilities = (side, side - gap) if gap >= 0 else (side + gap, side)
        cells.append({"currency": "USD", "location": "London", "bucket": bucket, "assets": assets,
                      "liabilities": liabilities, "net_gap": gap})
    return cells


def rules(recs) -> dict:
    return {(r.rule_code.value, r.bucket.value): r for r in recs}


def test_shortfall_raises_funding():
    cells = ladder([-60, 0, 0, 0, 0])
    r = rules(build_recommendations(cells, cells))[("RULE_A", "0-1M")]
    assert r.amount == 60 and r.severity == "high" and r.gap_type == "shortfall"


def test_surplus_without_later_shortfall_is_invested_after_buffer():
    cells = ladder([50, 0, 0, 0, 0])
    r = rules(build_recommendations(cells, cells))[("RULE_B", "0-1M")]
    assert r.required_buffer == 2.0 and r.investable_surplus == 48.0  # 4% buffer


def test_surplus_before_shortfall_is_preserved():
    cells = ladder([50, 0, -30, 0, 0])
    found = rules(build_recommendations(cells, cells))
    preserve = found[("RULE_D", "0-1M")]
    assert ("RULE_B", "0-1M") not in found
    assert preserve.reserved_amount == 30 and preserve.investable_surplus == 19.2  # (50 - 30) less 4% buffer
    assert ("RULE_A", "3-12M") in found


def test_behaviour_worsening_gap_raises_risk_alert():
    det, ai = ladder([-5, 0, 0, 0, 0]), ladder([-40, 0, 0, 0, 0])
    found = rules(build_recommendations(det, ai))
    alert = found[("RULE_C", "0-1M")]
    assert alert.amount == 35 and alert.severity == "monitor" and ("RULE_A", "0-1M") in found


def test_immaterial_gap_needs_no_action():
    cells = ladder([5, -5, 0, 0, 0])  # 5% of the larger side, below the 10% threshold
    assert build_recommendations(cells, cells) == []
