#!/usr/bin/env python3
"""Importa el bestiario SRD 5e (2014) en espanol a la SQLite del MVP.

- Solo coleccion Monsters (334 registros). Fase 1.
- Idempotente: dropea y recrea SOLO monsters + filas de collections/import_meta
  con slug/collection_slug='monsters'. No toca sessions/players/combatants/events.
- Si un registro falla, lo anota en import_meta.errors_json y sigue.
- Sin dependencias fuera de la stdlib.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config  # noqa: E402


DDL_COLLECTIONS = """
CREATE TABLE IF NOT EXISTS collections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'srd-2014-es',
    imported_at   TEXT NOT NULL,
    record_count  INTEGER NOT NULL DEFAULT 0
);
"""

DDL_IMPORT_META = """
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
"""

DDL_MONSTERS = """
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
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def map_monster(record: dict, collection_id: int) -> dict:
    """Convierte un registro de Monsters (es/) en kwargs para INSERT.

    armor_class es un array; tomamos [0].{value,type} como columnas reales
    y guardamos el registro completo en `data`.
    """
    ac = record.get("armor_class") or []
    ac0_value = ac[0]["value"] if ac else None
    ac0_type = ac[0]["type"] if ac else None
    return {
        "collection_id": collection_id,
        "index_slug": record["index"],
        "name": record["name"],
        "size": record.get("size"),
        "type": record.get("type"),
        "subtype": record.get("subtype"),
        "alignment": record.get("alignment"),
        "hit_points": int(record["hit_points"]),
        "hit_dice": record.get("hit_dice"),
        "hit_points_roll": record.get("hit_points_roll"),
        "armor_class": ac0_value,
        "armor_class_type": ac0_type,
        "challenge_rating": float(record["challenge_rating"]),
        "xp": int(record["xp"]),
        "strength": record.get("strength"),
        "dexterity": record.get("dexterity"),
        "constitution": record.get("constitution"),
        "intelligence": record.get("intelligence"),
        "wisdom": record.get("wisdom"),
        "charisma": record.get("charisma"),
        "proficiency_bonus": record.get("proficiency_bonus"),
        "damage_immunities_json": (
            json.dumps(record["damage_immunities"], ensure_ascii=False)
            if "damage_immunities" in record
            else "[]"
        ),
        "damage_resistances_json": (
            json.dumps(record["damage_resistances"], ensure_ascii=False)
            if "damage_resistances" in record
            else "[]"
        ),
        "damage_vulnerabilities_json": (
            json.dumps(record["damage_vulnerabilities"], ensure_ascii=False)
            if "damage_vulnerabilities" in record
            else "[]"
        ),
        "condition_immunities_json": (
            json.dumps(record["condition_immunities"], ensure_ascii=False)
            if "condition_immunities" in record
            else "[]"
        ),
        "special_abilities_json": (
            json.dumps(record["special_abilities"], ensure_ascii=False)
            if record.get("special_abilities") is not None
            else None
        ),
        "actions_json": (
            json.dumps(record["actions"], ensure_ascii=False)
            if record.get("actions") is not None
            else None
        ),
        "legendary_actions_json": (
            json.dumps(record["legendary_actions"], ensure_ascii=False)
            if record.get("legendary_actions") is not None
            else None
        ),
        "reactions_json": (
            json.dumps(record["reactions"], ensure_ascii=False)
            if record.get("reactions") is not None
            else None
        ),
        "data": json.dumps(record, ensure_ascii=False),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa el bestiario SRD 5e (Monsters) al MVP."
    )
    parser.add_argument(
        "--srd-dir",
        default=getattr(config, "SRD_DIR", None),
        help="Directorio con 5e-SRD-Monsters.json (default: config.SRD_DIR)",
    )
    parser.add_argument(
        "--db", default=config.SRD_DB_PATH, help="Ruta de la SQLite del SRD"
    )
    args = parser.parse_args()

    if not args.srd_dir:
        print(
            "ERROR: no se ha indicado SRD_DIR en config.py ni con --srd-dir",
            file=sys.stderr,
        )
        return 2

    src = os.path.join(args.srd_dir, "5e-SRD-Monsters.json")
    if not os.path.exists(src):
        print(f"ERROR: no existe {src}", file=sys.stderr)
        return 2

    try:
        with open(src, "r", encoding="utf-8") as fh:
            monsters = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"ERROR: {src} no es JSON valido: {e}", file=sys.stderr)
        return 2

    file_hash = file_sha256(src)
    total = len(monsters)
    inserted = 0
    errors = []

    db_dir = os.path.dirname(args.db)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(DDL_COLLECTIONS)
        conn.executescript(DDL_IMPORT_META)

        ts = now_iso()

        # Idempotencia: asegurar coleccion 'monsters' y obtener su ID
        cur = conn.execute("SELECT id FROM collections WHERE slug='monsters'")
        crow = cur.fetchone()
        if crow:
            collection_id = crow["id"]
        else:
            cur = conn.execute(
                "INSERT INTO collections (slug, name, source, imported_at, record_count) "
                "VALUES ('monsters', 'Monsters', 'srd-2014-es', ?, 0)",
                (ts,),
            )
            collection_id = cur.lastrowid

        # Recrear solo tabla monsters y limpiar import_meta de monsters
        conn.execute("DROP TABLE IF EXISTS monsters")
        conn.executescript(DDL_MONSTERS)
        conn.execute("DELETE FROM import_meta WHERE collection_slug='monsters'")

        for rec in monsters:
            try:
                row = map_monster(rec, collection_id)
                cols = list(row.keys())
                placeholders = ",".join(["?"] * len(cols))
                conn.execute(
                    f"INSERT INTO monsters ({','.join(cols)}) "
                    f"VALUES ({placeholders})",
                    [row[c] for c in cols],
                )
                inserted += 1
            except Exception as e:
                errors.append({"index": rec.get("index", "?"), "error": str(e)})

        errors_json = json.dumps(errors, ensure_ascii=False) if errors else None

        conn.execute(
            "UPDATE collections SET imported_at=?, record_count=? WHERE id=?",
            (ts, inserted, collection_id),
        )
        conn.execute(
            "INSERT INTO import_meta (collection_slug, source_path, source_locale, "
            "file_hash, imported_at, record_count, errors_json) "
            "VALUES ('monsters', ?, 'es', ?, ?, ?, ?)",
            (src, file_hash, ts, inserted, errors_json),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Fuente:     {src}")
    print(f"SHA-256:    {file_hash}")
    print(f"Registros:  {total}")
    print(f"Insertados: {inserted}")
    print(f"Errores:    {len(errors)}")
    if errors:
        for e in errors[:10]:
            print(f"  - {e['index']}: {e['error']}")
        if len(errors) > 10:
            print(f"  ... y {len(errors) - 10} mas (ver import_meta.errors_json)")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
