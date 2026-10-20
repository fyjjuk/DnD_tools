"""Capa SQLite: conexion, contexto de transaccion y esquema."""
import os
import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    code               TEXT NOT NULL UNIQUE,
    status             TEXT NOT NULL DEFAULT 'active',
    round              INTEGER NOT NULL DEFAULT 1,
    turn_combatant_id  INTEGER,
    dm_token           TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    closed_at          TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS combatants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    hp_max      INTEGER NOT NULL,
    hp_current  INTEGER NOT NULL,
    initiative  INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    player_id   INTEGER REFERENCES players(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ts          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    message     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hp_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    combatant_id   INTEGER NOT NULL REFERENCES combatants(id) ON DELETE CASCADE,
    old_hp         INTEGER NOT NULL,
    new_hp         INTEGER NOT NULL,
    ts             TEXT NOT NULL,
    undone         INTEGER NOT NULL DEFAULT 0
);
"""

SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS users (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    username           TEXT NOT NULL UNIQUE,
    display_name       TEXT NOT NULL,
    password_hash      TEXT,
    is_guest           INTEGER NOT NULL DEFAULT 0,
    claimed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at         TEXT NOT NULL,
    last_seen_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_guest ON users(is_guest);

CREATE TABLE IF NOT EXISTS user_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    revoked_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);

CREATE TABLE IF NOT EXISTS campaigns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    dm_user_id    INTEGER NOT NULL REFERENCES users(id),
    join_code     TEXT UNIQUE,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL,
    archived_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_campaigns_dm     ON campaigns(dm_user_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);

CREATE TABLE IF NOT EXISTS campaign_members (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id  INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         TEXT NOT NULL,
    joined_at    TEXT NOT NULL,
    UNIQUE(campaign_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_campaign_members_user ON campaign_members(user_id);

CREATE TABLE IF NOT EXISTS campaign_invites (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id         INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    code                TEXT NOT NULL UNIQUE,
    role                TEXT NOT NULL DEFAULT 'player',
    created_by_user_id  INTEGER NOT NULL REFERENCES users(id),
    max_uses            INTEGER,
    used_count          INTEGER NOT NULL DEFAULT 0,
    expires_at          TEXT,
    revoked_at          TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_campaign_invites_campaign ON campaign_invites(campaign_id);

CREATE TABLE IF NOT EXISTS session_participants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at   TEXT NOT NULL,
    UNIQUE(session_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_session_participants_user ON session_participants(user_id);

CREATE TABLE IF NOT EXISTS characters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id  INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    level        INTEGER,
    class_slug   TEXT,
    race_slug    TEXT,
    dex_mod      INTEGER,
    hp_max       INTEGER,
    data         TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_characters_campaign ON characters(campaign_id);
CREATE INDEX IF NOT EXISTS idx_characters_user     ON characters(user_id);

CREATE TABLE IF NOT EXISTS session_comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    content     TEXT NOT NULL,
    anonymous   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_comments_session ON session_comments(session_id);
"""


def _migrate_v2_columns(conn):
    """Anade columnas nuevas a sessions/combatants (idempotente)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    if "campaign_id" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN campaign_id INTEGER REFERENCES campaigns(id)")
    if "created_by_user_id" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN created_by_user_id INTEGER REFERENCES users(id)")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(combatants)")}
    if "user_id" not in cols:
        conn.execute("ALTER TABLE combatants ADD COLUMN user_id INTEGER REFERENCES users(id)")
    if "character_id" not in cols:
        conn.execute("ALTER TABLE combatants ADD COLUMN character_id INTEGER REFERENCES characters(id)")


def _connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    directory = os.path.dirname(config.DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_V2)
        _migrate_v2_columns(conn)
        conn.commit()
    finally:
        conn.close()
