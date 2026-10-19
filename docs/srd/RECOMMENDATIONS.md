# RECOMMENDATIONS.md — Orden de importación, tamaño, riesgos

**Proyecto:** DnD_tools · Fase 2.2–2.5
**Objetivo:** decir **cuándo** se importa cada colección, **cuánto ocupa** en SQLite tras cada fase, **qué se excluye** de 2.x, y **qué riesgos** tiene cada colección.

**Fuentes:** `INVENTORY.md` (qué se importa), `SHAPES.md` (estructura), `SCHEMAS.md` (drift), `MAPPING.md` (consumo por feature).
**Baseline:** `PRIOR_REPORT_v2.md §3` (schema SQLite) y `§6` (orden de importación) — se referencian, no se repiten. Este doc **sustituye** la estimación de tamaño de v2 (que no la daba) y **refina** el orden de v2 con la distinción D1/D2/D3.

## 0. Notación

- `[Dx]` — drift o contradicción de `SHAPES.md`/`SCHEMAS.md`.
- `[CONTRADICE v2 …]` — contradicción con `PRIOR_REPORT_v2.md`.
- Tamaños de SQLite: **estimados** con `PRAGMA page_size=4096` y `data TEXT` sin comprimir. Fórmula: `bytes_json_origen × 1,15 + overhead_por_tabla`. El factor 1,15 cubre índices e índices de `index_slug`.

---

## 1. Orden de importación por fase

Cada fase termina con `INSERT INTO import_meta` (schema de `PRIOR_REPORT_v2.md §3`) con `record_count` y `errors_json`. **No se avanza a la siguiente fase si `errors_json` no es `NULL`.**

### 1.1 Fase 2.2 — Bestiario (bloqueante para `/dm`)

| Orden | Colección | Tipo | Justificación |
|-------|-----------|------|---------------|
| 1 | `conditions` | referencia | **Primero**: `monsters.condition_immunities[]` y `monsters.armor_class[].condition` apuntan a `conditions.index`. Si se importa `monsters` antes, las FK lógicas no se pueden resolver. |
| 2 | `damage-types` | referencia | `monsters.actions[].damage[].damage_type` apunta a `damage-types.index`. Sin él, el `<details>` del monstruo no puede mostrar `Cortante` sino `slashing`. |
| 3 | `monsters` | entidad | El feature del bestiario (`MAPPING §7`) se apoya en `hit_points`, `armor_class[0].value`, `dexterity`, `actions[]`. Es la única colección que **cambia el comportamiento del MVP** en esta fase. |

**Criterio de salida de 2.2:** `SELECT COUNT(*) FROM monsters` = 334, `SELECT COUNT(*) FROM monsters WHERE armor_class IS NULL` = 0, `SELECT COUNT(*) FROM monsters WHERE challenge_rating IS NULL` = 0. Ver checklist de `PRIOR_REPORT_v2.md §7` (1–5, 12).

**Por qué solo estas 3:** Fase 2.2 = bestiario funcional. `monsters` sin `conditions` ni `damage-types` funciona pero muestra slugs. El resto (`equipment` para `armor_class[].armor`, `spells` para `armor_class[].spell`) es **opcional para 2.2** — se importa en 2.3/2.5, y la UI muestra la ref sin resolver hasta entonces.

### 1.2 Fase 2.3 — Mini-ficha (bloqueante para `/player`)

