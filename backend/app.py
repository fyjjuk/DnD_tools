"""API REST + WebSocket del MVP de combate D&D 5e."""
import datetime
import json
import os
import secrets
import sqlite3
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from backend.db import get_db, init_db
from backend.ws import ConnectionManager

BASE_DIR = config.BASE_DIR
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = FastAPI(title="DnD 5e Combat MVP")
manager = ConnectionManager()

init_db()


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


def require_dm(db, token):
    session = fetch_active_session(db)
    if session is None:
        raise HTTPException(status_code=404, detail="No hay sesion activa")
    if not token or token != session["dm_token"]:
        raise HTTPException(status_code=403, detail="Token de DM invalido")
    return session


def require_any_dm(db, token):
    """Acepta cualquier dm_token existente (activo o cerrado)."""
    if not token:
        raise HTTPException(status_code=403, detail="Token de DM requerido")
    row = db.execute("SELECT 1 FROM sessions WHERE dm_token=?", (token,)).fetchone()
    if row is None:
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


def build_state(session, combatants, players, role, player_id):
    ordered = sorted(combatants, key=lambda c: (-c["initiative"], c["id"]))
    out = []
    for c in ordered:
        is_me = role == "player" and c["player_id"] is not None and c["player_id"] == player_id
        show_hp = (role == "dm") or is_me
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
        })
    return {
        "type": "state",
        "session": {
            "code": session["code"],
            "status": session["status"],
            "round": session["round"],
            "turn_combatant_id": session["turn_combatant_id"],
        },
        "combatants": out,
        "players": [{"id": p["id"], "name": p["name"]} for p in players],
    }


