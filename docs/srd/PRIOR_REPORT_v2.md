# INFORME (v2, con datos reales del sondeo)

**Integración del SRD 5e (2014) en español en el MVP de combate**
**Fecha:** 2026-10-17 · **Fuente:** `reporte.txt` (sondeo en/es 1:1) + `schemas_review.txt` + `common.ts` del repomix 5e-bits
**Sustituye a:** informe v1 del mismo hilo. Los cambios se marcan con `[ACTUALIZADO]` o `[CORREGIDO]`.

> **Hallazgo estructural del sondeo:** `es/` es una **traducción 1:1 completa** de `en/` (25/25 colecciones, claves idénticas, tipos idénticos). No hay merge ni fallback: **`es/` es la única fuente del importador.** `en/` queda como referencia/auditoría. Esto elimina el riesgo bloqueante #0 del v1.

---

## 1. Inventario de colecciones `[ACTUALIZADO con conteos reales]`

Conteos exactos del sondeo (§1 y §20 del `reporte.txt`). Tamaño = `du -h` de `es/`.

| # | Colección | Nº reg. | Tamaño `es/` | Campos clave | Relevancia MVP |
|---|---|---|---|---|---|
| 1 | **Monsters** | **334** | 1,4 MB | `index`, `name`, `hit_points`, `armor_class[]`, `challenge_rating`, `type`, `size`, `strength..charisma`, `xp`, `speed`, `actions[]`, `special_abilities[]`, `legendary_actions[]`, `damage_vulnerabilities/resistances/immunities[]` (string), `condition_immunities[]` (APIReference) | **Alta** (combate) |
| 2 | **Levels** | **290** | 224 KB | `level`, `class`, `prof_bonus`, `spellcasting`, `class_specific`, `subclass_specific`, `features` | **Alta** (ficha) |
| 3 | **Spells** | **319** | 628 KB | `index`, `name`, `level`, `school`, `damage`, `dc`, `attack_type`, `area_of_effect`, `range`, `components`, `duration`, `concentration`, `casting_time` | **Media** (hechizos en combate, fase posterior) |
| 4 | **Equipment** | **237** | 184 KB | `index`, `name`, `equipment_category`, `weapon_category`, `armor_category`, `damage`, `two_handed_damage`, `armor_class`, `properties`, `cost`, `weight`, `str_minimum`, `stealth_disadvantage` | **Media** (ficha) |
| 5 | **Classes** | **12** | 152 KB | `index`, `name`, `hit_die`, `saving_throws`, `proficiencies`, `spellcasting` | **Media** (ficha) |
| 6 | **Races** | **9** | 28 KB | `index`, `name`, `speed`, `ability_bonuses`, `size`, `languages` | **Media** (ficha) |
| 7 | **Conditions** | **15** | 8 KB | `index`, `name`, `desc` | **Media** (referenciado) |
| 8 | **DamageTypes** | **13** | 4 KB | `index`, `name` | **Media** (referenciado) |
| 9 | **MagicSchools** | **8** | 4 KB | `index`, `name` | **Media** (referenciado) |
| 10 | **WeaponProperties** | **11** | 4 KB | `index`, `name`, `desc` | **Media** (referenciado) |
| 11 | **Subraces** | **4** | 4 KB | `race`, `ability_bonuses`, `desc` | Baja |
| 12 | **Features** | **407** | 364 KB | `index`, `name`, `level`, `class`, `subclass`, `desc`, `feature_specific` | Baja (ficha) |
| 13 | **Traits** | **38** | 56 KB | `index`, `name`, `desc`, `races`, `subraces`, `proficiency_choices` | Baja (ficha) |
| 14 | **Proficiencies** | **117** | 48 KB | `index`, `name`, `type`, `reference` | Baja (ficha) |
| 15 | **AbilityScores** | **6** | 8 KB | `index`, `name`, `full_name`, `skills` | Baja |
| 16 | **Skills** | **18** | 12 KB | `index`, `name`, `ability_score` | Baja |
| 17 | **Backgrounds** | **1** | 12 KB | `index`, `name`, `starting_proficiencies`, `starting_equipment` | Baja |
| 18 | **Subclasses** | **12** | 56 KB | `index`, `name`, `class`, `subclass_flavor` | Baja |
| 19 | **Feats** | **1** | 4 KB | `index`, `name`, `prerequisites`, `desc` | Baja |
| 20 | **MagicItems** | **362** | 460 KB | `index`, `name`, `equipment_category`, `rarity`, `variants`, `variant` | Baja (no hay inventario en MVP) |
| 21 | **EquipmentCategories** | **39** | 140 KB | `index`, `name`, `equipment` | Baja |
| 22 | **Alignments** | **9** | 4 KB | `index`, `name`, `abbreviation` | **Ninguna** |
| 23 | **Languages** | **16** | 8 KB | `index`, `name`, `type` | **Ninguna** |
| 24 | **Rules** | **6** | 12 KB | `index`, `name`, `desc`, `subsections` | **Ninguna** |
| 25 | **RuleSections** | **33** | 216 KB | `index`, `name`, `desc` | **Ninguna** |

