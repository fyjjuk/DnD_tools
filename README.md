# MVP · Combate D&D 5e en LAN

Tracker de iniciativa y HP para dirigir combates de D&D 5e desde una sola
laptop Linux, con los jugadores conectados desde el móvil en la misma red.

Sin servicios externos. Sin frameworks de frontend. Sin build step.

## Requisitos

- Python 3.10+
- Los móviles y la laptop en la MISMA red Wi-Fi / LAN

## Instalación (una sola vez)

```bash
cd /home/fyjjuk/DnD_MVP
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Arrancar el servidor

```bash
cd /home/fyjjuk/DnD_MVP
source .venv/bin/activate
python run.py
```

Verás algo como:

```text
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Averiguar la IP de la laptop

La app está pensada para LAN doméstica con **DHCP**: la IP cambia cuando te
conectas a otra red o cuando el router renueva la concesión. No la
memorices; la propia app la muestra en el panel **Compartir** de
`/campaigns` y en el botón **Compartir** de `/dm`.

Si aun así la necesitas a mano:

```bash
ip -4 addr show scope global | grep inet
```

La primera IPv4 (típicamente `192.168.x.x` o `10.x.x.x`) es la que sirve
la app.

## Conectarse

La URL depende de la IP de la laptop en cada red (DHCP). Para no teclearla:

1. Desde la laptop, abre `/campaigns` y pulsa **Compartir** en la tarjeta
   de tu campaña. Si estás dentro de `/dm`, pulsa **Compartir** en la
   barra superior (misma información, en un modal).
2. En el panel verás la URL actual, un botón **Copiar URL**, el código
   de campaña y un **QR**.
3. El jugador **escanea el QR con el móvil sin teclear nada** (o recibe
   la URL por el canal que uses, p. ej. WhatsApp) y la abre. El campo
   *Unirse por código* llega ya prellenado con el código de la campaña
   (`?code=XXXXXX`).
4. Si el jugador prefiere el flujo legacy sin cuenta, comparte el
   **código de sesión** que aparece en `/dm` y pídele que entre por
   `/player`.

Rutas fijas (solo cambia el host, no el path):

| Quién             | Ruta           |
|-------------------|----------------|
| DM                | `/dm`          |
| Jugador legacy    | `/player`      |
| Cuenta y campañas | `/login`, `/register`, `/campaigns` |

## Acceso con cuenta (Fase 2.1)

Ademas del flujo legacy con contrasena de DM y codigo de sesion,
ahora hay entrada con cuenta para DM y jugador. Los flujos legacy
siguen funcionando exactamente igual que en Fase 1 (el gate solo
enruta al inicio, no cambia el combate).

### DM con cuenta

1. Abre `/register` (o `/login`) y crea/usa tu cuenta.
2. Ve a `/campaigns` y crea una campana (o abre una existente).
3. Pulsa **Abrir consola DM** en la tarjeta de la campana.
   - Si no habia sesion activa, se crea una.
   - Si ya habia una, se reutiliza (idempotente).
4. El backend devuelve el `dm_token` de esa sesion y el frontend
   lo guarda en `localStorage.dnd_dm_token`. Redirige a `/dm`.
5. A partir de ahi, `/dm` funciona igual que en el flujo legacy.

### Jugador con cuenta

1. Abre `/login` y entra con tu cuenta.
2. Ve a `/campaigns` y unete por codigo a la campana del DM
   (el codigo de **CAMPANA** de 6 letras, no el de sesion).
3. Cuando el DM tenga una sesion activa, aparecera **Unirme a sesion**
   en la tarjeta de la campana.
4. Al pulsarlo, el backend devuelve (o crea) un `player_token` y el
   frontend lo guarda en `localStorage.dnd_player_token`. Redirige a
   `/player`.
5. Si hay un combatiente PC con el mismo nombre que tu
   `display_name`, se vincula solo. Si no, pidele al DM que te asigne.

### DM recovery con contrasena