| Orden | Colección | Tipo | Justificación |
|-------|-----------|------|---------------|
| 4 | `ability-scores` | referencia | Base de todo: `str`..`cha`. Necesario antes de `skills` (que la referencia) y de `classes.saving_throws`. |
| 5 | `skills` | referencia | `skills.ability_score` → `ability-scores`. La ficha del jugador marca competencias; el mapa `skill → ability` es obligatorio para el cálculo de pruebas (`MAPPING §5`). |
| 6 | `equipment-categories` | referencia | `equipment.equipment_category` y `gear_category` apuntan aquí. Necesario para poblar filtros ("armas", "armaduras"). |
| 7 | `proficiencies` | referencia | `classes.proficiencies[]` apunta aquí. Sin él, la ficha muestra `simple-weapons` en vez de `Armas sencillas`. |
| 8 | `weapon-properties` | referencia | `equipment.properties[]` apunta aquí. Necesario antes de `equipment` para poder resolver las refs. |
| 9 | `damage-types` | referencia | **Ya importado en 2.2** — no se reimporta. Se referencia aquí por completitud del shape de `equipment.damage`. |
| 10 | `equipment` | entidad | La más grande de 2.3 (237 reg., 180 KB). Depende de `equipment-categories`, `weapon-properties`, `damage-types`. Sin él, no hay inventario ni ataque. |
| 11 | `classes` | entidad | `hit_die`, `saving_throws`, `spellcasting`. Depende de `ability-scores`, `proficiencies`. |
| 12 | `levels` | entidad | Depende de `classes`. Sin él, no hay `prof_bonus` ni `spell_slots`. |
| 13 | `races` | entidad | `ability_bonuses[]`, `speed`, `size`. Depende de `ability-scores`. |

**Criterio de salida de 2.3:** `SELECT COUNT(*) FROM equipment` = 237, `SELECT COUNT(*) FROM classes` = 12, `SELECT COUNT(*) FROM levels` = 290, `SELECT COUNT(*) FROM races` = 9. Cross-check de FK lógicas: `SELECT COUNT(*) FROM equipment WHERE damage_type_slug IS NOT NULL AND damage_type_slug NOT IN (SELECT index_slug FROM reference_entries WHERE collection_slug='damage-types')` = 0.

**Por qué `classes` después de `equipment` y no antes:** `classes.starting_equipment` y `starting_equipment_options` (ChoiceSchema complejo) **no se usan** en 2.3 (`MAPPING §2.5`). Importar `equipment` primero permite popular `classes` sin dependencias de resolución de `starting_equipment` — que se deja como refs en `data`.

**Por qué `races` al final:** es la única colección de 2.3 que el jugador puede **no elegir** (sin raza, la ficha funciona). Su importación no bloquea al resto de 2.3.

### 1.3 Fase 2.4 — Tiradas interactivas (sin colecciones nuevas)

**Ninguna colección nueva.** Fase 2.4 reutiliza `equipment` + `classes` + `levels` + `races` de 2.3. La feature de iniciativa usa `monsters.dexterity` (Fase 2.2) o `characters.dexterity` (creado en 2.3).

**Lo único que cambia en 2.4 es código**, no schema:
- Cálculo de `attack_bonus`, `damage_roll`, `initiative`.
- Endpoints `POST /api/combat/attack`, `POST /api/combat/check`.
- No hay migración de datos.

**Advertencia para el programador:** si busca una "tabla de tiradas" o "colección de armas mágicas", no existe. Las armas están en `equipment` y el ataque se calcula, no se almacena.

### 1.4 Fase 2.5 — Espacios de conjuro

| Orden | Colección | Tipo | Justificación |
|-------|-----------|------|---------------|
| 14 | `magic-schools` | referencia | `spells.school` apunta aquí. Sin él, el catálogo de hechizos no filtra por escuela. |
| 15 | `spells` | entidad | La más grande de todas (319 reg., 625 KB). Depende de `magic-schools`, `damage-types`, `classes`, `ability-scores`, `subclasses` (refs en `data`, sin tabla). |

**Criterio de salida de 2.5:** `SELECT COUNT(*) FROM spells` = 319, `SELECT COUNT(*) FROM spells WHERE school_slug IS NULL` = 0.

**Por qué `spells` en 2.5 y no en 2.3:** la mini-ficha (2.3) **no necesita el catálogo completo**, solo `levels.spellcasting` (slots) y `classes.spellcasting.spellcasting_ability` (CD/ataque). El catálogo de hechizos es una feature separada de selección de conjuros que se activa en 2.5. Importar 625 KB en 2.3 sin usarlos va contra el principio de "importa lo que uses".

**`[D6]` — warning obligatorio en 2.5:** `eldritch-blast` no escala. El importador debe registrar en `import_meta.errors_json`: `{"warning": "eldritch-blast.damage_at_character_level no escala (1d10 en las 4 claves)"}`. El DM ve un icono de advertencia en el hechizo.

---

## 2. Colecciones que NO se importan en Fase 2.x

