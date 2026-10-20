"""Fase 2.1: resetea la password del user 'dm' a DM_PASSWORD (config.py).

Uso (con el servidor PARADO, desde la raiz del proyecto):
    python -m backend.reset_dm_password

Caso tipico: has cambiado DM_PASSWORD en config.py y quieres que el
login por cuenta (/login) del user 'dm' acepte la nueva. El flujo legacy
(/dm con DM_PASSWORD via /api/dm/bootstrap) no necesita este script:
lee DM_PASSWORD directamente de config.py en cada request.

Idempotente: se puede correr varias veces con el mismo resultado.
Requiere haber ejecutado antes `python -m backend.migration_v2_0`.
"""
import sys

import config
from backend.auth import hash_password, verify_password
from backend.db import get_db


def main() -> int:
    password = getattr(config, "DM_PASSWORD", "") or ""
    if not password:
        print("ERROR: DM_PASSWORD vacia en config.py")
        return 1

    with get_db() as db:
        user = db.execute(
            "SELECT id FROM users WHERE username='dm'"
        ).fetchone()
        if user is None:
            print("ERROR: no existe el user 'dm'. "
                  "Ejecuta primero: python -m backend.migration_v2_0")
            return 1
        db.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(password), user["id"]),
        )

    # Verificar releyendo (la conexion ya hizo commit al salir del with).
    with get_db() as db:
        row = db.execute(
            "SELECT password_hash FROM users WHERE username='dm'"
        ).fetchone()
    if row is None or not row["password_hash"] \
            or not verify_password(password, row["password_hash"]):
        print("ERROR: la actualizacion no se aplico")
        return 1

    print("OK: password del user 'dm' actualizada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
