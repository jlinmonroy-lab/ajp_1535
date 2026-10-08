"""
Pruebas del cliente de Smoothcomp contra servidores falsos en 127.0.0.1.

Cubren lo que el servidor multi-evento necesita de `scraper/fetch.py`:

  - distinguir "no publicado" (403 de la aplicación) de "no existe" (404) y de
    "nos bloquean" (reto de Cloudflare);
  - seguir la redirección de smoothcomp.com al subdominio del organizador y
    recordar el host final;
  - que todo el tráfico comparta un único ritmo, aunque lo pidan varios hilos.

Uso:  python -m unittest discover -s tests
"""
import json
import sys
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper import fetch  # noqa: E402
from scraper.fetch import ErrorOrigen, Ritmo  # noqa: E402

DIA = {"id": 10, "name": "Day 1", "date": "2026-10-17T09:00:00+02:00"}
RUTA_BASE = "/en/event/5/schedule/new"


class Falso:
    """Un servidor HTTP de mentira. `tabla` mapea ruta -> (código, cuerpo, cabeceras)
    o una función que recibe el número de petición a esa ruta y devuelve lo mismo."""

    def __init__(self, tabla):
        self.tabla = tabla
        self.peticiones = []
        falso = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                falso.peticiones.append(self.path)
                visto = falso.peticiones.count(self.path)
                respuesta = falso.tabla.get(self.path, (404, "no está", {}))
                if callable(respuesta):
                    respuesta = respuesta(visto)
                codigo, cuerpo, cabeceras = respuesta
                if not isinstance(cuerpo, (str, bytes)):
                    cuerpo = json.dumps(cuerpo)
                datos = cuerpo.encode("utf-8") if isinstance(cuerpo, str) else cuerpo
                self.send_response(codigo)
                for clave, valor in cabeceras.items():
                    self.send_header(clave, valor)
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, args=(0.02,),
                         daemon=True).start()

    def cerrar(self):
        self.servidor.shutdown()
        self.servidor.server_close()


def cfg_para(url):
    return {"baseUrl": url, "lang": "en", "requestPauseSeconds": 0, "timeoutSeconds": 5}


class PruebaConServidor(unittest.TestCase):
    def falso(self, tabla):
        servidor = Falso(tabla)
        self.addCleanup(servidor.cerrar)
        return servidor


class TestLecturaDeUnEvento(PruebaConServidor):
    def test_lee_dias_tatamis_y_combates(self):
        s = self.falso({
            f"{RUTA_BASE}/matcategories.json": (200, DIA, {}),   # un día = objeto
            f"{RUTA_BASE}/mats.json/10": (200, [
                {"id": 1, "name": "Mat 1"},
                {"id": 2, "name": "Oculto", "visible": 0},
            ], {}),
            f"{RUTA_BASE}/mat/1/matches.json": (200, [{"id": 99}], {}),
        })
        lectura = fetch.leer_evento(cfg_para(s.url), 5, log=lambda *_: None)

        self.assertEqual([d["id"] for d in lectura.dias], [10], "un solo día llega como lista")
        self.assertEqual([m["id"] for m in lectura.mats], [1], "el tatami oculto no se lee")
        self.assertEqual(lectura.mats[0]["dayId"], 10)
        self.assertEqual(lectura.mats[0]["dayDate"], DIA["date"])
        self.assertEqual(lectura.combates_por_mat, {1: [{"id": 99}]})
        self.assertEqual(lectura.base_url, s.url)
        self.assertNotIn(f"{RUTA_BASE}/mat/2/matches.json", s.peticiones)

    def test_sigue_la_redireccion_y_recuerda_el_host_final(self):
        # smoothcomp.com redirige al subdominio del organizador.
        destino = self.falso({
            f"{RUTA_BASE}/matcategories.json": (200, [DIA], {}),
            f"{RUTA_BASE}/mats.json/10": (200, [{"id": 1, "name": "Mat 1"}], {}),
            f"{RUTA_BASE}/mat/1/matches.json": (200, [], {}),
        })
        raiz = self.falso({
            f"{RUTA_BASE}/matcategories.json": (
                302, "", {"Location": f"{destino.url}{RUTA_BASE}/matcategories.json"}),
        })
        # Un tatami sin combates ([]) cuenta como leído, así que el ciclo sigue.
        lectura = fetch.leer_evento(cfg_para(raiz.url), 5, log=lambda *_: None)

        self.assertEqual(lectura.base_url, destino.url)
        self.assertEqual(raiz.peticiones, [f"{RUTA_BASE}/matcategories.json"],
                         "el resto de peticiones ya no pasan por la raíz")
        self.assertIn(f"{RUTA_BASE}/mat/1/matches.json", destino.peticiones)

    def test_base_url_explicita_manda_sobre_la_de_la_config(self):
        s = self.falso({
            f"{RUTA_BASE}/matcategories.json": (200, [DIA], {}),
            f"{RUTA_BASE}/mats.json/10": (200, [{"id": 1, "name": "Mat 1"}], {}),
            f"{RUTA_BASE}/mat/1/matches.json": (200, [], {}),
        })
        cfg = cfg_para("http://127.0.0.1:1")  # nadie escucha ahí
        lectura = fetch.leer_evento(cfg, 5, base_url=s.url, log=lambda *_: None)
        self.assertEqual(lectura.base_url, s.url)

    def test_un_tatami_que_falla_no_tumba_el_ciclo(self):
        s = self.falso({
            f"{RUTA_BASE}/matcategories.json": (200, [DIA], {}),
            f"{RUTA_BASE}/mats.json/10": (200, [
                {"id": 1, "name": "Mat 1"}, {"id": 2, "name": "Mat 2"}], {}),
            f"{RUTA_BASE}/mat/1/matches.json": (200, [{"id": 1}], {}),
            f"{RUTA_BASE}/mat/2/matches.json": (403, "{}", {}),
        })
        avisos = []
        lectura = fetch.leer_evento(cfg_para(s.url), 5, log=avisos.append)
        self.assertEqual(list(lectura.combates_por_mat), [1])
        self.assertEqual(len(avisos), 1, "queda constancia del tatami que falló")

    def test_si_ningun_tatami_responde_es_un_fallo(self):
        s = self.falso({
            f"{RUTA_BASE}/matcategories.json": (200, [DIA], {}),
            f"{RUTA_BASE}/mats.json/10": (200, [{"id": 1, "name": "Mat 1"}], {}),
        })
        with self.assertRaises(ErrorOrigen):
            fetch.leer_evento(cfg_para(s.url), 5, log=lambda *_: None)


