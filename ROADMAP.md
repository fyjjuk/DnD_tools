# Hoja de Ruta (ROADMAP) — DnD MVP LAN

Documento maestro del estado de desarrollo, fases completadas, fase activa y fases futuras del sistema de combate y campaña para D&D 5e en red local.

---

## 🗺️ Estado General de las Fases

| Fase | Título | Estado | Descripción / Hitos |
| :--- | :--- | :---: | :--- |
| **Fase 1** | **MVP Combate LAN** | ✅ Completada | Tracker de HP, orden de iniciativa manual, WebSocket en LAN, soporte inicial de monstruos SRD, logs de sesión. |
| **Fase 2.1** | **Cuentas y Campañas** | ✅ Completada | Autenticación ligera, campañas, miembros con roles (DM / Jugador), invitaciones por código, auto-reconexión. |
| **Fase 2.1.2-B-1** | **Aislamiento de DBs** | ✅ Completada | División en tres SQLite independientes: `dnd.db` (usuarios/sesiones), `srd.db` (compendio oficial) y `homebrew.db` (contenido propio). Modo WAL. |
| **Fase 2.1.2-B-2** | **Reconciliación SRD 5e** | ✅ Completada | Normalización de JSONs del SRD en español, migración reproducible, catalogación de discrepancias (I6-I13). |
| **Fase 2.2** | **Compendio SRD Completo** | ✅ Completada | Importación de monstruos, conjuros, equipo, clases, razas, niveles y tablas de referencia (`reference_entries`). |
| **Fase 2.3** | **Mini-ficha de Personaje** | ✅ Completada | Modelo híbrido en `characters`, auto-cálculos de modificadores, CA, HP max, CD de conjuros, asignación de PJs a combate. |
| **Fase 2.4.1** | **Iniciativa Interactiva y Superusuario** | ✅ Completada | Solicitud masiva de iniciativa (`initiative_requests`), tiradas de jugador en tiempo real, auto-tirada de NPCs, forzar/saltar/cancelar por DM y Superusuario, edición de fichas por DM. |
| **Fase 2.4.2** | **Tiradas de Habilidad / Checks** | ✅ Completada | Solicitudes de tiradas de habilidad/característica por el DM con CD (Clase de Dificultad), 1d20 + modificador + competencia, soporte de Ventaja/Desventaja y Tiradas Secretas, resolución automática Éxito/Fallo. |
| **Fase L1** | **Auditoría y Limpieza del Bridge Legacy** | ✅ Completada | Reconciliación total de datos Fase 1 a Fase 2 (espejo en `user_sessions`, sincronización `combatants.user_id`), desacoplamiento del hack `dm_token` en nuevas sesiones de campaña, autenticación dual por `X-User-Token` con fallback retrocompatible, script de auditoría idempotente `scripts/audit_legacy_bridge.py`. |
| **Fase 2.4.3** | **Tiradas de Salvación y Combate Avanzado** | 🟡 **SIGUIENTE** | Solicitud de tiros de salvación (Saving Throws) grupales/individuales con CD, resistencia a conjuros y daño directo asociado. |
| **Fase 2.5** | **Gestión de Conjuros y Spell Slots** | ⏳ Pendiente | Tracking de espacios de conjuro por nivel, lanzamiento en combate, consumo de slots y resolución de daño/efecto (atiende deuda técnica I6). |
| **Fase 2.6** | **Homebrew y Personalización** | ⏳ Pendiente | Edición y creación de monstruos, armas y objetos mágicos propios persistidos en `homebrew.db`. |

---

## 📌 Deuda Técnica y Estado de Reconciliación (según `docs/DEUDA_TECNICA.md`)

Las siguientes incidencias conocidas (*drifts*) están catalogadas y vinculadas a fases específicas:

| ID | Incidencia | Fase de Resolución | Estado Actual |
| :--- | :--- | :---: | :--- |
| **I6** | Escalado de daño en cantrips (`eldritch-blast` no escala en JSON) | **Fase 2.5** | Registrado; se aplicará parche en el parser de conjuros de combate. |
| **I7** | Plurales y traducción en filtros de monstruos (`type`, `size`) | **Fase 2.2 / 2.3** | Resuelto manteniendo texto en español en columnas indexadas para búsqueda directa. |
| **I8** | Inconsistencia de siglas de atributos (`STR` vs `FUE`) | **Fase 2.3 / 2.4** | Resuelto: se usa `index_slug` canónico (`str`, `dex`, `con`, `int`, `wis`, `cha`) en base de datos y mapeo en UI. |
| **I9** | Idiomas sin traducir en algunas razas (ej. Elfo) | **Fase 2.3** | Mitigado en parser de razas. |
| **I10** | Valores de enums traducidos en ataques y salvaciones (`mitad`, `ninguno`) | **Fase 2.4 / 2.5** | Normalización en tiempo de importación/ejecución (`half`, `none`). |
| **I13** | Prefijos de URL discordantes en `APIReference` (`/api/` vs `/api/2014/`) | **Permanente** | Arquitectura blindada: nunca se usa `url`, todas las claves foráneas resuelven por `index_slug`. |

---

## 🎯 Última Implementación: Fase 2.4.2 (Tiradas de Habilidad / Checks)

Reutiliza la arquitectura reactiva WebSocket probada en la Fase 2.4.1 (`initiative_requests` / `initiative_rolls`):
1. **Petición del DM:** El DM selecciona una habilidad (o característica pura) del SRD, una Clase de Dificultad (CD) y destinatarios (todos los PJs o específicos), con opciones de ventaja/desventaja y tirada secreta.
2. **Respuesta del Jugador:** Modal reactivo con dado animado, suma automática del modificador y bono de competencia.
3. **Resolución Automática:** Cálculo inmediato en backend: `Total = d20 + mod + (prof ? prof_bonus : 0)`. Evaluación de éxito (`Total >= CD`) o fallo (`Total < CD`).
4. **Herramientas DM:** Forzar tirada aleatoria, "Toma 10" (salto rápido) o cancelar la solicitud en cualquier momento.
5. **Verificación:** Suite de 11 tests automatizados en `scripts/verify_phase_2_4_2.py`.
