"""
Simula el torneo en vivo para ver cómo se comportará la web mañana.

Los datos reales están todos en `seeded`/`unseeded`, así que la página nunca se
ha visto con combates avanzando de verdad. Esto reproduce las dos jornadas en
unos minutos: los combates arrancan y terminan, las horas se retrasan como en un
torneo real, los cuadros avanzan y al final caen las medallas.

**No publica nada.** Trabaja sobre una copia en tmp-demo/ y la sirve en su
propio puerto: la web pública puede estar abierta en el móvil de cualquiera del
grupo, y enseñarle resultados inventados sería peor que no enseñar nada.

Los resultados son inventados y no predicen nada: esto sirve para ver el
comportamiento de la web, no para saber quién va a ganar.

Uso:  python research/simular_evento.py [--velocidad 15] [--puerto 8766]
"""
import argparse
import json
import random
import shutil
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.parse import construir_atletas  # noqa: E402
from scraper.publish import escribir_json  # noqa: E402

SITIO = RAIZ / "site"
DEMO = RAIZ / "tmp-demo"
ESTATICOS = ("index.html", "app.js", "style.css", ".nojekyll")

RESULTADOS = ("points", "submission", "decision", "points", "submission", "disqualification")

BANNER = """<div style="position:sticky;top:0;z-index:50;background:#b3261e;color:#fff;
padding:.5rem 16px;font:600 .85rem system-ui;text-align:center">
SIMULACIÓN · resultados inventados, no es el torneo real</div>"""


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def preparar_demo():
    """Copia aislada del sitio, con un banner que impida confundirla con la real."""
    DEMO.mkdir(exist_ok=True)
    for nombre in ESTATICOS:
        origen = SITIO / nombre
        if origen.exists():
            shutil.copy2(origen, DEMO / nombre)

    html = (DEMO / "index.html").read_text(encoding="utf-8")
    if "SIMULACIÓN ·" not in html:
        html = html.replace("<body>", "<body>\n" + BANNER, 1)
        (DEMO / "index.html").write_text(html, encoding="utf-8")


def cargar_estado():
    datos = json.loads((SITIO / "data.json").read_text(encoding="utf-8"))
    if not datos.get("matches"):
        raise SystemExit("site/data.json no tiene combates; lanza antes el scraper")
    return datos


def guionizar(datos, log=log):
    """Reparte oro, plata y bronce entre los del grupo.

    Dejarlo al azar casi siempre acaba con los tres eliminados pronto y sin ver
    ninguna medalla, que es justo lo que se quiere enseñar. Se les asigna un
    papel a cada uno y el resto del cuadro va por sorteo.
    """
    delgrupo = [a for a in datos["athletes"] if a.get("inGroup")]
    papeles = {}
    for atleta, papel in zip(delgrupo, ("gana", "pierde_final", "bronce")):
        papeles[atleta["id"]] = papel
        log(f"  {atleta['name']}: {papel}")
    return papeles


def preparar_desenlace(datos, papeles, log=log):
    """Asegura que cada uno del grupo llega al combate que le da su medalla.

    Con el cuadro a medio resolver, dejarlo a la propagación no basta: sus
    brackets tienen estructuras distintas y alguno no llega a ninguna final, así
    que la demo acababa sin enseñar ni una plata. Aquí se les sienta a la fuerza
    en el combate que decide su papel, y el resultado ya lo aplica el guion.
    """
    ronda_de = {"gana": "final", "pierde_final": "final", "bronce": "bronze match"}

    for atleta_id, papel in papeles.items():
        suyos = [c for c in datos["matches"]
                 if any(l["athleteId"] == atleta_id for l in c["sides"])]
        if not suyos:
            continue
        bracket = suyos[0]["bracketId"]
        yo = next(l for l in suyos[0]["sides"] if l["athleteId"] == atleta_id)

        decisivos = [c for c in datos["matches"]
                     if c["bracketId"] == bracket
                     and (c.get("round") or "").lower() == ronda_de[papel]]
        if not decisivos:
            # Sin ronda con ese nombre, vale el último combate del cuadro.
            hermanos = sorted((c for c in datos["matches"] if c["bracketId"] == bracket),
                              key=lambda c: c.get("estimatedStart") or "")
            decisivos = hermanos[-1:]
        if not decisivos:
            continue

        destino = decisivos[0]
        if all(l["athleteId"] != atleta_id for l in destino["sides"]):
            if len(destino["sides"]) < 2:
                destino["sides"].append({**yo, "isWinner": False})
            else:
                # Se cede el sitio a quien no es del grupo.
                for i, lado in enumerate(destino["sides"]):
                    if lado["athleteId"] not in papeles:
                        destino["sides"][i] = {**yo, "isWinner": False}
                        break
        # Sin rival, el combate decisivo no llega a jugarse nunca: solo arrancan
        # los que tienen dos. Pasaba de verdad, y dejaba a uno sin su plata y a
        # otro sin su bronce.
        if len(destino["sides"]) < 2:
            rival = next(
                (l for c in datos["matches"] if c["bracketId"] == bracket
                 for l in c["sides"]
                 if l["athleteId"] != atleta_id and l["athleteId"] not in papeles),
                None)
            if rival:
                destino["sides"].append({**rival, "isWinner": False})

        papeles[atleta_id] = {"papel": papel, "bracket": bracket, "decisivo": destino["id"]}
        log(f"  {yo['name']} llegará a «{destino.get('round')}» "
            f"({destino.get('day')} {(destino.get('estimatedStart') or '')[11:16]})")


