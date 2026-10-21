const DM_TOKEN_KEY = "dnd_dm_token";
const DM_PW_KEY = "dnd_dm_pw";  // sessionStorage: se borra al cerrar la pestaña
const $ = (id) => document.getElementById(id);

let state = null;
let socket = null;
let dmToken = localStorage.getItem(DM_TOKEN_KEY) || null;

// ---------------- vista login / main

function showLogin() {
  $("login-view").classList.remove("hidden");
  $("main-view").classList.add("hidden");
  $("login-error").textContent = "";
  setTimeout(() => $("login-pw").focus(), 50);
}

function showMain() {
  $("login-view").classList.add("hidden");
  $("main-view").classList.remove("hidden");
}

async function login(password) {
  try {
    const info = await API.post("/api/dm/bootstrap", { password });
    dmToken = info.dm_token;
    localStorage.setItem(DM_TOKEN_KEY, dmToken);
    sessionStorage.setItem(DM_PW_KEY, password);
    showMain();
    if (socket) { socket.close(); socket = null; }
    openSocket();
    loadClosedSessions();
  } catch (err) {
    $("login-error").textContent = err.message;
    showLogin();
  }
}

// ---------------- websocket + render

function openSocket() {
  if (socket) socket.close();
  socket = connectWS("dm", dmToken, (next) => {
    state = next;
    render();
  }, () => {
    // FIX I3: WS 4003 = dm_token invalido/caducado. Limpiar y redirigir
    // al login en vez de entrar en bucle de reconexion.
    localStorage.removeItem(DM_TOKEN_KEY);
    window.location.href = "/dm-login";
  });
}

