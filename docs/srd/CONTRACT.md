# CONTRACT.md — Schema SQLite (Fase 2.2), endpoints REST y límites de scope

**Proyecto:** DnD_tools · Fase 2.2 (y previsiones para 2.3 / 2.5)
**Objetivo:** definir el contrato **técnico** entre el importador SRD y el backend. Este doc es el que lee el programador cuando va a escribir la migración y los endpoints.

**Fuentes:** `INVENTORY.md` (qué se importa), `SHAPES.md` (estructura), `SCHEMAS.md` (drift), `MAPPING.md` (consumo), `RECOMMENDATIONS.md` (orden y tamaño).
**Baseline:** `PRIOR_REPORT_v2.md §3` (schema SQLite) y `§4` (endpoints) — se referencian, no se repiten. Las contradicciones con v2 se marcan `[CONTRADICE v2]`.

## 0. Notación

- `[CONTRADICE v2]` — el schema o endpoint propuesto aquí difiere del de `PRIOR_REPORT_v2.md`. Motivo anotado.
- `[CONTRADICE checkpoint 2]` — decisión de Checkpoint 2 que este doc revisa.
- `data TEXT` — JSON serializado del registro original `es/` (fuente de auditoría).
- `index_slug` — el campo `index` del JSON SRD. **Siempre** es la FK lógica. **Nunca** se usa `url` para FK (`SHAPES §13`).

---

## 1. Schema SQLite — Fase 2.2

Solo las colecciones que se importan en Fase 2.2 (`RECOMMENDATIONS §1.1`):
- `monsters` (entidad)
- `conditions` (referencia)
- `damage-types` (referencia)

Tablas transversales: `collections`, `import_meta`, `reference_entries`.

### 1.1 `collections` y `import_meta`

Idénticas a `PRIOR_REPORT_v2.md §3`. Se reproducen aquí para que el bloque SQL sea autocontenido.

```sql
CREATE TABLE IF NOT EXISTS collections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'srd-2014-es',
    imported_at   TEXT NOT NULL,
    record_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS import_meta (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_slug TEXT NOT NULL,
    source_path     TEXT NOT NULL,
    source_locale   TEXT NOT NULL DEFAULT 'es',
    file_hash       TEXT,
    imported_at     TEXT NOT NULL,
    record_count    INTEGER NOT NULL,
    errors_json     TEXT
);
CREATE INDEX IF NOT EXISTS idx_import_meta_coll ON import_meta(collection_slug, imported_at);
```

**`errors_json`:** se puebla con `NULL` si la importación de esa colección fue limpia; si no, con un JSON de la forma:

```json
{
  "warnings": ["..."],
  "errors": [{"index": "goblin", "reason": "..."}],
  "stats": {"total": 334, "ok": 334, "with_warnings": 1}
}
```

### 1.2 `monsters` — schema real

**`[CONTRADICE v2]`** — v2 proponía `armor_class_type TEXT` sin más. Aquí se añaden **columnas nuevas** justificadas por el sondeo:

| Columna nueva | Motivo | Evidencia |
|---------------|--------|-----------|
| `armor_class_type` | v2 ya la tenía; se mantiene. | `SHAPES §11.2` |
| `armor_class` | `armor_class[0].value`, no la CA condicional. | `monsters[ankheg]` |
| `damage_immunities_json` | `[str]` no cabe en columna; se guarda como JSON. | `SHAPES §11` |
| `condition_immunities_json` | `[ref(conditions)]` no cabe en columna; JSON de slugs. | `SHAPES §11` |
| `special_abilities_json` | `SpecialAbilitySchema[]`; no se normaliza. | `SHAPES §11.3` |
| `actions_json` | `MonsterActionSchema[]`; no se normaliza en Fase 2.2. | `SHAPES §11.1` |
| `legendary_actions_json` | idem. | `SHAPES §11` |
| `reactions_json` | idem. | `SHAPES §11` |

**`[CONTRADICE checkpoint 2 §4]`:** en Checkpoint 2 anoté que `armor_class` y `armor_class_type` iban a columnas. Correcto. Pero también anoté `actions_json` como "no necesaria en 2.2". **Falso:** la feature de bestiario (`MAPPING §7`) muestra `actions[]` en el `<details>`. Se eleva a columna JSON obligatoria en 2.2.

