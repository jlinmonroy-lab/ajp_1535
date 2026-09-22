"""
Ensayo general: comprueba cómo se comporta el scraper el día del torneo.

Ejecuta **el scraper de verdad** como subproceso contra un origen simulado
(research/mock_origen.py) y provoca las situaciones que importan, en vez de
esperar a que ocurran durante el evento:

  A  primer ciclo                  -> publica
  B  el torneo no avanza           -> NO publica (no malgastar builds de Pages)
  C  el torneo avanza              -> publica, con combates en curso
  D  el origen se cae (503)        -> tras N fallos marca stale y conserva los datos
  E  el origen vuelve              -> se recupera solo

Se lanza `python -m scraper.main` en lugar de reimplementar el bucle: si se
reimplantara, main.py se quedaría sin probar, que es justo lo que se quiere
verificar.

Usa su propia configuración temporal, así que no toca config.json, y al
terminar devuelve la web al data.json anonimizado de siempre.

Uso:  python research/rehearsal.py [--puerto 8899]
"""
import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TMP = RAIZ / "tmp-ensayo"
URL_PUBLICA = "https://jlinmonroy-lab.github.io/ajp_1535/data.json"

ESPERA_FASE = 90  # segundos máximos por fase antes de darla por fallida


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


class Scraper:
    """El scraper corriendo de verdad, con su salida accesible."""

    def __init__(self, config):
        self.lineas = []
        self.candado = threading.Lock()
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "scraper.main", "--config", str(config)],
            cwd=str(RAIZ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace")
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        for linea in self.proc.stdout:
            with self.candado:
                self.lineas.append(linea.rstrip())

    def marca(self):
        with self.candado:
            return len(self.lineas)

    def desde(self, marca):
        with self.candado:
            return self.lineas[marca:]

    def esperar(self, texto, marca, limite=ESPERA_FASE):
        """Espera a que aparezca `texto` en la salida. True si llega a tiempo."""
        fin = time.time() + limite
        while time.time() < fin:
            for linea in self.desde(marca):
                if texto in linea:
                    return True
            if self.proc.poll() is not None:
                return False
            time.sleep(1)
        return False

    def parar(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def control(puerto, accion):
    with urllib.request.urlopen(
            f"http://127.0.0.1:{puerto}/control/{accion}", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def datos(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def preparar_config(puerto):
    TMP.mkdir(exist_ok=True)
    cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
    cfg.update({
        "eventId": "1257",
        "eventName": "Ensayo general",
        "baseUrl": f"http://127.0.0.1:{puerto}",
        "refreshSeconds": 12,
        "requestPauseSeconds": 0.05,
        "staleAfterFailures": 3,
        "output": "tmp-ensayo/data.json",
    })
    cfg["publish"] = {**cfg["publish"], "enabled": True,
                      # Alto a propósito: la fase B comprueba que NO publica
                      # cuando nada cambia, y un refresco de cortesía lo taparía.
                      "maxMinutesSinPublish": 60,
                      "message": "ensayo general"}
    destino = TMP / "config.json"
    destino.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return destino, RAIZ / cfg["output"]


def main():
    p = argparse.ArgumentParser(description="Ensayo general del scraper")
    p.add_argument("--puerto", type=int, default=8899)
    args = p.parse_args()

    resultados = {}
    config, salida = preparar_config(args.puerto)

    log("Arrancando origen simulado (torneo en vivo)")
    mock = subprocess.Popen(
        [sys.executable, "-u", str(RAIZ / "research" / "mock_origen.py"),
         "--puerto", str(args.puerto), "--simular-vivo"],
        cwd=str(RAIZ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)

    scraper = None
    try:
        control(args.puerto, "estado")  # falla pronto si el mock no levantó

        log("Arrancando el scraper")
        scraper = Scraper(config)

        # --- A: publica en el primer ciclo -------------------------------
        marca = scraper.marca()
        ok = scraper.esperar("publicado en gh-pages", marca)
        resultados["A: publica la primera vez"] = ok
        log(f"  A -> {'PASA' if ok else 'FALLA'}")

        # --- B: sin cambios no gasta un build ----------------------------
        control(args.puerto, "congelar")
        log("Torneo congelado: nada debería publicarse")
        marca = scraper.marca()
        ok = scraper.esperar("no se publica", marca, limite=60)
        publico = any("publicado en gh-pages" in l for l in scraper.desde(marca))
        resultados["B: no publica si nada cambia"] = ok and not publico
        log(f"  B -> {'PASA' if ok and not publico else 'FALLA'}")

        # --- C: vuelve a avanzar y hay combates en curso ------------------
        control(args.puerto, "descongelar")
        log("Torneo en marcha otra vez")
        marca = scraper.marca()
        ok = scraper.esperar("publicado en gh-pages", marca)
        estados = Counter(m["state"] for m in datos(salida)["matches"])
        en_curso = estados.get("running", 0)
        resultados["C: publica los cambios"] = ok
        resultados["C: hay combates en curso"] = en_curso > 0
        log(f"  C -> {'PASA' if ok else 'FALLA'} · estados: {dict(estados)}")

        # --- D: el origen se cae -----------------------------------------
        combates_antes = len(datos(salida)["matches"])
        control(args.puerto, "fallar")
        log("Origen caído (503): deberían acumularse fallos hasta marcar stale")
        marca = scraper.marca()
        ok = scraper.esperar("marcado stale", marca, limite=120)
        d = datos(salida)
        conserva = len(d["matches"]) == combates_antes
        resultados["D: marca stale al caerse el origen"] = ok and d["stale"]
        resultados["D: conserva el último estado bueno"] = conserva
        log(f"  D -> {'PASA' if ok and d['stale'] else 'FALLA'} · "
            f"stale={d['stale']} combates={len(d['matches'])}")

        # --- E: se recupera solo ------------------------------------------
        control(args.puerto, "funcionar")
        log("Origen restaurado: debería recuperarse sin tocar nada")
        marca = scraper.marca()
        ok = scraper.esperar("combates,", marca, limite=90)
        time.sleep(3)
        d = datos(salida)
        resultados["E: se recupera solo"] = ok and not d["stale"]
        log(f"  E -> {'PASA' if ok and not d['stale'] else 'FALLA'} · stale={d['stale']}")

    finally:
        if scraper:
            scraper.parar()
        mock.terminate()
        log("Restaurando el data.json anonimizado en la web")
        subprocess.run([sys.executable, "research/build_from_fixtures.py"],
                       cwd=str(RAIZ), capture_output=True)
        subprocess.run([sys.executable, "-c",
                        "import json,sys;sys.path.insert(0,'.');"
                        "from scraper.publish import publicar;from pathlib import Path;"
                        "cfg=json.load(open('config.json'));"
                        "cfg['publish']['enabled']=True;"
                        "publicar(cfg, Path('site/data.json'))"],
                       cwd=str(RAIZ), capture_output=True)
        shutil.rmtree(TMP, ignore_errors=True)

    print()
    for nombre, ok in resultados.items():
        print(f"  {'PASA ' if ok else 'FALLA'}  {nombre}")
    fallidas = [n for n, ok in resultados.items() if not ok]
    print(f"\n{len(resultados) - len(fallidas)}/{len(resultados)} comprobaciones superadas")
    return 1 if fallidas else 0


if __name__ == "__main__":
    sys.exit(main())
