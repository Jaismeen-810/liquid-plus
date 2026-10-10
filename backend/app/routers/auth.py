from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.errors import UnauthorizedError
from app.models import User
from app.schemas import CurrentUser, LoginRequest, LoginResponse, UserOut
from app.security import create_access_token, verify_password
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        audit.record(db, None, "login_failed", username=body.username)
        raise UnauthorizedError("Invalid username or password")
    token, expires_in = create_access_token(user.username, user.role, user.location)
    audit.record(db, CurrentUser(id=user.id, username=user.username, role=user.role, location=user.location), "login")
    return LoginResponse(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.get(User, current.id)
