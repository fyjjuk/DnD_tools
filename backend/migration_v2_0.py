"""Fase 2.0: migracion de datos existentes al schema v2.

Uso (con el servidor PARADO, desde la raiz del proyecto):
    python -m backend.migration_v2_0

Idempotente: si detecta que ya se migro, termina sin hacer nada.
"""
import datetime
import os
import shutil
import sys

import config
from backend.db import get_db, init_db
from backend.auth import ensure_dm_user, ensure_user_session
from backend.campaigns import slugify


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def step_backup() -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = config.DB_PATH
    bak = f"{base}.bak.{ts}"
    wal = f"{base}-wal"
    if os.path.exists(wal) and os.path.getsize(wal) > 0:
        print(f"AVISO: {wal} tiene datos. El servidor deberia estar PARADO antes de migrar.")
    for src in (base, wal, f"{base}-shm"):
        if os.path.exists(src):
            suffix = src[len(base):]
            shutil.copy2(src, bak + suffix)
    print(f"[1] backup -> {bak}")
    return bak


def step_detect_migrated() -> bool:
    init_db()  # asegura que las tablas v2 existen (idempotente)
    with get_db() as db:
        dm = db.execute("SELECT id FROM users WHERE username='dm'").fetchone()
        has_camp_col = db.execute(
            "SELECT 1 FROM pragma_table_info('sessions') WHERE name='campaign_id'"
        ).fetchone()
    return dm is not None and has_camp_col is not None


