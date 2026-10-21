#!/usr/bin/env python3
"""Importa el compendio SRD 5e (2014) en español a la SQLite del MVP (srd.db).

Fase 2.2 — Importación Completa:
- Referencias: conditions, damage-types, ability-scores, skills,
  equipment-categories, proficiencies, weapon-properties, magic-schools.
- Entidades: monsters, equipment, classes, levels, races, spells.
- Idempotente: actualiza o recrea las tablas y metadatos sin tocar bases externas.
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
from backend.db import SCHEMA_SRD  # noqa: E402

REFERENCE_COLLECTIONS = [
    ("conditions", "5e-SRD-Conditions.json", "Conditions"),
    ("damage-types", "5e-SRD-Damage-Types.json", "Damage Types"),
    ("ability-scores", "5e-SRD-Ability-Scores.json", "Ability Scores"),
    ("skills", "5e-SRD-Skills.json", "Skills"),
    ("equipment-categories", "5e-SRD-Equipment-Categories.json", "Equipment Categories"),
    ("proficiencies", "5e-SRD-Proficiencies.json", "Proficiencies"),
    ("weapon-properties", "5e-SRD-Weapon-Properties.json", "Weapon Properties"),
    ("magic-schools", "5e-SRD-Magic-Schools.json", "Magic Schools"),
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_collection(conn: sqlite3.Connection, slug: str, name: str, ts: str) -> int:
    cur = conn.execute("SELECT id FROM collections WHERE slug=?", (slug,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO collections (slug, name, source, imported_at, record_count) "
        "VALUES (?, ?, 'srd-2014-es', ?, 0)",
        (slug, name, ts),
    )
    return cur.lastrowid


def map_monster(record: dict, collection_id: int) -> dict:
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


def map_equipment(record: dict, collection_id: int) -> dict:
    cost = record.get("cost") or {}
    cost_unit_raw = cost.get("unit")
    cost_unit_map = {"po": "gp", "pe": "sp", "pc": "cp"}
    cost_unit = cost_unit_map.get(cost_unit_raw, cost_unit_raw)

    dmg = record.get("damage") or {}
    dmg_type = dmg.get("damage_type") or {}

    ac = record.get("armor_class") or {}

    return {
        "collection_id": collection_id,
        "index_slug": record["index"],
        "name": record["name"],
        "equipment_category_slug": record.get("equipment_category", {}).get("index"),
        "weapon_category": record.get("weapon_category"),
        "armor_category": record.get("armor_category"),
        "cost_quantity": cost.get("quantity"),
        "cost_unit": cost_unit,
        "cost_unit_raw": cost_unit_raw,
        "weight": record.get("weight"),
        "damage_dice": dmg.get("damage_dice"),
        "damage_type_slug": dmg_type.get("index"),
        "armor_class_base": ac.get("base"),
        "armor_class_dex_bonus": 1 if ac.get("dex_bonus") else 0 if "dex_bonus" in ac else None,
        "armor_class_max_bonus": ac.get("max_bonus"),
        "data": json.dumps(record, ensure_ascii=False),
    }


def map_class(record: dict, collection_id: int) -> dict:
    sc = record.get("spellcasting") or {}
    ability = sc.get("spellcasting_ability", {}).get("index") if sc else None
    return {
        "collection_id": collection_id,
        "index_slug": record["index"],
        "name": record["name"],
        "hit_die": record.get("hit_die"),
        "spellcasting_ability_slug": ability,
        "data": json.dumps(record, ensure_ascii=False),
    }


def map_level(record: dict, collection_id: int) -> dict:
    cls_obj = record.get("class") or {}
    subcls_obj = record.get("subclass") or {}
    return {
        "collection_id": collection_id,
        "index_slug": record["index"],
        "class_slug": cls_obj.get("index"),
        "subclass_slug": subcls_obj.get("index"),
        "level": int(record["level"]),
        "prof_bonus": record.get("prof_bonus"),
        "data": json.dumps(record, ensure_ascii=False),
    }


def map_race(record: dict, collection_id: int) -> dict:
    return {
        "collection_id": collection_id,
        "index_slug": record["index"],
        "name": record["name"],
        "speed": record.get("speed"),
        "size": record.get("size"),
        "data": json.dumps(record, ensure_ascii=False),
    }


def map_spell(record: dict, collection_id: int) -> dict:
    school = record.get("school") or {}
    comps = record.get("components")
    if isinstance(comps, list):
        comps_str = ",".join(comps)
    else:
        comps_str = comps
    return {
        "collection_id": collection_id,
        "index_slug": record["index"],
        "name": record["name"],
        "level": int(record["level"]),
        "school_slug": school.get("index"),
        "casting_time": record.get("casting_time"),
        "range": record.get("range"),
        "duration": record.get("duration"),
        "concentration": 1 if record.get("concentration") else 0,
        "ritual": 1 if record.get("ritual") else 0,
        "components": comps_str,
        "attack_type": record.get("attack_type"),
        "data": json.dumps(record, ensure_ascii=False),
    }


def import_references(conn: sqlite3.Connection, srd_dir: str, ts: str) -> dict:
    stats = {}
    for slug, filename, name in REFERENCE_COLLECTIONS:
        src = os.path.join(srd_dir, filename)
        if not os.path.exists(src):
            print(f"AVISO: No se encuentra {src}, saltando.")
            continue

        with open(src, "r", encoding="utf-8") as fh:
            items = json.load(fh)

        file_hash = file_sha256(src)
        cid = ensure_collection(conn, slug, name, ts)

        conn.execute("DELETE FROM reference_entries WHERE collection_id=?", (cid,))
        conn.execute("DELETE FROM import_meta WHERE collection_slug=?", (slug,))

        inserted = 0
        errors = []
        for it in items:
            try:
                conn.execute(
                    "INSERT INTO reference_entries (collection_id, index_slug, name, data) "
                    "VALUES (?, ?, ?, ?)",
                    (cid, it["index"], it["name"], json.dumps(it, ensure_ascii=False)),
                )
                inserted += 1
            except Exception as e:
                errors.append({"index": it.get("index", "?"), "error": str(e)})

        err_json = json.dumps(errors, ensure_ascii=False) if errors else None
        conn.execute(
            "UPDATE collections SET imported_at=?, record_count=? WHERE id=?",
            (ts, inserted, cid),
        )
        conn.execute(
            "INSERT INTO import_meta (collection_slug, source_path, source_locale, "
            "file_hash, imported_at, record_count, errors_json) "
            "VALUES (?, ?, 'es', ?, ?, ?, ?)",
            (slug, src, file_hash, ts, inserted, err_json),
        )
        stats[slug] = inserted
    return stats


def import_entity_table(
    conn: sqlite3.Connection,
    srd_dir: str,
    ts: str,
    slug: str,
    filename: str,
    table_name: str,
    map_fn,
) -> int:
    src = os.path.join(srd_dir, filename)
    if not os.path.exists(src):
        print(f"ERROR: No se encuentra {src}")
        return 0

    with open(src, "r", encoding="utf-8") as fh:
        records = json.load(fh)

    file_hash = file_sha256(src)
    cid = ensure_collection(conn, slug, slug.title(), ts)

    conn.execute(f"DELETE FROM {table_name}")
    conn.execute("DELETE FROM import_meta WHERE collection_slug=?", (slug,))

    inserted = 0
    errors = []
    for rec in records:
        try:
            row = map_fn(rec, cid)
            cols = list(row.keys())
            placeholders = ",".join(["?"] * len(cols))
            conn.execute(
                f"INSERT INTO {table_name} ({','.join(cols)}) VALUES ({placeholders})",
                [row[c] for c in cols],
            )
            inserted += 1
        except Exception as e:
            errors.append({"index": rec.get("index", "?"), "error": str(e)})

    err_json = json.dumps(errors, ensure_ascii=False) if errors else None
    conn.execute(
        "UPDATE collections SET imported_at=?, record_count=? WHERE id=?",
        (ts, inserted, cid),
    )
    conn.execute(
        "INSERT INTO import_meta (collection_slug, source_path, source_locale, "
        "file_hash, imported_at, record_count, errors_json) "
        "VALUES (?, ?, 'es', ?, ?, ?, ?)",
        (slug, src, file_hash, ts, inserted, err_json),
    )
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa el compendio SRD 5e completo a srd.db."
    )
    parser.add_argument(
        "--srd-dir",
        default=getattr(config, "SRD_DIR", None),
        help="Directorio con los JSON del SRD (default: config.SRD_DIR)",
    )
    parser.add_argument(
        "--db", default=config.SRD_DB_PATH, help="Ruta de la SQLite del SRD"
    )
    args = parser.parse_args()

    if not args.srd_dir or not os.path.isdir(args.srd_dir):
        print(f"ERROR: directorio SRD no válido: {args.srd_dir}", file=sys.stderr)
        return 2

    db_dir = os.path.dirname(args.db)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        # Asegurar esquema completo del SRD
        conn.executescript(SCHEMA_SRD)
        ts = now_iso()

        print("=== 1. IMPORTANDO COLECCIONES DE REFERENCIA ===")
        ref_stats = import_references(conn, args.srd_dir, ts)
        for slug, count in ref_stats.items():
            print(f"  [OK] {slug:22}: {count:4} registros en reference_entries")

        print("\n=== 2. IMPORTANDO ENTIDADES PRINCIPALES ===")
        entities = [
            ("monsters", "5e-SRD-Monsters.json", "monsters", map_monster),
            ("equipment", "5e-SRD-Equipment.json", "equipment", map_equipment),
            ("classes", "5e-SRD-Classes.json", "classes", map_class),
            ("levels", "5e-SRD-Levels.json", "levels", map_level),
            ("races", "5e-SRD-Races.json", "races", map_race),
            ("spells", "5e-SRD-Spells.json", "spells", map_spell),
        ]

        entity_stats = {}
        for slug, fname, tbl, map_fn in entities:
            count = import_entity_table(conn, args.srd_dir, ts, slug, fname, tbl, map_fn)
            entity_stats[slug] = count
            print(f"  [OK] {slug:22}: {count:4} registros en {tbl}")

        conn.commit()
    finally:
        conn.close()

    print("\n=== IMPORTACIÓN SRD COMPLETA FINALIZADA CON ÉXITO ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