**Total `es/`:** 2.385 registros, **≈ 4,3 MB** (SQLite con `data TEXT` sin comprimir ≈ 4,5–5 MB; con `PRAGMA page_size=8192` y VACUUM, manejable).

`[CORREGIDO vs v1]`: `Backgrounds` = 1 (no 13), `Traits` = 38 (no 250), `Features` = 407 (no 450), `MagicItems` = 362 (no 200+).

---

## 2. Campos de integración por colección relevante

### 2.1 `Monsters` — ALTA `[ACTUALIZADO con datos reales]`

Pantalla: **`/dm` (`frontend/dm.html`), panel "Nuevo combatiente"**. Endpoint: `POST /api/combatants` (extendido).

| Campo schema | Tipo Zod | Valor real (`es/`) | Uso MVP |
|---|---|---|---|
| `index` | `string` | `"aboleth"` (idéntico a `en/`) | Slug estable; FK lógica. |
| `name` | `string` | `"Aboleth"` (sin traducir en [0]; otros sí) | Poblar `combatants.name`. |
| `hit_points` | `number` | `135` (idéntico a `en/`) | `combatants.hp_max` y `hp_current`. |
| `hit_dice` | `string` | `"18d10"` | Display / reroll. |
| `hit_points_roll` | `string` | `"18d10+36"` | Display. |
| `armor_class` | **array** de `{type,value,armor?,condition?,spell?,desc?}` | `[{type:"natural",value:14},{type:"condition",value:11,condition:{...}}]` | CA nominal = `[0].value`. Tipos observados: `natural`, `dex`, `spell`, `condition`. |
| `challenge_rating` | `number` | `10`, `0.125`, `0.25`, `0.5` (fraccionarios **presentes**) | Filtro; **`REAL`**. |
| `xp` | `number` | `5900` | Display. |
| `type` | `string` | `"aberración"` (traducido) `[ACTUALIZADO]` | Filtro UI. |
| `size` | `string` | `"Grande"` (traducido) | Filtro UI. |
| `strength..charisma` | `number` × 6 | `21,9,15,18,15,18` | Columnas reales. |
| `proficiency_bonus` | `number?` | derivado de CR | Display. |
| `speed` | `object` | `{walk:"10 pies", swim:"40 pies"}` (traducido) | `data` (display). |
| `senses` | `object` | `{darkvision:"120 pies", passive_perception:20}` | `data`. |
| `damage_vulnerabilities/resistances/immunities` | **`string[]`** | `["acid"]` | `data`. |
| `condition_immunities` | **`APIReference[]`** | `[{index:"charmed",...}]` | `data`; FK lógica. |
| `special_abilities[]` | `array<SpecialAbilitySchema>` | — | `data`. |
| `actions[]` | `array<MonsterActionSchema>` | — | `data`. |
| `legendary_actions[]` / `reactions[]` | arrays | — | `data`. |

