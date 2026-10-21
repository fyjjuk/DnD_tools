"""Fase 2.1.2-B-2: Reconciliación del SRD.
Migración reproducible e idempotente para data/srd.db:
- Añade collection_id a la tabla monsters y la vincula con la colección 'monsters'.
- Añade las 8 columnas JSON (damage_immunities_json, damage_resistances_json,
  damage_vulnerabilities_json, condition_immunities_json, special_abilities_json,
  actions_json, legendary_actions_json, reactions_json).
- Puebla estas columnas usando json_extract(data, '$.campo') para todos los monstruos.
- Asegura la existencia de reference_entries e importa 'conditions' y 'damage-types'.

Uso:
    python -m backend.migration_2_1_2b_2
"""
import json
import os
import sqlite3
import sys

import config

JSON_COLUMNS = [
    ("collection_id", "INTEGER"),
    ("damage_immunities_json", "TEXT"),
    ("damage_resistances_json", "TEXT"),
    ("damage_vulnerabilities_json", "TEXT"),
    ("condition_immunities_json", "TEXT"),
    ("special_abilities_json", "TEXT"),
    ("actions_json", "TEXT"),
    ("legendary_actions_json", "TEXT"),
    ("reactions_json", "TEXT"),
]

DDL_REFERENCE_ENTRIES = """
CREATE TABLE IF NOT EXISTS reference_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    index_slug    TEXT NOT NULL,
    name          TEXT NOT NULL,
    data          TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ref_coll_slug ON reference_entries(collection_id, index_slug);
CREATE INDEX IF NOT EXISTS idx_ref_coll ON reference_entries(collection_id);
"""


def get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def migrate(db_path: str = config.SRD_DB_PATH) -> int:
    print(f"SRD DB: {db_path}")

    if not os.path.exists(db_path):
        print(f"AVISO: No existe {db_path}. Se creará o esperará inicialización.")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # 1. Asegurar collection 'monsters'
        cur = conn.execute("SELECT id FROM collections WHERE slug='monsters'")
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO collections (slug, name, source, imported_at, record_count) "
                "VALUES ('monsters', 'Monsters', 'srd-2014-es', datetime('now'), 0)"
            )
            monsters_cid = cur.lastrowid
            print(f"Colección 'monsters' creada con ID={monsters_cid}.")
        else:
            monsters_cid = row[0]
            print(f"Colección 'monsters' existente con ID={monsters_cid}.")

        # 2. Comprobar columnas en 'monsters'
        existing_cols = get_table_columns(conn, "monsters")
        added_cols = []
        for col_name, col_type in JSON_COLUMNS:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE monsters ADD COLUMN {col_name} {col_type}")
                added_cols.append(col_name)

        if added_cols:
            print(f"Columnas añadidas a monsters: {', '.join(added_cols)}")
        else:
            print("[OK] Columnas ya presentes en tabla monsters.")

        # 3. Poblar datos JSON si hay registros sin collection_id o columnas recién añadidas
        pending_update = conn.execute(
            "SELECT COUNT(*) FROM monsters WHERE collection_id IS NULL"
        ).fetchone()[0]

        if pending_update > 0 or added_cols:
            print(f"Actualizando columnas JSON para registros de monsters ({pending_update} pendientes)...")
            conn.execute(
                """
                UPDATE monsters SET
                    collection_id = ?,
                    damage_immunities_json = json_extract(data, '$.damage_immunities'),
                    damage_resistances_json = json_extract(data, '$.damage_resistances'),
                    damage_vulnerabilities_json = json_extract(data, '$.damage_vulnerabilities'),
                    condition_immunities_json = json_extract(data, '$.condition_immunities'),
                    special_abilities_json = json_extract(data, '$.special_abilities'),
                    actions_json = json_extract(data, '$.actions'),
                    legendary_actions_json = json_extract(data, '$.legendary_actions'),
                    reactions_json = json_extract(data, '$.reactions')
                """,
                (monsters_cid,),
            )
            print("[OK] Actualización de columnas JSON completada.")
        else:
            print("[OK] Idempotencia: registros de monsters ya están poblados.")

        # 4. Asegurar reference_entries y colecciones de referencia
        conn.executescript(DDL_REFERENCE_ENTRIES)

        srd_dir = getattr(config, "SRD_DIR", "")
        ref_files = [
            ("conditions", "5e-SRD-Conditions.json"),
            ("damage-types", "5e-SRD-Damage-Types.json"),
        ]

        for slug, filename in ref_files:
            cur.execute("SELECT id FROM collections WHERE slug=?", (slug,))
            crow = cur.fetchone()

            # Verificar si ya existen referencias en la tabla
            existing_refs = 0
            if crow:
                existing_refs = conn.execute(
                    "SELECT COUNT(*) FROM reference_entries WHERE collection_id=?",
                    (crow[0],),
                ).fetchone()[0]

            if existing_refs > 0:
                print(f"[OK] Colección '{slug}' ya tiene {existing_refs} registros en reference_entries.")
                continue

            filepath = os.path.join(srd_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as fh:
                    items = json.load(fh)

                if crow:
                    cid = crow[0]
                    cur.execute(
                        "UPDATE collections SET record_count=? WHERE id=?",
                        (len(items), cid),
                    )
                else:
                    cur.execute(
                        "INSERT INTO collections (slug, name, source, imported_at, record_count) "
                        "VALUES (?, ?, 'srd-2014-es', datetime('now'), ?)",
                        (slug, slug.title(), len(items)),
                    )
                    cid = cur.lastrowid

                cur.execute("DELETE FROM reference_entries WHERE collection_id=?", (cid,))
                for item in items:
                    cur.execute(
                        "INSERT INTO reference_entries (collection_id, index_slug, name, data) "
                        "VALUES (?, ?, ?, ?)",
                        (cid, item["index"], item["name"], json.dumps(item, ensure_ascii=False)),
                    )
                print(f"[OK] Colección '{slug}': {len(items)} registros insertados en reference_entries.")

        conn.commit()

        # Verificación de integridad final
        null_cid = conn.execute(
            "SELECT COUNT(*) FROM monsters WHERE collection_id IS NULL"
        ).fetchone()[0]
        if null_cid != 0:
            raise RuntimeError(f"Fallo de verificación: {null_cid} monstruos con collection_id NULL")

        total_m = conn.execute("SELECT COUNT(*) FROM monsters").fetchone()[0]
        print(f"[OK] Migración 2.1.2-B-2 finalizada. Total monsters={total_m}, collection_id NULL={null_cid}.")
        return 0
    finally:
        conn.close()


def main() -> int:
    try:
        return migrate()
    except Exception as e:
        print(f"ERROR en migración 2.1.2-B-2: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