function renderInitiativeTracker() {
  const panel = $("initiative-tracker");
  if (!panel) return;
  const req = state.initiative_request;
  if (!req || req.status !== "active") {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  panel.classList.remove("hidden");
  const userToken = localStorage.getItem("dnd_user_token");

  let html = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <strong>🎲 Tirada de Iniciativa en curso (${req.pending_count} pendiente${req.pending_count === 1 ? '' : 's'})</strong>
      <button id="btn-cancel-init" class="danger small" type="button">Cancelar</button>
    </div>
    <div style="display:grid;gap:6px">
  `;

  for (const r of req.rolls) {
    const isPending = r.status === "pending";
    const statusLabel = r.status === "rolled"
      ? `<span style="color:#10b981">✓ Tiró: ${r.roll_value} + ${r.dex_mod} = <strong>${r.total}</strong></span>`
      : r.status === "forced"
      ? `<span style="color:#f59e0b">✓ Forzado: ${r.roll_value} + ${r.dex_mod} = <strong>${r.total}</strong></span>`
      : r.status === "skipped"
      ? `<span style="color:#9ca3af">✓ Toma 10: 10 + ${r.dex_mod} = <strong>${r.total}</strong></span>`
      : `<span style="color:#8b5cf6">⏳ Esperando tirada (DES ${r.dex_mod >= 0 ? '+' : ''}${r.dex_mod})</span>`;

    html += `
      <div style="display:flex;align-items:center;justify-content:space-between;background:var(--bg);padding:6px 10px;border-radius:6px;border:1px solid var(--border)">
        <div>
          <strong>${escapeHtml(r.combatant_name)}</strong>
          <span class="tag ${r.kind}" style="margin-left:6px">${r.kind === 'pc' ? 'PJ' : 'ENEMIGO'}</span>
          <span style="margin-left:10px">${statusLabel}</span>
        </div>
        ${isPending ? `
          <div style="display:flex;gap:6px">
            <button class="small" data-force="${r.combatant_id}" style="background:#8b5cf6;color:#fff">Forzar d20</button>
            <button class="small" data-skip="${r.combatant_id}">Toma 10</button>
          </div>
        ` : ''}
      </div>
    `;
  }
  html += `</div>`;
  panel.innerHTML = html;

  $("btn-cancel-init")?.addEventListener("click", async () => {
    if (!userToken) return;
    try {
      await API.post("/api/initiative/cancel", { request_id: req.id }, { "X-User-Token": userToken });
    } catch (err) {
      alert("Error al cancelar iniciativa: " + err.message);
    }
  });

  panel.querySelectorAll("button[data-force]").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!userToken) return;
      try {
        const cid = parseInt(btn.dataset.force, 10);
        await API.post("/api/initiative/force", { request_id: req.id, combatant_id: cid }, { "X-User-Token": userToken });
      } catch (err) {
        alert("Error al forzar tirada: " + err.message);
      }
    });
  });

  panel.querySelectorAll("button[data-skip]").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!userToken) return;
      try {
        const cid = parseInt(btn.dataset.skip, 10);
        await API.post("/api/initiative/skip", { request_id: req.id, combatant_id: cid }, { "X-User-Token": userToken });
      } catch (err) {
        alert("Error al saltar tirada: " + err.message);
      }
    });
  });
}

function render() {
  if (!state) return;
  $("session-code").textContent = state.session.code;
  $("round").textContent = state.session.round;

  const active = state.session.status === "active";
  const banner = $("banner");
  banner.classList.toggle("hidden", active);
  if (!active) banner.textContent = "Sesión cerrada. Pulsa «Nueva sesión» para empezar otra.";
  $("btn-close").textContent = active ? "Cerrar sesión" : "Nueva sesión";

  // Control para DM legacy (sesión sin campaña o sin token v2)
  const isLegacy = !state.session.campaign_id;
  const userToken = localStorage.getItem("dnd_user_token");
  const btnInit = $("btn-roll-initiative");
  const legacyNote = $("legacy-initiative-note");

  if (btnInit) {
    if (isLegacy || !userToken) {
      btnInit.disabled = true;
      btnInit.title = "Requiere cuenta de campaña";
      btnInit.style.opacity = "0.5";
      btnInit.style.cursor = "not-allowed";
      if (legacyNote) legacyNote.classList.remove("hidden");
    } else {
      btnInit.disabled = false;
      btnInit.title = "";
      btnInit.style.opacity = "1";
      btnInit.style.cursor = "pointer";
      if (legacyNote) legacyNote.classList.add("hidden");
    }
  }

  renderInitiativeTracker();
  renderList();
}

function renderList() {
  const container = $("combatants");
  container.innerHTML = "";

  if (!state.combatants.length) {
    container.innerHTML = '<p class="hp-text">Aún no hay combatientes.</p>';
    return;
  }

  const turnId = state.session.turn_combatant_id;
  const players = state.players || [];

  for (const c of state.combatants) {
    const row = document.createElement("div");
    row.className = "combatant";
    if (c.id === turnId) row.classList.add("current");
    if (c.dead) row.classList.add("dead");

    const pct = c.hp_max > 0
      ? Math.max(0, Math.min(100, (c.hp_current / c.hp_max) * 100))
      : 0;

    row.innerHTML = `
      <div class="c-head">
        <span class="init">${c.initiative}</span>
        <span class="c-name">${escapeHtml(c.name)}</span>
        <span class="tag ${c.kind}">${c.kind === "pc" ? "PJ" : "ENEMIGO"}</span>
        ${c.id === turnId ? '<span class="turn-tag">TURNO</span>' : ""}
      </div>
      <div class="hpbar"><div class="hpfill" style="width:${pct}%"></div></div>
      <div class="hp-text">${c.hp_current} / ${c.hp_max} HP${c.dead ? " · CAÍDO" : ""}</div>
      <div class="c-actions">
        <button class="dmg" data-hp="-10">−10</button>
        <button class="dmg" data-hp="-5">−5</button>
        <button class="dmg" data-hp="-1">−1</button>
        <button class="heal" data-hp="1">+1</button>
        <button class="heal" data-hp="5">+5</button>
        <button class="heal" data-hp="10">+10</button>
        <button data-undo="1" title="Deshacer último cambio de HP">↶</button>
        <button class="danger small" data-remove="1">✕</button>
      </div>
      ${c.kind === "pc" ? `
      <div class="c-link">
        <span>Jugador:</span>
        <select data-link="${c.id}">
          <option value="">— sin vincular —</option>
          ${players.map((p) =>
            `<option value="${p.id}"${p.id === c.linked_player_id ? " selected" : ""}>${escapeHtml(p.name)}</option>`
          ).join("")}
        </select>
      </div>` : ""}
    `;

    row.querySelectorAll("[data-hp]").forEach((btn) => {
      btn.addEventListener("click", () => changeHp(c.id, Number(btn.dataset.hp)));
    });
    row.querySelector("[data-remove]").addEventListener("click", () => removeCombatant(c.id));
    const undoBtn = row.querySelector("[data-undo]");
    if (undoBtn) undoBtn.addEventListener("click", () => undoHp(c.id));
    const select = row.querySelector("[data-link]");
    if (select) {
      select.addEventListener("change", () =>
        linkPlayer(c.id, select.value ? Number(select.value) : null)
      );
    }

    container.appendChild(row);
  }
}

// ---------------- autocompletado SRD

const monsterSearch = $("f-monster-search");
const monsterDatalist = $("srd-monsters");
const srdIndexInput = $("f-srd-index");
let monsterSearchTimer = null;

monsterSearch.addEventListener("input", () => {
  const q = monsterSearch.value.trim();
  clearTimeout(monsterSearchTimer);
  if (q.length < 2) {
    monsterDatalist.innerHTML = "";
    return;
  }
  monsterSearchTimer = setTimeout(async () => {
    try {
      const data = await API.get(
        `/api/srd/monsters?q=${encodeURIComponent(q)}&limit=20`
      );
      monsterDatalist.innerHTML = data.items
        .map((m) => {
          const dex = Number(m.dexterity) || 10;
          return (
            `<option value="${escapeHtml(m.name)}"` +
            ` data-index="${escapeHtml(m.index)}"` +
            ` data-hp="${m.hit_points}"` +
            ` data-dex="${dex}"></option>`
          );
        })
        .join("");
    } catch (err) {
      // Sin SRD importado el endpoint devuelve [] o falla en red:
      // el datalist se queda vacío y el flujo manual sigue funcionando.
      monsterDatalist.innerHTML = "";
    }
  }, 200);
});

// `change` se dispara al confirmar la opción del datalist (o al salir del
// campo). Si el valor coincide EXACTAMENTE con una opción poblamos
// los campos y marcamos `srd_index`. Si no coincide, limpiamos `srd_index`.
monsterSearch.addEventListener("change", () => {
  const val = monsterSearch.value.trim();
  const opt = Array.from(monsterDatalist.options).find((o) => o.value === val);
  if (!opt) {
    srdIndexInput.value = "";
    return;
  }
  srdIndexInput.value = opt.dataset.index || "";
  $("f-name").value = opt.value;
  $("f-hp").value = opt.dataset.hp || "1";
  const dex = Number(opt.dataset.dex) || 10;
  $("f-init").value = String(10 + Math.floor((dex - 10) / 2));
});

// ---------------- acciones

async function changeHp(id, delta) {
  try {
    await API.post(`/api/combatants/${id}/hp`, { delta }, { "X-DM-Token": dmToken });
  } catch (err) { toast(err.message); }
}

async function undoHp(id) {
  try {
    await API.post(`/api/combatants/${id}/undo-hp`, {}, { "X-DM-Token": dmToken });
  } catch (err) { toast(err.message); }
}

async function removeCombatant(id) {
  if (!confirm("¿Eliminar este combatiente?")) return;
  try {
    await API.del(`/api/combatants/${id}`, { "X-DM-Token": dmToken });
  } catch (err) { toast(err.message); }
}

async function linkPlayer(cid, playerId) {
  try {
    await API.post(`/api/combatants/${cid}/link`, { player_id: playerId }, { "X-DM-Token": dmToken });
  } catch (err) { toast(err.message); }
}

async function turnAction(path) {
  try {
    await API.post(path, {}, { "X-DM-Token": dmToken });
  } catch (err) { toast(err.message); }
}

async function loadClosedSessions() {
  if (!dmToken) return;
  try {
    const data = await API.get("/api/sessions/closed", { "X-DM-Token": dmToken });
    const sel = $("log-selector");
    sel.innerHTML = '<option value="">— selecciona una sesión —</option>';
    for (const s of data.sessions) {
      const opt = document.createElement("option");
      opt.value = s.code;
      opt.textContent = `${s.code} · ${s.closed_at || "?"} · ${s.n_events} eventos`;
      sel.appendChild(opt);
    }
  } catch (err) { /* silencioso: no romper la UI */ }
}

// ---------------- listeners globales

$("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const pw = $("login-pw").value;
  if (pw) login(pw);
});

$("add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    name: $("f-name").value.trim(),
    hp_max: Number($("f-hp").value) || 1,
    initiative: Number($("f-init").value) || 0,
    kind: $("f-kind").value,
  };
  const srdIdx = $("f-srd-index").value;
  if (srdIdx) payload.srd_index = srdIdx;
  if (!payload.name) return;
  try {
    await API.post("/api/combatants", payload, { "X-DM-Token": dmToken });
    $("f-name").value = "";
    $("f-monster-search").value = "";
    $("f-srd-index").value = "";
    $("f-name").focus();
  } catch (err) { toast(err.message); }
});

$("btn-roll-initiative")?.addEventListener("click", async () => {
  if (!state || !state.session || !state.session.id) return;
  const isLegacy = !state.session.campaign_id;
  const userToken = localStorage.getItem("dnd_user_token");

  if (isLegacy || !userToken) {
    toast("Iniciativa requiere cuenta de campaña");
    return;
  }

  try {
    await API.post(
      `/api/sessions/${state.session.id}/initiative/request`,
      {},
      { "X-User-Token": userToken }
    );
  } catch (err) {
    alert("Error al iniciar iniciativa: " + err.message);
  }
});

$("btn-next-turn").addEventListener("click", () => turnAction("/api/turn/next"));
$("btn-next-round").addEventListener("click", () => turnAction("/api/turn/round"));

$("btn-recover").addEventListener("click", () => {
  if (socket) { socket.close(); socket = null; }
  showLogin();
});

$("btn-close").addEventListener("click", async () => {
  if (state && state.session.status === "active") {
    if (!confirm("¿Cerrar la sesión y guardar el log de eventos?")) return;
    try {
      const res = await API.post("/api/session/close", {}, { "X-DM-Token": dmToken });
      toast("Log guardado en " + res.log);
      loadClosedSessions();
    } catch (err) { toast(err.message); }
  } else {
    const pw = sessionStorage.getItem(DM_PW_KEY);
    if (!pw) { showLogin(); return; }
    await login(pw);
  }
});

$("btn-load-log").addEventListener("click", async () => {
  const code = $("log-selector").value;
  if (!code) { toast("Selecciona una sesión cerrada"); return; }
  try {
    const data = await API.get(
      `/api/sessions/${encodeURIComponent(code)}/log`,
      { "X-DM-Token": dmToken }
    );
    const pre = $("log-view");
    pre.textContent = data.content;
    pre.classList.remove("hidden");
  } catch (err) { toast(err.message); }
});

// ---------------- Compartir sesión (Fase 2.1.1)

$("btn-share").addEventListener("click", async () => {
  $("share-modal").classList.remove("hidden");
  const content = $("share-modal-content");
  content.innerHTML = '<p class="hp-text">Cargando...</p>';
  try {
    const info = await API.get("/api/network-info");
    const ip = (info.ips && info.ips[0]) || "sin-ip";
    // FIX B1: si la sesion pertenece a una campana, meter ?code= en la URL
    // para que el QR (y el portapapeles) lleven el jugador directo con el
    // codigo prellenado. Sesion legacy -> sin query + aviso en el modal.
    const joinCode = state && state.session && state.session.campaign_join_code;
    const url = joinCode
      ? `http://${ip}:${info.port}/campaigns?code=${encodeURIComponent(joinCode)}`
      : `http://${ip}:${info.port}/campaigns`;
    const sessionCode = state && state.session && state.session.code;
    content.innerHTML = `
      <div class="share-url" style="margin-bottom:10px">
        <div class="label">URL para jugadores</div>
        <input readonly value="${escapeHtml(url)}" style="width:100%;margin-top:4px">
        <button class="small" data-copy="${escapeHtml(url)}" style="margin-top:6px">Copiar URL</button>
      </div>
      <div class="share-qr" style="text-align:center;margin:10px 0">
        <img src="/api/qr.svg?data=${encodeURIComponent(url)}" alt="QR" style="max-width:240px;background:#fff;padding:8px;border-radius:6px">
      </div>
      ${joinCode ? `<div class="share-code" style="margin-top:10px"><div class="label">Código de campaña</div><div class="code" style="font-size:22px">${escapeHtml(joinCode)}</div></div>` : ""}
      ${sessionCode ? `<div class="share-code" style="margin-top:10px"><div class="label">Código de sesión (legacy)</div><div class="code" style="font-size:22px">${escapeHtml(sessionCode)}</div></div>` : ""}
      ${!joinCode ? '<p class="hp-text" style="margin-top:10px">Sesión sin campaña asociada. Solo código de sesión disponible.</p>' : ""}
    `;
    content.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", () => {
        // FIX B2: copyToClipboard tiene fallback para HTTP LAN.
        copyToClipboard(btn.dataset.copy).then((ok) => {
          if (ok) { toast("Copiado"); }
          else { toast("No se pudo copiar. Selecciona el texto manualmente."); }
        });
      });
    });
  } catch (e) {
    content.innerHTML = `<p class="error">Error: ${escapeHtml(e.message)}</p>`;
  }
});
$("btn-share-close").addEventListener("click", () => {
  $("share-modal").classList.add("hidden");
});

// ---------------- init

(async function init() {
  const userToken = localStorage.getItem("dnd_user_token");
  const dmToken = localStorage.getItem(DM_TOKEN_KEY);
  if (!dmToken && userToken) {
    window.location.href = "/campaigns";
    return;
  }
  if (!dmToken && !userToken) {
    window.location.href = "/dm-login";
    return;
  }
  // dmToken existe: flujo legacy, proceder como hoy.
  showMain();
  openSocket();
  loadClosedSessions();
})();
