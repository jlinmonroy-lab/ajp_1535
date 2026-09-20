"""
Script de investigación desechable (Fase 0, continuación).
Igual que explore.py pero usando `patchright` (fork de Playwright con parches
anti-deteccion) en vez de Playwright vanilla, para comprobar si el bloqueo de
Cloudflare era por fingerprint de automatizacion o por reputacion de IP.

Siguiendo las recomendaciones de patchright: headless=False, sin forzar un
user_agent manual (dejar el real del navegador, para no generar
inconsistencias de fingerprint).
"""
import json
import re
import sys
from pathlib import Path
from patchright.sync_api import sync_playwright

BASE = "https://ajptour.com"
EVENT_ID = "1535"
EVENT_URL = f"{BASE}/es/event/{EVENT_ID}"
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURES.mkdir(exist_ok=True)

captured_requests = []


def on_response(response):
    req = response.request
    ct = response.headers.get("content-type", "")
    entry = {
        "url": response.url,
        "method": req.method,
        "status": response.status,
        "content_type": ct,
        "resource_type": req.resource_type,
    }
    captured_requests.append(entry)
    if "json" in ct and response.status == 200:
        try:
            body = response.text()
        except Exception:
            body = None
        if body:
            safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", response.url)[-120:]
            out = FIXTURES / f"xhr_{safe_name}.json"
            out.write_text(body, encoding="utf-8")
            print(f"[JSON XHR] {response.url} -> {out.name} ({len(body)} bytes)")


def dump_html(page, name):
    html = page.content()
    out = FIXTURES / name
    out.write_text(html, encoding="utf-8")
    print(f"[HTML] saved {out} ({len(html)} bytes), title={page.title()!r}")
    return html


def check_embedded_state(html, label):
    for marker in ["__NEXT_DATA__", "__INITIAL_STATE__", "__NUXT__", "window.__"]:
        if marker in html:
            print(f"  [{label}] contiene marcador de estado embebido: {marker}")


def main():
    headless = "--headless" in sys.argv  # por defecto headful, como recomienda patchright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(locale="es-ES")
        page = context.new_page()
        page.on("response", on_response)

        print(f"[patchright] Navegando a {EVENT_URL} (headless={headless})...")
        resp = page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=30000)
        print(f"Status HTTP de navegacion: {resp.status if resp else 'N/A'}")
        page.wait_for_timeout(3000)
        title = page.title()
        print(f"Titulo de pagina: {title!r}")

        t = title.lower()
        challenged = "just a moment" in t or "attention required" in t or "momento" in t

        if challenged:
            print("Challenge no resuelto de inmediato. Esperando hasta 20s extra...")
            for i in range(4):
                page.wait_for_timeout(5000)
                title = page.title()
                print(f"  tras {5*(i+1)}s -> titulo: {title!r}")
                if "momento" not in title.lower():
                    challenged = False
                    break

        cookies = context.cookies()
        cf_cookies = [c["name"] for c in cookies if "cf" in c["name"].lower()]
        print(f"Cookies presentes (nombres relacionados con cf): {cf_cookies}")
        print(f"Todas las cookies: {[c['name'] for c in cookies]}")

        html = dump_html(page, f"event_{EVENT_ID}_patchright.html")
        check_embedded_state(html, "patchright")

        hrefs = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href'))"
        )
        tab_links = sorted(set(h for h in hrefs if h and f"/event/{EVENT_ID}" in h))
        print("\nEnlaces reales encontrados que contienen la ruta del evento:")
        for h in tab_links:
            print(f"  {h}")
        (FIXTURES / "event_tab_links_patchright.json").write_text(
            json.dumps(tab_links, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        browser.close()

    print("\nPeticiones de red capturadas (resumen):")
    for r in captured_requests:
        if r["resource_type"] in ("xhr", "fetch") or "json" in r["content_type"]:
            print(f"  [{r['status']}] {r['method']} {r['url']} ({r['content_type']})")

    (FIXTURES / "network_log_patchright.json").write_text(
        json.dumps(captured_requests, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nLog de red completo guardado en {FIXTURES / 'network_log_patchright.json'}")
    print(f"\nVEREDICTO: challenged={challenged}")


if __name__ == "__main__":
    sys.exit(main() or 0)
