const $ = (id) => document.getElementById(id);

function setMsg(text, isError) {
  const el = $("msg");
  el.hidden = false;
  el.textContent = text;
  el.classList.toggle("error", !!isError);
  el.classList.toggle("ok", !isError);
}

async function onSubmit(ev) {
  ev.preventDefault();
  const username = $("f-username").value.trim();
  const password = $("f-password").value;
  const display_name = $("f-display").value.trim();
  if (!username || !password || !display_name) {
    setMsg("Rellena todos los campos", true);
    return;
  }
  $("btn-submit").disabled = true;
  try {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, display_name }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      setMsg(body.error || body.detail || ("Error " + res.status), true);
      return;
    }
    localStorage.setItem("dnd_user_token", body.token);
    window.location.href = "/campaigns";
  } catch (e) {
    setMsg("Error de red", true);
  } finally {
    $("btn-submit").disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("register-form").addEventListener("submit", onSubmit);
});