Si has perdido el acceso a la cuenta del DM, abre `/dm-login` e
introduce la contrasena de DM (`DND_DM_PASSWORD`). El
formulario llama a `/api/dm/bootstrap`, guarda el `dm_token` y
redirige a `/dm`.

Ese mismo `/dm-login` esta enlazado desde `/campaigns` (footer) y
desde `/dm` (cuando no hay token en localStorage).

### Reset de la contrasena del user `dm`

Si cambias `DND_DM_PASSWORD` o ejecutas `set_dm_password` y quieres
que el login por cuenta (`/login` como usuario `dm`) acepte la nueva
contrasena, ejecuta con el servidor parado:

```bash
python -m backend.reset_dm_password
# o si quieres resetear directamente desde la DB:
python -m backend.set_dm_password
```

El flujo legacy `/api/dm/bootstrap` **no** necesita este script:
lee `DND_DM_PASSWORD` del entorno en cada request.

## Flujo de uso

1. El DM abre `/dm`. Se crea automáticamente una sesión y aparece un
   código de 6 caracteres en la cabecera.

2. Cada jugador abre `/player` en el móvil, escribe el código y su
   nombre (idealmente el mismo nombre que tendrá su PJ).

3. El DM añade combatientes (nombre, HP máximo, iniciativa, PJ o Enemigo).
   - Si el nombre coincide con un jugador ya unido, se vinculan solos.
   - Si no, el DM puede vincularlo desde el desplegable de la fila.

4. El DM usa −10/−5/−1/+1/+5/+10 para daño/curación rápida,
   `Siguiente turno` y `Siguiente ronda`.

5. Los jugadores ven el orden de iniciativa, el turno actual, y solo su
   propio HP, con botones para dañarse/curarse a sí mismos.
   El HP de los enemigos nunca se envía a sus dispositivos.

6. Cerrar sesión guarda `data/logs/session_<CODIGO>.log` con todos
   los eventos (daño, curación, muertes, cambios de turno) y termina la sesión.

## Persistencia

- Estado en `data/dnd.db` (SQLite, modo WAL).
- Si cierras el navegador del DM y vuelves a `/dm`, la sesión activa
  se recupera automáticamente con su código y su combate en curso.
- El log de cada sesión cerrada queda en `data/logs/session_<CODIGO>.log`.

## Configuración

Todo en un único archivo: `config.py`

```python
PORT = 8000                                          # puerto HTTP
DB_PATH = os.path.join(BASE_DIR, "data", "dnd.db")   # ruta SQLite
```

### Contraseña de DM

La contraseña de recovery DM **NO** va en el repo. Se configura con
la variable de entorno `DND_DM_PASSWORD` o con el script:

```
DND_DM_PASSWORD='tu-clave' python run.py
# o:
python -m backend.set_dm_password
```

Sin `DM_PASSWORD` configurada, `/dm-login` devuelve 500 con mensaje
claro. El registro con `username='dm'` está reservado (409).

`DM_PASSWORD` protege la consola del DM. `/api/dm/bootstrap` exige
`{password}` que coincida con `DM_PASSWORD`. En el navegador del DM,
la primera visita muestra un formulario de contraseña; tras entrar,
la contraseña queda en `sessionStorage` (se borra al cerrar la
pestaña) y el `dm_token` en `localStorage`.

## Bestiario SRD (Fase 1)

El MVP integra el bestiario del **SRD 5e (2014) en español**. En esta fase
solo se importa la colección **Monsters** (334 registros). El resto de
colecciones (hechizos, equipo, niveles, dotes...) quedan para una fase
posterior.

### Importar

Con el servidor **parado** (para evitar bloqueos WAL de SQLite):

```bash
cd /home/fyjjuk/DnD_MVP
source .venv/bin/activate
python scripts/import_srd.py
```

Salida esperada:

```
Fuente:     /home/fyjjuk/DnD/raw/srd-2014/es/5e-SRD-Monsters.json
SHA-256:    <hash>
Registros:  334
Insertados: 334
Errores:    0
```

