# PRD: Fase 2.1.2-B-1 — Split de DB

> **Propósito**: Separar la base de datos SRD de la de usuario para evitar corrupciones en futuras importaciones.

---

## Tareas

### Step 1: Backup de seguridad
- [x] Copiar data/dnd.db a data/dnd.db.pre-2.1.2-b-1.bak (incluyendo -wal y -shm si existen).
- [x] Verificar que el backup se haya creado correctamente.

### Step 2: Configuración y Helpers
- [x] Añadir SRD_DB_PATH y HOMEBREW_DB_PATH a config.py (NO tocar DB_PATH).
- [x] Añadir get_srd_db(), get_homebrew_db(), SCHEMA_SRD y SCHEMA_HOMEBREW a backend/db.py.
- [x] Verificar que los archivos no tengan errores de sintaxis.

### Step 3: Script de Migración
- [x] Crear backend/migration_2_1_2b_1.py (script idempotente con ATTACH DATABASE).
- [x] Ejecutar python -m backend.migration_2_1_2b_1 por primera vez.
- [x] Ejecutar python -m backend.migration_2_1_2b_1 por segunda vez para verificar idempotencia.

### Step 4: Actualización de Endpoints y Scripts
- [x] Actualizar backend/app.py (cambiar get_db por get_srd_db en 3 sitios específicos).
- [x] Actualizar el --db default en scripts/import_srd.py a config.SRD_DB_PATH.
- [x] Actualizar el --db default en scripts/verify_srd.py a config.SRD_DB_PATH.

### Step 5: Documentación
- [x] Añadir sección "Bases de datos" al README.md explicando las 3 DBs y los backups.

### Step 6: Verificación Final y Commit
- [x] Ejecutar python scripts/verify_srd.py y confirmar que devuelve N/N OK.
- [x] Verificar que dnd.db ya no tiene las tablas monsters, collections, import_meta.
- [x] git add config.py backend/db.py backend/migration_2_1_2b_1.py backend/app.py scripts/import_srd.py scripts/verify_srd.py README.md
- [x] git commit -m "feat(2.1.2-B-1): split DB en srd.db + dnd.db + homebrew.db"

---
## 각 단계별 작업 중 필요하다면 PRD에 내용을 추가하거나 변경해라.
