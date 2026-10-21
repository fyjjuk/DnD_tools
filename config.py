"""Configuracion unica del MVP: puerto y ruta de la base de datos."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Puerto HTTP del servidor
PORT = 8000

# Ruta del archivo SQLite (se crea sola al arrancar)
DB_PATH = os.path.join(BASE_DIR, "data", "dnd.db")

# Rutas de las bases de datos separadas (Fase 2.1.2-B-1)
SRD_DB_PATH = os.path.join(BASE_DIR, "data", "srd.db")
HOMEBREW_DB_PATH = os.path.join(BASE_DIR, "data", "homebrew.db")


# Contrasena de DM.
# DM_PASSWORD: si vacia, /api/dm/bootstrap y /api/auth/login con
# username='dm' fallan con error claro. Configurala con la variable
# de entorno DND_DM_PASSWORD o con el script set_dm_password.py:
#   DND_DM_PASSWORD='tu-clave' python run.py
#   python -m backend.set_dm_password
DM_PASSWORD = os.getenv("DND_DM_PASSWORD", "")


# Directorio con los JSON del SRD 5e (2014) en espanol.
# Lo usa scripts/import_srd.py. Si no existe, el servidor arranca igual
# y el autocompletado del bestiario aparece vacio hasta que importes.
SRD_DIR = "/home/fyjjuk/DnD/raw/srd-2014/es"
