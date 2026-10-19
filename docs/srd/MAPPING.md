# MAPPING.md — De feature del proyecto a campo SRD

**Proyecto:** DnD_tools · Fase 2.2–2.5
**Objetivo:** para cada feature del proyecto, decir **qué campos SRD** consume, de **qué colección** vienen, y qué **cálculo** hace el backend. Sin este mapa, el programador no sabe si importar `spells` completo o solo 3 campos.

**Fuentes:** `SHAPES.md` (estructura), `SCHEMAS.md` (contratos `.ts`), `INVENTORY.md` (qué se importa y cuándo).
**Baseline:** `PRIOR_REPORT_v2.md §4` (mapeo UI/endpoints) — no se repite.

## 0. Notación

- `input` — dato que el jugador/DM introduce en la UI.
- `SRD` — campo que viene de una colección importada.
- `calc` — campo calculado en el backend; no se persiste como SRD.
- `state` — dato persistido en tablas del MVP (`combatants`, `characters`, …).
- `[Dx]` — remite a una discrepancia o drift ya documentado en `SHAPES.md`/`SCHEMAS.md`.
- La columna **Obligatorio** indica si el feature **falla** sin ese dato; **Opcional** si degrada la UI.

---

## 1. Resumen — 6 features, colecciones que cada una toca

| # | Feature | Fase | Colecciones SRD usadas | Colecciones SRD opcionales |
|---|---------|------|------------------------|----------------------------|
| 1 | Mini-ficha de personaje | 2.3 | `classes`, `levels`, `races`, `equipment`, `skills`, `ability-scores` | `equipment-categories`, `proficiencies`, `weapon-properties` |
| 2 | Iniciativa automática | 2.4 | `monsters` (para NPCs), `races` (si el jugador elige raza) | — |
| 3 | Ataque y daño con arma | 2.4 | `equipment`, `weapon-properties`, `damage-types` | `equipment-categories` |
| 4 | Pruebas de característica | 2.4 | `skills`, `ability-scores` | `classes` (proficiencias en skills) |
| 5 | Espacios de conjuro | 2.5 | `levels` (`spellcasting`), `classes` (`spellcasting.spellcasting_ability`) | `spells` (catálogo de hechizos), `magic-schools` |
| 6 | Bestiario en combate | 2.2 | `monsters`, `conditions`, `damage-types` | `equipment` (para `armor_class[].armor`), `spells` (para `armor_class[].spell`) |

**Regla general:** si una colección aparece como **opcional**, el feature funciona sin ella; solo se pierde display enriquecido. Si aparece como **usada**, el feature no funciona sin ella.

---

## 2. Feature: Mini-ficha de personaje (Fase 2.3)

**Pantalla:** `/player`, panel "Mi ficha". **Endpoint:** `GET /api/srd/classes/{index}`, `GET /api/srd/classes/{index}/levels`, `GET /api/srd/races`, `GET /api/srd/equipment?category=weapon`, `GET /api/srd/skills`.
**Persistencia del proyecto:** tabla `characters` (nueva en 2.3) — el SRD es solo **catálogo de origen**; el PJ guarda sus valores finales.

### 2.1 Datos que el jugador introduce (`input`)

| Campo character | Tipo | Validación | Notas |
|-----------------|------|------------|-------|
| `name` | str | no vacío | display |
| `level` | int | 1..20 | determina `prof_bonus` |
| `class_slug` | str | FK lógica a `classes.index` | selector |
| `race_slug` | str? | FK lógica a `races.index` | opcional |
| `strength..charisma` | int | 1..30 (típico 3..20 en creación) | 6 scores base |
| `skill_proficiencies[]` | [str] | FK lógica a `skills.index` | elección libre del jugador (limitada por background/class, fuera de scope del MVP) |
| `weapons[]` | [{equipment_slug, proficient: bool}] | FK lógica a `equipment.index` | inventario simplificado |
| `armor_slug` | str? | FK lógica a `equipment.index` | solo armadura equipada |

### 2.2 Datos SRD que se leen para poblar la ficha

