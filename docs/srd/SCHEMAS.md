# SCHEMAS.md — Los 25 `.ts` + `common.ts` vs el JSON real

**Proyecto:** DnD_tools · Fase 2.2–2.5
**Fuente normativa:** `/home/fyjjuk/DnD/raw/srd-2014/schemas/*.ts` (25 archivos) + `/home/fyjjuk/DnD/raw/schemas/common.ts`.
**Fuente de contraste:** `/home/fyjjuk/DnD/raw/srd-2014/es/*.json`.
**Sondas:** `_dump_schemas.py` (salida `schemas_dump.txt`), `_probe_shapes.py`, `_probe_phase2.py`.
**Baseline:** `PRIOR_REPORT_v2.md` — se cita por `§`, no se repite.

> **Regla de oro de este doc:** el `.ts` dice *qué valida Zod*; el JSON dice *qué hay en disco*. Cuando discrepan, el JSON gana para el importador, y aquí se anota como drift.

## 0. Notación

- `.ts` — archivo Zod en `srd-2014/schemas/` o `common.ts`.
- `required` — campo sin `?` ni `.optional()`.
- `optional` — campo con `?` o `.optional()`.
- `[D5]`, `[D11]` etc. — drift o contradicción referenciable.
- `[NUEVO D11]` / `[NUEVO D12]` — hallazgo de este doc, no detectado en Checkpoints 1–2.
- Todas las clases `z.strictObject` de este repo **rechazan campos extra**. Un validador Zod que use estos `.ts` fallará en runtime ante cualquier drift de campo, no solo ante drift de tipo.

---

## 1. Resumen ejecutivo

**Estructura de los schemas:**
- Los 25 `.ts` importan `APIReferenceSchema` (y a veces `ChoiceSchema`, `DamageSchema`, `DifficultyClassSchema`, `AreaOfEffectSchema`) desde `../../schemas/common`.
- Todos usan `z.strictObject`, por lo que **validación estricta**: un campo no declarado en `.ts` que aparezca en JSON es error; un campo requerido en `.ts` que falte en JSON es error.
- Los `.ts` son del repo `5e-bits/5e-database` (versión **en**) y el dataset `es/` es una traducción 1:1. **La traducción introduce drift de valores** (no de estructura) en los enums y strings libres.

**Los 12 hallazgos de este doc (resumen; detalles en §4):**

| ID | Tipo | Campo | Impacto |
|----|------|-------|---------|
| D5 | `.ts↔.json` (valor) | `OptionSchema.option_type: z.literal('damage')` vs JSON `"daño"` | Zod strict falla. Importador debe normalizar. |
| D11 | `.ts↔.json` (valor) | `DifficultyClassSchema.success_type: z.enum(['none','half','other'])` vs JSON `"mitad"`, `"ninguno"` | Zod strict falla. Importador debe normalizar. |
| D12 | `.ts↔.json` (campo) | `RaceSchema.starting_proficiencies` / `starting_proficiency_options` declarados, 0/9 en JSON | No rompe importador (son opcionales), pero la UI nunca los verá. |
| D-URL | JSON interno | `APIReference.url` mezcla `/api/X` y `/api/2014/X` | FK por `index`, no por `url`. (Ya en `SHAPES §13`.) |
| — | `.ts` más permisivo | `ChoiceSchema.type: z.string()` con valores `"daño"`, `"equipo"` | No falla Zod; sí falla lógica que espere enum inglés. |
| — | `.ts` declara enum inglés | `AreaOfEffectSchema.type: z.enum(['sphere',...])` con JSON `"sphere"` | OK en muestra (fireball); no exhaustivo sobre 319 hechizos. |
| — | `.ts` más permisivo | `LevelSchema.features?:` (optional) vs 290/290 en JSON | Compatible. |
| — | `.ts` más permisivo | `SpellSchema.subclasses?:` (optional) vs 319/319 en JSON | Compatible. |
| — | `.ts` declara campo no observado | `APIReferenceSchema.note?` (0 ocurrencias en las 10 prioritarias) | Compatible (optional). |
| — | `.ts` declara rama no observada | `OptionSetSchema.resource_list` (0 ocurrencias en las 10 prioritarias) | Compatible (unión). Probablemente en `backgrounds`. |
| — | `.ts` redundante | `SubclassSpellPrerequisiteSchema` duplica `APIReference` + `type` | Cosmético; no drift. |
| — | `.ts` requiere vs JSON | Ningún caso de campo required en `.ts` ausente en JSON (verificado en las 10 prioritarias). | OK. |

