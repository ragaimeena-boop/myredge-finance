import pytest
from fastapi.testclient import TestClient
import pyotp
from app.main import app
from app.database import get_connection, init_db
from app.auth import (
    hash_password,
    verify_password,
    create_user,
    get_user_by_username,
    create_session,
    validate_session,
    revoke_session,
    generate_totp_secret,
    verify_totp_code,
    get_user_settings,
    update_session_timeout
)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Set up temporary SQLite database for testing auth module."""
    db_file = tmp_path / "test_auth.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    return db_file

def test_password_hashing():
    raw_pass = "SecureDocPass123!"
    hashed = hash_password(raw_pass)
    assert hashed != raw_pass
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPass", hashed) is False

def test_totp_verification():
    secret = generate_totp_secret()
    totp = pyotp.TOTP(secret)
    current_code = totp.now()
    assert verify_totp_code(secret, current_code) is True
    assert verify_totp_code(secret, "000000") is False

def test_create_and_validate_session():
    conn = get_connection()
    try:
        user = create_user("physician_admin", "Password123!", conn=conn)
        token = create_session(user["id"], conn=conn)
        
        valid_user, is_timed_out = validate_session(token, conn=conn)
        assert is_timed_out is False
        assert valid_user is not None
        assert valid_user["username"] == "physician_admin"

        revoke_session(token, conn=conn)
        invalid_user, is_timed_out = validate_session(token, conn=conn)
        assert invalid_user is None
    finally:
        conn.close()

def test_auth_routes_and_middleware():
    client = TestClient(app)
    
    # 1. Unconfigured initial state (0 users in DB): GET / returns 200 OK
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 200

    # 2. Test Setup Admin page
    res_setup_page = client.get("/setup-admin")
    assert res_setup_page.status_code == 200
    assert "Create Master Account" in res_setup_page.text

    # 3. Post Setup Admin to create initial master account
    res_setup_post = client.post("/api/setup-admin", data={
        "username": "dr_ragaimeena",
        "password": "MasterPassword123!",
        "confirm_password": "MasterPassword123!"
    }, follow_redirects=False)
    assert res_setup_post.status_code == 303
    assert res_setup_post.headers["location"] == "/"
    assert "myredge_session" in res_setup_post.cookies

    # 4. Authenticated access to / with client session
    res_auth = client.get("/")
    assert res_auth.status_code == 200

    # 5. Test Settings page access
    res_settings = client.get("/settings")
    assert res_settings.status_code == 200
    assert "Settings" in res_settings.text

    # 6. Unauthenticated access on a new client redirects to /login (because user_count > 0!)
    unauth_client = TestClient(app)
    res_unauth = unauth_client.get("/", follow_redirects=False)
    assert res_unauth.status_code == 303
    assert res_unauth.headers["location"] == "/login"

    # 7. Test Logout
    res_logout = client.post("/api/logout", follow_redirects=False)
    assert res_logout.status_code == 303
    assert "/login?logged_out=1" in res_logout.headers["location"]
