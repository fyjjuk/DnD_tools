# SHAPES.md — Estructura real de las 10 colecciones prioritarias SRD 5e (2014) en español

**Proyecto:** DnD_tools · Fase 2.2–2.5
**Fuente primaria:** `/home/fyjjuk/DnD/raw/srd-2014/es/*.json` (volcado literal, parseado con Python stdlib).
**Fuente normativa:** `/home/fyjjuk/DnD/raw/srd-2014/schemas/*.ts` y `/home/fyjjuk/DnD/raw/schemas/common.ts` (autoritativos para tipos).
**Sondas:** `_probe_shapes.py` (salida `shapes.txt`), `_probe_phase2.py` (salida `phase2.txt`).
**Baseline:** `PRIOR_REPORT_v2.md` — se cita por `§`, no se repite.

## 0. Notación

- `campo: tipo` — campo obligatorio (siempre presente en todos los registros).
- `campo?: tipo` — campo opcional (puede faltar; el `.ts` lo marca `optional()`).
- `campo: tipo | null` — campo presente pero puede venir con valor JSON `null` (no confundir con `?`).
- `ref(X)` — `APIReference` cuya URL apunta a la colección `X`. Forma: `{index: str, name: str, url: str, note?: str}`.
- `[tipo]` — array de `tipo`. `[]` vacío es válido.
- `{k: v, …}` — objeto (shape inline).
- `{str: str}` — record JSON (claves string arbitrarias).
- Las variantes de una unión se listan como `branch1 | branch2`.
- Los ejemplos de datos reales se transcriben textualmente del `es/` (fragmentos recortados a ~120 chars).

**Correcciones al `PRIOR_REPORT_v2.md`** (trazabilidad completa en §13):
- `[CONTRADICE v2 §5.1 #2]` — `armor_class[].type` tiene 5 valores, no 4.
- `[CONTRADICE v2 §5.1 #7]` — `levels.spellcasting` está en 8/12 clases, no en 12/12.
- `[CONTRADICE v2 §5.1 #8]` — `class_specific` tiene 32 claves, no 33.
- `[CONTRADICE v2 §5.1 #5]` — `MonsterAction.damage` es `Array<Damage | Choice>`, no `Damage | Choice`.

---

## 1. Tipos comunes (`common.ts`)

Usados por casi todas las colecciones. Se definen aquí y se referencian por nombre en cada shape.

```text
APIReference:
  index: str
  name: str
  url: str
  note?: str

DifficultyClass:
  dc_type: ref(ability-scores)
  dc_value?: int
  success_type: 'none' | 'half' | 'other'    # en el JSON de es/ viene traducido ('mitad', …)

DamageSchema:
  damage_type: ref(damage-types)
  damage_dice: str                             # '1d8', '2d6+5', …
  dc?: DifficultyClass

AreaOfEffectSchema:
  size: int
  type: 'sphere' | 'cube' | 'cylinder' | 'line' | 'cone'
```

**Verificación contra datos reales** (phase2.txt):
- `DamageSchema` aparece en `monsters.actions[].damage[]` y `equipment.damage` — siempre con `damage_type` + `damage_dice`, con `dc` solo en variantes con salvación.
- `DifficultyClass` aparece en `monsters.actions[].dc`, `monsters.actions[].damage[].dc`, `monsters.attacks[].dc`, `monsters.legendary_actions[].dc`, `monsters.reactions[].dc`, `monsters.special_abilities[].dc`, `monsters.special_abilities[].spellcasting` (comparte `dc` como int en ese caso, ver §10) y `spells.dc`.
- `AreaOfEffectSchema` aparece en `spells.area_of_effect` con `{type: 'sphere', size: 20}` (fireball).
- `APIReference.note` **no apareció** en ningún registro de las 10 prioritarias. Es opcional y queda para futuros datasets.

---

## 2. ChoiceSchema + OptionSchema (los polimórficos de `common.ts`)

Son la estructura más compleja del SRD. Aparecen en `classes.*_choices`, `classes.starting_equipment_options`, `races.ability_bonus_options`, `races.language_options`, `races.starting_proficiency_options`, `monsters.actions[].action_options`, `monsters.actions[].options`, `monsters.actions[].damage[].from`.

```text
ChoiceSchema:
  desc?: str
  choose: int
  type?: str                                # 'proficiencies', 'equipment', 'languages', 'damage', …
  from: OptionSetSchema
```

### 2.1 `OptionSetSchema` — 3 ramas declaradas en `common.ts`

Sondeadas en las 10 prioritarias: **solo 2 ramas presentes**. `resource_list` está declarada pero no apareció (probablemente en `backgrounds`, fuera de scope Fase 2.x).

```text
OptionSetSchema:
  | { option_set_type: 'options_array', options: [OptionSchema | str] }
  | { option_set_type: 'equipment_category', equipment_category: ref(equipment-categories) }
  | { option_set_type: 'resource_list', resource_list_url: str }   # declarada, 0 ocurrencias en 2.x
```

**Ejemplos reales** (phase2.txt §B):

```json
// options_array (128 ocurrencias) — primera: classes[0].proficiency_choices[].from
{
  "option_set_type": "options_array",
  "options": [
    { "option_type": "reference",
      "item": { "index": "skill-animal-handling",
                "name": "Habilidad: Trato con Animales",
                "url": "/api/proficiencies/skill-animal-handling" } },
    // …(7 more)
  ]
}

// equipment_category (23 ocurrencias) — primera: classes[0].starting_equipment_options[].from.options[].choice.from
{
  "option_set_type": "equipment_category",
  "equipment_category": {
    "index": "martial-melee-weapons",
    "name": "Arma cuerpo a cuerpo marcial",
    "url": "/api/equipment-categories/martial-melee-weapons"
  }
}
```

### 2.2 `OptionSchema` — 13 ramas declaradas en `common.ts`

Sondeadas en las 10 prioritarias: aparecen al menos `reference`, `choice`, `counted_reference`, `multiple`, `damage`, `score_prerequisite`, `ability_bonus`. Las demás (`string`, `action`, `breath`, `ideal`, `money`, `size`) están declaradas y no se descartan (probablemente en `backgrounds`, `traits` o `monsters.actions[].action_options`).