| Campo SRD | Colección | Obligatorio | Uso |
|-----------|-----------|-------------|-----|
| `classes.hit_die` | `classes` | Sí | dado de golpe → HP inicial |
| `classes.saving_throws[]` | `classes` | Sí | competencia en salvaciones |
| `classes.proficiencies[]` | `classes` | No | competencia con armas (simple/martial) |
| `classes.spellcasting.spellcasting_ability.index` | `classes` | No | aptitud mágica (`int`/`wis`/`cha`) si castea |
| `levels.prof_bonus` | `levels` | Sí | +2 a +6 según nivel |
| `levels.ability_score_bonuses` | `levels` | Sí | a niveles 4/8/12/16/19 el PJ suma +2 |
| `levels.spellcasting` | `levels` | No | slots por nivel → Fase 2.5, se cachean aquí |
| `levels.class_specific` | `levels` | No | rasgos de clase (rage, ki, etc.) para display |
| `races.ability_bonuses[]` | `races` | No | suma a las 6 características |
| `races.speed` | `races` | No | velocidad base para display |
| `races.size` | `races` | No | "Mediano"/"Pequeño" — display |
| `skills.ability_score.index` | `skills` | Sí | para saber a qué característica va cada habilidad |
| `ability-scores.index`, `full_name` | `ability-scores` | Sí | display de las 6 características |
| `equipment.damage` | `equipment` | Sí | daño base de cada arma |
| `equipment.properties[]` | `equipment` | Sí | `finesse`, `two-handed`, `versatile`, `reach`, … |
| `weapon-properties.index` | `weapon-properties` | Sí | enum estable para lógica |

### 2.3 Cálculos del backend (`calc`)

| Cálculo | Fórmula | Depende de |
|---------|---------|------------|
| `str_mod..cha_mod` | `floor((score - 10) / 2)` | 6 scores + race bonus |
| `proficiency_bonus` | `levels.prof_bonus` | nivel + clase |
| `max_hp` | `classes.hit_die + con_mod + (level-1) * (hit_die/2 + 1 + con_mod)` | clase, nivel, CON |
| `initiative_mod` | `dex_mod` | DEX |
| `passive_perception` | `10 + wis_mod + (proficient ? prof_bonus : 0)` | WIS, skill proficiency |
| `weapon_attack_bonus` | `str_mod \| dex_mod (si finesse) + prof_bonus (si proficient)` | arma, STR/DEX, clase |
| `spell_dc` | `8 + prof_bonus + spellcasting_ability_mod` | clase, nivel, aptitud mágica |
| `spell_attack_bonus` | `prof_bonus + spellcasting_ability_mod` | clase, nivel, aptitud mágica |

### 2.4 Persistencia (`state`)

La tabla `characters` guarda: valores finales de las 6 características, modificadores, `max_hp`, `prof_bonus`, `class_slug`, `race_slug`, `skill_proficiencies[]`, `weapons[]`, `armor_slug`, `spellcasting_ability_slug`, `spell_slots` (cache de Fase 2.5). **No se re-calcula en cada GET** — se lee de la tabla.

### 2.5 Lo que el SRD NO aporta

- **Equipo inicial concreto** — el jugador elige armas del catálogo, no de `classes.starting_equipment` (que es un `ChoiceSchema` complejo con opciones anidadas; ver `SHAPES §2`).
- **Backgrounds** — no se importa en 2.3; el jugador no elige background. Ver `INVENTORY §2.3`.
- **Proficiencias de raza** — `races.starting_proficiencies` no existe en `es/` (D12). Si el jugador quiere proficiencias de raza, se le piden manualmente.
- **Features narrativas** — no se importan (fuera de scope; ver `INVENTORY §2.3`).

### 2.6 Trazabilidad

| ID | Impacto en este feature |
|----|-------------------------|
| D1 | `levels.spellcasting` es nullable: la ficha debe distinguir "no castea" de "slots=0" |
| D2 | `armor_class[].type` de monstruos no aplica al PJ (el PJ usa `equipment.armor_class`) |
| D3 | `class_specific` con 32 claves: la ficha puede mostrar rasgos de clase pero sin mapear 1:1 a UI |
| D7 | `monsters.type`/`size` traducidos no afectan al PJ |
| D8 | `ability-scores[str].name = 'STR'` vs `'FUE'`: la ficha usa `full_name` (`'Fuerza'`) para display |
| D10 | `attack_type`/`dc_success` traducidos no se usan en este feature |
| D12 | `races.starting_proficiencies` ausente: se documenta como limitación |

---

## 3. Feature: Iniciativa automática (Fase 2.4)

