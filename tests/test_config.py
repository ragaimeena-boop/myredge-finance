import pytest
from app.config import Settings

def test_dynamic_env_reload(tmp_path, monkeypatch):
    """Verify that Settings dynamically reloads SIMPLEFIN_ACCESS_URL from .env or env vars."""
    settings = Settings()
    
    # Test setting via attribute / monkeypatch setter
    settings.SIMPLEFIN_ACCESS_URL = "https://user:pass@bridge.simplefin.org/simplefin/accounts"
    assert settings.SIMPLEFIN_ACCESS_URL == "https://user:pass@bridge.simplefin.org/simplefin/accounts"
    
    # Test dynamic lookup from environment when not explicitly set on instance
    settings._simplefin_access_url = None
    monkeypatch.setattr("app.config.load_dotenv", lambda **k: None)
    monkeypatch.setenv("SIMPLEFIN_ACCESS_URL", "https://test:secret@bridge.simplefin.org/simplefin/accounts")
    assert settings.SIMPLEFIN_ACCESS_URL == "https://test:secret@bridge.simplefin.org/simplefin/accounts"
