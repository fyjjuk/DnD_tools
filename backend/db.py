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
        conn.commit()
    finally:
        conn.close()
