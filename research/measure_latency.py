"""
Mide cuánto tarda un dato nuevo en llegar al móvil, al ritmo real del evento.

El requisito es <2 min con refresco cada 75s. GitHub Pages reconstruye en cada
push y documenta un límite blando de 10 builds/hora (un push cada 75s son ~48),
respondiendo 429 al superarlo. Saber si aguanta ese ritmo es lo que decide la
arquitectura.

**El push y el sondeo van en hilos separados, y ahí está el meollo.** La primera
versión encadenaba los dos y, al esperar a que apareciera el dato, publicaba
cada ~4,5 min en lugar de cada 75s: medía un escenario que no era el real. Aquí
el publicador mantiene su cadencia pase lo que pase con el sondeo.

Si un push sobrescribe a otro antes de que llegue a servirse, ese nonce se
apunta como *sobrescrito*: significaría que al ritmo real el CDN no alcanza a
publicar todas las versiones, que es justo lo que interesa detectar.

Se mide GitHub Pages. raw.githubusercontent quedó descartado al medir 272,9s
(tiene una cache de ~5 min); se puede volver a incluir con --incluir-raw.

Uso:  python research/measure_latency.py [--ciclos 15] [--intervalo 75]
"""
import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config.json"
INFORME = RAIZ / "docs" / "latencia.md"

USUARIO = "jlinmonroy-lab"
REPO = "ajp_1535"
URL_PAGES = f"https://{USUARIO}.github.io/{REPO}/data.json"
URL_RAW = f"https://raw.githubusercontent.com/{USUARIO}/{REPO}/gh-pages/data.json"

CABECERA = 200  # bytes iniciales: el nonce va como primera clave del JSON

candado = threading.Lock()
pendientes = {}   # nonce -> momento del push
resultados = {}   # nonce -> {via: segundos | "sobrescrito"}
incidencias = []  # 429 y fallos de git, con su momento
orden = []        # nonces en el orden en que se publicaron
fin = threading.Event()


def log(mensaje):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {mensaje}", flush=True)


