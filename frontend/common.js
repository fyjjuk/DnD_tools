const API = {
  async _handle(res) {
    if (!res.ok) {
      let detail = "Error " + res.status;
      try {
        const body = await res.json();
        if (body && body.detail) detail = body.detail;
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
  del(path, headers = {}) {
    return fetch(path, { method: "DELETE", headers }).then((r) => API._handle(r));
  },
  get(path, headers = {}) {
    return fetch(path, { headers }).then((r) => API._handle(r));
  },
};

function connectWS(role, token, onState) {
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
    socket.onclose = () => {
      if (stopped) return;
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