**Pantalla:** `/dm` panel "Nuevo combatiente" (iniciativa ya existente en Fase 1) y `/player` botón "Tirar iniciativa". **Endpoint:** `POST /api/combat/start` (existente) + cálculo en cliente/servidor.
**Persistencia:** `combatants.initiative` (existente).

### 3.1 Datos de entrada

| Campo | Tipo | Origen | Notas |
|-------|------|--------|-------|
| `dexterity_score` | int | `characters.dexterity` (PJ) o `monsters.dexterity` (NPC) | **obligatorio** |
| `dex_mod` | int | `calc` = `floor((dex-10)/2)` | — |

### 3.2 SRD que se lee (si el combatiente es NPC)

| Campo SRD | Colección | Obligatorio | Uso |
|-----------|-----------|-------------|-----|
| `monsters.dexterity` | `monsters` | Sí (si NPC) | para `dex_mod` |
| `races.ability_bonuses[]` | `races` | No (si PJ con raza) | DEX bonus opcional |

### 3.3 Cálculo

| Cálculo | Fórmula |
|---------|---------|
| `initiative_roll` | `random(1, 20)` |
| `initiative` | `initiative_roll + dex_mod` |

**Ninguna colección SRD se importa específicamente para este feature.** Es aritmética sobre `monsters.dexterity` / `characters.dexterity`.

### 3.4 Lo que el SRD NO aporta

- **Dados** — el rango `1d20` es constante del sistema, no dato SRD.
- **Empates** — la regla de desempate por DEX es del sistema, no dato SRD.

### 3.5 Trazabilidad

Sin D activas. `monsters.dexterity` no tiene drift.

---

## 4. Feature: Ataque y daño con arma (Fase 2.4)

**Pantalla:** `/player` panel "Ataque" (selecciona arma del inventario, elige objetivo). **Endpoint:** `POST /api/combat/attack`.
**Persistencia:** ninguna nueva — modifica `combatants.hp_current` y registra en el log de combate (Fase 1).

### 4.1 Datos de entrada

| Campo | Tipo | Origen | Notas |
|-------|------|--------|-------|
| `attacker` | combatant_id | estado | — |
| `target` | combatant_id | estado | — |
| `weapon_slug` | str | `characters.weapons[].equipment_slug` | — |
| `two_handed` | bool | UI | solo armas `versatile` |
| `proficient` | bool | `characters.weapons[].proficient` | — |

### 4.2 SRD que se lee

| Campo SRD | Colección | Obligatorio | Uso |
|-----------|-----------|-------------|-----|
| `equipment.damage.damage_dice` | `equipment` | Sí | e.g. `1d8` |
| `equipment.damage.damage_type.index` | `equipment` | Sí | `slashing`/`piercing`/`bludgeoning` |
| `equipment.two_handed_damage.damage_dice` | `equipment` | Si `two_handed` | e.g. `1d10` |
| `equipment.properties[].index` | `equipment` | Sí | `finesse` cambia STR→DEX |
| `equipment.weapon_category` | `equipment` | No | simple/martial — display |
| `weapon-properties.index` | `weapon-properties` | Sí | enum estable |
| `damage-types.index` | `damage-types` | Sí | display del tipo de daño |
| `characters.str_mod` / `dex_mod` | `calc` | Sí | modificador de ataque |
| `characters.proficiency_bonus` | `calc` | Sí | suma si proficient |

### 4.3 Cálculo

| Cálculo | Fórmula |
|---------|---------|
| `is_finesse` | `'finesse' in equipment.properties[].index` |
| `is_ranged` | `equipment.weapon_range == 'A distancia'` |
| `attack_mod` | `is_finesse || is_ranged ? max(str_mod, dex_mod) : str_mod` |
| `attack_bonus` | `attack_mod + (proficient ? prof_bonus : 0)` |
| `attack_roll` | `random(1, 20) + attack_bonus` |
| `is_hit` | `attack_roll >= target.armor_class` |
| `is_crit` | `random_roll == 20` |
| `damage_dice` | `two_handed ? two_handed_damage.damage_dice : damage.damage_dice` |
| `damage_roll` | `roll(damage_dice) + attack_mod` (crit duplica dados, no mod) |

### 4.4 Casos especiales

