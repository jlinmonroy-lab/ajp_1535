"""
Mide cuánto tarda un dato nuevo en llegar al móvil, que es lo que decide si la
arquitectura elegida sirve.

El requisito es <2 min con refresco cada 75s. GitHub Pages reconstruye en cada
push y documenta un límite blando de 10 builds/hora (un push cada 75s son ~48),
respondiendo 429 al superarlo. Por eso se miden **dos vías a la vez** con el
mismo push, para poder comparar con datos en vez de con suposiciones:

  1. GitHub Pages          -> pasa por un build
  2. raw.githubusercontent -> sin build, pero con cache propia (~5 min)

Cada ciclo inyecta un identificador único al principio del data.json, lo
publica y cronometra cuándo aparece en cada URL. Se sondea con `Range` para
bajar solo los primeros bytes en lugar de 400 KB por comprobación, y **sin**
parámetros de cache-busting: un `?t=...` esquivaría el CDN y falsearía justo lo
que se quiere medir.

Uso:  python research/measure_latency.py [--ciclos 10] [--intervalo 75]
"""
import argparse
import json
import statistics
import subprocess
import sys
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
VIAS = {
    "pages": f"https://{USUARIO}.github.io/{REPO}/data.json",
    "raw": f"https://raw.githubusercontent.com/{USUARIO}/{REPO}/gh-pages/data.json",
}

CABECERA_NONCE = 200  # bytes iniciales donde va el nonce


def sondear(url):
    """Devuelve (status, primeros bytes) sin descargar el fichero entero."""
    req = urllib.request.Request(url, headers={
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Range": f"bytes=0-{CABECERA_NONCE}",
        "User-Agent": "medicion-latencia-ajp/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def publicar_nonce(worktree: Path, nonce: str, log):
    """Pone el nonce como primera clave del data.json y lo sube."""
    data = worktree / "data.json"
    estado = json.loads(data.read_text(encoding="utf-8"))
    estado = {"_nonce": nonce, **{k: v for k, v in estado.items() if k != "_nonce"}}
    data.write_text(json.dumps(estado, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")

    for args in (["add", "-A"], ["commit", "--amend", "-m", "medicion de latencia"],
                 ["push", "--force", "origin", "gh-pages"]):
        r = subprocess.run(["git", *args], cwd=str(worktree),
                           capture_output=True, text=True)
        if r.returncode != 0:
            log(f"  git {args[0]} falló: {r.stderr.strip()[:160]}")
            return False
    return True


def un_ciclo(worktree, nonce, timeout, log):
    if not publicar_nonce(worktree, nonce, log):
        return {}
    t0 = time.time()
    log(f"  push hecho, esperando a ver {nonce} …")

    pendientes = dict(VIAS)
    resultado = {}
    while pendientes and time.time() - t0 < timeout:
        for via in list(pendientes):
            status, cuerpo = sondear(pendientes[via])
            if status == 429:
                resultado[via] = {"error": "429 rate limit",
                                  "segundos": round(time.time() - t0, 1)}
                del pendientes[via]
                log(f"    {via}: HTTP 429 (límite de GitHub)")
            elif nonce in cuerpo:
                s = round(time.time() - t0, 1)
                resultado[via] = {"segundos": s}
                del pendientes[via]
                log(f"    {via}: visible en {s}s")
        if pendientes:
            time.sleep(2)

    for via in pendientes:
        resultado[via] = {"error": f"no apareció en {timeout}s"}
        log(f"    {via}: NO apareció en {timeout}s")
    return resultado


def resumen(mediciones, via):
    tiempos = [m[via]["segundos"] for m in mediciones
               if via in m and "segundos" in m[via] and "error" not in m[via]]
    fallos = sum(1 for m in mediciones if via in m and "error" in m[via])
    limites = sum(1 for m in mediciones
                  if via in m and "429" in str(m[via].get("error", "")))
    if not tiempos:
        return {"n": 0, "fallos": fallos, "429": limites}
    ordenados = sorted(tiempos)
    return {
        "n": len(tiempos),
        "mediana": round(statistics.median(ordenados), 1),
        "p90": round(ordenados[min(len(ordenados) - 1, int(len(ordenados) * 0.9))], 1),
        "max": round(max(ordenados), 1),
        "fallos": fallos,
        "429": limites,
    }


def escribir_informe(mediciones, args):
    filas = []
    for via in VIAS:
        r = resumen(mediciones, via)
        if r["n"]:
            filas.append(f"| {via} | {r['n']} | {r['mediana']}s | {r['p90']}s | "
                         f"{r['max']}s | {r['fallos']} | {r['429']} |")
        else:
            filas.append(f"| {via} | 0 | — | — | — | {r['fallos']} | {r['429']} |")

    INFORME.parent.mkdir(exist_ok=True)
    INFORME.write_text(f"""# Latencia de publicación

Medido el {datetime.now().strftime('%Y-%m-%d %H:%M')} con
`python research/measure_latency.py --ciclos {args.ciclos} --intervalo {args.intervalo}`.

Cada ciclo inyecta un identificador único en `data.json`, lo publica con
`commit --amend` + `push --force`, y cronometra cuándo se ve en cada URL.
Se sondea cada 2s, sin cache-busting, para medir lo que vería un móvil real.

| vía | medidas | mediana | p90 | máximo | fallos | 429 |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(filas)}

Requisito del proyecto: **<2 min (120s)**.

## Detalle por ciclo

```
{json.dumps(mediciones, indent=2, ensure_ascii=False)}
```
""", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description="Mide la latencia de publicación")
    p.add_argument("--ciclos", type=int, default=10)
    p.add_argument("--intervalo", type=int, default=75)
    p.add_argument("--timeout", type=int, default=300)
    args = p.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    worktree = Path(cfg["publish"]["worktree"])
    if not (worktree / "data.json").exists():
        print(f"No hay data.json en {worktree}. Publica algo antes.")
        return 1

    def log(m):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)

    log(f"{args.ciclos} ciclos cada {args.intervalo}s "
        f"(~{args.ciclos * args.intervalo // 60} min)")
    mediciones = []
    for i in range(1, args.ciclos + 1):
        inicio = time.time()
        log(f"Ciclo {i}/{args.ciclos}")
        mediciones.append(un_ciclo(worktree, f"nonce-{int(time.time())}-{i}",
                                   args.timeout, log))
        escribir_informe(mediciones, args)  # por si se corta a mitad
        if i < args.ciclos:
            time.sleep(max(0, args.intervalo - (time.time() - inicio)))

    print()
    for via in VIAS:
        print(f"{via}: {resumen(mediciones, via)}")
    print(f"\nInforme en {INFORME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
