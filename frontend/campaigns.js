const TOKEN_KEY = "dnd_user_token";
const $ = (id) => document.getElementById(id);

function token() { return localStorage.getItem(TOKEN_KEY); }

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function setMsg(text, isError) {
  const el = $("msg");
  el.hidden = false;
  el.textContent = text;
  el.classList.toggle("error", !!isError);
  el.classList.toggle("ok", !isError);
}

async function api(path, opts = {}) {
  const headers = Object.assign({ "X-User-Token": token() || "" }, opts.headers || {});
  let body = opts.body;
  if (body && typeof body !== "string") {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const res = await fetch(path, Object.assign({}, opts, { headers, body }));
  let data = null;
  try { data = await res.json(); } catch (e) { /* vacio */ }
  if (res.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    window.location.href = "/login";
    return null;
  }
  if (!res.ok) {
    const msg = (data && (data.error || data.detail)) || ("Error " + res.status);
    throw new Error(msg);
  }
  return data;
}

async function loadMe() {
  const me = await api("/api/auth/me");
  if (me) $("user-name").textContent = me.display_name + " (@" + me.username + ")";
}

async function loadCampaigns() {
  const data = await api("/api/campaigns");
  const list = $("campaign-list");
  if (!data || !data.items || !data.items.length) {
    list.innerHTML = '<p class="muted">No tienes campañas todavía.</p>';
    return;
  }
  // FIX I4: join_code ya viene en el listado (/api/campaigns).
  // Sin N+1: no se hace fetch por tarjeta.
  list.innerHTML = "";
  for (const c of data.items) {
    list.appendChild(renderCampaign(c));
  }
}

function renderCampaign(c) {
  const card = document.createElement("div");
  card.className = "campaign-card";

  const hasActive = (c.n_sessions_active || 0) > 0;

  const head = document.createElement("div");
  head.className = "campaign-head";
  head.innerHTML =
    '<div><div class="campaign-name"></div>' +
    '<div class="campaign-meta"></div></div>' +
    '<div class="row-actions"></div>';
  head.querySelector(".campaign-name").textContent = c.name;
  let meta = "rol: " + c.role + " · " + c.status + " · " +
             c.n_sessions + " sesiones";
  if (hasActive) meta += " · sesión activa";
  if (c.join_code) meta += " · código " + c.join_code;
  head.querySelector(".campaign-meta").textContent = meta;

  const actions = head.querySelector(".row-actions");
  const btnToggle = document.createElement("button");
  btnToggle.type = "button";
  btnToggle.className = "small";
  btnToggle.textContent = "Ver sesiones";
  actions.appendChild(btnToggle);

  if (c.role === "dm") {
    const btnOpen = document.createElement("button");
    btnOpen.type = "button";
    btnOpen.className = "primary small";
    btnOpen.textContent = "Abrir consola DM";
    btnOpen.addEventListener("click", async () => {
      try {
        const data = await api(
          "/api/campaigns/" + c.id + "/open-session",
          { method: "POST" }
        );
        if (data && data.dm_token) {
          localStorage.setItem("dnd_dm_token", data.dm_token);
        }
        window.location.href = "/dm";
      } catch (e) {
        setMsg("Error abriendo consola: " + e.message, true);
      }
    });
    actions.appendChild(btnOpen);

    if (!hasActive) {
      const btnCreate = document.createElement("button");
      btnCreate.type = "button";
      btnCreate.className = "small";
      btnCreate.textContent = "Crear sesión";
      btnCreate.addEventListener("click", () => createSession(c.id));
      actions.appendChild(btnCreate);
    }
  } else if (c.role === "player") {
    if (hasActive) {
      const btnJoin = document.createElement("button");
      btnJoin.type = "button";
      btnJoin.className = "primary small";
      btnJoin.textContent = "Unirme a sesión";
      btnJoin.addEventListener("click", async () => {
        try {
          const data = await api(
            "/api/campaigns/" + c.id + "/join-player",
            { method: "POST" }
          );
          if (data && data.token) {
            localStorage.setItem("dnd_player_token", data.token);
            window.location.href = "/player";
          }
        } catch (e) {
          setMsg("Error uniendo a sesión: " + e.message, true);
        }
      });
      actions.appendChild(btnJoin);
    } else {
      const note = document.createElement("span");
      note.className = "muted small";
      note.textContent = "Sin sesión activa";
      actions.appendChild(note);
    }
  }

  const panel = document.createElement("div");
  panel.className = "campaign-sessions";
  panel.hidden = true;

  const shareActions = document.createElement("div");
  shareActions.style.marginTop = "10px";

  const btnShare = document.createElement("button");
  btnShare.type = "button";
  btnShare.className = "small";
  btnShare.textContent = "Compartir";
  shareActions.appendChild(btnShare);

  const sharePanel = document.createElement("div");
  sharePanel.className = "share-panel";
  sharePanel.hidden = true;
  sharePanel.style.marginTop = "8px";

  btnShare.addEventListener("click", async () => {
    sharePanel.hidden = !sharePanel.hidden;
    if (sharePanel.hidden) return;
    sharePanel.innerHTML = '<p class="muted">Cargando…</p>';
    if (!c.join_code) {
      sharePanel.innerHTML =
        '<p class="muted">Esta campaña no tiene join_code.</p>';
      return;
    }
    try {
      const res = await fetch("/api/network-info");
      const info = await res.json();
      const ip = (info.ips && info.ips[0]) || "sin-ip";
      const shareUrl = "http://" + ip + ":" + info.port +
                       "/campaigns?code=" + c.join_code;
      sharePanel.innerHTML =
        '<div class="share-url">' +
          '<input readonly value="' + escapeHtml(shareUrl) + '">' +
          '<button class="small" data-copy="' + escapeHtml(shareUrl) +
            '" style="margin-top:6px">Copiar URL</button>' +
        '</div>' +
        '<div class="share-code" style="margin-top:8px">Código: ' +
          '<code class="code">' + escapeHtml(c.join_code) + '</code> ' +
          '<button class="small" data-copy="' + escapeHtml(c.join_code) +
            '">Copiar</button>' +
        '</div>' +
        '<div class="share-qr" style="margin-top:8px">' +
          '<img src="/api/qr.svg?data=' + encodeURIComponent(shareUrl) +
            '" alt="QR" style="max-width:220px">' +
        '</div>';
      sharePanel.querySelectorAll("[data-copy]").forEach((b) => {
        b.addEventListener("click", () => {
          // FIX B2: copyToClipboard (common.js) tiene fallback para HTTP LAN.
          copyToClipboard(b.dataset.copy).then((ok) => {
            if (ok) { setMsg("Copiado", false); }
            else { setMsg("No se pudo copiar. Selecciona el texto manualmente.", true); }
          });
        });
      });
    } catch (e) {
      sharePanel.innerHTML =
        '<p class="error">Error: ' + escapeHtml(e.message) + '</p>';
    }
  });

  btnToggle.addEventListener("click", async () => {
    panel.hidden = !panel.hidden;
    if (panel.hidden) return;
    try {
      const data = await api("/api/campaigns/" + c.id + "/sessions");
      renderSessions(panel, (data && data.items) || []);
    } catch (e) {
      panel.innerHTML = '<p class="muted">Error: ' + e.message + '</p>';
    }
  });

  card.appendChild(head);
  card.appendChild(panel);
  card.appendChild(shareActions);
  card.appendChild(sharePanel);
  return card;
}

function renderSessions(panel, items) {
  if (!items.length) {
    panel.innerHTML = '<p class="muted">Sin sesiones.</p>';
    return;
  }
  const rows = items.map((s) => {
    const closed = s.closed_at ? (" · cerrada " + s.closed_at) : "";
    return "<li><strong>" + s.code + "</strong> · " + s.status +
      " · ronda " + s.round + closed + "</li>";
  }).join("");
  panel.innerHTML = '<ul class="sessions-list">' + rows + "</ul>";
}

async function createSession(campaignId) {
  try {
    const data = await api("/api/campaigns/" + campaignId + "/sessions",
                           { method: "POST" });
    if (data) {
      setMsg("Sesión " + data.code + " creada (id " + data.session_id + ")", false);
      await loadCampaigns();
    }
  } catch (e) {
    setMsg("Error creando sesión: " + e.message, true);
  }
}

async function onCreate(ev) {
  ev.preventDefault();
  const name = $("new-name").value.trim();
  if (!name) return;
  try {
    const data = await api("/api/campaigns", { method: "POST", body: { name } });
    if (data) {
      $("new-name").value = "";
      setMsg("Campaña creada: " + data.name + " (código " + data.join_code + ")", false);
      await loadCampaigns();
    }
  } catch (e) {
    setMsg("Error: " + e.message, true);
  }
}

async function onJoin(ev) {
  ev.preventDefault();
  const code = $("join-code").value.trim().toUpperCase();
  if (!code) return;
  try {
    const data = await api("/api/campaigns/join", { method: "POST", body: { code } });
    if (data) {
      $("join-code").value = "";
      setMsg("Te uniste a " + data.name, false);
      await loadCampaigns();
    }
  } catch (e) {
    let msg = e.message || String(e);
    if (/not found|campana no encontrada|404/i.test(msg)) {
      msg += " (revisa que usas el código de CAMPAÑA de 6 letras, " +
             "no el código de SESIÓN)";
    }
    setMsg("Error: " + msg, true);
  }
}

async function onLogout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (e) { /* ignorar */ }
  localStorage.removeItem(TOKEN_KEY);
  window.location.href = "/login";
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!token()) {
    window.location.href = "/login";
    return;
  }
  $("form-new").addEventListener("submit", onCreate);
  $("form-join").addEventListener("submit", onJoin);
  $("btn-logout").addEventListener("click", onLogout);
  try {
    await loadMe();
    await loadCampaigns();
  } catch (e) {
    setMsg("Error: " + e.message, true);
  }
});

// Fase 2.1.1 — Prefill de "Unirse por código" desde ?code=XXXXXX
document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const preCode = params.get("code");
  if (preCode) {
    const input = document.getElementById("join-code");
    if (input) {
      input.value = preCode.toUpperCase().slice(0, 6);
      input.focus();
    }
  }
});