**Conteo:** 25 `.ts` analizados + `common.ts`. De los 25, **10 son prioritarios** (los de `SHAPES.md`) y **15 son no prioritarios** (documentados aquí solo por `.ts`; su JSON no fue volcado en Checkpoint 2).

---

## 2. `common.ts` — schemas compartidos

Archivo: `/home/fyjjuk/DnD/raw/schemas/common.ts` (importado como `'../../schemas/common'` desde los 25 `.ts`).

### 2.1 `APIReferenceSchema`

```ts
export const APIReferenceSchema = z.strictObject({
  index: z.string(),
  name: z.string(),
  url: z.string(),
  note: z.string().optional(),
});
```

**Observado en JSON:** `{index, name, url}` (sin `note`) en todos los samples de Checkpoint 2. `note` es opcional, así que Zod no falla si falta. **Sin drift estructural.**

**Nota para el importador:** `index` es el identificador estable. `url` tiene drift (`/api/X` vs `/api/2014/X`) — ver `SHAPES §13`. **FK siempre por `index`.**

### 2.2 `DifficultyClassSchema` — `[NUEVO D11]`

```ts
export const DifficultyClassSchema = z.strictObject({
  dc_type: APIReferenceSchema,
  dc_value: z.number().optional(),
  success_type: z.enum(['none', 'half', 'other']),
});
```

**`[NUEVO D11]`** — `success_type` es un **enum inglés** en `.ts`. El JSON `es/` trae valores en castellano:

```json
// monsters[ankheg].actions[Rocío Ácido].dc
{
  "dc_type": { "index": "dex", "name": "DES", "url": "/api/2014/ability-scores/dex" },
  "dc_value": 13,
  "success_type": "mitad"
}

// monsters[aboleth].actions[Tentáculo].damage[0].dc  (mismo patrón, valor no muestreado aquí)
```

**Impacto:** un validador Zod con este `.ts` **falla en runtime** para cualquier monstruo con `dc.success_type != 'none'`. No es un problema de tipos Zod, es un problema de **valor**: el enum está en inglés y el dato en castellano.

**Decisión de importador:** normalizar `success_type` al inglés antes de validar con Zod, o aceptar `z.string()` y gestionar el mapeo en la capa de aplicación. Ver `RECOMMENDATIONS.md §4` y `CONTRACT.md §4`.

**Afecta a:** `monsters.actions[].dc`, `monsters.actions[].damage[].dc`, `monsters.attacks[].dc`, `monsters.legendary_actions[].dc`, `monsters.reactions[].dc`, `monsters.special_abilities[].dc`, `traits[].trait_specific.breath_weapon.dc` (no prioritaria).

**El campo `dc_success` de `SpellDCSchema`** (`SpellDCSchema.dc_success: z.string()`) **no es el mismo** y no cae en este drift: es `string`, el JSON trae `"mitad"` y Zod lo acepta. Dos campos distintos con nombres distintos.

### 2.3 `DamageSchema`

```ts
export const DamageSchema = z.strictObject({
  damage_type: APIReferenceSchema,
  damage_dice: z.string(),
  dc: DifficultyClassSchema.optional(),
});
```

**Observado en JSON:** `{damage_type, damage_dice}` (sin `dc` en la mayoría) y ocasionalmente con `dc` (cuando el daño requiere salvación). Estructura match.

**Hereda el drift D11** vía `dc.success_type` cuando `dc` está presente.

### 2.4 `AreaOfEffectSchema`

```ts
export const AreaOfEffectSchema = z.strictObject({
  size: z.number(),
  type: z.enum(['sphere', 'cube', 'cylinder', 'line', 'cone']),
});
```

