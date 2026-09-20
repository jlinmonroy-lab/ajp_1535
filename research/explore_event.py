"""
Paso 1 — Con la sesión ya iniciada, averiguar qué expone de verdad el evento.

login_once.py deja el perfil de Chrome logueado en secrets/chrome-profile, pero
/schedule/new/matcategories.json devuelve 403 "not allowed" (error de Smoothcomp,
no reto de Cloudflare). Este script averigua por qué, sin adivinar:

1. Carga la página del evento y dice si existe y cómo se llama.
2. Saca las pestañas reales del evento desde el DOM.
3. Sondea rutas JSON candidatas y reporta el status de cada una.
4. Navega por cada pestaña capturando todas las XHR, para descubrir qué
   endpoints usa la propia web (que es la fuente de verdad, no mis suposiciones).

Todo lo que reciba se vuelca a fixtures/ para poder escribir el parser contra
datos reales.

No forma parte de la aplicación final.

Uso:  python research/explore_event.py [event_id]
"""
import json
import re
import sys
from pathlib import Path

from patchright.sync_api import sync_playwright

from login_once import abrir_contexto

BASE = "https://ajptour.com"
EVENT_ID = sys.argv[1] if len(sys.argv) > 1 else "1535"
EVENT_URL = f"{BASE}/en/event/{EVENT_ID}"

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURES.mkdir(exist_ok=True)

# Rutas candidatas. Las de schedule/new son las que usa Smoothcomp en eventos
# abiertos (verificado contra el evento 29650); el resto son las pestañas
# clásicas, para ver cuáles responden en este tenant.
CANDIDATAS = [
    "/schedule/new/matcategories.json",
    "/schedule/matcategories.json",
    "/schedule/new",
    "/schedule",
    "/matches",
    "/participants",
    "/results",
    "/brackets",
    "/livestreams",
    "/information",
]

capturado = []


def slug(texto):
    return re.sub(r"[^a-zA-Z0-9]+", "_", texto).strip("_")[:100]


def on_response(response):
    """Registra toda respuesta y vuelca a fixtures/ el JSON propio de la app."""
    ct = response.headers.get("content-type", "")
    capturado.append({
        "url": response.url,
        "method": response.request.method,
        "status": response.status,
        "content_type": ct,
        "resource_type": response.request.resource_type,
    })
    if "json" in ct and response.status == 200 and "cloudflare" not in response.url:
        try:
            cuerpo = response.text()
        except Exception:
            return
        destino = FIXTURES / f"xhr_{slug(response.url)}.json"
        destino.write_text(cuerpo, encoding="utf-8")
        print(f"    [JSON] {response.url} -> {destino.name} ({len(cuerpo)} bytes)")


def main():
    with sync_playwright() as p:
        context = abrir_contexto(p)
        page = context.pages[0] if context.pages else context.new_page()
        page.on("response", on_response)

        print(f"=== 1) Página del evento: {EVENT_URL}")
        resp = page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        print(f"STATUS: {resp.status if resp else 'N/A'}")
        print(f"TITULO: {page.title()!r}")

        html = page.content()
        (FIXTURES / f"event_{EVENT_ID}_real.html").write_text(html, encoding="utf-8")
        print(f"HTML guardado ({len(html)} bytes)")
        for marcador in ("__NEXT_DATA__", "__INITIAL_STATE__", "__NUXT__", "window.__"):
            if marcador in html:
                print(f"  estado embebido: {marcador}")

        print("\n=== 2) Pestañas reales del evento (desde el DOM)")
        hrefs = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href'))")
        pestanas = sorted({h for h in hrefs if h and f"/event/{EVENT_ID}" in h})
        (FIXTURES / f"event_{EVENT_ID}_tabs.json").write_text(
            json.dumps(pestanas, indent=2, ensure_ascii=False), encoding="utf-8")
        if pestanas:
            for h in pestanas:
                print(f"  {h}")
        else:
            print("  (ninguna: o el evento no existe, o el DOM no llegó a render)")

        print("\n=== 3) Sondeo de rutas candidatas (sin navegar)")
        accesibles = []
        for ruta in CANDIDATAS:
            url = f"{EVENT_URL}{ruta}"
            try:
                r = context.request.get(url)
                ct = r.headers.get("content-type", "")[:40]
                print(f"  {r.status:>3}  {ruta:<36} {ct}")
                if r.status == 200:
                    accesibles.append(ruta)
            except Exception as e:
                print(f"  ERR  {ruta:<36} {type(e).__name__}")

        print("\n=== 4) Navegación, capturando XHR")
        # Solo tiene sentido navegar a lo que responde 200: una ruta que da 403 o
        # 404 no va a disparar ninguna XHR de la aplicación.
        destinos = pestanas or [f"/en/event/{EVENT_ID}{r}" for r in accesibles]
        if not destinos:
            print("  (ninguna ruta accesible que visitar)")
        for href in destinos:
            url = href if href.startswith("http") else BASE + href
            print(f"  -> {url}")
            try:
                r = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                # Vue monta después del primer paint y sus XHR llegan más tarde;
                # con menos margen se capturaba la página aún vacía.
                page.wait_for_timeout(9000)
                print(f"     status={r.status if r else 'N/A'} titulo={page.title()!r}")
                cuerpo = page.content()
                (FIXTURES / f"event_{EVENT_ID}_{slug(href)}.html").write_text(
                    cuerpo, encoding="utf-8")
                print(f"     html guardado ({len(cuerpo)} bytes)")
                # Las pestañas reales solo aparecen una vez que carga una página
                # buena; desde el evento daban 403.
                nuevos = page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.getAttribute('href'))")
                tabs = sorted({h for h in nuevos if h and f"/event/{EVENT_ID}" in h})
                if tabs:
                    print("     pestañas visibles desde aquí:")
                    for t in tabs:
                        print(f"       {t}")
                    (FIXTURES / f"event_{EVENT_ID}_tabs.json").write_text(
                        json.dumps(tabs, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"     ERROR: {type(e).__name__}: {e}")

        (FIXTURES / f"network_log_{EVENT_ID}_session.json").write_text(
            json.dumps(capturado, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nPeticiones registradas: {len(capturado)}")
        propias = [c for c in capturado
                   if "json" in c["content_type"] and "cloudflare" not in c["url"]]
        print(f"Respuestas JSON de la app: {len(propias)}")
        for c in propias:
            print(f"  {c['status']}  {c['url']}")

        context.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
