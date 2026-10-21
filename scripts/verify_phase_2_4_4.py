#!/usr/bin/env python3
"""Script de verificación automatizada para la Fase 2.4.4 (Editor de Monedas y Riqueza).

Cubre:
1. Normalización y valores por defecto en calculate_character_data (cp, sp, ep, gp, pp a 0, clamp negatives).
2. Creación de personaje vía POST /api/characters con currency por defecto.
3. Actualización de monedas vía PUT /api/characters/{id} y persistencia.
4. Protección contra valores negativos (clamping a 0).
5. Inclusión de currency en build_state para rol DM y para el jugador dueño (is_me).
6. Ocultamiento de currency a otros jugadores no dueños.
7. Verificación de presencia de elementos UI en frontend/player.js, frontend/dm.js y frontend/app.css.
"""
import asyncio
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import (
    calculate_character_data,
    build_state,
    broadcast_state,
    characters_create,
    characters_get,
    characters_update,
    join,
    JoinIn,
    CharacterIn,
    get_db,
    init_db,
    auth_register,
    RegisterIn,
    create_campaign,
    create_session_in_campaign,
    now,
)


async def run_checks():
    print("Iniciando verificaciones de la Fase 2.4.4 (Editor de Monedas)...")
    init_db()

    # -------------------------------------------------------------
    # 1. Normalización en calculate_character_data
    # -------------------------------------------------------------
    _, _, data_empty = calculate_character_data(level=1, class_slug="fighter", race_slug="human", dex_mod=None, hp_max=None, data={})
    assert "currency" in data_empty, "calculate_character_data debe crear el objeto currency"
    assert data_empty["currency"] == {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}, "Monedas por defecto deben ser 0"

    # Con valores parciales, strings y negativos
    _, _, data_partial = calculate_character_data(
        level=1,
        class_slug=None,
        race_slug=None,
        dex_mod=None,
        hp_max=None,
        data={"currency": {"gp": "45", "sp": 12, "cp": -5}},
    )
    assert data_partial["currency"]["gp"] == 45, "gp debe convertirse a entero 45"
    assert data_partial["currency"]["sp"] == 12, "sp debe ser 12"
    assert data_partial["currency"]["cp"] == 0, "Valores negativos deben clamp a 0"
    assert data_partial["currency"]["ep"] == 0, "Monedas ausentes deben ser 0"
    assert data_partial["currency"]["pp"] == 0, "Monedas ausentes deben ser 0"
    print("[OK   ] 1. calculate_character_data normaliza currency y clamp valores negativos a 0")

    # -------------------------------------------------------------
    # 2. Creación de personaje vía POST /api/characters
    # -------------------------------------------------------------
    ts = int(asyncio.get_event_loop().time() * 1000)
    user_name = f"tester_coin_{ts}"
    reg = await auth_register(RegisterIn(username=user_name, password="Password123!", display_name="Monedero"))
    token = reg["token"]
    user_id = reg["user_id"]

    new_char = await characters_create(
        CharacterIn(name="Aventurero Acaudalado", level=3, class_slug="rogue", race_slug="elf"),
        x_user_token=token,
    )
    char_id = new_char["id"]
    assert "currency" in new_char["data"], "El JSON data del personaje creado debe contener currency"
    assert new_char["data"]["currency"] == {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}
    print("[OK   ] 2. POST /api/characters inicializa currency por defecto a 0")

    # -------------------------------------------------------------
    # 3. Actualización de monedas vía PUT /api/characters/{id}
    # -------------------------------------------------------------
    update_payload = CharacterIn(
        name="Aventurero Acaudalado",
        level=3,
        class_slug="rogue",
        race_slug="elf",
        data={
            **new_char["data"],
            "currency": {"cp": 100, "sp": 50, "ep": 5, "gp": 250, "pp": 2},
        },
    )
    updated_char = await characters_update(char_id, update_payload, x_user_token=token)
    assert updated_char["data"]["currency"] == {"cp": 100, "sp": 50, "ep": 5, "gp": 250, "pp": 2}

    # Verificar lectura limpia con GET
    fetched = await characters_get(char_id, x_user_token=token)
    assert fetched["data"]["currency"] == {"cp": 100, "sp": 50, "ep": 5, "gp": 250, "pp": 2}
    print("[OK   ] 3. PUT /api/characters/{id} y GET /api/characters/{id} persisten las monedas")

    # -------------------------------------------------------------
    # 4. Clamping de valores negativos en PUT
    # -------------------------------------------------------------
    neg_payload = CharacterIn(
        name="Aventurero Acaudalado",
        level=3,
        data={
            **new_char["data"],
            "currency": {"cp": -10, "sp": 5, "ep": -1, "gp": 100, "pp": -99},
        },
    )
    neg_char = await characters_update(char_id, neg_payload, x_user_token=token)
    assert neg_char["data"]["currency"]["cp"] == 0
    assert neg_char["data"]["currency"]["ep"] == 0
    assert neg_char["data"]["currency"]["pp"] == 0
    assert neg_char["data"]["currency"]["gp"] == 100
    print("[OK   ] 4. PUT /api/characters/{id} descarta valores negativos correctamente")

    # -------------------------------------------------------------
    # 5. build_state con currency para DM y dueño (is_me)
    # -------------------------------------------------------------
    with get_db() as db:
        camp = create_campaign(db, user_id, f"Campaña Monedas {ts}")
        sess = create_session_in_campaign(db, camp["id"], user_id)
        session_id = sess["id"]
        session_code = sess["code"]

    joined = await join(JoinIn(code=session_code, name="Jugador Rico"), x_user_token=token)
    player_id = joined["player_id"]

    with get_db() as db:
        db.execute(
            "INSERT INTO combatants (session_id, name, hp_current, hp_max, initiative, kind, character_id, user_id, player_id, created_at) "
            "VALUES (?, 'Aventurero Acaudalado', 20, 20, 15, 'pc', ?, ?, ?, datetime('now'))",
            (session_id, char_id, user_id, player_id),
        )

    with get_db() as db:
        session_row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        combatants = db.execute(
            """
            SELECT c.*, ch.data AS character_data
            FROM combatants c
            LEFT JOIN characters ch ON c.character_id = ch.id
            WHERE c.session_id=?
            """,
            (session_id,),
        ).fetchall()
        players_rows = db.execute("SELECT id, name FROM players WHERE session_id=? ORDER BY id", (session_id,)).fetchall()

    # Estado visto por el DM
    dm_state = build_state(session_row, combatants, players_rows, role="dm", player_id=None)
    pc_in_dm = [c for c in dm_state["combatants"] if c["kind"] == "pc"][0]
    assert pc_in_dm["currency"] is not None, "El DM debe recibir el objeto currency del PJ"
    assert pc_in_dm["currency"]["gp"] == 100, "El DM debe ver 100 gp"
    print("[OK   ] 5. build_state expone currency de los PJs al DM")

    # Estado visto por el dueño (is_me)
    owner_state = build_state(session_row, combatants, players_rows, role="player", player_id=player_id)
    pc_in_owner = [c for c in owner_state["combatants"] if c["kind"] == "pc"][0]
    assert pc_in_owner["is_me"] is True
    assert pc_in_owner["currency"] is not None
    assert pc_in_owner["currency"]["gp"] == 100
    print("[OK   ] 6. build_state expone currency al jugador dueño (is_me=True)")

    # Estado visto por otro jugador
    other_state = build_state(session_row, combatants, players_rows, role="player", player_id=999999)
    pc_in_other = [c for c in owner_state["combatants"] if c["kind"] == "pc"][0]
    other_pc = [c for c in other_state["combatants"] if c["kind"] == "pc"][0]
    assert other_pc["is_me"] is False
    assert other_pc["currency"] is None, "Otros jugadores no deben ver las monedas de sus compañeros"
    print("[OK   ] 7. build_state oculta currency a otros jugadores (is_me=False)")

    # -------------------------------------------------------------
    # 8. Verificación de archivos frontend
    # -------------------------------------------------------------
    with open("frontend/player.js", "r", encoding="utf-8") as f:
        pjs = f.read()
        assert "sheet-currency-grid" in pjs, "player.js debe incluir sheet-currency-grid"
        assert "btn-coin-step" in pjs, "player.js debe incluir botones btn-coin-step (+/-)"
        assert "coin-cp" in pjs and "coin-gp" in pjs, "player.js debe enlazar inputs de monedas"
        assert "scheduleCurrencySave" in pjs, "player.js debe incluir función con debounce de guardado"

    with open("frontend/dm.js", "r", encoding="utf-8") as f:
        dmjs = f.read()
        assert "gold-badge" in dmjs, "dm.js debe incluir insignia gold-badge"
        assert "po" in dmjs and "🪙" in dmjs, "dm.js debe mostrar icono y texto de oro"

    with open("frontend/app.css", "r", encoding="utf-8") as f:
        css = f.read()
        assert ".sheet-currency-grid" in css, "app.css debe incluir estilos para .sheet-currency-grid"
        assert ".currency-card" in css, "app.css debe incluir estilos para .currency-card"
        assert ".gold-badge" in css, "app.css debe incluir estilos para .gold-badge"

    print("[OK   ] 8. Presencia de componentes, debounce y estilos en frontend verificados")
    print("\nTODAS LAS PRUEBAS DE LA FASE 2.4.4 COMPLETADAS CON ÉXITO")


if __name__ == "__main__":
    asyncio.run(run_checks())