Caracteristicas:

- **Idempotente**: se puede correr varias veces. Recrea la tabla `monsters`
  y las filas de `collections`/`import_meta` con slug `monsters`. **No toca**
  `sessions`, `players`, `combatants`, `events`.
- Cada registro se intenta insertar por separado; si uno falla, se anota en
  `import_meta.errors_json` y se sigue con el resto.
- Guarda `armor_class[0].value` -> `armor_class` y `armor_class[0].type` ->
  `armor_class_type`. El registro completo va en la columna `data` (JSON).

La ruta del SRD se configura en `config.py`:

```python
SRD_DIR = "/home/fyjjuk/DnD/raw/srd-2014/es"
```

Tambien se puede sobreescribir con `--srd-dir`:

```bash
python scripts/import_srd.py --srd-dir /otra/ruta/es/
```

### Verificar

```bash
python scripts/verify_srd.py
```

Ejecuta las queries del checklist seccion 7 del informe v2 (las aplicables
a `monsters`; las de spells/equipment/levels se marcan como `SKIP`). Imprime
`OK`/`FALLO` por cada una y termina con `N/M OK`. Codigo de salida != 0 si
algo falla.

### Autocompletado en `/dm`

En el panel **Nuevo combatiente** hay un campo «Buscar monstruo SRD» con
un `<datalist>` que consulta `GET /api/srd/monsters?q=...` (debounce 200 ms,
minimo 2 caracteres).

- Al seleccionar un monstruo se rellenan `Nombre` y `HP max`, y se sugiere
  `Iniciativa = 10 + floor((DES-10)/2)`.
- Se envia `srd_index` en el `POST /api/combatants` **solo** si el monstruo
  se eligio del datalist. Si el DM escribe el nombre a mano, no se envia.
- El backend (`POST /api/combatants`) rellena `name`/`hp_max` desde
  `monsters` **solo si** el cliente no los envia. Si los envia, se respetan.
- Si el DM modifica el nombre tras seleccionar un monstruo, se sigue
  enviando `srd_index` -- el backend respeta el nombre editado (los campos
  ya vienen rellenos).

### Si `raw/srd-2014/es/` no existe

- El servidor arranca igual. `init_db()` crea las tablas del MVP.
- `GET /api/srd/monsters` captura `sqlite3.OperationalError` («no such
  table») y devuelve `{"items": []}`.
- El datalist aparece vacio hasta que importes el JSON. El flujo manual
  (nombre + HP a mano) sigue funcionando igual que antes.

## Sincronización

WebSocket en `/ws`. Cada mutación (REST) dispara un broadcast inmediato
del estado completo a todos los clientes de la sesión. En LAN la latencia es
de milisegundos. Si un cliente pierde la conexión, reconecta solo y al
conectarse recibe el estado actual de inmediato.

## API (referencia rápida)

```text
POST   /api/dm/bootstrap              {password} -> {code, dm_token, session_id}
POST   /api/join                      {code, name} -> {token, player_id}
GET    /api/player/me                 (header X-Player-Token)
POST   /api/me/hp                     {delta} (header X-Player-Token)

POST   /api/combatants                {name?,hp_max?,initiative,kind,srd_index?}  (X-DM-Token)
DELETE /api/combatants/{id}                                          (X-DM-Token)
POST   /api/combatants/{id}/hp        {delta | set_to}               (X-DM-Token)
POST   /api/combatants/{id}/link      {player_id}                    (X-DM-Token)
POST   /api/combatants/{id}/undo-hp                                  (X-DM-Token)
POST   /api/turn/next                                                (X-DM-Token)
POST   /api/turn/round                                               (X-DM-Token)
POST   /api/session/close                                            (X-DM-Token)

GET    /api/sessions/closed                                          (X-DM-Token, acepta token de sesion cerrada)
GET    /api/sessions/{code}/log                                      (X-DM-Token, acepta token de sesion cerrada)

GET    /api/srd/monsters?q=&cr_min=&cr_max=&type=&size=&limit=50     (sin token)
GET    /api/srd/monsters/{index}                                     (sin token)

WS     /ws?role=dm&token=...  |  /ws?role=player&token=...
```

