"""
Script de investigación desechable (Fase 0, cierre).
Solo tiene sentido ejecutarlo desde una red "buena" (móvil/residencial) que ya
sabemos que pasa el Cloudflare Managed Challenge de ajptour.com.

Hace dos cosas:
1. Comprueba con una petición HTTP simple (sin navegador) si desde esta red
   ya basta eso, o si de verdad hace falta un navegador real.
2. Navega con patchright por las pestañas reales del evento (Information,
   Athletes, Brackets, Matches, Schedule, Results, Livestreams), capturando
   HTML final, cualquier JSON interno real, y las rutas reales de cada pestaña,
   todo a fixtures/.

No forma parte de la aplicación final.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path
from patchright.sync_api import sync_playwright

BASE = "https://ajptour.com"
EVENT_ID = "1535"
EVENT_URL = f"{BASE}/es/event/{EVENT_ID}"
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURES.mkdir(exist_ok=True)

captured_requests = []


def plain_http_check():
    print("=== 1) Comprobación con HTTP simple (sin navegador) ===")
    req = urllib.request.Request(
        EVENT_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"STATUS: {resp.status}")
            (FIXTURES / "plain_http_event_1535.html").write_text(body, encoding="utf-8")
            print(f"Guardado ({len(body)} bytes). challenged={'Un momento' in body}")
            return "Un momento" not in body
    except urllib.error.HTTPError as e:
        print(f"STATUS: {e.code} (fallo)")
        return False


def on_response(response):
    req = response.request
    ct = response.headers.get("content-type", "")
    captured_requests.append({
        "url": response.url, "method": req.method, "status": response.status,
        "content_type": ct, "resource_type": req.resource_type,
    })
    if "json" in ct and response.status == 200 and "cloudflare" not in response.url:
        try:
            body = response.text()
        except Exception:
            body = None
        if body:
            safe = re.sub(r"[^a-zA-Z0-9]+", "_", response.url)[-100:]
            out = FIXTURES / f"xhr_{safe}.json"
            out.write_text(body, encoding="utf-8")
            print(f"  [JSON XHR] {response.url} -> {out.name} ({len(body)} bytes)")


def browser_pass():
    print("\n=== 2) Navegación completa con patchright ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="es-ES")
        page = context.new_page()
        page.on("response", on_response)

        print(f"Navegando a {EVENT_URL} ...")
        resp = page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        title = page.title()
        print(f"Status={resp.status if resp else 'N/A'} Titulo={title!r}")
        if "momento" in title.lower():
            print("SIGUE BLOQUEADO incluso en red buena. Abortando captura de pestañas.")
            browser.close()
            return False

        html = page.content()
        (FIXTURES / f"event_{EVENT_ID}_information.html").write_text(html, encoding="utf-8")
        for marker in ["__NEXT_DATA__", "__INITIAL_STATE__", "__NUXT__"]:
            if marker in html:
                print(f"  Estado embebido encontrado: {marker}")

        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
        tab_links = sorted(set(h for h in hrefs if h and f"/event/{EVENT_ID}" in h))
        (FIXTURES / "event_tab_links_real.json").write_text(
            json.dumps(tab_links, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Rutas reales de pestañas encontradas ({len(tab_links)}):")
        for h in tab_links:
            print(f"  {h}")

        # Visitar cada pestaña real encontrada y volcar su HTML
        for href in tab_links:
            url = href if href.startswith("http") else BASE + href
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
                slug = re.sub(r"[^a-zA-Z0-9]+", "_", href).strip("_")
                out_html = page.content()
                (FIXTURES / f"event_{EVENT_ID}_{slug}.html").write_text(out_html, encoding="utf-8")
                print(f"  [OK] {url} -> event_{EVENT_ID}_{slug}.html ({len(out_html)} bytes)")
            except Exception as e:
                print(f"  [ERROR] {url}: {e}")

        browser.close()
        return True


def main():
    ok_http = plain_http_check()
    ok_browser = browser_pass()

    (FIXTURES / "network_log_real.json").write_text(
        json.dumps(captured_requests, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nVEREDICTO: http_simple_basta={ok_http} navegador_paso={ok_browser}")


if __name__ == "__main__":
    sys.exit(main() or 0)