Reafirmo `INVENTORY.md §2.3` con la justificación **desde el punto de vista del feature**:

| Colección | Reg. | Bytes JSON | Por qué NO en 2.x |
|-----------|-----:|-----------:|--------------------|
| `alignments` | 9 | 3.040 | Ningún feature del MVP consume alineamiento. |
| `backgrounds` | 1 | 12.031 | La ficha 2.3 no elige background (`MAPPING §2.5`). |
| `feats` | 1 | 800 | No se modelan dotes. |
| `features` | 407 | 371.720 | El mayor ahorro: 371 KB de texto narrativo sin uso en 2.x. |
| `languages` | 16 | 4.353 | Solo display si `races.languages[]`; `races` ya guarda las refs en `data`. |
| `magic-items` | 362 | 469.368 | No hay inventario mágico. |
| `rules` | 6 | 10.146 | Sin motor de reglas (`MAPPING §8`). |
| `rule-sections` | 33 | 219.936 | Igual. |
| `subclasses` | 12 | 55.501 | El MVP no elige subclase; `classes.subclasses[]` y `spells.subclasses[]` quedan como refs en `data`. |
| `subraces` | 4 | 3.660 | Igual que `subclasses`. |
| `traits` | 38 | 56.980 | `races.traits[]` queda como refs en `data`; no se resuelven. |

**Total no importado en 2.x:** 11 colecciones, **1.207.535 bytes** (≈ 29,7 % del corpus).

**Consecuencia visible:** los endpoints `/api/srd/*` no ofrecen filtros por alineamiento, background, dote, feature, idioma, item mágico, regla, subclase, subraza ni trait. El DM/jugador no ve esas dimensiones.

---

## 3. Estimación de tamaño de SQLite por fase

**Fórmula:** `bytes_sqlite ≈ bytes_json_origen × 1,15` (columna `data TEXT` + índices + overhead de página). Incluye `reference_entries` para las referencias.

| Fase | Colecciones | Bytes JSON origen | Bytes SQLite est. | Acumulado SQLite |
|------|-------------|------------------:|------------------:|------------------:|
| **Base** (vacío) | — | 0 | 0 | 0 |
| **2.2** | `monsters`, `conditions`, `damage-types` | 1.404.143 + 7.902 + 3.173 = **1.415.218** | **≈ 1.628 KB** (1,6 MB) | 1,6 MB |
| **2.3** | `classes`, `levels`, `equipment`, `races`, `ability-scores`, `skills`, `equipment-categories`, `proficiencies`, `weapon-properties` | 153.386 + 227.085 + 184.911 + 26.825 + 5.591 + 10.132 + 140.515 + 47.648 + 4.091 = **800.184** | **≈ 920 KB** | **≈ 2,5 MB** |
| **2.4** | — (0 nuevas) | 0 | 0 | 2,5 MB |
| **2.5** | `spells`, `magic-schools` | 640.292 + 3.263 = **643.555** | **≈ 740 KB** | **≈ 3,3 MB** |
| **No 2.x** | (11 colecciones) | 1.207.535 | 0 | 3,3 MB |

**Comparación con v2:** `PRIOR_REPORT_v2.md §3` no daba estimación numérica de SQLite. Este doc la da por fase. **`[CONTRADICE v2: v2 decía "≈ 5 MB" total para el corpus completo; aquí el corpus completo en SQLite sería ≈ 4,7 MB, y solo 2.x suma 3,3 MB]`**.

**Desglose por tabla (Fase 2.2 + 2.3 + 2.5):**

| Tabla | Filas | Bytes est. |
|-------|------:|-----------:|
| `monsters` | 334 | 1.500 KB |
| `levels` | 290 | 245 KB |
| `equipment` | 237 | 200 KB |
| `spells` | 319 | 690 KB |
| `classes` | 12 | 170 KB |
| `races` | 9 | 28 KB |
| `reference_entries` (`conditions`, `damage-types`, `ability-scores`, `skills`, `equipment-categories`, `proficiencies`, `weapon-properties`, `magic-schools`) | 131 | 145 KB |
| **Total tablas de contenido** | **1.332** | **≈ 2,9 MB** |
| Metadatos (`collections`, `import_meta`) | ~30 | ~50 KB |
| Índices | — | ~350 KB |
| **Total SQLite** | — | **≈ 3,3 MB** |