def decidir_ganador(combate, papeles):
    """Quién gana. Los del grupo siguen su guion; el resto, al azar.

    El guion vale para un único cuadro por atleta: en los demás cae a la
    primera. Si no, uno acababa ganando por accidente otro bracket suyo —basta
    un cuadro de un solo combate para que cuente como final— y se llevaba un oro
    que no tocaba, tapando la plata que se quería enseñar.
    """
    lados = combate["sides"]
    if len(lados) < 2:
        return lados[0] if lados else None

    for i, lado in enumerate(lados):
        guion = papeles.get(lado["athleteId"])
        if guion is None:
            continue
        otro = lados[1 - i]

        if combate["bracketId"] != guion["bracket"]:
            return otro                       # fuera de su cuadro, eliminado
        if combate["id"] != guion["decisivo"]:
            return lado                       # camino hasta el combate decisivo

        # El combate que decide su medalla.
        return otro if guion["papel"] == "pierde_final" else lado

    return random.choice(lados)


def _hueco(combates, ronda):
    for c in combates:
        if (c.get("round") or "").lower() == ronda and len(c["sides"]) < 2:
            return c
    return None


def avanzar_cuadro(datos, combate, ganador):
    """Coloca a ganador y perdedor donde les toca en el cuadro.

    Un bracket funciona así: quien gana la semifinal va a la final y quien la
    pierde va al combate por el bronce. Rellenar el primer hueco libre sin mirar
    la ronda metía a los ganadores en el combate por el bronce y acababa dando
    tres bronces en vez de oro, plata y bronce.
    """
    if not ganador or len(combate["sides"]) < 2:
        return
    perdedor = next(l for l in combate["sides"]
                    if l["athleteId"] != ganador["athleteId"])

    hermanos = [c for c in datos["matches"]
                if c["bracketId"] == combate["bracketId"]
                and c["id"] != combate["id"]
                and c["state"] not in ("finished", "running")]

    def meter(destino, lado):
        if destino and all(l["athleteId"] != lado["athleteId"] for l in destino["sides"]):
            destino["sides"].append({**lado, "isWinner": False})

    if (combate.get("round") or "").lower() == "semifinals":
        meter(_hueco(hermanos, "final"), ganador)
        meter(_hueco(hermanos, "bronze match"), perdedor)
        return

    # Rondas previas: el ganador sigue al siguiente combate que quede por jugar.
    posteriores = sorted(
        (c for c in hermanos
         if (c.get("estimatedStart") or "") > (combate.get("estimatedStart") or "")
         and (c.get("round") or "").lower() != "bronze match"
         and len(c["sides"]) < 2),
        key=lambda c: c.get("estimatedStart") or "")
    meter(posteriores[0] if posteriores else None, ganador)


# Un combate dura unos ocho minutos de reloj real, así que en cada tick cabe
# ese número de combates por tatami. Sin esto la simulación se quedaba corta:
# con un solo combate por tatami y tick no daba tiempo a resolver los 54 que
# tiene cada uno, y los últimos cuadros no llegaban a decidirse.
MINUTOS_POR_COMBATE = 8


