"""Create the database tables and the predefined users.

    python scripts/init_db.py                      # uses seed_users.json
    python scripts/init_db.py my_users.json
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import init_db  # noqa: E402
from scripts.seed_users import seed  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("users_file", nargs="?", default=os.getenv("SEED_USERS_FILE", "seed_users.json"))
    users_file = Path(parser.parse_args().users_file)

    init_db()
    print("Tables created")
    if users_file.exists():
        seed(users_file)
    else:
        print(f"{users_file} not found: copy seed_users.example.json to seed_users.json, set passwords, and run again")
