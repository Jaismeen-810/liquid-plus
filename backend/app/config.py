from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Liquid+"
    environment: str = "development"
    api_prefix: str = "/api"

    database_url: str
    db_echo: bool = False

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: list[str] = ["http://localhost:5173"]

    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    upload_dir: Path = Path("uploads")
    model_dir: Path = Path("ml_models")
    max_upload_size_mb: int = 20

    day_count_basis: int = 365
    materiality_threshold_pct: float = 10.0
    anomaly_multiplier: float = 2.0
    anomaly_window_days: int = 90
    drilldown_max_page_size: int = 500
    export_max_rows: int = 50_000

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        # Accept plain URLs as copied from Supabase / pgAdmin and point them at the psycopg 3 driver.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @field_validator("log_dir", "upload_dir", "model_dir")
    @classmethod
    def relative_to_backend(cls, path: Path) -> Path:
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
