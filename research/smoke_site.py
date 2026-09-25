"""
Prueba de humo del frontend, a tamaño de móvil.

Levanta nada: asume que el sitio ya se sirve (python -m http.server 8765
--directory site). Recorre el flujo real —buscar, seguir, ver mis atletas,
ver tatamis— capturando errores de consola y una imagen de cada paso.

Uso:  python research/smoke_site.py [url]
"""
import json
import sys
import urllib.request
from pathlib import Path

from patchright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
SALIDA = Path(__file__).resolve().parent.parent / "tmp-capturas"


def termino_de_busqueda(url):
    """Un nombre que exista en los datos servidos ahora mismo.

    Se lee de data.json en lugar de escribirlo aquí: así no queda ningún nombre
    real en el repositorio y la prueba sirve igual con datos reales que con los
    fixtures anonimizados.
    """
    with urllib.request.urlopen(url.rstrip("/") + "/data.json", timeout=20) as r:
        atletas = json.loads(r.read().decode("utf-8")).get("athletes", [])
    return atletas[0]["name"] if atletas else ""


def main():
    SALIDA.mkdir(exist_ok=True)
    errores = []
    pasos = 0

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        ctx = navegador.new_context(
            viewport={"width": 390, "height": 844},  # tamaño de móvil
            device_scale_factor=2, locale="es-ES")
        page = ctx.new_page()
        page.on("console", lambda m: errores.append(f"{m.type}: {m.text}")
                if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errores.append(f"pageerror: {e}"))

        def captura(nombre):
            nonlocal pasos
            pasos += 1
            ruta = SALIDA / f"{pasos:02d}-{nombre}.png"
            page.screenshot(path=str(ruta))
            print(f"  [{pasos}] {nombre} -> {ruta.name}")

        print(f"Abriendo {URL}")
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1200)
        print(f"  titulo: {page.title()!r}")
        print(f"  estado: {page.inner_text('#estado')!r}")
        captura("inicio-sin-seguidos")

        busqueda = termino_de_busqueda(URL)
        print(f"Buscando un atleta ({busqueda!r})")
        if not busqueda:
            errores.append("data.json no trae atletas con los que buscar")
        page.click('.pestana[data-vista="buscar"]')
        page.fill("#busqueda", busqueda)
        page.wait_for_timeout(600)
        resultados = page.inner_text("#resultados").splitlines()[0]
        print(f"  {resultados}")
        captura("busqueda")

        print("Siguiendo al primero")
        # Acotado a los resultados: "Mis atletas" también tiene botones de
        # seguir, y los suyos están ocultos mientras se mira la búsqueda.
        botones = page.query_selector_all("#resultados [data-seguir]")
        if not botones:
            errores.append("la búsqueda no devolvió ningún atleta")
        else:
            botones[0].click()
            page.wait_for_timeout(400)
            page.click('.pestana[data-vista="seguidos"]')
            page.wait_for_timeout(600)
            captura("mis-atletas")

        print("Abriendo la ficha del atleta")
        ficha = page.query_selector("#vista-seguidos [data-atleta]")
        if ficha:
            ficha.click()
            page.wait_for_timeout(500)
            captura("ficha-atleta")
            page.click("#cerrar-detalle")

        print("Vista de tatamis")
        page.click('.pestana[data-vista="tatamis"]')
        page.wait_for_timeout(700)
        captura("tatamis")

        print("Comprobando que 'seguir' persiste al recargar")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1200)
        contador = page.inner_text("#contador-seguidos").strip()
        print(f"  seguidos tras recargar: {contador!r}")
        if not contador:
            errores.append("los atletas seguidos no sobrevivieron a la recarga")

        navegador.close()

    print(f"\nCapturas en {SALIDA}")
    if errores:
        print(f"\n{len(errores)} problema(s):")
        for e in errores[:20]:
            print(f"  - {e}")
        return 1
    print("Sin errores de consola.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
