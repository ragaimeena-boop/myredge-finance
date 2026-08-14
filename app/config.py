import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    def __init__(self):
        self._simplefin_access_url: str | None = None
        self._database_url: str | None = None
        self._timezone: str | None = None
        self._port: int | None = None
        self._host: str | None = None
        self._initial_sync_days: int | None = None

    @property
    def SIMPLEFIN_ACCESS_URL(self) -> str:
        if self._simplefin_access_url is not None:
            return self._simplefin_access_url
        load_dotenv(override=True)
        return os.getenv("SIMPLEFIN_ACCESS_URL", "").strip()

    @SIMPLEFIN_ACCESS_URL.setter
    def SIMPLEFIN_ACCESS_URL(self, value: str):
        self._simplefin_access_url = value

    @property
    def DATABASE_URL(self) -> str:
        if self._database_url is not None:
            return self._database_url
        return os.getenv("DATABASE_URL", "sqlite:///./data/finance.db")

    @DATABASE_URL.setter
    def DATABASE_URL(self, value: str):
        self._database_url = value

    @property
    def TIMEZONE(self) -> str:
        if self._timezone is not None:
            return self._timezone
        return os.getenv("TIMEZONE", "America/New_York")

    @TIMEZONE.setter
    def TIMEZONE(self, value: str):
        self._timezone = value

    @property
    def PORT(self) -> int:
        if self._port is not None:
            return self._port
        return int(os.getenv("PORT", "8585"))

    @PORT.setter
    def PORT(self, value: int):
        self._port = value

    @property
    def HOST(self) -> str:
        if self._host is not None:
            return self._host
        return os.getenv("HOST", "0.0.0.0")

    @HOST.setter
    def HOST(self, value: str):
        self._host = value

    @property
    def INITIAL_SYNC_DAYS(self) -> int:
        if self._initial_sync_days is not None:
            return self._initial_sync_days
        return int(os.getenv("INITIAL_SYNC_DAYS", "90"))

    @INITIAL_SYNC_DAYS.setter
    def INITIAL_SYNC_DAYS(self, value: int):
        self._initial_sync_days = value

    @property
    def db_path(self) -> Path:
        """Extract path object from sqlite DATABASE_URL."""
        db_url = self.DATABASE_URL
        if "sqlite:///" in db_url:
            raw_path = db_url.split("sqlite:///")[-1]
            p = Path(raw_path)
            if not p.is_absolute():
                p = (BASE_DIR / p).resolve()
            return p
        return (BASE_DIR / "data" / "finance.db").resolve()

settings = Settings()
