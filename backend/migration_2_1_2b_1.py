"""Fase 2.1.2-B-1: Split de base de datos.
Separa el contenido SRD (monsters, collections, import_meta) de dnd.db
hacia data/srd.db, e inicializa data/homebrew.db.

Uso:
    python -m backend.migration_2_1_2b_1

Idempotente: si detecta que las tablas ya no estan en dnd.db o ya
fueron migradas, no hace nada y termina con exito.
"""
import os
import sqlite3
import sys

import config
from backend.db import init_homebrew_db, init_srd_db

SRD_TABLES = ["collections", "import_meta", "monsters"]


def get_existing_tables(conn, schema: str = "main") -> set[str]:
    cur = conn.execute(f"SELECT name FROM {schema}.sqlite_master WHERE type='table'")
    return {row[0] for row in cur.fetchall()}


def migrate() -> int:
    print(f"Main DB:     {config.DB_PATH}")
    print(f"SRD DB:      {config.SRD_DB_PATH}")
    print(f"Homebrew DB: {config.HOMEBREW_DB_PATH}")

    # Asegurar que homebrew.db y srd.db esten inicializadas con sus esquemas
    init_srd_db()
    init_homebrew_db()

    if not os.path.exists(config.DB_PATH):
        print("AVISO: Main DB no existe todavia. Nada que migrar.")
        return 0

    conn = sqlite3.connect(config.DB_PATH)
    try:
        main_tables = get_existing_tables(conn, "main")
        tables_to_migrate = [t for t in SRD_TABLES if t in main_tables]

        if not tables_to_migrate:
            print("[OK] Idempotencia: no hay tablas SRD pendientes de migrar en dnd.db.")
            return 0

        print(f"Tablas a migrar desde dnd.db: {tables_to_migrate}")

        # Adjuntar srd.db
        conn.execute("ATTACH DATABASE ? AS srd", (config.SRD_DB_PATH,))

        for table in tables_to_migrate:
            main_count = conn.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
            print(f"  Migrando '{table}' ({main_count} filas)...")
            conn.execute(
                f"INSERT OR REPLACE INTO srd.{table} SELECT * FROM main.{table}"
            )
            srd_count = conn.execute(f"SELECT COUNT(*) FROM srd.{table}").fetchone()[0]
            if srd_count < main_count:
                raise RuntimeError(
                    f"Fallo de verificacion en '{table}': esperadas {main_count}, encontradas {srd_count} en srd.db"
                )
            print(f"  Verificacion OK: '{table}' en srd.db tiene {srd_count} filas.")
            conn.execute(f"DROP TABLE IF EXISTS main.{table}")
            print(f"  DROP TABLE main.{table} completado.")

        conn.commit()
        conn.execute("DETACH DATABASE srd")
        print("[OK] Migracion de tablas completada con exito.")
    finally:
        conn.close()

    # Reclamar espacio en dnd.db tras dropear las tablas
    try:
        vac_conn = sqlite3.connect(config.DB_PATH)
        vac_conn.execute("VACUUM")
        vac_conn.close()
        print("[OK] VACUUM ejecutado en dnd.db.")
    except Exception as e:
        print(f"AVISO: No se pudo ejecutar VACUUM en dnd.db: {e}")

    return 0


def main() -> int:
    try:
        return migrate()
    except Exception as e:
        print(f"ERROR en migracion: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