```text
OptionSchema:
  | { option_type: 'reference',          item: APIReference }
  | { option_type: 'choice',             choice: ChoiceSchema }
  | { option_type: 'string',             string: str }
  | { option_type: 'ability_bonus',      ability_score: ref(ability-scores), bonus: int }
  | { option_type: 'action',             action_name: str, count: int, type: str, desc?: str }
  | { option_type: 'breath',             name: str, dc: DifficultyClass, damage?: [DamageSchema] }
  | { option_type: 'counted_reference',  count: int, of: APIReference,
                                         prerequisites?: [{type: str, proficiency?: APIReference}] }
  | { option_type: 'damage',             damage_dice: str, damage_type: ref(damage-types), notes?: str }
  | { option_type: 'ideal',              alignments: [APIReference], desc: str }
  | { option_type: 'money',              count: int, unit: str }
  | { option_type: 'multiple',           items: [OptionSchema], desc?: str }
  | { option_type: 'score_prerequisite', ability_score: ref(ability-scores), minimum_score: int }
  | { option_type: 'size',               size: str }
```

**`[DRIFT DE DATOS, D5]`** — En el dataset `es/`, el `option_type` de la rama `damage` viene como **`"daño"`** (español), no `"damage"`. Ejemplos: `monsters[djinni].actions[Cimitarra]`, `monsters[drider].actions[Espada Larga]`, `monsters[druid].actions[Bastón]`. El importador debe normalizar `"daño"` → `"damage"`. Detalle en `SCHEMAS.md §4` y `RECOMMENDATIONS.md §4`.

**`[DRIFT DE DATOS, D5]` (variante)** — El campo `ChoiceSchema.type` (no el `option_type`) viene en español cuando describe el tipo de elección: `"daño"`, `"equipo"`, etc. Solo `type` es descriptivo; el importador no debe usarlo como enum.

---

## 3. `ability-scores`

**Registros:** 6 · **Fase:** 2.3 · **Tipo:** referencia

```text
ability-scores:
  index: str                                 # 'str', 'dex', 'con', 'int', 'wis', 'cha'
  name: str                                  # 'STR', 'DEX', … (abreviatura)
  full_name: str                             # 'Fuerza', 'Destreza', …
  desc: [str]
  skills: [ref(skills)]                      # habilidades asociadas a esta característica
  url: str
```

**Registro real** (phase2.txt §D, `ability-scores[str]`):

```json
{
  "index": "str",
  "name": "STR",
  "full_name": "Fuerza",
  "desc": ["La Fuerza mide el poder físico, el entrenamiento atlético y la capacidad de ejercer fuerza bruta.", "…"],
  "skills": [ { "name": "Atletismo", "index": "athletics", "url": "/api/skills/athletics" } ],
  "url": "/api/2014/ability-scores/str"
}
```

**`[DRIFT DE DATOS, D8]`** — `name: "STR"` (abreviatura inglesa) vs `skills.athletics.ability_score.name: "FUE"` (castellano). El `index` es estable (`str`); usar `index` para FK y para joins, no `name`.

**Uso en Fase 2.3/2.4** — modificador = `floor((score - 10) / 2)`. El proyecto calcula el modificador en el jugador; el SRD solo aporta el `index` y el `full_name` para UI. La tabla `skills` es la que mapea `ability_score` → habilidad.

---

## 4. `skills`

**Registros:** 18 · **Fase:** 2.3 · **Tipo:** referencia

```text
skills:
  index: str                                 # 'athletics', 'acrobatics', …
  name: str                                  # 'Atletismo', …
  desc: [str]
  ability_score: ref(ability-scores)         # característica asociada
  url: str
```

**Registro real** (phase2.txt §D, `skills[athletics]`):

```json
{
  "index": "athletics",
  "name": "Atletismo",
  "desc": ["Tu prueba de Fuerza (Atletismo) cubre situaciones difíciles que encuentras mientras escalas, saltas o nadas."],
  "ability_score": { "index": "str", "name": "FUE", "url": "/api/2014/ability-scores/str" },
  "url": "/api/2014/skills/athletics"
}
```

**Uso en Fase 2.3/2.4** — mapa `skill.index → ability_score.index`. La ficha del jugador marca competencias (`proficiencies[]` de `classes` + `backgrounds`), y las tiradas de habilidad se calculan sobre la característica correspondiente.

---

## 5. `classes`

**Registros:** 12 · **Fase:** 2.3 · **Tipo:** entidad

La colección más anidada después de `monsters`. `ChoiceSchema` recursivo en `starting_equipment_options` (una opción puede ser otra `choice`).

```text
classes:
  index: str                                 # 'fighter', 'wizard', …
  name: str                                  # 'Guerrero', 'Mago', …
  hit_die: int                               # 6, 8, 10, 12
  class_levels: str                          # '/api/classes/fighter/levels'  (NO es APIReference)
  proficiencies?: [ref(proficiencies)]       # competencias iniciales (armaduras, armas, herramientas)
  proficiency_choices: [ChoiceSchema]        # elecciones de competencia (2 habilidades de una lista)
  saving_throws?: [ref(ability-scores)]      # características con salvación competente
  starting_equipment?: [{equipment: ref(equipment), quantity: int}]
  starting_equipment_options: [ChoiceSchema]
  subclasses?: [ref(subclasses)]
  spellcasting?: {
    level: int                               # nivel al que empieza el spellcasting (1 para mago/clérigo)
    spellcasting_ability: ref(ability-scores)  # 'int', 'wis', 'cha'
    info: [{name: str, desc: [str]}]        # texto narrativo, solo UI
  }
  spells?: str                               # '/api/classes/wizard/spells'  (URL, no APIReference)
  multi_classing?: {
    prerequisites?: [{ability_score: ref(ability-scores), minimum_score: int}]
    prerequisite_options?: ChoiceSchema      # opción alternativa (e.g. STR o DEX >= 13)
    proficiencies?: [ref(proficiencies)]
    proficiency_choices?: [ChoiceSchema]
  }
  url: str
```

**Campos clave para Fase 2.3:**
- `hit_die` → `character.hit_die` en la ficha (dado de golpe).
- `saving_throws[]` → competencia en salvaciones (una de las tres fuentes de `proficient`).
- `spellcasting.spellcasting_ability.index` → `'int'`/`'wis'`/`'cha'` para calcular CD y ataque de conjuro.
- `proficiencies[]` → competencia con armas (simple/martial) y armaduras.

**Ejemplo de referencia** (phase2.txt §D, `classes[fighter]`, recortado):

