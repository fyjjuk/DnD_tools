const TOKEN_KEY = "dnd_player_token";
const $ = (id) => document.getElementById(id);

let playerToken = localStorage.getItem(TOKEN_KEY);
let state = null;
let socket = null;
let playerInfo = null;
let currentCharacter = null;
let userCharacters = [];
let srdCache = { classes: null, races: null, weapons: null, spells: null };

function showJoin() {
  $("join-view").classList.remove("hidden");
  $("combat-view").classList.add("hidden");
}

function showCombat() {
  $("join-view").classList.add("hidden");
  $("combat-view").classList.remove("hidden");
}

(async function init() {
  const userToken = localStorage.getItem("dnd_user_token");
  if (playerToken) {
    try {
      const headers = { "X-Player-Token": playerToken };
      if (userToken) headers["X-User-Token"] = userToken;
      playerInfo = await API.get("/api/player/me", headers);
      showCombat();
      openSocket();
      initTabs();
      return;
    } catch (err) {
      localStorage.removeItem(TOKEN_KEY);
      playerToken = null;
    }
  }
  if (userToken) {
    window.location.href = "/campaigns";
    return;
  }
  showJoin();
})();

function initTabs() {
  const tabCombat = $("tab-combat");
  const tabSheet = $("tab-sheet");
  const paneCombat = $("pane-combat");
  const paneSheet = $("pane-sheet");

  if (!tabCombat || !tabSheet) return;

  tabCombat.addEventListener("click", () => {
    tabCombat.classList.add("active");
    tabSheet.classList.remove("active");
    paneCombat.classList.remove("hidden");
    paneSheet.classList.add("hidden");
  });

  tabSheet.addEventListener("click", () => {
    tabSheet.classList.add("active");
    tabCombat.classList.remove("active");
    paneCombat.classList.add("hidden");
    paneSheet.classList.remove("hidden");
    loadAndRenderSheet();
  });
}

function openSocket() {
  if (socket) socket.close();
  socket = connectWS("player", playerToken, (next) => {
    state = next;
    render();
  }, () => {
    localStorage.removeItem(TOKEN_KEY);
    playerToken = null;
    if (localStorage.getItem("dnd_user_token")) {
      window.location.href = "/campaigns";
    } else {
      showJoin();
    }
  });
}

function render() {
  if (!state) return;

  $("p-code").textContent = state.session.code;
  $("p-round").textContent = state.session.round;

  if (state.session.status !== "active") {
    $("p-turn").innerHTML = "La sesión ha terminado.";
    $("p-me").innerHTML = `
      <h2>Tu personaje</h2>
      <p class="hp-text">La sesión fue cerrada por el DM.</p>
      <div class="c-actions">
        <button id="btn-rejoin" class="primary">Unirse a otra sesión</button>
      </div>
    `;
    $("p-list").innerHTML = "";
    const rejoin = $("btn-rejoin");
    if (rejoin) {
      rejoin.addEventListener("click", () => {
        if (socket) socket.close();
        localStorage.removeItem(TOKEN_KEY);
        playerToken = null;
        if (localStorage.getItem("dnd_user_token")) {
          window.location.href = "/campaigns";
        } else {
          state = null;
          $("j-code").value = "";
          $("j-name").value = "";
          showJoin();
        }
      });
    }
    return;
  }

  const current = state.combatants.find((c) => c.id === state.session.turn_combatant_id);
  $("p-turn").innerHTML = current
    ? `Turno de <span class="who">${escapeHtml(current.name)}</span>`
    : "Esperando inicio del combate…";

  renderMe();
  renderList();
  renderInitiativeModal();
  renderCheckModal();
}

let rollingInitiative = false;

