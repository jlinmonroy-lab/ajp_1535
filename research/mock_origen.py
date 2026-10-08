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

Para el servidor multi-evento (scraper/servidor.py) sirve además lo que usa el
buscador, con los eventos servidos más los de --sin-schedule en el catálogo:

    /en/events/upcoming?search=&page=     (y /past) -> HTML con `var events = [...]`
    /en/event/<id>/getCmsData             -> el título del evento

Un evento de --sin-schedule existe pero responde 403 (schedule sin publicar), como
el 33588 de verdad. Con --estricto, un id que no existe responde 404, que es lo
que hace Smoothcomp; sin él se mantiene el 403 de siempre, del que depende
research/rehearsal.py. Con --relleno N hay N eventos pasados más, para probar
la paginación.

Control en caliente, para que el ensayo pueda tumbar y levantar el origen sin
matar el proceso:

    /control/fallar        -> a partir de ahora responde 503
    /control/funcionar     -> vuelve a responder bien
    /control/congelar      -> el torneo deja de avanzar (nada cambia entre lecturas)
    /control/descongelar   -> vuelve a avanzar
    /control/estado        -> resumen de en qué punto va el torneo

Uso:  python research/mock_origen.py [--eventos 1535,1526] [--simular-vivo]
              [--sin-schedule 33588] [--estricto] [--relleno 55]
