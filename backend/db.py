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
    dex_mod     INTEGER DEFAULT 0,
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
    is_superuser       INTEGER NOT NULL DEFAULT 0,
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
    campaign_id  INTEGER REFERENCES campaigns(id) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS initiative_requests (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    status             TEXT NOT NULL DEFAULT 'active',
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at         TEXT NOT NULL,
    closed_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_initiative_requests_session ON initiative_requests(session_id);

CREATE TABLE IF NOT EXISTS initiative_rolls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    INTEGER NOT NULL REFERENCES initiative_requests(id) ON DELETE CASCADE,
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    combatant_id  INTEGER NOT NULL REFERENCES combatants(id) ON DELETE CASCADE,
    user_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    dex_mod       INTEGER NOT NULL DEFAULT 0,
    roll_value    INTEGER,
    total         INTEGER,
    status        TEXT NOT NULL DEFAULT 'pending',
    source        TEXT NOT NULL DEFAULT 'unknown',
    rolled_at     TEXT,
    UNIQUE(request_id, combatant_id)
);
CREATE INDEX IF NOT EXISTS idx_initiative_rolls_request ON initiative_rolls(request_id);
CREATE INDEX IF NOT EXISTS idx_initiative_rolls_combatant ON initiative_rolls(combatant_id);
"""

SCHEMA_SRD = """
CREATE TABLE IF NOT EXISTS collections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'srd-2014-es',
    imported_at   TEXT NOT NULL,
    record_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS import_meta (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_slug TEXT NOT NULL,
    source_path     TEXT NOT NULL,
    source_locale   TEXT NOT NULL DEFAULT 'es',
    file_hash       TEXT,
    imported_at     TEXT NOT NULL,
    record_count    INTEGER NOT NULL,
    errors_json     TEXT
);
CREATE INDEX IF NOT EXISTS idx_import_meta_coll
    ON import_meta(collection_slug, imported_at);