### 2.2 `Levels` — ALTA (ficha) `[CORREGIDO]`

Pantalla futura: **`/player`, panel "Mi ficha"**. Endpoint: `GET /api/srd/classes/{index}/levels`.

| Campo | Tipo | Uso |
|---|---|---|
| `class.index` | `string` | Filtro. |
| `level` | `number` | Columna real. |
| `prof_bonus` | `number?` | Columna real. |
| `spellcasting` | `LevelSpellcastingSchema?` | **Presente en las 12 clases** (slots 0 en no-lanzadoras). **No hay nulls que manejar.** |
| `class_specific` | `ClassSpecificSchema?` | 33 claves posibles (ver §5.3); va a `data`. |
| `subclass_specific` | `SubclassSpecificSchema?` | `data`. |
| `features[]` | `APIReference[]?` | Enlaces a `Features`. |

### 2.3 `Spells` — MEDIA

Pantalla futura: **`/player`, "Hechizos"**. Endpoint: `GET /api/srd/spells`.

| Campo | Tipo | Uso |
|---|---|---|
| `index`, `name` | `string` | Identidad. |
| `level` | `number` | Columna real; filtro. |
| `school.index` | `string` | Columna `school_slug`. |
| `casting_time`, `range`, `duration` | `string` | Display. |
| `components` | `string[]` | Display (`"V","S","M"`). |
| `concentration`, `ritual` | `boolean` | Columnas `INTEGER 0/1`. |
| `damage.damage_at_slot_level` | `record<string,string>` | Display. |
| `heal_at_slot_level` | `record<string,string>` | Display (`"5","10",...`). |
| `dc` | `{dc_type, dc_success, desc?}` | Display. **`dc_success`** (no `success_type`). |
| `area_of_effect` | `{type, size}` | Display. |
| `attack_type` | `string?` | Display. |
| `classes[]`, `subclasses[]` | `APIReference[]` | Filtro por clase. |

### 2.4 `Equipment` — MEDIA

Pantalla futura: **`/player`, "Inventario"**. Endpoint: `GET /api/srd/equipment`.

| Campo | Tipo | Uso |
|---|---|---|
| `index`, `name` | `string` | Identidad. |
| `equipment_category.index` | `string` | Columna `equipment_category_slug`. |
| `weapon_category` / `armor_category` | `string?` | Columnas; filtro. |
| `cost.quantity` / `cost.unit` | `number` / `string` | **`cost.unit` viene `pc/pe/po` en `es/`** → mapear a `cp/sp/gp` en importador (o guardar ambos). |
| `weight` | `number?` | Columna. |
| `damage.damage_dice` / `damage.damage_type.index` | `string` / `string` | Columnas `damage_dice` / `damage_type_slug`. |
| `two_handed_damage` | `DamageSchema?` | `data`. |
| `armor_class.base` / `dex_bonus` / `max_bonus` | `number` / `bool` / `number?` | Columnas `armor_class_*`. |
| `str_minimum` / `stealth_disadvantage` | `number?` / `bool?` | Display. |
| `properties[]` | `APIReference[]` | Display. |

### 2.5 `Classes` — MEDIA

`hit_die`, `spellcasting.spellcasting_ability.index` → columna `spellcasting_ability_slug`. Resto `data`.

### 2.6 `Races` — MEDIA

`speed`, `size`, `ability_bonuses[]` → columnas y display.

### 2.7 Referencias (`Conditions`, `DamageTypes`, `MagicSchools`, `WeaponProperties`)

**Media.** Solo `index_slug` + `name` + `data` en `reference_entries` para resolver `APIReference`.

---

## 3. Schema SQLite propuesto `[CORREGIDO con tipos reales]`

Se mantiene el modelo híbrido. Cambios respecto a v1 marcados con `⟵`.