function renderInitiativeModal() {
  const modal = $("initiative-modal");
  if (!modal) return;
  const req = state.initiative_request;
  if (!req || req.status !== "active") {
    modal.classList.add("hidden");
    rollingInitiative = false;
    return;
  }

  // Buscar si mi combatiente tiene tirada pendiente
  const myCombatant = state.combatants.find(c => c.is_me);
  if (!myCombatant) {
    modal.classList.add("hidden");
    return;
  }

  const myRoll = req.rolls ? req.rolls.find(r => r.combatant_id === myCombatant.id) : null;
  if (!myRoll || myRoll.status !== "pending") {
    modal.classList.add("hidden");
    rollingInitiative = false;
    return;
  }

  modal.classList.remove("hidden");
  $("init-modal-info").textContent = `¡El DM ha pedido iniciativa! Tira 1d20 para ${myCombatant.name} (Mod DES: ${myRoll.dex_mod >= 0 ? '+' : ''}${myRoll.dex_mod})`;
  $("init-modal-result").textContent = "";
  const btn = $("btn-roll-d20");
  btn.disabled = rollingInitiative;

  btn.onclick = async () => {
    if (rollingInitiative) return;
    rollingInitiative = true;
    btn.disabled = true;

    const diceDisplay = $("init-dice-display");
    const faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];
    let animCount = 0;
    const interval = setInterval(() => {
      diceDisplay.textContent = faces[Math.floor(Math.random() * faces.length)];
      animCount++;
      if (animCount > 10) clearInterval(interval);
    }, 80);

    setTimeout(async () => {
      const rollValue = Math.floor(Math.random() * 20) + 1;
      diceDisplay.textContent = `🎲 ${rollValue}`;
      const userToken = localStorage.getItem("dnd_user_token");
      try {
        const res = await API.post(
          "/api/initiative/roll",
          {
            request_id: req.id,
            combatant_id: myCombatant.id,
            roll_value: rollValue,
          },
          { "X-User-Token": userToken || "" }
        );
        $("init-modal-result").textContent = `Resultado: ${rollValue} + ${res.dex_mod} = ${res.total}`;
        setTimeout(() => {
          modal.classList.add("hidden");
          rollingInitiative = false;
        }, 1200);
      } catch (err) {
        $("init-modal-result").textContent = "Error: " + err.message;
        rollingInitiative = false;
        btn.disabled = false;
      }
    }, 900);
  };
}

let rollingCheck = false;

function renderCheckModal() {
  const modal = $("check-modal");
  if (!modal) return;
  const req = state.check_request;
  if (!req || req.status !== "active") {
    modal.classList.add("hidden");
    rollingCheck = false;
    return;
  }

  const myCombatant = state.combatants.find(c => c.is_me);
  if (!myCombatant) {
    modal.classList.add("hidden");
    return;
  }

  const myRoll = req.rolls ? req.rolls.find(r => r.combatant_id === myCombatant.id) : null;
  if (!myRoll || myRoll.status !== "pending") {
    modal.classList.add("hidden");
    rollingCheck = false;
    return;
  }

  modal.classList.remove("hidden");
  const checkTitle = req.skill_name ? `${req.skill_name} (${req.ability_name})` : `Prueba de ${req.ability_name}`;
  const dcText = req.dc !== null && req.dc !== undefined ? ` · CD ${req.dc}` : "";
  const advText = req.advantage_mode === "advantage" ? " · Con Ventaja (2d20)" : req.advantage_mode === "disadvantage" ? " · Con Desventaja (2d20)" : "";

  $("check-modal-title").textContent = `🎯 ${checkTitle}`;
  $("check-modal-info").textContent = `El DM solicita una tirada para ${myCombatant.name}.${dcText}${advText}\nModificador: ${myRoll.total_mod >= 0 ? '+' : ''}${myRoll.total_mod} (${myRoll.is_proficient ? 'Competente' : 'Sin competencia'})`;
  $("check-modal-result").textContent = "";

  const btn = $("btn-roll-check");
  btn.disabled = rollingCheck;
  const diceCount = req.advantage_mode === "normal" ? "1d20" : "2d20";
  btn.textContent = `¡Tirar ${diceCount}!`;

  btn.onclick = async () => {
    if (rollingCheck) return;
    rollingCheck = true;
    btn.disabled = true;

    const diceDisplay = $("check-dice-display");
    const faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];
    let animCount = 0;
    const interval = setInterval(() => {
      if (req.advantage_mode === "normal") {
        diceDisplay.textContent = faces[Math.floor(Math.random() * faces.length)];
      } else {
        diceDisplay.textContent = `${faces[Math.floor(Math.random() * faces.length)]}  ${faces[Math.floor(Math.random() * faces.length)]}`;
      }
      animCount++;
      if (animCount > 10) clearInterval(interval);
    }, 80);

    setTimeout(async () => {
      const r1 = Math.floor(Math.random() * 20) + 1;
      let r2 = null;
      if (req.advantage_mode !== "normal") {
        r2 = Math.floor(Math.random() * 20) + 1;
        diceDisplay.textContent = `🎲 ${r1}  |  🎲 ${r2}`;
      } else {
        diceDisplay.textContent = `🎲 ${r1}`;
      }

      const userToken = localStorage.getItem("dnd_user_token");
      try {
        const res = await API.post(
          "/api/check/roll",
          {
            request_id: req.id,
            combatant_id: myCombatant.id,
            roll_value_1: r1,
            roll_value_2: r2,
          },
          { "X-User-Token": userToken || "" }
        );

        let resText = `Total: ${res.chosen_roll} + (${res.total_mod}) = ${res.total}`;
        if (res.is_success !== null && res.is_success !== undefined) {
          resText += res.is_success ? " ➔ ¡ÉXITO! 🎉" : " ➔ FALLO 💥";
          $("check-modal-result").style.color = res.is_success ? "#10b981" : "#ef4444";
        } else {
          resText += " ➔ Tirada enviada al DM 🤫";
          $("check-modal-result").style.color = "#0ea5e9";
        }
        $("check-modal-result").textContent = resText;

        setTimeout(() => {
          modal.classList.add("hidden");
          rollingCheck = false;
        }, 1600);
      } catch (err) {
        $("check-modal-result").textContent = "Error: " + err.message;
        $("check-modal-result").style.color = "#ef4444";
        rollingCheck = false;
        btn.disabled = false;
      }
    }, 900);
  };
}