```sql
CREATE TABLE IF NOT EXISTS monsters (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id          INTEGER NOT NULL REFERENCES collections(id),
    index_slug             TEXT NOT NULL UNIQUE,
    name                   TEXT NOT NULL,
    size                   TEXT,
    type                   TEXT,
    subtype                TEXT,
    alignment              TEXT,
    hit_points             INTEGER NOT NULL,
    hit_dice               TEXT,
    hit_points_roll        TEXT,
    armor_class            INTEGER,
    armor_class_type       TEXT,
    challenge_rating       REAL NOT NULL,
    xp                     INTEGER NOT NULL,
    strength               INTEGER,
    dexterity              INTEGER,
    constitution           INTEGER,
    intelligence           INTEGER,
    wisdom                 INTEGER,
    charisma               INTEGER,
    proficiency_bonus      INTEGER,
    damage_immunities_json     TEXT,
    damage_resistances_json    TEXT,
    damage_vulnerabilities_json TEXT,
    condition_immunities_json  TEXT,
    special_abilities_json     TEXT,
    actions_json               TEXT,
    legendary_actions_json     TEXT,
    reactions_json             TEXT,
    data                   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monsters_cr   ON monsters(challenge_rating);
CREATE INDEX IF NOT EXISTS idx_monsters_type ON monsters(type);
CREATE INDEX IF NOT EXISTS idx_monsters_size ON monsters(size);
CREATE INDEX IF NOT EXISTS idx_monsters_name ON monsters(name COLLATE NOCASE);
```

**Columnas NO añadidas (justificación):**
- `senses_*`, `speed_*`: van en `data`; no se filtran ni se muestran por columna en Fase 2.2.
- `languages`: string libre; `data`.
- `image`: `data`; no se cachea fichero.
- `forms`: `data`; ref a `monsters` (no se resuelve).

### 1.3 `reference_entries` — para `conditions` y `damage-types`

Idéntica a `PRIOR_REPORT_v2.md §3`. Se reproduce para autocontención.

```sql
CREATE TABLE IF NOT EXISTS reference_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    index_slug    TEXT NOT NULL,
    name          TEXT NOT NULL,
    data          TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ref_coll_slug ON reference_entries(collection_id, index_slug);
CREATE INDEX IF NOT EXISTS idx_ref_coll ON reference_entries(collection_id);
```

**Por qué `conditions` y `damage-types` NO tienen tabla propia:** son `{index, name, desc[], url}`. No se filtran ni se consultan por campo, solo se **resuelven refs**. `reference_entries` es suficiente.

### 1.4 Lo que NO se crea en Fase 2.2

**`[CONTRADICE v2]`** — v2 §3 listaba `levels`, `spells`, `equipment`, `classes`, `races` como tablas del schema inicial. Aquí **no se crean en 2.2**: no hay datos que las pueblen (`RECOMMENDATIONS §1.1` solo importa 3 colecciones). Se crean en 2.3/2.5. La decisión de v2 de tener el schema completo desde el principio es prematura.

---

## 2. Endpoints REST

**Regla común a todos:**
- No mutan estado del SRD (`/api/srd/*` es read-only).
- No requieren token.
- No tocan `sessions`/`combatants`.
- Devuelven JSON con `items` o el objeto directo. Errores: `{error: str, code: str}`.
- `index_slug` se usa como identificador; los `url` **nunca** se exponen al frontend.

### 2.1 Endpoints de Fase 2.2 (obligatorios)

#### `GET /api/srd/monsters`

- **Query params:**
  - `q` (str, opcional) — búsqueda por `name` (LIKE, case-insensitive).
  - `cr_min` (float, opcional) — `challenge_rating >= cr_min`.
  - `cr_max` (float, opcional) — `challenge_rating <= cr_max`.
  - `type` (str, opcional) — `type = ?` (valor traducido, tal cual; ver D7).
  - `size` (str, opcional) — `size = ?` (valor traducido).
  - `limit` (int, default 50, max 200).
  - `offset` (int, default 0).
- **Response 200:**

```json
{
  "items": [
    {
      "index": "goblin",
      "name": "Goblin",
      "hit_points": 7,
      "armor_class": 15,
      "challenge_rating": 0.25,
      "type": "humanoides",
      "size": "Pequeño",
      "xp": 50
    }
  ],
  "total": 334,
  "limit": 50,
  "offset": 0
}
```

