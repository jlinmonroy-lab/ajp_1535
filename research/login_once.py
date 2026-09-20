"""
Paso 0 — Captura, una sola vez, la sesión iniciada del usuario en ajptour.com.

Abre Chrome (el de verdad, no el Chromium de Playwright) con un perfil propio y
persistente en secrets/chrome-profile. Persistente a propósito: así el reto de
Cloudflare y el login se resuelven una vez y las siguientes ejecuciones arrancan
ya dentro.

El usuario entra a mano; el script detecta solo cuándo ha entrado, porque se
lanza sin stdin interactivo y no puede pedir confirmación por consola. Luego
guarda el estado en secrets/storage_state.json y comprueba si con esa sesión el
endpoint JSON del schedule responde 200.

Va informando de URL y título en cada comprobación, para poder distinguir un
reto de Cloudflare de una pantalla de login normal sin tener que adivinar.

No forma parte de la aplicación final: se ejecuta cuando la sesión caduca.

Uso:  python research/login_once.py
"""
import json
import sys
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

BASE = "https://ajptour.com"
EVENT_ID = "1535"
LOGIN_URL = f"{BASE}/en/auth/login"
PROBE_URL = f"{BASE}/en/event/{EVENT_ID}/schedule/new/matcategories.json"

SECRETS = Path(__file__).resolve().parent.parent / "secrets"
STATE_FILE = SECRETS / "storage_state.json"
PROFILE_DIR = SECRETS / "chrome-profile"

ESPERA_MAX_S = 420  # 7 minutos para hacer login con calma (y resolver el reto si sale)


def es_reto(titulo):
    return any(s in (titulo or "").lower() for s in ("momento", "just a moment", "attention required"))


def esperar_login(context):
    """Espera a que el usuario complete el login.

    Smoothcomp es una app Vue y el login no cambia necesariamente la URL, así que
    mirar la barra de direcciones no vale (fue lo que falló en el primer intento).
    Se usan dos señales, y basta cualquiera de las dos:

      1. El endpoint que nos interesa ya responde 200 con las cookies del
         contexto. Es la señal definitiva: si esto pasa, hemos terminado.
      2. Alguna pestaña ha salido de /auth/login. Sirve de respaldo por si el
         evento 1535 estuviera restringido aun estando dentro, en cuyo caso la
         señal 1 no llegaría nunca.

    Devuelve "ok" (señal 1), "login" (señal 2) o None si se agota el tiempo o se
    cierra el navegador.
    """
    limite = time.time() + ESPERA_MAX_S
    siguiente_sondeo = 0.0
    while time.time() < limite:
        paginas = [pg for pg in context.pages if not pg.is_closed()]
        if not paginas:
            print("\nNavegador cerrado antes de completar el login.")
            return None

        # El sondeo va espaciado: es una petición real al origen, no conviene
        # repetirla cada pocos segundos durante siete minutos.
        if time.time() >= siguiente_sondeo:
            restante = int(limite - time.time())
            try:
                resp = context.request.get(PROBE_URL)
                status = resp.status
            except Exception as e:
                status = f"error ({type(e).__name__})"
            if status == 200:
                print(f"\nSesión válida: {PROBE_URL} responde 200.")
                return "ok"

            try:
                titulo = paginas[0].title()
            except Exception:
                titulo = None
            marca = " <-- RETO DE CLOUDFLARE" if es_reto(titulo) else ""
            print(f"  [{restante}s] schedule={status} titulo={titulo!r}{marca}")
            siguiente_sondeo = time.time() + 10

        fuera_del_login = [pg.url for pg in paginas if "/auth/login" not in pg.url]
        if fuera_del_login:
            print(f"\nLogin detectado (pestaña en {fuera_del_login[0]}).")
            return "login"

        time.sleep(2)

    print("\nSe agotó el tiempo de espera sin detectar el login.")
    return None


def abrir_contexto(p):
    """Chrome real con perfil persistente; si no está, Chromium de Playwright."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    comun = dict(user_data_dir=str(PROFILE_DIR), headless=False,
                 locale="es-ES", no_viewport=True)
    try:
        ctx = p.chromium.launch_persistent_context(channel="chrome", **comun)
        print("Navegador: Chrome instalado en el sistema (perfil propio persistente).")
        return ctx
    except Exception as e:
        print(f"No se pudo abrir Chrome ({type(e).__name__}); uso Chromium de Playwright.")
        return p.chromium.launch_persistent_context(**comun)


def main():
    SECRETS.mkdir(exist_ok=True)

    with sync_playwright() as p:
        context = abrir_contexto(p)
        page = context.pages[0] if context.pages else context.new_page()

        print(f"\nAbriendo {LOGIN_URL} ...")
        print("Si sale el reto de Cloudflare ('Un momento...'), resuélvelo tú.")
        print("Haz login en la ventana que se ha abierto; yo detecto solo cuándo entras.\n")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

        senal = esperar_login(context)
        if senal is None:
            context.close()
            return 1
        time.sleep(3)  # margen para que se asienten las cookies de sesión

        # La sesión vive en las cookies del contexto; storage_state las serializa
        # junto con localStorage, que es lo que luego reutiliza el scraper.
        context.storage_state(path=str(STATE_FILE))
        cookies = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("cookies", [])
        print(f"Sesión guardada en {STATE_FILE} ({len(cookies)} cookies).")
        if not cookies:
            print("AVISO: no se ha guardado ninguna cookie. ¿Seguro que el login se completó?")

        # Comprobación inmediata desde el propio navegador: si esto no da 200,
        # no tiene sentido pasar al probe con HTTP simple.
        print(f"\nProbando {PROBE_URL} desde el navegador ...")
        resp = page.request.get(PROBE_URL)
        print(f"STATUS: {resp.status}")
        print(f"RESPUESTA: {resp.text()[:400]}")
        if resp.status == 200:
            print("\nOK: la sesión da acceso al schedule.")
            print("Siguiente: python research/probe_session.py")
        else:
            print("\nNO OK: con sesión iniciada sigue sin dar 200.")
            print("Puede ser que el evento aún no tenga schedule publicado, o que AJP")
            print("restrinja esta pestaña. Dímelo y lo replanteamos.")

        context.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