```sql
-- ============================================================
-- Metadatos
-- ============================================================
CREATE TABLE IF NOT EXISTS collections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT NOT NULL UNIQUE,       -- 'monsters', 'spells', ...
    name          TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'srd-2014-es',
    imported_at   TEXT NOT NULL,
    record_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS import_meta (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_slug TEXT NOT NULL,
    source_path     TEXT NOT NULL,            -- 'srd-2014/es/5e-SRD-Monsters.json'
    source_locale   TEXT NOT NULL DEFAULT 'es',
    file_hash       TEXT,                     -- sha256
    imported_at     TEXT NOT NULL,
    record_count    INTEGER NOT NULL,
    errors_json     TEXT                      -- NULL si OK
);
CREATE INDEX IF NOT EXISTS idx_import_meta_coll ON import_meta(collection_slug, imported_at);

-- ============================================================
-- Monsters
-- ============================================================
CREATE TABLE IF NOT EXISTS monsters (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id      INTEGER NOT NULL REFERENCES collections(id),
    index_slug         TEXT NOT NULL UNIQUE,
    name               TEXT NOT NULL,
    size               TEXT,                  -- valor de es/ ("Grande") ⟵ display
    type               TEXT,                  -- valor de es/ ("aberración") ⟵ display
    subtype            TEXT,                  -- puede ser NULL
    alignment          TEXT,
    hit_points         INTEGER NOT NULL,
    hit_dice           TEXT,
    hit_points_roll    TEXT,
    armor_class        INTEGER,               -- armor_class[0].value
    armor_class_type   TEXT,                  -- ⟵ armor_class[0].type ("natural","dex","spell","condition")
    challenge_rating   REAL NOT NULL,         -- fraccionarios 0.125/0.25/0.5
    xp                 INTEGER NOT NULL,
    strength           INTEGER,
    dexterity          INTEGER,
    constitution       INTEGER,
    intelligence       INTEGER,
    wisdom             INTEGER,
    charisma           INTEGER,
    proficiency_bonus  INTEGER,               -- puede ser NULL
    data               TEXT NOT NULL          -- JSON completo de es/
);
CREATE INDEX IF NOT EXISTS idx_monsters_cr     ON monsters(challenge_rating);
CREATE INDEX IF NOT EXISTS idx_monsters_type   ON monsters(type);
CREATE INDEX IF NOT EXISTS idx_monsters_size   ON monsters(size);
CREATE INDEX IF NOT EXISTS idx_monsters_name   ON monsters(name COLLATE NOCASE);

-- ============================================================
-- Levels
-- ============================================================
CREATE TABLE IF NOT EXISTS levels (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    index_slug    TEXT NOT NULL UNIQUE,       -- 'barbarian-1'
    class_slug    TEXT NOT NULL,
    level         INTEGER NOT NULL,
    prof_bonus    INTEGER,
    data          TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_levels_class_level ON levels(class_slug, level);

-- ============================================================
-- Spells
-- ============================================================
CREATE TABLE IF NOT EXISTS spells (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id    INTEGER NOT NULL REFERENCES collections(id),
    index_slug       TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    level            INTEGER NOT NULL,
    school_slug      TEXT,
    casting_time     TEXT,
    range            TEXT,
    duration         TEXT,
    concentration    INTEGER NOT NULL DEFAULT 0,
    ritual           INTEGER NOT NULL DEFAULT 0,
    components       TEXT,                    -- "V,S,M"
    attack_type      TEXT,
    data             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spells_level  ON spells(level);
CREATE INDEX IF NOT EXISTS idx_spells_school ON spells(school_slug);
CREATE INDEX IF NOT EXISTS idx_spells_name   ON spells(name COLLATE NOCASE);

-- ============================================================
-- Equipment
-- ============================================================
CREATE TABLE IF NOT EXISTS equipment (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id            INTEGER NOT NULL REFERENCES collections(id),
    index_slug               TEXT NOT NULL UNIQUE,
    name                     TEXT NOT NULL,
    equipment_category_slug  TEXT,
    weapon_category          TEXT,
    armor_category           TEXT,
    cost_quantity            REAL,
    cost_unit                TEXT,            -- ⟵ normalizado a 'cp','sp','gp' en importador
    cost_unit_raw            TEXT,            -- ⟵ valor original de es/ ('pc','pe','po')
    weight                   REAL,
    damage_dice              TEXT,
    damage_type_slug         TEXT,
    armor_class_base         INTEGER,
    armor_class_dex_bonus    INTEGER,
    armor_class_max_bonus    INTEGER,
    data                     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equip_cat    ON equipment(equipment_category_slug);
CREATE INDEX IF NOT EXISTS idx_equip_weapon ON equipment(weapon_category);
CREATE INDEX IF NOT EXISTS idx_equip_armor  ON equipment(armor_category);

-- ============================================================
-- Classes / Races
-- ============================================================
CREATE TABLE IF NOT EXISTS classes (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id            INTEGER NOT NULL REFERENCES collections(id),
    index_slug               TEXT NOT NULL UNIQUE,
    name                     TEXT NOT NULL,
    hit_die                  INTEGER,
    spellcasting_ability_slug TEXT,          -- 'int','wis','cha' | NULL
    data                     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS races (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    index_slug    TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    speed         INTEGER,
    size          TEXT,
    data          TEXT NOT NULL
);

-- ============================================================
-- Resto (Baja / Ninguna): solo slug + data
-- ============================================================
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

**Columnas reales nuevas vs v1:**
- `monsters.armor_class_type` ⟵ porque hay monstruos con `armor_class[0].type = "condition"` o `"spell"` (Ankheg, Archmage). Útil para mostrar tooltip en UI.
- `equipment.cost_unit_raw` ⟵ porque `es/` trae `pc/pe/po` y queremos preservar el original sin perder la normalización a `cp/sp/gp`.

**Por qué `size` y `type` van a columna aunque estén traducidos:** son los dos filtros más usados en la búsqueda de monstruos. El valor se guarda tal cual viene en `es/` (lo que ve el usuario) y el `data` conserva también los valores. No hay lógica de negocio que dependa del valor en inglés (el MVP no calcula nada con `type`).

---

## 4. Mapeo a la UI y endpoints actuales `[ACTUALIZADO]`

> Sin pantallas nuevas. Todo se engancha a `dm.html` / `player.html`.

| # | Endpoint | Método | Request | Response | Pantalla | Cambio UI |
|---|---|---|---|---|---|---|
| 1 | `/api/srd/monsters` | GET | `?q=&cr_min=&cr_max=&type=&size=&limit=50` | `{items:[{index,name,hit_points,challenge_rating,type,size,xp}]}` | **`dm.html`** panel "Nuevo combatiente" | Datalist junto a `#f-name` que autocompleta `#f-hp` y sugiere `#f-init` (`10+floor((DEX-10)/2)`). |
| 2 | `/api/srd/monsters/{index}` | GET | — | `{...data}` | **`dm.html`** | `<details>` con `actions`, `special_abilities`, `legendary_actions`, `senses`. |
| 3 | `POST /api/combatants` (extendido) | POST | `{name, hp_max, initiative, kind, srd_index?}` | `{ok, id}` | **`dm.html`** | Si `srd_index` presente, backend lee `monsters` y rellena `hp_max`/`name` si el cliente no los envía. **No rompe** contrato actual. |
| 4 | `/api/srd/spells` | GET | `?level=&class=&school=&q=` | `{items:[{index,name,level,school_slug,concentration,ritual}]}` | **`player.html`** sección "Hechizos" (colapsable) | Solo lectura. |
| 5 | `/api/srd/spells/{index}` | GET | — | `{...data}` | **`player.html`** | `<details>` inline. |
| 6 | `/api/srd/equipment` | GET | `?category=&weapon_category=&armor_category=` | `{items:[{index,name,cost_quantity,cost_unit,damage_dice}]}` | **`player.html`** sección "Inventario" | Solo lectura. |
| 7 | `/api/srd/classes` | GET | — | `{items:[{index,name,hit_die,spellcasting_ability_slug}]}` | **`player.html`** ficha | Selector de clase. |
| 8 | `/api/srd/classes/{index}/levels` | GET | `?from=&to=` | `{items:[{level,prof_bonus,spellcasting,class_specific}]}` | **`player.html`** ficha | Tabla de progresión. |
| 9 | `/api/srd/races` | GET | — | `{items:[{index,name,speed,size,ability_bonuses}]}` | **`player.html`** ficha | Selector de raza. |
| 10 | `/api/srd/refs/{collection}` | GET | — | `{items:[{index,name}]}` | **`dm.html`** filtros | Poblar `<select>` de filtros. |