```json
{
  "index": "fighter",
  "name": "Guerrero",
  "hit_die": 10,
  "class_levels": "/api/classes/fighter/levels",
  "proficiencies": [
    { "index": "all-armor",       "name": "Todas las armaduras", "url": "/api/proficiencies/all-armor" },
    { "index": "shields",         "name": "Escudos",            "url": "/api/proficiencies/shields" },
    { "index": "simple-weapons",  "name": "Armas sencillas",   "url": "/api/proficiencies/simple-weapons" },
    { "index": "martial-weapons", "name": "Armas marciales",  "url": "/api/proficiencies/martial-weapons" }
  ],
  "saving_throws": [
    { "index": "str", "name": "FUE", "url": "/api/ability-scores/str" },
    { "index": "con", "name": "CON", "url": "/api/ability-scores/con" }
  ],
  "starting_equipment": [],
  "starting_equipment_options": [ /* ChoiceSchema anidado, ver §2 */ ],
  "subclasses": [ { "index": "champion", "name": "Campeón", "url": "/api/subclasses/champion" } ],
  "url": "/api/2014/classes/fighter"
}
```

**`[DRIFT DE DATOS, D9]`** — Algunas refs mezclan `/api/X` y `/api/2014/X` (ver §12). El `index` es estable; usar `index` para FK.

---

## 6. `levels`

**Registros:** 290 · **Fase:** 2.3 (consumido también por 2.5) · **Tipo:** entidad

Tabla de progresión por clase. Cada registro es `{clase, nivel}`: `fighter-1`, `fighter-2`, …, `wizard-20`.

```text
levels:
  index: str                                 # 'fighter-1', 'wizard-5', …
  level: int                                 # 1..20
  ability_score_bonuses?: int                # +2, +4, … (a niveles 4, 8, 12, 16, 19)
  prof_bonus?: int                           # +2 a +6
  features?: [ref(features)]                 # refs a 'features' (no importada en 2.x, quedan en data)
  class: ref(classes)
  subclass?: ref(subclasses)
  class_specific?: ClassSpecificSchema       # 32 claves, todas opcionales — ver §6.1
  subclass_specific?: {
    additional_magical_secrets_max_lvl?: int
    aura_range?: int
  }
  spellcasting?: LevelSpellcastingSchema     # 11 claves, presente solo en clases lanzadoras — ver §6.2
  url: str
```

### 6.1 `class_specific` — 32 claves (todas opcionales)

**`[CONTRADICE v2 §5.1 #8]`** — v2 reportó «33 claves». El sondeo cuenta **32** y coinciden 1:1 con `ClassSpecificSchema` de `5e-SRD-Levels.ts`. La 33ª no existe ni en `.ts` ni en JSON.

```text
ClassSpecificSchema:
  action_surges?: int
  arcane_recovery_levels?: int
  aura_range?: int
  bardic_inspiration_die?: int
  brutal_critical_dice?: int
  channel_divinity_charges?: int
  creating_spell_slots?: [{sorcery_point_cost: int, spell_slot_level: int}]
  destroy_undead_cr?: float | int            # fraccionario o entero
  extra_attacks?: int
  favored_enemies?: int
  favored_terrain?: int
  indomitable_uses?: int
  invocations_known?: int
  ki_points?: int
  magical_secrets_max_5?: int
  magical_secrets_max_7?: int
  magical_secrets_max_9?: int
  martial_arts?: {dice_count: int, dice_value: int}
  metamagic_known?: int
  mystic_arcanum_level_6?: int
  mystic_arcanum_level_7?: int
  mystic_arcanum_level_8?: int
  mystic_arcanum_level_9?: int
  rage_count?: int
  rage_damage_bonus?: int
  sneak_attack?: {dice_count: int, dice_value: int}
  song_of_rest_die?: int
  sorcery_points?: int
  unarmored_movement?: int
  wild_shape_fly?: bool
  wild_shape_max_cr?: float | int
  wild_shape_swim?: bool
```

**Cobertura:** 240/290 registros tienen `class_specific` no vacío. Cada clave aparece en 20/290 registros exactos (los 20 niveles de la clase que la usa). Ninguna clave es required.

**Ejemplo real** (phase2.txt §D, `levels[fighter-20]`):

```json
"class_specific": {
  "action_surges": 2,
  "indomitable_uses": 3,
  "extra_attacks": 3
}
```

### 6.2 `spellcasting` — 11 claves

**`[CONTRADICE v2 §5.1 #7]`** — v2 dice «presente en las 12 clases, slots 0 en no-lanzadoras, no hay nulls». **Falso.** El sondeo cuenta 160/290 registros con `spellcasting` no vacío, y las clases marciales (fighter, barbarian, monk, rogue) **no tienen la clave**: `levels[fighter-1]` no incluye `spellcasting`. Cuando la clave está presente, `spell_slots_level_1..5` son required y `6..9` opcionales.

```text
LevelSpellcastingSchema:
  cantrips_known?: int
  spell_slots_level_1: int                   # required cuando spellcasting existe
  spell_slots_level_2: int                   # required cuando spellcasting existe
  spell_slots_level_3: int                   # required cuando spellcasting existe
  spell_slots_level_4: int                   # required cuando spellcasting existe
  spell_slots_level_5: int                   # required cuando spellcasting existe
  spell_slots_level_6?: int                  # opcional (full casters llegan a 9)
  spell_slots_level_7?: int
  spell_slots_level_8?: int
  spell_slots_level_9?: int
  spells_known?: int                         # opcional (conocidos, no preparados — solo bardo/hechicero/brujo)
```

**Cobertura por clave** (probe 1, 290 registros totales):
- `spell_slots_level_1..5`: 160/290 (todas las clases que castean).
- `spell_slots_level_6..9`: 120/290 (solo full casters).
- `cantrips_known`: 120/290.
- `spells_known`: 80/290 (bard, sorcerer, warlock, ranger — no wizard/cleric/druid).

**Ejemplo real** (phase2.txt §D, `levels[wizard-5]`):

```json
"spellcasting": {
  "cantrips_known": 4,
  "spell_slots_level_1": 4,
  "spell_slots_level_2": 3,
  "spell_slots_level_3": 2,
  "spell_slots_level_4": 0,
  "spell_slots_level_5": 0,
  "spell_slots_level_6": 0,
  "spell_slots_level_7": 0,
  "spell_slots_level_8": 0,
  "spell_slots_level_9": 0
}
```

