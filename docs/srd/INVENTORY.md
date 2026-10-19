# INVENTORY.md — Inventario de las 25 colecciones SRD 5e (2014) en español

**Proyecto:** DnD_tools (MVP de combate + fases 2.2–2.5)
**Fuente JSON:** `/home/fyjjuk/DnD/raw/srd-2014/es/`
**Schemas TS:** `/home/fyjjuk/DnD/raw/srd-2014/schemas/`
**Baseline:** `PRIOR_REPORT_v2.md` (ver §1 conteos, §2 campos, §5 casos raros, §6 orden de importación) — no se repite aquí.
**Sondas usadas:** `_probe_shapes.py` (Checkpoint 1), `_probe_phase2.py` (Checkpoint 2). Salidas crudas en `/home/fyjjuk/DnD/raw/_analysis/shapes.txt` y `phase2.txt`.

> Los conteos de registros y campos clave se citan de `PRIOR_REPORT_v2.md §1` cuando coinciden con el sondeo. Los tamaños se miden con `os.path.getsize` (bytes exactos), no con `du -h` — ver §5.1.

---

## 1. Tabla completa de las 25 colecciones

Clasificación de `Tipo`:
- **entidad** — tiene (o tendrá) tabla propia con columnas reales en el schema SQLite.
- **referencia** — se importa a `reference_entries` para resolver `APIReference` (solo `index`, `name`, `data`).
- **nunca** — no se importa en Fase 2.x.

Columna `Fase 2.x` indica **cuándo** se importa. `2.4` no aparece porque Fase 2.4 (tiradas interactivas) **no añade colecciones nuevas** — reutiliza lo importado en 2.3.

| # | Slug | Archivo JSON | Reg | Tamaño | Tipo | Fase 2.x |
|---|------|--------------|-----|--------|------|----------|
| 1 | ability-scores | 5e-SRD-Ability-Scores.json | 6 | 5.5 KB | referencia | **2.3** |
| 2 | alignments | 5e-SRD-Alignments.json | 9 | 3.0 KB | nunca | — |
| 3 | backgrounds | 5e-SRD-Backgrounds.json | 1 | 11.7 KB | nunca | — |
| 4 | classes | 5e-SRD-Classes.json | 12 | 149.8 KB | entidad | **2.3** |
| 5 | conditions | 5e-SRD-Conditions.json | 15 | 7.7 KB | referencia | **2.2** |
| 6 | damage-types | 5e-SRD-Damage-Types.json | 13 | 3.1 KB | referencia | **2.3** |
| 7 | equipment-categories | 5e-SRD-Equipment-Categories.json | 39 | 137.2 KB | referencia | **2.3** |
| 8 | equipment | 5e-SRD-Equipment.json | 237 | 180.6 KB | entidad | **2.3** |
| 9 | feats | 5e-SRD-Feats.json | 1 | 0.8 KB | nunca | — |
| 10 | features | 5e-SRD-Features.json | 407 | 363.0 KB | nunca | — |
| 11 | languages | 5e-SRD-Languages.json | 16 | 4.3 KB | nunca | — |
| 12 | levels | 5e-SRD-Levels.json | 290 | 221.8 KB | entidad | **2.3** |
| 13 | magic-items | 5e-SRD-Magic-Items.json | 362 | 458.4 KB | nunca | — |
| 14 | magic-schools | 5e-SRD-Magic-Schools.json | 8 | 3.2 KB | referencia | **2.5** |
| 15 | monsters | 5e-SRD-Monsters.json | 334 | 1371.2 KB | entidad | **2.2** |
| 16 | proficiencies | 5e-SRD-Proficiencies.json | 117 | 46.5 KB | referencia | **2.3** |
| 17 | races | 5e-SRD-Races.json | 9 | 26.2 KB | entidad | **2.3** |
| 18 | rule-sections | 5e-SRD-Rule-Sections.json | 33 | 214.8 KB | nunca | — |
| 19 | rules | 5e-SRD-Rules.json | 6 | 9.9 KB | nunca | — |
| 20 | skills | 5e-SRD-Skills.json | 18 | 9.9 KB | referencia | **2.3** |
| 21 | spells | 5e-SRD-Spells.json | 319 | 625.3 KB | entidad | **2.5** |
| 22 | subclasses | 5e-SRD-Subclasses.json | 12 | 54.2 KB | nunca | — |
| 23 | subraces | 5e-SRD-Subraces.json | 4 | 3.6 KB | nunca | — |
| 24 | traits | 5e-SRD-Traits.json | 38 | 55.6 KB | nunca | — |
| 25 | weapon-properties | 5e-SRD-Weapon-Properties.json | 11 | 4.0 KB | referencia | **2.3** |

**Totales:** 25 colecciones, 2.385 registros, **4.066.492 bytes** (≈ 3,88 MiB). Ver §4 y §5.1.

