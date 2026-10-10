from tests.conftest import csv_bytes, liability_row


def test_upload_scores_live_books(client, support_headers, loaded):
    dates = client.get("/api/ingest/run-dates", headers=support_headers).json()
    assert dates[0] == {"run_date": str(loaded), "has_assets": True, "has_liabilities": True, "has_predictions": True}


def test_upload_reports_rejected_rows(client, support_headers, loaded):
    rows = [liability_row(900), liability_row(901, Currency="INR"), liability_row(902, Location="Paris")]
    r = client.post("/api/ingest/liabilities", files={"file": ("bad.csv", csv_bytes(rows))},
                    data={"run_date": "2020-01-01"}, headers=support_headers)
    body = r.json()
    assert r.status_code == 200
    assert body["batch"]["rows_accepted"] == 1 and body["batch"]["rows_rejected"] == 2
    assert {e["column_name"] for e in body["errors_preview"]} == {"Currency", "Location"}
    errors = client.get(f"/api/ingest/batches/{body['batch']['id']}/errors", headers=support_headers).json()
    assert errors["total"] == 2


def test_unsupported_file_type(client, support_headers):
    r = client.post("/api/ingest/assets", files={"file": ("data.txt", b"hello")}, headers=support_headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_file"


def test_missing_columns_rejected(client, support_headers):
    r = client.post("/api/ingest/assets", files={"file": ("asset_book - 10102026.csv", b"Transaction_ID\nAST-1\n")},
                    headers=support_headers)
    assert r.status_code == 422 and "Loan_Amount" in r.json()["error"]["details"]["missing_columns"]


def test_deterministic_ladder_totals(client, support_headers, loaded):
    body = client.get("/api/ladder/deterministic", params={"run_date": loaded}, headers=support_headers).json()
    assets = sum(b["asset_count"] for s in body["series"] for b in s["buckets"])
    liabilities = sum(b["liability_count"] for s in body["series"] for b in s["buckets"])
    assert assets == 50 and liabilities == 60
    for s in body["series"]:
        assert [b["bucket"] for b in s["buckets"]] == ["0-1M", "1-3M", "3-12M", "1-5Y", ">5Y"]
        for b in s["buckets"]:
            assert round(b["assets"] - b["liabilities"], 2) == b["net_gap"]


def test_branch_user_sees_only_own_location(client, london_headers, loaded):
    body = client.get("/api/ladder/deterministic", params={"run_date": loaded}, headers=london_headers).json()
    assert {s["location"] for s in body["series"]} == {"London"}
    r = client.get("/api/ladder/deterministic", params={"run_date": loaded, "location": "Paris"}, headers=london_headers)
    assert r.status_code == 403


def test_support_user_sees_all_locations(client, support_headers, loaded):
    body = client.get("/api/ladder/deterministic", params={"run_date": loaded}, headers=support_headers).json()
    assert len({s["location"] for s in body["series"]}) == 5


def test_drilldown_matches_bucket_count(client, support_headers, loaded):
    ladder = client.get("/api/ladder/deterministic", params={"run_date": loaded}, headers=support_headers).json()
    expected = sum(b["asset_count"] + b["liability_count"] for s in ladder["series"] for b in s["buckets"] if b["bucket"] == "1-3M")
    page = client.get("/api/ladder/deterministic/transactions", params={"run_date": loaded, "bucket": "1-3M"}, headers=support_headers).json()
    assert page["total"] == expected


def test_ai_ladder_and_rationale(client, london_headers, loaded):
    ai = client.get("/api/ladder/ai", params={"run_date": loaded}, headers=london_headers)
    assert ai.status_code == 200 and ai.json()["view"] == "ai"
    page = client.get("/api/ladder/ai/transactions", params={"run_date": loaded, "bucket": "3-12M"}, headers=london_headers).json()
    row = page["items"][0]
    assert row["adjusted_maturity"] <= row["contractual_maturity"] and 0 <= row["p_early"] <= 1 and row["risk_level"]
    rationale = client.get(f"/api/ml/predictions/{row['transaction_id']}", params={"run_date": loaded}, headers=london_headers).json()
    assert rationale["drivers"] and "probability" in rationale["summary"]
    assert {d["feature"] for d in rationale["drivers"]} >= {"Tenor", "Amount"}


def test_rationale_hidden_from_other_location(client, london_headers, support_headers, loaded):
    page = client.get("/api/ladder/ai/transactions", params={"run_date": loaded, "bucket": "3-12M", "location": "Paris"},
                      headers=support_headers).json()
    r = client.get(f"/api/ml/predictions/{page['items'][0]['transaction_id']}", params={"run_date": loaded}, headers=london_headers)
    assert r.status_code == 403


def test_compare_and_recommendations(client, support_headers, loaded):
    body = client.get("/api/ladder/compare", params={"run_date": loaded}, headers=support_headers).json()
    assert body["currencies"] and len(body["currencies"][0]["buckets"]) == 5
    recs = client.get("/api/recommendations", params={"run_date": loaded}, headers=support_headers)
    assert recs.status_code == 200
    assert all(r["action_text"] for r in recs.json())


def test_scenario_shift_changes_ladder(client, support_headers, loaded):
    body = {"run_date": str(loaded), "liability_shift": {"value": 3, "unit": "months", "direction": "earlier"}}
    result = client.post("/api/scenario/run", json=body, headers=support_headers).json()
    base = [b["net_gap"] for v in result["baseline"]["totals_by_currency"].values() for b in v]
    what_if = [b["net_gap"] for v in result["scenario"]["totals_by_currency"].values() for b in v]
    assert base != what_if


def test_scenario_requires_a_shift(client, support_headers, loaded):
    r = client.post("/api/scenario/run", json={"run_date": str(loaded)}, headers=support_headers)
    assert r.status_code == 422


def test_scenario_respects_location_scope(client, london_headers, loaded):
    body = {"run_date": str(loaded), "location": "Paris", "asset_shift": {"value": 1, "unit": "months", "direction": "later"}}
    assert client.post("/api/scenario/run", json=body, headers=london_headers).status_code == 403


def test_analytics_and_exports(client, support_headers, loaded):
    assert client.get("/api/analytics/exit-trends", headers=support_headers).json()["points"]
    assert client.get("/api/analytics/anomalies", headers=support_headers).status_code == 200
    r = client.get("/api/export/ladder", params={"run_date": loaded, "format": "pdf", "view": "ai"}, headers=support_headers)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    r = client.get("/api/export/transactions", params={"run_date": loaded, "bucket": "1-3M"}, headers=support_headers)
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_retrain_model(client, support_headers, loaded):
    r = client.post("/api/ml/train", headers=support_headers)
    assert r.status_code == 200, r.text
    assert all(m["available"] and m["metrics"]["roc_auc"] > 0 for m in r.json())