def sondear(url):
    """(status, primeros bytes). Con Range para no bajar 400 KB por sondeo."""
    req = urllib.request.Request(url, headers={
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Range": f"bytes=0-{CABECERA}",
        "User-Agent": "medicion-latencia-ajp/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def publicador(worktree, ciclos, intervalo):
    """Publica un nonce nuevo cada `intervalo` segundos, sin esperar al sondeo."""
    data = worktree / "data.json"
    for i in range(1, ciclos + 1):
        inicio = time.time()
        nonce = f"n{int(time.time())}x{i}"

        contenido = json.loads(data.read_text(encoding="utf-8"))
        contenido = {"_nonce": nonce,
                     **{k: v for k, v in contenido.items() if k != "_nonce"}}
        data.write_text(
            json.dumps(contenido, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")

        fallo = None
        for args in (["add", "-A"], ["commit", "--amend", "-m", "medicion"],
                     ["push", "--force", "origin", "gh-pages"]):
            r = subprocess.run(["git", *args], cwd=str(worktree),
                               capture_output=True, text=True)
            if r.returncode != 0:
                fallo = f"git {args[0]}: {r.stderr.strip()[:120]}"
                break

        with candado:
            if fallo:
                incidencias.append({"ciclo": i, "error": fallo})
                log(f"  ciclo {i}/{ciclos}: {fallo}")
            else:
                pendientes[nonce] = time.time()
                orden.append(nonce)
                log(f"  ciclo {i}/{ciclos}: push {nonce}")

        if i < ciclos:
            time.sleep(max(0, intervalo - (time.time() - inicio)))

    time.sleep(150)  # margen para que el último llegue a propagarse
    fin.set()


def sondeador(url, via):
    """Mira qué nonce sirve el CDN y cronometra los que estaban pendientes."""
    while not fin.is_set():
        status, cuerpo = sondear(url)
        ahora = time.time()

        if status == 429:
            with candado:
                incidencias.append({"via": via, "error": "HTTP 429",
                                    "hora": datetime.now().strftime("%H:%M:%S")})
            log(f"    {via}: HTTP 429 (límite de GitHub)")
        elif cuerpo:
            with candado:
                for nonce in [n for n in pendientes if n in cuerpo]:
                    segundos = round(ahora - pendientes.pop(nonce), 1)
                    resultados.setdefault(nonce, {})[via] = segundos
                    log(f"    {via}: {nonce} visible en {segundos}s")
                    # Lo publicado antes que este y aún pendiente ya no llegará
                    # a servirse nunca: quedó sobrescrito.
                    tope = orden.index(nonce)
                    for previo in [n for n in list(pendientes)
                                   if n in orden and orden.index(n) < tope]:
                        pendientes.pop(previo)
                        resultados.setdefault(previo, {})[via] = "sobrescrito"
                        log(f"    {via}: {previo} sobrescrito sin llegar a servirse")
        fin.wait(2)


def resumir(via):
    tiempos = sorted(v[via] for v in resultados.values()
                     if isinstance(v.get(via), (int, float)))
    sobrescritos = sum(1 for v in resultados.values() if v.get(via) == "sobrescrito")
    r429 = sum(1 for i in incidencias if i.get("error") == "HTTP 429")
    if not tiempos:
        return {"n": 0, "sobrescritos": sobrescritos, "429": r429}
    return {
        "n": len(tiempos),
        "mediana": round(statistics.median(tiempos), 1),
        "p90": round(tiempos[min(len(tiempos) - 1, int(len(tiempos) * 0.9))], 1),
        "max": round(max(tiempos), 1),
        "sobrescritos": sobrescritos,
        "429": r429,
    }


def escribir_informe(vias, args):
    filas = []
    for via in vias:
        r = resumir(via)
        if r["n"]:
            filas.append(f"| {via} | {r['n']} | {r['mediana']}s | {r['p90']}s | "
                         f"{r['max']}s | {r['sobrescritos']} | {r['429']} |")
        else:
            filas.append(f"| {via} | 0 | - | - | - | {r['sobrescritos']} | {r['429']} |")

    sin_resolver = [n for n in orden if n not in resultados]
    tabla = "\n".join(filas)
    inc = json.dumps(incidencias, indent=2, ensure_ascii=False) if incidencias else "ninguna"
    detalle = json.dumps(resultados, indent=2, ensure_ascii=False)
    builds_hora = 3600 // args.intervalo

    texto = f"""# Latencia de publicación

Medido el {datetime.now().strftime('%Y-%m-%d %H:%M')} con
`python research/measure_latency.py --ciclos {args.ciclos} --intervalo {args.intervalo}`.

Se publica un identificador único cada **{args.intervalo}s exactos** (el ritmo real del evento,
~{builds_hora} builds/hora) y en paralelo se sondea cada 2s qué versión sirve el CDN. Push y
sondeo van en hilos separados: encadenarlos hace que esperar al dato retrase el push siguiente,
y se acaba midiendo un ritmo que no es el real.

Sin cache-busting en las peticiones, para medir lo que vería un móvil de verdad.

| vía | medidas | mediana | p90 | máximo | sobrescritos | 429 |
| --- | --- | --- | --- | --- | --- | --- |
{tabla}

Requisito del proyecto: **<2 min (120s)**.
*Sobrescritos* = versiones que otro push reemplazó antes de que el CDN llegara a servirlas.

## Incidencias

```
{inc}
```

## Detalle

Publicados: {len(orden)} · medidos: {len(resultados)} · sin resolver al cerrar: {len(sin_resolver)}

```
{detalle}
```
"""
    INFORME.parent.mkdir(exist_ok=True)
    INFORME.write_text(texto, encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description="Mide la latencia de publicación")
    p.add_argument("--ciclos", type=int, default=15)
    p.add_argument("--intervalo", type=int, default=75)
    p.add_argument("--incluir-raw", action="store_true",
                   help="mide también raw.githubusercontent (descartado: ~273s)")
    args = p.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    worktree = Path(cfg["publish"]["worktree"])
    if not (worktree / "data.json").exists():
        print(f"No hay data.json en {worktree}. Publica algo antes.")
        return 1

    vias = {"pages": URL_PAGES}
    if args.incluir_raw:
        vias["raw"] = URL_RAW

    log(f"{args.ciclos} pushes cada {args.intervalo}s "
        f"(~{3600 // args.intervalo} builds/hora), midiendo: {', '.join(vias)}")

    hilos = [threading.Thread(target=sondeador, args=(url, via), daemon=True)
             for via, url in vias.items()]
    for h in hilos:
        h.start()

    try:
        publicador(worktree, args.ciclos, args.intervalo)
    except KeyboardInterrupt:
        fin.set()
    for h in hilos:
        h.join(timeout=5)

    escribir_informe(vias, args)
    print()
    for via in vias:
        print(f"{via}: {resumir(via)}")
    print(f"\nInforme en {INFORME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