**Conclusión:** el tamaño es despreciable. El ahorro de no importar `features` (371 KB) + `magic-items` (469 KB) + `rule-sections` (215 KB) = 1 MB es irrelevante en disco; el ahorro real es **tiempo de importación** (≈ 60 % menos filas) y **superficie de error** (menos uniones polimórficas, menos drift).

**`[CONTRADICE checkpoint 2 §5]`:** en Checkpoint 2 estimé el tamaño como "despreciable" sin cifra. Aquí la doy (3,3 MB). No cambia la decisión, solo la cuantifica.

---

## 4. Riesgos por colección

Tabla por colección importada en 2.x, con la categoría de riesgo, la mitigación y el `[Dx]` asociado.

### 4.1 `monsters` (Fase 2.2) — riesgo **ALTO**

| Riesgo | Mitigación | D |
|--------|-----------|---|
| `armor_class[]` es array de 5 tipos; `[0].value` no es siempre la CA nominal (condicionales) | Aplanar `[0].value` a `armor_class`, `[0].type` a `armor_class_type`; descartar los condicionales (van en `data`) | D2 |
| `actions[].damage` es `Array<Damage\|Choice>` | Iterar `damage[]`; normalizar `option_type` | D4, D5 |
| `actions[].dc.success_type` puede venir como `'mitad'` | Normalizar a `half`/`none`/`other` antes de validar Zod | D11 |
| `special_abilities[].spellcasting.dc` es `int`, no `DifficultyClass` | No confundir con `spells.dc`; inspeccionar contexto | — |
| `type` y `size` traducidos, con plural a veces (`'humanoides'`) | No usar como enum; solo display. No hay columna `type_slug` normalizada | D7 |
| `damage_*` son strings, `condition_immunities` son refs | No unificar; cada uno va a `data` | — |
| URL drift en `APIReference.url` | FK por `index` | — |

**Mitigación global:** validar cada registro con un `z.strictObject` adaptado (con `success_type: z.string()` y `option_type: z.string()`) y registrar en `import_meta.errors_json` los `index` que fallen. Si falla > 5 % de los 334, **abortar la fase**.

### 4.2 `levels` (Fase 2.3) — riesgo **MEDIO**

| Riesgo | Mitigación | D |
|--------|-----------|---|
| `spellcasting` nullable: 160/290 con datos, 130/290 sin la clave | Columna `spellcasting_json TEXT NULL`; no `'{}'`. La UI distingue `NULL` de `0` | D1 |
| `class_specific` con 32 claves | Guardar entero en `data`; no normalizar a columnas | D3 |
| `spell_slots_level_6..9` opcionales | Aceptar `NULL` en esas claves | — |

**Mitigación global:** `spellcasting` se persiste como JSON en `data` (no como columnas por slot). El endpoint `GET /api/srd/classes/{index}/levels` devuelve el objeto tal cual.

### 4.3 `classes` (Fase 2.3) — riesgo **MEDIO**

| Riesgo | Mitigación | D |
|--------|-----------|---|
| `starting_equipment_options` es `ChoiceSchema` recursivo (profundidad 3+) | No parsear; guardar en `data` | — |
| `multi_classing.prerequisite_options` es `ChoiceSchema` | Idem | — |
| `spells` es URL (`'/api/classes/wizard/spells'`), no `APIReference` | Tratar como string; no resolver | — |
| URL drift en `proficiencies[]` | FK por `index` | — |

**Mitigación global:** las columnas reales se limitan a `hit_die`, `spellcasting_ability_slug`. El resto va a `data`.

### 4.4 `equipment` (Fase 2.3) — riesgo **BAJO-MEDIO**

| Riesgo | Mitigación | D |
|--------|-----------|---|
| `cost.unit` en `po`/`pe`/`pc` | Mapear a `gp`/`sp`/`cp`; guardar `cost_unit_raw` | — |
| `two_handed_damage` opcional (solo armas `versatile`) | Aceptar `NULL` | — |
| `armor_class.dex_bonus` bool; `max_bonus` opcional | Columnas `armor_class_dex_bonus INTEGER`, `armor_class_max_bonus INTEGER NULL` | — |
| `throw_range`, `range`, `speed` opcionales | `data` | — |
| `contents[]` para paquetes (refs a `equipment`) | `data`; no se resuelven | — |

