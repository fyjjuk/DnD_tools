#!/usr/bin/env python
"""E2E tests automatizados para Fase 2.1 (Selenium + urllib).

Requiere:
  - Servidor arrancado en http://127.0.0.1:8000 (python run.py)
  - Chrome/Chromium instalado (selenium-manager descarga el driver)
  - selenium instalado en el venv:
        source .venv/bin/activate && pip install selenium
    (dev-only; NO se anade a requirements.txt)

Uso:
  python scripts/test_e2e_fase_2_1.py            # headless
  python scripts/test_e2e_fase_2_1.py --headful  # ver el navegador

Exit code: 0 si todos los checks pasan, 1 si alguno falla, 2 si falta
dependencia o el servidor no responde.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Bootstrap sys.path para que `import config` funcione aunque se ejecute
# como `python scripts/test_e2e_fase_2_1.py` (cwd=raiz, script en scripts/).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("ERROR: selenium no instalado. Ejecuta:")
    print("  source .venv/bin/activate && pip install selenium")
    sys.exit(2)

import config


def setUpModule():
    """Cierra sesiones activas para que el E2E sea re-ejecutable."""
    import datetime
    from backend.db import get_db
    with get_db() as db:
        rows = db.execute(
            "SELECT id, code FROM sessions WHERE status='active'"
        ).fetchall()
        for r in rows:
            db.execute(
                "UPDATE sessions SET status='closed', closed_at=? WHERE id=?",
                (datetime.datetime.now().isoformat(timespec='seconds'), r["id"]),
            )
            print(f"E2E: cerrada sesión huérfana {r['code']}")


BASE = "http://127.0.0.1:8000"
DM_PW = getattr(config, "DM_PASSWORD", "") or ""
SUFFIX = str(int(time.time()))
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    return bool(cond)


def info(name, detail=""):
    print(f"[INFO] {name}" + (f"  {detail}" if detail else ""))


def http(method, path, body=None, headers=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers or {})
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, raw.decode(errors="replace")


def new_driver(headless):
    opts = Options()
    if headless:
        opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    return webdriver.Chrome(options=opts)


def wait_path(drv, path, timeout=10):
    def _m(d):
        return urllib.parse.urlparse(d.current_url).path == path
    return WebDriverWait(drv, timeout).until(_m)


def wait_el(drv, css, timeout=10):
    return WebDriverWait(drv, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css)))


def click(drv, css):
    wait_el(drv, css).click()


def fill(drv, css, value):
    el = wait_el(drv, css)
    el.clear()
    el.send_keys(value)


def is_hidden(drv, id_):
    el = drv.find_element(By.ID, id_)
    return "hidden" in (el.get_attribute("class") or "").split()


def ls_get(drv, key):
    return drv.execute_script(f'return localStorage.getItem("{key}");')


# --------------------------------------------------------------- preflight

def preflight():
    try:
        status, _ = http("GET", "/")
    except Exception as e:
        check("servidor arrancado en " + BASE, False, str(e))
        return False
    return check("servidor arrancado en " + BASE, status == 200, f"HTTP {status}")


# --------------------------------------------------------------- tests

def test_1_legacy_dm(headless):
    info("Test 1: DM legacy via /dm-login")
    drv = new_driver(headless)
    try:
        drv.get(BASE + "/dm")
        wait_path(drv, "/dm-login")
        check("1.1 /dm sin token -> /dm-login", True)

        fill(drv, "#f-pw", DM_PW)
        click(drv, "#btn-submit")
        wait_path(drv, "/dm")
        WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.ID, "session-code").text.strip() != "------")
        code = drv.find_element(By.ID, "session-code").text.strip()
        check("1.2 password correcta -> /dm con codigo", len(code) == 6, code)
        check("1.3 #main-view visible", not is_hidden(drv, "main-view"))
        check("1.4 #login-view oculto", is_hidden(drv, "login-view"))
        sess_dm_token = ls_get(drv, "dnd_dm_token")
        return code, sess_dm_token
    finally:
        drv.quit()


def test_2_legacy_player(code, headless):
    info("Test 2: Jugador legacy via /player")
    drv = new_driver(headless)
    try:
        drv.get(BASE + "/player")
        wait_el(drv, "#join-form")
        check("2.1 #join-view visible sin cuenta", not is_hidden(drv, "join-view"))
        fill(drv, "#j-code", code)
        fill(drv, "#j-name", "LegacyP_" + SUFFIX)
        click(drv, '#join-form button[type="submit"]')
        WebDriverWait(drv, 10).until(lambda d: not is_hidden(d, "combat-view"))
        check("2.2 unirse -> #combat-view visible", True)
    finally:
        drv.quit()


def test_1_5_close_legacy(sess_dm_token):
    info("Test 1.5: cerrar sesion legacy para liberar slot")
    status, _ = http("POST", "/api/session/close",
                     headers={"X-DM-Token": sess_dm_token})
    check("1.5 cerrar sesion legacy", status == 200, f"HTTP {status}")


def test_3_new_dm_and_campaign(headless, player_display):
    info("Test 3: DM con cuenta -> /campaigns -> Abrir consola DM")
    drv = new_driver(headless)
    try:
        drv.get(BASE + "/register")
        wait_el(drv, "#register-form")
        fill(drv, "#f-username", "dmtest_" + SUFFIX)
        fill(drv, "#f-password", "test12345")
        fill(drv, "#f-display", "DMTest " + SUFFIX)
        click(drv, "#btn-submit")
        wait_path(drv, "/campaigns")
        user_token = ls_get(drv, "dnd_user_token")
        check("3.1 /register -> /campaigns", True)
        check("3.2 dnd_user_token guardado", bool(user_token))

        campaign_name = "CampTest " + SUFFIX
        fill(drv, "#new-name", campaign_name)
        click(drv, '#form-new button[type="submit"]')
        WebDriverWait(drv, 10).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, ".campaign-card"))
        check("3.3 campana creada", True)

        _, camp_list = http("GET", "/api/campaigns",
                            headers={"X-User-Token": user_token})
        items = (camp_list or {}).get("items", []) if camp_list else []
        camp = next((x for x in items if x["name"] == campaign_name), None)
        campaign_id = camp["id"] if camp else None
        check("3.4 campana en /api/campaigns", campaign_id is not None)

        _, camp_detail = http("GET", f"/api/campaigns/{campaign_id}",
                              headers={"X-User-Token": user_token})
        join_code = camp_detail.get("join_code") if camp_detail else None
        info("join_code de campana", join_code)

        btn = drv.find_element(
            By.XPATH, "//button[contains(., 'Abrir consola DM')]")
        btn.click()
        wait_path(drv, "/dm")
        WebDriverWait(drv, 10).until(lambda d: not is_hidden(d, "main-view"))
        check("3.5 Abrir consola DM -> /dm directo en consola (SIN re-pedir password)",
              not is_hidden(drv, "main-view") and is_hidden(drv, "login-view"))
        sess_dm_token = ls_get(drv, "dnd_dm_token")
        check("3.6 dnd_dm_token guardado", bool(sess_dm_token))

        status, _ = http("POST", "/api/combatants",
                         body={"name": player_display, "hp_max": 20,
                               "initiative": 12, "kind": "pc"},
                         headers={"X-DM-Token": sess_dm_token})
        check("3.7 PC combatant creado via API", status == 200, f"HTTP {status}")
        return user_token, campaign_id, join_code
    finally:
        drv.quit()


def test_4_new_player_autolink(join_code, player_display, headless):
    info("Test 4: Jugador con cuenta (auto-vinculo por nombre)")
    drv = new_driver(headless)
    try:
        drv.get(BASE + "/register")
        wait_el(drv, "#register-form")
        fill(drv, "#f-username", "pltest_" + SUFFIX)
        fill(drv, "#f-password", "test12345")
        fill(drv, "#f-display", player_display)
        click(drv, "#btn-submit")
        wait_path(drv, "/campaigns")
        check("4.1 jugador /register -> /campaigns", True)

        fill(drv, "#join-code", join_code)
        click(drv, '#form-join button[type="submit"]')
        WebDriverWait(drv, 10).until(
            lambda d: "Te uniste" in (d.find_element(By.ID, "msg").text or ""))
        check("4.2 unirse por join_code de CAMPANA", True)

        # OJO: buscar "Unirme a sesion" (de la tarjeta), NO "Unirme"
        # (del form de join por codigo, que tambien esta visible).
        try:
            WebDriverWait(drv, 10).until(
                lambda d: any("Unirme a sesión" in (b.text or "")
                              for b in d.find_elements(By.TAG_NAME, "button")))
        except Exception:
            metas = [c.find_element(By.CSS_SELECTOR, ".campaign-meta").text
                     for c in drv.find_elements(By.CSS_SELECTOR, ".campaign-card")]
            buttons = [b.text for b in drv.find_elements(By.TAG_NAME, "button")]
            check("4.3a boton 'Unirme a sesion' presente", False,
                  f"metas={metas} buttons={buttons}")
            raise
        for b in drv.find_elements(By.TAG_NAME, "button"):
            if "Unirme a sesión" in (b.text or ""):
                b.click()
                break
        wait_path(drv, "/player")
        WebDriverWait(drv, 10).until(lambda d: not is_hidden(d, "combat-view"))
        check("4.3 Unirme a sesion -> /player con combate", True)
    finally:
        drv.quit()


def test_5_autolink(player_display):
    info("Test 5: PC auto-vinculado (player_id y user_id != NULL)")
    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT player_id, user_id FROM combatants "
            "WHERE kind='pc' AND lower(name)=lower(?) "
            "ORDER BY id DESC LIMIT 1", (player_display,)).fetchone()
    finally:
        conn.close()
    ok = row is not None and row["player_id"] is not None
    check("5.1 combatant.player_id != NULL", ok,
          f"player_id={row['player_id'] if row else None}")
    check("5.2 combatant.user_id != NULL",
          ok and row["user_id"] is not None,
          f"user_id={row['user_id'] if row else None}")


def test_6_409_double_session(user_token, campaign_id):
    info("Test 6: crear sesion con otra activa -> 409")
    status, body = http("POST", f"/api/campaigns/{campaign_id}/sessions",
                        headers={"X-User-Token": user_token})
    check("6.1 POST /sessions con sesion activa -> 409",
          status == 409, f"HTTP {status} {body}")


def test_7_migration_idempotent():
    info("Test 7: migration_v2_0 idempotente")
    r = subprocess.run([sys.executable, "-m", "backend.migration_v2_0"],
                       capture_output=True, text=True, timeout=30)
    out = (r.stdout or "") + (r.stderr or "")
    check("7.1 'ya migrado' en salida",
          "ya migrado" in out,
          (out.strip().splitlines()[-1] if out.strip() else ""))


def test_8_reset_dm_password():
    info("Test 8: reset_dm_password")
    r = subprocess.run([sys.executable, "-m", "backend.reset_dm_password"],
                       capture_output=True, text=True, timeout=30)
    ok_line = "OK: password del user 'dm' actualizada"
    check("8.1 reset script imprime OK",
          ok_line in (r.stdout or ""),
          (r.stdout or r.stderr or "").strip())
    status, _ = http("POST", "/api/auth/login",
                     body={"username": "dm", "password": DM_PW})
    check("8.2 /api/auth/login dm con DM_PASSWORD -> 200",
          status == 200, f"HTTP {status}")


# --------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headful", action="store_true")
    args = ap.parse_args()
    headless = not args.headful

    if not DM_PW:
        print("ERROR: DM_PASSWORD vacia en config.py")
        return 2

    # Fase 2.1.1: cerrar sesiones huérfanas antes de empezar.
    setUpModule()

    if not preflight():
        return 2

    try:
        code, sess_dm_token = test_1_legacy_dm(headless)
        test_2_legacy_player(code, headless)
        test_1_5_close_legacy(sess_dm_token)

        player_display = "Heroe " + SUFFIX
        user_token, campaign_id, join_code = test_3_new_dm_and_campaign(
            headless, player_display)

        if join_code:
            test_4_new_player_autolink(join_code, player_display, headless)
            test_5_autolink(player_display)

        if user_token and campaign_id:
            test_6_409_double_session(user_token, campaign_id)

        test_7_migration_idempotent()
        test_8_reset_dm_password()
    except Exception as e:
        check("excepcion no controlada", False, f"{type(e).__name__}: {e}")

    print()
    print("=" * 60)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    fails = [n for n, ok, _ in RESULTS if not ok]
    if fails:
        print("FALLOS:")
        for n in fails:
            print("  -", n)
    print(f"RESUMEN: {passed}/{total} PASS")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
