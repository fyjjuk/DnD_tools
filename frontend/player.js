const TOKEN_KEY = "dnd_player_token";
const $ = (id) => document.getElementById(id);

let playerToken = localStorage.getItem(TOKEN_KEY);
let state = null;
let socket = null;

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
      await API.get("/api/player/me", { "X-Player-Token": playerToken });
      showCombat();
      openSocket();
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

function openSocket() {
  if (socket) socket.close();
  socket = connectWS("player", playerToken, (next) => {
    state = next;
    render();
  }, () => {
    // FIX I3: WS 4003 = player_token invalido/caducado. Limpiar; si hay
    // user_token (cuenta) volver a /campaigns, si no (guest) al join.
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
    // Limpiar paneles para que no queden botones vivos contra una sesión cerrada.
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
    const info = await API.post("/api/join", {
      code: $("j-code").value.trim().toUpperCase(),
      name: $("j-name").value.trim(),
    });
    playerToken = info.token;
    localStorage.setItem(TOKEN_KEY, playerToken);
    showCombat();
    openSocket();
  } catch (err) {
    $("join-error").textContent = err.message;
  }
});