function renderMe() {
  const box = $("p-me");
  const me = state.combatants.find((c) => c.is_me);

  if (!me) {
    box.innerHTML = '<p class="hp-text">El DM todavía no ha vinculado tu personaje. Dile tu nombre exacto o pídele que te asigne.</p>';
    return;
  }

  const pct = me.hp_max > 0
    ? Math.max(0, Math.min(100, (me.hp_current / me.hp_max) * 100))
    : 0;

  box.innerHTML = `
    <h2>Tu personaje</h2>
    <div class="c-name c-name-large">${escapeHtml(me.name)}</div>
    <div class="me-hp">${me.hp_current} / ${me.hp_max} HP</div>
    <div class="hpbar"><div class="hpfill" style="width:${pct}%"></div></div>
    <div class="c-actions">
      <button class="dmg" data-hp="-10">−10</button>
      <button class="dmg" data-hp="-5">−5</button>
      <button class="dmg" data-hp="-1">−1</button>
      <button class="heal" data-hp="1">+1</button>
      <button class="heal" data-hp="5">+5</button>
      <button class="heal" data-hp="10">+10</button>
    </div>
  `;

  box.querySelectorAll("[data-hp]").forEach((btn) => {
    btn.addEventListener("click", () => selfHp(Number(btn.dataset.hp)));
  });
}

function renderList() {
  const container = $("p-list");
  container.innerHTML = "";
  const turnId = state.session.turn_combatant_id;

  for (const c of state.combatants) {
    const row = document.createElement("div");
    row.className = "combatant";
    if (c.id === turnId) row.classList.add("current");
    if (c.dead) row.classList.add("dead");

    const hasHp = c.hp_current !== null && c.hp_current !== undefined;
    const hpLine = hasHp
      ? `<div class="hp-text">${c.hp_current} / ${c.hp_max} HP</div>`
      : "";

    row.innerHTML = `
      <div class="c-head">
        <span class="init">${c.initiative}</span>
        <span class="c-name">${escapeHtml(c.name)}${c.is_me ? " (tú)" : ""}</span>
        <span class="tag ${c.kind}">${c.kind === "pc" ? "PJ" : "ENEMIGO"}</span>
        ${c.id === turnId ? '<span class="turn-tag">TURNO</span>' : ""}
      </div>
      ${hpLine}
    `;
    container.appendChild(row);
  }
}

async function selfHp(delta) {
  try {
    await API.post("/api/me/hp", { delta }, { "X-Player-Token": playerToken });
  } catch (err) { toast(err.message); }
}

$("join-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("join-error").textContent = "";
  try {
    const userToken = localStorage.getItem("dnd_user_token");
    const headers = {};
    if (userToken) headers["X-User-Token"] = userToken;
    const info = await API.post("/api/join", {
      code: $("j-code").value.trim().toUpperCase(),
      name: $("j-name").value.trim(),
    }, headers);
    playerToken = info.token;
    localStorage.setItem(TOKEN_KEY, playerToken);
    playerInfo = await API.get("/api/player/me", { "X-Player-Token": playerToken, ...headers });
    showCombat();
    openSocket();
    initTabs();
  } catch (err) {
    $("join-error").textContent = err.message;
  }
});

/* ================================================================
   Fase 2.3: Panel "Mi Ficha" y Gestión de Personaje
   ================================================================ */

async function ensureSrdData() {
  const promises = [];
  if (!srdCache.classes) {
    promises.push(API.get("/api/srd/classes").then(r => srdCache.classes = r.items || []));
  }
  if (!srdCache.races) {
    promises.push(API.get("/api/srd/races").then(r => srdCache.races = r.items || []));
  }
  if (!srdCache.weapons) {
    promises.push(API.get("/api/srd/equipment?category=weapon&limit=100").then(r => srdCache.weapons = r.items || []));
  }
  if (!srdCache.spells) {
    promises.push(API.get("/api/srd/spells?limit=150").then(r => srdCache.spells = r.items || []));
  }
  await Promise.all(promises);
}

