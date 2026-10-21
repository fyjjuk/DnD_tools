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
    tabCombat.style.borderBottomColor = "var(--accent)";
    tabCombat.style.color = "var(--text)";

    tabSheet.classList.remove("active");
    tabSheet.style.borderBottomColor = "transparent";
    tabSheet.style.color = "var(--muted)";

    paneCombat.classList.remove("hidden");
    paneSheet.classList.add("hidden");
  });

  tabSheet.addEventListener("click", () => {
    tabSheet.classList.add("active");
    tabSheet.style.borderBottomColor = "var(--accent)";
    tabSheet.style.color = "var(--text)";

    tabCombat.classList.remove("active");
    tabCombat.style.borderBottomColor = "transparent";
    tabCombat.style.color = "var(--muted)";

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
    <div class="c-name" style="font-size:20px">${escapeHtml(me.name)}</div>
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
      <div class="panel" style="text-align:center;padding:28px 16px;">
        <div style="font-size:42px;margin-bottom:12px;">🛡️</div>
        <h2 style="font-size:19px;color:var(--accent);margin-bottom:8px;text-transform:none;">Estás jugando como Invitado</h2>
        <p style="color:var(--text);margin-bottom:12px;font-size:15px;line-height:1.5;">
          Como invitado puedes seguir participando en este combate y modificando tus puntos de vida normalmente en la pestaña <strong>Combate</strong>.
        </p>
        <p style="color:var(--muted);font-size:13px;margin-bottom:22px;max-width:380px;margin-left:auto;margin-right:auto;">
          Para guardar una <strong>Ficha de Personaje permanente</strong> con tus estadísticas, armas y conjuros, necesitas una cuenta de aventurero.
        </p>
        <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
          <a href="/register" style="padding:10px 20px;border-radius:9px;background:var(--accent);color:#191d27;text-decoration:none;font-weight:700;">Crear cuenta gratis</a>
          <a href="/login" style="padding:10px 20px;border-radius:9px;background:var(--panel-2);color:var(--text);border:1px solid var(--border);text-decoration:none;font-weight:600;">Iniciar sesión</a>
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = '<div style="text-align:center;padding:30px;color:var(--muted);">Cargando tu ficha…</div>';

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

  function fmtMod(v) {
    return v >= 0 ? `+${v}` : `${v}`;
  }

  let selectorHtml = "";
  if (userCharacters.length > 1) {
    selectorHtml = `
      <div style="margin-bottom:12px;display:flex;align-items:center;gap:8px;">
        <label class="label" style="min-width:60px;">Cambiar PJ:</label>
        <select id="sel-char" style="padding:6px 10px;font-size:13px;">
          ${userCharacters.map((c) => `<option value="${c.id}" ${c.id === char.id ? "selected" : ""}>${escapeHtml(c.name)} (Nivel ${c.level})</option>`).join("")}
        </select>
      </div>
    `;
  }

  container.innerHTML = `
    <div style="max-width:640px;margin:0 auto;">
      ${selectorHtml}

      <!-- Cabecera de Ficha -->
      <div class="panel" style="margin:0 0 14px;border-color:var(--accent);">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;">
          <div>
            <h1 style="font-size:24px;margin:0 0 4px;color:var(--accent);">${escapeHtml(char.name)}</h1>
            <div style="color:var(--muted);font-size:14px;">
              Nivel ${char.level} · ${escapeHtml(d.race_name || char.race_slug || "Raza")} · ${escapeHtml(d.class_name || char.class_slug || "Clase")}
            </div>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <button id="btn-link-char" class="primary small">⚔️ Vincular a Combate</button>
            <button id="btn-edit-char" class="small">✏️ Editar</button>
            <button id="btn-new-char" class="small">➕ Nuevo PJ</button>
          </div>
        </div>

        <!-- Estadísticas vitales -->
        <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:8px;margin-top:14px;text-align:center;">
          <div style="background:var(--panel-2);padding:8px 4px;border-radius:8px;border:1px solid var(--border);">
            <div class="label">Puntos de Vida</div>
            <div style="font-size:20px;font-weight:800;color:var(--green);">${hpMax} HP</div>
          </div>
          <div style="background:var(--panel-2);padding:8px 4px;border-radius:8px;border:1px solid var(--border);">
            <div class="label">Clase Armadura</div>
            <div style="font-size:20px;font-weight:800;color:var(--accent);">${ac} CA</div>
          </div>
          <div style="background:var(--panel-2);padding:8px 4px;border-radius:8px;border:1px solid var(--border);">
            <div class="label">Velocidad</div>
            <div style="font-size:20px;font-weight:800;">${speed} ft</div>
          </div>
          <div style="background:var(--panel-2);padding:8px 4px;border-radius:8px;border:1px solid var(--border);">
            <div class="label">Competencia</div>
            <div style="font-size:20px;font-weight:800;color:var(--accent);">+${prof}</div>
          </div>
        </div>
      </div>

      <!-- Rejilla de 6 Características -->
      <div class="panel" style="margin:0 0 14px;">
        <h2>Características</h2>
        <div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:8px;">
          ${[
            { key: "FUE", name: "Fuerza", score: stats.strength, mod: mods.str_mod },
            { key: "DES", name: "Destreza", score: stats.dexterity, mod: mods.dex_mod },
            { key: "CON", name: "Constitución", score: stats.constitution, mod: mods.con_mod },
            { key: "INT", name: "Inteligencia", score: stats.intelligence, mod: mods.int_mod },
            { key: "SAB", name: "Sabiduría", score: stats.wisdom, mod: mods.wis_mod },
            { key: "CAR", name: "Carisma", score: stats.charisma, mod: mods.cha_mod },
          ].map((s) => `
            <div style="background:var(--panel-2);padding:10px;border-radius:8px;border:1px solid var(--border);text-align:center;">
              <div class="label">${s.key}</div>
              <div style="font-size:22px;font-weight:800;margin:2px 0;">${fmtMod(s.mod)}</div>
              <div style="font-size:12px;color:var(--muted);">${s.score} (${s.name})</div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- Armas y Ataques -->
      <div class="panel" style="margin:0 0 14px;">
        <h2>Armas y Ataques</h2>
        ${weapons.length === 0 ? `
          <p style="color:var(--muted);font-size:13px;margin:0;">No tienes armas equipadas todavía.</p>
        ` : `
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${weapons.map((w) => {
              const strMod = mods.str_mod;
              const dexMod = mods.dex_mod;
              const modToUse = (w.properties && w.properties.includes("finesse") && dexMod > strMod) ? dexMod : strMod;
              const atkBonus = w.attack_bonus !== undefined ? w.attack_bonus : (modToUse + prof);
              return `
                <div style="background:var(--panel-2);padding:10px 12px;border-radius:8px;border:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
                  <div>
                    <div style="font-weight:700;font-size:15px;">🗡️ ${escapeHtml(w.name)}</div>
                    <div style="color:var(--muted);font-size:12px;">Daño: ${escapeHtml(w.damage || w.damage_dice || "1d8")} ${escapeHtml(w.damage_type || "")}</div>
                  </div>
                  <div style="text-align:right;">
                    <span style="font-weight:800;color:var(--accent);font-size:15px;">${fmtMod(atkBonus)}</span>
                    <span class="label" style="display:block;font-size:10px;">Ataque</span>
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        `}
      </div>

      <!-- Hechizos y Conjuros -->
      <div class="panel" style="margin:0 0 14px;">
        <h2>Conjuros y Magia</h2>
        ${d.spell_dc ? `
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">
            <div style="background:var(--panel-2);padding:8px;border-radius:8px;text-align:center;border:1px solid var(--border);">
              <div class="label">CD Salvación Conjuros</div>
              <div style="font-size:18px;font-weight:800;color:var(--accent);">${d.spell_dc}</div>
            </div>
            <div style="background:var(--panel-2);padding:8px;border-radius:8px;text-align:center;border:1px solid var(--border);">
              <div class="label">Bonus Ataque Mágico</div>
              <div style="font-size:18px;font-weight:800;color:var(--accent);">${fmtMod(d.spell_attack_bonus || 0)}</div>
            </div>
          </div>
        ` : ""}
        ${spells.length === 0 ? `
          <p style="color:var(--muted);font-size:13px;margin:0;">No tienes conjuros registrados en esta ficha.</p>
        ` : `
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${spells.map((s) => `
              <div style="background:var(--panel-2);padding:10px 12px;border-radius:8px;border:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
                <div>
                  <div style="font-weight:700;font-size:15px;">✨ ${escapeHtml(s.name)}</div>
                  <div style="color:var(--muted);font-size:12px;">Nivel ${s.level !== undefined ? (s.level === 0 ? "Truco" : s.level) : "—"} · ${escapeHtml(s.school || "")}</div>
                </div>
                ${s.range ? `<div style="font-size:12px;color:var(--accent);">${escapeHtml(s.range)}</div>` : ""}
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
      const chosen = userCharacters.find((c) => c.id === Number(selChar.value));
      if (chosen) {
        currentCharacter = chosen;
        renderCharacterSheet(container, chosen);
      }
    });
  }

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
  container.innerHTML = '<div style="text-align:center;padding:30px;color:var(--muted);">Cargando catálogo SRD…</div>';
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

  // Existing first weapon / spell
  const initialWeapon = (d.weapons && d.weapons[0] && d.weapons[0].equipment_slug) || (weapons[0] && weapons[0].index) || "";
  const initialSpell = (d.spells && d.spells[0] && d.spells[0].spell_slug) || "";

  container.innerHTML = `
    <div style="max-width:600px;margin:0 auto;" class="panel">
      <h2>${isEdit ? "Editar Ficha de Personaje" : "Crear Nueva Ficha de Personaje"}</h2>
      <form id="char-form" style="display:flex;flex-direction:column;gap:12px;margin-top:14px;">
        <div>
          <label class="label">Nombre del Personaje</label>
          <input id="f-name" value="${escapeHtml((charToEdit && charToEdit.name) || "")}" placeholder="Ej. Valeros, Mialee..." required maxlength="60">
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">
          <div>
            <label class="label">Nivel (1-20)</label>
            <input id="f-level" type="number" min="1" max="20" value="${(charToEdit && charToEdit.level) || 1}" required>
          </div>
          <div>
            <label class="label">Clase</label>
            <select id="f-class">
              ${classes.map((c) => `<option value="${c.index}" ${c.index === initialClass ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("")}
            </select>
          </div>
          <div>
            <label class="label">Raza</label>
            <select id="f-race">
              ${races.map((r) => `<option value="${r.index}" ${r.index === initialRace ? "selected" : ""}>${escapeHtml(r.name)}</option>`).join("")}
            </select>
          </div>
        </div>

        <div>
          <label class="label">Puntuaciones de Característica</label>
          <div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:8px;margin-top:4px;">
            <div>
              <span class="label">Fuerza</span>
              <input id="f-str" type="number" min="1" max="30" value="${stats.strength}">
            </div>
            <div>
              <span class="label">Destreza</span>
              <input id="f-dex" type="number" min="1" max="30" value="${stats.dexterity}">
            </div>
            <div>
              <span class="label">Constitución</span>
              <input id="f-con" type="number" min="1" max="30" value="${stats.constitution}">
            </div>
            <div>
              <span class="label">Inteligencia</span>
              <input id="f-int" type="number" min="1" max="30" value="${stats.intelligence}">
            </div>
            <div>
              <span class="label">Sabiduría</span>
              <input id="f-wis" type="number" min="1" max="30" value="${stats.wisdom}">
            </div>
            <div>
              <span class="label">Carisma</span>
              <input id="f-cha" type="number" min="1" max="30" value="${stats.charisma}">
            </div>
          </div>
        </div>

        <div>
          <label class="label">Arma Principal</label>
          <select id="f-weapon">
            <option value="">-- Sin arma --</option>
            ${weapons.map((w) => `<option value="${w.index}" ${w.index === initialWeapon ? "selected" : ""}>${escapeHtml(w.name)} (${w.damage ? w.damage.damage_dice : ""})</option>`).join("")}
          </select>
        </div>

        <div>
          <label class="label">Conjuro Principal (Opcional)</label>
          <select id="f-spell">
            <option value="">-- Sin conjuro --</option>
            ${spells.map((s) => `<option value="${s.index}" ${s.index === initialSpell ? "selected" : ""}>${escapeHtml(s.name)} (Nivel ${s.level === 0 ? "Truco" : s.level})</option>`).join("")}
          </select>
        </div>

        <p id="f-error" class="error"></p>

        <div style="display:flex;gap:8px;margin-top:6px;">
          <button type="submit" class="primary" style="flex:1;">${isEdit ? "Guardar Cambios" : "Crear Ficha"}</button>
          ${isEdit ? '<button id="btn-cancel-edit" type="button" style="flex:1;">Cancelar</button>' : ""}
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
        stats: scores,
        weapons: weaponsList,
        spells: spellsList,
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