def step_close_active_session():
    with get_db() as db:
        s = db.execute(
            "SELECT * FROM sessions WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if s is None:
            print("[3] no habia sesion activa")
            return None
        sid, code = s["id"], s["code"]
        ts = _now()
        db.execute(
            "INSERT INTO events (session_id, ts, kind, message) VALUES (?,?,?,?)",
            (sid, ts, "session", "Sesion cerrada por migracion v2.0"),
        )
        db.execute(
            "UPDATE sessions SET status='closed', closed_at=? WHERE id=?",
            (ts, sid),
        )
        events = db.execute(
            "SELECT * FROM events WHERE session_id=? ORDER BY id", (sid,)
        ).fetchall()
        log_dir = os.path.join(config.BASE_DIR, "data", "logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"session_{code}.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"Sesion {code} - cerrada {ts}\n")
            fh.write("-" * 60 + "\n")
            for e in events:
                fh.write(f"[{e['ts']}] {e['kind']:<9} {e['message']}\n")
    print(f"[3] sesion activa {code} cerrada -> {path}")
    return code


def step_create_dm_user() -> int:
    with get_db() as db:
        uid = ensure_dm_user(db)
    print(f"[4] dm user id={uid}")
    return uid


def step_migrate_players() -> dict:
    mapping = {}
    with get_db() as db:
        players = db.execute("SELECT * FROM players ORDER BY id").fetchall()
        for p in players:
            base_username = f"{slugify(p['name'])}_{p['id']}"
            uname = base_username
            n = 1
            while db.execute("SELECT 1 FROM users WHERE username=?", (uname,)).fetchone():
                n += 1
                uname = f"{base_username}_x{n}"
            cur = db.execute(
                "INSERT INTO users (username, display_name, is_guest, created_at) "
                "VALUES (?,?,1,?)",
                (uname, p["name"], p["created_at"]),
            )
            uid = cur.lastrowid
            mapping[p["id"]] = uid
            ensure_user_session(db, uid, p["token"], p["created_at"])
            db.execute(
                "INSERT OR IGNORE INTO session_participants "
                "(session_id, user_id, joined_at) VALUES (?,?,?)",
                (p["session_id"], uid, p["created_at"]),
            )
    print(f"[5] players migrados: {len(mapping)}")
    return mapping


def step_migrate_combatants(mapping: dict):
    n_ok = 0
    n_missing = 0
    with get_db() as db:
        rows = db.execute(
            "SELECT id, player_id FROM combatants WHERE player_id IS NOT NULL"
        ).fetchall()
        for r in rows:
            uid = mapping.get(r["player_id"])
            if uid is None:
                n_missing += 1
                continue
            db.execute(
                "UPDATE combatants SET user_id=? WHERE id=?", (uid, r["id"])
            )
            n_ok += 1
    print(f"[6] combatants con player_id: {len(rows)} "
          f"(user_id set: {n_ok}, missing mapping: {n_missing})")
    return n_ok, n_missing


def step_migrate_dm_tokens(dm_uid: int):
    n = 0
    skipped = 0
    with get_db() as db:
        sessions = db.execute("SELECT * FROM sessions ORDER BY id").fetchall()
        for s in sessions:
            if not s["dm_token"]:
                continue
            existing = db.execute(
                "SELECT user_id FROM user_sessions WHERE token=?", (s["dm_token"],)
            ).fetchone()
            if existing is not None:
                if existing["user_id"] != dm_uid:
                    print(f"AVISO: dm_token de sesion {s['code']} ya asignado a otro "
                          f"user (id={existing['user_id']}), skip")
                skipped += 1
                continue
            ensure_user_session(db, dm_uid, s["dm_token"], s["created_at"])
            n += 1
    print(f"[7] dm_tokens migrados: {n} (ya existentes: {skipped})")
    return n, skipped


def step_verify(n_players_expected: int) -> bool:
    ok = True
    with get_db() as db:
        n_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        n_dm = db.execute("SELECT COUNT(*) FROM users WHERE username='dm'").fetchone()[0]
        n_guest = db.execute("SELECT COUNT(*) FROM users WHERE is_guest=1").fetchone()[0]
        n_us = db.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0]
        n_sp = db.execute("SELECT COUNT(*) FROM session_participants").fetchone()[0]
        n_c_uid = db.execute(
            "SELECT COUNT(*) FROM combatants WHERE user_id IS NOT NULL"
        ).fetchone()[0]
        n_c_missing = db.execute(
            "SELECT COUNT(*) FROM combatants "
            "WHERE player_id IS NOT NULL AND user_id IS NULL"
        ).fetchone()[0]
        n_sessions = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    print()
    print("=== RESUMEN ===")
    print(f"users:                          {n_users} total (1 dm + {n_guest} guests)")
    print(f"user_sessions:                  {n_us} ({n_guest} guest + {n_us - n_guest} dm_tokens)")
    print(f"session_participants:           {n_sp} (= {n_guest} guests)")
    print(f"combatants con user_id != NULL: {n_c_uid}")
    print()

    if n_dm != 1:
        print(f"FALLO: esperaba 1 dm user, hay {n_dm}")
        ok = False
    if n_guest != n_players_expected:
        print(f"FALLO: esperaba {n_players_expected} guests, hay {n_guest}")
        ok = False
    if n_sp != n_players_expected:
        print(f"FALLO: esperaba {n_players_expected} session_participants, hay {n_sp}")
        ok = False
    if n_c_missing > 0:
        print(f"FALLO: {n_c_missing} combatants con player_id pero user_id NULL")
        ok = False
    if n_us != n_players_expected + n_sessions:
        print(f"AVISO: user_sessions={n_us}, esperado ~{n_players_expected + n_sessions}")
    return ok


def main() -> int:
    print(f"DB: {config.DB_PATH}")
    print(f"timestamp: {_now()}")
    step_backup()

    if step_detect_migrated():
        with get_db() as db:
            n_bad = db.execute(
                "SELECT COUNT(*) FROM combatants "
                "WHERE player_id IS NOT NULL AND user_id IS NULL"
            ).fetchone()[0]
        if n_bad > 0:
            print(f"AVISO: migracion previa detectada pero {n_bad} combatants sin user_id.")
            print("       Restaura data/dnd.db.bak.* y vuelve a ejecutar si es un fallo.")
            return 1
        print("ya migrado, nada que hacer")
        return 0

    step_close_active_session()
    dm_uid = step_create_dm_user()
    mapping = step_migrate_players()
    step_migrate_combatants(mapping)
    step_migrate_dm_tokens(dm_uid)
    ok = step_verify(len(mapping))

    if ok:
        print("OK: migracion completada")
        print("    (si algo se ve mal, restaura data/dnd.db.bak.* y reporta)")
        return 0
    print("ERROR: verificacion fallo")
    return 1


if __name__ == "__main__":
    sys.exit(main())