async function loadAndRenderSheet() {
  const container = $("sheet-content");
  if (!container) return;

  const userToken = localStorage.getItem("dnd_user_token");
  const isGuest = !userToken || (playerInfo && playerInfo.user && playerInfo.user.is_guest);

  if (isGuest) {
    container.innerHTML = `
      <div class="guest-sheet-card">
        <div class="guest-icon-badge">🛡️</div>
        <h2 class="guest-title">Estás jugando como Invitado</h2>
        <p class="guest-desc">
          Como invitado puedes participar activamente en el combate y modificar tus puntos de vida en la pestaña <strong>Combate</strong>.
        </p>
        <p class="guest-subtext">
          Para crear y guardar tu <strong>Ficha de Personaje permanente</strong> con todas tus estadísticas, armas y conjuros, crea una cuenta de aventurero.
        </p>
        <div class="guest-btn-group">
          <a href="/register" class="guest-btn-primary">Crear cuenta gratis</a>
          <a href="/login" class="guest-btn-secondary">Iniciar sesión</a>
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = '<div class="sheet-loading">Cargando tu ficha de personaje…</div>';

  try {
    const res = await API.get("/api/characters", { "X-User-Token": userToken });
    userCharacters = res.items || [];

    if (!currentCharacter && userCharacters.length > 0) {
      if (playerInfo && playerInfo.character_id) {
        currentCharacter = userCharacters.find((c) => c.id === playerInfo.character_id);
      }
      if (!currentCharacter) {
        currentCharacter = userCharacters[0];
      }
    }

    if (userCharacters.length === 0 || !currentCharacter) {
      renderCharacterForm(container, null);
    } else {
      renderCharacterSheet(container, currentCharacter);
    }
  } catch (err) {
    container.innerHTML = `<div class="panel error">${escapeHtml(err.message)}</div>`;
  }
}

function renderCharacterSheet(container, char) {
  const d = char.data || {};
  const stats = d.stats || { strength: 10, dexterity: 10, constitution: 10, intelligence: 10, wisdom: 10, charisma: 10 };
  const mods = d.modifiers || {
    str_mod: Math.floor((stats.strength - 10) / 2),
    dex_mod: Math.floor((stats.dexterity - 10) / 2),
    con_mod: Math.floor((stats.constitution - 10) / 2),
    int_mod: Math.floor((stats.intelligence - 10) / 2),
    wis_mod: Math.floor((stats.wisdom - 10) / 2),
    cha_mod: Math.floor((stats.charisma - 10) / 2),
  };
  const prof = d.proficiency_bonus || Math.floor((char.level - 1) / 4) + 2;
  const ac = d.armor_class !== undefined ? d.armor_class : 10 + (char.dex_mod || 0);
  const hpMax = char.hp_max || d.max_hp || 10;
  const speed = d.speed || 30;
  const weapons = d.weapons || [];
  const spells = d.spells || [];
  const curr = d.currency || { cp: 0, sp: 0, ep: 0, gp: 0, pp: 0 };

  function fmtMod(v) {
    return v >= 0 ? `+${v}` : `${v}`;
  }

  let selectorHtml = "";
  if (userCharacters.length > 1) {
    selectorHtml = `
      <div class="sheet-selector-row">
        <span class="label">Cambiar Personaje:</span>
        <select id="sel-char">
          ${userCharacters.map((c) => `<option value="${c.id}" ${c.id === char.id ? "selected" : ""}>${escapeHtml(c.name)} · Nivel ${c.level} ${escapeHtml(c.class_slug || "")}</option>`).join("")}
        </select>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="sheet-container">
      ${selectorHtml}

      <!-- Cabecera Hero -->
      <div class="sheet-header-card">
        <div class="sheet-title-row">
          <div>
            <h1 class="sheet-char-name">${escapeHtml(char.name)}</h1>
            <div class="sheet-char-badges">
              <span class="sheet-badge level">Nivel ${char.level}</span>
              <span class="sheet-badge class-race">${escapeHtml(d.race_name || char.race_slug || "Raza")}</span>
              <span class="sheet-badge class-race">${escapeHtml(d.class_name || char.class_slug || "Clase")}</span>
            </div>
          </div>
          <div class="sheet-header-actions">
            <button id="btn-link-char" class="btn-link-hero small">⚔️ Vincular a Combate</button>
            <button id="btn-edit-char" class="small">✏️ Editar Ficha</button>
            <button id="btn-new-char" class="small">➕ Nuevo PJ</button>
          </div>
        </div>

        <!-- Estadísticas vitales -->
        <div class="sheet-vitals-grid">
          <div class="vital-stat-box hp">
            <span class="label">Puntos de Vida</span>
            <span class="vital-val">${hpMax} HP</span>
          </div>
          <div class="vital-stat-box ac">
            <span class="label">Armadura (CA)</span>
            <span class="vital-val">${ac} CA</span>
          </div>
          <div class="vital-stat-box speed">
            <span class="label">Velocidad</span>
            <span class="vital-val">${speed} ft</span>
          </div>
          <div class="vital-stat-box prof">
            <span class="label">Competencia</span>
            <span class="vital-val">+${prof}</span>
          </div>
        </div>
      </div>

      <!-- Rejilla de 6 Características D&D -->
      <div class="sheet-section">
        <h2 class="sheet-section-title">📊 Características Base</h2>
        <div class="sheet-abilities-grid">
          ${[
            { key: "FUE", name: "Fuerza", score: stats.strength, mod: mods.str_mod },
            { key: "DES", name: "Destreza", score: stats.dexterity, mod: mods.dex_mod },
            { key: "CON", name: "Constitución", score: stats.constitution, mod: mods.con_mod },
            { key: "INT", name: "Inteligencia", score: stats.intelligence, mod: mods.int_mod },
            { key: "SAB", name: "Sabiduría", score: stats.wisdom, mod: mods.wis_mod },
            { key: "CAR", name: "Carisma", score: stats.charisma, mod: mods.cha_mod },
          ].map((s) => `
            <div class="ability-score-card">
              <span class="ability-name">${s.key}</span>
              <span class="ability-mod">${fmtMod(s.mod)}</span>
              <span class="ability-score-pill">${s.score}</span>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- Monedas y Riqueza (Fase 2.4.4) -->
      <div class="sheet-section">
        <div class="sheet-section-header-row">
          <h2 class="sheet-section-title">🪙 Monedas y Riqueza</h2>
          <span id="currency-save-status" class="currency-save-status"></span>
        </div>
        <div class="sheet-currency-grid">
          ${[
            { key: "cp", name: "Cobre (cp)", icon: "🟤", val: curr.cp ?? 0 },
            { key: "sp", name: "Plata (sp)", icon: "⚪", val: curr.sp ?? 0 },
            { key: "ep", name: "Electro (ep)", icon: "🔵", val: curr.ep ?? 0 },
            { key: "gp", name: "Oro (gp)", icon: "🟡", val: curr.gp ?? 0 },
            { key: "pp", name: "Platino (pp)", icon: "🟣", val: curr.pp ?? 0 },
          ].map((c) => `
            <div class="currency-card">
              <div class="currency-header">
                <span class="currency-icon">${c.icon}</span>
                <span class="currency-name">${c.name}</span>
              </div>
              <div class="currency-control">
                <button type="button" class="btn-coin-step btn-coin-minus" data-coin="${c.key}" aria-label="Restar 1 ${c.name}">−</button>
                <input type="number" id="coin-${c.key}" class="coin-input" data-coin="${c.key}" min="0" step="1" value="${c.val}">
                <button type="button" class="btn-coin-step btn-coin-plus" data-coin="${c.key}" aria-label="Sumar 1 ${c.name}">+</button>
              </div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- Armas y Ataques -->
      <div class="sheet-section">
        <h2 class="sheet-section-title">🗡️ Armas y Ataques</h2>
        ${weapons.length === 0 ? `
          <p class="sheet-empty-hint">No tienes armas equipadas en esta ficha.</p>
        ` : `
          <div class="sheet-items-list">
            ${weapons.map((w) => {
              const strMod = mods.str_mod;
              const dexMod = mods.dex_mod;
              const modToUse = (w.properties && w.properties.includes("finesse") && dexMod > strMod) ? dexMod : strMod;
              const atkBonus = w.attack_bonus !== undefined ? w.attack_bonus : (modToUse + prof);
              return `
                <div class="sheet-item-card">
                  <div class="sheet-item-main">
                    <div class="sheet-item-name">🗡️ ${escapeHtml(w.name)}</div>
                    <div class="sheet-item-desc">
                      <span class="sheet-item-pill">Daño: ${escapeHtml(w.damage || w.damage_dice || "1d8")}</span>
                      ${w.damage_type ? `<span class="sheet-item-pill">${escapeHtml(w.damage_type)}</span>` : ""}
                    </div>
                  </div>
                  <div class="sheet-item-stat">
                    <span class="sheet-stat-big">${fmtMod(atkBonus)}</span>
                    <span class="sheet-stat-sub">Bono Ataque</span>
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        `}
      </div>

      <!-- Conjuros y Magia -->
      <div class="sheet-section">
        <h2 class="sheet-section-title">✨ Conjuros y Magia</h2>
        ${d.spell_dc ? `
          <div class="sheet-magic-banner">
            <div class="magic-stat-box">
              <span class="label">CD Salvación de Conjuros</span>
              <div class="magic-stat-val">${d.spell_dc}</div>
            </div>
            <div class="magic-stat-box">
              <span class="label">Bono de Ataque Mágico</span>
              <div class="magic-stat-val">${fmtMod(d.spell_attack_bonus || 0)}</div>
            </div>
          </div>
        ` : ""}
        ${spells.length === 0 ? `
          <p class="sheet-empty-hint">No tienes conjuros registrados en esta ficha.</p>
        ` : `
          <div class="sheet-items-list">
            ${spells.map((s) => `
              <div class="sheet-item-card spell-card">
                <div class="sheet-item-main">
                  <div class="sheet-item-name">✨ ${escapeHtml(s.name)}</div>
                  <div class="sheet-item-desc">
                    <span class="sheet-item-pill">${s.level !== undefined ? (s.level === 0 ? "Truco" : "Nivel " + s.level) : "—"}</span>
                    ${s.school ? `<span class="sheet-item-pill">${escapeHtml(s.school)}</span>` : ""}
                  </div>
                </div>
                ${s.range ? `
                  <div class="sheet-item-stat">
                    <span class="sheet-stat-big sheet-range-val">${escapeHtml(s.range)}</span>
                    <span class="sheet-stat-sub">Alcance</span>
                  </div>
                ` : ""}
              </div>
            `).join("")}
          </div>
        `}
      </div>
    </div>
  `;

  const selChar = $("sel-char");
  if (selChar) {
    selChar.addEventListener("change", () => {
      if (currencySaveTimer) clearTimeout(currencySaveTimer);
      const chosen = userCharacters.find((c) => c.id === Number(selChar.value));
      if (chosen) {
        currentCharacter = chosen;
        renderCharacterSheet(container, chosen);
      }
    });
  }

  // Guardado silencioso de monedas con debounce de 1s
  let currencySaveTimer = null;

  function scheduleCurrencySave() {
    const statusEl = $("currency-save-status");
    if (statusEl) {
      statusEl.textContent = "Guardando…";
      statusEl.className = "currency-save-status saving";
    }

    clearTimeout(currencySaveTimer);
    currencySaveTimer = setTimeout(async () => {
      const userToken = localStorage.getItem("dnd_user_token");
      if (!userToken) return;

      const cp = Math.max(0, parseInt($("coin-cp")?.value, 10) || 0);
      const sp = Math.max(0, parseInt($("coin-sp")?.value, 10) || 0);
      const ep = Math.max(0, parseInt($("coin-ep")?.value, 10) || 0);
      const gp = Math.max(0, parseInt($("coin-gp")?.value, 10) || 0);
      const pp = Math.max(0, parseInt($("coin-pp")?.value, 10) || 0);

      const newCurrency = { cp, sp, ep, gp, pp };
      char.data = char.data || {};
      char.data.currency = newCurrency;

      const payload = {
        name: char.name,
        campaign_id: char.campaign_id,
        level: char.level,
        class_slug: char.class_slug,
        race_slug: char.race_slug,
        dex_mod: char.dex_mod,
        hp_max: char.hp_max,
        data: {
          ...char.data,
          currency: newCurrency,
        },
      };

      try {
        const updated = await API.put(`/api/characters/${char.id}`, payload, { "X-User-Token": userToken });
        if (updated && updated.data) {
          char.data = updated.data;
          const idx = userCharacters.findIndex((c) => c.id === char.id);
          if (idx !== -1) userCharacters[idx].data = updated.data;
        }
        if (statusEl) {
          statusEl.textContent = "Guardado ✓";
          statusEl.className = "currency-save-status saved";
          setTimeout(() => {
            if (statusEl.textContent === "Guardado ✓") {
              statusEl.textContent = "";
              statusEl.className = "currency-save-status";
            }
          }, 2000);
        }
      } catch (err) {
        if (statusEl) {
          statusEl.textContent = "Error al guardar";
          statusEl.className = "currency-save-status error";
        }
        console.error("Error guardando monedas:", err);
      }
    }, 1000);
  }

  ["cp", "sp", "ep", "gp", "pp"].forEach((key) => {
    const input = $(`coin-${key}`);
    if (input) {
      input.addEventListener("input", () => {
        let val = parseInt(input.value, 10);
        if (isNaN(val) || val < 0) {
          if (input.value !== "") input.value = "0";
        }
        scheduleCurrencySave();
      });
      input.addEventListener("change", () => {
        let val = parseInt(input.value, 10);
        if (isNaN(val) || val < 0) val = 0;
        input.value = val;
        scheduleCurrencySave();
      });
    }
  });

  container.querySelectorAll(".btn-coin-step").forEach((btn) => {
    btn.addEventListener("click", () => {
      const coin = btn.dataset.coin;
      const input = $(`coin-${coin}`);
      if (!input) return;
      let val = parseInt(input.value, 10) || 0;
      if (btn.classList.contains("btn-coin-plus")) {
        val += 1;
      } else {
        val = Math.max(0, val - 1);
      }
      input.value = val;
      scheduleCurrencySave();
    });
  });

  const btnLink = $("btn-link-char");
  if (btnLink) {
    btnLink.addEventListener("click", async () => {
      try {
        const userToken = localStorage.getItem("dnd_user_token");
        await API.post("/api/me/link-character", { character_id: char.id }, {
          "X-Player-Token": playerToken,
          "X-User-Token": userToken || "",
        });
        toast(`Ficha vinculada: ${char.name} asignado a este combate`);
        if (playerInfo) playerInfo.character_id = char.id;
      } catch (err) {
        toast("Error vinculando: " + err.message);
      }
    });
  }

  const btnEdit = $("btn-edit-char");
  if (btnEdit) {
    btnEdit.addEventListener("click", () => {
      renderCharacterForm(container, char);
    });
  }

  const btnNew = $("btn-new-char");
  if (btnNew) {
    btnNew.addEventListener("click", () => {
      renderCharacterForm(container, null);
    });
  }
}

async function renderCharacterForm(container, charToEdit) {
  container.innerHTML = '<div class="sheet-loading">Cargando catálogo SRD…</div>';
  await ensureSrdData();

  const isEdit = !!charToEdit;
  const d = (charToEdit && charToEdit.data) || {};
  const stats = d.stats || { strength: 15, dexterity: 14, constitution: 13, intelligence: 12, wisdom: 10, charisma: 8 };

  const classes = srdCache.classes || [];
  const races = srdCache.races || [];
  const weapons = srdCache.weapons || [];
  const spells = srdCache.spells || [];

  const initialClass = (charToEdit && charToEdit.class_slug) || (classes[0] && classes[0].index) || "fighter";
  const initialRace = (charToEdit && charToEdit.race_slug) || (races[0] && races[0].index) || "human";
  const initialWeapon = (d.weapons && d.weapons[0] && d.weapons[0].equipment_slug) || (weapons[0] && weapons[0].index) || "";
  const initialSpell = (d.spells && d.spells[0] && d.spells[0].spell_slug) || "";

  container.innerHTML = `
    <div class="sheet-form-card">
      <h2 class="sheet-form-title">${isEdit ? "✏️ Editar Ficha de Personaje" : "✨ Crear Nueva Ficha de Personaje"}</h2>
      <form id="char-form">
        <!-- Fila 1: Identidad básica -->
        <div class="form-field-group">
          <label>Identidad del Personaje</label>
          <div class="form-row-identity">
            <div>
              <input id="f-name" value="${escapeHtml((charToEdit && charToEdit.name) || "")}" placeholder="Nombre (ej. Valeros, Mialee...)" required maxlength="60">
            </div>
            <div>
              <input id="f-level" type="number" min="1" max="20" value="${(charToEdit && charToEdit.level) || 1}" required placeholder="Nivel">
            </div>
            <div>
              <select id="f-class">
                ${classes.map((c) => `<option value="${c.index}" ${c.index === initialClass ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("")}
              </select>
            </div>
            <div>
              <select id="f-race">
                ${races.map((r) => `<option value="${r.index}" ${r.index === initialRace ? "selected" : ""}>${escapeHtml(r.name)}</option>`).join("")}
              </select>
            </div>
          </div>
        </div>

        <!-- Fila 2: Puntuaciones de Característica -->
        <div class="form-field-group">
          <label>Puntuaciones de Característica (1 - 30)</label>
          <div class="form-scores-grid">
            <div class="score-input-card">
              <span>Fuerza (FUE)</span>
              <input id="f-str" type="number" min="1" max="30" value="${stats.strength}">
            </div>
            <div class="score-input-card">
              <span>Destreza (DES)</span>
              <input id="f-dex" type="number" min="1" max="30" value="${stats.dexterity}">
            </div>
            <div class="score-input-card">
              <span>Constitución (CON)</span>
              <input id="f-con" type="number" min="1" max="30" value="${stats.constitution}">
            </div>
            <div class="score-input-card">
              <span>Inteligencia (INT)</span>
              <input id="f-int" type="number" min="1" max="30" value="${stats.intelligence}">
            </div>
            <div class="score-input-card">
              <span>Sabiduría (SAB)</span>
              <input id="f-wis" type="number" min="1" max="30" value="${stats.wisdom}">
            </div>
            <div class="score-input-card">
              <span>Carisma (CAR)</span>
              <input id="f-cha" type="number" min="1" max="30" value="${stats.charisma}">
            </div>
          </div>
        </div>

        <!-- Fila 3: Arma Principal -->
        <div class="form-field-group">
          <label>Arma Principal</label>
          <select id="f-weapon">
            <option value="">-- Sin arma --</option>
            ${weapons.map((w) => `<option value="${w.index}" ${w.index === initialWeapon ? "selected" : ""}>${escapeHtml(w.name)} (${w.damage ? w.damage.damage_dice : ""})</option>`).join("")}
          </select>
        </div>

        <!-- Fila 4: Conjuro Principal -->
        <div class="form-field-group">
          <label>Conjuro Principal (Opcional)</label>
          <select id="f-spell">
            <option value="">-- Sin conjuro --</option>
            ${spells.map((s) => `<option value="${s.index}" ${s.index === initialSpell ? "selected" : ""}>${escapeHtml(s.name)} (Nivel ${s.level === 0 ? "Truco" : s.level})</option>`).join("")}
          </select>
        </div>

        <p id="f-error" class="error"></p>

        <div class="form-actions-row">
          <button type="submit" class="primary">${isEdit ? "Guardar Cambios" : "Crear Ficha"}</button>
          ${isEdit ? '<button id="btn-cancel-edit" type="button">Cancelar</button>' : ""}
        </div>
      </form>
    </div>
  `;

  if (isEdit) {
    const btnCancel = $("btn-cancel-edit");
    if (btnCancel) {
      btnCancel.addEventListener("click", () => renderCharacterSheet(container, charToEdit));
    }
  }

  $("char-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("f-error").textContent = "";

    const userToken = localStorage.getItem("dnd_user_token");
    if (!userToken) {
      $("f-error").textContent = "Debes iniciar sesión para guardar una ficha.";
      return;
    }

    const name = $("f-name").value.trim();
    const level = Number($("f-level").value) || 1;
    const classSlug = $("f-class").value;
    const raceSlug = $("f-race").value;
    const scores = {
      strength: Number($("f-str").value) || 10,
      dexterity: Number($("f-dex").value) || 10,
      constitution: Number($("f-con").value) || 10,
      intelligence: Number($("f-int").value) || 10,
      wisdom: Number($("f-wis").value) || 10,
      charisma: Number($("f-cha").value) || 10,
    };

    const weaponSlug = $("f-weapon").value;
    const spellSlug = $("f-spell").value;

    const weaponsList = [];
    if (weaponSlug) {
      const wObj = weapons.find((w) => w.index === weaponSlug);
      weaponsList.push({
        equipment_slug: weaponSlug,
        name: wObj ? wObj.name : weaponSlug,
        damage: wObj && wObj.damage ? wObj.damage.damage_dice : "1d8",
        damage_type: wObj && wObj.damage && wObj.damage.damage_type ? wObj.damage.damage_type.name : "",
        properties: (wObj && wObj.properties && wObj.properties.map((p) => p.index)) || [],
        proficient: true,
      });
    }

    const spellsList = [];
    if (spellSlug) {
      const sObj = spells.find((s) => s.index === spellSlug);
      spellsList.push({
        spell_slug: spellSlug,
        name: sObj ? sObj.name : spellSlug,
        level: sObj ? sObj.level : 1,
        school: sObj && sObj.school ? sObj.school.name : "",
        range: sObj ? sObj.range : "",
      });
    }

    const payload = {
      name,
      level,
      class_slug: classSlug,
      race_slug: raceSlug,
      campaign_id: (playerInfo && playerInfo.campaign_id) || null,
      data: {
        ...(charToEdit ? charToEdit.data : {}),
        stats: scores,
        weapons: weaponsList,
        spells: spellsList,
        currency: (charToEdit && charToEdit.data && charToEdit.data.currency) || { cp: 0, sp: 0, ep: 0, gp: 0, pp: 0 },
      },
    };

    try {
      let savedChar;
      if (isEdit) {
        savedChar = await API.put(`/api/characters/${charToEdit.id}`, payload, { "X-User-Token": userToken });
        toast("Ficha actualizada");
      } else {
        savedChar = await API.post("/api/characters", payload, { "X-User-Token": userToken });
        toast("Ficha creada con éxito");
        // Auto-vincular al combate actual si estamos en una sesión
        if (playerToken) {
          try {
            await API.post("/api/me/link-character", { character_id: savedChar.id }, {
              "X-Player-Token": playerToken,
              "X-User-Token": userToken,
            });
            if (playerInfo) playerInfo.character_id = savedChar.id;
          } catch (ign) {}
        }
      }

      currentCharacter = savedChar;
      const res = await API.get("/api/characters", { "X-User-Token": userToken });
      userCharacters = res.items || [savedChar];
      renderCharacterSheet(container, savedChar);
    } catch (err) {
      $("f-error").textContent = err.message;
    }
  });
}


