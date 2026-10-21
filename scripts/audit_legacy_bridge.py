#!/usr/bin/env python3
"""Script de auditoría y reconciliación idempotente del Bridge Legacy (Fase L1).

Detecta y repara discrepancias entre el modelo Fase 1 (players, sessions.dm_token)
y el modelo Fase 2 (users, user_sessions, session_participants, combatants.user_id).

Uso:
    python scripts/audit_legacy_bridge.py        # Modo diagnóstico (dry-run)
    python scripts/audit_legacy_bridge.py --fix  # Repara todas las discrepancias
"""

import argparse
import datetime
import os
import sqlite3
import sys

# Bootstrap sys.path para imports de backend
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config
from backend.auth import ensure_dm_user, ensure_user_session
from backend.campaigns import slugify


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def audit_and_fix(db_path: str, fix: bool = False) -> tuple[int, int]:
    """Audita y opcionalmente repara discrepancias del bridge legacy.
    
    Retorna (discrepancias_detectadas, discrepancias_reparadas).
    """
    conn = _connect(db_path)
    try:
        total_issues = 0
        total_fixed = 0

        print(f"\n=======================================================")
        print(f"  AUDITORÍA DEL BRIDGE LEGACY (Fase L1)")
        print(f"  Base de datos: {db_path}")
        print(f"  Modo: {'REPARACIÓN (--fix)' if fix else 'DIAGNÓSTICO (dry-run)'}")
        print(f"=======================================================\n")

        # -------------------------------------------------------------
        # 0. Integridad: Jugadores con session_id inexistente (huérfanos)
        # -------------------------------------------------------------
        print("[-] 0. Verificando integridad referencial en 'players'...")
        orphan_players = conn.execute("""
            SELECT p.id, p.name, p.session_id, p.created_at
            FROM players p
            LEFT JOIN sessions s ON s.id = p.session_id
            WHERE s.id IS NULL
            ORDER BY p.id ASC
        """).fetchall()

        if orphan_players:
            print(f"    [ALERTA] {len(orphan_players)} jugador(es) huérfano(s) (sesión eliminada):")
            total_issues += len(orphan_players)
            for p in orphan_players:
                print(f"       - Player #{p['id']}: '{p['name']}' (session_id inexistente={p['session_id']})")
                if fix:
                    conn.execute("DELETE FROM players WHERE id=?", (p["id"],))
                    total_fixed += 1
                    print(f"         -> [FIXED] Player #{p['id']} purgado según política ON DELETE CASCADE.")
        else:
            print("    [OK] No existen jugadores huérfanos en 'players'.")

        # -------------------------------------------------------------
        # 1. Jugadores en 'players' sin espejo en 'user_sessions'
        # -------------------------------------------------------------
        print("\n[-] 1. Verificando espejo de 'players' en 'user_sessions'...")
        unmatched_players = conn.execute("""
            SELECT p.id, p.name, p.token, p.session_id, p.created_at
            FROM players p
            LEFT JOIN user_sessions us ON us.token = p.token
            WHERE us.token IS NULL
            ORDER BY p.id ASC
        """).fetchall()

        if unmatched_players:
            print(f"    [ALERTA] {len(unmatched_players)} jugador(es) legacy sin 'user_sessions':")
            total_issues += len(unmatched_players)
            for p in unmatched_players:
                print(f"       - Player #{p['id']}: '{p['name']}' (session={p['session_id']}, token={p['token'][:10]}...)")
                if fix:
                    # Buscar o crear usuario guest
                    base_uname = f"{slugify(p['name'])}_{p['id']}"
                    uname = base_uname
                    n = 1
                    while conn.execute("SELECT 1 FROM users WHERE username=?", (uname,)).fetchone():
                        n += 1
                        uname = f"{base_uname}_x{n}"

                    cur = conn.execute(
                        "INSERT INTO users (username, display_name, is_guest, created_at) "
                        "VALUES (?, ?, 1, ?)",
                        (uname, p["name"], p["created_at"]),
                    )
                    uid = cur.lastrowid
                    ensure_user_session(conn, uid, p["token"], p["created_at"])
                    # Verificar si la sesión existe antes de insertar participante
                    s_exists = conn.execute("SELECT 1 FROM sessions WHERE id=?", (p["session_id"],)).fetchone()
                    if s_exists:
                        conn.execute(
                            "INSERT OR IGNORE INTO session_participants (session_id, user_id, joined_at) "
                            "VALUES (?, ?, ?)",
                            (p["session_id"], uid, p["created_at"]),
                        )
                    # Sincronizar combatientes vinculados a este player
                    conn.execute(
                        "UPDATE combatants SET user_id=? WHERE player_id=? AND (user_id IS NULL OR user_id != ?)",
                        (uid, p["id"], uid),
                    )
                    total_fixed += 1
                    print(f"         -> [FIXED] Creado guest #{uid} ('{uname}'), user_session y participant vinculados.")
        else:
            print("    [OK] Todos los registros de 'players' tienen su sesión de usuario correspondiente.")

        # -------------------------------------------------------------
        # 2. Combatientes con player_id pero sin user_id sincronizado
        # -------------------------------------------------------------
        print("\n[-] 2. Verificando sincronización combatants.player_id -> combatants.user_id...")
        mismatched_combatants = conn.execute("""
            SELECT c.id, c.name, c.player_id, c.user_id, us.user_id AS expected_user_id
            FROM combatants c
            JOIN players p ON p.id = c.player_id
            LEFT JOIN user_sessions us ON us.token = p.token
            WHERE c.player_id IS NOT NULL AND (c.user_id IS NULL OR c.user_id != us.user_id)
            ORDER BY c.id ASC
        """).fetchall()

        if mismatched_combatants:
            print(f"    [ALERTA] {len(mismatched_combatants)} combatiente(s) desincronizado(s):")
            total_issues += len(mismatched_combatants)
            for c in mismatched_combatants:
                exp_uid = c["expected_user_id"]
                print(f"       - Combatant #{c['id']}: '{c['name']}' (player_id={c['player_id']}, actual_uid={c['user_id']}, esperado={exp_uid})")
                if fix and exp_uid is not None:
                    conn.execute(
                        "UPDATE combatants SET user_id=? WHERE id=?",
                        (exp_uid, c["id"]),
                    )
                    total_fixed += 1
                    print(f"         -> [FIXED] combatant #{c['id']} actualizado con user_id={exp_uid}")
        else:
            print("    [OK] Todos los combatientes con player_id tienen su user_id sincronizado.")

        # -------------------------------------------------------------
        # 3. dm_token de sesiones sin espejo en 'user_sessions'
        # -------------------------------------------------------------
        print("\n[-] 3. Verificando espejo de 'sessions.dm_token' en 'user_sessions'...")
        unmatched_dm = conn.execute("""
            SELECT s.id, s.code, s.dm_token, s.campaign_id, s.created_by_user_id, s.created_at
            FROM sessions s
            LEFT JOIN user_sessions us ON us.token = s.dm_token
            WHERE s.dm_token IS NOT NULL AND s.dm_token != '' AND us.token IS NULL
            ORDER BY s.id ASC
        """).fetchall()

        if unmatched_dm:
            print(f"    [ALERTA] {len(unmatched_dm)} sesión(es) con dm_token sin 'user_sessions':")
            total_issues += len(unmatched_dm)
            for s in unmatched_dm:
                print(f"       - Session #{s['id']} ({s['code']}): dm_token={s['dm_token'][:10]}... (creator={s['created_by_user_id']}, camp={s['campaign_id']})")
                if fix:
                    # Determinar el usuario DM de esta sesión
                    target_uid = None
                    if s["created_by_user_id"]:
                        u_check = conn.execute("SELECT id FROM users WHERE id=?", (s["created_by_user_id"],)).fetchone()
                        if u_check:
                            target_uid = u_check["id"]

                    if target_uid is None and s["campaign_id"]:
                        camp_row = conn.execute("SELECT dm_user_id FROM campaigns WHERE id=?", (s["campaign_id"],)).fetchone()
                        if camp_row:
                            target_uid = camp_row["dm_user_id"]

                    if target_uid is None:
                        dm_row = conn.execute("SELECT id FROM users WHERE username='dm'").fetchone()
                        if dm_row:
                            target_uid = dm_row["id"]
                        else:
                            try:
                                target_uid = ensure_dm_user(conn)
                            except Exception:
                                target_uid = None

                    if target_uid is not None:
                        created_ts = s["created_at"] or _now()
                        ensure_user_session(conn, target_uid, s["dm_token"], created_ts)
                        total_fixed += 1
                        print(f"         -> [FIXED] dm_token registrado en user_sessions para user #{target_uid}")
        else:
            print("    [OK] Todos los dm_token no vacíos están presentes en user_sessions.")

        # -------------------------------------------------------------
        # 4. Integridad: combatientes con player_id huérfano
        # -------------------------------------------------------------
        print("\n[-] 4. Verificando combatientes con player_id huérfano...")
        orphan_combatants = conn.execute("""
            SELECT c.id, c.name, c.player_id
            FROM combatants c
            LEFT JOIN players p ON p.id = c.player_id
            WHERE c.player_id IS NOT NULL AND p.id IS NULL
            ORDER BY c.id ASC
        """).fetchall()

        if orphan_combatants:
            print(f"    [ALERTA] {len(orphan_combatants)} combatiente(s) con player_id inexistente:")
            total_issues += len(orphan_combatants)
            for c in orphan_combatants:
                print(f"       - Combatant #{c['id']}: '{c['name']}' (player_id huérfano={c['player_id']})")
                if fix:
                    conn.execute("UPDATE combatants SET player_id=NULL WHERE id=?", (c["id"],))
                    total_fixed += 1
                    print(f"         -> [FIXED] Combatant #{c['id']}: player_id reseteado a NULL.")
        else:
            print("    [OK] No existen combatientes con player_id huérfano.")

        if fix:
            conn.commit()

        print(f"\n=======================================================")
        print(f"  RESUMEN:")
        print(f"  Discrepancias detectadas: {total_issues}")
        if fix:
            print(f"  Discrepancias reparadas:  {total_fixed}")
            remaining = total_issues - total_fixed
            print(f"  Discrepancias pendientes: {remaining}")
        print(f"=======================================================\n")

        return total_issues, total_fixed
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Auditoría y corrección del Bridge Legacy")
    parser.add_argument("--fix", action="store_true", help="Reparar automáticamente las discrepancias encontradas")
    parser.add_argument("--db", type=str, default=config.DB_PATH, help="Ruta a la base de datos SQLite")
    args = parser.parse_args()

    issues, fixed = audit_and_fix(args.db, fix=args.fix)

    if args.fix:
        remaining = issues - fixed
        sys.exit(0 if remaining == 0 else 1)
    else:
        sys.exit(0 if issues == 0 else 1)


if __name__ == "__main__":
    main()
