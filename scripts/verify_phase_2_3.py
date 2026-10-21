#!/usr/bin/env python3
"""Script de verificación automatizada para la Fase 2.3 (Mini-ficha de Personaje)."""
import asyncio
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import (
    characters_create, characters_list, characters_get,
    characters_update, characters_delete, link_my_character,
    CharacterIn, LinkCharacterIn, auth_register, auth_login,
    RegisterIn, LoginIn, ApiError, join, JoinIn, player_me
)
from backend.db import get_db, init_db


async def run_checks():
    print("Iniciando verificaciones de la Fase 2.3...")

    # 1. Verificar esquema en dnd.db
    with get_db() as db:
        cols = {row[1]: row[2] for row in db.execute("PRAGMA table_info(characters)").fetchall()}
        expected_cols = ["id", "campaign_id", "user_id", "name", "level", "class_slug", "race_slug", "dex_mod", "hp_max", "data", "created_at", "updated_at"]
        for c in expected_cols:
            assert c in cols, f"Falta columna {c} en characters"
    print("[OK   ] 1. Esquema de tabla 'characters' en dnd.db es correcto")

    # 2. Registrar usuario de prueba
    username = "pj_test_user_23"
    password = "password12345"
    try:
        reg = await auth_register(RegisterIn(username=username, display_name="Heroe Fase 2.3", password=password))
        token = reg["token"]
        uid = reg["user_id"]
    except ApiError:
        log = await auth_login(LoginIn(username=username, password=password))
        token = log["token"]
        uid = log["user_id"]
    print(f"[OK   ] 2. Usuario registrado autenticado (uid={uid})")

    # 3. Intentar crear ficha como invitado o sin token válido -> 401/403
    try:
        await characters_create(CharacterIn(name="PJ Fantasma"), x_user_token="token_invalido_123")
        assert False, "Debió rechazar token inválido"
    except ApiError as e:
        assert e.status_code == 401
    print("[OK   ] 3. Control de acceso para usuarios no autenticados (401)")

    # 4. Crear personaje completo y verificar cálculos automáticos de SRD
    char_payload = CharacterIn(
        name="Elminster Junior",
        level=3,
        class_slug="wizard",
        race_slug="human",
        data={
            "stats": {
                "strength": 10,
                "dexterity": 14,
                "constitution": 14,
                "intelligence": 16,
                "wisdom": 12,
                "charisma": 8
            },
            "weapons": [
                {"equipment_slug": "dagger", "name": "Daga", "damage": "1d4", "damage_type": "perforante"}
            ],
            "spells": [
                {"spell_slug": "fireball", "name": "Bola de Fuego", "level": 3, "school": "Evocación"}
            ]
        }
    )
    char = await characters_create(char_payload, x_user_token=token)
    cid = char["id"]
    assert char["name"] == "Elminster Junior"
    assert char["level"] == 3
    assert char["dex_mod"] == 2
    # Wizard hit die es 6. CON mod es +2.
    # HP nivel 1: 6 + 2 = 8
    # HP niveles 2-3: 2 * (6//2 + 1 + 2) = 2 * 6 = 12
    # Total HP = 20
    assert char["hp_max"] == 20, f"Esperado 20 HP, obtenido {char['hp_max']}"
    assert char["data"]["hit_die"] == 6
    assert char["data"]["proficiency_bonus"] == 2
    assert char["data"]["modifiers"]["int_mod"] == 3
    # Wizard spellcasting ability es int -> spell_dc = 8 + 2 (prof) + 3 (int) = 13
    assert char["data"]["spell_dc"] == 13, f"Esperado CD 13, obtenido {char['data']['spell_dc']}"
    assert char["data"]["spell_attack_bonus"] == 5, f"Esperado Bono +5, obtenido {char['data']['spell_attack_bonus']}"
    print(f"[OK   ] 4. Ficha creada con auto-cálculos SRD (HP={char['hp_max']}, CA={char['data']['armor_class']}, CD_Magia={char['data']['spell_dc']})")

    # 5. Listar personajes del usuario
    lst = await characters_list(x_user_token=token)
    assert any(c["id"] == cid for c in lst["items"])
    print(f"[OK   ] 5. Listado de personajes del usuario correcto ({len(lst['items'])} encontrados)")

    # 6. Consultar personaje por ID
    got = await characters_get(cid, x_user_token=token)
    assert got["id"] == cid
    assert got["class_slug"] == "wizard"
    print("[OK   ] 6. Consulta GET /api/characters/{id} verificada")

    # 7. Actualizar ficha (subir a nivel 4)
    update_payload = CharacterIn(
        name="Elminster el Sabio",
        level=4,
        class_slug="wizard",
        race_slug="human",
        data=got["data"]
    )
    updated = await characters_update(cid, update_payload, x_user_token=token)
    assert updated["name"] == "Elminster el Sabio"
    assert updated["level"] == 4
    # Nivel 4 HP: 8 + 3 * 6 = 26
    assert updated["hp_max"] == 26
    print("[OK   ] 7. Actualización PUT /api/characters/{id} verificada (nivel 4, HP=26)")

    # 8. Eliminar personaje y comprobar 404
    del_res = await characters_delete(cid, x_user_token=token)
    assert del_res["ok"] is True
    try:
        await characters_get(cid, x_user_token=token)
        assert False, "Debió responder 404"
    except ApiError as e:
        assert e.status_code == 404
    print("[OK   ] 8. Eliminación DELETE /api/characters/{id} verificada")

    print("\nTODAS LAS PRUEBAS DE LA FASE 2.3 COMPLETADAS CON ÉXITO (8/8 OK)")


if __name__ == "__main__":
    asyncio.run(run_checks())
