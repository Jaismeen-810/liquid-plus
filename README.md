# Liquid+: liquidity gap forecasting

Full-stack prototype for the BNP Paribas "Liquid+" use case: deterministic and AI-adjusted (behavioral)
maturity gap ladders per currency and location, with drill-down, what-if scenarios, recommendations,
behavioral analytics and Excel/PDF export.

| Layer    | Tech |
|----------|------|
| Frontend | React 18, Vite, Recharts (`frontend/`) |
| Backend  | Python 3.12, FastAPI, SQLAlchemy (`backend/`) |
| Database | PostgreSQL (local or Supabase) |
| ML       | scikit-learn logistic regression, one model for assets and one for liabilities (`backend/ml_models/`) |

## Project layout

```
backend/
  app/
    main.py            FastAPI app, routers, logging, error handling
    config.py          settings from .env (no hard-coded config or secrets)
    constants.py       enums, allowed values, ID patterns, buckets
    db.py, models.py   engine/session and the 8 tables
    schemas.py         request/response models
    deps.py            auth + location scoping (the two user types)
    security.py        bcrypt passwords, JWT tokens
    routers/           auth, ingest, ladder, ml, reports (what-if, recommendations, analytics, export), health
    services/          validation, ingestion, cashflow, ladder, scenario, recommendation, analytics, export, audit
    ml/
      features.py      feature engineering (ported from the ML project; must match the saved models)
      behavior.py      load models, predict, adjusted maturity, per-transaction explanation
      train.py         retrain both models from the historical log
  ml_models/           asset_model.joblib, liability_model.joblib + thresholds (from the ML project)
  data/                sample input files (run date 10-10-2026)
  scripts/             init_db.py, load_data.py, train_model.py, seed_users.py
  tests/               pytest: validation, cashflow, auth, API end-to-end
frontend/
  src/pages/           Ladder (deterministic + AI), Compare, WhatIf, Recommendations, Analytics, Data, Login
  src/components/      chart, tables, drill-down, rationale panel
```

## Users and access

Two roles:

| Role      | Sees | Can |
|-----------|------|-----|
| `BRANCH`  | only their assigned location (Hong Kong, New York, London, Singapore or Paris); the location filter is locked | view ladders, drill-down, what-if, recommendations, analytics, export |
| `SUPPORT` | all locations, or any single one | everything above, plus upload files, retrain the model, re-score a run date |

Location scoping is enforced on the server for every endpoint (`app/deps.py`). A branch user asking for another
location gets `403` and an `access_denied` audit entry. Users are defined in `backend/seed_users.json`
(not committed; see `seed_users.example.json`).

## Data injection flow

```
 CSV/XLSX ──► read ──► validate every row ──► store accepted rows ──► score with behavioral model
 (UI upload        (all rules from the      (+ rejected rows with      (live books only; history
  or load_data.py)  problem statement)       row/column/reason)          refreshes the calibration)
```

1. **Historical log** (`historical_log*.xlsx`): upserted by `Transaction_ID`. Used to calibrate how many days
   before maturity customers typically exit, and to retrain the models.
2. **Asset book** and **liability book** (`asset_book - DDMMYYYY.xlsx`, `liability_book - DDMMYYYY.xlsx`): the run
   date comes from the file name. Uploading a book replaces that book for that run date (daily refresh). Interest
   (simple, actual/365, paid at maturity) and maturity cash flow are computed on load. Every live transaction is
   then scored and its adjusted maturity stored in `predictions`.

Rows that break a rule are rejected and reported with row number, column and reason. The rest of the file is
still loaded. A file with missing columns or an unsupported type is rejected as a whole. Scoring never undoes an
upload: if the model is unavailable, the upload succeeds and scoring runs on the next AI-ladder request.

## Behavioral model

Taken from the ML project: two scikit-learn pipelines (scaling + one-hot encoding + logistic regression) with
tuned thresholds (asset 0.43, liability 0.62).