### 4.5 `spells` (Fase 2.5) — riesgo **MEDIO-ALTO**

| Riesgo | Mitigación | D |
|--------|-----------|---|
| `damage_at_slot_level` y `damage_at_character_level` son `z.record(str, str)` con claves string numéricas | Guardar en `data` como JSON; no normalizar a columnas por nivel en 2.x | — |
| `eldritch-blast` no escala (dato erróneo) | Registrar warning en `import_meta.errors_json` | D6 |
| `attack_type` y `dc_success` traducidos | No usar como enum; normalizar si se consumen | D10 |
| `area_of_effect.type` enum inglés; no exhaustivamente verificado | Loguear fallos de validación | — |
| `classes[]` y `subclasses[]` con URL drift | FK por `index` | — |
| `heal_at_slot_level` coexiste con `damage` | Ambos pueden estar a la vez (raro); aceptar | — |

### 4.6 `races` (Fase 2.3) — riesgo **BAJO**

| Riesgo | Mitigación | D |
|--------|-----------|---|
| `starting_proficiencies` / `starting_proficiency_options` declarados en `.ts` pero 0/9 en JSON | No añadir columnas; documentar limitación | D12 |
| `languages[].name` en inglés (`'Common'`, `'Elvish'`) | Usar `index`; tabla de traducción manual para display | D9 |
| `traits[]` y `subraces[]` como refs a colecciones no importadas | Quedan en `data` sin resolver | — |
| `ability_bonus_options` ChoiceSchema opcional (solo half-elf) | `data` | — |

### 4.7 Referencias (`conditions`, `damage-types`, `ability-scores`, `skills`, `equipment-categories`, `proficiencies`, `weapon-properties`, `magic-schools`) — riesgo **BAJO**

Todas son `{index, name, desc[], url}`. El único riesgo es el drift de nombres (D8: `ability-scores`), que no afecta a la importación (solo a display).

---

## 5. Drift de datos (`[DRIFT DE DATOS]`) y su tratamiento

Hallazgos del dataset `es/` que el importador **no debe corregir automáticamente** (para no divergir del original) pero **sí debe registrar**:

| ID | Drift | Tratamiento recomendado |
|----|-------|--------------------------|
| D5 | `option_type: 'daño'` | Normalizar a `'damage'` antes de validar Zod. Registrar en `import_meta.errors_json` los valores no mapeados. |
| D6 | `eldritch-blast.damage_at_character_level` no escala | **No corregir**. Registrar warning. Mostrar al DM en la UI del hechizo. |
| D7 | `monsters.type = 'humanoides'` (plural) | **No corregir**. No usar `type` como enum. Solo display. |
| D8 | `ability-scores[str].name = 'STR'` vs `'FUE'` | **No corregir**. Usar `full_name` (`'Fuerza'`) para display; `index` para FK. |
| D9 | `races[elf].languages[]` con `name` inglés | **No corregir**. Usar `index`; si display importa, tabla manual. |
| D10 | `attack_type` (`'a distancia'`), `dc_success` (`'mitad'`) | **No corregir**. Normalizar en la capa de aplicación si se usan como enum. |
| D11 | `success_type: 'mitad'` vs enum `.ts` | Normalizar a `half`/`none`/`other` antes de validar Zod. |
| D12 | `races.starting_proficiencies` ausente | **No reconstruir**. Documentar limitación; el jugador las introduce manualmente. |

**Principio:** el importador **preserva el dato original** en `data`; las normalizaciones solo se aplican a columnas reales y a la validación Zod. Nunca se reescribe `data`.

---

## 6. Estimación de esfuerzo de importación

**No es un compromiso de tiempo**, es una estimación de complejidad relativa para priorizar.