- **Errores:** `400 INVALID_QUERY` (parámetro mal formado), `500 INTERNAL`.

#### `GET /api/srd/monsters/{index}`

- **Path params:** `index` (str, obligatorio).
- **Response 200:** objeto `monsters.data` completo (JSON parseado).
- **Errores:** `404 MONSTER_NOT_FOUND`, `500 INTERNAL`.

#### `GET /api/srd/refs/{collection}`

- **Path params:** `collection` ∈ `{"conditions", "damage-types"}` (Fase 2.2). En 2.3/2.5 se ampliará a `ability-scores`, `skills`, `weapon-properties`, `equipment-categories`, `proficiencies`, `magic-schools`.
- **Response 200:**

```json
{
  "collection": "conditions",
  "items": [
    { "index": "blinded", "name": "Cegado" },
    { "index": "charmed", "name": "Hechizado" }
  ]
}
```

- **Errores:** `404 COLLECTION_NOT_FOUND`, `500 INTERNAL`.

#### `POST /api/combatants` (extendido)

- **Contrato actual (Fase 1):** `{name, hp_max, initiative, kind}`.
- **Extensión Fase 2.2:** añadir `srd_index` (str, opcional).
  - Si `srd_index` presente: el backend lee `monsters` y rellena `hp_max`/`name` si el cliente no los envía.
  - Si `srd_index` ausente: comportamiento Fase 1 sin cambios.
- **Response 200:** `{ok: true, id: int}`.
- **Errores:** `400 MISSING_FIELDS`, `404 MONSTER_NOT_FOUND` (si `srd_index` no existe).

### 2.2 Endpoints de Fase 2.3 (previstos, no en 2.2)

Documentados aquí para que el programador no los reinvente, pero **no se implementan en 2.2**:

| Método | Path | Colección |
|--------|------|-----------|
| GET | `/api/srd/classes` | `classes` |
| GET | `/api/srd/classes/{index}/levels` | `levels` |
| GET | `/api/srd/equipment` | `equipment` |
| GET | `/api/srd/races` | `races` |
| GET | `/api/srd/skills` | `skills` |

### 2.3 Endpoints de Fase 2.5 (previstos, no en 2.2)

| Método | Path | Colección |
|--------|------|-----------|
| GET | `/api/srd/spells` | `spells` |
| GET | `/api/srd/spells/{index}` | `spells` |

### 2.4 Códigos de error unificados

| Código | HTTP | Significado |
|--------|------|-------------|
| `INVALID_QUERY` | 400 | Query param mal formado (p.ej. `cr_min=abc`). |
| `MISSING_FIELDS` | 400 | Faltan campos obligatorios en el body. |
| `MONSTER_NOT_FOUND` | 404 | `index` no existe en `monsters`. |
| `COLLECTION_NOT_FOUND` | 404 | `collection` no está en `reference_entries`. |
| `INTERNAL` | 500 | Error no controlado. |

---

## 3. Queries SQL de ejemplo

Las 4 queries del prompt. Las de armas/slots/habilidades son **Fase 2.3/2.5** (previstas); las de monstruos son **Fase 2.2** (implementadas).

### 3.1 Buscar arma por tipo (Fase 2.3)

```sql
-- Armas marciales cuerpo a cuerpo con daño 1d8 o superior.
-- Nota: 'Marcial' y 'Cuerpo a cuerpo' son valores de es/ (traducidos).
SELECT index_slug, name, damage_dice, damage_type_slug, cost_quantity, cost_unit
FROM equipment
WHERE weapon_category = 'Marcial'
  AND weapon_range = 'Cuerpo a cuerpo'
  AND damage_dice IN ('1d8','1d10','1d12','2d6')
ORDER BY name;
```

**Nota:** `weapon_category` es columna real (`equipment`). El valor `'Marcial'` es el del `es/` — no normalizar a `'Martial'`.

### 3.2 Lista de armas simples (Fase 2.3)

```sql
SELECT index_slug, name, damage_dice, damage_type_slug
FROM equipment
WHERE weapon_category = 'Simple'
ORDER BY name;
```

**Nota:** `weapon_category` toma `'Simple'` o `'Marcial'` en `es/`. No se normaliza.

### 3.3 Slots de conjuro del nivel 5 (Fase 2.5)