Conteos de `#1, #4, #5..#8, #12, #14..#17, #20, #21, #25` verificados en el sondeo (Checkpoint 1 y 2). Los demás coinciden con `PRIOR_REPORT_v2.md §1`; no fueron re-sondeados aquí (fuera de scope Fase 2.x).

---

## 2. Colecciones prioritarias (Fase 2.2–2.5)

### 2.1 Las 10 prioritarias (con shape analysis en `SHAPES.md`)

Estas 10 son las que necesitan shape compacto completo y cross-check con sus `.ts` (van en `SHAPES.md` y `SCHEMAS.md`). Son las que el proyecto **usa activamente** en 2.2–2.5.

| # | Slug | Tipo | Fase | Campos clave que usa el proyecto |
|---|------|------|------|-----------------------------------|
| 1 | ability-scores | referencia | 2.3 | `index`, `name`, `full_name`, `skills[]` (para calcular modificadores e iniciativa) |
| 2 | skills | referencia | 2.3 | `index`, `name`, `ability_score` (mapa habilidad → característica) |
| 3 | classes | entidad | 2.3 | `hit_die`, `proficiencies[]`, `saving_throws[]`, `spellcasting.spellcasting_ability` |
| 4 | levels | entidad | 2.3 | `level`, `prof_bonus`, `spellcasting` (slots), `class_specific` (32 claves) |
| 5 | equipment | entidad | 2.3 | `damage`, `two_handed_damage`, `cost`, `weight`, `properties[]`, `armor_class` |
| 6 | weapon-properties | referencia | 2.3 | `index` (para `versatile`, `finesse`, `two-handed`, `reach`…) |
| 7 | damage-types | referencia | 2.3 | `index` (resuelve `damage.damage_type` de `equipment` y `monsters`) |
| 8 | spells | entidad | 2.5 | `level`, `school`, `damage.damage_at_slot_level`, `heal_at_slot_level` |
| 9 | monsters | entidad | 2.2 | `hit_points`, `armor_class[]`, `challenge_rating`, 6 características, `actions[].damage[]`, `special_abilities[].spellcasting` |
| 10 | races | entidad | 2.3 | `speed`, `ability_bonuses[]`, `size` (bonus opcional para mini-ficha) |

### 2.2 Referencias secundarias (importadas como `reference_entries`, sin shape analysis)

Estas 4 **sí se importan en Fase 2.x** pero no necesitan `SHAPES.md` porque su estructura ya está cubierta por `common.ts` (`{index, name, url}` o `{index, name, desc[], url}`). Se cargan en `reference_entries` para poder resolver `APIReference`.

| # | Slug | Fase | Referenciada por | Uso |
|---|------|------|------------------|-----|
| 1 | conditions | 2.2 | `monsters.condition_immunities[]`, `monsters.armor_class[].condition` | display "Inmune a: derribado, apresado…" |
| 2 | equipment-categories | 2.3 | `equipment.equipment_category`, `equipment.gear_category` | filtro UI "¿armas? ¿armaduras?" |
| 3 | proficiencies | 2.3 | `classes.proficiencies[]`, `classes.multi_classing.proficiencies[]` | display "Competente con: armas marciales, escudos…" |
| 4 | magic-schools | 2.5 | `spells.school` | filtro "Escuela de Evocación" en hechizos |

### 2.3 Colecciones fuera de Fase 2.x

No se importan en ninguna fase 2.x (ni 2.2, ni 2.3, ni 2.5). Motivos:

| Slug | Registros | Motivo de exclusión | Reconsiderable en |
|------|-----------|---------------------|-------------------|
| alignments | 9 | El MVP de combate no usa alineamiento. No hay lógica de negocio asociada. | Fase 3 (rol) |
| backgrounds | 1 | La mini-ficha de Fase 2.3 se centra en 6 características + clase + armas. Backgrounds no añade valor jugable. | Fase 3 (rol) |
| feats | 1 | 1 solo registro (Grappler). No es feature de ficha en 2.3. | Fase 3+ |
| features | 407 | 363 KB de descripciones narrativas. La ficha 2.3 solo necesita slots y prof_bonus. | Fase 3+ (progresión) |
| languages | 16 | Referenciada solo por `races.languages[]`; el MVP no muestra idiomas. Las refs quedan en `data`. | Fase 3 |
| magic-items | 362 | No hay inventario mágico en el MVP. v2 §6 ya lo excluye. | Fase 3+ (inventario) |
| rules | 6 | 6 reglas base; el MVP no valida reglas. | Nunca (decorativo) |
| rule-sections | 33 | 215 KB de texto de reglas. Sin lógica. | Nunca (decorativo) |
| subclasses | 12 | Referenciada por `spells.subclasses[]`, pero el MVP no filtra por subclase. Sus refs van en `data` sin resolver. | Fase 3+ |
| subraces | 4 | 4 registros. La ficha 2.3 usa `races`, no `subraces`. | Fase 3+ |
| traits | 38 | Referenciada por `races.traits[]`, pero el MVP no muestra traits. `data` los conserva como refs. | Fase 3+ |