**Invariante:** ningún endpoint `srd/*` muta estado, no requiere token, no toca `sessions`/`combatants`.

---

## 5. Casos raros y riesgos `[ACTUALIZADO con evidencia]`

### 5.1 Ambigüedades del schema — resueltas con datos reales

| # | Pregunta v1 | Respuesta del sondeo | Acción |
|---|---|---|---|
| 1 | `challenge_rating` fraccionario | **Sí**: `0.125, 0.25, 0.5` presentes (`§6`) | `REAL` confirmado. |
| 2 | `armor_class` array | **Sí**, con tipos `natural`, `dex`, `spell`, `condition` (`§7`) | Aplanar `[0].value` + columna `armor_class_type`. |
| 3 | `speed`/`senses` strings | **Sí**, traducidos (`"10 pies"`) (`§17`) | `data`. |
| 4 | `damage_*` string vs `condition_immunities` APIReference | **Confirmado**: `damage_immunities[0]` = `string`, `condition_immunities[0]` = `object` (`§8`) | `data`; no resolver strings como referencias. |
| 5 | `MonsterAction.damage` union `Damage\|Choice` | **Sí existe Choice**: `{choose:1, type:"damage", from:{option_set_type:"options_array", options:[{option_type:"damage",...}]}}` (`§9`) | Importador debe ramificar por `has("damage_dice")` vs `has("from")`. |
| 6 | `spellcasting` slots record | **Sí**: `{cantrips_known, spells_known, spell_slots_level_1..9}`, todas las claves presentes (`§15`) | `data`. |
| 7 | Clases sin `spellcasting` | **Todas las 12 lo tienen** (slots 0 en no-lanzadoras) (`§15`) `[CORREGIDO vs v1]` | No hay nulls que manejar. |
| 8 | `class_specific` polimórfico | 33 claves posibles (`§14`) | `data`. |
| 9 | `SubclassSpellPrerequisiteSchema` | Pendiente (no sondeado) — schema TS indica `{index,type,name,url}`, no `APIReference` puro | `data`. |
| 10 | `FeatureSpecificSchema` Choices anidados | Pendiente (no sondeado) | `data`. |
| 11 | `ChoiceSchema` forma | **3 ramas reales** (`§10`): `options_array` (163), `equipment_category` (24), `resource_list` (1) | Importador ramifica por `from.option_set_type`. |
| 12 | `Background.starting_equipment_options` array | No sondeado | `data`. |

