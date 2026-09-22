"""
Bucle del scraper: lee el schedule cada N segundos, lo convierte y lo publica.

Uso:
    python -m scraper.main                 # bucle continuo con config.json
    python -m scraper.main --once          # un solo ciclo (para probar)
    python -m scraper.main --event 1257    # sobreescribe el evento configurado
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.fetch import ErrorOrigen, leer_schedule  # noqa: E402
from scraper.parse import construir_estado  # noqa: E402
from scraper.publish import escribir_json, publicar  # noqa: E402

CONFIG = RAIZ / "config.json"


def ahora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(mensaje):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {mensaje}", flush=True)


def cargar_config(args, anterior=None):
    """Lee la configuración. Si no se puede, sigue con la que ya había.

    Se relee en cada ciclo para poder ajustar cosas durante el evento —el
    intervalo, los enlaces de los streams— sin parar el scraper. Como el fichero
    puede leerse justo mientras alguien lo guarda, un JSON a medias no debe
    tumbar el bucle: se avisa y se sigue con el anterior.
    """
    ruta = Path(args.config) if args.config else CONFIG
    try:
        cfg = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        if anterior is None:
            raise
        log(f"  no se pudo releer {ruta.name} ({type(e).__name__}); sigo con la anterior")
        return anterior

    if args.event:
        # Al apuntar a un evento suelto, los nombres configurados ya no valen.
        cfg["events"] = [{"id": args.event, "label": None, "name": None}]
    return cfg


def un_ciclo(cfg, estado_previo):
    """Lee todos los eventos, los combina y devuelve el estado nuevo.

    Un evento que falle no invalida el ciclo: el día del torneo es normal que
    uno esté publicado y el otro todavía no. Solo se da el ciclo por fallido si
    no se pudo leer ninguno.
    """
    eventos = cfg.get("events") or []
    if not eventos:
        raise ErrorOrigen("no hay eventos configurados")

    datos = {}
    fallos = []
    for evento in eventos:
        event_id = str(evento["id"])
        etiqueta = evento.get("label") or event_id
        try:
            datos[event_id] = leer_schedule(cfg, event_id, log=log)
        except ErrorOrigen as e:
            fallos.append(f"{etiqueta}: {e}")
            log(f"  evento {etiqueta} no disponible ({e})")

    if not datos:
        raise ErrorOrigen("; ".join(fallos) or "ningún evento devolvió datos")

    estado = construir_estado(
        eventos=eventos, datos_por_evento=datos, fetched_at=ahora_iso(),
        streams=cfg.get("streams") or [],
    )
    en_curso = sum(1 for m in estado["matches"] if m["state"] == "running")
    por_evento = ", ".join(
        f"{e.get('label') or e['id']}: "
        f"{sum(1 for m in estado['matches'] if m['eventId'] == str(e['id']))}"
        for e in eventos)
    log(f"  {len(estado['matches'])} combates ({por_evento}), "
        f"{len(estado['athletes'])} atletas, {len(estado['mats'])} tatamis, "
        f"{en_curso} en curso")
    return estado


def marcar_stale(estado, desde):
    """Reutiliza el último estado bueno, avisando de que ya no está fresco."""
    copia = dict(estado)
    copia["stale"] = True
    copia["staleSince"] = desde
    return copia


def main():
    p = argparse.ArgumentParser(description="Scraper del schedule de AJP Tour")
    p.add_argument("--once", action="store_true", help="un solo ciclo y salir")
    p.add_argument("--event", help="id de evento, sobreescribe config.json")
    p.add_argument("--config", help="ruta de configuración alternativa")
    args = p.parse_args()

    cfg = cargar_config(args)
    destino = RAIZ / cfg.get("output", "site/data.json")

    nombres = ", ".join(f"{e.get('label') or e['id']} ({e['id']})"
                        for e in cfg.get("events", []))
    log(f"Eventos: {nombres} · refresco {cfg.get('refreshSeconds', 75)}s "
        f"· salida {destino}")

    ultimo_bueno = None
    fallos = 0
    primer_fallo = None

    while True:
        inicio = time.time()
        # Releer antes de cada ciclo: permite ajustar el ritmo o añadir streams
        # con el scraper en marcha.
        cfg = cargar_config(args, anterior=cfg)
        destino = RAIZ / cfg.get("output", "site/data.json")
        intervalo = cfg.get("refreshSeconds", 75)
        limite_fallos = cfg.get("staleAfterFailures", 3)

        try:
            estado = un_ciclo(cfg, ultimo_bueno)
            ultimo_bueno, fallos, primer_fallo = estado, 0, None
        except ErrorOrigen as e:
            fallos += 1
            primer_fallo = primer_fallo or ahora_iso()
            log(f"  fallo {fallos}/{limite_fallos}: {e}")

            if ultimo_bueno is None:
                log("  aún no hay ningún estado bueno que publicar")
                estado = None
            elif fallos >= limite_fallos:
                # Se conserva el último estado bueno, pero marcado: mejor que la
                # web avise de que los datos están viejos a que mienta.
                estado = marcar_stale(ultimo_bueno, primer_fallo)
                log(f"  marcado stale desde {primer_fallo}")
            else:
                estado = ultimo_bueno

        if estado is not None:
            tam = escribir_json(destino, estado)
            log(f"  escrito {destino.name} ({tam / 1024:.0f} KB)")
            publicar(cfg, destino, log=log)

        if args.once:
            return 0

        espera = max(5.0, intervalo - (time.time() - inicio))
        time.sleep(espera)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nDetenido.")
        sys.exit(0)
