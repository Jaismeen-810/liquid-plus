def test_health_endpoints(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/db").json()["database"] == "up"


def test_login_success_and_me(client, london_headers):
    me = client.get("/api/auth/me", headers=london_headers).json()
    assert me["username"] == "london" and me["location"] == "London"


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "london", "password": "wrong-password"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_missing_and_invalid_token(client):
    assert client.get("/api/ladder/deterministic").status_code == 401
    assert client.get("/api/ladder/deterministic", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_branch_user_cannot_upload_or_train(client, london_headers):
    assert client.post("/api/ingest/assets", files={"file": ("a.csv", b"x")}, headers=london_headers).status_code == 403
    assert client.post("/api/ml/train", json={}, headers=london_headers).status_code == 403


def test_auth_checked_before_data_lookup(client):
    r = client.get("/api/ladder/deterministic", params={"run_date": "1999-01-01"})
    assert r.status_code == 401


def test_branch_user_cannot_see_other_branch_history(client, london_headers):
    r = client.get("/api/analytics/exit-trends", params={"location": "Singapore"}, headers=london_headers)
    assert r.status_code == 403