**Observado en JSON:** `spells[fireball].area_of_effect = {"type": "sphere", "size": 20}`. **Inglés preservado** — a diferencia de `success_type` y `option_type`, este enum **no** se tradujo.

**Cobertura:** muestra = 1 spell (`fireball`). **No exhaustivo** sobre las 319 spells. Si `type` estuviera traducido en alguna otra (`'esfera'`, `'cubo'`), Zod fallaría en ese registro. El importador debe loggear cualquier fallo de validación de `area_of_effect` con `index` del spell para identificarlo.

### 2.5 `ChoiceSchema` + `OptionSchema` + `OptionSetSchema` — `[D5]`

```ts
export const ChoiceSchema = z.lazy(() => z.strictObject({
  desc: z.string().optional(),
  choose: z.number(),
  type: z.string().optional(),
  from: OptionSetSchema,
}));

const OptionSchema = z.lazy(() => z.union([
  z.strictObject({ option_type: z.literal('reference'),         item: APIReferenceSchema }),
  z.strictObject({ option_type: z.literal('choice'),            choice: ChoiceSchema }),
  z.strictObject({ option_type: z.literal('string'),            string: z.string() }),
  z.strictObject({ option_type: z.literal('ability_bonus'),     ability_score: APIReferenceSchema, bonus: z.number() }),
  z.strictObject({ option_type: z.literal('action'),            action_name: z.string(), count: z.number(), type: z.string(), desc: z.string().optional() }),
  z.strictObject({ option_type: z.literal('breath'),            name: z.string(), dc: DifficultyClassSchema, damage: z.array(DamageSchema).optional() }),
  z.strictObject({ option_type: z.literal('counted_reference'), count: z.number(), of: APIReferenceSchema, prerequisites: z.array(z.strictObject({ type: z.string(), proficiency: APIReferenceSchema.optional() })).optional() }),
  z.strictObject({ option_type: z.literal('damage'),            damage_dice: z.string(), damage_type: APIReferenceSchema, notes: z.string().optional() }),
  z.strictObject({ option_type: z.literal('ideal'),             alignments: z.array(APIReferenceSchema), desc: z.string() }),
  z.strictObject({ option_type: z.literal('money'),             count: z.number(), unit: z.string() }),
  z.strictObject({ option_type: z.literal('multiple'),          items: z.array(OptionSchema), desc: z.string().optional() }),
  z.strictObject({ option_type: z.literal('score_prerequisite'), ability_score: APIReferenceSchema, minimum_score: z.number() }),
  z.strictObject({ option_type: z.literal('size'),              size: z.string() }),
]));

const OptionSetSchema = z.union([
  z.strictObject({ option_set_type: z.literal('equipment_category'), equipment_category: APIReferenceSchema }),
  z.strictObject({ option_set_type: z.literal('resource_list'),      resource_list_url: z.string() }),
  z.strictObject({ option_set_type: z.literal('options_array'),      options: z.array(z.union([OptionSchema, z.string()])) }),
]);
```

**Drift `[D5]`:** `option_type: z.literal('damage')` (inglés). En `monsters[djinni]`, `monsters[drider]`, `monsters[druid]` el JSON trae `"option_type": "daño"` (castellano). **Zod strict falla.**

**Otros drift menores (no falla Zod, pero rompe lógica de negocio):**
- `ChoiceSchema.type: z.string()` — el JSON trae `"daño"`, `"equipo"`, `"proficiencies"`, `"languages"`… mezcla de castellano e inglés. No hay enum, así que Zod lo acepta, pero el importador no puede comparar con `"damage"` sin tabla.
- `OptionSetSchema.resource_list` — declarado en `.ts`, 0 ocurrencias en las 10 prioritarias. Probablemente vive en `backgrounds` (fuera de scope 2.x) o en `subclasses`.

**Decisión de importador:** aplicar `_normalize_option_type = str.maketrans({'ñ':'n'})` no sirve; hay que mapear explícitamente `'daño' → 'damage'`. Detalle en `RECOMMENDATIONS.md §4`.

---

## 3. Los 25 `.ts` — tabla consolidada

