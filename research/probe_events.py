"""
Paso 1 — ¿De qué depende que el schedule sea accesible?

El evento 1535 (AJP NO-GI MADRID 2026) dice "Brackets are not published yet" y su
matcategories.json responde 403 "not allowed". La hipótesis es que el 403 no es
por permisos ni por anti-bot, sino porque todavía no hay schedule publicado.

Este script la contrasta sondeando varios eventos AJP, cada uno dos veces: con las
cookies de la sesión y sin ellas. Si un evento con schedule publicado responde 200
en ambos casos, el login no hace falta para leer datos y la arquitectura se
simplifica bastante.

Sirve además para encontrar un evento pasado con datos reales contra el que
escribir el parser mientras el 1535 sigue sin publicar.

Uso:  python research/probe_events.py [id ...]
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://ajptour.com"
SECRETS = Path(__file__).resolve().parent.parent / "secrets"
STATE_FILE = SECRETS / "storage_state.json"

# Eventos AJP conocidos (de búsquedas y del propio sitio). 1535 es el objetivo;
# el resto son pasados, para encontrar uno con schedule publicado.
POR_DEFECTO = ["1535", "1257", "1216", "1151"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

PAUSA_S = 2.5  # cortesía con el origen entre peticiones


def cookie_header():
    if not STATE_FILE.exists():
        return ""
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    relevantes = [c for c in state.get("cookies", [])
                  if "ajptour.com" in c.get("domain", "")]
    return "; ".join(f"{c['name']}={c['value']}" for c in relevantes)


def get(url, cookies=""):
    cabeceras = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
    }
    if cookies:
        cabeceras["Cookie"] = cookies
    req = urllib.request.Request(url, headers=cabeceras)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", errors="replace")
        # Distinguir el error propio de Smoothcomp del reto de Cloudflare importa:
        # el primero es "no hay datos / no puedes", el segundo es anti-bot.
        if "not allowed" in cuerpo:
            return e.code, "<403 not allowed - Smoothcomp>"
        if "Un momento" in cuerpo or "Just a moment" in cuerpo:
            return e.code, "<reto de Cloudflare>"
        return e.code, cuerpo[:120]
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def main():
    ids = sys.argv[1:] or POR_DEFECTO
    cookies = cookie_header()
    print(f"Cookies de sesión: {'sí' if cookies else 'NO (solo pruebas anónimas)'}\n")
    print(f"{'evento':<8} {'con sesión':<34} {'anónimo':<34}")
    print("-" * 78)

    accesibles = []
    for ev in ids:
        url = f"{BASE}/en/event/{ev}/schedule/new/matcategories.json"

        s1, b1 = get(url, cookies) if cookies else (None, "(sin cookies)")
        time.sleep(PAUSA_S)
        s2, b2 = get(url)
        time.sleep(PAUSA_S)

        def resumen(status, cuerpo):
            if status == 200:
                return f"200 {cuerpo[:28]}"
            return f"{status} {cuerpo[:28]}"

        print(f"{ev:<8} {resumen(s1, b1):<34} {resumen(s2, b2):<34}")
        if 200 in (s1, s2):
            accesibles.append((ev, s2 == 200))

    print()
    if not accesibles:
        print("Ningún evento con schedule accesible. Si todos dicen 'not allowed',")
        print("la hipótesis se sostiene: el 403 es 'schedule no publicado'.")
        return 1

    for ev, anonimo in accesibles:
        print(f"Evento {ev}: schedule ACCESIBLE"
              f"{' incluso sin login' if anonimo else ' (requiere sesión)'}")
    print("\nSiguiente: python research/capture_event.py <id> para volcar fixtures reales.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
