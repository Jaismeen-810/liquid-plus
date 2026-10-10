from typing import Any

from sqlalchemy.orm import Session

from app.logs import audit_log
from app.models import AuditLog
from app.schemas import CurrentUser


def record(db: Session, user: CurrentUser | None, action: str, **detail: Any) -> None:
    username = user.username if user else detail.pop("username", None)
    audit_log(username, action, **detail)
    db.add(AuditLog(user_id=user.id if user else None, username=username, action=action, detail=_jsonable(detail)))
    db.commit()


def _jsonable(detail: dict) -> dict:
    return {k: v if isinstance(v, (int, float, bool, str, type(None), list, dict)) else str(v) for k, v in detail.items()}