- **Armas `versatile`**: si `two_handed=true`, se usa `two_handed_damage`; si no, `damage`.
- **`finesse`**: el jugador elige STR o DEX; el MVP toma `max(str_mod, dex_mod)` — simplificación documentada.
- **`ranged`**: `attack_mod` usa DEX por defecto; si el arma tiene `finesse` (raro en ranged), gana DEX igualmente.
- **`thrown`**: no se modela el cambio de STR/DEX en el MVP (fuera de scope).

### 4.5 Lo que el SRD NO aporta

- **Modificadores de daño por clase/feature** (e.g. Sneak Attack, Rage damage) — no se modelan en el MVP; el DM los aplica manualmente.
- **Resistencias/vulnerabilidades** del target — Fase 2.2 las guarda en `monsters.damage_resistances[]` (strings), pero Fase 2.4 **no las aplica automáticamente**. El log muestra el daño bruto; el DM ve el tipo y decide.
- **Inmunidades** — igual que resistencias.

### 4.6 Trazabilidad

| ID | Impacto |
|----|---------|
| D4 | `MonsterAction.damage` es array: relevante solo si un monstruo ataca al PJ (el PJ ataca con `equipment.damage`, no con `monsters.actions`) |
| D5 | `option_type: 'daño'` no afecta a este feature (armas no usan `ChoiceSchema`) |
| D10 | `attack_type` traducido no afecta (no se consulta para armas) |
| D11 | `success_type` no afecta (armas no tienen `dc`) |

---

## 5. Feature: Pruebas de característica (Fase 2.4)

**Pantalla:** `/player` botón "Tirar prueba" con DC definido por el DM. **Endpoint:** `POST /api/combat/check`.

### 5.1 Datos de entrada

| Campo | Tipo | Origen |
|-------|------|--------|
| `ability` | enum | `str` / `dex` / `con` / `int` / `wis` / `cha` |
| `skill` | str? | `skills.index` (opcional; si null, prueba pura de característica) |
| `dc` | int | DM |
| `proficient` | bool | `characters.skill_proficiencies[]` contiene `skill` |

### 5.2 SRD que se lee

| Campo SRD | Colección | Obligatorio | Uso |
|-----------|-----------|-------------|-----|
| `skills.ability_score.index` | `skills` | Sí (si `skill != null`) | mapa `skill → ability` |
| `ability-scores.index` | `ability-scores` | Sí | enum de características |
| `classes.proficiencies[]` | `classes` | No | proficiencias en skills por clase |

### 5.3 Cálculo

| Cálculo | Fórmula |
|---------|---------|
| `mod` | `floor((ability_score - 10) / 2)` |
| `bonus` | `mod + (proficient ? prof_bonus : 0)` |
| `roll` | `random(1, 20) + bonus` |
| `is_success` | `roll >= dc` |

### 5.4 Lo que el SRD NO aporta

- **Ventaja/desventaja** — la decide el DM en la UI, no el SRD.
- **Expertise** (doble proficiency) — no modelado en el MVP.

### 5.5 Trazabilidad

Sin D activas. `skills` y `ability-scores` no tienen drift relevante.

---

## 6. Feature: Espacios de conjuro (Fase 2.5)

**Pantalla:** `/player` panel "Hechizos" (slots disponibles + hechizos conocidos). **Endpoint:** `GET /api/srd/classes/{index}/levels?from=1&to=20`, `POST /api/combat/spend-slot`.

### 6.1 Datos de entrada

| Campo | Tipo | Origen |
|-------|------|--------|
| `class_slug` | str | `characters.class_slug` |
| `level` | int | `characters.level` |

### 6.2 SRD que se lee

| Campo SRD | Colección | Obligatorio | Uso |
|-----------|-----------|-------------|-----|
| `levels.spellcasting.spell_slots_level_1..9` | `levels` | Sí (si castea) | slots por nivel |
| `levels.spellcasting.cantrips_known` | `levels` | No | trucos conocidos |
| `levels.spellcasting.spells_known` | `levels` | No | hechizos conocidos (algunas clases) |
| `classes.spellcasting.spellcasting_ability.index` | `classes` | Sí (si castea) | aptitud mágica para CD/ataque |
| `spells.level` | `spells` | No | catálogo de hechizos por nivel |
| `spells.school.index` | `spells` | No | display de escuela |

### 6.3 Cálculo

