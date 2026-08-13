import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    SIMPLEFIN_ACCESS_URL: str = os.getenv("SIMPLEFIN_ACCESS_URL", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/finance.db")
    TIMEZONE: str = os.getenv("TIMEZONE", "America/New_York")
    PORT: int = int(os.getenv("PORT", "8585"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    INITIAL_SYNC_DAYS: int = int(os.getenv("INITIAL_SYNC_DAYS", "90"))

    @property
    def db_path(self) -> Path:
        """Extract path object from sqlite DATABASE_URL."""
        if self.DATABASE_URL.startswith("sqlite:///"):
            raw_path = self.DATABASE_URL.replace("sqlite:///", "")
            return (BASE_DIR / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path)
        return BASE_DIR / "data" / "finance.db"

settings = Settings()