### 5.2 `common.ts` — forma confirmada (del repomix 5e-bits)

```ts
APIReferenceSchema = { index, name, url, note? }         // note opcional
DamageSchema       = { damage_type: APIReference, damage_dice, dc? }
DifficultyClass    = { dc_type: APIReference, dc_value: number?, success_type: 'none'|'half'|'other' }
AreaOfEffect       = { size: number, type: 'sphere'|'cube'|'cylinder'|'line'|'cone' }
ChoiceSchema       = { desc?, choose: number, type?: string, from: OptionSetSchema }
OptionSetSchema    = union: equipment_category | resource_list | options_array
OptionSchema       = union de 13 formas (incluye 'damage', 'choice' recursivo, 'multiple', ...)
```

**Confirmado contra datos (§13):**
- `DifficultyClass` real: `{dc_type, dc_value, success_type}` ✓
- `Spell.dc` real (¡distinto!): `{dc_type, dc_success, desc?}` ✓
- `AreaOfEffect` real: `{type:"cube", size:20}` ✓
- `APIReference` real: todos tienen `{index, name, url}`; `note` no apareció en los samples (§13).

**Acción:** guardar `common.ts` en `srd-2014/schemas/common.ts` (no está local — `§21`). Se puede copiar del repo `5e-bits/5e-database@src/schemas/common.ts`.

