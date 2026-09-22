"""
Origen simulado: imita los tres endpoints de Smoothcomp sirviendo los fixtures.

Sirve para ensayar el scraper sin mandar tráfico a AJP, sin publicar nombres
reales (los fixtures están anonimizados) y, sobre todo, pudiendo provocar a
voluntad situaciones que en los datos reales no se dan.

La más importante es el modo **--simular-vivo**: el evento 1257 está terminado
(todos los combates `finished`) y el 1535 aún no tiene schedule, así que los
estados `seeded` y `running` no se han podido observar nunca. Aquí el torneo
avanza: los combates arrancan `seeded`, pasan a `running` y terminan
`finished`, unos pocos en cada lectura.

Endpoints (los mismos que documenta docs/data-source.md):

    /en/event/<id>/schedule/new/matcategories.json
    /en/event/<id>/schedule/new/mats.json/<dayId>
    /en/event/<id>/schedule/new/mat/<matId>/matches.json

Control en caliente, para que el ensayo pueda tumbar y levantar el origen sin
matar el proceso:

    /control/fallar        -> a partir de ahora responde 503
    /control/funcionar     -> vuelve a responder bien
    /control/congelar      -> el torneo deja de avanzar (nada cambia entre lecturas)
    /control/descongelar   -> vuelve a avanzar
    /control/estado        -> resumen de en qué punto va el torneo

Uso:  python research/mock_origen.py [--puerto 8899] [--evento 1257] [--simular-vivo]
"""
import argparse
import json
import random
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

RUTA_DIAS = re.compile(r"^/en/event/(\d+)/schedule/new/matcategories\.json$")
RUTA_MATS = re.compile(r"^/en/event/(\d+)/schedule/new/mats\.json/(\d+)$")
RUTA_COMBATES = re.compile(r"^/en/event/(\d+)/schedule/new/mat/(\d+)/matches\.json$")

# Cuántos combates avanzan de estado en cada lectura del schedule.
ARRANCAN_POR_LECTURA = 3
TERMINAN_POR_LECTURA = 2

RESULTADOS = ("points", "submission", "decision", "walkover", "disqualification")


class Origen:
    """Los datos del evento y, si procede, su evolución durante el torneo."""

    def __init__(self, event_id, simular_vivo):
        carpeta = RAIZ / "fixtures" / f"event_{event_id}"
        if not carpeta.exists():
            raise SystemExit(f"No existe {carpeta}; captura antes con capture_event.py")

        self.candado = threading.Lock()
        self.fallar = False
        self.congelado = False
        self.lecturas = 0
        self.dias = json.loads((carpeta / "days.json").read_text(encoding="utf-8"))

        self.mats = []
        for d in self.dias:
            self.mats += json.loads(
                (carpeta / f"mats_{d['id']}.json").read_text(encoding="utf-8"))

        self.combates = {}
        for m in self.mats:
            fichero = carpeta / f"matches_{m['id']}.json"
            if fichero.exists():
                self.combates[m["id"]] = json.loads(fichero.read_text(encoding="utf-8"))

        if simular_vivo:
            self._reiniciar_torneo()

    def _reiniciar_torneo(self):
        """Devuelve todos los combates al estado previo al arranque."""
        for lista in self.combates.values():
            for c in lista:
                c["state"] = "seeded"
                c["wonBy"] = None
                c["time_passed"] = None
                for plaza in c.get("seats", []):
                    plaza["isWinner"] = False

    def _todos(self):
        return [c for lista in self.combates.values() for c in lista]

    def avanzar(self):
        """Termina algunos combates en curso y arranca otros. Como un torneo."""
        combates = self._todos()

        for c in [x for x in combates if x["state"] == "running"][:TERMINAN_POR_LECTURA]:
            c["state"] = "finished"
            c["wonBy"] = random.choice(RESULTADOS)
            plazas = [p for p in c.get("seats", []) if p.get("type") == "registration"]
            if plazas:
                random.choice(plazas)["isWinner"] = True

        for c in [x for x in combates if x["state"] == "seeded"][:ARRANCAN_POR_LECTURA]:
            c["state"] = "running"
            c["time_passed"] = "00:42"

    def resumen(self):
        combates = self._todos()
        cuenta = {}
        for c in combates:
            cuenta[c["state"]] = cuenta.get(c["state"], 0) + 1
        return {"lecturas": self.lecturas, "fallando": self.fallar,
                "congelado": self.congelado, "combates": len(combates),
                "estados": cuenta}


def crear_handler(origen, simular_vivo):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # sin ruido: el ensayo ya tiene su propio log

        def _responder(self, codigo, cuerpo, tipo="application/json"):
            datos = (json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
                     if tipo == "application/json" else str(cuerpo).encode("utf-8"))
            self.send_response(codigo)
            self.send_header("Content-Type", f"{tipo}; charset=utf-8")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def do_GET(self):
            ruta = self.path

            if ruta.startswith("/control/"):
                with origen.candado:
                    accion = ruta.rsplit("/", 1)[-1]
                    if accion == "fallar":
                        origen.fallar = True
                    elif accion == "funcionar":
                        origen.fallar = False
                    elif accion == "congelar":
                        origen.congelado = True
                    elif accion == "descongelar":
                        origen.congelado = False
                    return self._responder(200, origen.resumen())

            with origen.candado:
                if origen.fallar:
                    # 503 es reintentable: así se ejercita el backoff de fetch.py
                    # antes de que el scraper se dé por vencido y marque stale.
                    return self._responder(503, {"error": "origen caído (simulado)"})

                if m := RUTA_DIAS.match(ruta):
                    origen.lecturas += 1
                    if simular_vivo and not origen.congelado:
                        origen.avanzar()
                    return self._responder(200, origen.dias)

                if m := RUTA_MATS.match(ruta):
                    dia = int(m.group(2))
                    if not any(d["id"] == dia for d in origen.dias):
                        return self._responder(404, {"error": "día desconocido"})
                    return self._responder(200, origen.mats)

                if m := RUTA_COMBATES.match(ruta):
                    mat = int(m.group(2))
                    if mat not in origen.combates:
                        return self._responder(404, {"error": "tatami desconocido"})
                    return self._responder(200, origen.combates[mat])

            self._responder(404, {"error": "ruta no reconocida"})

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--puerto", type=int, default=8899)
    p.add_argument("--evento", default="1257")
    p.add_argument("--simular-vivo", action="store_true",
                   help="el torneo avanza: seeded -> running -> finished")
    args = p.parse_args()

    origen = Origen(args.evento, args.simular_vivo)
    servidor = HTTPServer(("127.0.0.1", args.puerto),
                          crear_handler(origen, args.simular_vivo))

    print(f"Origen simulado en http://127.0.0.1:{args.puerto} "
          f"(evento {args.evento}, {len(origen.mats)} tatamis, "
          f"{sum(len(v) for v in origen.combates.values())} combates)")
    if args.simular_vivo:
        print("Modo en vivo: cada lectura del schedule avanza el torneo.")
    print("Control: /control/fallar · /control/funcionar · /control/estado")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
