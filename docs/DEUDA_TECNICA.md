# Deuda Técnica — Reconciliación SRD 5e (Fase 2.1.2-B-2)

**Proyecto:** DnD_tools  
**Fase:** 2.1.2-B-2 (Reconciliación del SRD)  
**Fecha:** 2026-10-21  

Este documento consolida y cataloga las discrepancias, limitaciones de datos e incidencias conocidas (*drifts*) identificadas durante el análisis del compendio SRD 5e (2014) en español (`es/`) y su contraste con los esquemas TypeScript/Zod de `5e-bits` y el contrato del sistema.

---

## 1. Incidencias Principales (I6–I13)

### I6 (D6) — Escalado de daño en conjuros (`eldritch-blast`)
- **Origen:** `5e-SRD-Spells.json` (`eldritch-blast`).
- **Problema:** El campo `damage_at_character_level` no escala adecuadamente; contiene `"1d10"` en los cuatro niveles de corte (`"1"`, `"5"`, `"11"`, `"17"`), en lugar de reflejar el aumento de rayos/daño del conjuro.
- **Impacto:** Fase 2.5 (conjuros). En Fase 2.2 no afecta dado que los conjuros no se exponen en combate directo.
- **Acción futura:** Aplicar parche o regla especial en el importador de la Fase 2.5 y registrar advertencia en `import_meta.errors_json`.

### I7 (D7) — Pluralización y traducción en filtros de monstruos
- **Origen:** `5e-SRD-Monsters.json` (`type`, `size`).
- **Problema:** En el dataset `es/`, `type` contiene valores traducidos y en ocasiones pluralizados (p. ej. `"humanoides"`, `"aberración"`), y `size` está en español (`"Grande"`, `"Medio"`, `"Pequeño"`).
- **Impacto:** Cualquier filtro que asuma valores canónicos en inglés (como `"humanoid"` o `"Large"`) no arrojará resultados.
- **Resolución/Estado:** Se mantiene el valor textual de `es/` en las columnas indexadas `type` y `size` de `monsters` para permitir búsqueda directa sin conversiones artificiales en runtime.

### I8 (D8) — Inconsistencia en nombres de características (`ability-scores`)
- **Origen:** `5e-SRD-Ability-Scores.json` vs referencias cruzadas en `skills` y fichas.
- **Problema:** `ability-scores[str].name` permanece en inglés (`"STR"`), mientras que las referencias cruzadas y descripciones traducidas usan abreviaturas en español (`"FUE"`, `"DES"`, `"CON"`, `"INT"`, `"SAB"`, `"CAR"`).
- **Impacto:** La UI debe manejar el mapeo de visualización para no confundir al usuario mostrando etiquetas mixtas inglés/español.
- **Resolución/Estado:** Resolver referencias mediante `index` (`str`, `dex`, etc.) y utilizar tabla de visualización en frontend.

### I9 (D9) — Nombres de idiomas de razas sin traducir
- **Origen:** `5e-SRD-Races.json` (`languages[]`).
- **Problema:** Ciertas razas (como `elf`) conservan nombres en inglés dentro del array de idiomas (`"Common"`, `"Elvish"`) a pesar de estar en el archivo de localización español.
- **Impacto:** Fase 2.3 (ficha de personaje). En Fase 2.2 no impacta al bestiario.
- **Acción futura:** Mapear en importador de razas en Fase 2.3 a `"Común"`, `"Élfico"`, etc.

### I10 (D10) — Valores de enums traducidos en datos de combate
- **Origen:** `monsters.actions[].attacks[]`, `monsters.actions[].dc`, `spells.dc`.
- **Problema:** Campos como `attack_type` y `dc_success` (`success_type`) contienen cadenas traducidas (`"cuerpo a cuerpo"`, `"mitad"`, `"ninguno"`) en vez de los enums estrictos esperados por validadores Zod (`"melee"`, `"half"`, `"none"`).
- **Impacto:** Si se pasa un validador estricto sin preprocesamiento, se producen errores de validación.
- **Resolución/Estado:** Normalización controlada documentada en `CONTRACT.md §4` (`option_type` 'daño'→'damage', `success_type` 'mitad'→'half').

### I13 (D-URL / SHAPES §13) — Discrepancia de prefijos en URLs de `APIReference`
- **Origen:** Enlaces `url` en todas las colecciones del SRD.
- **Problema:** Coexisten de forma inconsistente rutas con prefijo `/api/X` y `/api/2014/X` (p. ej. `/api/conditions/blinded` vs `/api/2014/conditions/blinded`).
- **Impacto:** Extraer la colección destino o la clave foránea a partir del string de `url` genera fallos silenciosos y referencias rotas.
- **Resolución/Estado:** Regla estricta de contrato arquitectónico: **las claves foráneas siempre se resuelven mediante `index_slug` (el campo `index`)**. El campo `url` nunca se usa para lógica relacional ni se expone al cliente.

---

## 2. Problemas Cosméticos y No Bloqueantes

1. **Campos opcionales en `.ts` presentes al 100 % en JSON:**
   - Atributos definidos con `.optional()` en TypeScript/Zod (como `LevelSchema.features`, `LevelSchema.prof_bonus`, `SpellSchema.subclasses`, `MonsterSchema.proficiency_bonus`) se encuentran poblados en el 100% de los registros del JSON. No constituyen drift estructural y no rompen compatibilidad.
2. **Esquemas redundantes en TypeScript:**
   - Tipos como `SubclassSpellPrerequisiteSchema` duplican la estructura de `APIReference` con un campo `type` adicional sin valor operativo extra.
3. **Campos y ramas no observados:**
   - `APIReference.note` y `OptionSetSchema.resource_list` están contemplados en los schemas TypeScript de referencia pero no presentan instancias en las colecciones prioritarias analizadas.
4. **Ausencia de `starting_proficiencies` en `races` (D12):**
   - El esquema declara competencias iniciales para razas, pero en `5e-SRD-Races.json` (es/) el campo no está presente (0/9). Se reconstruirá a partir de `traits[]` en la Fase 2.3 si se requiere.
