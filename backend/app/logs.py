import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from app.config import get_settings

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_audit = logging.getLogger("audit")


def setup_logging() -> None:
    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(settings.log_level)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(FORMAT))
        app_file = RotatingFileHandler(settings.log_dir / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        app_file.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(console)
        root.addHandler(app_file)

    if not _audit.handlers:
        audit_file = RotatingFileHandler(settings.log_dir / "audit.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        audit_file.setFormatter(logging.Formatter("%(message)s"))
        _audit.addHandler(audit_file)
        _audit.setLevel(logging.INFO)
        _audit.propagate = False


def audit_log(username: str | None, action: str, **detail) -> None:
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "user": username, "action": action, **detail}
    _audit.info(json.dumps(entry, default=str))