| Cálculo | Fórmula |
|---------|---------|
| `slots_total[lvl]` | `levels.spellcasting.spell_slots_level_N` (0 si no castea, NULL si no aplica) |
| `slots_used[lvl]` | contador persistido en `characters.spell_slots_used` |
| `slots_available[lvl]` | `slots_total[lvl] - slots_used[lvl]` |
| `spell_dc` | `8 + prof_bonus + ability_mod` (ya calculado en Fase 2.3) |
| `spell_attack_bonus` | `prof_bonus + ability_mod` (ya calculado en Fase 2.3) |

### 6.4 Regla crítica `[D1]` — distinguir 0 de NULL

- `slots_total[lvl] == 0` → el PJ es lanzador pero aún no tiene acceso a ese nivel.
- `slots_total[lvl] == NULL` → el PJ no es lanzador, o no ha llegado al nivel de spellcasting de su clase.
- **La UI debe mostrar `0/0` como "sin acceso"**, y `NULL` como "esta clase no castea".
- El importador debe preservar la distinción: `NULL` si `levels.spellcasting` está ausente o `spell_slots_level_N` ausente; `0` si está presente con valor `0`.

### 6.5 Recuperación de slots

El MVP **no modela descanso largo/corto**. El DM puede hacer `POST /api/combat/reset-slots` para resetear `slots_used` a 0. Regla documentada como fuera de scope.

### 6.6 Lo que el SRD NO aporta

- **Warlock pact magic** — `levels.spellcasting` no lo distingue; el MVP no lo modela específicamente.
- **Preparación de conjuros** — no modelada (el jugador conoce todos los de su nivel, simplificación).
- **Componentes materiales** — `spells.material` es display, no se valida.

### 6.7 Trazabilidad

| ID | Impacto |
|----|---------|
| D1 | `levels.spellcasting` nullable: la UI debe manejar ausencia vs 0 |
| D6 | `eldritch-blast.damage_at_character_level` no escala: si el brujo usa este truco, el daño calculado será 1d10 siempre. Se anota en `import_meta` y se muestra un warning al DM |
| D10 | `dc_success` traducido: solo display, no afecta al cálculo |

---

## 7. Feature: Bestiario en combate (Fase 2.2)

**Pantalla:** `/dm` panel "Nuevo combatiente" (datalist). **Endpoint:** `GET /api/srd/monsters`, `GET /api/srd/monsters/{index}`, `POST /api/combatants` (extendido con `srd_index`).

### 7.1 Datos de entrada

| Campo | Tipo | Origen |
|-------|------|--------|
| `srd_index` | str | datalist del DM |
| `name` (override) | str? | UI |
| `hp_max` (override) | int? | UI |

### 7.2 SRD que se lee

| Campo SRD | Colección | Obligatorio | Uso |
|-----------|-----------|-------------|-----|
| `monsters.index` | `monsters` | Sí | identidad |
| `monsters.name` | `monsters` | Sí | `combatants.name` |
| `monsters.hit_points` | `monsters` | Sí | `combatants.hp_max` / `hp_current` |
| `monsters.armor_class[0].value` | `monsters` | Sí | CA nominal |
| `monsters.dexterity` | `monsters` | Sí | `initiative_mod` |
| `monsters.challenge_rating` | `monsters` | No | display |
| `monsters.xp` | `monsters` | No | display |
| `monsters.type`, `monsters.size` | `monsters` | No | filtro UI (`[D7]` — traducidos) |
| `monsters.actions[].damage[]` | `monsters` | No | `<details>` de ataques (`[D4]` — es array) |
| `monsters.special_abilities[]` | `monsters` | No | `<details>` |
| `monsters.legendary_actions[]` | `monsters` | No | `<details>` |
| `monsters.condition_immunities[]` | `monsters` | No | `<details>` (necesita `conditions` importado) |
| `conditions.index` | `conditions` | No | display de inmunidades |
| `damage-types.index` | `damage-types` | No | display de tipos de daño en `actions[].damage[]` |

### 7.3 Cálculo

| Cálculo | Fórmula |
|---------|---------|
| `hp_max` | `monsters.hit_points` (o override del DM) |
| `armor_class` | `monsters.armor_class[0].value` (ignorar condicionales) |
| `initiative_mod` | `floor((monsters.dexterity - 10) / 2)` |

### 7.4 Persistencia

Tabla `combatants` (existente): `srd_index` (nueva columna), `hp_max`, `hp_current`, `name`, `initiative`, `kind='monster'`. El `monsters.data` completo **no se duplica** en `combatants`; solo se referencia por `srd_index`.