| Fase | Colecciones | Complejidad | Riesgo | Justificación |
|------|-------------|-------------|--------|---------------|
| **2.2** | 3 | Media | Alto | `monsters` tiene 4 uniones polimórficas (`damage`, `action_options`, `options`, `spellcasting`) y drift D2/D4/D5/D11. |
| **2.3** | 9 | Baja-Media | Medio | `levels` con `class_specific` (32 claves) y `spellcasting` nullable (D1); el resto es plano. |
| **2.4** | 0 | Baja | Bajo | Solo código, sin importación. |
| **2.5** | 2 | Media | Medio | `spells` es plano pero con records anidados y drift D6. |

**Total:** 14 colecciones en 2.x (3 + 9 + 0 + 2 = 14; `damage-types` cuenta en 2.2 y no se reimporta en 2.3; `magic-schools` cuenta en 2.5).

---

## 7. Checklist de importación por fase

Reutilizo los checks de `PRIOR_REPORT_v2.md §7` (no los repito) y añado los que son nuevos por drift:

### 7.1 Nuevos checks post-importación

```sql
-- D2: los 5 tipos de armor_class están cubiertos
SELECT DISTINCT json_extract(ac.value, '$.type') FROM monsters,
  json_each(json_extract(monsters.data, '$.armor_class')) ac;
-- esperado: natural, dex, armor, spell, condition (5 filas)

-- D4: acciones con >1 elemento en damage[]
SELECT COUNT(*) FROM monsters
WHERE json_array_length(json_extract(data, '$.actions[0].damage')) > 1;
-- esperado: >0 (e.g. aboleth.Tentáculo tiene 2)

-- D5: option_type 'daño' debe estar normalizado en data
SELECT COUNT(*) FROM monsters
WHERE data LIKE '%"option_type": "daño"%';
-- esperado: 0 (si normalizamos) o >0 (si preservamos; documentar cuál)

-- D1: levels con y sin spellcasting
SELECT COUNT(*) FROM levels WHERE json_extract(data, '$.spellcasting') IS NOT NULL;
-- esperado: 160
SELECT COUNT(*) FROM levels WHERE json_extract(data, '$.spellcasting') IS NULL;
-- esperado: 130

-- D3: class_specific con 32 claves máximo
SELECT MAX((SELECT COUNT(*) FROM json_each(json_extract(data, '$.class_specific'))))
FROM levels WHERE json_extract(data, '$.class_specific') IS NOT NULL;
-- esperado: <= 5 (cada clase tiene 2-4 claves por nivel)

-- D6: warning de eldritch-blast registrado
SELECT errors_json FROM import_meta WHERE collection_slug='spells';
-- esperado: contiene 'eldritch-blast'

-- D12: races sin starting_proficiencies
SELECT COUNT(*) FROM races
WHERE json_extract(data, '$.starting_proficiencies') IS NULL;
-- esperado: 9 (0/9 tienen la clave)
```

---

## 8. Decisiones (una línea de justificación cada una)

- **`conditions` y `damage-types` antes que `monsters` en 2.2** — sin ellos, las FK lógicas de `monsters` quedan sin resolver y el `<details>` muestra slugs.
- **`equipment` antes que `classes` en 2.3** — `classes.starting_equipment` referencia `equipment`; invertir el orden complica la importación sin beneficio.
- **`races` al final de 2.3** — es la única colección opcional del feature (sin raza, la ficha funciona).
- **Fase 2.4 sin colecciones nuevas** — las tiradas se calculan sobre datos existentes; importar algo más sería scope creep.
- **`spells` solo en 2.5** — la ficha 2.3 no necesita el catálogo, solo `levels.spellcasting`. Importar 625 KB antes de tiempo no aporta.
- **No corregir D6–D10 en `data`** — preservar el dato original permite auditar el drift; corregirlo en `data` lo ocultaría.
- **Normalizar D5 y D11 antes de validar Zod** — si no, Zod strict falla y la importación aborta. La normalización va en el importador, no en `data`.
- **Warning de D6 en `import_meta.errors_json`** — es la única forma de que el DM vea que `eldritch-blast` está mal sin que el importador falle.
- **Estimación de 3,3 MB para 2.x** — reemplaza el "≈ 5 MB" de v2 (que incluía todo el corpus); da cifra concreta por fase.
- **14 colecciones en 2.x** — 3 + 9 + 0 + 2 = 14; el resto (11) queda fuera. Coherente con `INVENTORY.md §4`.