**Uso en Fase 2.5** — el listado de slots disponibles por nivel del PJ se obtiene por `(class_slug, level)` de esta tabla. Los slots a 0 son válidos y significan «no disponible a este nivel». `NULL` significa «esta clase no castea a este nivel» (todavía no ha llegado a nivel de spellcasting) — la UI debe distinguir 0 de `NULL`.

**Uso en Fase 2.3** — `prof_bonus` (nivel) → modificador de ataque/DC. `ability_score_bonuses` → a niveles 4/8/12/16/19 el PJ sube +2 a una característica.

---

## 7. `equipment`

**Registros:** 237 · **Fase:** 2.3 · **Tipo:** entidad

Cubre armas, armaduras, herramientas, vehículos, monturas, paquetes. El discriminante es `equipment_category.index` (`weapon`, `armor`, `tool`, `mount`, `vehicle`, `gear`, `pack`…).

```text
equipment:
  index: str                                 # 'longsword', 'leather-armor', …
  name: str                                  # 'Espada larga', …
  equipment_category: ref(equipment-categories)
  cost: {quantity: int, unit: str}           # unit ∈ {'po','pe','pc'} — ver §7.1
  weight?: float | int
  desc?: [str]
  image?: str
  weapon_category?: str                      # 'Simple' | 'Marcial'
  weapon_range?: str                         # 'Cuerpo a cuerpo' | 'A distancia'
  category_range?: str                       # 'Marcial cuerpo a cuerpo', etc.
  damage?: DamageSchema                      # solo armas
  two_handed_damage?: DamageSchema           # solo armas versátiles
  range?: {normal: int, long?: int}          # alcance de arma a distancia
  throw_range?: {normal: int, long: int}     # solo armas arrojadizas
  properties?: [ref(weapon-properties)]      # 'versatile', 'finesse', 'two-handed', 'reach', …
  armor_category?: str                       # 'Ligera' | 'Media' | 'Pesada' | 'Escudo'
  armor_class?: {base: int, dex_bonus: bool, max_bonus?: int}
  str_minimum?: int                          # 13 o 15 para armaduras pesadas
  stealth_disadvantage?: bool
  capacity?: str                             # vehículos/monturas
  contents?: [{item: ref(equipment), quantity: int}]  # paquetes
  gear_category?: ref(equipment-categories)
  quantity?: int
  special?: [str]
  speed?: {quantity: float | int, unit: str} # vehículos
  tool_category?: str
  vehicle_category?: str
  url: str
```

### 7.1 `cost.unit` — 3 valores reales

El `.ts` declara `unit: z.string()` (no enum). El sondeo cuenta los valores reales en `es/`:

| `unit` (es) | Equivalente en (en) | Ocurrencias |
|-------------|---------------------|-------------|
| `po` (pieza de oro) | `gp` | 190 |
| `pe` (pieza de electro) | `sp` | 23 |
| `pc` (pieza de cobre) | `cp` | 24 |

**Mapeo obligatorio en importador:** `po → gp`, `pe → sp`, `pc → cp`. Guardar también `cost_unit_raw` con el valor original para auditoría (ver `CONTRACT.md §4`).

### 7.2 Ejemplo real: arma (`longsword`)

```json
{
  "index": "longsword",
  "name": "Espada larga",
  "equipment_category": { "index": "weapon", "name": "Arma", "url": "/api/2014/equipment-categories/weapon" },
  "weapon_category": "Marcial",
  "weapon_range": "Cuerpo a cuerpo",
  "category_range": "Marcial cuerpo a cuerpo",
  "cost": { "quantity": 15, "unit": "po" },
  "damage": {
    "damage_dice": "1d8",
    "damage_type": { "index": "slashing", "name": "Cortante", "url": "/api/2014/damage-types/slashing" }
  },
  "range": { "normal": 5 },
  "weight": 3,
  "properties": [
    { "index": "versatile", "name": "Versátil", "url": "/api/2014/weapon-properties/versatile" }
  ],
  "two_handed_damage": {
    "damage_dice": "1d10",
    "damage_type": { "index": "slashing", "name": "Cortante", "url": "/api/2014/damage-types/slashing" }
  },
  "url": "/api/2014/equipment/longsword"
}
```

### 7.3 Ejemplo real: armadura (`leather-armor`)

```json
{
  "index": "leather-armor",
  "name": "Armadura de cuero",
  "equipment_category": { "index": "armor", "name": "Armadura", "url": "/api/2014/equipment-categories/armor" },
  "armor_category": "Ligera",
  "armor_class": { "base": 11, "dex_bonus": true },
  "str_minimum": 0,
  "stealth_disadvantage": false,
  "weight": 10,
  "cost": { "quantity": 10, "unit": "po" },
  "url": "/api/2014/equipment/leather-armor"
}
```

**Uso en Fase 2.4** — tirada de ataque con arma: `attack_bonus = str_mod | dex_mod (según finesse) + prof_bonus`, `damage_dice = damage.damage_dice` (o `two_handed_damage.damage_dice` si empuña a dos manos), `damage_type = damage.damage_type.index`. Ver `MAPPING.md §3`.

**Uso en Fase 2.3** — `armor_class` calcula CA; `properties` marca `finesse` (permite DEX en lugar de STR) y `versatile` (elegir entre `damage` y `two_handed_damage`).

---

## 8. `weapon-properties`

**Registros:** 11 · **Fase:** 2.3 · **Tipo:** referencia

```text
weapon-properties:
  index: str                                 # 'versatile', 'finesse', 'two-handed', 'reach', …
  name: str                                  # 'Versátil', …
  desc: [str]
  url: str
```

**Registro real** (phase2.txt §D, `weapon-properties[versatile]`):

```json
{
  "index": "versatile",
  "name": "Versátil",
  "desc": ["Esta arma se puede usar con una o dos manos. …"],
  "url": "/api/2014/weapon-properties/versatile"
}
```

**Los 11 `index` reales** (del fichero; no transcritos aquí por brevedad): `ammunition`, `finesse`, `heavy`, `light`, `loading`, `range`, `reach`, `special`, `thrown`, `two-handed`, `versatile`.

**Uso en Fase 2.4** — `finesse` cambia el modificador de ataque (STR → DEX); `two-handed` fuerza `two_handed_damage`; `reach` afecta al rango de ataque (fuera del scope mínimo de combate del MVP, pero se documenta).

---

## 9. `damage-types`

**Registros:** 13 · **Fase:** 2.3 · **Tipo:** referencia

