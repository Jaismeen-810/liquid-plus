import io
import os
import random
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
_tmp = Path(tempfile.mkdtemp(prefix="liquidplus-test-"))
shutil.copytree(BACKEND / "ml_models", _tmp / "ml_models")  # retraining in tests must not touch the real model files

if "TEST_DATABASE_URL" not in os.environ:
    raise RuntimeError("Set TEST_DATABASE_URL to an empty PostgreSQL database; the tests drop and recreate every table")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-not-for-production-use")
os.environ["LOG_DIR"] = str(_tmp / "logs")
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["MODEL_DIR"] = str(_tmp / "ml_models")

from fastapi.testclient import TestClient  # noqa: E402

from app.constants import ENTITY_LOCATION, Role  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

RUN_DATE = date(2026, 10, 10)
PASSWORD = "test-password"
ENTITIES = list(ENTITY_LOCATION)
SEGMENTS = ["Retail", "Corporate", "SME", "Institutional"]
CURRENCIES = ["USD", "EUR", "GBP", "SGD", "HKD"]


def iso(d: date) -> str:
    return d.isoformat()


def asset_row(i: int, **overrides) -> dict:
    entity = ENTITIES[i % 5]
    row = {
        "Transaction_ID": f"AST-{i:06d}", "Entity": entity, "Location": ENTITY_LOCATION[entity], "Customer_ID": f"CUS-{i:05d}",
        "Loan_Amount": "1000000", "Currency": CURRENCIES[i % 5], "Transaction_Date": iso(RUN_DATE - timedelta(days=30)),
        "Maturity_Date": iso(RUN_DATE + timedelta(days=20 + 90 * (i % 12))), "Interest_Rate_Pct": "5.0",
        "Market_Interest_Rate_Pct": "4.5", "Loan_Type": "Loan-Type-A", "Customer_Segment": SEGMENTS[i % 4], "Client_Rating": "3",
    }
    row.update(overrides)
    return row


def liability_row(i: int, **overrides) -> dict:
    row = asset_row(i)
    row["Transaction_ID"] = f"LIA-{i:06d}"
    row["Amount"] = row.pop("Loan_Amount")
    row.pop("Loan_Type")
    row["Product_Type"] = "Product-B"
    row.update(overrides)
    return {k: row[k] for k in ["Transaction_ID", "Entity", "Location", "Customer_ID", "Amount", "Currency", "Transaction_Date",
                                "Maturity_Date", "Interest_Rate_Pct", "Market_Interest_Rate_Pct", "Product_Type",
                                "Customer_Segment", "Client_Rating"]}


def history_rows(n: int = 1200, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        entity = rng.choice(ENTITIES)
        is_asset = i % 2 == 0
        start = date(2023, 1, 1) + timedelta(days=rng.randint(0, 1000))
        tenor = rng.randint(60, 1500)
        maturity = start + timedelta(days=tenor)
        rate, market = round(rng.uniform(2, 7), 2), round(rng.uniform(2, 7), 2)
        incentive = (rate - market) if is_asset else (market - rate)
        p_early = min(0.9, max(0.05, 0.3 + 0.12 * incentive + tenor / 6000))
        if rng.random() < p_early:
            closure = start + timedelta(days=rng.randint(10, tenor - 1))
        elif maturity < date(2026, 9, 30):
            closure = maturity
        else:
            closure = None
        rows.append({
            "Transaction_ID": f"{'AST' if is_asset else 'LIA'}-{100000 + i}", "Entity": entity,
            "Type": "Asset" if is_asset else "Liability", "Location": ENTITY_LOCATION[entity], "Transaction_Date": iso(start),
            "Customer_ID": f"CUS-{rng.randint(1, 9999):05d}", "Customer_Segment": rng.choice(SEGMENTS),
            "Client_Rating": str(rng.randint(1, 5)), "Amount": str(rng.randint(1, 50) * 100000), "Currency": rng.choice(CURRENCIES),
            "Interest_Rate_Pct": str(rate), "Market_Interest_Rate_Pct": str(market),
            "Product_Type": rng.choice(["Loan-Type-A", "Loan-Type-C"]) if is_asset else rng.choice(["Product-A", "Product-D"]),
            "Contractual_Maturity_Date": iso(maturity), "Actual_Closure_Date": iso(closure) if closure else "",
        })
    return rows


def csv_bytes(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    pd.DataFrame(rows).to_csv(buffer, index=False)
    return buffer.getvalue().encode()


@pytest.fixture(scope="session", autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add_all([
            User(username="support", role=Role.SUPPORT, location=None, password_hash=hash_password(PASSWORD)),
            User(username="london", role=Role.BRANCH, location="London", password_hash=hash_password(PASSWORD)),
            User(username="singapore", role=Role.BRANCH, location="Singapore", password_hash=hash_password(PASSWORD)),
        ])
        db.commit()
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    shutil.rmtree(_tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _token(client, username: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def support_headers(client):
    return _token(client, "support")


@pytest.fixture(scope="session")
def london_headers(client):
    return _token(client, "london")


@pytest.fixture(scope="session")
def loaded(client, support_headers):
    """Runs the full data injection flow: historical log, then the two live books (scored on upload)."""
    stamp = RUN_DATE.strftime("%d%m%Y")
    files = {
        "historical": ("historical_log.csv", csv_bytes(history_rows())),
        "assets": (f"asset_book - {stamp}.csv", csv_bytes([asset_row(i) for i in range(1, 51)])),
        "liabilities": (f"liability_book - {stamp}.csv", csv_bytes([liability_row(i, Amount="800000") for i in range(1, 61)])),
    }
    for book, f in files.items():
        r = client.post(f"/api/ingest/{book}", files={"file": f}, headers=support_headers)
        assert r.status_code == 200, r.text
    return RUN_DATE
