import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.constants import LOCATIONS, Role  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.models import User  # noqa: E402
from app.db import SessionLocal  # noqa: E402


def load_users(path: Path) -> list[dict]:
    users = json.loads(path.read_text(encoding="utf-8"))
    for u in users:
        role = Role(u["role"])
        if role == Role.BRANCH and u.get("location") not in LOCATIONS:
            raise ValueError(f"User {u['username']} needs a valid location, one of {sorted(LOCATIONS)}")
        if len(u.get("password", "")) < 8:
            raise ValueError(f"User {u['username']} needs a password of at least 8 characters")
    return users


def seed(path: Path) -> None:
    users = load_users(path)
    with SessionLocal() as db:
        for u in users:
            existing = db.query(User).filter(User.username == u["username"]).one_or_none()
            target = existing or User(username=u["username"])
            target.full_name = u.get("full_name")
            target.role = Role(u["role"])
            target.location = u.get("location") if target.role == Role.BRANCH else None
            target.password_hash = hash_password(u["password"])
            target.is_active = True
            db.add(target)
            print(f"{'updated' if existing else 'created'}: {u['username']} ({target.role}, {target.location or 'all locations'})")
        db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or update predefined Liquid+ users")
    parser.add_argument("file", nargs="?", default=os.getenv("SEED_USERS_FILE", "seed_users.json"))
    seed(Path(parser.parse_args().file))
