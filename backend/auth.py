"""Helpers de autenticacion: passwords (scrypt), tokens, user_sessions."""
import datetime
import hashlib
import hmac
import os
import secrets


class ApiError(Exception):
    """Error de API con cuerpo {error, code}. Se maneja con un handler."""

    def __init__(self, status_code: int, error: str, code: str):
        self.status_code = status_code
        self.error = error
        self.code = code
        super().__init__(error)


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _plus_days(iso_ts: str, days: int = 30) -> str:
    d = datetime.datetime.fromisoformat(iso_ts)
    return (d + datetime.timedelta(days=days)).isoformat(timespec="seconds")


# ---------------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    """Devuelve scrypt$n=16384,r=8,p=1$<salt_hex>$<hash_hex>."""
    salt = os.urandom(16)
    h = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=64
    )
    return f"scrypt$n=16384,r=8,p=1${salt.hex()}${h.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        parts = encoded.split("$")
        if len(parts) != 4 or parts[0] != "scrypt":
            return False
        params = dict(kv.split("=") for kv in parts[1].split(","))
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(params["n"]),
            r=int(params["r"]),
            p=int(params["p"]),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


# ---------------------------------------------------------------- tokens

def new_user_token() -> str:
    return secrets.token_urlsafe(32)


def create_user_session(db, user_id: int):
    """Crea user_sessions y devuelve (token, expires_at)."""
    token = new_user_token()
    now = _now()
    expires = _plus_days(now, 30)
    db.execute(
        "INSERT INTO user_sessions (user_id, token, created_at, expires_at) "
        "VALUES (?,?,?,?)",
        (user_id, token, now, expires),
    )
    return token, expires


def ensure_user_session(db, user_id: int, token: str, created_at: str) -> None:
    """Idempotente: inserta la sesion solo si el token no existe."""
    if db.execute("SELECT 1 FROM user_sessions WHERE token=?", (token,)).fetchone():
        return
    db.execute(
        "INSERT INTO user_sessions (user_id, token, created_at, expires_at) "
        "VALUES (?,?,?,?)",
        (user_id, token, created_at, _plus_days(created_at, 30)),
    )


def ensure_dm_user(db) -> int:
    """Devuelve el id del user 'dm', creandolo si no existe."""
    row = db.execute("SELECT id FROM users WHERE username='dm'").fetchone()
    if row is not None:
        return row["id"]
    import config
    password = getattr(config, "DM_PASSWORD", "") or ""
    pw_hash = hash_password(password) if password else None
    cur = db.execute(
        "INSERT INTO users (username, display_name, password_hash, is_guest, created_at) "
        "VALUES ('dm', 'DM', ?, 0, ?)",
        (pw_hash, _now()),
    )
    return cur.lastrowid


# ---------------------------------------------------------------- requiere*

def require_user(db, token):
    """Devuelve fila de users o lanza 401 UNAUTHENTICATED."""
    if not token:
        raise ApiError(401, "unauthenticated", "UNAUTHENTICATED")
    row = db.execute(
        "SELECT u.* FROM users u JOIN user_sessions us ON us.user_id=u.id "
        "WHERE us.token=? AND us.revoked_at IS NULL AND us.expires_at > ?",
        (token, _now()),
    ).fetchone()
    if row is None:
        raise ApiError(401, "unauthenticated", "UNAUTHENTICATED")
    return row


def require_user_campaign_member(db, token, campaign_id: int):
    """Devuelve (user_row, member_row) o lanza 404/403."""
    user = require_user(db, token)
    c = db.execute("SELECT 1 FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    if c is None:
        raise ApiError(404, "campaign not found", "NOT_FOUND")
    m = db.execute(
        "SELECT * FROM campaign_members WHERE campaign_id=? AND user_id=?",
        (campaign_id, user["id"]),
    ).fetchone()
    if m is None:
        raise ApiError(403, "forbidden", "FORBIDDEN")
    return user, m


def require_user_campaign_dm(db, token, campaign_id: int):
    """Devuelve (user_row, member_row) o lanza 404/403 (403 si no es dm)."""
    user = require_user(db, token)
    c = db.execute("SELECT 1 FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    if c is None:
        raise ApiError(404, "campaign not found", "NOT_FOUND")
    m = db.execute(
        "SELECT * FROM campaign_members WHERE campaign_id=? AND user_id=?",
        (campaign_id, user["id"]),
    ).fetchone()
    if m is None or m["role"] != "dm":
        raise ApiError(403, "forbidden", "FORBIDDEN")
    return user, m
