const API = {
  async _handle(res) {
    if (!res.ok) {
      let detail = "Error " + res.status;
      try {
        const body = await res.json();
        if (body && (body.error || body.detail)) detail = body.error || body.detail;
      } catch (e) { /* sin body */ }
      throw new Error(detail);
    }
    return res.json();
  },
  post(path, body = {}, headers = {}) {
    return fetch(path, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, headers),
      body: JSON.stringify(body),
    }).then((r) => API._handle(r));
  },
  put(path, body = {}, headers = {}) {
    return fetch(path, {
      method: "PUT",
      headers: Object.assign({ "Content-Type": "application/json" }, headers),
      body: JSON.stringify(body),
    }).then((r) => API._handle(r));
  },
  del(path, headers = {}) {
    return fetch(path, { method: "DELETE", headers }).then((r) => API._handle(r));
  },
  get(path, headers = {}) {
    return fetch(path, { headers }).then((r) => API._handle(r));
  },
};

function connectWS(role, token, onState, onAuthError) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws?role=${encodeURIComponent(role)}&token=${encodeURIComponent(token)}`;
  let socket = null;
  let stopped = false;
  let delay = 800;

  function open() {
    socket = new WebSocket(url);
    socket.onopen = () => { delay = 800; };
    socket.onmessage = (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch (e) { return; }
      if (data.type === "state") onState(data);
    };
    socket.onclose = (event) => {
      if (stopped) return;
      // FIX I3: WS 4003 = token invalido/caducado (dm_token o player_token).
      // Si el caller paso onAuthError, delegamos la limpieza + redireccion
      // y NO reintentamos (evita el bucle de reconexion).
      if (event && event.code === 4003 && typeof onAuthError === "function") {
        stopped = true;
        onAuthError();
        return;
      }
      setTimeout(open, delay);
      delay = Math.min(delay * 1.6, 5000);
    };
    socket.onerror = () => { try { socket.close(); } catch (e) {} };
  }

  open();

  return {
    close() { stopped = true; if (socket) socket.close(); },
  };
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

let _toastTimer = null;
function toast(message) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add("hidden"), 3200);
}

// FIX B2: copiar al portapapeles con fallback para HTTP LAN.
// navigator.clipboard solo existe en contexto seguro (HTTPS o
// localhost); en http://192.168.x.x hay que recurrir a execCommand.
// Devuelve Promise<boolean>. No lanza: false si no se pudo copiar.
async function copyToClipboard(text) {
  // Camino 1: Clipboard API (HTTPS o localhost)
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (e) { /* cae al fallback */ }
  // Camino 2: textarea + execCommand
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    ta.style.pointerEvents = "none";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (e) {
    return false;
  }
}
