from datetime import date

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.constants import CURRENCIES, LOCATIONS
from app.db import get_db
from app.errors import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.models import User
from app.schemas import CurrentUser
from app.security import decode_access_token
from app.services import audit
from app.services.ingestion import latest_run_date
from app.services.ladder import Scope

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> CurrentUser:
    if credentials is None:
        raise UnauthorizedError("Authentication required")
    payload = decode_access_token(credentials.credentials)
    user = db.query(User).filter(User.username == payload.get("sub")).one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return CurrentUser(id=user.id, username=user.username, role=user.role, location=user.location)


def require_support(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_support:
        raise ForbiddenError("This action requires the support role")
    return user


def build_scope(db: Session, user: CurrentUser, location: str | None, currency: str | None) -> Scope:
    """Location-based users only ever see their own location; support users see all (or the one they pick)."""
    if currency and currency.upper() not in CURRENCIES:
        raise AppError(f"Unknown currency '{currency}'", {"allowed": sorted(CURRENCIES)})
    if location and location not in LOCATIONS:
        raise AppError(f"Unknown location '{location}'", {"allowed": sorted(LOCATIONS)})

    allowed = user.allowed_locations(LOCATIONS)
    if location and location not in allowed:
        audit.record(db, user, "access_denied", requested_location=location)
        raise ForbiddenError("You do not have access to this location's data")
    locations = (location,) if location else tuple(sorted(allowed))
    return Scope(locations=locations, currency=currency.upper() if currency else None, location=location)


def get_scope(
    location: str | None = Query(None, description="Filter to one location"),
    currency: str | None = Query(None, min_length=3, max_length=3, description="Filter to one currency"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Scope:
    return build_scope(db, user, location, currency)


def resolve_run_date(
    run_date: date | None = Query(None, description="Calculation date the buckets are measured from (default: today)"),
    _: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> date:
    """Any calendar date. Ladders always use the latest uploaded books, bucketed from this date."""
    if latest_run_date(db) is None:
        raise NotFoundError("No data uploaded yet")
    return run_date or date.today()