```text
damage-types:
  index: str                                 # 'slashing', 'piercing', 'bludgeoning', 'fire', 'cold', …
  name: str                                  # 'Cortante', 'Perforante', …
  desc: [str]
  url: str
```

**Uso:** resolver `equipment.damage.damage_type` y `monsters.actions[].damage[].damage_type`. Sin esta tabla, la UI mostraría `slashing` en vez de `Cortante`.

---

## 10. `spells`

**Registros:** 319 · **Fase:** 2.5 · **Tipo:** entidad

```text
spells:
  index: str                                 # 'fireball', …
  name: str                                  # 'Bola de Fuego', …
  desc: [str]
  higher_level?: [str]
  range: str                                 # '150 pies', 'Toque', …
  components: [str]                          # ['V','S','M']
  material?: str
  ritual: bool
  duration: str                              # 'Instantáneo', '1 minuto', …
  concentration: bool
  casting_time: str                          # '1 acción', '1 acción adicional', …
  level: int                                 # 0 = truco (cantrip)
  attack_type?: str                          # 'a distancia' | 'cuerpo a cuerpo'  [DRIFT D10]
  damage?: {
    damage_type?: ref(damage-types)
    damage_at_slot_level?: {str: str}        # {'3':'8d6','4':'9d6',…} claves str no int
    damage_at_character_level?: {str: str}   # {'1':'1d10','5':'2d10',…}
  }
  dc?: {
    dc_type: ref(ability-scores)
    dc_success: str                          # 'mitad', 'ninguno'  [DRIFT D10]
    desc?: str
  }
  area_of_effect?: AreaOfEffectSchema
  heal_at_slot_level?: {str: str}            # {'1':'1d8 + APT', …}
  school: ref(magic-schools)
  classes: [ref(classes)]
  subclasses?: [ref(subclasses)]
  url: str
```

### 10.1 `damage_at_slot_level` y `damage_at_character_level` — records con claves string

En el `.ts`: `z.record(z.string(), z.string())`. El JSON los serializa como objeto. **Las claves son strings numéricos** (`"3"`, no `3`). El importador puede dejarlos como TEXT (JSON) o normalizar a columnas por nivel; el MVP de Fase 2.5 solo necesita `damage_at_slot_level`.

### 10.2 Ejemplo real: `fireball` (daño por slot)

```json
{
  "index": "fireball",
  "name": "Bola de Fuego",
  "level": 3,
  "school": { "index": "evocation", "name": "Evocación", "url": "/api/magic-schools/evocation" },
  "damage": {
    "damage_type": { "index": "fire", "name": "Fuego", "url": "/api/damage-types/fire" },
    "damage_at_slot_level": {
      "3": "8d6", "4": "9d6", "5": "10d6", "6": "11d6",
      "7": "12d6", "8": "13d6", "9": "14d6"
    }
  },
  "dc": {
    "dc_type": { "index": "dex", "name": "DEX", "url": "/api/ability-scores/dex" },
    "dc_success": "mitad"
  },
  "area_of_effect": { "type": "sphere", "size": 20 },
  "url": "/api/2014/spells/fireball"
}
```

### 10.3 Ejemplo real: `cure-wounds` (curación, sin `damage`)

```json
{
  "index": "cure-wounds",
  "name": "Curar Heridas",
  "level": 1,
  "heal_at_slot_level": {
    "1": "1d8 + APT", "2": "2d8 + APT", "3": "3d8 + APT",
    "4": "4d8 + APT", "5": "5d8 + APT", "6": "6d8 + APT",
    "7": "7d8 + APT", "8": "8d8 + APT", "9": "9d8 + APT"
  },
  "url": "/api/2014/spells/cure-wounds"
}
```

### 10.4 Ejemplo real: `eldritch-blast` (truco, `damage_at_character_level`) — con **drift de datos**

```json
{
  "index": "eldritch-blast",
  "name": "Descarga Sobrenatural",
  "level": 0,
  "attack_type": "a distancia",
  "damage": {
    "damage_type": { "index": "force", "name": "Fuerza", "url": "/api/damage-types/force" },
    "damage_at_character_level": { "1": "1d10", "5": "1d10", "11": "1d10", "17": "1d10" }
  },
  "url": "/api/2014/spells/eldritch-blast"
}
```

**`[DRIFT DE DATOS, D6]`** — Según el SRD 5e (en inglés), `eldritch-blast` escala `1d10` → `2d10` → `3d10` → `4d10` a niveles 5/11/17. El dataset `es/` tiene `1d10` en las 4 claves — **bug del dataset**. El importador debe (a) preservar el dato tal cual viene y (b) anotar en `import_meta.errors_json` la incoherencia, para que el DM sepa que el cálculo de daño del brujo es aproximado. Detalle en `SCHEMAS.md §4` y `RECOMMENDATIONS.md §5`.

**`[DRIFT DE DATOS, D10]`** — `attack_type` viene traducido (`'a distancia'`, `'cuerpo a cuerpo'`). El `.ts` declara `z.string()`; el importador debe normalizar a un enum inglés si va a usarlo como discriminante. Igual para `dc_success: 'mitad'`.

**Uso en Fase 2.5** — el PJ conoce N conjuros. La ficha necesita: `level`, `school`, `damage.damage_type`, `damage.damage_at_slot_level`, `dc.dc_type`, `concentration`, `ritual`. El texto `desc` es solo UI. La lista de clases a la que pertenece el conjuro ya se filtra por `classes[]`.

---

## 11. `monsters`

**Registros:** 334 · **Fase:** 2.2 · **Tipo:** entidad

La colección más anidada. Incluye `actions`, `special_abilities`, `legendary_actions`, `reactions` con sub-estructuras polimórficas.