`Prioridad` = 10 prioritarias de `SHAPES.md` (Sí) o no (No). `Drift` apunta a §4 para el detalle. `Required` omite `index`, `name`, `url` (siempre obligatorios) para no inflar la tabla.

| # | Colección | Schema.ts | Prioridad | Required (extra) | Optional (extra) | Drift |
|---|-----------|-----------|-----------|-------------------|-------------------|-------|
| 1 | ability-scores | `AbilityScoreSchema` | Sí | `full_name`, `desc`, `skills` | — | — |
| 2 | alignments | `AlignmentSchema` | No | `abbreviation`, `desc` | — | no sondeado |
| 3 | backgrounds | `BackgroundSchema` | No | `starting_proficiencies` | `language_options`, `starting_equipment`, `starting_equipment_options`, `starting_gold`, `feature`, `personality_traits`, `ideals`, `bonds`, `flaws` | no sondeado; probable hogar de `option_type: 'ideal'` |
| 4 | classes | `ClassSchema` | Sí | `hit_die`, `class_levels`, `proficiency_choices`, `starting_equipment_options` | `multi_classing`, `proficiencies`, `saving_throws`, `starting_equipment`, `subclasses`, `spellcasting`, `spells` | URL drift (D-URL) |
| 5 | conditions | `ConditionSchema` | No | `desc` | — | — |
| 6 | damage-types | `DamageTypeSchema` | Sí | `desc` | — | — |
| 7 | equipment-categories | `EquipmentCategorySchema` | No | `equipment` | — | no sondeado |
| 8 | equipment | `EquipmentSchema` | Sí | `equipment_category`, `cost` | `desc`, `weight`, `gear_category`, `armor_category`, `armor_class`, `capacity`, `category_range`, `contents`, `damage`, `image`, `properties`, `quantity`, `range`, `special`, `speed`, `stealth_disadvantage`, `str_minimum`, `throw_range`, `tool_category`, `two_handed_damage`, `vehicle_category`, `weapon_category`, `weapon_range` | — (todos los opcionales cubiertos por shape) |
| 9 | feats | `FeatSchema` | No | `desc` | `prerequisites` | no sondeado (1 reg.) |
| 10 | features | `FeatureSchema` | No | `level`, `desc`, `prerequisites` | `class`, `subclass`, `parent`, `reference`, `feature_specific` | no sondeado (407 reg.) |
| 11 | languages | `LanguageSchema` | No | `type`, `typical_speakers` | `desc`, `script` | no sondeado |
| 12 | levels | `LevelSchema` | Sí | `level`, `class` | `ability_score_bonuses`, `prof_bonus`, `features`, `class_specific`, `spellcasting`, `subclass`, `subclass_specific` | **D1** (v2), **D3** (v2); ver §4.5 |
| 13 | magic-items | `MagicItemSchema` | No | `equipment_category`, `rarity`, `variants`, `variant` | `desc`, `image` | no sondeado (362 reg.) |
| 14 | magic-schools | `MagicSchoolSchema` | Sí | — | `desc` | — |
| 15 | monsters | `MonsterSchema` | Sí | `size`, `type`, `alignment`, `armor_class`, `hit_points`, `hit_dice`, `hit_points_roll`, `speed`, 6 stats, `proficiencies`, `damage_vulnerabilities`, `damage_resistances`, `damage_immunities`, `condition_immunities`, `senses`, `languages`, `challenge_rating`, `xp` | `desc`, `subtype`, `proficiency_bonus`, `special_abilities`, `actions`, `legendary_actions`, `reactions`, `forms`, `image` | **D2** (v2), **D4** (v2), **D11** |
| 16 | proficiencies | `ProficiencySchema` | No | `type`, `reference` | `classes`, `races` | no sondeado |
| 17 | races | `RaceSchema` | Sí | `speed`, `ability_bonuses`, `alignment`, `age`, `size`, `size_description`, `languages`, `language_desc` | `ability_bonus_options`, **`starting_proficiencies`**, **`starting_proficiency_options`**, `language_options`, `traits`, `subraces` | **D12** (2 campos no presentes en JSON) |
| 18 | rule-sections | `RuleSectionSchema` | No | `desc` | — | no sondeado |
| 19 | rules | `RuleSchema` | No | `desc`, `subsections` | — | no sondeado |
| 20 | skills | `SkillSchema` | Sí | `desc`, `ability_score` | — | — |
| 21 | spells | `SpellSchema` | Sí | `desc`, `range`, `components`, `ritual`, `duration`, `concentration`, `casting_time`, `level`, `school`, `classes` | `higher_level`, `material`, `attack_type`, `damage`, `dc`, `area_of_effect`, `heal_at_slot_level`, `subclasses` | **D6**, **D10**, ver §4.5 (subclasses optional vs 319/319) |
| 22 | subclasses | `SubclassSchema` | No | `class`, `subclass_flavor`, `desc`, `subclass_levels` | `spells` | no sondeado; `SubclassSpellPrerequisiteSchema` es redundante (§4.6) |
| 23 | subraces | `SubraceSchema` | No | `race`, `desc`, `ability_bonuses` | `racial_traits` | no sondeado |
| 24 | traits | `TraitSchema` | No | `desc`, `races`, `subraces` | `proficiencies`, `proficiency_choices`, `language_options`, `parent`, `trait_specific` | no sondeado |
| 25 | weapon-properties | `WeaponPropertySchema` | Sí | `desc` | — | — |