def un_tick(datos, reloj, papeles, retraso, velocidad=15):
    """Hace avanzar el torneo hasta `reloj`. Devuelve cuántos cambiaron."""
    cambios = 0
    cupo = max(1, velocidad // MINUTOS_POR_COMBATE)

    # Los que llevan un rato en curso, terminan.
    for c in [x for x in datos["matches"] if x["state"] == "running"]:
        if c.get("_desde", 0) + 1 <= 0:
            continue
        c["state"] = "finished"
        c["wonBy"] = random.choice(RESULTADOS)
        c["timePassed"] = f"0{random.randint(1, 5)}:{random.randint(10, 59)}"
        ganador = decidir_ganador(c, papeles)
        for lado in c["sides"]:
            lado["isWinner"] = ganador is not None and lado["athleteId"] == ganador["athleteId"]
        avanzar_cuadro(datos, c, ganador)
        cambios += 1

    # Arrancan los que tocaban, pero solo uno por tatami: en el pabellón hay
    # seis tatamis y ver cincuenta combates "en curso" no se parecería a nada.
    por_tatami = {}
    for c in datos["matches"]:
        if c["state"] == "running":
            por_tatami[c["matKey"]] = por_tatami.get(c["matKey"], 0) + 1

    pendientes = sorted(
        (c for c in datos["matches"]
         if c["state"] not in ("finished", "running")
         and (c.get("estimatedStart") or "") <= reloj
         and len(c["sides"]) == 2),
        key=lambda c: c.get("estimatedStart") or "")
    for c in pendientes:
        if por_tatami.get(c["matKey"], 0) >= cupo:
            continue
        c["state"] = "running"
        c["_desde"] = 1
        c["timePassed"] = "00:12"
        por_tatami[c["matKey"]] = por_tatami.get(c["matKey"], 0) + 1
        cambios += 1

    # El torneo se retrasa: los pendientes se desplazan. La web tiene que
    # aguantarlo sin descolocarse, que es parte de lo que se quiere ver.
    if retraso:
        for c in datos["matches"]:
            if c["state"] in ("seeded", "unseeded") and c.get("estimatedStart"):
                nueva = datetime.fromisoformat(c["estimatedStart"]) + timedelta(minutes=retraso)
                c["estimatedStart"] = nueva.isoformat()
                c["day"] = c["estimatedStart"][:10]

    return cambios


def recomponer(datos):
    """Recalcula atletas y medallas con el mismo código que usa el scraper."""
    del_grupo = {a.get("id") for a in (datos.get("group") or {}).get("athletes") or []}
    datos["athletes"] = construir_atletas(datos["matches"])
    for atleta in datos["athletes"]:
        atleta["inGroup"] = atleta["id"] in del_grupo
    datos["fetchedAt"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def resumen(datos):
    estados = {}
    for c in datos["matches"]:
        estados[c["state"]] = estados.get(c["state"], 0) + 1
    medallas = [(a["name"], a["bestMedal"])
                for a in datos["athletes"] if a.get("inGroup") and a.get("bestMedal")]
    return estados, medallas


def servir(puerto):
    handler = partial(SimpleHTTPRequestHandler, directory=str(DEMO))
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def main():
    p = argparse.ArgumentParser(description="Simulador del torneo en vivo")
    p.add_argument("--puerto", type=int, default=8766)
    p.add_argument("--velocidad", type=int, default=15,
                   help="minutos de torneo por tick (2s reales)")
    p.add_argument("--tick", type=float, default=2.0, help="segundos reales por tick")
    args = p.parse_args()

    preparar_demo()
    datos = cargar_estado()
    log(f"{len(datos['matches'])} combates reales cargados (copia aislada en tmp-demo/)")

    log("Guion de los del grupo:")
    papeles = guionizar(datos)
    if not papeles:
        log("  (nadie en el grupo; se simula todo al azar)")
    else:
        preparar_desenlace(datos, papeles)

    # Punto de partida: el primer combate del torneo.
    horas = sorted(c["estimatedStart"] for c in datos["matches"] if c.get("estimatedStart"))
    reloj = datetime.fromisoformat(horas[0])
    final = datetime.fromisoformat(horas[-1]) + timedelta(hours=5)

    recomponer(datos)
    escribir_json(DEMO / "data.json", datos)
    servir(args.puerto)

    print()
    log(f"Simulación en http://127.0.0.1:{args.puerto}  <-- ábrela ahora")
    log(f"Del {reloj:%d/%m %H:%M} al {final:%d/%m %H:%M}, "
        f"a {args.velocidad} min por cada {args.tick}s")
    print()

    tick = 0
    while reloj < final:
        tick += 1
        reloj += timedelta(minutes=args.velocidad)
        # Un retraso pequeño y realista, solo de vez en cuando.
        retraso = random.choice([0, 0, 0, 1, 2]) if tick % 3 == 0 else 0
        cambios = un_tick(datos, reloj.isoformat(), papeles, retraso, args.velocidad)

        if cambios:
            recomponer(datos)
            escribir_json(DEMO / "data.json", datos)
            estados, medallas = resumen(datos)
            log(f"{reloj:%a %H:%M} · en curso {estados.get('running', 0)}"
                f" · terminados {estados.get('finished', 0)}"
                f" · pendientes {estados.get('seeded', 0) + estados.get('unseeded', 0)}"
                + (f" · medallas: {medallas}" if medallas else ""))
        time.sleep(args.tick)

    estados, medallas = resumen(datos)
    print()
    log("Fin de la simulación.")
    for nombre, medalla in medallas:
        log(f"  {nombre}: {medalla}")
    log("Recuerda: resultados inventados. La web real no se ha tocado.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nSimulación detenida.")
        sys.exit(0)