```sql
-- Slots del mago a nivel 5 (clase lanzadora con spellcasting en ese nivel).
SELECT level,
       json_extract(data, '$.spellcasting.spell_slots_level_1') AS slots_lvl1,
       json_extract(data, '$.spellcasting.spell_slots_level_2') AS slots_lvl2,
       json_extract(data, '$.spellcasting.spell_slots_level_3') AS slots_lvl3
FROM levels
WHERE class_slug = 'wizard' AND level = 5;
-- esperado: 5|4|3|2
```

**`[D1]`:** si `class_slug = 'fighter'`, la query devuelve `NULL` en las 3 columnas (no `0`). La UI debe distinguir.

### 3.4 Todas las habilidades de Fuerza (Fase 2.3)

```sql
SELECT s.index_slug, s.name
FROM reference_entries s
JOIN collections c ON c.id = s.collection_id
WHERE c.slug = 'skills'
  AND json_extract(s.data, '$.ability_score.index') = 'str'
ORDER BY s.name;
-- esperado: Atletismo
```

### 3.5 Búsqueda de monstruos por CR y tipo (Fase 2.2, implementada)

```sql
SELECT index_slug, name, hit_points, armor_class, challenge_rating
FROM monsters
WHERE challenge_rating BETWEEN 1 AND 3
  AND type = 'humanoides'
ORDER BY challenge_rating, name;
```

### 3.6 Monstruos con múltiples `damage[]` en su primera acción (verificación D4)

```sql
SELECT index_slug, name,
       json_array_length(json_extract(actions_json, '$[0].damage')) AS n_damage
FROM monsters
WHERE json_array_length(json_extract(actions_json, '$[0].damage')) > 1
ORDER BY n_damage DESC;
-- esperado: >0 filas (aboleth.Tentáculo, ankheg.Mordisco, etc.)
```

---

## 4. Normalización obligatoria en el importador

Esta sección es **contrato**: el importador que no aplique estas normalizaciones falla. Se derivan de `SCHEMAS.md §4` y `RECOMMENDATIONS.md §5`.

### 4.1 `option_type: 'daño'` → `'damage'` (D5)

Afecta a `monsters.actions[].damage[].from.options[]`. Se aplica **antes** de la validación Zod. Si aparece un valor no mapeado, se registra en `import_meta.errors_json` y el registro se **omite** de `actions_json` (no se aborta el lote).

### 4.2 `success_type: 'mitad'` → `'half'` (D11)

Afecta a `monsters.actions[].dc.success_type`, `.attacks[].dc.success_type`, `.legendary_actions[].dc.success_type`, `.reactions[].dc.success_type`, `.special_abilities[].dc.success_type`. Tabla de mapeo obligatoria:

| `es/` | `en` (Zod) |
|-------|-----------|
| `'ninguno'` | `'none'` |
| `'mitad'` | `'half'` |
| `'otro'` | `'other'` |

Si aparece un valor no mapeado: warning en `errors_json`, `success_type` se **omite** del JSON normalizado.

### 4.3 `cost.unit: 'po'/'pe'/'pc'` → `'gp'/'sp'/'cp'` (Fase 2.3)

Afecta a `equipment.cost.unit`. Se guarda en `cost_unit` normalizado; el original en `cost_unit_raw`. Fase 2.3, no 2.2.

### 4.4 FK por `index`, no por `url` (D-URL)

El importador **no debe** parsear `APIReference.url` para extraer la colección destino. Debe usar el `index` del `APIReference` y validar que exista en la colección destino (o registrar warning). Esto ya está en `SHAPES §13`.

### 4.5 `import_meta.errors_json` — estructura

Obligatoria para que la fase 2.2 pueda avanzar a 2.3 (criterio de salida de `RECOMMENDATIONS §1.1`).

{
  "stats": {"total": 334, "ok": 334, "with_warnings": 1},
  "warnings": [
    "eldritch-blast.damage_at_character_level no escala (1d10 en las 4 claves)"
  ],
  "errors": [],
  "normalizations_applied": ["D5: option_type 'daño'→'damage'", "D11: success_type 'mitad'→'half'"]
}

**Si `errors` no está vacío, la fase NO avanza.** El programador debe revisar y corregir el importador antes de la siguiente fase.

---

## 5. Contradicciones con v2 y con Checkpoint 2

### 5.1 `[CONTRADICE v2 §3]` — el schema de v2 incluía tablas de 2.3/2.5 desde el principio

