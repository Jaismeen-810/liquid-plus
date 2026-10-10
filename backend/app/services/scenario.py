from sqlalchemy.orm import Session

from app.constants import LadderView
from app.errors import NotFoundError
from app.schemas import ScenarioRequest, ScenarioResponse
from app.services.ladder import Scope, build_response, compute_cells, flows_subquery, ladder_cells


def run_scenario(db: Session, request: ScenarioRequest, scope: Scope) -> ScenarioResponse:
    """What-if: shift contractual maturities and recompute the ladder. The behavioral model is not used."""
    sub = flows_subquery(request.run_date, LadderView.SCENARIO, asset_shift=request.asset_shift, liability_shift=request.liability_shift)
    cells = compute_cells(db, sub, scope)
    if not cells:
        raise NotFoundError("No transactions match the selected filters")

    parts = []
    if request.asset_shift and request.asset_shift.value:
        parts.append(f"asset maturities {request.asset_shift.label()}")
    if request.liability_shift and request.liability_shift.value:
        parts.append(f"liability maturities {request.liability_shift.label()}")

    return ScenarioResponse(
        description="Shift " + " and ".join(parts),
        baseline=build_response(request.run_date, LadderView.DETERMINISTIC, ladder_cells(db, request.run_date, LadderView.DETERMINISTIC, scope)),
        scenario=build_response(request.run_date, LadderView.SCENARIO, cells),
    )
