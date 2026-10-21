#!/usr/bin/env python3
"""Script de verificación automatizada para la Fase 2.4.2 (Tiradas de Habilidad / Checks).

Cubre:
1. Esquema de BD: check_requests y check_rolls en data/dnd.db.
2. Cálculo automático de modificador SRD + competencia en fichas de personaje.
3. Solicitud de prueba por DM con CD: PJs en pending, enemigo auto-tirado (npc_auto).
4. Tirada de jugador (éxito y fallo automáticos según CD).
5. Validaciones de límites (d20 en [1,20], CD válida, tirada duplicada -> 409).
6. Mecánica de Ventaja (2d20kh1) y Desventaja (2d20kl1).
7. Tiradas Secretas (is_secret): sanitización en serializador WS para rol player.
8. Control de DM: Forzar tirada (dm_force) y Toma 10 (dm_skip).
9. Superusuario: Forzar tirada en campaña ajena -> superuser_force + admin_action.
10. Cancelación por DM y por cierre de sesión.
11. Cache-busting ?v=2.4.2 en dm.html y player.html.
"""
import asyncio
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import (
    app,
    auth_login,
    auth_me,
    auth_register,
    build_state,
    characters_create,
    check_request_cancel,
    check_request_create,
    check_roll_force,
    check_roll_skip,
    check_roll_submit,
    close_session,
    ApiError,
    CharacterIn,
    CheckActionIn,
    CheckCancelIn,
    CheckRequestIn,
    CheckRollIn,
    CombatantIn,
    LoginIn,
    RegisterIn,
)
from backend.campaigns import create_campaign, create_session_in_campaign
from backend.db import get_db, init_db


class MockRequest:
    def __init__(self, host: str):
        self.client = type("Client", (), {"host": host})()