```text
monsters:
  index: str
  name: str
  desc?: str
  size: str                                  # 'Pequeño', 'Mediano', 'Grande', …  (traducido)
  type: str                                  # 'humanoides', 'monstruosidad', …  (traducido; plural a veces — D7)
  subtype?: str
  alignment: str
  armor_class: [{
    type: str,                               # 5 valores: 'natural','dex','armor','spell','condition'  (D2)
    value: int,
    armor?: [ref(equipment)],                # presente solo cuando type='armor'
    condition?: ref(conditions),             # presente solo cuando type='condition'
    spell?: ref(spells),                     # presente solo cuando type='spell'
    desc?: str
  }]
  hit_points: int
  hit_dice: str
  hit_points_roll: str
  speed: {
    walk?: str, burrow?: str, climb?: str, fly?: str, swim?: str,
    hover?: bool                             # 'hover' es bool, no str
  }
  strength: int
  dexterity: int
  constitution: int
  intelligence: int
  wisdom: int
  charisma: int
  proficiencies: [{value: int, proficiency: ref(proficiencies)}]
  damage_vulnerabilities: [str]              # strings, no refs
  damage_resistances: [str]                  # strings, no refs
  damage_immunities: [str]                   # strings, no refs
  condition_immunities: [ref(conditions)]    # refs, no strings
  senses: {
    passive_perception: int                  # required
    blindsight?: str, darkvision?: str, tremorsense?: str, truesight?: str
  }
  languages: str                             # 'Común, Goblin'  (string libre)
  challenge_rating: float | int              # 0.125, 0.25, 0.5, 1, 2, … 10
  proficiency_bonus?: int
  xp: int
  special_abilities?: [SpecialAbilitySchema]
  actions?: [MonsterActionSchema]
  legendary_actions?: [{
    name: str,
    desc: str,
    attack_bonus?: int,
    damage?: [DamageSchema],
    dc?: DifficultyClass
  }]
  reactions?: [{name: str, desc: str, dc?: DifficultyClass}]
  forms?: [ref(monsters)]
  image?: str
  url: str
```

### 11.1 `MonsterActionSchema` — `damage` es `Array<Damage | Choice>`

**`[CONTRADICE v2 §5.1 #5]`** — v2 dice «union `Damage | Choice`». El `.ts` dice `z.array(z.union([DamageSchema, ChoiceSchema]))` y el JSON lo confirma: **es un array**, y cada elemento es `Damage` o `Choice`. El importador debe **iterar `damage[]`**, no asumir un único objeto.

```text
MonsterActionSchema:
  name: str
  desc: str
  attack_bonus?: int
  dc?: DifficultyClass
  usage?: {
    type: str, dice?: str, min_value?: int, times?: int, rest_types?: [str]
  }
  multiattack_type?: str
  actions?: [{action_name: str, count: int | str, type: str}]
  action_options?: ChoiceSchema
  attacks?: [{
    name: str,
    dc: DifficultyClass,
    damage?: [DamageSchema]
  }]
  options?: ChoiceSchema
  damage?: [
    | DamageSchema                                # {damage_type: ref, damage_dice: str, dc?: DC}
    | ChoiceSchema                                # {choose: int, type?: str, from: OptionSetSchema}
  ]
```

**Rama `Damage` — 3 ejemplos reales** (phase2.txt §C):

```json
// monsters[aboleth].actions[Tentáculo]
{
  "damage_type": { "index": "bludgeoning", "name": "Contundente", "url": "/api/2014/damage-types/bludgeoning" },
  "damage_dice": "2d6+5"
}

// monsters[aboleth].actions[Tentáculo] (segundo elemento del array)
{
  "damage_type": { "index": "acid", "name": "Ácido", "url": "/api/2014/damage-types/acid" },
  "damage_dice": "1d12"
}

// monsters[ankheg].actions[Rocío Ácido] (con dc)
{
  "damage_type": { "index": "acid", "name": "Ácido", "url": "/api/2014/damage-types/acid" },
  "damage_dice": "3d6"
}
```

**Rama `Choice` — 3 ejemplos reales** (phase2.txt §C):

```json
// monsters[djinni].actions[Cimitarra] — elegir tipo de daño
{
  "choose": 1,
  "type": "daño",                                // ← D5: en español, no 'damage'
  "from": {
    "option_set_type": "options_array",
    "options": [
      { "option_type": "daño",                    // ← D5
        "damage_type": { "index": "lightning", "name": "Rayo", "url": "/api/2014/damage-types/lightning" },
        "damage_dice": "1d6" },
      { "option_type": "daño",
        "damage_type": { "index": "thunder", "name": "Trueno", "url": "/api/2014/damage-types/thunder" },
        "damage_dice": "1d6" }
    ]
  }
}

// monsters[drider].actions[Espada Larga] — una mano / dos manos (con notes)
{
  "choose": 1,
  "type": "daño",
  "from": {
    "option_set_type": "options_array",
    "options": [
      { "option_type": "daño", "damage_type": {…},"damage_dice": "1d8+3",  "notes": "Una mano" },
      { "option_type": "daño", "damage_type": {…},"damage_dice": "1d10+3", "notes": "Dos manos" }
    ]
  }
}

// monsters[druid].actions[Bastón] — 3 opciones (una mano, dos manos, con palo rígido)
// misma estructura que arriba con 3 elementos
```

**`[DRIFT DE DATOS, D5]`** — `option_type: "daño"` y `type: "daño"`. El `.ts` declara `z.literal('damage')`. El importador debe normalizar. Afecta **solo** a `monsters.actions[].damage[].from.options[]` (y por simetría a `action_options`/`options` si los hubiera).

### 11.2 `armor_class[].type` — 5 valores

**`[CONTRADICE v2 §5.1 #2]`** — v2 reporta 4 valores (`natural`, `dex`, `spell`, `condition`). El sondeo cuenta **5**, añadiendo **`armor`** con 37 ocurrencias (monstruos con armadura equipada: goblin, hobgoblin, bandit, etc.).

| `type` | Ocurrencias | Campos adicionales típicos | Ejemplo |
|--------|-------------|----------------------------|---------|
| `natural` | 180 | ninguno | `{"type":"natural","value":14}` |
| `dex` | 119 | ninguno | `{"type":"dex","value":15}` |
| `armor` | 37 | `armor: [ref(equipment)]` | `{"type":"armor","value":15,"armor":[{leather-armor},{shield}]}` |
| `spell` | 4 | `spell: ref(spells)` | `{"type":"spell","value":15,"spell":{mage-armor}}` |
| `condition` | 1 | `condition: ref(conditions)` | `{"type":"condition","value":11,"condition":{prone}}` (ankheg) |

**Regla de lectura:** CA nominal = `armor_class[0].value`. Si `len(armor_class) > 1`, el segundo y siguientes son **condicionales** (e.g. ankheg: CA 14 natural, pero 11 mientras está derribado). El MVP puede ignorar los condicionales y usar `[0].value`.

**Ejemplo real** (phase2.txt §D, `monsters[goblin]`):