"""
import argparse
import json
import random
import re
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

RUTA_DIAS = re.compile(r"^/en/event/(\d+)/schedule/new/matcategories\.json$")
RUTA_MATS = re.compile(r"^/en/event/(\d+)/schedule/new/mats\.json/(\d+)$")
RUTA_COMBATES = re.compile(r"^/en/event/(\d+)/schedule/new/mat/(\d+)/matches\.json$")
RUTA_LISTA = re.compile(r"^/(?:en|es)/events/(upcoming|past)$")
RUTA_CMS = re.compile(r"^/(?:en|es)/event/(\d+)/getCmsData$")
POR_PAGINA_PASADOS = 40   # como Smoothcomp

# Cuántos combates avanzan de estado en cada lectura del schedule.
ARRANCAN_POR_LECTURA = 3
TERMINAN_POR_LECTURA = 2

RESULTADOS = ("points", "submission", "decision", "walkover", "disqualification")


class Evento:
    """Un evento servido por el mock, con su propia copia de los datos."""

    def __init__(self, event_id, fixture, indice, simular_vivo):
        carpeta = RAIZ / "fixtures" / f"event_{fixture}"
        if not carpeta.exists():
            raise SystemExit(f"No existe {carpeta}; captura antes con capture_event.py")

        self.id = str(event_id)
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

        if indice:
            self._separar_del_primero(indice)
        if simular_vivo:
            self._reiniciar_torneo()

    def _separar_del_primero(self, indice):
        """Hace que el segundo evento se parezca a lo que pasará de verdad.

        Los mismos atletas compiten en Gi y en No-Gi, pero con inscripciones
        distintas: se desplazan los `event_registration_id` conservando nombre y
        club, que es justo lo que pone a prueba la unificación. Los tatamis se
        renombran para comprobar que no se mezclan los de un evento con otro.
        """
        desplazamiento = 500000 * indice
        for i, m in enumerate(self.mats):
            m["id"] += desplazamiento
            m["name"] = f"Mat {chr(ord('A') + i)}"
        self.combates = {
            mat["id"]: lista
            for mat, lista in zip(self.mats, list(self.combates.values()))
        }
        for lista in self.combates.values():
            for c in lista:
                c["id"] += desplazamiento
                c["bracket_id"] += desplazamiento
                for plaza in c.get("seats", []):
                    if plaza.get("event_registration_id") is not None:
                        plaza["event_registration_id"] += desplazamiento

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
        cuenta = {}
        for c in self._todos():
            cuenta[c["state"]] = cuenta.get(c["state"], 0) + 1
        return {"id": self.id, "tatamis": len(self.mats),
                "combates": len(self._todos()), "estados": cuenta}


class Origen:
    """Todos los eventos servidos, más el control de fallos y congelación."""

    def __init__(self, ids, fixture, simular_vivo, sin_schedule=(), estricto=False,
                 relleno=0, puerto=8899):
        self.candado = threading.Lock()
        self.fallar = False
        self.congelado = False
        self.lecturas = 0
        self.estricto = estricto
        self.eventos = {str(e): Evento(e, fixture, i, simular_vivo)
                        for i, e in enumerate(ids)}
        self.sin_schedule = [str(e) for e in sin_schedule]
        self.catalogo = self._catalogo(puerto, relleno)

    def existe(self, event_id):
        return event_id in self.eventos or event_id in self.sin_schedule

    def _catalogo(self, puerto, relleno):
        """Los eventos que el buscador conoce: los próximos y los pasados.

        Los servidos están en Arganda del Rey (Madrid). Además hay unos "ajenos"
        fijos para probar el filtro de zona: uno en Alcalá de Henares que no dice
        Madrid en el título (solo el radio lo encuentra), otros en Barcelona y
        Lisboa, y un "Madrid Open" de Texas, que dice Madrid pero no es de España.
        """
        def evento(event_id, titulo, fecha, pasado=False, ciudad="Arganda del Rey",
                   pais="ES", lat="40.3012", lon="-3.4402"):
            return {"id": int(event_id), "title": titulo,
                    "url": f"http://127.0.0.1:{puerto}/en/event/{event_id}",
                    "startdate": fecha, "enddate": fecha,
                    "location_city": ciudad, "location_country": pais,
                    "location_lat": lat, "location_long": lon,
                    "eventEnded": pasado, "cover_image": None}

        proximos = [evento(e, f"Evento simulado {e}", "2026-10-17")
                    for e in [*self.eventos, *self.sin_schedule]]
        proximos += [
            evento(800001, "Open Alcala simulado", "2026-10-25",
                   ciudad="Alcala de Henares", lat="40.4818", lon="-3.3635"),
            evento(800002, "Evento simulado Barcelona", "2026-11-07",
                   ciudad="Barcelona", lat="41.3874", lon="2.1686"),
            evento(800003, "Evento simulado Lisboa", "2026-11-14",
                   ciudad="Lisboa", pais="PT", lat="38.7223", lon="-9.1393"),
            evento(800004, "Madrid Open (Texas)", "2026-12-05",
                   ciudad="Madrid, TX", pais="US", lat="31.0", lon="-100.0"),
        ]
        # Dos de cada tres, de Madrid y con "Madrid" en el título; el resto, de Barcelona.
        pasados = [
            evento(900000 + i, f"Evento pasado {i + 1}", "2025-05-10", True,
                   ciudad="Barcelona", lat="41.3874", lon="2.1686")
            if i % 3 == 0 else
            evento(900000 + i, f"Madrid Cup pasado {i + 1}", "2025-05-10", True,
                   ciudad="Madrid", lat="40.4168", lon="-3.7038")
            for i in range(relleno)]
        return {"upcoming": proximos, "past": pasados}

    def lista(self, cuando, consulta):
        """La página de Smoothcomp con `var events = [...]`, filtrada y paginada.

        Como el Smoothcomp de verdad, `search` es una frase sobre el título (no mira
        la ciudad) y `countries` filtra por país en el servidor.
        """
        params = urllib.parse.parse_qs(consulta)
        buscado = (params.get("search") or [""])[0].lower()
        pais = (params.get("countries") or [""])[0].upper()
        pagina = int((params.get("page") or ["1"])[0])
        eventos = [e for e in self.catalogo[cuando]
                   if buscado in e["title"].lower()
                   and (not pais or e["location_country"] == pais)]
        if cuando == "past":    # 40 por página; `upcoming` viene entero
            inicio = (pagina - 1) * POR_PAGINA_PASADOS
            eventos = eventos[inicio:inicio + POR_PAGINA_PASADOS]
        return ("<html><head><script>\n  var events = "
                f"{json.dumps(eventos, ensure_ascii=False)};\n  </script></head><body></body></html>")

    def resumen(self):
        return {"lecturas": self.lecturas, "fallando": self.fallar,
                "congelado": self.congelado,
                "eventos": [e.resumen() for e in self.eventos.values()]}


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
            ruta, _, consulta = self.path.partition("?")

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

                if m := RUTA_LISTA.match(ruta):
                    return self._responder(200, origen.lista(m.group(1), consulta), "text/html")

                if m := RUTA_CMS.match(ruta):
                    if origen.estricto and not origen.existe(m.group(1)):
                        return self._responder(404, "404 - not found", "text/html")
                    return self._responder(
                        200, {"eventData": {"title": f"Evento simulado {m.group(1)}"}})

                if m := RUTA_DIAS.match(ruta):
                    evento = origen.eventos.get(m.group(1))
                    if evento is None:
                        if origen.estricto and not origen.existe(m.group(1)):
                            return self._responder(404, "404 - not found", "text/html")
                        # Igual que AJP con un evento sin schedule publicado.
                        return self._responder(403, {"error": "not allowed"})
                    origen.lecturas += 1
                    if simular_vivo and not origen.congelado:
                        evento.avanzar()
                    return self._responder(200, evento.dias)

                if m := RUTA_MATS.match(ruta):
                    evento = origen.eventos.get(m.group(1))
                    if evento is None:
                        return self._responder(403, {"error": "not allowed"})
                    if not any(d["id"] == int(m.group(2)) for d in evento.dias):
                        return self._responder(404, {"error": "día desconocido"})
                    return self._responder(200, evento.mats)

                if m := RUTA_COMBATES.match(ruta):
                    evento = origen.eventos.get(m.group(1))
                    if evento is None:
                        return self._responder(403, {"error": "not allowed"})
                    mat = int(m.group(2))
                    if mat not in evento.combates:
                        return self._responder(404, {"error": "tatami desconocido"})
                    return self._responder(200, evento.combates[mat])

            self._responder(404, {"error": "ruta no reconocida"})

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--puerto", type=int, default=8899)
    p.add_argument("--eventos", default="1257",
                   help="ids a servir, separados por comas (p.ej. 1535,1526)")
    p.add_argument("--fixture", default="1257",
                   help="carpeta de fixtures de la que salen los datos")
    p.add_argument("--simular-vivo", action="store_true",
                   help="el torneo avanza: seeded -> running -> finished")
    p.add_argument("--sin-schedule", default="",
                   help="ids que existen en el buscador pero aún no han publicado (403)")
    p.add_argument("--estricto", action="store_true",
                   help="un id que no existe responde 404, como Smoothcomp")
    p.add_argument("--relleno", type=int, default=0,
                   help="eventos pasados de relleno, para probar la paginación")
    args = p.parse_args()

    ids = [e.strip() for e in args.eventos.split(",") if e.strip()]
    sin = [e.strip() for e in args.sin_schedule.split(",") if e.strip()]
    origen = Origen(ids, args.fixture, args.simular_vivo, sin_schedule=sin,
                    estricto=args.estricto, relleno=args.relleno, puerto=args.puerto)
    servidor = HTTPServer(("127.0.0.1", args.puerto),
                          crear_handler(origen, args.simular_vivo))

    print(f"Origen simulado en http://127.0.0.1:{args.puerto}")
    for e in origen.eventos.values():
        print(f"  evento {e.id}: {len(e.mats)} tatamis, "
              f"{sum(len(v) for v in e.combates.values())} combates")
    for e in origen.sin_schedule:
        print(f"  evento {e}: sin schedule publicado (403)")
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
