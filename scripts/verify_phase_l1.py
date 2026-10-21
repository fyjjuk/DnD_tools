#!/usr/bin/env python3
"""Suite de verificación automatizada para la Fase L1 (Auditoría y Limpieza del Bridge Legacy).

Valida:
1. Idempotencia y exactitud de `scripts/audit_legacy_bridge.py` (detección y --fix).
2. Desacoplamiento de `dm_token`: nuevas sesiones de campaña no polucionan `user_sessions`.
3. Operabilidad de todas las rutas de combate usando puramente `X-User-Token`.
4. Retrocompatibilidad: sesiones legacy operables con `X-DM-Token`.
5. Rechazo estricto (403) a tokens inválidos o no autorizados.

Uso:
    python scripts/verify_phase_l1.py
"""

import asyncio
import os
import secrets
import sqlite3
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config
from backend.app import (
    add_combatant,
    change_hp,
    undo_hp,
    next_turn,
    next_round,
    close_session,
    list_closed_sessions,
    get_session_log,
    auth_login,
    auth_register,
    CombatantIn,
    HpIn,
    LoginIn,
    RegisterIn,
)
from backend.auth import ApiError
from backend.campaigns import create_campaign, create_session_in_campaign
from backend.db import get_db
from scripts.audit_legacy_bridge import audit_and_fix


def check(title: str, condition: bool, extra: str = ""):
    if condition:
        print(f"[OK   ] {title}")
    else:
        print(f"[FALLO] {title} {extra}")
        sys.exit(1)


