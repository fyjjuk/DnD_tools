const TOKEN_KEY = "dnd_user_token";
const $ = (id) => document.getElementById(id);

function token() { return localStorage.getItem(TOKEN_KEY); }

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
          window.location.href = "/dm";
        }
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