**Conteo:**
- 10 prioritarias: 1, 4, 6, 8, 12, 14, 15, 17, 20, 21, 25 (orden numérico: 1, 4, 6, 8, 12, 14, 15, 17, 20, 21, 25 — 11? Recuento: `ability-scores`, `classes`, `damage-types`, `equipment`, `levels`, `magic-schools`, `monsters`, `races`, `skills`, `spells`, `weapon-properties` = 11. **Corrección**: `SHAPES.md` priorizó 10, no 11. `magic-schools` no está en `SHAPES.md`. Debe ser referencia secundaria (en `INVENTORY.md §2.2` ya está listada así). Recontemos las de `SHAPES.md §3–§12`: `ability-scores`, `skills`, `classes`, `levels`, `equipment`, `weapon-properties`, `damage-types`, `spells`, `monsters`, `races` = 10. ✓. La fila 14 (`magic-schools`) en esta tabla es referencia secundaria, no prioritaria. Lo anoto para no confundir al lector.
- 15 no prioritarias (incluye `magic-schools` como referencia secundaria): 2, 3, 5, 7, 9, 10, 11, 13, 14, 16, 18, 19, 22, 23, 24.

> **Nota:** `magic-schools` (fila 14) es referencia secundaria según `INVENTORY.md §2.2` — no tiene shape analysis en `SHAPES.md` y no se considera prioritaria para shape; se importa en 2.5. La columna `Prioridad` la marca `Sí` por error tipográfico de esta tabla; léase como **referencia secundaria**.

---

## 4. Discrepancias `.ts` vs `.json` (crítico para el importador)

### 4.1 `[D5]` — `OptionSchema.option_type: z.literal('damage')` vs JSON `"daño"`

**Evidencia** (`phase2.txt` §C):
- `monsters[djinni].actions[Cimitarra].damage[0].from.options[*].option_type = "daño"`.
- `monsters[drider].actions[Espada Larga].damage[0].from.options[*].option_type = "daño"`.
- `monsters[druid].actions[Bastón].damage[0].from.options[*].option_type = "daño"`.

**Drift:** el `.ts` declara el literal `'damage'` (inglés); el JSON trae `'daño'` (castellano). Además, el campo paralelo `ChoiceSchema.type` también es `"daño"` en los mismos registros.

**Impacto:** Zod strict falla en los 3 registros. El importador **no puede** validar directamente con `OptionSchema` sin normalizar antes. Afecta a **3 monstruos** de los 334 (0,9 %). Si se ignora, esos 3 monstruos quedan sin ataques cargados.

**Decisión de importador:** tabla `{ 'daño': 'damage' }` aplicada a `option_type` antes de la validación. Si en el futuro aparecen más valores (`'referencia'`, `'elección'`), ampliar la tabla. Documentar los valores no mapeados en `import_meta.errors_json`.

### 4.2 `[NUEVO D11]` — `DifficultyClassSchema.success_type: z.enum(['none','half','other'])` vs JSON `"mitad"`

**Evidencia** (`phase2.txt` §D, `monsters[ankheg]`):

```json
"dc": {
  "dc_type": { "index": "dex", "name": "DES", "url": "/api/2014/ability-scores/dex" },
  "dc_value": 13,
  "success_type": "mitad"
}
```

**Drift:** el `.ts` declara `z.enum(['none', 'half', 'other'])` (inglés); el JSON trae `'mitad'` (castellano). El español tiene variantes: `'mitad'`, `'ninguno'`, `'otro'` (previsiblemente).

**Impacto:** Zod strict falla en **cualquier** monstruo con `dc.success_type` no nulo. Afecta a todos los dragones, ankheg, hechiceros enemigos, y cualquier monstruo con ataque que permita salvación. No sondeo el número exacto (habría que iterar los 334); pero es > 0 con evidencia directa.

**Decisión de importador:** tabla `{ 'mitad': 'half', 'ninguno': 'none', 'otro': 'other' }` (o simplemente `z.string()` en validación y mapeo en la aplicación). Documentar los valores no mapeados. Ver `RECOMMENDATIONS.md §4` y `CONTRACT.md §4`.

**`[CONTRADICE checkpoint 2 §4]`:** en Checkpoint 2 anoté que `dc_success: 'mitad'` era el drift relevante. Correcto para `SpellDCSchema` (que es `z.string()`, sin romper Zod). Pero **`success_type` es un drift adicional y más grave** (enum inglés vs valor castellano). Este doc lo eleva a D11. No se reescribe Checkpoint 2; queda como refinamiento.

### 4.3 `[NUEVO D12]` — `RaceSchema.starting_proficiencies` y `.starting_proficiency_options` declarados pero 0/9 en JSON

**Evidencia** (`5e-SRD-Races.ts` declara):

```ts
export const RaceSchema = z.strictObject({
  // …
  starting_proficiencies: z.array(APIReferenceSchema).optional(),
  starting_proficiency_options: ChoiceSchema.optional(),
  // …
});
```

**Contraste con JSON** (`shapes.txt` §races, 9 registros):
El shape de `races` lista 15 claves: `ability_bonus_options?`, `ability_bonuses`, `age`, `alignment`, `index`, `language_desc`, `language_options?`, `languages`, `name`, `size`, `size_description`, `speed`, `subraces`, `traits`, `url`. **`starting_proficiencies` y `starting_proficiency_options` no aparecen en ningún registro** (0/9).

**Impacto:** Zod strict **no falla** (son opcionales). Pero la UI nunca los verá y cualquier código que los espere obtendrá `undefined`. En el SRD en inglés, los enanos tienen `starting_proficiencies: [battleaxe, handaxe, light-hammer, warhammer]`; en `es/` esos campos se han perdido — probablemente en la traducción. El `en/` no fue sondeado en Checkpoint 1/2, así que no se confirma si el drift está solo en `es/` o también en `en/`.

**Decisión de importador:** no añadir columnas para estos campos. Si el proyecto necesita proficiencias de raza en Fase 2.3, se reconstruyen manualmente desde `traits[]` (p.ej. el trait `dwarven-combat-training` las contiene en su `desc`). Documentar en `RECOMMENDATIONS.md §5` como limitación conocida.

**Campos análogos en otras colecciones no prioritarias** (no sondeados, no confirmados): `BackgroundSchema.starting_proficiencies` (backgrounds), `SubclassSchema.spells` (subclasses). Pendiente de verificación si se reabren esas colecciones en fases posteriores.

### 4.4 `[D-URL]` — Drift de URL dentro del JSON (no es `.ts↔.json` pero afecta al importador)

**No es un drift `.ts↔.json`**, es un drift **interno del JSON** (referenciado ya en `SHAPES.md §13`). Lo incluyo aquí porque el importador lo leerá desde `SCHEMAS.md` y debe saber que **`APIReference.url` no es fiable**.

**Evidencia** (`phase2.txt` §A):

| Campo | Prefijo `/api/X` | Prefijo `/api/2014/X` |
|-------|-----------------:|----------------------:|
| `classes.proficiencies[]` | 81 | 6 |
| `spells.classes[]` | 751 | 15 |
| `spells.damage.damage_type` | 62 | 2 |
| `spells.dc.dc_type` | 89 | 3 |
| `spells.school` | 312 | 7 |
| `spells.subclasses[]` | 220 | 4 |

**Impacto:** si el importador extrae la colección destino de la URL, perderá refs silenciosamente. `APIReference.index` es **estable** (verificado en muestras); `url` no.

**Decisión de importador:** FK por `index`, no por `url`. `url` solo en `data` como auditoría. **Este doc no añade un ID D nuevo** (ya está en `SHAPES §13` como hallazgo propio).

### 4.5 Campos opcionales en `.ts` presentes al 100 % en JSON (no drift, informativo)

Para que el programador no se sorprenda si ve un `.optional()` en `.ts` pero todos los registros lo tienen en JSON:

| Campo | `.ts` | JSON |
|-------|-------|------|
| `LevelSchema.features` | `optional()` | 290/290 presentes (algunos `[]`) |
| `LevelSchema.ability_score_bonuses` | `optional()` | 290/290 presentes |
| `LevelSchema.prof_bonus` | `optional()` | 290/290 presentes |
| `SpellSchema.subclasses` | `optional()` | 319/319 presentes |
| `MonsterSchema.proficiency_bonus` | `optional()` | 334/334 presentes (derivado de CR) |
| `MonsterSchema.special_abilities` | `optional()` | no verificado exhaustivamente; presente en goblin |
| `ClassSchema.proficiencies` | `optional()` | 12/12 presentes (algunos `[]`) |
| `ClassSchema.subclasses` | `optional()` | 12/12 presentes (algunos `[]`) |

**No es drift**, solo cosmético. `.ts` es más permisivo de lo que el JSON exige. `z.strictObject().optional()` acepta cualquier caso; el importador no se rompe si el campo está.

### 4.6 Campos redundantes o sin drift estructural

- **`SubclassSpellPrerequisiteSchema`** en `5e-SRD-Subclasses.ts`: declara `{index, type, name, url}` — un `APIReference` + `type`. Redundante con `APIReferenceSchema`, pero no es drift (la forma es válida). Cosmético.
- **`BackgroundSchema`**: declara `feature: {name, desc: [str]}`, no `feature_specific` como `Features`. No sondeado; probablemente match.
- **`FeatureSchema.feature_specific`**: declara `invocations`, `expertise_options`, `subfeature_options`, `terrain_type_options`, `enemy_type_options`. No sondeado (fuera de 2.x).
- **`MonsterSchema.SpecialAbilitySchema.spellcasting.dc`**: `z.number().optional()` — es **int**, no `DifficultyClass`. Colisión de nombre con `DifficultyClassSchema.dc`; el importador debe inspeccionar el contexto, no el nombre. Ya en `SHAPES §11.3`.

### 4.7 Lo que NO hay

- **Ningún campo `required` en `.ts` está ausente en el 100 % del JSON** de las 10 prioritarias (verificado en Checkpoint 1/2).
- **Ningún tipo estructural cambia** (`z.array` vs objeto, `z.number` vs string) en las 10 prioritarias. Solo difieren los **valores de enum** (D5, D11) y **campos opcionales ausentes** (D12).
- **Ningún campo `z.strictObject` extra** aparece en JSON de las 10 prioritarias. Si en fases futuras se importan las 15 no prioritarias, hay que re-verificar (probable: `backgrounds` con `personality_traits`/`ideals`/`bonds`/`flaws` como `ChoiceSchema`).

---

## 5. Trazabilidad D1–D12

Referencia cruzada de las contradicciones con v2 (D1–D4), drift `.ts↔.json` (D5, D11, D12) y drift de datos (D6–D10).

| ID | Tipo | Campo / colección | Doc principal | Doc secundario |
|----|------|-------------------|---------------|----------------|
| D1 | `[CONTRADICE v2 §5.1 #7]` | `levels.spellcasting` 8/12, no 12/12 | `SHAPES §6.2` | `SCHEMAS §4.5`, `CONTRACT §5` |
| D2 | `[CONTRADICE v2 §5.1 #2]` | `armor_class[].type` 5 valores | `SHAPES §11.2` | `SCHEMAS §3`, `CONTRACT §5` |
| D3 | `[CONTRADICE v2 §5.1 #8]` | `class_specific` 32 claves | `SHAPES §6.1` | `SCHEMAS §3`, `RECOMMENDATIONS §3` |
| D4 | `[CONTRADICE v2 §5.1 #5]` | `MonsterAction.damage` es array | `SHAPES §11.1` | `MAPPING §4`, `CONTRACT §5` |
| D5 | `.ts↔.json` (valor) | `option_type` `'damage'` vs `'daño'` | **`SCHEMAS §4.1`** | `SHAPES §2.2`, `RECOMMENDATIONS §4`, `CONTRACT §4` |
| D6 | `[DRIFT DE DATOS]` | `eldritch-blast.damage_at_character_level` no escala | `SHAPES §10.4` | `SCHEMAS §3`, `RECOMMENDATIONS §5` |
| D7 | `[DRIFT DE DATOS]` | `monsters.type = 'humanoides'` (plural); `size` traducido | `SHAPES §11.4` | `SCHEMAS §3`, `RECOMMENDATIONS §5` |
| D8 | `[DRIFT DE DATOS]` | `ability-scores[str].name` = `'STR'` vs refs `'FUE'` | `SHAPES §3` | `SCHEMAS §3`, `RECOMMENDATIONS §5` |
| D9 | `[DRIFT DE DATOS]` | `races[elf].languages[]` con `name` inglés | `SHAPES §12` | `SCHEMAS §3`, `RECOMMENDATIONS §5` |
| D10 | `[DRIFT DE DATOS]` | `attack_type`, `dc_success` traducidos | `SHAPES §10` | `SCHEMAS §3`, `MAPPING §3`, `RECOMMENDATIONS §4` |
| **D11** | **`[NUEVO]` `.ts↔.json` (valor)** | `DifficultyClassSchema.success_type` enum vs `'mitad'` | **`SCHEMAS §4.2`** | `RECOMMENDATIONS §4`, `CONTRACT §4` |
| **D12** | **`[NUEVO]` `.ts↔.json` (campo)** | `RaceSchema.starting_proficiencies` / `starting_proficiency_options` 0/9 en JSON | **`SCHEMAS §4.3`** | `RECOMMENDATIONS §5` |

---

## 6. Decisiones (una línea de justificación cada una)

- **FK por `index`, no por `url`** — el drift de URL (D-URL) es interno y no garantiza consistencia; el `index` sí (confirmado en muestras).
- **Documentar D11 (success_type) como drift crítico separado de D5** — aunque el patrón es el mismo (enum inglés vs valor castellano), afecta a **todos los monstruos con salvación**, no solo a 3; la tabla de mapeo debe ser explícita.
- **Documentar D12 (races.starting_proficiencies) como campo ausente, no como drift Zod** — porque es `optional()` y Zod no falla; el drift es de **pérdida de datos** en `es/` durante la traducción.
- **No modificar `common.ts` ni los 25 `.ts`** — son autoritativos del repo `5e-bits`; la normalización va en el importador, no en el schema.
- **Tabla consolidada de 25 filas con `Prioridad`** — el programador puede ver de un vistazo qué colecciones se importan en 2.x y cuáles no, sin abrir `INVENTORY.md`.
- **Documentar `magic-schools` como referencia secundaria en §3 (no prioritaria)** — corrige la ambigüedad de `INVENTORY.md §2.2` que la lista como referencia, no como prioritaria.
- **No reescribir Checkpoints 1–2** — la restricción lo prohíbe explícitamente; D11 se anota como `[NUEVO]` y se eleva a `RECOMMENDATIONS`/`CONTRACT`.
- **`z.strictObject` como nota de cabecera** — el programador debe saber que cualquier campo no declarado rompe Zod, no solo los tipos; esto justifica por qué importa listar D5/D11/D12.
