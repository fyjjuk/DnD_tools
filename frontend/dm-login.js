const $ = (id) => document.getElementById(id);

function setMsg(text, isError) {
  const el = $("msg");
  el.hidden = false;
  el.textContent = text;
  el.classList.toggle("error", !!isError);
  el.classList.toggle("ok", !isError);
}

// Si ya hay sesión de cuenta, no pintamos el form: /campaigns.
(function gate() {
  if (localStorage.getItem("dnd_user_token")) {
    window.location.href = "/campaigns";
  }
})();

async function onSubmit(ev) {
  ev.preventDefault();
  const pw = $("f-pw").value;
  if (!pw) return;
  $("btn-submit").disabled = true;
  try {
    const res = await fetch("/api/dm/bootstrap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      setMsg(body.error || body.detail || ("Error " + res.status), true);
      return;
    }
    localStorage.setItem("dnd_dm_token", body.dm_token);
    sessionStorage.setItem("dnd_dm_pw", pw);
    window.location.href = "/dm";
  } catch (e) {
    setMsg("Error de red", true);
  } finally {
    $("btn-submit").disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("recover-form").addEventListener("submit", onSubmit);
});