```json
"armor_class": [
  {
    "type": "armor",
    "value": 15,
    "armor": [
      { "index": "leather-armor", "name": "Armadura de Cuero", "url": "/api/2014/equipment/leather-armor" },
      { "index": "shield",        "name": "Escudo",             "url": "/api/2014/equipment/shield" }
    ]
  }
]
```

### 11.3 `SpecialAbilitySchema` — con `spellcasting` embebido

**No documentado en v2.** Algunos monstruos (archmage, lich, drow mage, etc.) llevan su `spellcasting` dentro de `special_abilities[]`, con estructura **distinta** a `levels.spellcasting`.

```text
SpecialAbilitySchema:
  name: str
  desc: str
  attack_bonus?: int
  damage?: [DamageSchema]
  dc?: DifficultyClass
  usage?: {type: str, times?: int, rest_types?: [str]}
  spellcasting?: {
    ability: ref(ability-scores)
    components_required: [str]                # ['V','S','M']
    spells: [{name: str, level: int, url: str, usage?: {type: str, times?: int}, notes?: str}]
    level?: int
    dc?: int                                 # ← int, NO DifficultyClass
    modifier?: int
    school?: str
    slots?: {str: int}                       # {'1': 4, '2': 3, …}
  }
```

**Ojo:** `special_abilities[].spellcasting.dc` es **int** (CD numérica), no `DifficultyClass`. Es una **colisión de nombre** con `spells.dc` y `monsters.actions[].dc`. El importador debe inspeccionar el contexto, no el nombre.

**Ejemplo real** (`monsters[goblin]` con `special_abilities` sin spellcasting):

```json
"special_abilities": [
  {
    "name": "Escape Ágil",
    "desc": "El goblin puede tomar la acción de Desengagement o Esconderse como acción adicional en cada uno de sus turnos."
  }
]
```

### 11.4 Ejemplo real completo: `monsters[goblin]`

```json
{
  "index": "goblin",
  "name": "Goblin",
  "size": "Pequeño",
  "type": "humanoides",
  "subtype": "goblin",
  "alignment": "neutral maligno",
  "armor_class": [ { "type": "armor", "value": 15, "armor": […] } ],
  "hit_points": 7,
  "hit_dice": "2d6",
  "hit_points_roll": "2d6",
  "speed": { "walk": "30 pies" },
  "strength": 8, "dexterity": 14, "constitution": 10,
  "intelligence": 10, "wisdom": 8, "charisma": 8,
  "proficiencies": [ { "value": 6, "proficiency": { "index": "skill-stealth", … } } ],
  "damage_vulnerabilities": [], "damage_resistances": [],
  "damage_immunities": [], "condition_immunities": [],
  "senses": { "darkvision": "60 pies", "passive_perception": 9 },
  "languages": "Común, Goblin",
  "challenge_rating": 0.25,
  "proficiency_bonus": 2,
  "xp": 50,
  "special_abilities": [ { "name": "Escape Ágil", "desc": "…" } ],
  "actions": [
    { "name": "Cimitarra",
      "desc": "Ataque de Arma Cuerpo a Cuerpo: +4 al ataque, alcance 5 pies, …",
      "attack_bonus": 4,
      "damage": [ { "damage_type": { "index": "slashing", … }, "damage_dice": "1d6+2" } ] },
    { "name": "Arco Corto",
      "attack_bonus": 4,
      "damage": [ { "damage_type": { "index": "piercing", … }, "damage_dice": "1d6+2" } ] }
  ],
  "image": "/api/images/monsters/goblin.png",
  "url": "/api/2014/monsters/goblin"
}
```

**`[DRIFT DE DATOS, D7]`** — `type: "humanoides"` (plural). En inglés `"humanoid"` (singular). El importador no debe usar `type` como enum estricto ni como clave de join; usar `index` si se necesita agrupar. Igual pasa con `size`: viene traducido (`"Pequeño"`, `"Grande"`) y no es machine-readable sin tabla de traducción.

**Uso en Fase 2.2** — el DM busca un monstruo por nombre, lo añade como combatiente, el sistema lee `hit_points` (7), `armor_class[0].value` (15), `dexterity` (14 → mod +2, iniciativa 12), `actions[]` para el panel de ataques. `challenge_rating` y `xp` son solo display. `special_abilities[]` y `legendary_actions[]` van al `<details>` del panel.

---

## 12. `races`

**Registros:** 9 · **Fase:** 2.3 · **Tipo:** entidad

```text
races:
  index: str                                 # 'elf', 'human', 'dwarf', …
  name: str                                  # 'Elfo', 'Humano', …
  speed: int                                 # 30, 25, …
  ability_bonuses: [{ability_score: ref(ability-scores), bonus: int}]
  ability_bonus_options?: ChoiceSchema       # elección entre bonuses (e.g. half-elf)
  alignment: str
  age: str
  size: str                                  # 'Mediano', 'Pequeño'
  size_description: str
  starting_proficiencies?: [ref(proficiencies)]
  starting_proficiency_options?: ChoiceSchema
  languages: [ref(languages)]                # refs, no strings
  language_desc: str
  language_options?: ChoiceSchema
  traits?: [ref(traits)]                     # refs a 'traits' (no importada en 2.x)
  subraces?: [ref(subraces)]
  url: str
```

**Ejemplo real** (phase2.txt §D, `races[elf]`, recortado):

```json
{
  "index": "elf",
  "name": "Elfo",
  "speed": 30,
  "ability_bonuses": [
    { "ability_score": { "index": "dex", "name": "DES", "url": "/api/ability-scores/dex" }, "bonus": 2 }
  ],
  "size": "Mediano",
  "languages": [
    { "index": "common", "name": "Common", "url": "/api/2014/languages/common" },
    { "index": "elvish", "name": "Elvish", "url": "/api/2014/languages/elvish" }
  ],
  "traits": [
    { "index": "darkvision", "name": "Visión en la Oscuridad", "url": "/api/traits/darkvision" },
    { "index": "fey-ancestry", "name": "Ascendencia Feérica", "url": "/api/traits/fey-ancestry" },
    { "index": "trance", "name": "Trance", "url": "/api/traits/trance" },
    { "index": "keen-senses", "name": "Sentidos Agudos", "url": "/api/traits/keen-senses" }
  ],
  "subraces": [ { "index": "high-elf", "name": "Alto Elfo", "url": "/api/subraces/high-elf" } ],
  "url": "/api/2014/races/elf"
}
```