v2 §3 proponía crear `levels`, `spells`, `equipment`, `classes`, `races` en la migración inicial. Este doc **solo crea las tablas de 2.2** (más las transversales). Las demás se crean en su fase. Motivo: no tiene sentido crear tablas vacías que no se van a poblar hasta 2.3/2.5; además, si el schema de 2.3 evoluciona (p.ej. cambia el tipo de una columna de `equipment` al ver D5/D11), se evita una migración sobre tablas ya creadas.

### 5.2 `[CONTRADICE v2 §4]` — el contrato de `POST /api/combatants` no cambia

v2 §4 proponía **extender** `POST /api/combatants` con `srd_index`. Este doc lo confirma: es una extensión **no breaking** (`srd_index` opcional), no cambia el contrato existente. No hay contradicción real, solo la reafirmo.

### 5.3 `[CONTRADICE checkpoint 2 §4]` — `actions_json` es obligatoria en 2.2

En Checkpoint 2 anoté `actions_json` como "no necesaria en 2.2". Al redactar `MAPPING §7` y este doc, se confirma que el `<details>` del bestiario necesita `actions[]`. Se eleva a columna JSON obligatoria. **No se reescribe Checkpoint 2; queda registrado aquí.**

### 5.4 `[CONTRADICE v2 §3]` — `armor_class_type` como enum

v2 §3 proponía `armor_class_type` como `TEXT` (sin enum). Este doc lo mantiene como `TEXT` pero documenta los 5 valores (`natural`, `dex`, `armor`, `spell`, `condition`). No se usa `CHECK constraint` porque el importador no normaliza el valor; se guarda tal cual viene de `es/` y se usa solo para display. Si el frontend necesita el enum cerrado, se añade en 2.3.

### 5.5 Sin contradicción con `D6`

`D6` (eldritch-blast no escala) no es 2.2; es 2.5. No se documenta en este schema. Se recuerda en §4.5 para que el importador de 2.5 lo registre en `import_meta.errors_json`.

---

## 6. Lo que el proyecto NO va a hacer con el SRD (anti-scope-creep)

Esta sección es **vinculante**. Cualquier PR que añada funcionalidad fuera de esta lista se rechaza, salvo que se abra una fase nueva.

### 6.1 No motor de reglas

- No se valida que un conjuro sea lanzable (componentes, nivel, espacio).
- No se valida que un ataque sea legal (rango, línea de visión, cobertura).
- No se aplican automáticamente resistencias/vulnerabilidades/inmunidades.
- No se valida el peso del inventario ni la capacidad de carga.
- No se simula la iniciativa en tiempo real (solo se tira una vez al iniciar combate).

**Por qué:** el DM es el árbitro; el MVP es una herramienta, no un simulador. Implementar el motor de reglas es una fase aparte que no está en 2.x.

### 6.2 No validación de conjuros

- No se comprueba que el jugador tenga el conjuro preparado (Fase 2.5 solo consume slots, no prepara).

**Por qué:** la preparación de conjuros es opcional en el MVP y el DM la gestiona fuera de la herramienta.

### 6.3 No simulación de combate

- El backend **no decide** las acciones de los monstruos. El DM las introduce manualmente.
- El backend **no tira** iniciativa por los monstruos; el DM lo hace o se calcula con `dexterity` pero el DM confirma.

**Por qué:** el objetivo es asistir, no automatizar. Un motor de IA de monstruos es un proyecto en sí.

### 6.4 No persistencia de `data` en el cliente

- El frontend **no** guarda `monsters.data` localmente. Siempre consulta `/api/srd/monsters/{index}`.
- Si el DM quiere un monstruo custom, se crea un combatiente normal (sin `srd_index`); no se modifica el SRD.

### 6.5 No cache HTTP con expiración

- Los endpoints `/api/srd/*` no usan `ETag` ni `Cache-Control: max-age` en Fase 2.2. Se puede añadir en una fase posterior.

**Por qué:** el SRD es inmutable (mismo hash de fichero), pero la cache añade complejidad no justificada para 2.2.

### 6.6 No i18n

- No se traduce ni se normaliza `name` de `monsters`, `spells`, etc. Se muestra lo que viene en `es/`.
- No se mezcla con `en/` en runtime (el `en/` es solo auditoría, ver `PRIOR_REPORT_v2.md §1`).

---

## 7. Checklist de implementación de Fase 2.2