CREATE TABLE IF NOT EXISTS monsters (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id          INTEGER NOT NULL REFERENCES collections(id),
    index_slug             TEXT NOT NULL UNIQUE,
    name                   TEXT NOT NULL,
    size                   TEXT,
    type                   TEXT,
    subtype                TEXT,
    alignment              TEXT,
    hit_points             INTEGER NOT NULL,
    hit_dice               TEXT,
    hit_points_roll        TEXT,
    armor_class            INTEGER,
    armor_class_type       TEXT,
    challenge_rating       REAL NOT NULL,
    xp                     INTEGER NOT NULL,
    strength               INTEGER,
    dexterity              INTEGER,
    constitution           INTEGER,
    intelligence           INTEGER,
    wisdom                 INTEGER,
    charisma               INTEGER,
    proficiency_bonus      INTEGER,
    damage_immunities_json     TEXT,
    damage_resistances_json    TEXT,
    damage_vulnerabilities_json TEXT,
    condition_immunities_json  TEXT,
    special_abilities_json     TEXT,
    actions_json               TEXT,
    legendary_actions_json     TEXT,
    reactions_json             TEXT,
    data                   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monsters_cr   ON monsters(challenge_rating);
CREATE INDEX IF NOT EXISTS idx_monsters_type ON monsters(type);
CREATE INDEX IF NOT EXISTS idx_monsters_size ON monsters(size);
CREATE INDEX IF NOT EXISTS idx_monsters_name ON monsters(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS reference_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    index_slug    TEXT NOT NULL,
    name          TEXT NOT NULL,
    data          TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ref_coll_slug ON reference_entries(collection_id, index_slug);
CREATE INDEX IF NOT EXISTS idx_ref_coll ON reference_entries(collection_id);

CREATE TABLE IF NOT EXISTS levels (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    index_slug    TEXT NOT NULL UNIQUE,
    class_slug    TEXT NOT NULL,
    subclass_slug TEXT,
    level         INTEGER NOT NULL,
    prof_bonus    INTEGER,
    data          TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_levels_class_subclass_level ON levels(class_slug, coalesce(subclass_slug, ''), level);
CREATE INDEX IF NOT EXISTS idx_levels_class ON levels(class_slug);

CREATE TABLE IF NOT EXISTS spells (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id    INTEGER NOT NULL REFERENCES collections(id),
    index_slug       TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    level            INTEGER NOT NULL,
    school_slug      TEXT,
    casting_time     TEXT,
    range            TEXT,
    duration         TEXT,
    concentration    INTEGER NOT NULL DEFAULT 0,
    ritual           INTEGER NOT NULL DEFAULT 0,
    components       TEXT,
    attack_type      TEXT,
    data             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spells_level  ON spells(level);
CREATE INDEX IF NOT EXISTS idx_spells_school ON spells(school_slug);
CREATE INDEX IF NOT EXISTS idx_spells_name   ON spells(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS equipment (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id            INTEGER NOT NULL REFERENCES collections(id),
    index_slug               TEXT NOT NULL UNIQUE,
    name                     TEXT NOT NULL,
    equipment_category_slug  TEXT,
    weapon_category          TEXT,
    armor_category           TEXT,
    cost_quantity            REAL,
    cost_unit                TEXT,
    cost_unit_raw            TEXT,
    weight                   REAL,
    damage_dice              TEXT,
    damage_type_slug         TEXT,
    armor_class_base         INTEGER,
    armor_class_dex_bonus    INTEGER,
    armor_class_max_bonus    INTEGER,
    data                     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equip_cat    ON equipment(equipment_category_slug);
CREATE INDEX IF NOT EXISTS idx_equip_weapon ON equipment(weapon_category);
CREATE INDEX IF NOT EXISTS idx_equip_armor  ON equipment(armor_category);
CREATE INDEX IF NOT EXISTS idx_equip_name   ON equipment(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS classes (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id             INTEGER NOT NULL REFERENCES collections(id),
    index_slug                TEXT NOT NULL UNIQUE,
    name                      TEXT NOT NULL,
    hit_die                   INTEGER,
    spellcasting_ability_slug TEXT,
    data                      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_classes_name ON classes(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS races (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    index_slug    TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    speed         INTEGER,
    size          TEXT,
    data          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_races_name ON races(name COLLATE NOCASE);
"""

SCHEMA_HOMEBREW = """
CREATE TABLE IF NOT EXISTS collections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'homebrew',
    created_at    TEXT NOT NULL,
    record_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS monsters (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_slug    TEXT NOT NULL DEFAULT 'homebrew',
    index_slug         TEXT NOT NULL UNIQUE,
    name               TEXT NOT NULL,
    size               TEXT,
    type               TEXT,
    subtype            TEXT,
    alignment          TEXT,
    hit_points         INTEGER NOT NULL,
    hit_dice           TEXT,
    hit_points_roll    TEXT,
    armor_class        INTEGER,
    armor_class_type   TEXT,
    challenge_rating   REAL NOT NULL DEFAULT 0,
    xp                 INTEGER NOT NULL DEFAULT 0,
    strength           INTEGER,
    dexterity          INTEGER,
    constitution       INTEGER,
    intelligence       INTEGER,
    wisdom             INTEGER,
    charisma           INTEGER,
    proficiency_bonus  INTEGER,
    data               TEXT NOT NULL DEFAULT '{}',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_homebrew_monsters_cr   ON monsters(challenge_rating);
CREATE INDEX IF NOT EXISTS idx_homebrew_monsters_type ON monsters(type);
CREATE INDEX IF NOT EXISTS idx_homebrew_monsters_name ON monsters(name COLLATE NOCASE);
"""


def _migrate_v2_columns(conn):
    """Anade columnas nuevas a sessions/combatants/users (idempotente)."""
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
    if "dex_mod" not in cols:
        conn.execute("ALTER TABLE combatants ADD COLUMN dex_mod INTEGER DEFAULT 0")
    cols_users = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "is_superuser" not in cols_users:
        conn.execute("ALTER TABLE users ADD COLUMN is_superuser INTEGER NOT NULL DEFAULT 0")
    cols_rolls = {row[1] for row in conn.execute("PRAGMA table_info(initiative_rolls)")}
    if "source" not in cols_rolls:
        conn.execute("ALTER TABLE initiative_rolls ADD COLUMN source TEXT NOT NULL DEFAULT 'unknown'")


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


def _connect_srd():
    conn = sqlite3.connect(config.SRD_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_srd_db():
    conn = _connect_srd()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _connect_homebrew():
    conn = sqlite3.connect(config.HOMEBREW_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_homebrew_db():
    conn = _connect_homebrew()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_srd_db():
    directory = os.path.dirname(config.SRD_DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(config.SRD_DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA_SRD)
        conn.commit()
    finally:
        conn.close()


def init_homebrew_db():
    directory = os.path.dirname(config.HOMEBREW_DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(config.HOMEBREW_DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA_HOMEBREW)
        conn.commit()
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
    init_srd_db()
    init_homebrew_db()
