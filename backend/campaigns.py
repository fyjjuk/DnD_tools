"""Helpers de campanas: CRUD, membresias y sesiones de campana."""
import datetime
import re
import secrets
import sqlite3

from backend.auth import ApiError, ensure_user_session


CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def slugify(name: str) -> str:
    """Minusculas, ascii-ish, solo [a-z0-9_]. Fallback 'user' si vacio."""
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "user"


def _random_code(n: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(n))


def generate_session_code(db) -> str:
    """Codigo 6 chars unico en sessions.code (mismo alfabeto que Fase 1)."""
    while True:
        code = _random_code(6)
        if not db.execute("SELECT 1 FROM sessions WHERE code=?", (code,)).fetchone():
            return code


def generate_campaign_join_code(db) -> str:
    """Codigo 6 chars unico en campaigns.join_code."""
    while True:
        code = _random_code(6)
        if not db.execute("SELECT 1 FROM campaigns WHERE join_code=?", (code,)).fetchone():
            return code


def create_campaign(db, user_id: int, name: str, join_code=None):
    """Crea campana + membership(role=dm) para el user. Devuelve campaign_row."""
    if join_code:
        join_code = join_code.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{6}", join_code):
            raise ApiError(400, "join_code invalido", "INVALID_INPUT")
        taken = db.execute(
            "SELECT 1 FROM campaigns WHERE join_code=?", (join_code,)
        ).fetchone()
        if taken:
            raise ApiError(409, "join_code ya en uso", "JOIN_CODE_TAKEN")
    else:
        join_code = generate_campaign_join_code(db)

    now = _now()
    cur = db.execute(
        "INSERT INTO campaigns (name, dm_user_id, join_code, status, created_at) "
        "VALUES (?,?,?,?,?)",
        (name, user_id, join_code, "active", now),
    )
    cid = cur.lastrowid
    db.execute(
        "INSERT OR IGNORE INTO campaign_members (campaign_id, user_id, role, joined_at) "
        "VALUES (?,?,?,?)",
        (cid, user_id, "dm", now),
    )
    return db.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()


def list_campaigns_for_user(db, user_id: int):
    """Devuelve filas enriquecidas con role y n_sessions."""
    rows = db.execute(
        """
        SELECT c.*, c.join_code AS join_code, m.role AS role,
               (SELECT COUNT(*) FROM sessions s WHERE s.campaign_id = c.id) AS n_sessions,
               (SELECT COUNT(*) FROM sessions s
                WHERE s.campaign_id = c.id AND s.status='active') AS n_sessions_active
        FROM campaigns c
        JOIN campaign_members m ON m.campaign_id = c.id
        WHERE m.user_id = ?
        ORDER BY c.id DESC
        """,
        (user_id,),
    ).fetchall()
    return rows


def get_campaign(db, campaign_id: int):
    return db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()


def add_member(db, campaign_id: int, user_id: int, role: str) -> bool:
    """Idempotente. True si inserto fila nueva, False si ya existia."""
    now = _now()
    try:
        cur = db.execute(
            "INSERT INTO campaign_members (campaign_id, user_id, role, joined_at) "
            "VALUES (?,?,?,?)",
            (campaign_id, user_id, role, now),
        )
        return cur.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def list_members(db, campaign_id: int):
    return db.execute(
        """
        SELECT u.id AS user_id, u.username, u.display_name, m.role, m.joined_at
        FROM campaign_members m
        JOIN users u ON u.id = m.user_id
        WHERE m.campaign_id = ?
        ORDER BY m.role = 'dm' DESC, m.id ASC
        """,
        (campaign_id,),
    ).fetchall()


def create_session_in_campaign(db, campaign_id: int, dm_user_id: int):
    """Crea sesion activa para la campana.

    Fase 1 solo soporta UNA sesion activa global (WebSocket y /dm legacy
    asumen fetch_active_session()). Por eso rechazamos si existe cualquier
    sesion activa (no solo en esta campana). Codigo de error sigue el
    contrato: CAMPAIGN_HAS_ACTIVE_SESSION.
    """
    campaign = get_campaign(db, campaign_id)
    if campaign is None:
        raise ApiError(404, "campaign not found", "NOT_FOUND")
    if campaign["status"] == "archived":
        raise ApiError(400, "campaign archived", "INVALID_INPUT")
    now = _now()
    db.execute(
        "UPDATE sessions SET status='closed', closed_at=? WHERE status='active'",
        (now,),
    )

    code = generate_session_code(db)
    # L1: Las sesiones de campana no generan tokens basura en user_sessions.
    # El campo dm_token se almacena como "" (NOT NULL en SQLite) y la autorizacion
    # se realiza directamente con el X-User-Token del usuario DM / superusuario.
    cur = db.execute(
        "INSERT INTO sessions "
        "(code, status, round, turn_combatant_id, dm_token, created_at, "
        " campaign_id, created_by_user_id) "
        "VALUES (?, 'active', 1, NULL, '', ?, ?, ?)",
        (code, now, campaign_id, dm_user_id),
    )
    sid = cur.lastrowid
    return db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()


def list_sessions_in_campaign(db, campaign_id: int):
    return db.execute(
        "SELECT id, code, status, round, created_at, closed_at, campaign_id "
        "FROM sessions WHERE campaign_id=? ORDER BY id DESC",
        (campaign_id,),
    ).fetchall()
