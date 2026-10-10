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

## Setup (run it locally)

The commands below are for **Windows PowerShell**. On macOS/Linux, use `/` instead of `\` and
`.venv/bin/python` instead of `.venv\Scripts\python`.

### 0. Prerequisites (install once)

| Tool | Version | Download | Check with |
|------|---------|----------|------------|
| Git | any recent | https://git-scm.com/download/win | `git --version` |
| Python | 3.12 (3.11 minimum) | https://www.python.org/downloads/ (tick **"Add python.exe to PATH"**) | `python --version` |
| Node.js | 20 or newer (LTS) | https://nodejs.org/ | `node --version` |
| PostgreSQL + pgAdmin 4 | 15 or newer | see below | pgAdmin opens and connects |

If a version check fails right after installing, close and reopen PowerShell.

#### Installing PostgreSQL and pgAdmin (one installer)

Skip this if PostgreSQL and pgAdmin are already installed. Check the Start menu for "pgAdmin 4".

1. Go to https://www.postgresql.org/download/windows/ → **Download the installer** (EDB). Choose the latest
   version (17.x) for **Windows x86-64**.
2. Run the installer and keep the defaults on each screen:
   - **Components:** leave all ticked: *PostgreSQL Server*, *pgAdmin 4*, *Command Line Tools*.
     *Stack Builder* is not needed.
   - **Data directory:** default.
   - **Password:** choose a password for the `postgres` user and **write it down**. You need it in step 3.
     It's simplest to avoid `#`, `@`, `:`, `/` and `%`. If you do use them, step 3 shows how to encode them.
   - **Port:** `5432` (default). If the installer suggests 5433, another PostgreSQL is already installed;
     remember that port for step 3.
   - **Locale:** default.
3. Click **Finish**. Untick "Launch Stack Builder" if it asks.
4. PostgreSQL now runs automatically as a Windows service (`postgresql-x64-17`), including after restarts.
5. Open **pgAdmin 4** from the Start menu. The first time, it may ask you to set a pgAdmin master password;
   that only protects pgAdmin's saved passwords, so choose anything. Click **Servers → PostgreSQL 17** and enter
   the `postgres` password from step 2. If the server expands and shows **Databases**, the install is working.

### 1. Clone the repo

```powershell
git clone https://github.com/HEsanthosh/BNP-MUM-Team-04.git
cd BNP-MUM-Team-04
```

### 2. Create the database in pgAdmin

1. Open pgAdmin 4 → **Servers → PostgreSQL 17** and enter the `postgres` user's password (the one set during installation).
2. Right-click **Databases** → **Create → Database…**
3. Set **Database** to `liquidplus` and **Owner** to `postgres`, then click **Save**.

Don't create any tables yourself; step 5 does that.

### 3. Backend configuration

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
copy seed_users.example.json seed_users.json
```

Edit **`backend\.env`**:

- `DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/liquidplus`
  - If the password contains special characters, encode them: `#` → `%23`, `@` → `%40`, `:` → `%3A`,
    `/` → `%2F`, `%` → `%25`. This prints the encoded form for you:
    `python -c "import urllib.parse, getpass; print(urllib.parse.quote(getpass.getpass('Password: '), safe=''))"`
  - If pgAdmin shows a port other than 5432 (Server → Properties → Connection), use that port.
- `JWT_SECRET_KEY=`: paste the output of
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`

Edit **`backend\seed_users.json`**: replace every `<at least 8 characters>` with a password. These are the
logins for the web app (not the database).

`.env` and `seed_users.json` are git-ignored. Never commit them.

### 4. Check the database connection

```powershell
.venv\Scripts\python -c "from app.db import check_db_connection; print(check_db_connection())"
```

Expected: `(True, None)`. Anything else means `DATABASE_URL` is wrong (see Troubleshooting).

### 5. Create tables and users, then load the sample data

```powershell
.venv\Scripts\python scripts\init_db.py
.venv\Scripts\python scripts\load_data.py
```

Expected output from `load_data.py`:

```
historical_log - 10102026.xlsx: 16179/16186 accepted, 7 rejected ...
asset_book - 10102026.xlsx: 753/755 accepted, 2 rejected ...
    753 live asset transactions scored by the behavioral model
liability_book - 10102026.xlsx: 1103/1104 accepted, 1 rejected ...
    1103 live liability transactions scored by the behavioral model
```

The 10 rejected rows are intentionally invalid rows in the dataset.

### 6. Start the backend (keep this terminal open)

```powershell
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Check http://localhost:8000/health/db; it should show `"database":"up"`. API docs are at http://localhost:8000/docs.

### 7. Start the frontend (second terminal)

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

Open **http://localhost:5173** and log in with a user from `backend\seed_users.json`:

- `support_user`: all locations, plus uploads and model retraining (**Data and models** page)
- `hk_user`, `ny_user`, `ldn_user`, `sg_user`, `paris_user`: only their own location

### Next time

You only need step 6 and `npm run dev` from step 7. The data stays in the database.

### Troubleshooting

| Problem | Fix |
|---------|-----|
| `password authentication failed for user "postgres"` | Wrong password in `DATABASE_URL`, or special characters not encoded (step 3). |
| `database "liquidplus" does not exist` | Create it in pgAdmin (step 2). |
| `Connection refused` on port 5432 | PostgreSQL service isn't running: Windows Services → `postgresql-x64-NN` → Start. |
| `Field required ... jwt_secret_key` or `database_url` | `backend\.env` is missing or still has the placeholders. |
| `error while attempting to bind on address ... 8000` | Port 8000 is busy: start with `--port 8090` and set `VITE_PROXY_TARGET=http://127.0.0.1:8090` in `frontend\.env`. |
| Frontend loads but every page shows an error | The backend isn't running, or `VITE_PROXY_TARGET` points to the wrong port. |
| Login says "Invalid username or password" | Use the passwords from `seed_users.json`; if you changed them, re-run `scripts\init_db.py`. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | You don't need to activate; call `.venv\Scripts\python` directly as shown above. |
| `InconsistentVersionWarning` from scikit-learn | Install exactly from `requirements.txt` (scikit-learn 1.9.1). |
| `python` opens the Microsoft Store | Install Python from python.org and tick "Add python.exe to PATH". |

### Tests (optional)

Create a second, empty database `liquidplus_test` in pgAdmin (the tests drop and recreate its tables), then:

```powershell
cd backend
$env:TEST_DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@localhost:5432/liquidplus_test"
.venv\Scripts\python -m pytest -q          # 48 tests

cd ..\frontend
npm test -- --no-file-parallelism            # 15 tests
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
