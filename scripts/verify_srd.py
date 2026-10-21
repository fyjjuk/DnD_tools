#!/usr/bin/env python3
"""Verifica la importacion del bestiario SRD (checklist seccion 7 del informe v2).

Queries 1-7 y 12 son ejecutables con la tabla `monsters`.
Queries 8-11 corresponden a colecciones NO importadas en Fase 1
(spells / equipment / levels); se marcan como SKIP.

Codigo de salida 0 si todo OK, !=0 si algo falla.
"""
import argparse
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config  # noqa: E402

PASS = "OK   "
FAIL = "FALLO"


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        print(f"[{FAIL}] {name}: EXCEPCION {e}")
        return False
    print(f"[{PASS if ok else FAIL}] {name}{(' -- ' + detail) if detail else ''}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=config.SRD_DB_PATH)
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"ERROR: no existe {args.db}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    results = []

    # 1. Goblin
    def q1():
        r = conn.execute(
            "SELECT name, hit_points, armor_class, challenge_rating, xp "
            "FROM monsters WHERE index_slug='goblin'"
        ).fetchone()
        if r is None:
            return False, "no hay fila para 'goblin'"
        ok = (
            r["hit_points"] == 7
            and r["armor_class"] == 15
            and abs(r["challenge_rating"] - 0.25) < 1e-9
            and r["xp"] == 50
        )
        return ok, (
            f"{r['name']} HP={r['hit_points']} AC={r['armor_class']} "
            f"CR={r['challenge_rating']} XP={r['xp']}"
        )

    results.append(check("1. Goblin", q1))

    # 2. CRs fraccionarios presentes
    def q2():
        rows = {
            r["challenge_rating"]
            for r in conn.execute("SELECT DISTINCT challenge_rating FROM monsters")
        }
        required = {0.125, 0.25, 0.5}
        missing = sorted(required - rows)
        return (not missing), f"CRs={sorted(rows)} faltan={missing}"

    results.append(check("2. CRs fraccionarios (0.125/0.25/0.5)", q2))

    # 3. Sin CR NULL
    def q3():
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM monsters WHERE challenge_rating IS NULL"
        ).fetchone()["n"]
        return (n == 0), f"{n} filas con CR NULL"

    results.append(check("3. Sin CR NULL", q3))

    # 4. Total 334
    def q4():
        n = conn.execute("SELECT COUNT(*) AS n FROM monsters").fetchone()["n"]
        return (n == 334), f"{n} filas (esperado 334)"

    results.append(check("4. Total = 334", q4))

    # 5. Todos con acciones o habilidades
    def q5():
        n = conn.execute(
            """
            SELECT COUNT(*) AS n FROM monsters
            WHERE json_extract(data,'$.actions') IS NULL
              AND json_extract(data,'$.special_abilities') IS NULL
              AND json_extract(data,'$.legendary_actions') IS NULL
            """
        ).fetchone()["n"]
        return (n == 0), f"{n} monstruos sin acciones/habilidades"

    results.append(check("5. Monstruos sin acciones/habilidades = 0", q5))

    # 6. Ankheg: AC array multi
    def q6():
        r = conn.execute(
            """
            SELECT armor_class, armor_class_type,
                   json_array_length(json_extract(data,'$.armor_class')) AS ac_len
            FROM monsters WHERE index_slug='ankheg'
            """
        ).fetchone()
        if r is None:
            return False, "no hay fila para 'ankheg'"
        ok = (
            r["armor_class"] == 14
            and r["armor_class_type"] == "natural"
            and r["ac_len"] == 2
        )
        return ok, (
            f"AC={r['armor_class']} tipo={r['armor_class_type']} ac_len={r['ac_len']}"
        )

    results.append(check("6. Ankheg (AC array multi)", q6))

    # 7. Aboleth STR..CHA
    def q7():
        r = conn.execute(
            """
            SELECT strength, dexterity, constitution, intelligence, wisdom, charisma
            FROM monsters WHERE index_slug='aboleth'
            """
        ).fetchone()
        if r is None:
            return False, "no hay fila para 'aboleth'"
        expected = (21, 9, 15, 18, 15, 18)
        actual = (
            r["strength"], r["dexterity"], r["constitution"],
            r["intelligence"], r["wisdom"], r["charisma"],
        )
        return (actual == expected), f"{actual}"

    results.append(check("7. Aboleth STR..CHA", q7))

    # 8-11: no aplican (spells / equipment / levels no importados en Fase 1)
    print("[SKIP ] 8. Fireball (spells no importado)")
    print("[SKIP ] 9. Longsword (equipment no importado)")
    print("[SKIP ] 10. Cross-check damage_type (equipment no importado)")
    print("[SKIP ] 11. Fighter niveles (levels no importado)")

    # 12. import_meta monsters
    def q12():
        r = conn.execute(
            "SELECT record_count, errors_json FROM import_meta "
            "WHERE collection_slug='monsters' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if r is None:
            return False, "no hay fila en import_meta para 'monsters'"
        ok = r["record_count"] == 334 and r["errors_json"] in (None, "", "[]")
        return ok, f"record_count={r['record_count']} errors={r['errors_json']}"

    results.append(check("12. import_meta monsters", q12))

    conn.close()

    failed = sum(1 for r in results if not r)
    print()
    print(f"{len(results) - failed}/{len(results)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
