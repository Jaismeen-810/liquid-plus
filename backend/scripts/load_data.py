"""Load a folder of data files through the same pipeline as the UI upload.

Order: historical log -> asset book -> liability book. Each file is validated, stored, and the live
books are scored by the behavioral model. The run date comes from the file name (DDMMYYYY).

    python scripts/load_data.py                    # loads ./data
    python scripts/load_data.py path/to/folder --user support_user
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.constants import Book, Role  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.errors import AppError  # noqa: E402
from app.logs import setup_logging  # noqa: E402
from app.models import User  # noqa: E402
from app.schemas import CurrentUser  # noqa: E402
from app.services.ingestion import ingest_file  # noqa: E402

ORDER = [(Book.HISTORICAL, "historical"), (Book.ASSET, "asset"), (Book.LIABILITY, "liability")]


def find_files(folder: Path) -> list[tuple[Book, Path]]:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".csv", ".xlsx"})
    return [(book, f) for book, key in ORDER for f in files if f.name.lower().startswith(key)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", default="data")
    parser.add_argument("--user", help="support user recorded as the uploader (default: first support user)")
    args = parser.parse_args()

    setup_logging()
    init_db()
    folder = Path(args.folder)
    files = find_files(folder)
    if not files:
        print(f"No historical_log*, asset_book* or liability_book* files in {folder.resolve()}")
        return 1

    with SessionLocal() as db:
        stmt = select(User).where(User.role == Role.SUPPORT)
        user = db.scalar(stmt.where(User.username == args.user) if args.user else stmt.order_by(User.id))
        if user is None:
            print("No support user found. Run scripts/init_db.py first")
            return 1
        uploader = CurrentUser(id=user.id, username=user.username, role=user.role, location=user.location)

        for book, path in files:
            try:
                batch, predictions = ingest_file(db, book, path.read_bytes(), path.name, uploader)
            except AppError as exc:
                print(f"FAILED {path.name}: {exc.message} {exc.details or ''}")
                return 1
            print(f"{path.name}: {batch.rows_accepted}/{batch.rows_total} accepted, {batch.rows_rejected} rejected "
                  f"(run date {batch.run_date}, {batch.status})")
            if predictions:
                print(f"    {predictions}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
