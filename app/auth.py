import os
import secrets
import io
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import pyotp
import qrcode
import qrcode.image.svg
import bcrypt

from app.database import get_connection
from app.utils import current_eastern_time

def hash_password(password: str) -> str:
    """Hash plain-text password securely with bcrypt (capped at 72 bytes)."""
    clean_pass = (password or "")[:72].encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(clean_pass, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain-text password against bcrypt hash."""
    if not hashed_password or not plain_password:
        return False
    try:
        clean_pass = plain_password[:72].encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(clean_pass, hashed_bytes)
    except Exception:
        return False

# --- TOTP 2FA Helpers ---

def generate_totp_secret() -> str:
    """Generate a random Base32 TOTP secret key for Google Authenticator / Authy."""
    return pyotp.random_base32()

def get_totp_uri(secret: str, username: str) -> str:
    """Generate otpauth:// URI for authenticator apps."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name="MYREDGE Finance")

def get_totp_qr_data_url(secret: str, username: str) -> str:
    """Generate inline SVG data URL for QR code display in Settings."""
    uri = get_totp_uri(secret, username)
    factory = qrcode.image.svg.SvgImage
    img = qrcode.make(uri, image_factory=factory)
    stream = io.BytesIO()
    img.save(stream)
    svg_bytes = stream.getvalue()
    b64_svg = base64.b64encode(svg_bytes).decode('utf-8')
    return f"data:image/svg+xml;base64,{b64_svg}"

def verify_totp_code(secret: str, code: str) -> bool:
    """Verify 6-digit TOTP code with 30-second window tolerance."""
    if not secret or not code:
        return False
    clean_code = code.strip().replace(" ", "")
    if not clean_code.isdigit():
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(clean_code, valid_window=1)

# --- User Management ---

def get_user_count(conn=None) -> int:
    """Return total number of registered users."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users;")
        return cursor.fetchone()[0]
    finally:
        if close_conn:
            conn.close()

def create_user(username: str, password: str, conn=None) -> Dict[str, Any]:
    """Create initial admin master account."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        now_str = current_eastern_time().isoformat()
        pass_hash = hash_password(password)
        totp_sec = generate_totp_secret()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO users (username, password_hash, totp_secret, is_totp_enabled, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?);
        """, (username.strip(), pass_hash, totp_sec, now_str, now_str))
        user_id = cursor.lastrowid
        
        # Ensure user_settings row exists
        cursor.execute("SELECT COUNT(*) FROM user_settings;")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO user_settings (session_timeout_minutes, created_at, updated_at) VALUES (30, ?, ?);", (now_str, now_str))

        conn.commit()
        return get_user_by_id(user_id, conn=conn)
    finally:
        if close_conn:
            conn.close()

def get_user_by_username(username: str, conn=None) -> Optional[Dict[str, Any]]:
    """Retrieve user dictionary by username."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?);", (username.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        if close_conn:
            conn.close()

def get_user_by_id(user_id: int, conn=None) -> Optional[Dict[str, Any]]:
    """Retrieve user dictionary by ID."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        if close_conn:
            conn.close()

def update_user_credentials(user_id: int, new_username: Optional[str] = None, new_password: Optional[str] = None, conn=None):
    """Update user's master username or password."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        now_str = current_eastern_time().isoformat()
        cursor = conn.cursor()
        if new_username and new_username.strip():
            cursor.execute("UPDATE users SET username = ?, updated_at = ? WHERE id = ?;", (new_username.strip(), now_str, user_id))
        if new_password and new_password.strip():
            pass_hash = hash_password(new_password.strip())
            cursor.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?;", (pass_hash, now_str, user_id))
        conn.commit()
    finally:
        if close_conn:
            conn.close()

def update_user_totp_secret(user_id: int, secret: str, is_enabled: bool, conn=None):
    """Update 2FA TOTP secret and enabled status."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        now_str = current_eastern_time().isoformat()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE users 
        SET totp_secret = ?, is_totp_enabled = ?, updated_at = ?
        WHERE id = ?;
        """, (secret, 1 if is_enabled else 0, now_str, user_id))
        conn.commit()
    finally:
        if close_conn:
            conn.close()

# --- User Settings & Session Timeout ---

def get_user_settings(conn=None) -> Dict[str, Any]:
    """Get global user settings (e.g. session timeout)."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_settings ORDER BY id ASC LIMIT 1;")
        row = cursor.fetchone()
        if row:
            return dict(row)
        now_str = current_eastern_time().isoformat()
        cursor.execute("INSERT INTO user_settings (session_timeout_minutes, created_at, updated_at) VALUES (30, ?, ?);", (now_str, now_str))
        conn.commit()
        return {"session_timeout_minutes": 30}
    finally:
        if close_conn:
            conn.close()

def update_session_timeout(timeout_minutes: int, conn=None):
    """Update session inactivity timeout minutes."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        now_str = current_eastern_time().isoformat()
        cursor = conn.cursor()
        cursor.execute("UPDATE user_settings SET session_timeout_minutes = ?, updated_at = ?;", (timeout_minutes, now_str))
        conn.commit()
    finally:
        if close_conn:
            conn.close()

# --- Session Token Management & Inactivity Timeout ---

def create_session(user_id: int, conn=None) -> str:
    """Create a new authenticated session token."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        token = secrets.token_hex(32)
        now = current_eastern_time()
        now_str = now.isoformat()
        settings_data = get_user_settings(conn=conn)
        timeout_mins = settings_data.get("session_timeout_minutes", 30)
        expires_at = (now + timedelta(days=7)).isoformat()

        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO sessions (token, user_id, created_at, last_activity, expires_at)
        VALUES (?, ?, ?, ?, ?);
        """, (token, user_id, now_str, now_str, expires_at))
        conn.commit()
        return token
    finally:
        if close_conn:
            conn.close()

def validate_session(token: str, conn=None) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Validate session token against inactivity timeout.
    Returns tuple: (user_dict, is_timed_out).
    """
    if not token:
        return None, False
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE token = ?;", (token,))
        row = cursor.fetchone()
        if not row:
            return None, False

        session_data = dict(row)
        now = current_eastern_time()
        
        # Parse last_activity timestamp
        last_act = datetime.fromisoformat(session_data["last_activity"])
        settings_data = get_user_settings(conn=conn)
        timeout_mins = settings_data.get("session_timeout_minutes", 30)

        # Check if inactive beyond configured timeout
        inactive_seconds = (now - last_act).total_seconds()
        if inactive_seconds > (timeout_mins * 60):
            cursor.execute("DELETE FROM sessions WHERE token = ?;", (token,))
            conn.commit()
            return None, True

        # Update last_activity timestamp
        now_str = now.isoformat()
        cursor.execute("UPDATE sessions SET last_activity = ? WHERE token = ?;", (now_str, token))
        conn.commit()

        user = get_user_by_id(session_data["user_id"], conn=conn)
        return user, False
    finally:
        if close_conn:
            conn.close()

def revoke_session(token: str, conn=None):
    """Revoke session token (Logout)."""
    if not token:
        return
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE token = ?;", (token,))
        conn.commit()
    finally:
        if close_conn:
            conn.close()