Para que el programador sepa cuándo ha terminado:

- [ ] Migración SQL creada (solo tablas de §1).
- [ ] Importador de `conditions` funciona; `reference_entries` tiene 15 filas.
- [ ] Importador de `damage-types` funciona; `reference_entries` tiene 13 filas.
- [ ] Importador de `monsters` funciona; `monsters` tiene 334 filas.
- [ ] `import_meta` tiene 3 filas (una por colección) con `errors_json = NULL` o con `errors` vacío.
- [ ] `GET /api/srd/monsters` responde con paginación y filtros.
- [ ] `GET /api/srd/monsters/goblin` devuelve el JSON completo.
- [ ] `GET /api/srd/refs/conditions` devuelve 15 items.
- [ ] `POST /api/combatants` con `srd_index="goblin"` crea un combatiente con `hp_max=7`.
- [ ] Las 4 queries de §3.5–3.6 pasan.
- [ ] `errors_json` de `monsters` incluye el warning de D5/D11 si se aplicaron normalizaciones.

**Criterio de "Fase 2.2 terminada":** los 11 ítems marcados.

---

## 8. Decisiones (una línea de justificación cada una)

- **Solo tablas de 2.2 en la migración** — crear tablas de 2.3/2.5 vacías no aporta y arriesga migraciones innecesarias.
- **`actions_json` como columna JSON en 2.2** — la feature de bestiario la necesita en el `<details>`; `[CONTRADICE checkpoint 2]` registrada.
- **`armor_class` y `armor_class_type` como columnas reales** — son filtro/display de la datalist; no van solo en `data`.
- **`condition_immunities_json` y `damage_*_json` como columnas JSON** — son arrays; no caben en columnas escalares.
- **`reference_entries` para `conditions` y `damage-types`** — son referencias planas; no merecen tabla propia.
- **`POST /api/combatants` extendido con `srd_index` opcional** — no rompe Fase 1; el cliente actual sigue funcionando sin el campo.
- **Endpoints de 2.3/2.5 documentados pero no implementados** — el programador ve el horizonte sin implementarlo antes de tiempo.
- **Normalización D5/D11 en importador, no en `.ts`** — los `.ts` son autoritativos del repo `5e-bits`; la normalización es responsabilidad del importador.
- **`errors_json` obligatorio para avanzar de fase** — sin este gate, un drift no detectado se propaga a 2.3/2.5.
- **Anti-scope-creep §6 vinculante** — cualquier PR que implemente motor de reglas, simulación o i18n se rechaza; evita que el proyecto se desborde.
- **Checklist de 11 ítems §7** — da un criterio objetivo de "Fase 2.2 terminada".

---

## 9. Estado de implementación (Fase 2.1.2-B-2)

Con la ejecución de la Fase 2.1.2-B-2 (Reconciliación del SRD), se han completado las siguientes integraciones y ajustes sobre `data/srd.db` y `backend/app.py`:

1. **Columnas JSON en `monsters`:**
   - Columna `collection_id` añadida y vinculada con `collections(id)` para los 334 monstruos (0 nulos).
   - Añadidas y pobladas las 8 columnas JSON: `damage_immunities_json`, `damage_resistances_json`, `damage_vulnerabilities_json`, `condition_immunities_json`, `special_abilities_json`, `actions_json`, `legendary_actions_json` y `reactions_json` mediante `json_extract(data, '$.campo')`.
   - Se mantiene la columna original `data` íntegra.

2. **Colecciones de referencia en SQLite:**
   - Tabla `reference_entries` creada e indexada con las colecciones `conditions` (15 registros) y `damage-types` (13 registros).

3. **Importadores y verificadores:**
   - `scripts/import_srd.py` actualizado para poblar de forma automática `collection_id` y las 8 columnas JSON en futuras ejecuciones.
   - `scripts/verify_srd.py` ampliado con validaciones automáticas de `collection_id` (sin nulos ni huérfanas) y comprobación de integridad y no vacuidad de las columnas JSON (12/12 verificaciones OK).

4. **Endpoints REST:**
   - `GET /api/srd/monsters`: soporta paginación con `offset` (default 0) y `limit`, retornando el objeto con `{ items, total, limit, offset }`.
   - `GET /api/srd/refs/{collection}`: implementado y operativo para `conditions` y `damage-types` (retorna lista de `{index, name}`, 404 para otras colecciones).

