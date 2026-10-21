#!/usr/bin/env python3
"""Script de verificación automatizada para la Fase 2.4.1.

Cubre:
1. set_superuser.py funcional vía stdin pipe.
2. Login admin desde IP no-loopback simulada -> 403 SUPERUSER_IP_FORBIDDEN.
3. Login admin desde loopback -> 200 OK y devuelve is_superuser=True en /api/auth/me.
4. DM edita ficha de un PJ de su campaña -> 200 OK.
5. DM intenta editar ficha de PJ de otra campaña -> 403 FORBIDDEN.
6. Edición de ficha sin campaña por superusuario -> 200 OK.
7. Crear request de iniciativa: enemigo auto-tirado, jugadores en estado pending.
8. Submit de jugador: cálculo en servidor (roll_value + dex_mod).
9. Submit duplicado rechazado con error controlado (409).
10. Forzar tirada (DM o superusuario) y saltar tirada (toma 10).
11. Reset por segundo request de iniciativa.
12. Superusuario fuerza tirada de un jugador fuera de su campaña -> 200 OK + evento admin_action.
13. Cancelación de request por cierre de sesión.
14. Cache-busting ?v=2.4 en dm.html y player.html.
15. Validación roll_value fuera de [1,20] devuelve 400 INVALID_ROLL y no altera iniciativa.
16. Trazabilidad explícita de source en initiative_rolls (npc_auto, player, dm_force, dm_skip, superuser_force).

NOTA DE COMPATIBILIDAD:
Iniciativa interactiva requiere cuenta de campaña (v2). DM legacy
en /dm recovery puede seguir usando el resto de features sin problema.
"""
import asyncio
import os
import sqlite3
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import (
    app,
    auth_login,
    auth_me,
    auth_register,
    characters_create,
    characters_update,
    close_session,
    initiative_request_cancel,
    initiative_request_create,
    initiative_roll_force,
    initiative_roll_skip,
    initiative_roll_submit,
    ApiError,
    CharacterIn,
    InitiativeActionIn,
    InitiativeCancelIn,
    InitiativeRollIn,
    LoginIn,
    RegisterIn,
)
from backend.db import get_db, init_db


class MockRequest:
    def __init__(self, host: str):
        self.client = type("Client", (), {"host": host})()


