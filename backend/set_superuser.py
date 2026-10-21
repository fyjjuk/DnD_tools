"""Script interactivo/CLI para fijar la contrasena del superusuario 'admin'.

Uso:
    python -m backend.set_superuser
    echo 'secreto123' | python -m backend.set_superuser

Pide la password por stdin (o lee de pipe), valida longitud minima 6,
y hace upsert del hash scrypt en la tabla users con is_superuser=1.
NO toca config.py ni variables de entorno: solo la DB.
"""
import datetime
import getpass
import sys

from backend.auth import hash_password
from backend.db import get_db, init_db


MIN_LEN = 6


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def set_superuser_password(password: str) -> str:
    """Hace upsert del usuario 'admin' con is_superuser=1. Devuelve 'updated' o 'created'."""
    pw_hash = hash_password(password)
    with get_db() as db:
        row = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if row is not None:
            db.execute(
                "UPDATE users SET password_hash=?, is_guest=0, is_superuser=1 WHERE id=?",
                (pw_hash, row["id"]),
            )
            return "updated"
        db.execute(
            "INSERT INTO users (username, display_name, password_hash, is_guest, is_superuser, created_at) "
            "VALUES ('admin', 'Administrador', ?, 0, 1, ?)",
            (pw_hash, _now()),
        )
        return "created"


def _read_password(prompt: str) -> str:
    """Lee password de forma que funcione interactivo Y con pipe.

    - stdin es TTY (ejecucion manual)  -> getpass, no muestra en pantalla.
    - stdin es pipe (echo | python -m) -> readline del pipe.
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
        pw = _read_password("Nueva contrasena del superusuario admin: ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.", file=sys.stderr)
        return 1
    if len(pw) < MIN_LEN:
        print(f"ERROR: password demasiado corta (min {MIN_LEN}).", file=sys.stderr)
        return 2
    status = set_superuser_password(pw)
    print(f"OK: password del superusuario admin actualizada ({status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
