"""Script interactivo para fijar la contrasena del user 'dm' en la DB.

Uso:
    python -m backend.set_dm_password

Pide la password por stdin con getpass (no se muestra en pantalla),
valida longitud minima 6, y hace upsert del hash scrypt en la tabla
users. NO toca config.py ni variables de entorno: solo la DB.

Este script es la alternativa a la variable de entorno DND_DM_PASSWORD
para fijar la password del DM. Si ya existe un user 'dm' con hash
incoherente (p. ej. quedo de un DM_PASSWORD anterior hardcodeado),
este script lo repara sin tocar el resto de usuarios.
"""
import datetime
import getpass
import sys

from backend.auth import hash_password
from backend.db import get_db, init_db


MIN_LEN = 6


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def set_password(password: str) -> str:
    """Hace upsert del hash. Devuelve 'updated' o 'created'."""
    pw_hash = hash_password(password)
    with get_db() as db:
        row = db.execute("SELECT id FROM users WHERE username='dm'").fetchone()
        if row is not None:
            db.execute(
                "UPDATE users SET password_hash=?, is_guest=0 WHERE id=?",
                (pw_hash, row["id"]),
            )
            return "updated"
        db.execute(
            "INSERT INTO users (username, display_name, password_hash, is_guest, created_at) "
            "VALUES ('dm', 'DM', ?, 0, ?)",
            (pw_hash, _now()),
        )
        return "created"


def _read_password(prompt: str) -> str:
    """Lee password de forma que funcione interactivo Y con pipe.

    - stdin es TTY (ejecucion manual)  -> getpass, no muestra en pantalla.
    - stdin es pipe (echo | python -m) -> readline del pipe.

    getpass.getpass() en Linux prioriza /dev/tty sobre stdin, lo que
    rompe la automatizacion: `echo 'x' | python -m set_dm_password`
    se queda colgado en /dev/tty aunque stdin sea un pipe.
    """
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    line = sys.stdin.readline()
    if not line:
        raise EOFError("stdin cerrado sin password")
    return line.rstrip("\n")


def main() -> int:
    init_db()
    try:
        pw = _read_password("Nueva contrasena del user dm: ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.", file=sys.stderr)
        return 1
    if len(pw) < MIN_LEN:
        print(f"ERROR: password demasiado corta (min {MIN_LEN}).", file=sys.stderr)
        return 2
    status = set_password(pw)
    print(f"OK: password del user dm actualizada ({status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
