"""API REST + WebSocket del MVP de combate D&D 5e."""
import datetime
import io
import json
import os
import random
import re
import secrets
import socket
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import segno

import config
from backend.db import get_db, get_srd_db, init_db
from backend.ws import ConnectionManager
from backend.auth import (
    ApiError, create_user_session, ensure_dm_user, ensure_user_session,
    hash_password, require_user, require_user_campaign_dm,
    require_user_campaign_member, verify_password,
)
from backend.campaigns import (
    add_member, create_campaign, create_session_in_campaign,
    get_campaign, list_campaigns_for_user, list_members,
    list_sessions_in_campaign, slugify,
)

BASE_DIR = config.BASE_DIR
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = FastAPI(title="DnD 5e Combat MVP")
manager = ConnectionManager()

init_db()


@app.exception_handler(ApiError)
async def _apierror_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "code": exc.code},
    )


# ---------------------------------------------------------------- utilidades

def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def log_event(db, session_id, kind, message):
    db.execute(
        "INSERT INTO events (session_id, ts, kind, message) VALUES (?,?,?,?)",
        (session_id, now(), kind, message),
    )


def fetch_active_session(db):
    return db.execute(
        "SELECT * FROM sessions WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()


def _is_user_authorized_dm(db, session, user_row) -> bool:
    if user_row["is_superuser"] == 1:
        return True
    if session["campaign_id"]:
        m = db.execute(
            "SELECT 1 FROM campaign_members WHERE campaign_id=? AND user_id=? AND role='dm'",
            (session["campaign_id"], user_row["id"]),
        ).fetchone()
        if m:
            return True
    if session["created_by_user_id"] and session["created_by_user_id"] == user_row["id"]:
        return True
    if user_row["username"] == "dm":
        return True
    return False


def _clean_token(t) -> Optional[str]:
    if isinstance(t, str) and t.strip():
        return t.strip()
    return None


def require_dm(db, x_dm_token: Optional[str] = None, x_user_token: Optional[str] = None):
    x_dm_token = _clean_token(x_dm_token)
    x_user_token = _clean_token(x_user_token)

    session = fetch_active_session(db)
    if session is None:
        raise HTTPException(status_code=404, detail="No hay sesion activa")

    # 1. Prioridad: X-User-Token si viene especificado
    if x_user_token:
        user_row = db.execute(
            "SELECT u.* FROM users u JOIN user_sessions us ON us.user_id=u.id "
            "WHERE us.token=? AND us.revoked_at IS NULL AND us.expires_at > ?",
            (x_user_token, now()),
        ).fetchone()
        if user_row and _is_user_authorized_dm(db, session, user_row):
            return session

    # 2. Si x_dm_token fue provisto, verificar si es en realidad un token de usuario o el legacy dm_token
    if x_dm_token:
        user_row = db.execute(
            "SELECT u.* FROM users u JOIN user_sessions us ON us.user_id=u.id "
            "WHERE us.token=? AND us.revoked_at IS NULL AND us.expires_at > ?",
            (x_dm_token, now()),
        ).fetchone()
        if user_row and _is_user_authorized_dm(db, session, user_row):
            return session

        # Legacy fallback
        if session["dm_token"] and x_dm_token == session["dm_token"]:
            return session

    raise HTTPException(status_code=403, detail="Token de DM invalido")


def require_any_dm(db, x_dm_token: Optional[str] = None, x_user_token: Optional[str] = None):
    """Acepta cualquier DM (activo o cerrado) por X-User-Token o legacy dm_token."""
    x_dm_token = _clean_token(x_dm_token)
    x_user_token = _clean_token(x_user_token)
    token = x_user_token or x_dm_token
    if not token:
        raise HTTPException(status_code=403, detail="Token de DM requerido")

    user_row = db.execute(
        "SELECT u.* FROM users u JOIN user_sessions us ON us.user_id=u.id "
        "WHERE us.token=? AND us.revoked_at IS NULL AND us.expires_at > ?",
        (token, now()),
    ).fetchone()
    if user_row:
        if user_row["is_superuser"] == 1 or user_row["username"] == "dm":
            return user_row
        m = db.execute(
            "SELECT 1 FROM campaign_members WHERE user_id=? AND role='dm'",
            (user_row["id"],),
        ).fetchone()
        if m:
            return user_row

    row = db.execute("SELECT 1 FROM sessions WHERE dm_token=? AND dm_token != ''", (token,)).fetchone()
    if row is not None:
        return None

    raise HTTPException(status_code=403, detail="Token de DM invalido")


CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code(db) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not db.execute("SELECT 1 FROM sessions WHERE code=?", (code,)).fetchone():
            return code


def apply_hp(db, session, combatant, delta=None, set_to=None):
    old = combatant["hp_current"]
    new = int(set_to) if set_to is not None else old + int(delta or 0)
    new = max(0, min(combatant["hp_max"], new))
    if new == old:
        return
    db.execute("UPDATE combatants SET hp_current=? WHERE id=?", (new, combatant["id"]))
    db.execute(
        "INSERT INTO hp_history (combatant_id, old_hp, new_hp, ts) VALUES (?,?,?,?)",
        (combatant["id"], old, new, now()),
    )
    if new < old:
        log_event(db, session["id"], "damage",
                  f"{old - new} de dano a {combatant['name']} ({old} -> {new})")
    else:
        log_event(db, session["id"], "heal",
                  f"{new - old} de curacion a {combatant['name']} ({old} -> {new})")
    if old > 0 and new <= 0:
        log_event(db, session["id"], "death", f"{combatant['name']} ha caido")


ABILITY_NAMES = {
    "str": "Fuerza",
    "dex": "Destreza",
    "con": "Constitución",
    "int": "Inteligencia",
    "wis": "Sabiduría",
    "cha": "Carisma",
}

SKILL_INFO = {
    "athletics": {"name": "Atletismo", "ability": "str"},
    "acrobatics": {"name": "Acrobacias", "ability": "dex"},
    "sleight-of-hand": {"name": "Juego de Manos", "ability": "dex"},
    "stealth": {"name": "Sigilo", "ability": "dex"},
    "arcana": {"name": "Arcano", "ability": "int"},
    "history": {"name": "Historia", "ability": "int"},
    "investigation": {"name": "Investigación", "ability": "int"},
    "nature": {"name": "Naturaleza", "ability": "int"},
    "religion": {"name": "Religión", "ability": "int"},
    "animal-handling": {"name": "Trato con Animales", "ability": "wis"},
    "insight": {"name": "Perspicacia", "ability": "wis"},
    "medicine": {"name": "Medicina", "ability": "wis"},
    "perception": {"name": "Percepción", "ability": "wis"},
    "survival": {"name": "Supervivencia", "ability": "wis"},
    "deception": {"name": "Engaño", "ability": "cha"},
    "intimidation": {"name": "Intimidación", "ability": "cha"},
    "performance": {"name": "Actuación", "ability": "cha"},
    "persuasion": {"name": "Persuasión", "ability": "cha"},
}


def build_state(session, combatants, players, role, player_id):
    ordered = sorted(combatants, key=lambda c: (-c["initiative"], c["id"]))
    out = []
    for c in ordered:
        is_me = role == "player" and c["player_id"] is not None and c["player_id"] == player_id
        show_hp = (role == "dm") or is_me

        currency = None
        c_keys = c.keys() if hasattr(c, "keys") else []
        if "character_data" in c_keys and c["character_data"]:
            try:
                ch_data = json.loads(c["character_data"]) if isinstance(c["character_data"], str) else c["character_data"]
                if isinstance(ch_data, dict):
                    currency = ch_data.get("currency")
            except Exception:
                currency = None
        elif "currency" in c_keys:
            currency = c["currency"]

        out.append({
            "id": c["id"],
            "name": c["name"],
            "initiative": c["initiative"],
            "kind": c["kind"],
            "dead": c["hp_current"] <= 0,
            "linked_player_id": c["player_id"],
            "is_me": is_me,
            "hp_current": c["hp_current"] if show_hp else None,
            "hp_max": c["hp_max"] if show_hp else None,
            "currency": currency if (role == "dm" or is_me) else None,
        })
    # FIX B1: incluir campaign_id + campaign_join_code en state.session
    # para que el modal Compartir de /dm pueda construir la URL con
    # ?code=XXXXXX y el QR lo lleve. Ambos son nullable (sesiones legacy
    # con campaign_id=NULL). No rompe el contrato: solo AÑADE campos.
    campaign_id = None
    campaign_join_code = None
    keys = session.keys()
    if "campaign_id" in keys and session["campaign_id"] is not None:
        campaign_id = session["campaign_id"]
        with get_db() as db:
            row = db.execute(
                "SELECT join_code FROM campaigns WHERE id=?", (campaign_id,)
            ).fetchone()
            if row is not None:
                campaign_join_code = row["join_code"]

    active_req = None
    active_check = None
    with get_db() as db:
        req = db.execute(
            "SELECT * FROM initiative_requests WHERE session_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (session["id"],),
        ).fetchone()
        if req is not None:
            rolls = db.execute(
                """SELECT r.*, c.name AS combatant_name, c.kind 
                   FROM initiative_rolls r
                   JOIN combatants c ON c.id = r.combatant_id
                   WHERE r.request_id = ?
                   ORDER BY r.id ASC""",
                (req["id"],),
            ).fetchall()
            active_req = {
                "id": req["id"],
                "status": req["status"],
                "created_at": req["created_at"],
                "rolls": [
                    {
                        "id": r["id"],
                        "combatant_id": r["combatant_id"],
                        "combatant_name": r["combatant_name"],
                        "kind": r["kind"],
                        "user_id": r["user_id"],
                        "status": r["status"],
                        "source": r["source"] if "source" in r.keys() else "unknown",
                        "dex_mod": r["dex_mod"],
                        "roll_value": r["roll_value"],
                        "total": r["total"],
                    }
                    for r in rolls
                ],
                "pending_count": sum(1 for r in rolls if r["status"] == "pending"),
                "total_count": len(rolls),
            }

        c_req = db.execute(
            "SELECT * FROM check_requests WHERE session_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (session["id"],),
        ).fetchone()
        if c_req is not None:
            c_rolls = db.execute(
                """SELECT r.*, c.name AS combatant_name, c.kind 
                   FROM check_rolls r
                   JOIN combatants c ON c.id = r.combatant_id
                   WHERE r.request_id = ?
                   ORDER BY r.id ASC""",
                (c_req["id"],),
            ).fetchall()
            is_secret = bool(c_req["is_secret"])
            is_dm = (role == "dm")

            sk_info = SKILL_INFO.get(c_req["skill_slug"]) if c_req["skill_slug"] else None
            skill_name = sk_info["name"] if sk_info else None
            ability_name = ABILITY_NAMES.get(c_req["ability"], c_req["ability"].upper())

            active_check = {
                "id": c_req["id"],
                "ability": c_req["ability"],
                "ability_name": ability_name,
                "skill_slug": c_req["skill_slug"],
                "skill_name": skill_name,
                "dc": c_req["dc"] if (is_dm or not is_secret) else None,
                "is_secret": is_secret,
                "advantage_mode": c_req["advantage_mode"],
                "status": c_req["status"],
                "created_at": c_req["created_at"],
                "pending_count": sum(1 for r in c_rolls if r["status"] == "pending"),
                "total_count": len(c_rolls),
                "rolls": [
                    {
                        "id": r["id"],
                        "combatant_id": r["combatant_id"],
                        "combatant_name": r["combatant_name"],
                        "kind": r["kind"],
                        "user_id": r["user_id"],
                        "status": r["status"],
                        "source": r["source"] if "source" in r.keys() else "unknown",
                        "ability_mod": r["ability_mod"],
                        "prof_bonus": r["prof_bonus"],
                        "is_proficient": bool(r["is_proficient"]),
                        "total_mod": r["total_mod"],
                        "roll_value_1": r["roll_value_1"],
                        "roll_value_2": r["roll_value_2"],
                        "chosen_roll": r["chosen_roll"],
                        "total": r["total"],
                        "is_success": (bool(r["is_success"]) if r["is_success"] is not None else None) if (is_dm or not is_secret) else None,
                    }
                    for r in c_rolls
                ],
            }

    return {
        "type": "state",
        "session": {
            "id": session["id"],
            "code": session["code"],
            "status": session["status"],
            "round": session["round"],
            "turn_combatant_id": session["turn_combatant_id"],
            "campaign_id": campaign_id,
            "campaign_join_code": campaign_join_code,
        },
        "combatants": out,
        "players": [{"id": p["id"], "name": p["name"]} for p in players],
        "initiative_request": active_req,
        "check_request": active_check,
    }


async def broadcast_state(session_id: int):
    with get_db() as db:
        session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if session is None:
            return
        combatants = db.execute(
            """
            SELECT c.*, ch.data AS character_data
            FROM combatants c
            LEFT JOIN characters ch ON c.character_id = ch.id
            WHERE c.session_id=?
            """,
            (session_id,),
        ).fetchall()
        players = db.execute(
            "SELECT id, name FROM players WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()

    await manager.broadcast(
        session_id,
        lambda role, pid: build_state(session, combatants, players, role, pid),
    )


# ---------------------------------------------------------------- modelos

class JoinIn(BaseModel):
    code: str
    name: str


class CombatantIn(BaseModel):
    name: Optional[str] = None
    hp_max: Optional[int] = None
    initiative: int
    kind: str  # 'pc' | 'enemy'
    srd_index: Optional[str] = None


class HpIn(BaseModel):
    delta: int = 0
    set_to: Optional[int] = None


class LinkIn(BaseModel):
    player_id: Optional[int] = None


# ---------------------------------------------------------------- DM: sesion

class BootstrapIn(BaseModel):
    password: str = ""


@app.post("/api/dm/bootstrap")
async def dm_bootstrap(payload: Optional[BootstrapIn] = None):
    """Devuelve la sesion activa (recuperacion) o crea una nueva.
    Requiere DM_PASSWORD correcta (config.py)."""
    password = payload.password if payload else ""
    if not getattr(config, "DM_PASSWORD", ""):
        raise HTTPException(status_code=500, detail="DM_PASSWORD no configurada. Exporta DND_DM_PASSWORD o ejecuta python -m backend.set_dm_password")
    if password != config.DM_PASSWORD:
        raise HTTPException(status_code=403, detail="Contrasena de DM incorrecta")

    with get_db() as db:
        session = fetch_active_session(db)
        if session is None:
            code = generate_code(db)
            token = secrets.token_urlsafe(18)
            cur = db.execute(
                "INSERT INTO sessions (code, status, round, turn_combatant_id, dm_token, created_at) "
                "VALUES (?, 'active', 1, NULL, ?, ?)",
                (code, token, now()),
            )
            log_event(db, cur.lastrowid, "session", f"Sesion {code} creada")
            session = db.execute("SELECT * FROM sessions WHERE id=?", (cur.lastrowid,)).fetchone()
        # Bridge v2: dm_token tambien vale como X-User-Token.
        dm_uid = ensure_dm_user(db)
        ensure_user_session(db, dm_uid, session["dm_token"], session["created_at"])
    return {
        "session_id": session["id"],
        "code": session["code"],
        "dm_token": session["dm_token"],
        "round": session["round"],
    }


@app.post("/api/session/close")
async def close_session(x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        sid, code = session["id"], session["code"]
        log_event(db, sid, "session", "Sesion cerrada por el DM")
        ts = now()
        db.execute("UPDATE sessions SET status='closed', closed_at=? WHERE id=?", (ts, sid))
        db.execute(
            "UPDATE initiative_requests SET status='cancelled', closed_at=? WHERE session_id=? AND status='active'",
            (ts, sid),
        )
        db.execute(
            "UPDATE initiative_rolls SET status='cancelled' WHERE session_id=? AND status='pending'",
            (sid,),
        )
        db.execute(
            "UPDATE check_requests SET status='cancelled', closed_at=? WHERE session_id=? AND status='active'",
            (ts, sid),
        )
        db.execute(
            "UPDATE check_rolls SET status='cancelled' WHERE session_id=? AND status='pending'",
            (sid,),
        )
        events = db.execute(
            "SELECT * FROM events WHERE session_id=? ORDER BY id", (sid,)
        ).fetchall()

        log_dir = os.path.join(BASE_DIR, "data", "logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"session_{code}.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"Sesion {code} - cerrada {now()}\n")
            fh.write("-" * 60 + "\n")
            for e in events:
                fh.write(f"[{e['ts']}] {e['kind']:<9} {e['message']}\n")

    await broadcast_state(sid)
    return {"ok": True, "log": path}


# ---------------------------------------------------------------- jugadores

@app.post("/api/join")
async def join(payload: JoinIn, x_user_token: Optional[str] = Header(None)):
    code = payload.code.strip().upper()
    name = payload.name.strip()
    if not name or len(name) > 40:
        raise HTTPException(status_code=400, detail="Nombre invalido")

    with get_db() as db:
        session = fetch_active_session(db)
        if session is None or session["code"] != code:
            raise HTTPException(status_code=404, detail="Codigo de sesion invalido")

        # Verificar si quien entra tiene una cuenta registrada
        user = None
        if x_user_token:
            try:
                u_cand = require_user(db, x_user_token)
                if u_cand and not u_cand["is_guest"]:
                    user = u_cand
            except Exception:
                user = None

        existing = db.execute(
            "SELECT * FROM players WHERE session_id=? AND lower(name)=lower(?)",
            (session["id"], name),
        ).fetchone()
        if existing:
            player = existing
            if user:
                ensure_user_session(db, user["id"], player["token"], now())
                db.execute(
                    "INSERT OR IGNORE INTO session_participants (session_id, user_id, joined_at) VALUES (?,?,?)",
                    (session["id"], user["id"], now()),
                )
                db.execute(
                    "UPDATE combatants SET user_id=? WHERE session_id=? AND player_id=?",
                    (user["id"], session["id"], player["id"]),
                )
        else:
            token = secrets.token_urlsafe(24)
            cur = db.execute(
                "INSERT INTO players (session_id, name, token, created_at) VALUES (?,?,?,?)",
                (session["id"], name, token, now()),
            )
            player = db.execute("SELECT * FROM players WHERE id=?", (cur.lastrowid,)).fetchone()
            log_event(db, session["id"], "player", f"{name} se unio")

            if user:
                target_uid = user["id"]
            else:
                # Bridge v2: crear user guest + user_session + session_participant.
                uname = f"{slugify(name)}_{player['id']}"
                if db.execute("SELECT 1 FROM users WHERE username=?", (uname,)).fetchone():
                    uname = f"{uname}_p{player['id']}"
                ucur = db.execute(
                    "INSERT INTO users (username, display_name, is_guest, created_at) "
                    "VALUES (?,?,1,?)",
                    (uname, name, player["created_at"]),
                )
                target_uid = ucur.lastrowid

            ensure_user_session(db, target_uid, player["token"], player["created_at"])
            db.execute(
                "INSERT OR IGNORE INTO session_participants (session_id, user_id, joined_at) "
                "VALUES (?,?,?)",
                (session["id"], target_uid, player["created_at"]),
            )
            # auto-vinculo con un PJ del mismo nombre que aun no tenga jugador
            db.execute(
                "UPDATE combatants SET player_id=?, user_id=? "
                "WHERE session_id=? AND kind='pc' AND player_id IS NULL AND lower(name)=lower(?)",
                (player["id"], target_uid, session["id"], name),
            )
            await broadcast_state(session["id"])

    return {
        "player_id": player["id"],
        "token": player["token"],
        "name": player["name"],
        "session_id": session["id"],
        "code": session["code"],
    }


@app.get("/api/player/me")
async def player_me(x_player_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        player = db.execute("SELECT * FROM players WHERE token=?", (x_player_token,)).fetchone()
        if player is None:
            raise HTTPException(status_code=404, detail="Token invalido")
        session = db.execute("SELECT * FROM sessions WHERE id=?", (player["session_id"],)).fetchone()
        if session is None or session["status"] != "active":
            raise HTTPException(status_code=404, detail="Sesion cerrada")

        user_info = None
        if x_user_token:
            u_row = db.execute(
                "SELECT u.id, u.username, u.display_name, u.is_guest "
                "FROM user_sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token = ? AND s.revoked_at IS NULL AND s.expires_at > ?",
                (x_user_token, now()),
            ).fetchone()
            if u_row:
                user_info = {
                    "id": u_row["id"],
                    "username": u_row["username"],
                    "display_name": u_row["display_name"],
                    "is_guest": bool(u_row["is_guest"]),
                }

        if not user_info:
            us = db.execute(
                "SELECT u.id, u.username, u.display_name, u.is_guest "
                "FROM user_sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token = ? AND s.revoked_at IS NULL AND s.expires_at > ?",
                (x_player_token, now()),
            ).fetchone()
            if us:
                user_info = {
                    "id": us["id"],
                    "username": us["username"],
                    "display_name": us["display_name"],
                    "is_guest": bool(us["is_guest"]),
                }

        comb = db.execute(
            "SELECT character_id FROM combatants WHERE session_id=? AND player_id=? LIMIT 1",
            (session["id"], player["id"]),
        ).fetchone()
        character_id = comb["character_id"] if comb else None

    campaign_id = session["campaign_id"] if "campaign_id" in session.keys() else None
    return {
        "player_id": player["id"],
        "name": player["name"],
        "session_id": session["id"],
        "code": session["code"],
        "campaign_id": campaign_id,
        "user": user_info,
        "character_id": character_id,
    }


@app.post("/api/me/hp")
async def my_hp(payload: HpIn, x_player_token: Optional[str] = Header(None)):
    with get_db() as db:
        player = db.execute("SELECT * FROM players WHERE token=?", (x_player_token,)).fetchone()
        if player is None:
            raise HTTPException(status_code=403, detail="Token invalido")
        session = db.execute("SELECT * FROM sessions WHERE id=?", (player["session_id"],)).fetchone()
        if session is None or session["status"] != "active":
            raise HTTPException(status_code=400, detail="Sesion cerrada")
        c = db.execute(
            "SELECT * FROM combatants WHERE session_id=? AND player_id=?",
            (session["id"], player["id"]),
        ).fetchone()
        if c is None:
            raise HTTPException(status_code=404, detail="Tu PJ no esta en el combate")
        apply_hp(db, session, c, delta=payload.delta, set_to=payload.set_to)
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True}


# ---------------------------------------------------------------- combate

@app.post("/api/combatants")
async def add_combatant(payload: CombatantIn, x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    name = (payload.name or "").strip()
    hp_max = payload.hp_max

    srd = None
    if payload.srd_index:
        with get_srd_db() as db:
            try:
                srd = db.execute(
                    "SELECT name, hit_points, dexterity FROM monsters WHERE index_slug = ?",
                    (payload.srd_index,),
                ).fetchone()
            except sqlite3.OperationalError:
                srd = None
        if srd is None:
            raise HTTPException(
                status_code=404,
                detail=f"Monstruo SRD '{payload.srd_index}' no encontrado",
            )
        if not name:
            name = srd["name"]
        if hp_max is None:
            hp_max = srd["hit_points"]

    if not name or len(name) > 40:
        raise HTTPException(status_code=400, detail="Nombre invalido")
    if hp_max is None:
        raise HTTPException(status_code=400, detail="hp_max requerido")
    kind = "enemy" if payload.kind == "enemy" else "pc"
    hp_max = max(1, int(hp_max))

    dex_mod = 0
    if srd is not None and srd["dexterity"] is not None:
        dex_mod = (srd["dexterity"] - 10) // 2

    with get_db() as db:
        session = require_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        cur = db.execute(
            "INSERT INTO combatants (session_id, name, hp_max, hp_current, initiative, kind, dex_mod, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (session["id"], name, hp_max, hp_max, int(payload.initiative), kind, dex_mod, now()),
        )
        cid = cur.lastrowid

        if kind == "pc":
            player = db.execute(
                "SELECT id, token FROM players WHERE session_id=? AND lower(name)=lower(?)",
                (session["id"], name),
            ).fetchone()
            if player:
                db.execute("UPDATE combatants SET player_id=? WHERE id=?", (player["id"], cid))
                # Bridge v2: escribir tambien user_id si el player tiene user asociado.
                uid_row = db.execute(
                    "SELECT user_id FROM user_sessions WHERE token=?", (player["token"],)
                ).fetchone()
                if uid_row is not None:
                    db.execute(
                        "UPDATE combatants SET user_id=? WHERE id=?",
                        (uid_row["user_id"], cid),
                    )

        log_event(db, session["id"], "combatant",
                  f"Agregado {name} ({kind}) init {payload.initiative} HP {hp_max}")

        if session["turn_combatant_id"] is None:
            first = db.execute(
                "SELECT id FROM combatants WHERE session_id=? ORDER BY initiative DESC, id ASC LIMIT 1",
                (session["id"],),
            ).fetchone()
            db.execute("UPDATE sessions SET turn_combatant_id=? WHERE id=?",
                       (first["id"], session["id"]))
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True, "id": cid}


@app.delete("/api/combatants/{cid}")
async def remove_combatant(cid: int, x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        c = db.execute(
            "SELECT * FROM combatants WHERE id=? AND session_id=?", (cid, session["id"])
        ).fetchone()
        if c is None:
            raise HTTPException(status_code=404, detail="Combatiente no encontrado")

        db.execute("DELETE FROM combatants WHERE id=?", (cid,))
        log_event(db, session["id"], "combatant", f"Eliminado {c['name']}")

        if session["turn_combatant_id"] == cid:
            # Siguiente turno = primer combatiente VIVO por iniciativa.
            nxt = db.execute(
                "SELECT id FROM combatants WHERE session_id=? AND hp_current>0 "
                "ORDER BY initiative DESC, id ASC LIMIT 1",
                (session["id"],),
            ).fetchone()
            db.execute("UPDATE sessions SET turn_combatant_id=? WHERE id=?",
                       (nxt["id"] if nxt else None, session["id"]))
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True}


@app.post("/api/combatants/{cid}/hp")
async def change_hp(cid: int, payload: HpIn, x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        c = db.execute(
            "SELECT * FROM combatants WHERE id=? AND session_id=?", (cid, session["id"])
        ).fetchone()
        if c is None:
            raise HTTPException(status_code=404, detail="Combatiente no encontrado")
        apply_hp(db, session, c, delta=payload.delta, set_to=payload.set_to)
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True}


@app.post("/api/combatants/{cid}/undo-hp")
async def undo_hp(cid: int, x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        c = db.execute(
            "SELECT * FROM combatants WHERE id=? AND session_id=?", (cid, session["id"])
        ).fetchone()
        if c is None:
            raise HTTPException(status_code=404, detail="Combatiente no encontrado")
        last = db.execute(
            "SELECT * FROM hp_history WHERE combatant_id=? AND undone=0 ORDER BY id DESC LIMIT 1",
            (cid,),
        ).fetchone()
        if last is None:
            raise HTTPException(status_code=400, detail="No hay cambios de HP para deshacer")
        db.execute("UPDATE combatants SET hp_current=? WHERE id=?", (last["old_hp"], cid))
        db.execute("UPDATE hp_history SET undone=1 WHERE id=?", (last["id"],))
        log_event(db, session["id"], "undo",
                   f"Deshecho HP de {c['name']}: {last['new_hp']} -> {last['old_hp']}")
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True}


@app.post("/api/combatants/{cid}/link")
async def link_player(cid: int, payload: LinkIn, x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        c = db.execute(
            "SELECT * FROM combatants WHERE id=? AND session_id=?", (cid, session["id"])
        ).fetchone()
        if c is None:
            raise HTTPException(status_code=404, detail="Combatiente no encontrado")

        if payload.player_id is not None:
            p = db.execute(
                "SELECT * FROM players WHERE id=? AND session_id=?",
                (payload.player_id, session["id"]),
            ).fetchone()
            if p is None:
                raise HTTPException(status_code=404, detail="Jugador no encontrado")
            db.execute("UPDATE combatants SET player_id=? WHERE id=?", (p["id"], cid))
            # Bridge v2: escribir tambien user_id.
            uid_row = db.execute(
                "SELECT user_id FROM user_sessions WHERE token=?", (p["token"],)
            ).fetchone()
            db.execute(
                "UPDATE combatants SET user_id=? WHERE id=?",
                (uid_row["user_id"] if uid_row else None, cid),
            )
        else:
            db.execute("UPDATE combatants SET player_id=NULL, user_id=NULL WHERE id=?", (cid,))
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True}


@app.post("/api/turn/next")
async def next_turn(x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        combatants = db.execute(
            "SELECT * FROM combatants WHERE session_id=? ORDER BY initiative DESC, id ASC",
            (session["id"],),
        ).fetchall()
        if not combatants:
            raise HTTPException(status_code=400, detail="Sin combatientes")

        ids = [c["id"] for c in combatants]
        n = len(ids)
        try:
            idx = ids.index(session["turn_combatant_id"])
        except ValueError:
            idx = -1

        round_no = session["round"]
        new_idx = None
        wrapped = False

        for step in range(1, n + 1):
            raw = (idx + step) if idx >= 0 else (step - 1)
            wrapped_step = raw >= n
            cand = raw % n
            if combatants[cand]["hp_current"] > 0:
                new_idx = cand
                wrapped = wrapped_step
                break

        if new_idx is None:
            new_idx = 0 if idx < 0 else idx
            wrapped = False
        elif new_idx == idx:
            # El siguiente vivo es el MISMO que tenia el turno (p.ej. es el
            # unico vivo). No cuenta como "vuelta completa" -> no subir ronda.
            wrapped = False

        if wrapped:
            round_no += 1

        db.execute("UPDATE sessions SET turn_combatant_id=?, round=? WHERE id=?",
                   (ids[new_idx], round_no, session["id"]))
        log_event(db, session["id"], "turn",
                  f"Turno de {combatants[new_idx]['name']} (ronda {round_no})")
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True}


@app.post("/api/turn/round")
async def next_round(x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        combatants = db.execute(
            "SELECT * FROM combatants WHERE session_id=? ORDER BY initiative DESC, id ASC",
            (session["id"],),
        ).fetchall()
        if not combatants:
            raise HTTPException(status_code=400, detail="Sin combatientes")

        first = next((c for c in combatants if c["hp_current"] > 0), combatants[0])
        round_no = session["round"] + 1
        db.execute("UPDATE sessions SET round=?, turn_combatant_id=? WHERE id=?",
                   (round_no, first["id"], session["id"]))
        log_event(db, session["id"], "turn",
                  f"Inicio de ronda {round_no} - turno de {first['name']}")
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True}


# ---------------------------------------------------------------- logs

@app.get("/api/sessions/closed")
async def list_closed_sessions(x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        require_any_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        rows = db.execute("""
            SELECT s.code, s.closed_at,
                   (SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) AS n_events
            FROM sessions s
            WHERE s.status = 'closed'
            ORDER BY s.id DESC
            LIMIT 100
        """).fetchall()
    return {"sessions": [
        {"code": r["code"], "closed_at": r["closed_at"], "n_events": r["n_events"]}
        for r in rows
    ]}


@app.get("/api/sessions/{code}/log")
async def get_session_log(code: str, x_dm_token: Optional[str] = Header(None), x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        require_any_dm(db, x_dm_token=x_dm_token, x_user_token=x_user_token)
        session = db.execute(
            "SELECT * FROM sessions WHERE code=?", (code.upper(),)
        ).fetchone()
        if session is None or session["status"] != "closed":
            raise HTTPException(status_code=404, detail="Sesion no encontrada o no cerrada")
    path = os.path.join(BASE_DIR, "data", "logs", f"session_{session['code']}.log")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Log no encontrado en disco")
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    return {"code": session["code"], "content": content}


# ---------------------------------------------------------------- SRD bestiario

@app.get("/api/srd/monsters")
async def srd_monsters(
    q: Optional[str] = None,
    cr_min: Optional[float] = None,
    cr_max: Optional[float] = None,
    type: Optional[str] = None,
    size: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Lista/busca monstruos del bestiario SRD (solo lectura, sin token).

    Si la tabla `monsters` no existe (SRD no importado todavia), devuelve
    una lista vacia en lugar de 500: el servidor arranca y /dm funciona.
    """
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    where_sql = " FROM monsters WHERE 1=1"
    params: list = []
    if q:
        where_sql += " AND (name LIKE ? OR index_slug LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if cr_min is not None:
        where_sql += " AND challenge_rating >= ?"
        params.append(cr_min)
    if cr_max is not None:
        where_sql += " AND challenge_rating <= ?"
        params.append(cr_max)
    if type:
        where_sql += " AND type = ?"
        params.append(type)
    if size:
        where_sql += " AND size = ?"
        params.append(size)

    try:
        with get_srd_db() as db:
            count_sql = "SELECT COUNT(*)" + where_sql
            total = db.execute(count_sql, params).fetchone()[0]

            select_sql = (
                "SELECT index_slug, name, hit_points, armor_class, challenge_rating, "
                "       type, size, xp, dexterity "
                + where_sql
                + " ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?"
            )
            rows = db.execute(select_sql, params + [limit, offset]).fetchall()
    except sqlite3.OperationalError:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    return {
        "items": [
            {
                "index": r["index_slug"],
                "name": r["name"],
                "hit_points": r["hit_points"],
                "armor_class": r["armor_class"],
                "challenge_rating": r["challenge_rating"],
                "type": r["type"],
                "size": r["size"],
                "xp": r["xp"],
                # `dexterity` extra: permite al frontend sugerir #f-init sin
                # un round-trip adicional a /api/srd/monsters/{index}.
                "dexterity": r["dexterity"],
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


ALLOWED_REF_COLLECTIONS = {
    "conditions": "5e-SRD-Conditions.json",
    "damage-types": "5e-SRD-Damage-Types.json",
    "ability-scores": "5e-SRD-Ability-Scores.json",
    "skills": "5e-SRD-Skills.json",
    "equipment-categories": "5e-SRD-Equipment-Categories.json",
    "proficiencies": "5e-SRD-Proficiencies.json",
    "weapon-properties": "5e-SRD-Weapon-Properties.json",
    "magic-schools": "5e-SRD-Magic-Schools.json",
}


@app.get("/api/srd/refs/{collection}")
async def srd_refs(collection: str):
    """Devuelve una lista con index y name de la colección solicitada."""
    if collection not in ALLOWED_REF_COLLECTIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Colección '{collection}' no encontrada en referencias SRD."
        )

    items = []
    try:
        with get_srd_db() as db:
            rows = db.execute(
                """
                SELECT r.index_slug AS "index", r.name
                FROM reference_entries r
                JOIN collections c ON c.id = r.collection_id
                WHERE c.slug = ?
                ORDER BY r.name COLLATE NOCASE
                """,
                (collection,),
            ).fetchall()
            if rows:
                items = [{"index": r["index"], "name": r["name"]} for r in rows]
    except sqlite3.OperationalError:
        pass

    if not items:
        srd_dir = getattr(config, "SRD_DIR", "")
        json_path = os.path.join(srd_dir, ALLOWED_REF_COLLECTIONS[collection])
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as fh:
                    raw_items = json.load(fh)
                    items = [{"index": x["index"], "name": x["name"]} for x in raw_items]
                    items.sort(key=lambda x: x["name"].lower())
            except Exception:
                pass

    return items


@app.get("/api/srd/skills")
async def srd_skills():
    """Lista de habilidades con su característica asociada."""
    try:
        with get_srd_db() as db:
            rows = db.execute(
                """
                SELECT r.index_slug AS "index", r.name, r.data
                FROM reference_entries r
                JOIN collections c ON c.id = r.collection_id
                WHERE c.slug = 'skills'
                ORDER BY r.name COLLATE NOCASE
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return {"items": []}

    items = []
    for r in rows:
        d = json.loads(r["data"]) if r["data"] else {}
        ability = d.get("ability_score", {}).get("index")
        items.append({
            "index": r["index"],
            "name": r["name"],
            "ability_score": ability,
        })
    return {"items": items}


@app.get("/api/srd/equipment")
async def srd_equipment(
    q: Optional[str] = None,
    category: Optional[str] = None,
    weapon_category: Optional[str] = None,
    armor_category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Catálogo de equipo y armas SRD con filtros y paginación."""
    limit = max(1, min(int(limit), 250))
    offset = max(0, int(offset))

    where_sql = " FROM equipment WHERE 1=1"
    params: list = []
    if q:
        where_sql += " AND (name LIKE ? OR index_slug LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if category:
        where_sql += " AND equipment_category_slug = ?"
        params.append(category)
    if weapon_category:
        where_sql += " AND weapon_category = ?"
        params.append(weapon_category)
    if armor_category:
        where_sql += " AND armor_category = ?"
        params.append(armor_category)

    try:
        with get_srd_db() as db:
            total = db.execute("SELECT COUNT(*)" + where_sql, params).fetchone()[0]
            select_sql = (
                "SELECT index_slug, name, equipment_category_slug, weapon_category, armor_category, "
                "       cost_quantity, cost_unit, cost_unit_raw, weight, damage_dice, damage_type_slug, "
                "       armor_class_base, armor_class_dex_bonus, armor_class_max_bonus "
                + where_sql
                + " ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?"
            )
            rows = db.execute(select_sql, params + [limit, offset]).fetchall()
    except sqlite3.OperationalError:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    return {
        "items": [
            {
                "index": r["index_slug"],
                "name": r["name"],
                "category": r["equipment_category_slug"],
                "weapon_category": r["weapon_category"],
                "armor_category": r["armor_category"],
                "cost_quantity": r["cost_quantity"],
                "cost_unit": r["cost_unit"],
                "cost_unit_raw": r["cost_unit_raw"],
                "weight": r["weight"],
                "damage_dice": r["damage_dice"],
                "damage_type": r["damage_type_slug"],
                "armor_class_base": r["armor_class_base"],
                "armor_class_dex_bonus": r["armor_class_dex_bonus"],
                "armor_class_max_bonus": r["armor_class_max_bonus"],
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/srd/equipment/{index}")
async def srd_equipment_item(index: str):
    """Detalle completo de un objeto de equipo."""
    try:
        with get_srd_db() as db:
            row = db.execute(
                "SELECT data FROM equipment WHERE index_slug = ?", (index,)
            ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return json.loads(row["data"])


@app.get("/api/srd/classes")
async def srd_classes(q: Optional[str] = None):
    """Lista de clases de personaje SRD."""
    where_sql = " FROM classes WHERE 1=1"
    params: list = []
    if q:
        where_sql += " AND (name LIKE ? OR index_slug LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]

    try:
        with get_srd_db() as db:
            rows = db.execute(
                "SELECT index_slug, name, hit_die, spellcasting_ability_slug "
                + where_sql
                + " ORDER BY name COLLATE NOCASE",
                params,
            ).fetchall()
    except sqlite3.OperationalError:
        return {"items": []}

    return {
        "items": [
            {
                "index": r["index_slug"],
                "name": r["name"],
                "hit_die": r["hit_die"],
                "spellcasting_ability": r["spellcasting_ability_slug"],
            }
            for r in rows
        ]
    }


@app.get("/api/srd/classes/{index}")
async def srd_class_detail(index: str):
    """Detalle completo de una clase."""
    try:
        with get_srd_db() as db:
            row = db.execute(
                "SELECT data FROM classes WHERE index_slug = ?", (index,)
            ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    return json.loads(row["data"])


@app.get("/api/srd/classes/{index}/levels")
async def srd_class_levels(
    index: str,
    from_level: Optional[int] = None,
    to_level: Optional[int] = None,
    subclass: Optional[str] = None,
):
    """Progresión de niveles de una clase (1 a 20)."""
    where_sql = " FROM levels WHERE class_slug = ?"
    params: list = [index]
    if from_level is not None:
        where_sql += " AND level >= ?"
        params.append(from_level)
    if to_level is not None:
        where_sql += " AND level <= ?"
        params.append(to_level)
    if subclass is not None:
        where_sql += " AND (subclass_slug = ? OR subclass_slug IS NULL)"
        params.append(subclass)
    else:
        where_sql += " AND subclass_slug IS NULL"

    try:
        with get_srd_db() as db:
            rows = db.execute(
                "SELECT index_slug, class_slug, subclass_slug, level, prof_bonus, data "
                + where_sql
                + " ORDER BY level ASC",
                params,
            ).fetchall()
    except sqlite3.OperationalError:
        return {"items": []}

    items = []
    for r in rows:
        d = json.loads(r["data"]) if r["data"] else {}
        items.append({
            "index": r["index_slug"],
            "class": r["class_slug"],
            "subclass": r["subclass_slug"],
            "level": r["level"],
            "prof_bonus": r["prof_bonus"],
            "spellcasting": d.get("spellcasting"),
            "features": d.get("features", []),
            "class_specific": d.get("class_specific"),
        })

    return {"items": items}


@app.get("/api/srd/races")
async def srd_races(q: Optional[str] = None):
    """Lista de razas de personaje SRD."""
    where_sql = " FROM races WHERE 1=1"
    params: list = []
    if q:
        where_sql += " AND (name LIKE ? OR index_slug LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]

    try:
        with get_srd_db() as db:
            rows = db.execute(
                "SELECT index_slug, name, speed, size "
                + where_sql
                + " ORDER BY name COLLATE NOCASE",
                params,
            ).fetchall()
    except sqlite3.OperationalError:
        return {"items": []}

    return {
        "items": [
            {
                "index": r["index_slug"],
                "name": r["name"],
                "speed": r["speed"],
                "size": r["size"],
            }
            for r in rows
        ]
    }


@app.get("/api/srd/races/{index}")
async def srd_race_detail(index: str):
    """Detalle completo de una raza."""
    try:
        with get_srd_db() as db:
            row = db.execute(
                "SELECT data FROM races WHERE index_slug = ?", (index,)
            ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        raise HTTPException(status_code=404, detail="Raza no encontrada")
    return json.loads(row["data"])


@app.get("/api/srd/spells")
async def srd_spells(
    q: Optional[str] = None,
    level: Optional[int] = None,
    school: Optional[str] = None,
    class_slug: Optional[str] = None,
    concentration: Optional[int] = None,
    ritual: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Catálogo de conjuros SRD con filtros y paginación."""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    where_sql = " FROM spells WHERE 1=1"
    params: list = []
    if q:
        where_sql += " AND (name LIKE ? OR index_slug LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if level is not None:
        where_sql += " AND level = ?"
        params.append(level)
    if school:
        where_sql += " AND school_slug = ?"
        params.append(school)
    if concentration is not None:
        where_sql += " AND concentration = ?"
        params.append(1 if concentration else 0)
    if ritual is not None:
        where_sql += " AND ritual = ?"
        params.append(1 if ritual else 0)
    if class_slug:
        where_sql += " AND data LIKE ?"
        params.append(f'%"index": "{class_slug}"%')

    try:
        with get_srd_db() as db:
            total = db.execute("SELECT COUNT(*)" + where_sql, params).fetchone()[0]
            select_sql = (
                "SELECT index_slug, name, level, school_slug, casting_time, range, duration, "
                "       concentration, ritual, components, attack_type "
                + where_sql
                + " ORDER BY level ASC, name COLLATE NOCASE LIMIT ? OFFSET ?"
            )
            rows = db.execute(select_sql, params + [limit, offset]).fetchall()
    except sqlite3.OperationalError:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    return {
        "items": [
            {
                "index": r["index_slug"],
                "name": r["name"],
                "level": r["level"],
                "school": r["school_slug"],
                "casting_time": r["casting_time"],
                "range": r["range"],
                "duration": r["duration"],
                "concentration": bool(r["concentration"]),
                "ritual": bool(r["ritual"]),
                "components": r["components"],
                "attack_type": r["attack_type"],
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/srd/spells/{index}")
async def srd_spell_detail(index: str):
    """Detalle completo de un conjuro."""
    try:
        with get_srd_db() as db:
            row = db.execute(
                "SELECT data FROM spells WHERE index_slug = ?", (index,)
            ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        raise HTTPException(status_code=404, detail="Conjuro no encontrado")
    return json.loads(row["data"])


@app.get("/api/srd/monsters/{index}")
async def srd_monster(index: str):
    """Ficha completa de un monstruo del bestiario SRD (solo lectura, sin token)."""
    try:
        with get_srd_db() as db:
            row = db.execute(
                "SELECT * FROM monsters WHERE index_slug = ?", (index,)
            ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        raise HTTPException(status_code=404, detail="Monstruo no encontrado")

    try:
        data = json.loads(row["data"])
    except Exception:
        data = None

    return {
        "index": row["index_slug"],
        "name": row["name"],
        "size": row["size"],
        "type": row["type"],
        "subtype": row["subtype"],
        "alignment": row["alignment"],
        "hit_points": row["hit_points"],
        "hit_dice": row["hit_dice"],
        "hit_points_roll": row["hit_points_roll"],
        "armor_class": row["armor_class"],
        "armor_class_type": row["armor_class_type"],
        "challenge_rating": row["challenge_rating"],
        "xp": row["xp"],
        "strength": row["strength"],
        "dexterity": row["dexterity"],
        "constitution": row["constitution"],
        "intelligence": row["intelligence"],
        "wisdom": row["wisdom"],
        "charisma": row["charisma"],
        "proficiency_bonus": row["proficiency_bonus"],
        "data": data,
    }


# ---------------------------------------------------------------- WebSocket

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, role: str = "player", token: str = ""):
    role = role if role in ("dm", "player") else "player"

    with get_db() as db:
        if role == "dm":
            session = None
            active_s = fetch_active_session(db)
            if active_s and token:
                # 1. Verificar si token es de un usuario DM o Superusuario de la sesion activa
                user_row = db.execute(
                    "SELECT u.* FROM users u JOIN user_sessions us ON us.user_id=u.id "
                    "WHERE us.token=? AND us.revoked_at IS NULL AND us.expires_at > ?",
                    (token, now()),
                ).fetchone()
                if user_row and _is_user_authorized_dm(db, active_s, user_row):
                    session = active_s

            # 2. Fallback legacy: dm_token de la sesion activa
            if session is None and token:
                session = db.execute(
                    "SELECT * FROM sessions WHERE dm_token = ? AND status = 'active' AND dm_token != ''",
                    (token,),
                ).fetchone()

            if session is None:
                # FIX I3: accept() antes de close() para que el cliente
                # reciba un close frame WS con code=4003. Si se cierra
                # antes de accept(), Starlette/Uvicorn lo convierte en
                # HTTP 403 handshake rejection y el browser ve code=1006
                # (abnormal closure), rompiendo onAuthError de common.js.
                await websocket.accept()
                await websocket.close(code=4003)
                return
            session_id, player_id = session["id"], None
        else:
            player = db.execute("SELECT * FROM players WHERE token=?", (token,)).fetchone()
            if player is None:
                await websocket.accept()
                await websocket.close(code=4003)
                return
            session = db.execute(
                "SELECT * FROM sessions WHERE id=?", (player["session_id"],)
            ).fetchone()
            if session is None:
                await websocket.accept()
                await websocket.close(code=4003)
                return
            session_id, player_id = session["id"], player["id"]

    await manager.connect(websocket, session_id, role, player_id)
    await broadcast_state(session_id)

    try:
        while True:
            await websocket.receive_text()  # keepalive / ignorado
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ---------------------------------------------------------------- frontend

@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/dm")
async def dm_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "dm.html"))


@app.get("/player")
async def player_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "player.html"))



@app.get("/player/{path:path}")
async def player_catchall(path: str):
    # Cualquier /player/<algo> sirve la app del jugador.
    # Evita 404 si el movil llega con un token pegado en la URL o un typo.
    return FileResponse(os.path.join(FRONTEND_DIR, "player.html"))


# ================================================================
# Fase 2.0: paginas nuevas (/register, /login, /campaigns)
# ================================================================


@app.get("/register")
async def register_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "register.html"))


@app.get("/login")
async def login_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))


@app.get("/campaigns")
async def campaigns_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "campaigns.html"))


# Fase 2.1: pagina de recovery de DM (password legacy).
@app.get("/dm-login")
async def dm_login_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "dm-login.html"))


