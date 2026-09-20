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
from scraper.publish import escribir_json, publicar_git  # noqa: E402

CONFIG = RAIZ / "config.json"


def ahora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(mensaje):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {mensaje}", flush=True)


def cargar_config(args):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if args.event and args.event != cfg.get("eventId"):
        # Al apuntar a otro evento, el nombre configurado ya no vale: mejor sin
        # nombre que con el del evento equivocado.
        cfg["eventId"] = args.event
        cfg["eventName"] = None
    return cfg


def un_ciclo(cfg, estado_previo):
    """Lee, convierte y publica. Devuelve el estado nuevo, o None si falló."""
    dias, mats, combates = leer_schedule(cfg, log=log)

    estado = construir_estado(
        evento={"id": cfg["eventId"], "name": cfg.get("eventName")},
        dias=dias, mats=mats, combates_por_mat=combates,
        fetched_at=ahora_iso(),
        streams=cfg.get("streams") or [],
    )
    en_curso = sum(1 for m in estado["matches"] if m["state"] == "running")
    log(f"  {len(estado['matches'])} combates, {len(estado['athletes'])} atletas, "
        f"{len(estado['mats'])} tatamis, {en_curso} en curso")
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
    args = p.parse_args()

    cfg = cargar_config(args)
    destino = RAIZ / cfg.get("output", "site/data.json")
    intervalo = cfg.get("refreshSeconds", 75)
    limite_fallos = cfg.get("staleAfterFailures", 3)

    log(f"Evento {cfg['eventId']} · refresco {intervalo}s · salida {destino}")

    ultimo_bueno = None
    fallos = 0
    primer_fallo = None

    while True:
        inicio = time.time()
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
            publicar_git(cfg, destino.parent, log=log)

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