async def run_checks():
    print("Iniciando verificaciones de la Fase 2.4.1...")
    init_db()

    # 1. Probar backend/set_superuser.py funcional con pipe
    admin_pw = "admin_super_secret_pw"
    proc = subprocess.run(
        [sys.executable, "-m", "backend.set_superuser"],
        input=f"{admin_pw}\n".encode("utf-8"),
        capture_output=True,
        check=True,
    )
    assert proc.returncode == 0, f"set_superuser falló: {proc.stderr.decode()}"
    with get_db() as db:
        admin_row = db.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        assert admin_row is not None and admin_row["is_superuser"] == 1
    print("[OK   ] 1. backend/set_superuser.py funcional (stdin pipe)")

    # 2. Login admin desde IP no-loopback simulada -> 403 SUPERUSER_IP_FORBIDDEN
    try:
        await auth_login(
            LoginIn(username="admin", password=admin_pw),
            request=MockRequest("198.51.100.24"),
        )
        assert False, "Debió rechazar login de superusuario desde IP no permitida"
    except ApiError as e:
        assert e.status_code == 403
        assert e.code == "SUPERUSER_IP_FORBIDDEN"
    print("[OK   ] 2. Login admin desde IP no-loopback simulada -> 403 SUPERUSER_IP_FORBIDDEN")

    # 3. Login admin desde loopback -> 200 OK
    admin_login = await auth_login(
        LoginIn(username="admin", password=admin_pw),
        request=MockRequest("127.0.0.1"),
    )
    admin_token = admin_login["token"]
    me_admin = await auth_me(admin_token)
    assert me_admin["is_superuser"] is True
    print("[OK   ] 3. Login admin desde loopback y verify is_superuser=True")

    # Registrar usuarios de prueba: DM1, DM2, Player1, Player2
    async def get_or_create_user(uname, dname, pw="pass123456"):
        try:
            r = await auth_register(RegisterIn(username=uname, display_name=dname, password=pw))
            return r["user_id"], r["token"]
        except ApiError:
            l = await auth_login(LoginIn(username=uname, password=pw), request=MockRequest("127.0.0.1"))
            return l["user_id"], l["token"]

    dm1_id, dm1_token = await get_or_create_user("dm_camp1_user", "DM Campana 1")
    dm2_id, dm2_token = await get_or_create_user("dm_camp2_user", "DM Campana 2")
    p1_id, p1_token = await get_or_create_user("player1_user", "Jugador 1")
    p2_id, p2_token = await get_or_create_user("player2_user", "Jugador 2")

    # Crear Campaña 1 (DM1) y Campaña 2 (DM2)
    with get_db() as db:
        c1 = db.execute(
            "INSERT INTO campaigns (name, dm_user_id, status, created_at) VALUES ('Campana 1', ?, 'active', datetime('now'))",
            (dm1_id,),
        )
        camp1_id = c1.lastrowid
        db.execute(
            "INSERT OR IGNORE INTO campaign_members (campaign_id, user_id, role, joined_at) VALUES (?, ?, 'dm', datetime('now'))",
            (camp1_id, dm1_id),
        )

        c2 = db.execute(
            "INSERT INTO campaigns (name, dm_user_id, status, created_at) VALUES ('Campana 2', ?, 'active', datetime('now'))",
            (dm2_id,),
        )
        camp2_id = c2.lastrowid
        db.execute(
            "INSERT OR IGNORE INTO campaign_members (campaign_id, user_id, role, joined_at) VALUES (?, ?, 'dm', datetime('now'))",
            (camp2_id, dm2_id),
        )

    # 4. DM1 edita ficha de un PJ de su campaña -> 200 OK
    # Player1 crea personaje en Campana 1
    char1 = await characters_create(
        CharacterIn(name="Guerrero Valiente", level=2, dex_mod=2, hp_max=20, campaign_id=camp1_id),
        x_user_token=p1_token,
    )
    char1_id = char1["id"]

    updated_char1 = await characters_update(
        char1_id,
        CharacterIn(name="Guerrero Valiente Editado", level=3, dex_mod=2, hp_max=25),
        x_user_token=dm1_token,
    )
    assert updated_char1["name"] == "Guerrero Valiente Editado"
    assert updated_char1["level"] == 3
    print("[OK   ] 4. DM edita ficha de un PJ de su campaña -> 200 OK")

    # 5. DM2 intenta editar ficha de PJ de Campana 1 -> 403 FORBIDDEN
    try:
        await characters_update(
            char1_id,
            CharacterIn(name="Hackeado por DM2", level=20),
            x_user_token=dm2_token,
        )
        assert False, "DM2 no debió poder editar ficha de Campaña 1"
    except ApiError as e:
        assert e.status_code == 403
    print("[OK   ] 5. DM intenta editar ficha de PJ de otra campaña -> 403 FORBIDDEN")

    # 6. Ficha sin campaña: solo dueño o superusuario pueden editar
    char_no_camp = await characters_create(
        CharacterIn(name="PJ Solitario", level=1, dex_mod=1, hp_max=10),
        x_user_token=p2_token,
    )
    char_no_camp_id = char_no_camp["id"]

    try:
        await characters_update(
            char_no_camp_id,
            CharacterIn(name="Intento DM1", level=2),
            x_user_token=dm1_token,
        )
        assert False, "DM1 no debió poder editar ficha sin campaña"
    except ApiError as e:
        assert e.status_code == 403

    super_edited = await characters_update(
        char_no_camp_id,
        CharacterIn(name="PJ Solitario Bendecido", level=5),
        x_user_token=admin_token,
    )
    assert super_edited["name"] == "PJ Solitario Bendecido"
    print("[OK   ] 6. Edición de ficha sin campaña por superusuario -> 200 OK")

    # 7. Crear sesión de combate en Campaña 1 y solicitar iniciativa interactiva
    import secrets
    session_code = f"S{secrets.token_hex(2).upper()}"
    with get_db() as db:
        s_cur = db.execute(
            "INSERT INTO sessions (code, status, round, dm_token, campaign_id, created_by_user_id, created_at) "
            "VALUES (?, 'active', 1, '', ?, ?, datetime('now'))",
            (session_code, camp1_id, dm1_id),
        )
        s1_id = s_cur.lastrowid

        # Enemigo 1: Trasgo (kind='enemy', dex_mod=2)
        c_enemy = db.execute(
            "INSERT INTO combatants (session_id, name, hp_max, hp_current, initiative, kind, dex_mod, created_at) "
            "VALUES (?, 'Trasgo 1', 7, 7, 10, 'enemy', 2, datetime('now'))",
            (s1_id,),
        )
        enemy_id = c_enemy.lastrowid

        # Jugador 1: Guerrero vinculado (kind='pc', dex_mod=3, character_id=char1_id, user_id=p1_id)
        c_p1 = db.execute(
            "INSERT INTO combatants (session_id, name, hp_max, hp_current, initiative, kind, dex_mod, character_id, user_id, created_at) "
            "VALUES (?, 'Guerrero', 25, 25, 10, 'pc', 3, ?, ?, datetime('now'))",
            (s1_id, char1_id, p1_id),
        )
        comb_p1_id = c_p1.lastrowid

        # Jugador 2: Mago (kind='pc', dex_mod=1, user_id=p2_id)
        c_p2 = db.execute(
            "INSERT INTO combatants (session_id, name, hp_max, hp_current, initiative, kind, dex_mod, user_id, created_at) "
            "VALUES (?, 'Mago', 15, 15, 10, 'pc', 1, ?, datetime('now'))",
            (s1_id, p2_id),
        )
        comb_p2_id = c_p2.lastrowid

    # DM1 solicita tirar iniciativa
    req_res = await initiative_request_create(s1_id, x_user_token=dm1_token)
    req_id = req_res["request_id"]

    with get_db() as db:
        # Verificar que el enemigo tiene tirada resuelta
        roll_enemy = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (req_id, enemy_id),
        ).fetchone()
        assert roll_enemy is not None
        assert roll_enemy["status"] == "rolled"
        assert roll_enemy["roll_value"] is not None
        assert roll_enemy["total"] == roll_enemy["roll_value"] + 2

        # Verificar que los PJs están en 'pending'
        roll_p1 = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (req_id, comb_p1_id),
        ).fetchone()
        assert roll_p1["status"] == "pending"

        roll_p2 = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (req_id, comb_p2_id),
        ).fetchone()
        assert roll_p2["status"] == "pending"
    print("[OK   ] 7. Request iniciativa: enemigo auto-tirado, jugadores en pending")

    # 8. Submit del jugador 1 (d20 = 14, dex_mod = 2 del PJ -> total = 16)
    roll_res = await initiative_roll_submit(
        InitiativeRollIn(request_id=req_id, combatant_id=comb_p1_id, roll_value=14),
        x_user_token=p1_token,
    )
    assert roll_res["dex_mod"] == 2
    assert roll_res["total"] == 16
    assert roll_res["roll_value"] == 14
    with get_db() as db:
        c_row = db.execute("SELECT initiative FROM combatants WHERE id=?", (comb_p1_id,)).fetchone()
        assert c_row["initiative"] == 16
    print("[OK   ] 8. Submit del jugador: cálculo en servidor (14 + 2 = 16)")

    # 9. Submit duplicado del mismo jugador rechazado con 409
    try:
        await initiative_roll_submit(
            InitiativeRollIn(request_id=req_id, combatant_id=comb_p1_id, roll_value=18),
            x_user_token=p1_token,
        )
        assert False, "Debió rechazar submit duplicado"
    except ApiError as e:
        assert e.status_code == 409
        assert e.code == "ALREADY_ROLLED"
    print("[OK   ] 9. Submit duplicado rechazado con error controlado (409)")

    # 10. DM salta la tirada del Jugador 2 (toma 10: 10 + 1 = 11)
    skip_res = await initiative_roll_skip(
        InitiativeActionIn(request_id=req_id, combatant_id=comb_p2_id),
        x_user_token=dm1_token,
    )
    assert skip_res["total"] == 11
    assert skip_res["roll_value"] == 10
    with get_db() as db:
        req_status = db.execute("SELECT status FROM initiative_requests WHERE id=?", (req_id,)).fetchone()["status"]
        assert req_status == "completed"
    print("[OK   ] 10. DM salta tirada pendiente (toma 10) y request finaliza en completed")

    # 11. Reset por segundo request de iniciativa cancela requests abiertos
    req2_res = await initiative_request_create(s1_id, x_user_token=dm1_token)
    req2_id = req2_res["request_id"]
    with get_db() as db:
        r2 = db.execute("SELECT status FROM initiative_requests WHERE id=?", (req2_id,)).fetchone()
        assert r2["status"] == "active"

    # Lanzar nuevo request mientras req2 sigue abierto/activo
    req3_res = await initiative_request_create(s1_id, x_user_token=dm1_token)
    req3_id = req3_res["request_id"]
    assert req3_id != req2_id
    with get_db() as db:
        old_req = db.execute("SELECT status FROM initiative_requests WHERE id=?", (req2_id,)).fetchone()
        assert old_req["status"] == "cancelled"
        new_req = db.execute("SELECT status FROM initiative_requests WHERE id=?", (req3_id,)).fetchone()
        assert new_req["status"] == "active"
    print("[OK   ] 11. Reset por segundo request cancela el anterior abierto e inicia nuevo")

    # 12. Superusuario fuerza tirada de un jugador fuera de su campaña -> 200 OK
    # Admin no pertenece a Campaña 1, pero puede forzar la tirada de comb_p1_id
    force_res = await initiative_roll_force(
        InitiativeActionIn(request_id=req3_id, combatant_id=comb_p1_id),
        x_user_token=admin_token,
    )
    assert force_res["ok"] is True
    assert force_res["total"] == force_res["roll_value"] + 2
    with get_db() as db:
        # Verificar que se registró evento admin_action
        admin_event = db.execute(
            "SELECT * FROM events WHERE session_id=? AND kind='admin_action' ORDER BY id DESC LIMIT 1",
            (s1_id,),
        ).fetchone()
        assert admin_event is not None
        assert "Superusuario 'admin' forzó tirada" in admin_event["message"]
    print("[OK   ] 12. Superusuario fuerza tirada fuera de su campaña -> 200 + evento admin_action")

    # 13. Cancel por cierre de sesión
    await close_session(x_user_token=dm1_token)
    with get_db() as db:
        closed_req = db.execute("SELECT status FROM initiative_requests WHERE id=?", (req3_id,)).fetchone()
        assert closed_req["status"] == "cancelled"
        pending_rolls = db.execute(
            "SELECT COUNT(*) AS c FROM initiative_rolls WHERE request_id=? AND status='pending'",
            (req3_id,),
        ).fetchone()["c"]
        assert pending_rolls == 0
    print("[OK   ] 13. Cancel por cierre de sesión verificado")

    # 14. Cache-busting ?v=2.4 en frontend/dm.html y frontend/player.html
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dm_html = open(os.path.join(base_dir, "frontend", "dm.html"), encoding="utf-8").read()
    player_html = open(os.path.join(base_dir, "frontend", "player.html"), encoding="utf-8").read()
    assert "?v=2.4" in dm_html, "Falta ?v=2.4 en dm.html"
    assert "?v=2.4" in player_html, "Falta ?v=2.4 en player.html"
    print("[OK   ] 14. Cache-busting ?v=2.4 verificado en dm.html y player.html")

    # 15. Validación roll_value fuera de [1,20] devuelve 400 INVALID_ROLL y no altera iniciativa
    s2_code = f"S{secrets.token_hex(2).upper()}"
    with get_db() as db:
        s2_cur = db.execute(
            "INSERT INTO sessions (code, status, round, dm_token, campaign_id, created_by_user_id, created_at) "
            "VALUES (?, 'active', 1, '', ?, ?, datetime('now'))",
            (s2_code, camp1_id, dm1_id),
        )
        s2_id = s2_cur.lastrowid
        # Enemigo (dex_mod=1)
        c_enemy2 = db.execute(
            "INSERT INTO combatants (session_id, name, hp_max, hp_current, initiative, kind, dex_mod, created_at) "
            "VALUES (?, 'Orco', 15, 15, 7, 'enemy', 1, datetime('now'))",
            (s2_id,),
        ).lastrowid
        # Jugador 1 (dex_mod=2, iniciativa previa=5)
        c_p1_s2 = db.execute(
            "INSERT INTO combatants (session_id, name, hp_max, hp_current, initiative, kind, dex_mod, character_id, user_id, created_at) "
            "VALUES (?, 'Guerrero 2', 25, 25, 5, 'pc', 2, ?, ?, datetime('now'))",
            (s2_id, char1_id, p1_id),
        ).lastrowid
        # Jugador 2 (dex_mod=0)
        c_p2_s2 = db.execute(
            "INSERT INTO combatants (session_id, name, hp_max, hp_current, initiative, kind, dex_mod, user_id, created_at) "
            "VALUES (?, 'Mago 2', 15, 15, 0, 'pc', 0, ?, datetime('now'))",
            (s2_id, p2_id),
        ).lastrowid

    req4_res = await initiative_request_create(s2_id, x_user_token=dm1_token)
    req4_id = req4_res["request_id"]

    # Probar roll_value = 0 (menor a 1)
    try:
        await initiative_roll_submit(
            InitiativeRollIn(request_id=req4_id, combatant_id=c_p1_s2, roll_value=0),
            x_user_token=p1_token,
        )
        assert False, "Debió rechazar roll_value=0"
    except ApiError as e:
        assert e.status_code == 400
        assert e.code == "INVALID_ROLL"

    # Probar roll_value = 21 (mayor a 20)
    try:
        await initiative_roll_submit(
            InitiativeRollIn(request_id=req4_id, combatant_id=c_p1_s2, roll_value=21),
            x_user_token=p1_token,
        )
        assert False, "Debió rechazar roll_value=21"
    except ApiError as e:
        assert e.status_code == 400
        assert e.code == "INVALID_ROLL"

    # Verificar que la iniciativa del combatiente NO se modificó (sigue siendo 5) y la tirada sigue pending
    with get_db() as db:
        c_row = db.execute("SELECT initiative FROM combatants WHERE id=?", (c_p1_s2,)).fetchone()
        assert c_row["initiative"] == 5
        r_row = db.execute(
            "SELECT status FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (req4_id, c_p1_s2),
        ).fetchone()
        assert r_row["status"] == "pending"
    print("[OK   ] 15. Validación roll_value fuera de [1,20] devuelve 400 INVALID_ROLL y no altera iniciativa")

    # 16. Trazabilidad explícita de source en initiative_rolls
    # 16.1 Jugador 1 envía tirada válida -> source='player'
    await initiative_roll_submit(
        InitiativeRollIn(request_id=req4_id, combatant_id=c_p1_s2, roll_value=15),
        x_user_token=p1_token,
    )
    # 16.2 DM fuerza la tirada del Jugador 2 -> source='dm_force'
    await initiative_roll_force(
        InitiativeActionIn(request_id=req4_id, combatant_id=c_p2_s2),
        x_user_token=dm1_token,
    )
    # Verificaciones en DB de todas las fuentes
    with get_db() as db:
        # npc_auto: enemigo auto-tirado con user_id IS NULL
        r_npc = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (req4_id, c_enemy2),
        ).fetchone()
        assert r_npc["source"] == "npc_auto"
        assert r_npc["user_id"] is None
        assert r_npc["status"] == "rolled"

        # player: jugador 1
        r_player = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (req4_id, c_p1_s2),
        ).fetchone()
        assert r_player["source"] == "player"
        assert r_player["status"] == "rolled"

        # dm_force: DM forzó la tirada
        r_dm_force = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (req4_id, c_p2_s2),
        ).fetchone()
        assert r_dm_force["source"] == "dm_force"
        assert r_dm_force["status"] == "forced"

        # dm_skip: verificado de req_id / comb_p2_id (test 10)
        r_dm_skip = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (req_id, comb_p2_id),
        ).fetchone()
        assert r_dm_skip["source"] == "dm_skip"
        assert r_dm_skip["status"] == "skipped"

        # superuser_force: verificado de req3_id / comb_p1_id (test 12)
        r_su_force = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (req3_id, comb_p1_id),
        ).fetchone()
        assert r_su_force["source"] == "superuser_force"
        assert r_su_force["status"] == "forced"
    print("[OK   ] 16. Trazabilidad explícita de source (npc_auto, player, dm_force, dm_skip, superuser_force)")

    print("\nTODAS LAS PRUEBAS DE LA FASE 2.4.1 COMPLETADAS CON ÉXITO")


if __name__ == "__main__":
    asyncio.run(run_checks())