# ================================================================
# Fase 2.0: auth
# ================================================================

USERNAME_RE = re.compile(r"^[a-z0-9_-]{3,32}$")


class RegisterIn(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    display_name: Optional[str] = None


class LoginIn(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None


class CampaignIn(BaseModel):
    name: Optional[str] = None
    join_code: Optional[str] = None


class CampaignPatchIn(BaseModel):
    name: Optional[str] = None
    join_code: Optional[str] = None


class JoinCampaignIn(BaseModel):
    code: Optional[str] = None


@app.post("/api/auth/register")
async def auth_register(payload: RegisterIn):
    username = (payload.username or "").strip()
    password = payload.password or ""
    display_name = (payload.display_name or "").strip()
    # FIX B3: 'dm' reservado. El check va ANTES de USERNAME_RE para que el
    # cliente reciba 409 USERNAME_RESERVED (no 400 INVALID_INPUT: 'dm'
    # tiene 2 chars y la regex exige 3-32).
    if username == "dm":
        raise ApiError(409, "username reservado", "USERNAME_RESERVED")
    if not USERNAME_RE.match(username):
        raise ApiError(400, "username invalido (3-32, [a-z0-9_-])", "INVALID_INPUT")
    if len(password) < 8:
        raise ApiError(400, "password demasiado corta (min 8)", "INVALID_INPUT")
    if not (1 <= len(display_name) <= 40):
        raise ApiError(400, "display_name invalido (1-40)", "INVALID_INPUT")
    with get_db() as db:
        if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise ApiError(409, "username ya existe", "USERNAME_TAKEN")
        cur = db.execute(
            "INSERT INTO users (username, display_name, password_hash, is_guest, created_at) "
            "VALUES (?,?,?,0,?)",
            (username, display_name, hash_password(password), now()),
        )
        uid = cur.lastrowid
        token, expires = create_user_session(db, uid)
    return {
        "user_id": uid,
        "token": token,
        "expires_at": expires,
        "display_name": display_name,
    }


@app.post("/api/auth/login")
async def auth_login(payload: LoginIn, request: Request = None):
    username = (payload.username or "").strip()
    password = payload.password or ""
    if not username or not password:
        raise ApiError(400, "username y password requeridos", "INVALID_INPUT")
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user is None or not user["password_hash"]:
            raise ApiError(401, "credenciales invalidas", "UNAUTHENTICATED")
        if not verify_password(password, user["password_hash"]):
            raise ApiError(401, "credenciales invalidas", "UNAUTHENTICATED")

        if user["is_superuser"]:
            client_ip = request.client.host if (request and request.client) else ""
            allowed_ips = {"127.0.0.1", "::1", "localhost", "testclient"}
            env_ips = os.getenv("DND_ADMIN_ALLOWED_IPS", "")
            if env_ips:
                for ip in env_ips.split(","):
                    ip = ip.strip()
                    if ip:
                        allowed_ips.add(ip)
            if client_ip not in allowed_ips:
                raise ApiError(403, "acceso denegado para superusuario", "SUPERUSER_IP_FORBIDDEN")

        token, expires = create_user_session(db, user["id"])
        db.execute("UPDATE users SET last_seen_at=? WHERE id=?", (now(), user["id"]))
        uid = user["id"]
        display_name = user["display_name"]
    return {
        "user_id": uid,
        "token": token,
        "expires_at": expires,
        "display_name": display_name,
    }


@app.post("/api/auth/logout")
async def auth_logout(x_user_token: Optional[str] = Header(None)):
    if not x_user_token:
        raise ApiError(401, "token requerido", "UNAUTHENTICATED")
    with get_db() as db:
        db.execute(
            "UPDATE user_sessions SET revoked_at=? WHERE token=? AND revoked_at IS NULL",
            (now(), x_user_token),
        )
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        user = require_user(db, x_user_token)
    return {
        "user_id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "is_guest": user["is_guest"],
        "is_superuser": bool(user["is_superuser"]),
    }


# ================================================================
# Fase 2.0: campanas
# ================================================================


@app.post("/api/campaigns")
async def campaigns_create(payload: CampaignIn, x_user_token: Optional[str] = Header(None)):
    name = (payload.name or "").strip()
    if not (1 <= len(name) <= 60):
        raise ApiError(400, "name invalido (1-60)", "INVALID_INPUT")
    with get_db() as db:
        user = require_user(db, x_user_token)
        camp = create_campaign(db, user["id"], name, payload.join_code)
    return {
        "campaign_id": camp["id"],
        "name": camp["name"],
        "join_code": camp["join_code"],
        "role": "dm",
    }


@app.get("/api/campaigns")
async def campaigns_list(x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        user = require_user(db, x_user_token)
        rows = list_campaigns_for_user(db, user["id"])
    return {
        "items": [
            {
                "id": r["id"],
                "name": r["name"],
                "role": r["role"],
                "status": r["status"],
                "n_sessions": r["n_sessions"],
                "n_sessions_active": r["n_sessions_active"],
                "join_code": r["join_code"],
            }
            for r in rows
        ]
    }


@app.get("/api/campaigns/{campaign_id}")
async def campaigns_get(campaign_id: int, x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        _user, _member = require_user_campaign_member(db, x_user_token, campaign_id)
        camp = get_campaign(db, campaign_id)
        members = list_members(db, campaign_id)
        sessions = list_sessions_in_campaign(db, campaign_id)
    return {
        "id": camp["id"],
        "name": camp["name"],
        "join_code": camp["join_code"],
        "status": camp["status"],
        "members": [
            {"user_id": m["user_id"], "display_name": m["display_name"], "role": m["role"]}
            for m in members
        ],
        "sessions": [
            {
                "id": s["id"], "code": s["code"], "status": s["status"],
                "round": s["round"], "created_at": s["created_at"],
                "closed_at": s["closed_at"],
            }
            for s in sessions
        ],
    }


@app.patch("/api/campaigns/{campaign_id}")
async def campaigns_patch(campaign_id: int, payload: CampaignPatchIn,
                          x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        _user, _member = require_user_campaign_dm(db, x_user_token, campaign_id)
        camp = get_campaign(db, campaign_id)
        new_name = camp["name"]
        new_code = camp["join_code"]
        if payload.name is not None:
            name = payload.name.strip()
            if not (1 <= len(name) <= 60):
                raise ApiError(400, "name invalido (1-60)", "INVALID_INPUT")
            new_name = name
        if payload.join_code is not None:
            code = payload.join_code.strip().upper()
            if not re.fullmatch(r"[A-Z0-9]{6}", code):
                raise ApiError(400, "join_code invalido", "INVALID_INPUT")
            taken = db.execute(
                "SELECT 1 FROM campaigns WHERE join_code=? AND id<>?",
                (code, campaign_id),
            ).fetchone()
            if taken:
                raise ApiError(409, "join_code ya en uso", "JOIN_CODE_TAKEN")
            new_code = code
        db.execute(
            "UPDATE campaigns SET name=?, join_code=? WHERE id=?",
            (new_name, new_code, campaign_id),
        )
    return {"ok": True}


@app.post("/api/campaigns/{campaign_id}/archive")
async def campaigns_archive(campaign_id: int, x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        _user, _member = require_user_campaign_dm(db, x_user_token, campaign_id)
        db.execute(
            "UPDATE campaigns SET status='archived', archived_at=? WHERE id=?",
            (now(), campaign_id),
        )
    return {"ok": True}


@app.post("/api/campaigns/join")
async def campaigns_join(payload: JoinCampaignIn, x_user_token: Optional[str] = Header(None)):
    code = (payload.code or "").strip().upper()
    if not code:
        raise ApiError(400, "code requerido", "INVALID_INPUT")
    with get_db() as db:
        user = require_user(db, x_user_token)
        camp = db.execute("SELECT * FROM campaigns WHERE join_code=?", (code,)).fetchone()
        if camp is None or camp["status"] != "active":
            raise ApiError(404, "campana no encontrada", "NOT_FOUND")
        add_member(db, camp["id"], user["id"], "player")
    return {"campaign_id": camp["id"], "name": camp["name"], "role": "player"}


@app.post("/api/campaigns/{campaign_id}/sessions")
async def campaigns_create_session(campaign_id: int,
                                   x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        user, _member = require_user_campaign_dm(db, x_user_token, campaign_id)
        sess = create_session_in_campaign(db, campaign_id, user["id"])
    return {
        "session_id": sess["id"],
        "code": sess["code"],
        "dm_token": sess["dm_token"],
        "campaign_id": campaign_id,
    }


@app.post("/api/campaigns/{campaign_id}/open-session")
async def campaigns_open_session(campaign_id: int,
                                 x_user_token: Optional[str] = Header(None)):
    """Devuelve el dm_token de la sesion activa de esta campana (o la crea).

    Auth: X-User-Token del DM de la campana. Idempotente mientras haya
    sesion activa en la campana. Si hay una sesion activa de OTRA
    campana, create_session_in_campaign devuelve 409 (una sesion activa
    global).
    """
    with get_db() as db:
        user, _member = require_user_campaign_dm(db, x_user_token, campaign_id)
        sess = db.execute(
            "SELECT * FROM sessions WHERE campaign_id=? AND status='active' LIMIT 1",
            (campaign_id,),
        ).fetchone()
        if sess is None:
            sess = create_session_in_campaign(db, campaign_id, user["id"])
    return {
        "session_id": sess["id"],
        "code": sess["code"],
        "dm_token": sess["dm_token"],
        "campaign_id": campaign_id,
    }


@app.post("/api/campaigns/{campaign_id}/join-player")
async def campaigns_join_player(campaign_id: int,
                                x_user_token: Optional[str] = Header(None)):
    """Devuelve (o crea) un player_token para el user en la sesion activa.

    Auth: X-User-Token de un miembro de la campana. Reusa la fila de
    players si ya existe para (session_id, display_name); si no, crea
    una con nombre = user.display_name. Registra session_participants
    (idempotente) y auto-vincula el primer PJ con el mismo nombre.
    """
    with get_db() as db:
        user, _member = require_user_campaign_member(db, x_user_token, campaign_id)
        sess = db.execute(
            "SELECT * FROM sessions WHERE campaign_id=? AND status='active' LIMIT 1",
            (campaign_id,),
        ).fetchone()
        if sess is None:
            raise ApiError(404, "no hay sesion activa en esta campana", "NOT_FOUND")

        # FIX I2: identidad por user_id. El player de una cuenta en esta
        # sesion es el que tiene su user_token en user_sessions (bridge v2:
        # user_sessions.token == players.token). NO se busca por display_name.
        existing = db.execute(
            "SELECT p.* FROM players p "
            "JOIN user_sessions us ON us.token = p.token "
            "WHERE p.session_id=? AND us.user_id=? "
            "ORDER BY p.id DESC LIMIT 1",
            (sess["id"], user["id"]),
        ).fetchone()
        if existing:
            player = existing
        else:
            # FIX I2: si ya hay otro player con el mismo display_name en esta
            # sesion (otra cuenta homonima), desambiguar con username.
            name = user["display_name"]
            clash = db.execute(
                "SELECT 1 FROM players WHERE session_id=? AND lower(name)=lower(?)",
                (sess["id"], name),
            ).fetchone()
            if clash:
                name = f"{user['display_name']} ({user['username']})"
            token = secrets.token_urlsafe(24)
            cur = db.execute(
                "INSERT INTO players (session_id, name, token, created_at) "
                "VALUES (?,?,?,?)",
                (sess["id"], name, token, now()),
            )
            player = db.execute(
                "SELECT * FROM players WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            log_event(db, sess["id"], "player", f"{name} se unio (cuenta)")

        # FIX I1: registrar user_sessions para este player_token. Asi
        # add_combatant y link_player (que buscan por user_sessions.token)
        # encuentran el user_id y combatants.user_id queda consistente.
        ensure_user_session(db, user["id"], player["token"], now())
        db.execute(
            "INSERT OR IGNORE INTO session_participants "
            "(session_id, user_id, joined_at) VALUES (?,?,?)",
            (sess["id"], user["id"], now()),
        )
        db.execute(
            "UPDATE combatants SET player_id=?, user_id=? "
            "WHERE session_id=? AND kind='pc' AND player_id IS NULL "
            "AND lower(name)=lower(?)",
            (player["id"], user["id"], sess["id"], player["name"]),
        )
        sid = sess["id"]
    await broadcast_state(sid)
    return {
        "player_id": player["id"],
        "token": player["token"],
        "session_id": sess["id"],
        "code": sess["code"],
        "campaign_id": campaign_id,
    }


@app.get("/api/campaigns/{campaign_id}/sessions")
async def campaigns_list_sessions(campaign_id: int,
                                  x_user_token: Optional[str] = Header(None)):
    with get_db() as db:
        _user, _member = require_user_campaign_member(db, x_user_token, campaign_id)
        sessions = list_sessions_in_campaign(db, campaign_id)
    return {
        "items": [
            {
                "id": s["id"], "code": s["code"], "status": s["status"],
                "round": s["round"], "created_at": s["created_at"],
                "closed_at": s["closed_at"],
            }
            for s in sessions
        ]
    }


# ================================================================
# Fase 2.3: Personajes (Mini-ficha) y endpoints CRUD
# ================================================================

class CharacterIn(BaseModel):
    name: str
    campaign_id: Optional[int] = None
    level: Optional[int] = 1
    class_slug: Optional[str] = None
    race_slug: Optional[str] = None
    dex_mod: Optional[int] = None
    hp_max: Optional[int] = None
    data: Optional[Dict[str, Any]] = None


class LinkCharacterIn(BaseModel):
    character_id: int


def calculate_character_data(
    level: int,
    class_slug: Optional[str],
    race_slug: Optional[str],
    dex_mod: Optional[int],
    hp_max: Optional[int],
    data: Optional[Dict[str, Any]],
):
    data = dict(data) if data else {}
    stats = data.get("stats") or {}
    scores = {
        "strength": int(stats.get("strength", 10)),
        "dexterity": int(stats.get("dexterity", 10)),
        "constitution": int(stats.get("constitution", 10)),
        "intelligence": int(stats.get("intelligence", 10)),
        "wisdom": int(stats.get("wisdom", 10)),
        "charisma": int(stats.get("charisma", 10)),
    }
    modifiers = {
        "str_mod": (scores["strength"] - 10) // 2,
        "dex_mod": (scores["dexterity"] - 10) // 2,
        "con_mod": (scores["constitution"] - 10) // 2,
        "int_mod": (scores["intelligence"] - 10) // 2,
        "wis_mod": (scores["wisdom"] - 10) // 2,
        "cha_mod": (scores["charisma"] - 10) // 2,
    }
    computed_dex_mod = dex_mod if dex_mod is not None else modifiers["dex_mod"]
    prof_bonus = ((level - 1) // 4) + 2

    # Class data from SRD
    hit_die = 8
    spellcasting_ability = None
    class_name = None
    if class_slug:
        try:
            with get_srd_db() as sdb:
                crow = sdb.execute(
                    "SELECT name, hit_die, spellcasting_ability_slug FROM classes WHERE index_slug=?",
                    (class_slug,),
                ).fetchone()
                if crow:
                    class_name = crow["name"]
                    if crow["hit_die"]:
                        hit_die = crow["hit_die"]
                    spellcasting_ability = crow["spellcasting_ability_slug"]
        except Exception:
            pass

    # Race data from SRD
    speed = data.get("speed", 30)
    size = data.get("size", "Mediano")
    race_name = None
    if race_slug:
        try:
            with get_srd_db() as sdb:
                rrow = sdb.execute(
                    "SELECT name, speed, size FROM races WHERE index_slug=?",
                    (race_slug,),
                ).fetchone()
                if rrow:
                    race_name = rrow["name"]
                    if rrow["speed"]:
                        speed = rrow["speed"]
                    if rrow["size"]:
                        size = rrow["size"]
        except Exception:
            pass

    computed_hp_max = hp_max
    if not computed_hp_max or computed_hp_max <= 0:
        con_mod = modifiers["con_mod"]
        computed_hp_max = hit_die + con_mod + max(0, level - 1) * max(1, (hit_die // 2 + 1 + con_mod))
        computed_hp_max = max(1, computed_hp_max)

    base_ac = data.get("armor_class")
    if base_ac is None:
        base_ac = 10 + computed_dex_mod

    spell_dc = None
    spell_attack_bonus = None
    if spellcasting_ability:
        ability_mod_key = f"{spellcasting_ability[:3]}_mod"
        ability_mod = modifiers.get(ability_mod_key, 0)
        spell_dc = 8 + prof_bonus + ability_mod
        spell_attack_bonus = prof_bonus + ability_mod

    data["stats"] = scores
    data["modifiers"] = modifiers
    data["proficiency_bonus"] = prof_bonus
    data["armor_class"] = base_ac
    data["speed"] = speed
    data["size"] = size
    data["hit_die"] = hit_die
    if class_name:
        data["class_name"] = class_name
    if race_name:
        data["race_name"] = race_name
    data["spellcasting_ability"] = spellcasting_ability
    if spell_dc is not None:
        data["spell_dc"] = spell_dc
        data["spell_attack_bonus"] = spell_attack_bonus
    if "weapons" not in data:
        data["weapons"] = []
    if "spells" not in data:
        data["spells"] = []
    if "skill_proficiencies" not in data:
        data["skill_proficiencies"] = []

    currency = data.get("currency")
    if not isinstance(currency, dict):
        currency = {}
    data["currency"] = {
        "cp": max(0, int(currency.get("cp") or 0)),
        "sp": max(0, int(currency.get("sp") or 0)),
        "ep": max(0, int(currency.get("ep") or 0)),
        "gp": max(0, int(currency.get("gp") or 0)),
        "pp": max(0, int(currency.get("pp") or 0)),
    }

    return computed_dex_mod, computed_hp_max, data


def _format_character_row(r) -> dict:
    try:
        data = json.loads(r["data"]) if r["data"] else {}
    except Exception:
        data = {}
    return {
        "id": r["id"],
        "campaign_id": r["campaign_id"],
        "user_id": r["user_id"],
        "name": r["name"],
        "level": r["level"],
        "class_slug": r["class_slug"],
        "race_slug": r["race_slug"],
        "dex_mod": r["dex_mod"],
        "hp_max": r["hp_max"],
        "data": data,
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


@app.get("/api/characters")
async def characters_list(
    campaign_id: Optional[int] = None,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        if user["is_guest"]:
            return {"items": []}
        if campaign_id is not None:
            rows = db.execute(
                "SELECT * FROM characters WHERE user_id=? AND campaign_id=? ORDER BY id DESC",
                (user["id"], campaign_id),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM characters WHERE user_id=? ORDER BY id DESC",
                (user["id"],),
            ).fetchall()

        return {"items": [_format_character_row(r) for r in rows]}


@app.post("/api/characters")
async def characters_create(
    payload: CharacterIn,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        if user["is_guest"]:
            raise ApiError(403, "Los invitados no pueden crear fichas. Por favor crea una cuenta.", "GUEST_FORBIDDEN")

        name = (payload.name or "").strip()
        if not (1 <= len(name) <= 60):
            raise ApiError(400, "Nombre inválido (1-60 caracteres)", "INVALID_NAME")

        level = max(1, min(20, payload.level or 1))

        if payload.campaign_id is not None:
            camp = db.execute("SELECT 1 FROM campaigns WHERE id=?", (payload.campaign_id,)).fetchone()
            if camp is None:
                raise ApiError(404, "Campaña no encontrada", "NOT_FOUND")

        dex_mod, hp_max, data = calculate_character_data(
            level=level,
            class_slug=payload.class_slug,
            race_slug=payload.race_slug,
            dex_mod=payload.dex_mod,
            hp_max=payload.hp_max,
            data=payload.data,
        )

        ts = now()
        cur = db.execute(
            "INSERT INTO characters (campaign_id, user_id, name, level, class_slug, race_slug, dex_mod, hp_max, data, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                payload.campaign_id,
                user["id"],
                name,
                level,
                payload.class_slug,
                payload.race_slug,
                dex_mod,
                hp_max,
                json.dumps(data, ensure_ascii=False),
                ts,
                ts,
            ),
        )
        cid = cur.lastrowid
        row = db.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone()
        return _format_character_row(row)


@app.get("/api/characters/{char_id}")
async def characters_get(
    char_id: int,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        row = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
        if row is None:
            raise ApiError(404, "Personaje no encontrado", "NOT_FOUND")

        # Dueño, superusuario o DM de la campaña
        allowed = (row["user_id"] == user["id"]) or bool(user["is_superuser"])
        if not allowed and row["campaign_id"]:
            camp = db.execute("SELECT dm_user_id FROM campaigns WHERE id=?", (row["campaign_id"],)).fetchone()
            if camp and camp["dm_user_id"] == user["id"]:
                allowed = True
            else:
                member = db.execute(
                    "SELECT role FROM campaign_members WHERE campaign_id=? AND user_id=?",
                    (row["campaign_id"], user["id"]),
                ).fetchone()
                if member and member["role"] == "dm":
                    allowed = True
        if not allowed:
            raise ApiError(403, "No tienes permiso para ver este personaje", "FORBIDDEN")

        return _format_character_row(row)


@app.put("/api/characters/{char_id}")
async def characters_update(
    char_id: int,
    payload: CharacterIn,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        row = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
        if row is None:
            raise ApiError(404, "Personaje no encontrado", "NOT_FOUND")

        # Dueño, superusuario o DM de la campaña del personaje
        allowed = (row["user_id"] == user["id"]) or bool(user["is_superuser"])
        if not allowed and row["campaign_id"] is not None:
            camp = db.execute("SELECT dm_user_id FROM campaigns WHERE id=?", (row["campaign_id"],)).fetchone()
            if camp and camp["dm_user_id"] == user["id"]:
                allowed = True
            else:
                member = db.execute(
                    "SELECT role FROM campaign_members WHERE campaign_id=? AND user_id=?",
                    (row["campaign_id"], user["id"]),
                ).fetchone()
                if member and member["role"] == "dm":
                    allowed = True
        if not allowed:
            raise ApiError(403, "No tienes permiso para editar este personaje", "FORBIDDEN")

        name = (payload.name or "").strip()
        if not (1 <= len(name) <= 60):
            raise ApiError(400, "Nombre inválido (1-60 caracteres)", "INVALID_NAME")

        level = max(1, min(20, payload.level or 1))

        campaign_id = payload.campaign_id if payload.campaign_id is not None else row["campaign_id"]
        if campaign_id is not None:
            camp = db.execute("SELECT 1 FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if camp is None:
                raise ApiError(404, "Campaña no encontrada", "NOT_FOUND")

        dex_mod, hp_max, data = calculate_character_data(
            level=level,
            class_slug=payload.class_slug,
            race_slug=payload.race_slug,
            dex_mod=payload.dex_mod,
            hp_max=payload.hp_max,
            data=payload.data,
        )

        ts = now()
        db.execute(
            "UPDATE characters SET campaign_id=?, name=?, level=?, class_slug=?, race_slug=?, dex_mod=?, hp_max=?, data=?, updated_at=? "
            "WHERE id=?",
            (
                campaign_id,
                name,
                level,
                payload.class_slug,
                payload.race_slug,
                dex_mod,
                hp_max,
                json.dumps(data, ensure_ascii=False),
                ts,
                char_id,
            ),
        )
        # Sincronizar dex_mod en combatientes vinculados
        db.execute("UPDATE combatants SET dex_mod=? WHERE character_id=?", (dex_mod, char_id))
        linked_sessions = db.execute("SELECT DISTINCT session_id FROM combatants WHERE character_id=?", (char_id,)).fetchall()
        sids = [r["session_id"] for r in linked_sessions if r["session_id"]]
        updated = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()

    for sid in sids:
        try:
            await broadcast_state(sid)
        except Exception:
            pass

    return _format_character_row(updated)


@app.delete("/api/characters/{char_id}")
async def characters_delete(
    char_id: int,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        row = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
        if row is None:
            raise ApiError(404, "Personaje no encontrado", "NOT_FOUND")
        allowed = (row["user_id"] == user["id"]) or bool(user["is_superuser"])
        if not allowed:
            raise ApiError(403, "Solo el dueño puede eliminar el personaje", "FORBIDDEN")

        db.execute("DELETE FROM characters WHERE id=?", (char_id,))
        return {"ok": True}


@app.post("/api/me/link-character")
async def link_my_character(
    payload: LinkCharacterIn,
    x_player_token: Optional[str] = Header(None),
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        player = db.execute("SELECT * FROM players WHERE token=?", (x_player_token,)).fetchone()
        if player is None:
            raise HTTPException(status_code=403, detail="Player token inválido")
        session = db.execute("SELECT * FROM sessions WHERE id=?", (player["session_id"],)).fetchone()
        if session is None or session["status"] != "active":
            raise HTTPException(status_code=400, detail="Sesión inactiva")

        user = None
        if x_user_token:
            user = require_user(db, x_user_token)
        else:
            us = db.execute(
                "SELECT u.* FROM user_sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token = ? AND s.revoked_at IS NULL AND s.expires_at > ?",
                (x_player_token, now()),
            ).fetchone()
            if us:
                user = us

        if not user or user["is_guest"]:
            raise ApiError(403, "Se requiere cuenta de usuario registrada para vincular ficha", "GUEST_FORBIDDEN")

        char = db.execute("SELECT * FROM characters WHERE id=?", (payload.character_id,)).fetchone()
        if not char:
            raise ApiError(404, "Personaje no encontrado", "NOT_FOUND")
        if char["user_id"] != user["id"]:
            raise ApiError(403, "No eres el dueño de este personaje", "FORBIDDEN")

        comb = db.execute("SELECT * FROM combatants WHERE session_id=? AND player_id=?", (session["id"], player["id"])).fetchone()
        if comb:
            db.execute(
                "UPDATE combatants SET character_id=?, name=?, hp_max=?, hp_current=?, dex_mod=?, user_id=? WHERE id=?",
                (char["id"], char["name"], char["hp_max"], char["hp_max"], char["dex_mod"], user["id"], comb["id"]),
            )
            log_event(db, session["id"], "character", f"{player['name']} vinculó la ficha de {char['name']}")
        else:
            db.execute(
                "UPDATE combatants SET character_id=?, dex_mod=?, user_id=? WHERE session_id=? AND lower(name)=lower(?)",
                (char["id"], char["dex_mod"], user["id"], session["id"], char["name"]),
            )
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True, "character": _format_character_row(char)}


# ================================================================
# Fase 2.4.1: Iniciativa interactiva
# ================================================================

class InitiativeRollIn(BaseModel):
    request_id: int
    combatant_id: int
    roll_value: int


class InitiativeActionIn(BaseModel):
    request_id: int
    combatant_id: int


class InitiativeCancelIn(BaseModel):
    request_id: int


def check_is_session_dm_or_superuser(db, user, session):
    """Devuelve (is_authorized, is_superuser_override).

    Autorizado si:
    - user['is_superuser'] == 1
    - o user es el DM de la campaña de la sesión (campaign_members con role='dm' o campaigns.dm_user_id)
    - o la sesión no tiene campaña y user['id'] == session['created_by_user_id']
    """
    is_super = bool(user["is_superuser"])
    is_dm = False

    camp_id = session["campaign_id"] if "campaign_id" in session.keys() else None
    if camp_id is not None:
        camp = db.execute("SELECT dm_user_id FROM campaigns WHERE id=?", (camp_id,)).fetchone()
        if camp and camp["dm_user_id"] == user["id"]:
            is_dm = True
        else:
            member = db.execute(
                "SELECT role FROM campaign_members WHERE campaign_id=? AND user_id=?",
                (camp_id, user["id"]),
            ).fetchone()
            if member and member["role"] == "dm":
                is_dm = True
    else:
        created_by = session["created_by_user_id"] if "created_by_user_id" in session.keys() else None
        if created_by == user["id"]:
            is_dm = True

    if is_dm:
        return True, False
    if is_super:
        return True, True
    return False, False


@app.post("/api/sessions/{session_id}/initiative/request")
async def initiative_request_create(
    session_id: int,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if session is None or session["status"] != "active":
            raise ApiError(400, "Sesión no encontrada o inactiva", "SESSION_NOT_ACTIVE")

        authorized, is_admin_override = check_is_session_dm_or_superuser(db, user, session)
        if not authorized:
            raise ApiError(403, "No tienes permiso para iniciar la iniciativa", "FORBIDDEN")

        ts = now()
        db.execute(
            "UPDATE initiative_requests SET status='cancelled', closed_at=? WHERE session_id=? AND status='active'",
            (ts, session_id),
        )
        db.execute(
            "UPDATE initiative_rolls SET status='cancelled' WHERE session_id=? AND status='pending'",
            (session_id,),
        )

        cur = db.execute(
            "INSERT INTO initiative_requests (session_id, status, created_by_user_id, created_at) "
            "VALUES (?, 'active', ?, ?)",
            (session_id, user["id"], ts),
        )
        req_id = cur.lastrowid

        combatants = db.execute(
            "SELECT * FROM combatants WHERE session_id=?", (session_id,)
        ).fetchall()

        for c in combatants:
            if c["kind"] == "enemy":
                r_val = random.randint(1, 20)
                d_mod = c["dex_mod"] if c["dex_mod"] is not None else 0
                tot = r_val + d_mod
                db.execute("UPDATE combatants SET initiative=? WHERE id=?", (tot, c["id"]))
                db.execute(
                    "INSERT INTO initiative_rolls (request_id, session_id, combatant_id, user_id, dex_mod, roll_value, total, status, source, rolled_at) "
                    "VALUES (?, ?, ?, NULL, ?, ?, ?, 'rolled', 'npc_auto', ?)",
                    (req_id, session_id, c["id"], d_mod, r_val, tot, ts),
                )
                log_event(db, session_id, "roll", f"{c['name']} (enemigo) tiró iniciativa: {r_val} + {d_mod} = {tot}")
            else:
                d_mod = c["dex_mod"] if c["dex_mod"] is not None else 0
                uid = c["user_id"]
                if c["character_id"]:
                    char = db.execute("SELECT * FROM characters WHERE id=?", (c["character_id"],)).fetchone()
                    if char:
                        if char["dex_mod"] is not None:
                            d_mod = char["dex_mod"]
                        if char["user_id"]:
                            uid = char["user_id"]
                elif not uid and c["player_id"]:
                    p_row = db.execute("SELECT token FROM players WHERE id=?", (c["player_id"],)).fetchone()
                    if p_row:
                        us_row = db.execute(
                            "SELECT user_id FROM user_sessions WHERE token=?", (p_row["token"],)
                        ).fetchone()
                        if us_row:
                            uid = us_row["user_id"]

                db.execute(
                    "INSERT INTO initiative_rolls (request_id, session_id, combatant_id, user_id, dex_mod, roll_value, total, status, source, rolled_at) "
                    "VALUES (?, ?, ?, ?, ?, NULL, NULL, 'pending', 'unknown', NULL)",
                    (req_id, session_id, c["id"], uid, d_mod),
                )

        pending = db.execute(
            "SELECT COUNT(*) AS c FROM initiative_rolls WHERE request_id=? AND status='pending'",
            (req_id,),
        ).fetchone()["c"]
        if pending == 0:
            db.execute(
                "UPDATE initiative_requests SET status='completed', closed_at=? WHERE id=?",
                (ts, req_id),
            )

        if is_admin_override:
            log_event(db, session_id, "admin_action", f"Superusuario '{user['username']}' inició tirada de iniciativa")
        else:
            log_event(db, session_id, "combat", "Tirada de iniciativa iniciada por el DM")

    await broadcast_state(session_id)
    return {"ok": True, "request_id": req_id}


@app.post("/api/initiative/roll")
async def initiative_roll_submit(
    payload: InitiativeRollIn,
    x_user_token: Optional[str] = Header(None),
):
    if not (1 <= payload.roll_value <= 20):
        raise ApiError(400, "Tirada inválida (debe estar entre 1 y 20)", "INVALID_ROLL")

    with get_db() as db:
        user = require_user(db, x_user_token)
        roll = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (payload.request_id, payload.combatant_id),
        ).fetchone()
        if roll is None:
            raise ApiError(404, "Tirada no encontrada", "NOT_FOUND")

        req = db.execute("SELECT * FROM initiative_requests WHERE id=?", (payload.request_id,)).fetchone()
        if req is None or req["status"] != "active":
            raise ApiError(400, "La solicitud de iniciativa no está activa", "REQUEST_NOT_ACTIVE")

        if roll["status"] != "pending":
            raise ApiError(409, "Esta tirada ya fue enviada o resuelta", "ALREADY_ROLLED")

        c = db.execute("SELECT * FROM combatants WHERE id=?", (payload.combatant_id,)).fetchone()
        if c is None:
            raise ApiError(404, "Combatiente no encontrado", "NOT_FOUND")

        allowed = bool(user["is_superuser"])
        if not allowed:
            if roll["user_id"] == user["id"] or c["user_id"] == user["id"]:
                allowed = True
            elif c["character_id"]:
                char = db.execute("SELECT user_id FROM characters WHERE id=?", (c["character_id"],)).fetchone()
                if char and char["user_id"] == user["id"]:
                    allowed = True
            elif c["player_id"]:
                p_row = db.execute("SELECT token FROM players WHERE id=?", (c["player_id"],)).fetchone()
                if p_row:
                    us_row = db.execute(
                        "SELECT user_id FROM user_sessions WHERE token=?", (p_row["token"],)
                    ).fetchone()
                    if us_row and us_row["user_id"] == user["id"]:
                        allowed = True
        if not allowed:
            raise ApiError(403, "No tienes permiso para tirar por este combatiente", "FORBIDDEN")

        d_mod = roll["dex_mod"]
        tot = payload.roll_value + d_mod
        ts = now()
        db.execute(
            "UPDATE initiative_rolls SET roll_value=?, total=?, status='rolled', source='player', rolled_at=? WHERE id=?",
            (payload.roll_value, tot, ts, roll["id"]),
        )
        db.execute("UPDATE combatants SET initiative=? WHERE id=?", (tot, payload.combatant_id))
        log_event(db, req["session_id"], "roll", f"{c['name']} tiró iniciativa: {payload.roll_value} + {d_mod} = {tot}")

        pending = db.execute(
            "SELECT COUNT(*) AS c FROM initiative_rolls WHERE request_id=? AND status='pending'",
            (req["id"],),
        ).fetchone()["c"]
        if pending == 0:
            db.execute(
                "UPDATE initiative_requests SET status='completed', closed_at=? WHERE id=?",
                (ts, req["id"]),
            )
        sid = req["session_id"]

    await broadcast_state(sid)
    return {"ok": True, "total": tot, "roll_value": payload.roll_value, "dex_mod": d_mod}


@app.post("/api/initiative/force")
async def initiative_roll_force(
    payload: InitiativeActionIn,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        roll = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (payload.request_id, payload.combatant_id),
        ).fetchone()
        if roll is None:
            raise ApiError(404, "Tirada no encontrada", "NOT_FOUND")

        req = db.execute("SELECT * FROM initiative_requests WHERE id=?", (payload.request_id,)).fetchone()
        if req is None or req["status"] != "active":
            raise ApiError(400, "La solicitud de iniciativa no está activa", "REQUEST_NOT_ACTIVE")

        if roll["status"] != "pending":
            raise ApiError(409, "Esta tirada ya fue resuelta", "ALREADY_ROLLED")

        session = db.execute("SELECT * FROM sessions WHERE id=?", (req["session_id"],)).fetchone()
        authorized, is_admin_override = check_is_session_dm_or_superuser(db, user, session)
        if not authorized:
            raise ApiError(403, "Solo el DM o un superusuario pueden forzar tiradas", "FORBIDDEN")

        c = db.execute("SELECT * FROM combatants WHERE id=?", (payload.combatant_id,)).fetchone()
        c_name = c["name"] if c else "Combatiente"
        r_val = random.randint(1, 20)
        d_mod = roll["dex_mod"]
        tot = r_val + d_mod
        ts = now()
        src = "superuser_force" if is_admin_override else "dm_force"
        db.execute(
            "UPDATE initiative_rolls SET roll_value=?, total=?, status='forced', source=?, rolled_at=? WHERE id=?",
            (r_val, tot, src, ts, roll["id"]),
        )
        db.execute("UPDATE combatants SET initiative=? WHERE id=?", (tot, payload.combatant_id))

        if is_admin_override:
            log_event(db, req["session_id"], "admin_action", f"Superusuario '{user['username']}' forzó tirada de {c_name}: {r_val} + {d_mod} = {tot}")
        else:
            log_event(db, req["session_id"], "roll", f"DM forzó tirada de {c_name}: {r_val} + {d_mod} = {tot}")

        pending = db.execute(
            "SELECT COUNT(*) AS c FROM initiative_rolls WHERE request_id=? AND status='pending'",
            (req["id"],),
        ).fetchone()["c"]
        if pending == 0:
            db.execute(
                "UPDATE initiative_requests SET status='completed', closed_at=? WHERE id=?",
                (ts, req["id"]),
            )
        sid = req["session_id"]

    await broadcast_state(sid)
    return {"ok": True, "total": tot, "roll_value": r_val, "dex_mod": d_mod}


@app.post("/api/initiative/skip")
async def initiative_roll_skip(
    payload: InitiativeActionIn,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        roll = db.execute(
            "SELECT * FROM initiative_rolls WHERE request_id=? AND combatant_id=?",
            (payload.request_id, payload.combatant_id),
        ).fetchone()
        if roll is None:
            raise ApiError(404, "Tirada no encontrada", "NOT_FOUND")

        req = db.execute("SELECT * FROM initiative_requests WHERE id=?", (payload.request_id,)).fetchone()
        if req is None or req["status"] != "active":
            raise ApiError(400, "La solicitud de iniciativa no está activa", "REQUEST_NOT_ACTIVE")

        if roll["status"] != "pending":
            raise ApiError(409, "Esta tirada ya fue resuelta", "ALREADY_ROLLED")

        session = db.execute("SELECT * FROM sessions WHERE id=?", (req["session_id"],)).fetchone()
        authorized, is_admin_override = check_is_session_dm_or_superuser(db, user, session)
        if not authorized:
            raise ApiError(403, "Solo el DM o un superusuario pueden saltar tiradas", "FORBIDDEN")

        c = db.execute("SELECT * FROM combatants WHERE id=?", (payload.combatant_id,)).fetchone()
        c_name = c["name"] if c else "Combatiente"
        d_mod = roll["dex_mod"]
        tot = 10 + d_mod
        ts = now()
        src = "superuser_skip" if is_admin_override else "dm_skip"
        db.execute(
            "UPDATE initiative_rolls SET roll_value=10, total=?, status='skipped', source=?, rolled_at=? WHERE id=?",
            (tot, src, ts, roll["id"]),
        )
        db.execute("UPDATE combatants SET initiative=? WHERE id=?", (tot, payload.combatant_id))

        if is_admin_override:
            log_event(db, req["session_id"], "admin_action", f"Superusuario '{user['username']}' saltó tirada (toma 10) de {c_name}: 10 + {d_mod} = {tot}")
        else:
            log_event(db, req["session_id"], "roll", f"DM saltó tirada (toma 10) de {c_name}: 10 + {d_mod} = {tot}")

        pending = db.execute(
            "SELECT COUNT(*) AS c FROM initiative_rolls WHERE request_id=? AND status='pending'",
            (req["id"],),
        ).fetchone()["c"]
        if pending == 0:
            db.execute(
                "UPDATE initiative_requests SET status='completed', closed_at=? WHERE id=?",
                (ts, req["id"]),
            )
        sid = req["session_id"]

    await broadcast_state(sid)
    return {"ok": True, "total": tot, "roll_value": 10, "dex_mod": d_mod}


@app.post("/api/initiative/cancel")
async def initiative_request_cancel(
    payload: InitiativeCancelIn,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        req = db.execute("SELECT * FROM initiative_requests WHERE id=?", (payload.request_id,)).fetchone()
        if req is None:
            raise ApiError(404, "Solicitud no encontrada", "NOT_FOUND")

        session = db.execute("SELECT * FROM sessions WHERE id=?", (req["session_id"],)).fetchone()
        authorized, is_admin_override = check_is_session_dm_or_superuser(db, user, session)
        if not authorized:
            raise ApiError(403, "Solo el DM o un superusuario pueden cancelar la iniciativa", "FORBIDDEN")

        ts = now()
        db.execute(
            "UPDATE initiative_requests SET status='cancelled', closed_at=? WHERE id=?",
            (ts, req["id"]),
        )
        db.execute(
            "UPDATE initiative_rolls SET status='cancelled' WHERE request_id=? AND status='pending'",
            (req["id"],),
        )

        if is_admin_override:
            log_event(db, req["session_id"], "admin_action", f"Superusuario '{user['username']}' canceló la iniciativa")
        else:
            log_event(db, req["session_id"], "system", "Tirada de iniciativa cancelada por el DM")
        sid = req["session_id"]

    await broadcast_state(sid)
    return {"ok": True}


# ================================================================
# Fase 2.4.2: Tiradas de Habilidad / Checks
# ================================================================

class CheckRequestIn(BaseModel):
    ability: Optional[str] = "str"
    skill_slug: Optional[str] = None
    dc: int
    is_secret: Optional[bool] = False
    advantage_mode: Optional[str] = "normal"  # 'normal', 'advantage', 'disadvantage'
    target_combatant_ids: Optional[List[int]] = None


class CheckRollIn(BaseModel):
    request_id: int
    combatant_id: int
    roll_value_1: int
    roll_value_2: Optional[int] = None


class CheckActionIn(BaseModel):
    request_id: int
    combatant_id: int


class CheckCancelIn(BaseModel):
    request_id: int


def _get_combatant_check_info(db, combatant, ability: str, skill_slug: Optional[str] = None):
    ability = (ability or "str").lower()[:3]
    char = None
    uid = combatant["user_id"]
    if combatant["character_id"]:
        char = db.execute("SELECT * FROM characters WHERE id=?", (combatant["character_id"],)).fetchone()
        if char and char["user_id"]:
            uid = char["user_id"]
    elif not uid and combatant["player_id"]:
        p_row = db.execute("SELECT token FROM players WHERE id=?", (combatant["player_id"],)).fetchone()
        if p_row:
            us_row = db.execute(
                "SELECT user_id FROM user_sessions WHERE token=?", (p_row["token"],)
            ).fetchone()
            if us_row:
                uid = us_row["user_id"]

    ability_mod = 0
    prof_bonus = 2
    is_proficient = False

    if char:
        try:
            cdata = json.loads(char["data"]) if char["data"] else {}
        except Exception:
            cdata = {}
        modifiers = cdata.get("modifiers") or {}
        ability_mod = modifiers.get(f"{ability}_mod", 0)
        prof_bonus = cdata.get("proficiency_bonus", 2)
        if skill_slug:
            skill_profs = cdata.get("skill_proficiencies") or []
            if skill_slug in skill_profs:
                is_proficient = True
    elif combatant["kind"] == "enemy":
        score = 10
        prof_bonus = 2
        is_proficient = False
        if "srd_index" in combatant.keys() and combatant["srd_index"]:
            try:
                with get_srd_db() as sdb:
                    mrow = sdb.execute("SELECT * FROM monsters WHERE index_slug=?", (combatant["srd_index"],)).fetchone()
                    if mrow:
                        ability_col_map = {"str": "strength", "dex": "dexterity", "con": "constitution", "int": "intelligence", "wis": "wisdom", "cha": "charisma"}
                        col = ability_col_map.get(ability, "strength")
                        if col in mrow.keys() and mrow[col] is not None:
                            score = mrow[col]
                        if mrow["proficiency_bonus"]:
                            prof_bonus = mrow["proficiency_bonus"]
                        if skill_slug:
                            m_data = json.loads(mrow["data"]) if mrow["data"] else {}
                            for p in (m_data.get("proficiencies") or []):
                                p_idx = p.get("proficiency", {}).get("index", "")
                                if p_idx in (f"skill-{skill_slug}", skill_slug):
                                    is_proficient = True
                                    break
            except Exception:
                pass
        elif ability == "dex" and combatant["dex_mod"] is not None:
            ability_mod = combatant["dex_mod"]
            return ability_mod, prof_bonus, 0, ability_mod, None

        ability_mod = (score - 10) // 2
    else:
        # PC sin ficha de personaje
        if ability == "dex" and combatant["dex_mod"] is not None:
            ability_mod = combatant["dex_mod"]
        else:
            ability_mod = 0
        prof_bonus = 2
        is_proficient = False

    total_mod = ability_mod + (prof_bonus if is_proficient else 0)
    return ability_mod, prof_bonus, 1 if is_proficient else 0, total_mod, uid


def _evaluate_check_roll(r1: int, r2: Optional[int], advantage_mode: str) -> int:
    if advantage_mode == "advantage":
        if r2 is not None:
            return max(r1, r2)
        return r1
    elif advantage_mode == "disadvantage":
        if r2 is not None:
            return min(r1, r2)
        return r1
    return r1


@app.post("/api/sessions/{session_id}/check/request")
async def check_request_create(
    session_id: int,
    payload: CheckRequestIn,
    x_user_token: Optional[str] = Header(None),
):
    if not (1 <= payload.dc <= 40):
        raise ApiError(400, "CD inválida (debe estar entre 1 y 40)", "INVALID_DC")

    adv_mode = payload.advantage_mode or "normal"
    if adv_mode not in ("normal", "advantage", "disadvantage"):
        raise ApiError(400, "Modo de ventaja inválido", "INVALID_ADVANTAGE_MODE")

    skill_slug = payload.skill_slug
    ability = (payload.ability or "str").lower()[:3]
    if skill_slug:
        sk_entry = SKILL_INFO.get(skill_slug)
        if sk_entry:
            ability = sk_entry["ability"]
    if ability not in ABILITY_NAMES:
        raise ApiError(400, "Característica inválida", "INVALID_ABILITY")

    with get_db() as db:
        user = require_user(db, x_user_token)
        session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if session is None or session["status"] != "active":
            raise ApiError(400, "Sesión no encontrada o inactiva", "SESSION_NOT_ACTIVE")

        authorized, is_admin_override = check_is_session_dm_or_superuser(db, user, session)
        if not authorized:
            raise ApiError(403, "No tienes permiso para solicitar tiradas de habilidad", "FORBIDDEN")

        ts = now()
        db.execute(
            "UPDATE check_requests SET status='cancelled', closed_at=? WHERE session_id=? AND status='active'",
            (ts, session_id),
        )
        db.execute(
            "UPDATE check_rolls SET status='cancelled' WHERE session_id=? AND status='pending'",
            (session_id,),
        )

        is_sec = 1 if payload.is_secret else 0
        cur = db.execute(
            "INSERT INTO check_requests (session_id, ability, skill_slug, dc, is_secret, advantage_mode, status, created_by_user_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (session_id, ability, skill_slug, payload.dc, is_sec, adv_mode, user["id"], ts),
        )
        req_id = cur.lastrowid

        if payload.target_combatant_ids:
            placeholders = ",".join("?" * len(payload.target_combatant_ids))
            combatants = db.execute(
                f"SELECT * FROM combatants WHERE session_id=? AND id IN ({placeholders})",
                (session_id, *payload.target_combatant_ids),
            ).fetchall()
        else:
            combatants = db.execute(
                "SELECT * FROM combatants WHERE session_id=? AND kind='pc'", (session_id,)
            ).fetchall()

        sk_entry = SKILL_INFO.get(skill_slug) if skill_slug else None
        check_title = sk_entry["name"] if sk_entry else f"Característica ({ABILITY_NAMES[ability]})"

        for c in combatants:
            a_mod, p_bonus, is_prof, tot_mod, uid = _get_combatant_check_info(db, c, ability, skill_slug)
            if c["kind"] == "enemy":
                r1 = random.randint(1, 20)
                r2 = random.randint(1, 20) if adv_mode in ("advantage", "disadvantage") else None
                chosen = _evaluate_check_roll(r1, r2, adv_mode)
                tot = chosen + tot_mod
                is_succ = 1 if tot >= payload.dc else 0
                db.execute(
                    "INSERT INTO check_rolls (request_id, session_id, combatant_id, user_id, ability_mod, prof_bonus, is_proficient, total_mod, roll_value_1, roll_value_2, chosen_roll, total, is_success, status, source, rolled_at) "
                    "VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'rolled', 'npc_auto', ?)",
                    (req_id, session_id, c["id"], a_mod, p_bonus, is_prof, tot_mod, r1, r2, chosen, tot, is_succ, ts),
                )
                log_event(db, session_id, "roll", f"{c['name']} (enemigo) tiró prueba de {check_title}: {chosen} + {tot_mod} = {tot} (CD {payload.dc}) -> {'ÉXITO' if is_succ else 'FALLO'}")
            else:
                db.execute(
                    "INSERT INTO check_rolls (request_id, session_id, combatant_id, user_id, ability_mod, prof_bonus, is_proficient, total_mod, roll_value_1, roll_value_2, chosen_roll, total, is_success, status, source, rolled_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, 'pending', 'unknown', NULL)",
                    (req_id, session_id, c["id"], uid, a_mod, p_bonus, is_prof, tot_mod),
                )

        pending = db.execute(
            "SELECT COUNT(*) AS c FROM check_rolls WHERE request_id=? AND status='pending'",
            (req_id,),
        ).fetchone()["c"]
        if pending == 0:
            db.execute(
                "UPDATE check_requests SET status='completed', closed_at=? WHERE id=?",
                (ts, req_id),
            )

        sec_text = " [SECRETA]" if is_sec else ""
        if is_admin_override:
            log_event(db, session_id, "admin_action", f"Superusuario '{user['username']}' pidió prueba de {check_title} (CD {payload.dc}){sec_text}")
        else:
            log_event(db, session_id, "combat", f"DM pidió prueba de {check_title} (CD {payload.dc}){sec_text}")

    await broadcast_state(session_id)
    return {"ok": True, "request_id": req_id}


@app.post("/api/check/roll")
async def check_roll_submit(
    payload: CheckRollIn,
    x_user_token: Optional[str] = Header(None),
):
    if not (1 <= payload.roll_value_1 <= 20):
        raise ApiError(400, "Tirada inválida (debe estar entre 1 y 20)", "INVALID_ROLL")
    if payload.roll_value_2 is not None and not (1 <= payload.roll_value_2 <= 20):
        raise ApiError(400, "Tirada 2 inválida (debe estar entre 1 y 20)", "INVALID_ROLL")

    with get_db() as db:
        user = require_user(db, x_user_token)
        roll = db.execute(
            "SELECT * FROM check_rolls WHERE request_id=? AND combatant_id=?",
            (payload.request_id, payload.combatant_id),
        ).fetchone()
        if roll is None:
            raise ApiError(404, "Tirada no encontrada", "NOT_FOUND")

        req = db.execute("SELECT * FROM check_requests WHERE id=?", (payload.request_id,)).fetchone()
        if req is None or req["status"] != "active":
            raise ApiError(400, "La solicitud de prueba no está activa", "REQUEST_NOT_ACTIVE")

        if roll["status"] != "pending":
            raise ApiError(409, "Esta tirada ya fue enviada o resuelta", "ALREADY_ROLLED")

        c = db.execute("SELECT * FROM combatants WHERE id=?", (payload.combatant_id,)).fetchone()
        if c is None:
            raise ApiError(404, "Combatiente no encontrado", "NOT_FOUND")

        allowed = bool(user["is_superuser"])
        if not allowed:
            if roll["user_id"] == user["id"] or c["user_id"] == user["id"]:
                allowed = True
            elif c["character_id"]:
                char = db.execute("SELECT user_id FROM characters WHERE id=?", (c["character_id"],)).fetchone()
                if char and char["user_id"] == user["id"]:
                    allowed = True
            elif c["player_id"]:
                p_row = db.execute("SELECT token FROM players WHERE id=?", (c["player_id"],)).fetchone()
                if p_row:
                    us_row = db.execute(
                        "SELECT user_id FROM user_sessions WHERE token=?", (p_row["token"],)
                    ).fetchone()
                    if us_row and us_row["user_id"] == user["id"]:
                        allowed = True
        if not allowed:
            raise ApiError(403, "No tienes permiso para tirar por este combatiente", "FORBIDDEN")

        chosen = _evaluate_check_roll(payload.roll_value_1, payload.roll_value_2, req["advantage_mode"])
        tot = chosen + roll["total_mod"]
        is_succ = 1 if tot >= req["dc"] else 0
        ts = now()

        db.execute(
            "UPDATE check_rolls SET roll_value_1=?, roll_value_2=?, chosen_roll=?, total=?, is_success=?, status='rolled', source='player', rolled_at=? WHERE id=?",
            (payload.roll_value_1, payload.roll_value_2, chosen, tot, is_succ, ts, roll["id"]),
        )

        sk_entry = SKILL_INFO.get(req["skill_slug"]) if req["skill_slug"] else None
        check_title = sk_entry["name"] if sk_entry else f"Característica ({ABILITY_NAMES.get(req['ability'], req['ability'].upper())})"

        if req["is_secret"]:
            log_event(db, req["session_id"], "roll", f"{c['name']} realizó tirada secreta para prueba de {check_title}")
        else:
            verdict = "ÉXITO" if is_succ else "FALLO"
            log_event(db, req["session_id"], "roll", f"{c['name']} tiró prueba de {check_title}: d20={chosen} + mod={roll['total_mod']} = {tot} frente a CD {req['dc']} -> {verdict}")

        pending = db.execute(
            "SELECT COUNT(*) AS c FROM check_rolls WHERE request_id=? AND status='pending'",
            (req["id"],),
        ).fetchone()["c"]
        if pending == 0:
            db.execute(
                "UPDATE check_requests SET status='completed', closed_at=? WHERE id=?",
                (ts, req["id"]),
            )
        sid = req["session_id"]

    await broadcast_state(sid)
    return {
        "ok": True,
        "total": tot,
        "chosen_roll": chosen,
        "total_mod": roll["total_mod"],
        "is_success": bool(is_succ) if not req["is_secret"] else None,
    }


@app.post("/api/check/force")
async def check_roll_force(
    payload: CheckActionIn,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        roll = db.execute(
            "SELECT * FROM check_rolls WHERE request_id=? AND combatant_id=?",
            (payload.request_id, payload.combatant_id),
        ).fetchone()
        if roll is None:
            raise ApiError(404, "Tirada no encontrada", "NOT_FOUND")

        req = db.execute("SELECT * FROM check_requests WHERE id=?", (payload.request_id,)).fetchone()
        if req is None or req["status"] != "active":
            raise ApiError(400, "La solicitud de prueba no está activa", "REQUEST_NOT_ACTIVE")

        if roll["status"] != "pending":
            raise ApiError(409, "Esta tirada ya fue resuelta", "ALREADY_ROLLED")

        session = db.execute("SELECT * FROM sessions WHERE id=?", (req["session_id"],)).fetchone()
        authorized, is_admin_override = check_is_session_dm_or_superuser(db, user, session)
        if not authorized:
            raise ApiError(403, "Solo el DM o un superusuario pueden forzar tiradas", "FORBIDDEN")

        c = db.execute("SELECT * FROM combatants WHERE id=?", (payload.combatant_id,)).fetchone()
        c_name = c["name"] if c else "Combatiente"
        adv_mode = req["advantage_mode"]

        r1 = random.randint(1, 20)
        r2 = random.randint(1, 20) if adv_mode in ("advantage", "disadvantage") else None
        chosen = _evaluate_check_roll(r1, r2, adv_mode)
        tot = chosen + roll["total_mod"]
        is_succ = 1 if tot >= req["dc"] else 0
        ts = now()
        src = "superuser_force" if is_admin_override else "dm_force"

        db.execute(
            "UPDATE check_rolls SET roll_value_1=?, roll_value_2=?, chosen_roll=?, total=?, is_success=?, status='forced', source=?, rolled_at=? WHERE id=?",
            (r1, r2, chosen, tot, is_succ, src, ts, roll["id"]),
        )

        sk_entry = SKILL_INFO.get(req["skill_slug"]) if req["skill_slug"] else None
        check_title = sk_entry["name"] if sk_entry else f"Característica ({ABILITY_NAMES.get(req['ability'], req['ability'].upper())})"
        verdict = "ÉXITO" if is_succ else "FALLO"

        actor = f"Superusuario '{user['username']}'" if is_admin_override else "DM"
        log_kind = "admin_action" if is_admin_override else "roll"
        log_event(db, req["session_id"], log_kind, f"{actor} forzó prueba de {check_title} de {c_name}: {chosen} + {roll['total_mod']} = {tot} frente a CD {req['dc']} -> {verdict}")

        pending = db.execute(
            "SELECT COUNT(*) AS c FROM check_rolls WHERE request_id=? AND status='pending'",
            (req["id"],),
        ).fetchone()["c"]
        if pending == 0:
            db.execute(
                "UPDATE check_requests SET status='completed', closed_at=? WHERE id=?",
                (ts, req["id"]),
            )
        sid = req["session_id"]

    await broadcast_state(sid)
    return {"ok": True, "total": tot, "chosen_roll": chosen, "total_mod": roll["total_mod"], "is_success": bool(is_succ)}


@app.post("/api/check/skip")
async def check_roll_skip(
    payload: CheckActionIn,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        roll = db.execute(
            "SELECT * FROM check_rolls WHERE request_id=? AND combatant_id=?",
            (payload.request_id, payload.combatant_id),
        ).fetchone()
        if roll is None:
            raise ApiError(404, "Tirada no encontrada", "NOT_FOUND")

        req = db.execute("SELECT * FROM check_requests WHERE id=?", (payload.request_id,)).fetchone()
        if req is None or req["status"] != "active":
            raise ApiError(400, "La solicitud de prueba no está activa", "REQUEST_NOT_ACTIVE")

        if roll["status"] != "pending":
            raise ApiError(409, "Esta tirada ya fue resuelta", "ALREADY_ROLLED")

        session = db.execute("SELECT * FROM sessions WHERE id=?", (req["session_id"],)).fetchone()
        authorized, is_admin_override = check_is_session_dm_or_superuser(db, user, session)
        if not authorized:
            raise ApiError(403, "Solo el DM o un superusuario pueden saltar tiradas", "FORBIDDEN")

        c = db.execute("SELECT * FROM combatants WHERE id=?", (payload.combatant_id,)).fetchone()
        c_name = c["name"] if c else "Combatiente"
        chosen = 10
        tot = chosen + roll["total_mod"]
        is_succ = 1 if tot >= req["dc"] else 0
        ts = now()
        src = "superuser_skip" if is_admin_override else "dm_skip"

        db.execute(
            "UPDATE check_rolls SET roll_value_1=10, roll_value_2=NULL, chosen_roll=10, total=?, is_success=?, status='skipped', source=?, rolled_at=? WHERE id=?",
            (tot, is_succ, src, ts, roll["id"]),
        )

        sk_entry = SKILL_INFO.get(req["skill_slug"]) if req["skill_slug"] else None
        check_title = sk_entry["name"] if sk_entry else f"Característica ({ABILITY_NAMES.get(req['ability'], req['ability'].upper())})"
        verdict = "ÉXITO" if is_succ else "FALLO"

        actor = f"Superusuario '{user['username']}'" if is_admin_override else "DM"
        log_kind = "admin_action" if is_admin_override else "roll"
        log_event(db, req["session_id"], log_kind, f"{actor} saltó prueba (toma 10) de {check_title} de {c_name}: 10 + {roll['total_mod']} = {tot} frente a CD {req['dc']} -> {verdict}")

        pending = db.execute(
            "SELECT COUNT(*) AS c FROM check_rolls WHERE request_id=? AND status='pending'",
            (req["id"],),
        ).fetchone()["c"]
        if pending == 0:
            db.execute(
                "UPDATE check_requests SET status='completed', closed_at=? WHERE id=?",
                (ts, req["id"]),
            )
        sid = req["session_id"]

    await broadcast_state(sid)
    return {"ok": True, "total": tot, "chosen_roll": 10, "total_mod": roll["total_mod"], "is_success": bool(is_succ)}


@app.post("/api/check/cancel")
async def check_request_cancel(
    payload: CheckCancelIn,
    x_user_token: Optional[str] = Header(None),
):
    with get_db() as db:
        user = require_user(db, x_user_token)
        req = db.execute("SELECT * FROM check_requests WHERE id=?", (payload.request_id,)).fetchone()
        if req is None:
            raise ApiError(404, "Solicitud no encontrada", "NOT_FOUND")

        session = db.execute("SELECT * FROM sessions WHERE id=?", (req["session_id"],)).fetchone()
        authorized, is_admin_override = check_is_session_dm_or_superuser(db, user, session)
        if not authorized:
            raise ApiError(403, "Solo el DM o un superusuario pueden cancelar la prueba", "FORBIDDEN")

        ts = now()
        db.execute(
            "UPDATE check_requests SET status='cancelled', closed_at=? WHERE id=?",
            (ts, req["id"]),
        )
        db.execute(
            "UPDATE check_rolls SET status='cancelled' WHERE request_id=? AND status='pending'",
            (req["id"],),
        )

        sk_entry = SKILL_INFO.get(req["skill_slug"]) if req["skill_slug"] else None
        check_title = sk_entry["name"] if sk_entry else f"Característica ({ABILITY_NAMES.get(req['ability'], req['ability'].upper())})"

        if is_admin_override:
            log_event(db, req["session_id"], "admin_action", f"Superusuario '{user['username']}' canceló la prueba de {check_title}")
        else:
            log_event(db, req["session_id"], "system", f"Prueba de {check_title} cancelada por el DM")
        sid = req["session_id"]

    await broadcast_state(sid)
    return {"ok": True}


# ================================================================
# Fase 1: frontend legacy (se conserva tal cual)
# ================================================================

@app.get("/favicon.ico")
@app.get("/favicon.svg")
async def favicon():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect width="32" height="32" rx="6" fill="#e0b45c"/>'
        '<text x="16" y="22" font-family="sans-serif" font-size="14" '
        'font-weight="800" text-anchor="middle" fill="#191d27">d20</text>'
        '</svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


# ============================================================================
# Fase 2.1.1 — Compartir sesion: IP dinamica + QR
# ============================================================================

def get_lan_ips():
    """IPv4s no-loopback, no-link-local. Orden preferente:
    192.168.* > 10.* > 172.* > resto. Deterministico."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass

    result = []
    for ip in ips:
        if ":" in ip:
            continue
        if ip.startswith("127."):
            continue
        if ip.startswith("169.254."):
            continue
        result.append(ip)

    def score(ip):
        if ip.startswith("192.168."):
            return (0, ip)
        if ip.startswith("10."):
            return (1, ip)
        if ip.startswith("172."):
            return (2, ip)
        return (3, ip)

    return sorted(result, key=score)


@app.get("/api/network-info")
async def network_info():
    """IPv4s de la LAN + puerto. Sin auth (la IP ya es publica en LAN)."""
    ips = get_lan_ips()
    port = config.PORT
    urls = [f"http://{ip}:{port}" for ip in ips]
    return {"ips": ips, "port": port, "urls": urls}


@app.get("/api/qr.svg")
async def qr_svg(request: Request):
    """Genera QR SVG para `data` (1-500 chars). Sin auth."""
    data = request.query_params.get("data", "").strip()
    if not data or len(data) > 500:
        raise ApiError(400, "data invalido (1-500 chars)", "INVALID_INPUT")
    qr = segno.make(data, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=6, border=2)
    svg = buf.getvalue().decode("utf-8")
    return Response(content=svg, media_type="image/svg+xml")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