### 7.5 Lo que el SRD NO aporta

- **Comportamiento de la IA** — el DM decide las acciones; el MVP no simula.
- **Variantes de monstruo** — no hay tabla de variantes; el DM puede hacer override de `name`/`hp_max`.
- **Aplicación automática de resistencias** — Fase 2.4 calcula daño bruto; el DM aplica resistencias manualmente.

### 7.6 Trazabilidad

| ID | Impacto |
|----|---------|
| D2 | `armor_class[].type` con 5 valores: el MVP ignora el tipo y usa `[0].value`. Los condicionales se descartan |
| D4 | `actions[].damage` es array: el importador itera; el `<details>` muestra todas las entradas |
| D7 | `type`/`size` traducidos: el filtro de la datalist los usa tal cual (display) |
| D11 | `dc.success_type` puede estar en castellano: si el MVP no usa `dc` (no simula), no impacta; si en el futuro se simula, normalizar antes |

---

## 8. Colecciones NO usadas por ningún feature

| Colección | Motivo |
|-----------|--------|
| `alignments` | No hay lógica de alineamiento en el MVP. |
| `backgrounds` | La ficha 2.3 no elige background (simplificación). |
| `feats` | 1 registro; no se modelan dotes. |
| `features` | 407 registros narrativos; no se modelan features de clase. |
| `languages` | Solo display si el PJ tiene `races.languages[]`; no es feature propia. |
| `magic-items` | No hay inventario mágico. |
| `rules`, `rule-sections` | Sin lógica de reglas. |
| `subclasses`, `subraces` | El MVP no elige subclase/subraza. |
| `traits` | Los traits de raza no se importan; `races.traits[]` queda como refs en `data`. |
| `equipment-categories` | **Referencia secundaria**: usada por `equipment` para resolver `equipment_category`, pero ningún feature la consulta directamente. Se importa en `reference_entries` por completitud de FK. |
| `proficiencies` | **Referencia secundaria**: usada por `classes.proficiencies[]`; el MVP la muestra pero no la consulta como feature propia. |
| `magic-schools` | **Referencia secundaria**: usada por `spells.school`; solo display. |

---

## 9. Trazabilidad global D1–D12 ↔ features

| ID | Features afectados |
|----|---------------------|
| D1 | Mini-ficha (2.3), Espacios de conjuro (2.5) |
| D2 | Bestiario (2.2), Mini-ficha (2.3) |
| D3 | Mini-ficha (2.3) |
| D4 | Ataque/daño (2.4), Bestiario (2.2) |
| D5 | Bestiario (2.2), Ataque/daño (2.4) — si el DM ataca con monstruo |
| D6 | Espacios de conjuro (2.5) — `eldritch-blast` |
| D7 | Bestiario (2.2) |
| D8 | Mini-ficha (2.3) |
| D9 | Mini-ficha (2.3) — display de idiomas de raza |
| D10 | Espacios de conjuro (2.5) — display |
| D11 | Bestiario (2.2) — si el MVP simula `dc` en el futuro |
| D12 | Mini-ficha (2.3) — proficiencias de raza |

---

## 10. Decisiones (una línea de justificación cada una)

- **Cada feature tiene su propia sección con `input`/`SRD`/`calc`/`state`** — el programador puede leer solo la sección del feature que está implementando y tener todo el contrato.
- **Iniciativa, ataque y pruebas listan `calc` explícito** — el programador no debe asumir fórmulas; están aquí para que no las busque en el SRD (que no las tiene).
- **`MAPPING.md` es por feature, no por colección** — `SHAPES.md` ya cubre "qué hay en cada colección"; aquí se cubre "qué necesita cada feature", que es el orden en el que se programa.
- **Documentar D1–D12 por feature** — un programador que trabaje solo en `ataque/daño` no necesita saber D7 (que afecta a `bestiario`), pero sí D4 y D5.
- **Sección §8 "colecciones NO usadas"** — evita que el programador importe `rules` por si acaso; las exclusiones están justificadas.
- **No incluir `magic-schools`, `equipment-categories`, `proficiencies` como features propios** — son referencias secundarias; ningún feature las consume directamente como input.
- **Resistencias/inmunidades no se aplican automáticamente** — el MVP calcula daño bruto; aplicarlas requiere motor de reglas, que está fuera de scope (`CONTRACT §8`).
