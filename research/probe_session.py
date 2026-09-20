"""
Paso 0 — La pregunta que decide la arquitectura del scraper:
¿basta una petición HTTP simple llevando las cookies de la sesión, o hace falta
arrancar un navegador en cada ciclo de refresco?

Lee secrets/storage_state.json (lo genera research/login_once.py) y pide los tres
endpoints del schedule con urllib, sin navegador y sin dependencias externas.

  200 en los tres  -> el scraper puede ser httpx puro: rápido, ligero, sin navegador.
  403              -> hace falta navegador con sesión; se replantea el Paso 2.

No imprime nunca el valor de una cookie: el repo es público y esta salida se pega
en conversaciones.

Uso:  python research/probe_session.py
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://ajptour.com"
EVENT_ID = "1535"
SCHEDULE = f"{BASE}/en/event/{EVENT_ID}/schedule/new"

SECRETS = Path(__file__).resolve().parent.parent / "secrets"
STATE_FILE = SECRETS / "storage_state.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


def cookie_header():
    """Las cookies de storage_state, aplanadas a una cabecera Cookie."""
    if not STATE_FILE.exists():
        print(f"No existe {STATE_FILE}.")
        print("Ejecuta primero: python research/login_once.py")
        sys.exit(1)
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    cookies = state.get("cookies", [])
    # Solo las del dominio de AJP: no mandamos cookies de terceros a ningún sitio.
    relevant = [c for c in cookies if "ajptour.com" in c.get("domain", "")]
    print(f"Cookies cargadas para ajptour.com: {len(relevant)} (nombres: "
          f"{', '.join(sorted(c['name'] for c in relevant))})")
    return "; ".join(f"{c['name']}={c['value']}" for c in relevant)


def get(url, cookies):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Referer": f"{BASE}/en/event/{EVENT_ID}/schedule",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookies,
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:300]
    except Exception as e:  # noqa: BLE001 - queremos ver cualquier fallo de red tal cual
        return None, f"{type(e).__name__}: {e}"


def main():
    cookies = cookie_header()
    if not cookies:
        print("No hay cookies de ajptour.com en el storage_state. ¿Se completó el login?")
        return 1

    print(f"\n=== 1) días: {SCHEDULE}/matcategories.json")
    status, body = get(f"{SCHEDULE}/matcategories.json", cookies)
    print(f"STATUS: {status}")
    if status != 200:
        print(f"CUERPO: {body}")
        print("\nVEREDICTO: HTTP simple con cookies NO basta. Toca navegador con sesión.")
        return 1
    print(f"CUERPO: {body[:500]}")

    days = json.loads(body)
    if isinstance(days, dict):  # un único día llega como objeto, no como lista
        days = [days]
    print(f"Días encontrados: {len(days)}")

    time.sleep(2)
    day_id = days[0]["id"]
    print(f"\n=== 2) tatamis: {SCHEDULE}/mats.json/{day_id}")
    status, body = get(f"{SCHEDULE}/mats.json/{day_id}", cookies)
    print(f"STATUS: {status}")
    if status != 200:
        print(f"CUERPO: {body}")
        return 1
    mats = json.loads(body)
    print(f"Tatamis: {len(mats)} -> {', '.join(str(m.get('name')) for m in mats)}")

    time.sleep(2)
    mat_id = mats[0]["id"]
    print(f"\n=== 3) combates: {SCHEDULE}/mat/{mat_id}/matches.json")
    status, body = get(f"{SCHEDULE}/mat/{mat_id}/matches.json", cookies)
    print(f"STATUS: {status}")
    if status != 200:
        print(f"CUERPO: {body}")
        return 1
    matches = json.loads(body)
    print(f"Combates en este tatami: {len(matches)}")
    if matches:
        print("CAMPOS REALES: " + ", ".join(matches[0].keys()))
        print("\nEJEMPLO DE COMBATE:")
        print(json.dumps(matches[0], indent=2, ensure_ascii=False)[:1200])

    print(f"\nVEREDICTO: HTTP simple con cookies BASTA. "
          f"Ciclo estimado: {1 + len(days) + len(mats)} peticiones.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