**`[DRIFT DE DATOS, D9]`** — `languages[].name = "Common"` / `"Elvish"` (inglés) en un fichero en español. Inconsistente con `traits[].name` que sí está traducido (`"Visión en la Oscuridad"`). El importador debe usar `index` para joins y `name` solo para display; si el display importa, aplicar tabla de traducción manual.

**Uso en Fase 2.3** — si el jugador elige raza, `ability_bonuses[]` se suma a las 6 características. `speed` es la velocidad base. `languages[]` es display. `traits[]` y `subraces[]` quedan como refs en `data` sin resolver (fuera de scope 2.x).

---

## 13. URL drift — `/api/X` vs `/api/2014/X`

**Hallazgo nuevo** (no documentado en v2). Los `APIReference.url` del dataset `es/` mezclan dos prefijos: `/api/<colección>/<index>` y `/api/2014/<colección>/<index>`. El `index` es **idéntico** en ambas variantes; solo cambia el prefijo.

Campos afectados (de `phase2.txt` §A — solo se listan los que tienen >1 prefijo):

| Colección.campo | `/api/X` | `/api/2014/X` |
|-----------------|---------:|---------------:|
| `classes.proficiencies[]` | 81 | 6 |
| `spells.classes[]` | 751 | 15 |
| `spells.damage.damage_type` | 62 | 2 |
| `spells.dc.dc_type` | 89 | 3 |
| `spells.school` | 312 | 7 |
| `spells.subclasses[]` | 220 | 4 |

**Implicación para el importador:** extraer FK del `url` es **frágil**. Usar siempre el campo `index` del `APIReference` para resolver la FK lógica. El `url` se conserva en `data` como auditoría. Esto ya lo anticipó v2 §5.3 #5 para el caso de `index`, pero el drift de URL es nuevo y refuerza la decisión.

**Ningún caso en el que el `index` difiera entre las dos variantes.** Confirmado por el sondeo: `spells[fireball].school.index = "evocation"` aunque la URL sea `/api/magic-schools/evocation` (sin `2014`).

---

## 14. Trazabilidad D1–D10

Referencia cruzada de las correcciones y drift documentados aquí con su ubicación en otros docs.

| ID | Tipo | Descripción | Detectado en | Doc donde se resuelve |
|----|------|-------------|--------------|------------------------|
| D1 | `[CONTRADICE v2 §5.1 #7]` | `levels.spellcasting` en 8/12 clases, no 12/12 | probe 1 `# extras` | `SHAPES §6.2`, `SCHEMAS §4`, `CONTRACT §5` |
| D2 | `[CONTRADICE v2 §5.1 #2]` | `armor_class[].type` tiene 5 valores (falta `armor`) | probe 1 `# extras` + `monsters[goblin]` | `SHAPES §11.2`, `SCHEMAS §4`, `CONTRACT §5` |
| D3 | `[CONTRADICE v2 §5.1 #8]` | `class_specific` tiene 32 claves, no 33 | probe 1 `# extras` + `.ts` | `SHAPES §6.1`, `SCHEMAS §4` |
| D4 | `[CONTRADICE v2 §5.1 #5]` | `MonsterAction.damage` es `Array<Damage\|Choice>`, no `Damage\|Choice` | probe 2 §C | `SHAPES §11.1`, `MAPPING §4`, `CONTRACT §5` |
| D5 | `[DRIFT .ts↔.json]` | `option_type: "daño"` (es) vs `z.literal('damage')` (ts) | probe 2 §C | `SHAPES §2.2`, `SCHEMAS §4`, `RECOMMENDATIONS §4` |
| D6 | `[DRIFT DE DATOS]` | `eldritch-blast.damage_at_character_level` no escala (1d10 en las 4 claves) | probe 2 §D | `SHAPES §10.4`, `SCHEMAS §4`, `RECOMMENDATIONS §5` |
| D7 | `[DRIFT DE DATOS]` | `monsters.type = "humanoides"` (plural); `size` traducido | probe 2 §D | `SHAPES §11.4`, `SCHEMAS §4`, `RECOMMENDATIONS §5` |
| D8 | `[DRIFT DE DATOS]` | `ability-scores[str].name = "STR"` vs `skills.athletics.ability_score.name = "FUE"` | probe 2 §D | `SHAPES §3`, `SCHEMAS §4`, `RECOMMENDATIONS §5` |
| D9 | `[DRIFT DE DATOS]` | `races[elf].languages[]` con `name` en inglés (`"Common"`, `"Elvish"`) | probe 2 §D | `SHAPES §12`, `SCHEMAS §4` |
| D10 | `[DRIFT DE DATOS]` | `attack_type`, `dc_success` traducidos (`"a distancia"`, `"mitad"`) | probe 2 §D | `SHAPES §10`, `MAPPING §3`, `RECOMMENDATIONS §4` |

---

## 15. Decisiones (una línea de justificación cada una)

- **`type` de `armor_class[]` se documenta con 5 valores, no 4** — el JSON manda; `armor` aparece 37 veces y dejarlo fuera rompería el importador en 37 registros.
- **`class_specific` con 32 claves, no 33** — `.ts` y JSON coinciden 1:1; la 33ª no existe.
- **`levels.spellcasting` documentado como nullable (clave ausente, no `{}` ni `null`)** — 130/290 registros no lo tienen; tratarlo como `{}` rompería la lógica de "no castea".
- **`MonsterAction.damage` como array** — el importador debe iterar; documentarlo como unión única llevaría a perder el segundo elemento de ataques como `aboleth.Tentáculo` (bludgeoning + acid).
- **`special_abilities[].spellcasting.dc` es int, no `DifficultyClass`** — colisión de nombre con `spells.dc`; documentarlo aquí evita que el programador asuma la misma forma.
- **`ChoiceSchema.from` con 3 ramas declaradas y 2 observadas** — `resource_list` se documenta como "declarada, 0 ocurrencias en 2.x" en lugar de eliminarla, para no divergir del `.ts`.
- **URL drift como hallazgo propio** — no estaba en v2; refuerza la decisión de FK por `index` y se documenta aquí para que `CONTRACT.md` lo asuma.
- **Ejemplos reales recortados a ~120 chars** — el shape se entiende, el doc no se infla a 200 KB.
- **`[DRIFT DE DATOS]` D5–D10 visibles, no ocultos** — el importador debe saber que el dataset `es/` tiene bugs antes de confiar en `eldritch-blast` o en `option_type`.