async def broadcast_state(session_id: int):
    with get_db() as db:
        session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if session is None:
            return
        combatants = db.execute(
            "SELECT * FROM combatants WHERE session_id=?", (session_id,)
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
        raise HTTPException(status_code=500, detail="DM_PASSWORD no configurada en config.py")
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
    return {
        "session_id": session["id"],
        "code": session["code"],
        "dm_token": session["dm_token"],
        "round": session["round"],
    }


@app.post("/api/session/close")
async def close_session(x_dm_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token)
        sid, code = session["id"], session["code"]
        log_event(db, sid, "session", "Sesion cerrada por el DM")
        db.execute("UPDATE sessions SET status='closed', closed_at=? WHERE id=?", (now(), sid))
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
async def join(payload: JoinIn):
    code = payload.code.strip().upper()
    name = payload.name.strip()
    if not name or len(name) > 40:
        raise HTTPException(status_code=400, detail="Nombre invalido")

    with get_db() as db:
        session = fetch_active_session(db)
        if session is None or session["code"] != code:
            raise HTTPException(status_code=404, detail="Codigo de sesion invalido")

        existing = db.execute(
            "SELECT * FROM players WHERE session_id=? AND lower(name)=lower(?)",
            (session["id"], name),
        ).fetchone()
        if existing:
            player = existing
        else:
            token = secrets.token_urlsafe(24)
            cur = db.execute(
                "INSERT INTO players (session_id, name, token, created_at) VALUES (?,?,?,?)",
                (session["id"], name, token, now()),
            )
            player = db.execute("SELECT * FROM players WHERE id=?", (cur.lastrowid,)).fetchone()
            log_event(db, session["id"], "player", f"{name} se unio")
            # auto-vinculo con un PJ del mismo nombre que aun no tenga jugador
            db.execute(
                "UPDATE combatants SET player_id=? "
                "WHERE session_id=? AND kind='pc' AND player_id IS NULL AND lower(name)=lower(?)",
                (player["id"], session["id"], name),
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
async def player_me(x_player_token: Optional[str] = Header(None)):
    with get_db() as db:
        player = db.execute("SELECT * FROM players WHERE token=?", (x_player_token,)).fetchone()
        if player is None:
            raise HTTPException(status_code=404, detail="Token invalido")
        session = db.execute("SELECT * FROM sessions WHERE id=?", (player["session_id"],)).fetchone()
        if session is None or session["status"] != "active":
            raise HTTPException(status_code=404, detail="Sesion cerrada")
    return {
        "player_id": player["id"],
        "name": player["name"],
        "session_id": session["id"],
        "code": session["code"],
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
async def add_combatant(payload: CombatantIn, x_dm_token: Optional[str] = Header(None)):
    name = (payload.name or "").strip()
    hp_max = payload.hp_max

    if payload.srd_index:
        with get_db() as db:
            try:
                srd = db.execute(
                    "SELECT name, hit_points FROM monsters WHERE index_slug = ?",
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

    with get_db() as db:
        session = require_dm(db, x_dm_token)
        cur = db.execute(
            "INSERT INTO combatants (session_id, name, hp_max, hp_current, initiative, kind, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (session["id"], name, hp_max, hp_max, int(payload.initiative), kind, now()),
        )
        cid = cur.lastrowid

        if kind == "pc":
            player = db.execute(
                "SELECT id FROM players WHERE session_id=? AND lower(name)=lower(?)",
                (session["id"], name),
            ).fetchone()
            if player:
                db.execute("UPDATE combatants SET player_id=? WHERE id=?", (player["id"], cid))

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
async def remove_combatant(cid: int, x_dm_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token)
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
async def change_hp(cid: int, payload: HpIn, x_dm_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token)
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
async def undo_hp(cid: int, x_dm_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token)
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
async def link_player(cid: int, payload: LinkIn, x_dm_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token)
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
        else:
            db.execute("UPDATE combatants SET player_id=NULL WHERE id=?", (cid,))
        sid = session["id"]

    await broadcast_state(sid)
    return {"ok": True}


@app.post("/api/turn/next")
async def next_turn(x_dm_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token)
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
async def next_round(x_dm_token: Optional[str] = Header(None)):
    with get_db() as db:
        session = require_dm(db, x_dm_token)
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
async def list_closed_sessions(x_dm_token: Optional[str] = Header(None)):
    with get_db() as db:
        require_any_dm(db, x_dm_token)
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
async def get_session_log(code: str, x_dm_token: Optional[str] = Header(None)):
    with get_db() as db:
        require_any_dm(db, x_dm_token)
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
):
    """Lista/busca monstruos del bestiario SRD (solo lectura, sin token).

    Si la tabla `monsters` no existe (SRD no importado todavia), devuelve
    una lista vacia en lugar de 500: el servidor arranca y /dm funciona.
    """
    limit = max(1, min(int(limit), 200))

    sql = (
        "SELECT index_slug, name, hit_points, armor_class, challenge_rating, "
        "       type, size, xp, dexterity "
        "FROM monsters WHERE 1=1"
    )
    params: list = []
    if q:
        sql += " AND (name LIKE ? OR index_slug LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if cr_min is not None:
        sql += " AND challenge_rating >= ?"
        params.append(cr_min)
    if cr_max is not None:
        sql += " AND challenge_rating <= ?"
        params.append(cr_max)
    if type:
        sql += " AND type = ?"
        params.append(type)
    if size:
        sql += " AND size = ?"
        params.append(size)
    sql += " ORDER BY name COLLATE NOCASE LIMIT ?"
    params.append(limit)

    try:
        with get_db() as db:
            rows = db.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return {"items": []}

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
        ]
    }


@app.get("/api/srd/monsters/{index}")
async def srd_monster(index: str):
    """Ficha completa de un monstruo del bestiario SRD (solo lectura, sin token)."""
    try:
        with get_db() as db:
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
            session = fetch_active_session(db)
            if session is None or session["dm_token"] != token:
                await websocket.close(code=4003)
                return
            session_id, player_id = session["id"], None
        else:
            player = db.execute("SELECT * FROM players WHERE token=?", (token,)).fetchone()
            if player is None:
                await websocket.close(code=4003)
                return
            session = db.execute(
                "SELECT * FROM sessions WHERE id=?", (player["session_id"],)
            ).fetchone()
            if session is None:
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


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