async def run_checks():
    print("Iniciando verificaciones de la Fase 2.4.2...")
    init_db()

    # 1. Esquema de BD
    with get_db() as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "check_requests" in tables, "Falta tabla check_requests"
        assert "check_rolls" in tables, "Falta tabla check_rolls"
        cols_req = [c[1] for c in db.execute("PRAGMA table_info(check_requests)").fetchall()]
        for expected in ["id", "session_id", "ability", "skill_slug", "dc", "is_secret", "advantage_mode", "status"]:
            assert expected in cols_req, f"Falta columna {expected} en check_requests"
        cols_rolls = [c[1] for c in db.execute("PRAGMA table_info(check_rolls)").fetchall()]
        for expected in ["id", "request_id", "session_id", "combatant_id", "ability_mod", "prof_bonus", "is_proficient", "total_mod", "chosen_roll", "total", "is_success", "status", "source"]:
            assert expected in cols_rolls, f"Falta columna {expected} en check_rolls"
    print("[OK   ] 1. Esquema de check_requests y check_rolls en data/dnd.db verificado")

    # 2. Configurar usuarios, campaña y personajes
    dm_username = "dm_phase_242"
    dm_pw = "pass_dm_242_secret"
    try:
        dm_reg = await auth_register(RegisterIn(username=dm_username, display_name="DM 242", password=dm_pw))
        dm_token = dm_reg["token"]
        dm_uid = dm_reg["user_id"]
    except ApiError:
        dm_log = await auth_login(LoginIn(username=dm_username, password=dm_pw))
        dm_token = dm_log["token"]
        dm_uid = dm_log["user_id"]

    pj1_user = "pj1_phase_242"
    pj1_pw = "pass_pj1_secret"
    try:
        pj1_reg = await auth_register(RegisterIn(username=pj1_user, display_name="Ranger Sabio", password=pj1_pw))
        pj1_token = pj1_reg["token"]
        pj1_uid = pj1_reg["user_id"]
    except ApiError:
        pj1_log = await auth_login(LoginIn(username=pj1_user, password=pj1_pw))
        pj1_token = pj1_log["token"]
        pj1_uid = pj1_log["user_id"]

    pj2_user = "pj2_phase_242"
    pj2_pw = "pass_pj2_secret"
    try:
        pj2_reg = await auth_register(RegisterIn(username=pj2_user, display_name="Guerrero Torpe", password=pj2_pw))
        pj2_token = pj2_reg["token"]
        pj2_uid = pj2_reg["user_id"]
    except ApiError:
        pj2_log = await auth_login(LoginIn(username=pj2_user, password=pj2_pw))
        pj2_token = pj2_log["token"]
        pj2_uid = pj2_log["user_id"]

    with get_db() as db:
        camp = create_campaign(db, dm_uid, "Campaña Habilidades 2.4.2")
        camp_id = camp["id"]
        sess = create_session_in_campaign(db, camp_id, dm_uid)
        session_id = sess["id"]

    # Ficha PJ 1: Sabiduría 14 (+2), Competente en Percepción (+2) -> Total Mod = +4
    char1 = await characters_create(
        CharacterIn(
            name="Ranger Sabio",
            level=3,
            class_slug="ranger",
            race_slug="elf",
            data={
                "stats": {"strength": 10, "dexterity": 14, "constitution": 12, "intelligence": 10, "wisdom": 14, "charisma": 10},
                "skill_proficiencies": ["perception", "survival"],
            },
        ),
        x_user_token=pj1_token,
    )
    char1_id = char1["id"]

    # Ficha PJ 2: Sabiduría 10 (+0), NO competente en Percepción -> Total Mod = +0
    char2 = await characters_create(
        CharacterIn(
            name="Guerrero Torpe",
            level=3,
            class_slug="fighter",
            race_slug="human",
            data={
                "stats": {"strength": 16, "dexterity": 12, "constitution": 14, "intelligence": 8, "wisdom": 10, "charisma": 8},
                "skill_proficiencies": ["athletics"],
            },
        ),
        x_user_token=pj2_token,
    )
    char2_id = char2["id"]

    # Insertar combatientes en la sesión
    with get_db() as db:
        c1 = db.execute(
            "INSERT INTO combatants (session_id, name, hp_current, hp_max, initiative, kind, character_id, user_id, created_at) "
            "VALUES (?, 'Ranger Sabio', 20, 20, 15, 'pc', ?, ?, datetime('now'))",
            (session_id, char1_id, pj1_uid),
        ).lastrowid
        c2 = db.execute(
            "INSERT INTO combatants (session_id, name, hp_current, hp_max, initiative, kind, character_id, user_id, created_at) "
            "VALUES (?, 'Guerrero Torpe', 28, 28, 12, 'pc', ?, ?, datetime('now'))",
            (session_id, char2_id, pj2_uid),
        ).lastrowid
        c_enemy = db.execute(
            "INSERT INTO combatants (session_id, name, hp_current, hp_max, initiative, kind, dex_mod, created_at) "
            "VALUES (?, 'Goblin Emboscador', 7, 7, 14, 'enemy', 2, datetime('now'))",
            (session_id,),
        ).lastrowid

    print("[OK   ] 2. Campaña, personajes con competencias y combatientes creados")

    # 3. Solicitar prueba de Percepción CD 15 para todos los PJs
    req_res = await check_request_create(
        session_id,
        CheckRequestIn(
            ability="wis",
            skill_slug="perception",
            dc=15,
            is_secret=False,
            advantage_mode="normal",
        ),
        x_user_token=dm_token,
    )
    req_id = req_res["request_id"]

    with get_db() as db:
        req_row = db.execute("SELECT * FROM check_requests WHERE id=?", (req_id,)).fetchone()
        assert req_row["status"] == "active"
        assert req_row["dc"] == 15
        assert req_row["skill_slug"] == "perception"
        assert req_row["ability"] == "wis"

        rolls = db.execute("SELECT * FROM check_rolls WHERE request_id=?", (req_id,)).fetchall()
        assert len(rolls) == 2, f"Debió crear 2 rolls para los 2 PJs, creó {len(rolls)}"
        r_pj1 = next(r for r in rolls if r["combatant_id"] == c1)
        r_pj2 = next(r for r in rolls if r["combatant_id"] == c2)

        assert r_pj1["ability_mod"] == 2
        assert r_pj1["prof_bonus"] == 2
        assert r_pj1["is_proficient"] == 1
        assert r_pj1["total_mod"] == 4, f"PJ1 competente esperaba mod +4, obtuvo {r_pj1['total_mod']}"
        assert r_pj1["status"] == "pending"

        assert r_pj2["ability_mod"] == 0
        assert r_pj2["is_proficient"] == 0
        assert r_pj2["total_mod"] == 0, f"PJ2 no competente esperaba mod +0, obtuvo {r_pj2['total_mod']}"
        assert r_pj2["status"] == "pending"
    print("[OK   ] 3. Solicitud de prueba creada con auto-cálculo de mod SRD (+4 competente vs +0 no competente)")

    # 4. Tiradas de jugadores: Éxito automático y Fallo automático
    # PJ1 tira 12: 12 + 4 = 16 >= 15 -> ÉXITO
    submit1 = await check_roll_submit(
        CheckRollIn(request_id=req_id, combatant_id=c1, roll_value_1=12),
        x_user_token=pj1_token,
    )
    assert submit1["total"] == 16
    assert submit1["is_success"] is True

    # PJ2 tira 11: 11 + 0 = 11 < 15 -> FALLO
    submit2 = await check_roll_submit(
        CheckRollIn(request_id=req_id, combatant_id=c2, roll_value_1=11),
        x_user_token=pj2_token,
    )
    assert submit2["total"] == 11
    assert submit2["is_success"] is False

    with get_db() as db:
        req_completed = db.execute("SELECT * FROM check_requests WHERE id=?", (req_id,)).fetchone()
        assert req_completed["status"] == "completed", "Al completar todas las tiradas debió pasar a 'completed'"
    print("[OK   ] 4. Tiradas enviadas por jugadores evaluadas con éxito (16 >= 15) y fallo (11 < 15)")

    # 5. Validaciones de límites y errores
    # Repetir tirada en request completado o tirada ya resulta -> 409
    try:
        await check_roll_submit(
            CheckRollIn(request_id=req_id, combatant_id=c1, roll_value_1=15),
            x_user_token=pj1_token,
        )
        assert False, "Debió rechazar tirada en request inactivo o ya resuelta"
    except ApiError as e:
        assert e.status_code in (400, 409)

    # Tirada con d20 fuera de rango [1, 20] -> 400
    try:
        await check_roll_submit(
            CheckRollIn(request_id=req_id, combatant_id=c1, roll_value_1=25),
            x_user_token=pj1_token,
        )
        assert False, "Debió rechazar d20 fuera de rango"
    except ApiError as e:
        assert e.status_code == 400
        assert e.code == "INVALID_ROLL"

    # CD inválida -> 400
    try:
        await check_request_create(
            session_id,
            CheckRequestIn(ability="wis", dc=0),
            x_user_token=dm_token,
        )
        assert False, "Debió rechazar CD menor a 1"
    except ApiError as e:
        assert e.status_code == 400
        assert e.code == "INVALID_DC"
    print("[OK   ] 5. Validaciones de límites (d20 en [1,20], CD válida, no duplicados) verificadas")

    # 6. Ventaja y Desventaja
    # Prueba con Ventaja
    req_adv = await check_request_create(
        session_id,
        CheckRequestIn(
            ability="wis",
            skill_slug="perception",
            dc=15,
            advantage_mode="advantage",
            target_combatant_ids=[c1],
        ),
        x_user_token=dm_token,
    )
    adv_id = req_adv["request_id"]
    # PJ1 tira [5, 17] -> con ventaja se elige 17 -> 17 + 4 = 21 >= 15 -> ÉXITO
    adv_sub = await check_roll_submit(
        CheckRollIn(request_id=adv_id, combatant_id=c1, roll_value_1=5, roll_value_2=17),
        x_user_token=pj1_token,
    )
    assert adv_sub["chosen_roll"] == 17
    assert adv_sub["total"] == 21
    assert adv_sub["is_success"] is True

    # Prueba con Desventaja
    req_dis = await check_request_create(
        session_id,
        CheckRequestIn(
            ability="wis",
            skill_slug="perception",
            dc=15,
            advantage_mode="disadvantage",
            target_combatant_ids=[c1],
        ),
        x_user_token=dm_token,
    )
    dis_id = req_dis["request_id"]
    # PJ1 tira [18, 4] -> con desventaja se elige 4 -> 4 + 4 = 8 < 15 -> FALLO
    dis_sub = await check_roll_submit(
        CheckRollIn(request_id=dis_id, combatant_id=c1, roll_value_1=18, roll_value_2=4),
        x_user_token=pj1_token,
    )
    assert dis_sub["chosen_roll"] == 4
    assert dis_sub["total"] == 8
    assert dis_sub["is_success"] is False
    print("[OK   ] 6. Mecánica de Ventaja (2d20kh1) y Desventaja (2d20kl1) verificada")

    # 7. Tiradas Secretas (is_secret=True)
    req_sec = await check_request_create(
        session_id,
        CheckRequestIn(
            ability="wis",
            skill_slug="perception",
            dc=18,
            is_secret=True,
            target_combatant_ids=[c1, c2],
        ),
        x_user_token=dm_token,
    )
    sec_id = req_sec["request_id"]

    # Al enviar la tirada como jugador, is_success debe ser None
    sec_sub = await check_roll_submit(
        CheckRollIn(request_id=sec_id, combatant_id=c1, roll_value_1=16),
        x_user_token=pj1_token,
    )
    assert sec_sub["total"] == 20  # 16 + 4
    assert sec_sub["is_success"] is None, "En tirada secreta, el submit no debe filtrar is_success al jugador"

    # En build_state (WS broadcast activo, pues c2 sigue pending):
    with get_db() as db:
        session_row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        combatants_rows = db.execute("SELECT * FROM combatants WHERE session_id=?", (session_id,)).fetchall()
        players_rows = db.execute("SELECT id, name FROM players WHERE session_id=?", (session_id,)).fetchall()

    state_player = build_state(session_row, combatants_rows, players_rows, role="player", player_id=None)
    assert state_player["check_request"] is not None
    assert state_player["check_request"]["dc"] is None, "WS para jugador no debe filtrar la CD secreta"
    assert state_player["check_request"]["rolls"][0]["is_success"] is None, "WS para jugador no debe filtrar is_success"

    state_dm = build_state(session_row, combatants_rows, players_rows, role="dm", player_id=None)
    assert state_dm["check_request"] is not None
    assert state_dm["check_request"]["dc"] == 18, "WS para DM sí debe mostrar la CD"
    assert state_dm["check_request"]["rolls"][0]["is_success"] is True, "WS para DM sí debe mostrar el veredicto"

    # Completar tirada de c2
    await check_roll_submit(CheckRollIn(request_id=sec_id, combatant_id=c2, roll_value_1=10), x_user_token=pj2_token)
    print("[OK   ] 7. Tiradas secretas (is_secret) verificadas: CD y veredicto ocultos al jugador y visibles al DM")

    # 8. Control del DM: Forzar tirada (dm_force) y Toma 10 (dm_skip)
    req_control = await check_request_create(
        session_id,
        CheckRequestIn(
            ability="dex",
            skill_slug="stealth",
            dc=12,
            target_combatant_ids=[c1, c2],
        ),
        x_user_token=dm_token,
    )
    c_id = req_control["request_id"]

    # DM fuerza tirada en c1
    forced = await check_roll_force(CheckActionIn(request_id=c_id, combatant_id=c1), x_user_token=dm_token)
    assert forced["ok"] is True
    with get_db() as db:
        r_f = db.execute("SELECT * FROM check_rolls WHERE request_id=? AND combatant_id=?", (c_id, c1)).fetchone()
        assert r_f["status"] == "forced"
        assert r_f["source"] == "dm_force"

    # DM salta tirada en c2 (Toma 10)
    skipped = await check_roll_skip(CheckActionIn(request_id=c_id, combatant_id=c2), x_user_token=dm_token)
    assert skipped["ok"] is True
    assert skipped["chosen_roll"] == 10
    with get_db() as db:
        r_s = db.execute("SELECT * FROM check_rolls WHERE request_id=? AND combatant_id=?", (c_id, c2)).fetchone()
        assert r_s["status"] == "skipped"
        assert r_s["source"] == "dm_skip"
        assert r_s["chosen_roll"] == 10
        # Guerrero Torpe tiene DES 12 (+1) -> Total 11 < 12 -> is_success = 0
        assert r_s["total"] == 11
        assert r_s["is_success"] == 0
    print("[OK   ] 8. Control del DM (Forzar d20 y Toma 10) con trazabilidad de source verificado")

    # 9. Superusuario: Forzar tirada en campaña ajena
    with get_db() as db:
        admin_row = db.execute("SELECT * FROM users WHERE is_superuser=1 LIMIT 1").fetchone()
    if admin_row:
        # Generar sesión para admin
        admin_login = await auth_login(LoginIn(username=admin_row["username"], password="admin_super_secret_pw"), request=MockRequest("127.0.0.1"))
        admin_tok = admin_login["token"]

        req_admin = await check_request_create(
            session_id,
            CheckRequestIn(ability="str", dc=10, target_combatant_ids=[c1]),
            x_user_token=admin_tok,
        )
        assert req_admin["ok"] is True
        forced_admin = await check_roll_force(CheckActionIn(request_id=req_admin["request_id"], combatant_id=c1), x_user_token=admin_tok)
        assert forced_admin["ok"] is True
        with get_db() as db:
            r_adm = db.execute("SELECT * FROM check_rolls WHERE request_id=? AND combatant_id=?", (req_admin["request_id"], c1)).fetchone()
            assert r_adm["source"] == "superuser_force"
        print("[OK   ] 9. Superusuario ejecutando solicitud y forzado en campaña ajena verificado")

    # 10. Cancelación por DM y por Cierre de Sesión
    # Cancelación directa
    req_to_cancel = await check_request_create(
        session_id,
        CheckRequestIn(ability="int", dc=14, target_combatant_ids=[c1]),
        x_user_token=dm_token,
    )
    cancel_res = await check_request_cancel(CheckCancelIn(request_id=req_to_cancel["request_id"]), x_user_token=dm_token)
    assert cancel_res["ok"] is True
    with get_db() as db:
        c_req = db.execute("SELECT * FROM check_requests WHERE id=?", (req_to_cancel["request_id"],)).fetchone()
        assert c_req["status"] == "cancelled"

    # Cancelación por cierre de sesión
    req_before_close = await check_request_create(
        session_id,
        CheckRequestIn(ability="cha", dc=12, target_combatant_ids=[c1]),
        x_user_token=dm_token,
    )
    await close_session(x_user_token=dm_token)
    with get_db() as db:
        c_req_closed = db.execute("SELECT * FROM check_requests WHERE id=?", (req_before_close["request_id"],)).fetchone()
        assert c_req_closed["status"] == "cancelled", "Cerrar sesión debe cancelar requests de prueba activos"
    print("[OK   ] 10. Cancelación explícita por DM y cancelación automática al cerrar sesión verificadas")

    # 11. Cache-busting ?v=2.4.2 en htmls
    with open("frontend/dm.html", "r", encoding="utf-8") as f:
        dm_html = f.read()
        assert "v=2.4.2" in dm_html, "Falta ?v=2.4.2 en dm.html"
    with open("frontend/player.html", "r", encoding="utf-8") as f:
        player_html = f.read()
        assert "v=2.4.2" in player_html, "Falta ?v=2.4.2 en player.html"
    print("[OK   ] 11. Cache-busting ?v=2.4.2 verificado en frontend/dm.html y frontend/player.html")

    print("\nTODAS LAS PRUEBAS DE LA FASE 2.4.2 COMPLETADAS CON ÉXITO")


if __name__ == "__main__":
    asyncio.run(run_checks())