## Test manual: fix de ronda cuando queda 1 vivo

1. Abre `/dm`, entra con la contraseña de DM. Anota la ronda inicial (1).
2. Crea 3 combatientes:
   - `A` (PJ, iniciativa 15, HP 10)
   - `B` (enemigo, iniciativa 10, HP 10)
   - `C` (enemigo, iniciativa 5, HP 10)
3. El turno debe estar en `A` (mayor iniciativa).
4. Baja el HP de `B` y `C` a 0 (botón `−10` un par de veces en cada uno). Ambos quedan `CAÍDO`.
5. Pulsa **Siguiente turno** 3 o 4 veces seguidas.
6. **Resultado esperado**:
   - El turno sigue en `A` (único vivo).
   - La ronda **NO** avanza (se queda en 1).
7. **Bug corregido**: antes, cada click incrementaba la ronda (1→2→3→…) aunque el
   turno seguía en `A`, porque el código contaba la "vuelta sobre los caídos" como
   ronda completa. Con el fix, si el siguiente vivo es el mismo que tenía el turno,
   `wrapped` queda en `False` y la ronda no cambia.

## Notas de operación

- Tras cerrar una sesión con **Cerrar sesión**, el DM ve un toast con la ruta
  del `.log` (`data/logs/session_<CODIGO>.log`) y la sección **Sesiones
  anteriores** se refresca para permitir leerlo in-app.
- El botón **Recuperar sesión** vuelve a pedir la contraseña de DM y refresca
  el `dm_token`. Si la sesión activa sigue viva, devuelve el mismo token
  (no-op). Si fue cerrada desde otra pestaña y hay otra activa, adopta la
  nueva. Si no hay ninguna activa, crea una nueva.
- El botón **↶** en cada fila deshace el último cambio de HP de ese
  combatiente. El historial no se borra: la fila queda marcada con
  `undone=1` en `hp_history`.
- Tras aplicar estos cambios, recarga el navegador del DM con
  `Ctrl+Shift+R` (o vacía caché) para que cargue el `dm.js` nuevo: si no,
  el `POST /api/dm/bootstrap` del JS antiguo se queda sin `password` y
  devolverá 403.

## Problemas típicos

- **El móvil no carga la página**: revisa que esté en la misma red y que el
  firewall de la laptop permita el puerto (`sudo ufw allow 8000/tcp`
  si usas ufw).

- **"Código de sesión inválido"**: el DM debe tener la sesión abierta y el
  código se escribe sin espacios.

- **"Tu PJ no está en el combate"**: el DM debe crear un combatiente de tipo
  PJ con tu nombre exacto, o vincularlo manualmente.

## Tests E2E (dev-only)

Los tests end-to-end de la Fase 2.1 requieren Selenium y un Chrome/Chromium
instalado. **No** van a producción; instálalos solo en el venv de
desarrollo:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Arranca el servidor en otra terminal:

```bash
python run.py
```

Y ejecuta:

```bash
python scripts/test_e2e_fase_2_1.py            # headless
python scripts/test_e2e_fase_2_1.py --headful  # ver el navegador
```

El script cierra al inicio cualquier sesión huérfana (`status='active'`
antigua) para poder re-ejecutarse sin reiniciar el servidor. Al terminar
imprime `N/M PASS` y sale con código != 0 si algún check falla.

## Limitaciones conocidas (a propósito)

- Una sola sesión activa a la vez.
- Sin autenticación real: los tokens son suficientes para una mesa de
  confianza en LAN.
- Sin edición de iniciativa: borra y vuelve a añadir si te equivocas.
- No hay biblioteca, notas, hojas de personaje ni SRD.
- El bestiario SRD solo cubre `Monsters` (Fase 1). El resto de colecciones
  queda para Fase 2. La ficha de personaje sigue sin existir.