class TestCodigosDeError(PruebaConServidor):
    def leer(self, servidor):
        return fetch.leer_evento(cfg_para(servidor.url), 5, log=lambda *_: None)

    def test_403_de_la_aplicacion_es_schedule_no_publicado(self):
        s = self.falso({f"{RUTA_BASE}/matcategories.json": (
            403, "<title>403 - not allowed</title>", {"Content-Type": "application/json"})})
        with self.assertRaises(ErrorOrigen) as ctx:
            self.leer(s)
        self.assertEqual(ctx.exception.codigo, 403)
        self.assertFalse(ctx.exception.desafio, "no es anti-bot, es 'no publicado'")
        self.assertEqual(len(s.peticiones), 1, "un 403 no se reintenta")

    def test_404_es_evento_inexistente(self):
        s = self.falso({})
        with self.assertRaises(ErrorOrigen) as ctx:
            self.leer(s)
        self.assertEqual(ctx.exception.codigo, 404)

    def test_el_reto_de_cloudflare_se_distingue_del_403_normal(self):
        s = self.falso({f"{RUTA_BASE}/matcategories.json": (
            403, "<title>Just a moment...</title>", {"Cf-Mitigated": "challenge"})})
        with self.assertRaises(ErrorOrigen) as ctx:
            self.leer(s)
        self.assertEqual(ctx.exception.codigo, 403)
        self.assertTrue(ctx.exception.desafio)

    def test_un_503_se_reintenta_y_un_404_no(self):
        s = self.falso({
            "/ok": lambda visto: (503, "", {}) if visto == 1 else (200, {"va": "bien"}, {}),
            "/caido": (503, "", {}),
        })
        datos, _ = fetch._get(f"{s.url}/ok", 5, espera_base=0.01)
        self.assertEqual(datos, {"va": "bien"})
        self.assertEqual(s.peticiones.count("/ok"), 2)

        with self.assertRaises(ErrorOrigen) as ctx:
            fetch._get(f"{s.url}/caido", 5, intentos=2, espera_base=0.01)
        self.assertEqual(ctx.exception.codigo, 503)
        self.assertEqual(s.peticiones.count("/caido"), 2)

    def test_una_respuesta_que_no_es_json_es_un_fallo(self):
        s = self.falso({"/raro": (200, "<html>Just a moment...</html>", {})})
        with self.assertRaises(ErrorOrigen) as ctx:
            fetch._get(f"{s.url}/raro", 5)
        self.assertTrue(ctx.exception.desafio)


class TestPedirHtml(PruebaConServidor):
    def test_devuelve_el_texto_y_la_url_final(self):
        s = self.falso({"/es/events/upcoming?search=madrid": (200, "<html>hola</html>", {})})
        texto, final = fetch.pedir_html(f"{s.url}/es/events/upcoming?search=madrid")
        self.assertIn("hola", texto)
        self.assertEqual(final, f"{s.url}/es/events/upcoming?search=madrid")


class TestRitmo(unittest.TestCase):
    def test_los_turnos_no_se_solapan_y_respetan_la_pausa(self):
        ritmo = Ritmo(pausa=0.15)
        marcas = []
        candado = threading.Lock()

        def peticion():
            with ritmo.turno():
                inicio = time.monotonic()
                time.sleep(0.05)  # lo que tarda la petición
                fin = time.monotonic()
            with candado:
                marcas.append((inicio, fin))

        hilos = [threading.Thread(target=peticion) for _ in range(4)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        marcas.sort()
        for (_, fin), (inicio, _) in zip(marcas, marcas[1:]):
            self.assertGreaterEqual(inicio - fin, 0.15 - 0.02,
                                    "entre una petición y la siguiente debe haber pausa")

    def test_configurar_ritmo_no_admite_pausas_negativas(self):
        anterior = fetch.RITMO.pausa
        self.addCleanup(setattr, fetch.RITMO, "pausa", anterior)
        fetch.configurar_ritmo(-5)
        self.assertEqual(fetch.RITMO.pausa, 0.0)


if __name__ == "__main__":
    unittest.main()