---

## 3. Criterio de clasificación `referencia` vs `entidad`

- **entidad**: tiene columnas propias más allá de `index_slug` + `name` + `data`. Se necesita query por esos campos (e.g. `monsters.challenge_rating`, `equipment.cost_unit`, `spells.level`). En Fase 2.x son **6**: `monsters`, `spells`, `equipment`, `classes`, `levels`, `races`.
- **referencia**: se resuelve con `{index_slug, name, data}` en `reference_entries`. En Fase 2.x son **8**: `ability-scores`, `skills`, `damage-types`, `weapon-properties`, `conditions`, `equipment-categories`, `proficiencies`, `magic-schools`.
- **nunca**: no se importa en 2.x. En total **11**: las 11 de §2.3.

6 + 8 + 11 = 25. ✓

---

## 4. Totales por fase

Cifras de **bytes JSON de origen** (no de SQLite, que va en `RECOMMENDATIONS.md`).

| Fase | Colecciones importadas | Bytes JSON origen | Acumulado |
|------|------------------------|-------------------|-----------|
| **2.2** (bestiario) | `monsters` (entidad) + `conditions` (ref) | 1.404.143 + 7.902 = **1.412.045** | 1.412.045 |
| **2.3** (mini-ficha) | `classes`, `levels`, `equipment`, `races` (entidades) + `ability-scores`, `skills`, `damage-types`, `weapon-properties`, `equipment-categories`, `proficiencies` (refs) | 153.386 + 227.085 + 184.911 + 26.825 + 5.591 + 10.132 + 3.173 + 4.091 + 140.515 + 47.648 = **803.357** | 2.215.402 |
| **2.4** (tiradas) | ninguna nueva (reutiliza 2.3) | 0 | 2.215.402 |
| **2.5** (slots) | `spells` (entidad) + `magic-schools` (ref) | 640.292 + 3.263 = **643.555** | 2.858.957 |
| **Nunca en 2.x** | 11 colecciones | 1.207.535 | — |
| **Total es/** | 25 | **4.066.492** | — |

**Porcentaje del corpus usado en 2.x:** 2.858.957 / 4.066.492 = **70,3 %**. El 29,7 % restante (rules, rule-sections, magic-items, features, subclasses, etc.) queda en disco para futuras fases pero no entra en SQLite.

**Verificación cruzada con `PRIOR_REPORT_v2.md §1`:**
- Total registros v2: 2.385. Suma del sondeo: 2.385. ✓
- Total bytes v2 (du): ≈4,3 MB. Sondeo (getsize): 4.066.492 bytes = 3,88 MiB. → ver §5.1.
- Conteos por colección de las 10 prioritarias: 6, 18, 12, 290, 237, 11, 13, 319, 334, 9. Idénticos a v2. ✓

---

## 5. Notas de coherencia con `PRIOR_REPORT_v2.md` y con el sondeo

### 5.1 Medición de tamaño

- **Sondeo (fuente de este doc):** `os.path.getsize` sobre cada archivo. Total **4.066.492 bytes** = 3,88 MiB.
- **`PRIOR_REPORT_v2.md §1`:** reporta "≈ 4,3 MB" midiendo con `du -h`. La diferencia (~400 KB) es atribuible a:
  1. `du` cuenta bloques de 4 KB por archivo (25 archivos × ~1,5 KB de overhead medio ≈ 40 KB).
  2. `du` incluye el directorio `es/` (4 KB) y posiblemente `.` si se lanzó desde `es/`.
  3. Posible redondeo de `du -h` a un decimal.
- **No es contradicción**, es diferencia de tooling. El tamaño real de bytes es 4.066.492.

### 5.2 Contradicciones con v2 (D1–D4) — trazabilidad

Estas 4 están **detalladas** en el doc indicado. En este inventario solo se listan para que no se pierdan.

| ID | Contradicción con v2 | Detectada en | Doc donde se detalla |
|----|----------------------|--------------|----------------------|
| D1 | `[CONTRADICE v2 §5.1 #7]` — `levels.spellcasting` **no** está en 12/12 clases; solo en 8/12 (160/290). `fighter-1` no lo tiene. | probe 1 `# extras` | `SCHEMAS.md §4`, `CONTRACT.md §5` |
| D2 | `[CONTRADICE v2 §5.1 #2]` — `armor_class[].type` tiene **5** valores (`natural`, `dex`, `armor`, `spell`, `condition`), no 4. | probe 1 `# extras` + `monsters[goblin]` | `SHAPES.md §monsters`, `SCHEMAS.md §4`, `CONTRACT.md §5` |
| D3 | `[CONTRADICE v2 §5.1 #8]` — `class_specific` tiene **32** claves, no 33. | probe 1 `# extras` + `.ts` | `SHAPES.md §levels`, `SCHEMAS.md §4` |
| D4 | `[CONTRADICE v2 §5.1 #5]` — `MonsterAction.damage` es `Array<Damage \| Choice>`, no `Damage \| Choice`. El importador itera `damage[]`. | probe 2 Section C | `SHAPES.md §monsters`, `MAPPING.md`, `CONTRACT.md §5` |

### 5.3 Drift de datos (D5–D10) — trazabilidad

Encontrados durante el Checkpoint 2. No son contradicciones con v2 sino **bugs / inconsistencias del dataset `es/`** o drift `.ts` vs `.json`.

| ID | Drift | Evidencia | Doc donde se detalla |
|----|-------|-----------|----------------------|
| D5 | `option_type: "daño"` (español) donde `common.ts` declara `z.literal('damage')` (inglés). Solo en `monsters.actions[].damage[].from.options[]`. | `phase2.txt` Section C (`djinni`, `drider`, `druid`) | `SCHEMAS.md §4`, `RECOMMENDATIONS.md §4` |
| D6 | `spells[eldritch-blast].damage.damage_at_character_level` = `{"1":"1d10","5":"1d10","11":"1d10","17":"1d10"}`. En SRD inglés: `1d10/2d10/3d10/4d10`. **Dato erróneo del dataset**. | `phase2.txt` Section D | `SCHEMAS.md §4`, `RECOMMENDATIONS.md §5` |
| D7 | `monsters[goblin].type = "humanoides"` (plural), SRD inglés = `"humanoid"`. `name: "Goblin"` sin traducir, `size: "Pequeño"` traducido. | `phase2.txt` Section D | `SCHEMAS.md §4`, `RECOMMENDATIONS.md §5` |
| D8 | `ability-scores[str].name = "STR"`, `full_name = "Fuerza"`. Pero refs (`skills.athletics.ability_score`) usan `name: "FUE"`. Misma entidad, dos `name` distintos. | `phase2.txt` Section D | `SCHEMAS.md §4`, `RECOMMENDATIONS.md §5` |
| D9 | `races[elf].languages[]` = `["Common", "Elvish"]` (inglés dentro de fichero español). | `phase2.txt` Section D | `SCHEMAS.md §4` |
| D10 | `attack_type: "a distancia"` (`eldritch-blast`), `dc_success: "mitad"` (`fireball`). `.ts` declara `z.string()` — correcto, pero el valor no es machine-readable sin tabla de traducción. | `phase2.txt` Section D | `MAPPING.md`, `RECOMMENDATIONS.md §4` |

### 5.4 Contradicciones con Checkpoint 2

Ninguna detectada al redactar `INVENTORY.md`. Las decisiones del Checkpoint 2 (FK por `index`, normalizar `daño`→`damage`, `po/pe/pc`→`gp/sp/cp`, `levels.spellcasting` nullable) siguen vigentes.

---

## 6. Decisiones (una línea de justificación cada una)

- **Excluir `features` (407 reg., 363 KB) de Fase 2.x** — la ficha 2.3 solo necesita `levels.spellcasting` + `levels.prof_bonus`; las `features[]` van a `data` como refs sin resolver.
- **Excluir `subclasses` (12 reg.) de Fase 2.x** — el MVP no tiene selector de subclase; `spells.subclasses[]` queda como refs en `data` sin tabla destino.
- **Excluir `magic-items` (362 reg., 458 KB)** — no hay inventario en el MVP; v2 §6 ya lo excluye y aquí se confirma.
- **Importar `conditions` en 2.2** — `monsters.condition_immunities[]` lo necesita para el display del bestiario. Sin él, "Inmune a: prone" mostraría solo el slug.
- **Importar `equipment-categories`, `proficiencies`, `magic-schools` como refs** — son necesarias para resolver `APIReference` en 2.3/2.5; sin tabla de resolución, los filtros de UI no pueden agrupar.
- **No importar `languages` en 2.x** — solo aparece como `races.languages[]`; el MVP no muestra idiomas y las refs quedan en `data`.
- **Fase 2.4 no añade colecciones** — las tiradas interactivas reutilizan `equipment` + `classes` + `levels` + `races` de 2.3. Documentar esto evita que el programador busque una colección "de tiradas" que no existe.
- **Tamaño total 4.066.492 bytes (getsize), no 4,3 MB (du)** — reportar la cifra exacta y anotar la diferencia de tooling evita que el programador dimensione SQLite con un +10 % innecesario.