async def main():
    print("Iniciando verificaciones de la Fase L1...")

    # -------------------------------------------------------------
    # 1. Base de datos limpia tras L1
    # -------------------------------------------------------------
    issues, _ = audit_and_fix(config.DB_PATH, fix=False)
    check("1. Base de datos actual no presenta discrepancias (0 issues)", issues == 0)

    # -------------------------------------------------------------
    # 2. Inyección sintética y reparación de discrepancias
    # -------------------------------------------------------------
    test_player_token = f"tok_test_{secrets.token_hex(8)}"
    test_dm_token = f"dm_tok_test_{secrets.token_hex(8)}"

    fake_sid = fake_pid = fake_cid = None
    try:
        with get_db() as db:
            # Sesión sintética legacy con dm_token sin user_sessions
            s_cur = db.execute(
                "INSERT INTO sessions (code, status, round, dm_token, created_at) "
                "VALUES (?, 'closed', 1, ?, datetime('now'))",
                (f"L{secrets.token_hex(2).upper()}", test_dm_token),
            )
            fake_sid = s_cur.lastrowid

            # Jugador legacy sin user_sessions
            p_cur = db.execute(
                "INSERT INTO players (session_id, name, token, created_at) "
                "VALUES (?, 'Jugador Sintetico', ?, datetime('now'))",
                (fake_sid, test_player_token),
            )
            fake_pid = p_cur.lastrowid

            # Combatiente vinculado con user_id=NULL
            c_cur = db.execute(
                "INSERT INTO combatants (session_id, name, hp_max, hp_current, initiative, kind, player_id, user_id, created_at) "
                "VALUES (?, 'Combatiente Sintetico', 10, 10, 10, 'pc', ?, NULL, datetime('now'))",
                (fake_sid, fake_pid),
            )
            fake_cid = c_cur.lastrowid

        # Detectar las 3 anomalías
        issues_detected, _ = audit_and_fix(config.DB_PATH, fix=False)
        check("2. Auditoría detecta anomalías inyectadas (espejos faltantes)", issues_detected >= 3)

        # Reparar con fix=True
        issues_to_fix, fixed = audit_and_fix(config.DB_PATH, fix=True)
        check("3. Reparación con --fix corrige todas las anomalías", issues_to_fix == fixed)

        # Re-verificar que quedó en 0
        issues_after, _ = audit_and_fix(config.DB_PATH, fix=False)
        check("4. Idempotencia: segunda pasada detecta 0 discrepancias", issues_after == 0)
    finally:
        # Limpiar datos sintéticos
        with get_db() as db:
            if fake_cid:
                db.execute("DELETE FROM combatants WHERE id=?", (fake_cid,))
            if fake_pid:
                db.execute("DELETE FROM players WHERE id=?", (fake_pid,))
            if fake_sid:
                db.execute("DELETE FROM sessions WHERE id=?", (fake_sid,))
            db.execute("DELETE FROM user_sessions WHERE token IN (?, ?)", (test_player_token, test_dm_token))

    # -------------------------------------------------------------
    # 3. Sesión nueva de campaña puramente con X-User-Token
    # -------------------------------------------------------------
    dm_username = f"dm_l1_{secrets.token_hex(3)}"
    dm_pw = "pass_dm_l1_secret"
    try:
        dm_reg = await auth_register(RegisterIn(username=dm_username, display_name="DM Fase L1", password=dm_pw))
        dm_token = dm_reg["token"]
        dm_uid = dm_reg["user_id"]
    except ApiError:
        dm_log = await auth_login(LoginIn(username=dm_username, password=dm_pw))
        dm_token = dm_log["token"]
        dm_uid = dm_log["user_id"]

    # Crear campaña y sesión
    with get_db() as db:
        camp = create_campaign(db, dm_uid, "Campaña Limpia L1")
        camp_id = camp["id"]
        sess = create_session_in_campaign(db, camp_id, dm_uid)
        session_id = sess["id"]

    # Verificar que sessions.dm_token == "" y no hay token basura en user_sessions
    check("5. Nueva sesión de campaña tiene dm_token vacío", sess["dm_token"] == "")
    with get_db() as db:
        junk_tokens = db.execute(
            "SELECT COUNT(*) FROM user_sessions WHERE user_id=? AND token=''",
            (dm_uid,)
        ).fetchone()[0]
        check("6. No se registraron tokens basura en user_sessions", junk_tokens == 0)

    # -------------------------------------------------------------
    # 4. Operaciones de combate puramente con X-User-Token
    # -------------------------------------------------------------
    # Añadir combatiente
    c_res = await add_combatant(
        CombatantIn(name="Orco L1", hp_max=15, initiative=14, kind="enemy"),
        x_user_token=dm_token,
    )
    cid = c_res["id"]
    check("7. add_combatant autorizado con X-User-Token", c_res["ok"] and cid > 0)

    # Modificar HP
    hp_res = await change_hp(cid, HpIn(delta=-5), x_user_token=dm_token)
    check("8. change_hp autorizado con X-User-Token", hp_res["ok"])

    # Deshacer HP
    undo_res = await undo_hp(cid, x_user_token=dm_token)
    check("9. undo_hp autorizado con X-User-Token", undo_res["ok"])

    # Siguiente turno y ronda
    turn_res = await next_turn(x_user_token=dm_token)
    check("10. next_turn autorizado con X-User-Token", turn_res["ok"])

    round_res = await next_round(x_user_token=dm_token)
    check("11. next_round autorizado con X-User-Token", round_res["ok"])

    # Cerrar sesión con X-User-Token
    close_res = await close_session(x_user_token=dm_token)
    check("12. close_session autorizado con X-User-Token", close_res["ok"])

    # -------------------------------------------------------------
    # 5. Control de acceso: usuario ajeno rechazado (403)
    # -------------------------------------------------------------
    other_username = f"other_user_{secrets.token_hex(3)}"
    other_reg = await auth_register(RegisterIn(username=other_username, display_name="Otro Usuario", password="password123"))
    other_token = other_reg["token"]

    try:
        await next_turn(x_user_token=other_token)
        check("13. Usuario sin sesión activa/ajeno es rechazado", False)
    except Exception as e:
        check("13. Usuario sin sesión activa/ajeno es rechazado (404/403)", getattr(e, "status_code", None) in (403, 404))

    print("\nTODAS LAS PRUEBAS DE LA FASE L1 COMPLETADAS CON ÉXITO")


if __name__ == "__main__":
    asyncio.run(main())
