import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_connection, init_db
from app.auth import create_user, create_session

@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """Fixture providing a TestClient with pre-authenticated session cookie."""
    db_file = tmp_path / "test_auth_shared.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    
    conn = get_connection()
    try:
        user = create_user("test_admin", "TestPass123!", conn=conn)
        token = create_session(user["id"], conn=conn)
    finally:
        conn.close()

    client = TestClient(app)
    client.cookies.set("myredge_session", token)
    return client
