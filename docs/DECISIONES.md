# Registro de Decisiones de Diseño y Arquitectura (Fase 2.3)

Este documento registra las decisiones tomadas durante la implementación de la Fase 2.3 ("Mini-ficha de Personaje").

---

## 1. Experiencia de Usuario y Navegación en `/player`

### Decisión
Se introdujo una barra de navegación por pestañas en la vista de jugador:
- **⚔️ Combate:** Mantiene intacta la interfaz existente de combate (banner de turno, panel de HP de tu combatiente, lista de iniciativa en tiempo real vía WebSocket).
- **📜 Mi Ficha:** Muestra la mini-ficha completa del personaje o el asistente de creación/edición.

### Justificación
Los jugadores de mesa necesitan poder consultar sus modificadores, daño de armas y conjuros durante su turno sin perder la conexión con el combate ni recargar la pantalla.

---

## 2. Flujo de Invitado ("Guest") vs Usuario Registrado

### Decisión
- **Invitados:** Pueden seguir entrando al combate con su código y nombre de jugador sin crear cuenta. En la pestaña "Combate" participan plenamente. Al acceder a la pestaña "Mi Ficha", se les presenta un banner informativo que explica que los personajes persistentes requieren cuenta, ofreciendo botones a `/register` y `/login`.
- **Usuarios Registrados:** Al entrar al combate se vincula su sesión con su `user_id`. En "Mi Ficha" pueden crear personajes, editar sus atributos, listar múltiples personajes y vincular su ficha al combate actual.

---

## 3. Modelo de Persistencia en Base de Datos (`characters`)

### Decisión
Se activó la tabla `characters` en `data/dnd.db` con modelo híbrido relacional/JSON:
- **Columnas relacionales indexadas:** `id`, `campaign_id` (nullable para admitir personajes creados fuera o dentro de campañas), `user_id`, `name`, `level`, `class_slug`, `race_slug`, `dex_mod`, `hp_max`, `created_at`, `updated_at`.
- **Columna `data` (JSON):** Estructura rica con:
  - `stats`: Las 6 características base (`strength`, `dexterity`, `constitution`, `intelligence`, `wisdom`, `charisma`).
  - `modifiers`: Los 6 modificadores calculados (`str_mod`, `dex_mod`, `con_mod`, `int_mod`, `wis_mod`, `cha_mod`).
  - `proficiency_bonus`: Bono de competencia según el nivel (+2 a +6).
  - `armor_class`: Clase de armadura (por defecto 10 + dex_mod o armadura equipada).
  - `speed` y `size`: Provenientes de la raza elegida en el SRD.
  - `hit_die`: Dado de golpe de la clase en el SRD (ej. d10 para Guerrero, d6 para Mago).
  - `weapons`: Lista de armas con daño (`1d8`), tipo de daño (`slashing`/cortante), y cálculo de bono de ataque.
  - `spells`: Lista de conjuros con nivel, escuela mágica, alcance, CD de salvación y bono de ataque mágico.

---

## 4. Cálculos Automáticos en Backend

### Decisión
El endpoint `POST /api/characters` y `PUT /api/characters/{id}` calcula y valida automáticamente los valores derivados si no se proporcionan explícitamente:
- **Modificadores:** `floor((score - 10) / 2)`.
- **Competencia:** `((level - 1) // 4) + 2`.
- **Puntos de Golpe Máximos:** `hit_die + con_mod + (level - 1) * (hit_die // 2 + 1 + con_mod)`.
- **Magia:** Si la clase tiene aptitud mágica (ej. Mago con Inteligencia, Clérigo con Sabiduría), se calculan automáticamente:
  - `spell_dc`: `8 + prof_bonus + mod`.
  - `spell_attack_bonus`: `prof_bonus + mod`.

---

## 5. Visualización de Armas y Conjuros en la UI

### Decisión
- **Armas:** Se muestran en tarjetas que desglosan nombre, daño base con tipo y bono de tirada de ataque calculado considerando si el arma tiene la propiedad `finesse` (usa el mayor entre Destreza y Fuerza) y la competencia.
- **Conjuros:** Se muestran con insignias destacadas de CD de Salvación y Ataque Mágico en la parte superior, seguidas por una lista de conjuros con su nivel (o "Truco"), escuela de magia y alcance.

---

## 6. Sincronización con el Combate Activo

### Decisión
Se implementó el endpoint `POST /api/me/link-character` y un botón "⚔️ Vincular a Combate" en la ficha. Al activarse, actualiza el combatiente del jugador en `combatants` con el `character_id`, actualiza su `hp_max` y su nombre, y emite un broadcast inmediato por WebSocket a toda la mesa.