### 5.3 Riesgos que persisten

1. **`es/` traduce `size`, `type`, `speed`, `senses`, `cost.unit`, `armor_class[].type`** (probablemente). Para columnas de filtro (`size`, `type`) usar el valor de `es/` (display). Para lógica de negocio (ninguna en MVP), no depender de estos campos.
2. **`cost.unit` mapeo obligatorio** `po→gp`, `pe→sp`, `pc→cp` para compatibilidad. Guardar `cost_unit_raw` para auditoría.
3. **`armor_class[].condition`** trae `APIReference` a `Conditions`; `armor_class[].spell` a `Spells`. FK lógicas que no se resuelven en MVP (van en `data`).
4. **Bug del script §12**: la sección de `APIReference` salió vacía por error de sintaxis (`shift 2` + `$*`). No afecta; se confirma por §13 y por `common.ts`.
5. **`index` idéntico en/es**: verificado en §2. Ningún `!! index cambió`. FK entre colecciones seguras.
6. **`name` NO siempre traducido**: `Aboleth`, `Berserker`, `STR` quedan igual. No asumir traducción completa de todos los `name`.
7. **`json_extract` para validaciones**: SQLite ≥ 3.38 lo soporta nativo (CachyOS Arch viene con ≥ 3.45). OK.

---

## 6. Orden de importación recomendado `[ACTUALIZADO con es/]`

Como `es/` es la única fuente (no hay merge), el orden es más simple:

**Fase 0 — Referencias (antes que todo):**
1. `damage-types`, `magic-schools`, `conditions`, `ability-scores`, `skills`, `weapon-properties`, `equipment-categories`, `alignments`, `languages` → `reference_entries`.

**Fase 1 — Combate (MVP):**
2. `monsters` → tabla `monsters`. **Única colección que cambia el comportamiento del MVP en esta iteración.**

**Fase 2 — Ficha (post-combate):**
3. `equipment`, `classes`, `levels`, `races`, `subraces`.
4. `spells`, `features`, `traits`, `proficiencies`, `backgrounds`, `feats`, `subclasses`.

**Fase 3 — Nunca / opcional:**
5. `magic-items` (solo si hay inventario).
6. `rules`, `rule-sections`: **nunca** en esta fase.
7. `alignments`, `languages`: importar en fase 0 como referencias; no invertir en UI.

Cada fase termina con `INSERT INTO import_meta` con `record_count` y `errors_json`. Si `errors_json` no es null, no avanzar.

---

## 7. Checklist de verificación `[ACTUALIZADO con datos reales]`