- `p_early`: model probability that the loan is pre-closed or the deposit withdrawn early.
- `expected shift`: median number of days before maturity that similar historical contracts closed early
  (by type + product + segment, falling back to segment, type, then all history).
- **Adjusted maturity** = contractual maturity − `p_early` × expected shift, never before the run date.
- **Rationale**: for each transaction, how much each factor (tenor, market rate, interest-rate difference,
  amount, client rating, product/segment, location/currency, booking timing) moves the probability compared
  with an average transaction.
- **Retrain**: `POST /api/ml/train` or `python scripts/train_model.py` refits both models on the current
  historical log (same search and threshold tuning as the ML project), overwrites `ml_models/`, and re-scores
  every run date.

## Setup

Prerequisites: Python 3.12, Node 20+, PostgreSQL 15+ (local), or a Supabase project.

### 1. Database

**Local (recommended for development).** Create an empty database:

```bash
createdb -U postgres liquidplus
```

**Supabase.** Use the *Session pooler* connection string (Project Settings → Database → Connect). The direct
`db.<ref>.supabase.co` host is IPv6-only and often unreachable from home networks.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env             # then set DATABASE_URL and JWT_SECRET_KEY
copy seed_users.example.json seed_users.json   # then set a password for each user

python scripts/init_db.py          # create tables + users
python scripts/load_data.py        # load data/ : historical log, asset book, liability book
uvicorn app.main:app --reload      # http://localhost:8000/docs
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173 (proxies /api to localhost:8000)
```

Change the backend address with `VITE_PROXY_TARGET` in `frontend/.env`.

### Tests

```bash
cd backend
set TEST_DATABASE_URL=postgresql://postgres:<password>@localhost:5432/liquidplus_test   # an empty, throwaway database
pytest                             # 48 tests

cd frontend
npm test                           # 15 tests
```

## API overview

| Method | Path | Who |
|--------|------|-----|
| GET  | `/health`, `/health/db` | anyone |
| POST | `/api/auth/login`, GET `/api/auth/me` | anyone / logged in |
| POST | `/api/ingest/{historical,assets,liabilities}` | support |
| GET  | `/api/ingest/run-dates`, `/api/ingest/batches`, `/api/ingest/batches/{id}/errors` | logged in / support |
| GET  | `/api/ladder/{deterministic,ai}`, `/api/ladder/{view}/transactions`, `/api/ladder/compare` | logged in |
| GET  | `/api/ml/models`, `/api/ml/predictions/{transaction_id}` | logged in |
| POST | `/api/ml/train`, `/api/ml/predict` | support |
| POST | `/api/scenario/run` | logged in |
| GET  | `/api/recommendations`, `/api/analytics/{exit-trends,anomalies}` | logged in |
| GET  | `/api/export/{ladder,transactions,recommendations}` | logged in |

All data endpoints accept `run_date` (default: latest), `location` and `currency`, and are scoped to the
user's allowed locations.

## Assumptions

- Buckets are measured from the run date in calendar months: 0–1M, 1–3M, 3–12M, 1–5Y, >5Y. A maturity on a
  boundary falls in the earlier bucket. Deals that matured before the run date are excluded.
- Gaps are per currency; amounts are never converted between currencies.
- In the AI and what-if views, interest is recomputed to the adjusted or shifted maturity date.
- What-if shifts move contractual maturities (never before the run date) and do not use the model.
- Recommendations are generated for buckets where |AI-adjusted gap| ≥ `MATERIALITY_THRESHOLD_PCT` (10%) of
  the larger side, and are recomputed on request (no stale cache).
- Anomalies: a day's deposit outflow ≥ `ANOMALY_MULTIPLIER` × the previous `ANOMALY_WINDOW_DAYS`-day average.
- Logs: `backend/logs/app.log` (operations) and `backend/logs/audit.log` (logins, uploads, exports, denied
  access). The audit trail is also stored in the `audit_log` table.