```sql
-- 1. Goblin con HP y CR correctos
SELECT index_slug, name, hit_points, armor_class, challenge_rating, xp
FROM monsters WHERE index_slug='goblin';
-- esperado: goblin|Goblin|7|15|0.25|50
-- (name puede ser 'Goblin' o 'Duende' según traducción)

-- 2. Fraccionarios de CR como filas propias
SELECT challenge_rating, COUNT(*) FROM monsters
GROUP BY challenge_rating ORDER BY challenge_rating;
-- esperado: incluir 0.125, 0.25, 0.5 como filas (NO 0)

-- 3. Sin CR NULL
SELECT COUNT(*) FROM monsters WHERE challenge_rating IS NULL;
-- esperado: 0

-- 4. Total exacto
SELECT COUNT(*) FROM monsters;
-- esperado: 334

-- 5. Todos los monstruos tienen bloque de acciones o habilidades
SELECT COUNT(*) FROM monsters
WHERE json_extract(data,'$.actions') IS NULL
  AND json_extract(data,'$.special_abilities') IS NULL
  AND json_extract(data,'$.legendary_actions') IS NULL;
-- esperado: 0

-- 6. Ankheg: armor_class[0].value = 14, [1] con condition (array multi)
SELECT index_slug, armor_class, armor_class_type,
       json_array_length(json_extract(data,'$.armor_class')) AS ac_len
FROM monsters WHERE index_slug='ankheg';
-- esperado: ankheg|14|natural|2

-- 7. Aboleth: abilities correctas
SELECT strength, dexterity, constitution, intelligence, wisdom, charisma
FROM monsters WHERE index_slug='aboleth';
-- esperado: 21|9|15|18|15|18

-- 8. Fireball: nivel 3, evocación, sin concentración
SELECT name, level, school_slug, concentration, ritual
FROM spells WHERE index_slug='fireball';
-- esperado: *|3|evocation|0|0

-- 9. Longsword: 1d8 slashing, coste 15 gp
SELECT name, damage_dice, damage_type_slug, cost_quantity, cost_unit, cost_unit_raw
FROM equipment WHERE index_slug='longsword';
-- esperado: *|1d8|slashing|15|gp|po

-- 10. Cross-check: todo damage_type_slug existe en reference_entries
SELECT DISTINCT e.damage_type_slug FROM equipment e
WHERE e.damage_type_slug IS NOT NULL
  AND e.damage_type_slug NOT IN (
    SELECT index_slug FROM reference_entries r
    JOIN collections c ON c.id = r.collection_id
    WHERE c.slug='damage-types'
  );
-- esperado: 0 filas

-- 11. Fighter niveles 1 y 20 con prof_bonus correcto
SELECT class_slug, level, prof_bonus FROM levels
WHERE class_slug='fighter' AND level IN (1,20) ORDER BY level;
-- esperado: fighter|1|2 y fighter|20|6

-- 12. Validación de import completo (post fase 1)
SELECT collection_slug, record_count FROM import_meta
WHERE collection_slug='monsters';
-- esperado: monsters|334
```

**Adicional (no SQL):**
- Simular `POST /api/combatants` con `srd_index:"goblin"` y verificar `combatants.hp_max=7`, `name='Goblin'` o `'Duende'`.
- `SELECT SUM(record_count) FROM import_meta` ≈ 2385.

---

### Resumen ejecutivo para el arquitecto

1. **`es/` es reemplazo completo de `en/`.** No hay merge ni fallback. El importador lee solo `srd-2014/es/`. `en/` queda como auditoría.
2. **Una sola tabla de contenido pesa en MVP:** `monsters`. Después `levels`+`spells`+`equipment` (ficha). El resto va a `reference_entries`.
3. **El contrato del MVP no cambia:** `POST /api/combatants` se extiende con `srd_index` opcional; los `GET /api/srd/*` son nuevos y no mutan estado.
4. **Mapeos obligatorios en importador:** `cost.unit` (`po/pe/pc` → `gp/sp/cp`), `armor_class[0].value` a `armor_class`, `armor_class[0].type` a `armor_class_type`.
5. **Riesgos residuales:** (a) `armor_class[]` con tipos heterogéneos, (b) `MonsterAction.damage` con union `Damage|Choice` real, (c) `ChoiceSchema.from.option_set_type` con 3 ramas, (d) `common.ts` no está local y hay que traerlo del repo 5e-bits, (e) `size`/`type`/`speed`/`senses` traducidos (van a display, no a lógica).
6. **Números finales:** 2.385 registros, ≈4,3 MB en JSON, ≈5 MB en SQLite con `data TEXT`. Despreciable para el MVP.
