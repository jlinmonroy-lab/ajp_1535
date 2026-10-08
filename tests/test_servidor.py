"""
Pruebas del servidor HTTP: rutas, estados, ETag/gzip y, sobre todo, quién puede
cambiar la lista del grupo.

Se levanta un servidor de verdad en un puerto libre de 127.0.0.1 con un buscador
y un lector de Smoothcomp falsos; las lecturas encoladas las procesa el test.

Uso:  python -m unittest discover -s tests
"""
import gzip
import http.client
import json
import sys
import tempfile
import threading
import unittest
from collections import namedtuple
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.almacen import Almacen  # noqa: E402
from scraper.fetch import ErrorOrigen, Lectura  # noqa: E402
from scraper.grupos import Grupos  # noqa: E402
from scraper.servidor import crear_servidor, es_panel_local  # noqa: E402

CFG = {"baseUrl": "https://smoothcomp.com", "lang": "en", "refreshSeconds": 75,
       "staleAfterFailures": 3,
       "servidor": {"inactividadMinutos": 30, "maxEventosEnCache": 20, "workers": 0}}
DIA = {"id": 10, "name": "Day 1", "date": "2026-10-17T09:00:00+02:00"}
MAT = {"id": 1, "name": "Mat 1", "dayId": 10, "dayName": "Day 1", "dayDate": DIA["date"]}
Resp = namedtuple("Resp", "status headers cuerpo")


def combate(mid=1):
    return {
        "id": mid, "bracket_id": 7, "name": "Final", "round": 1,
        "group": "Men's GI / Black / Adults / 77KG", "state": "seeded", "match_nr": 1,
        "wonBy": None, "estimated_start": "2026-10-17T10:00:00+02:00",
        "seats": [
            {"type": "registration", "event_registration_id": 11, "name": "Ana Pérez",
             "club": "Gracie Madrid", "isWinner": False},
            {"type": "registration", "event_registration_id": 12, "name": "Otro",
             "club": "Club B", "isWinner": False},
        ],
    }


class BuscadorFalso:
    def __init__(self):
        self.consultas = []
        self.respuesta = {"events": [{"id": "33588", "title": "MADRID BJJ CUP"}],
                          "page": 1, "hasMore": False, "stale": False}

    def buscar(self, q, cuando, pagina, zona=False):
        self.consultas.append((q, cuando, pagina, zona))
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta

    def conocido(self, event_id):
        return {"id": event_id, "title": "MADRID BJJ CUP"} if event_id == "33588" else None

    def evento(self, event_id):
        if event_id == "999":
            raise ErrorOrigen("HTTP 404", codigo=404)
        return {"id": event_id, "title": f"Evento {event_id}",
                "baseUrl": "https://org.smoothcomp.com"}


class Entorno(unittest.TestCase):
    CFG_EXTRA = {}     # claves que una clase de pruebas añade a la config del servidor

    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        sitio = Path(carpeta.name) / "site"
        sitio.mkdir()
        (sitio / "index.html").write_text("<h1>hola web</h1>", encoding="utf-8")
        (sitio / "app.js").write_text("console.log(1)", encoding="utf-8")
        (Path(carpeta.name) / "secreto.txt").write_text("no debe salir", encoding="utf-8")

        self.grupos = Grupos(Path(carpeta.name) / "data" / "grupos.json")
        self.buscador = BuscadorFalso()
        self.respuestas_lector = {"33588": Lectura([DIA], [MAT], {1: [combate()]},
                                                   "https://org.smoothcomp.com")}
        self.almacen = Almacen(
            CFG, self.buscador, self.grupos,
            leer=lambda cfg, event_id, base_url=None, log=print: self._leer(event_id),
            log=lambda *_: None, workers=0)
        self.servidor = crear_servidor(
            {**CFG, "branding": {"teamName": "Mi Club"}, **self.CFG_EXTRA}, "127.0.0.1", 0,
            self.buscador,
            self.almacen, self.grupos, sitio)
        self.puerto = self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, args=(0.02,), daemon=True).start()
        self.addCleanup(self._cerrar)

    def _cerrar(self):
        self.servidor.shutdown()
        self.servidor.server_close()

    def _leer(self, event_id):
        respuesta = self.respuestas_lector[event_id]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        cabeceras = dict(cabeceras or {})
        if cuerpo is not None and not isinstance(cuerpo, (bytes, str)):
            cuerpo = json.dumps(cuerpo)
            cabeceras.setdefault("Content-Type", "application/json")
        con = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=10)
        try:
            con.request(metodo, ruta, body=cuerpo, headers=cabeceras)
            r = con.getresponse()
            return Resp(r.status, {k.lower(): v for k, v in r.getheaders()}, r.read())
        finally:
            con.close()

    def json(self, resp):
        return json.loads(resp.cuerpo)

    def cargar(self, ids="33588"):
        """Pide el evento, deja que se lea y vuelve a pedirlo."""
        self.pedir("GET", f"/api/events/{ids}/data")
        self.almacen.procesar_pendientes()
        return self.pedir("GET", f"/api/events/{ids}/data")


class TestConfigYEstaticos(Entorno):
    def test_config_mezcla_el_branding_con_los_valores_por_defecto(self):
        r = self.pedir("GET", "/api/config")
        self.assertEqual(r.status, 200)
        self.assertEqual(self.json(r), {"teamName": "Mi Club", "logo": "img/logo.png",
                                        "zona": None})

    def test_sirve_la_web(self):
        r = self.pedir("GET", "/")
        self.assertEqual((r.status, r.cuerpo), (200, b"<h1>hola web</h1>"))
        self.assertEqual(r.headers["cache-control"], "no-cache")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertEqual(self.pedir("GET", "/app.js").status, 200)

    def test_no_sale_nada_de_fuera_de_site(self):
        for ruta in ("/../secreto.txt", "/%2e%2e/secreto.txt", "/..%2fsecreto.txt",
                     "/data/grupos.json"):
            r = self.pedir("GET", ruta)
            self.assertNotEqual(r.cuerpo, b"no debe salir", ruta)
            self.assertEqual(r.status, 404, ruta)

    def test_ruta_de_api_desconocida(self):
        r = self.pedir("GET", "/api/nada")
        self.assertEqual(r.status, 404)
        self.assertIn("error", self.json(r))

    def test_no_se_abre_a_otras_webs_por_cors_ni_contesta_preflight(self):
        r = self.pedir("GET", "/api/config", cabeceras={"Origin": "https://malo.example"})
        self.assertNotIn("access-control-allow-origin", r.headers)
        self.assertEqual(self.pedir("OPTIONS", "/api/events/33588/grupo").status, 501)


class TestBusqueda(Entorno):
    def test_pasa_los_parametros_al_buscador(self):
        r = self.pedir("GET", "/api/events/search?q=madrid%20cup&when=past&page=2")
        self.assertEqual(r.status, 200)
        self.assertEqual(self.buscador.consultas, [("madrid cup", "past", "2", False)])
        self.assertEqual(self.json(r)["events"][0]["id"], "33588")

    def test_valores_por_defecto(self):
        self.pedir("GET", "/api/events/search")
        self.assertEqual(self.buscador.consultas, [("", "upcoming", "1", False)])

    def test_parametros_invalidos_son_un_400(self):
        self.buscador.respuesta = ValueError("'when' debe ser uno de upcoming, past, all")
        r = self.pedir("GET", "/api/events/search?when=ma%C3%B1ana")
        self.assertEqual(r.status, 400)
        self.assertIn("upcoming", self.json(r)["error"])

    def test_si_smoothcomp_falla_es_un_502(self):
        self.buscador.respuesta = ErrorOrigen("HTTP 502 tras 3 intentos", codigo=502)
        r = self.pedir("GET", "/api/events/search?q=x")
        self.assertEqual(r.status, 502)
        self.assertIn("502", self.json(r)["error"])

    def test_si_cloudflare_bloquea_se_sugiere_abrir_por_numero(self):
        self.buscador.respuesta = ErrorOrigen("HTTP 403", codigo=403, desafio=True)
        r = self.pedir("GET", "/api/events/search?q=x")
        self.assertEqual(r.status, 502)
        self.assertIn("número o su enlace", self.json(r)["error"])


class TestZona(Entorno):
    CFG_EXTRA = {"zona": {"nombre": "Madrid, España", "pais": "ES", "texto": "madrid",
                          "centro": [40.4168, -3.7038], "radioKm": 50}}

    def test_la_config_de_la_web_solo_dice_como_se_llama_la_zona(self):
        zona = self.json(self.pedir("GET", "/api/config"))["zona"]
        self.assertEqual(zona, {"nombre": "Madrid, España"})   # ni centro ni radio

    def test_zona_uno_llega_al_buscador(self):
        for valor in ("1", "true"):
            self.pedir("GET", f"/api/events/search?q=x&zona={valor}")
        self.assertEqual([c[3] for c in self.buscador.consultas], [True, True])

    def test_sin_zona_o_con_otro_valor_no_hay_zona(self):
        for ruta in ("/api/events/search", "/api/events/search?zona=0",
                     "/api/events/search?zona=", "/api/events/search?zona=si"):
            self.pedir("GET", ruta)
        self.assertEqual([c[3] for c in self.buscador.consultas], [False] * 4)

    def test_pedir_la_zona_sin_tenerla_es_un_400(self):
        self.buscador.respuesta = ValueError("no hay ninguna zona configurada")
        r = self.pedir("GET", "/api/events/search?zona=1")
        self.assertEqual(r.status, 400)
        self.assertIn("zona", self.json(r)["error"])


class TestDatos(Entorno):
    def test_primero_cargando_despues_el_estado(self):
        r = self.pedir("GET", "/api/events/33588/data")
        self.assertEqual(r.status, 202)
        cuerpo = self.json(r)
        self.assertEqual(cuerpo["status"], "loading")
        self.assertEqual(cuerpo["events"][0]["title"], "MADRID BJJ CUP")
        self.assertEqual(r.headers["retry-after"], "3")

        self.almacen.procesar_pendientes()
        r = self.pedir("GET", "/api/events/33588/data")
        self.assertEqual(r.status, 200)
        estado = self.json(r)
        self.assertEqual(len(estado["matches"]), 1)
        self.assertTrue(estado["events"][0]["published"])
        self.assertEqual(r.headers["content-type"], "application/json; charset=utf-8")

    def test_gzip_solo_si_el_cliente_lo_acepta(self):
        self.cargar()
        con_gzip = self.pedir("GET", "/api/events/33588/data",
                              cabeceras={"Accept-Encoding": "gzip, deflate"})
        self.assertEqual(con_gzip.headers["content-encoding"], "gzip")
        self.assertEqual(con_gzip.headers["vary"], "Accept-Encoding")
        sin = self.pedir("GET", "/api/events/33588/data")
        self.assertNotIn("content-encoding", sin.headers)
        self.assertEqual(gzip.decompress(con_gzip.cuerpo), sin.cuerpo)
        self.assertLess(len(con_gzip.cuerpo), len(sin.cuerpo))

    def test_etag_y_304(self):
        self.cargar()
        r = self.pedir("GET", "/api/events/33588/data")
        etag = r.headers["etag"]
        self.assertTrue(etag.startswith('W/"'))

        r304 = self.pedir("GET", "/api/events/33588/data", cabeceras={"If-None-Match": etag})
        self.assertEqual(r304.status, 304)
        self.assertEqual(r304.cuerpo, b"")
        self.assertEqual(r304.headers["etag"], etag)

        # Un ETag distinto, o varios entre los que está el bueno.
        self.assertEqual(self.pedir("GET", "/api/events/33588/data",
                                    cabeceras={"If-None-Match": 'W/"otro"'}).status, 200)
        self.assertEqual(self.pedir("GET", "/api/events/33588/data",
                                    cabeceras={"If-None-Match": f'W/"x", {etag}'}).status, 304)

    def test_evento_inexistente_es_404(self):
        self.respuestas_lector["999"] = ErrorOrigen("HTTP 404", codigo=404)
        r = self.cargar("999")
        self.assertEqual(r.status, 404)
        self.assertIn("no existe", self.json(r)["error"])

    def test_no_publicado_es_200_sin_combates(self):
        self.respuestas_lector["33588"] = ErrorOrigen("HTTP 403", codigo=403)
        r = self.cargar()
        self.assertEqual(r.status, 200)
        estado = self.json(r)
        self.assertEqual(estado["matches"], [])
        self.assertFalse(estado["events"][0]["published"])

    def test_origen_caido_sin_copia_es_502(self):
        self.respuestas_lector["33588"] = ErrorOrigen("HTTP 503", codigo=503)
        self.assertEqual(self.cargar().status, 502)

    def test_ids_invalidos_son_400(self):
        for malo in ("abc", "1,2,3,4", "1;2", "..", "99999999999"):
            r = self.pedir("GET", f"/api/events/{malo}/data")
            self.assertEqual(r.status, 400, malo)

    def test_varios_eventos_con_coma_o_coma_codificada(self):
        self.respuestas_lector["1526"] = Lectura([DIA], [MAT], {1: [combate(2)]}, "https://o.smoothcomp.com")
        r = self.cargar("33588,1526")
        self.assertEqual(r.status, 200)
        r = self.cargar("33588%2C1526")
        self.assertEqual(len(self.json(r)["events"]), 2)

    def test_saturado_es_503(self):
        for i in range(1, 11):
            self.pedir("GET", f"/api/events/{i}/data")    # 10 lecturas en cola
        r = self.pedir("GET", "/api/events/999/data")
        self.assertEqual(r.status, 503)
        self.assertEqual(r.headers["retry-after"], "10")

    def test_un_error_inesperado_es_un_500_con_cuerpo(self):
        self.almacen.pedir = lambda ids: 1 / 0
        r = self.pedir("GET", "/api/events/33588/data")
        self.assertEqual(r.status, 500)
        self.assertIn("error", self.json(r))


class TestGrupo(Entorno):
    ANA = {"name": "Ana Pérez", "club": "Gracie Madrid", "accion": "añadir"}

    def test_leer_es_publico(self):
        self.grupos.actualizar("33588", "añadir", nombre="Ana")
        r = self.pedir("GET", "/api/events/33588/grupo",
                       cabeceras={"Host": "mi-servidor.example", "X-Forwarded-For": "8.8.8.8"})
        self.assertEqual(r.status, 200)
        self.assertEqual(self.json(r)["atletas"][0]["name"], "Ana")

    def test_el_operador_puede_apuntar_y_se_ve_al_instante_sin_releer_smoothcomp(self):
        self.cargar()
        lecturas = []
        self.almacen._leer = lambda *a, **k: lecturas.append(1)

        r = self.pedir("POST", "/api/events/33588/grupo", self.ANA)
        self.assertEqual(r.status, 200)
        self.assertEqual(self.json(r)["atletas"][0]["id"], "ana perez|gracie madrid")

        estado = self.json(self.pedir("GET", "/api/events/33588/data"))
        self.assertEqual({a["name"] for a in estado["athletes"] if a["inGroup"]}, {"Ana Pérez"})
        self.assertEqual(lecturas, [])

        r = self.pedir("POST", "/api/events/33588/grupo",
                       {"id": "ana perez|gracie madrid", "accion": "quitar"})
        self.assertEqual(self.json(r)["atletas"], [])
        estado = self.json(self.pedir("GET", "/api/events/33588/data"))
        self.assertFalse(any(a["inGroup"] for a in estado["athletes"]))

    def assert_rechazado(self, codigo, cabeceras=None, cuerpo=None, ruta="/api/events/33588/grupo"):
        r = self.pedir("POST", ruta, self.ANA if cuerpo is None else cuerpo, cabeceras)
        self.assertEqual(r.status, codigo, r.cuerpo)
        self.assertEqual(self.grupos.leer("33588")["atletas"], [], "no debe haber escrito nada")

    def test_rechaza_lo_que_llega_por_un_tunel(self):
        # Un túnel conecta desde 127.0.0.1, pero añade estas cabeceras.
        for cabecera, valor in (("X-Forwarded-For", "203.0.113.9"),
                                ("Forwarded", "for=203.0.113.9"),
                                ("CF-Connecting-IP", "203.0.113.9"),
                                ("X-Real-Ip", "203.0.113.9"),
                                ("Via", "1.1 cloudflare")):
            with self.subTest(cabecera):
                self.assert_rechazado(403, {cabecera: valor})

    def test_rechaza_un_host_que_no_es_el_local(self):
        for host in ("mi-servidor.trycloudflare.com", "192.168.1.20:8765", "localhost.malo.com"):
            with self.subTest(host):
                self.assert_rechazado(403, {"Host": host})

    def test_acepta_los_hosts_locales_con_puerto(self):
        for host in ("localhost", f"localhost:{self.puerto}", f"127.0.0.1:{self.puerto}"):
            with self.subTest(host):
                r = self.pedir("POST", "/api/events/33588/grupo", self.ANA, {"Host": host})
                self.assertEqual(r.status, 200)

    def test_rechaza_a_otra_web_abierta_en_el_navegador_del_operador(self):
        # CSRF: la web malo.example hace un POST a http://127.0.0.1:...
        self.assert_rechazado(403, {"Origin": "https://malo.example"})
        self.assert_rechazado(403, {"Origin": "null"})
        # y un formulario clásico no puede mandar application/json
        self.assert_rechazado(415, {"Content-Type": "text/plain"}, cuerpo=json.dumps(self.ANA))
        self.assert_rechazado(415, {"Content-Type": "application/x-www-form-urlencoded"},
                              cuerpo="name=Ana")

    def test_acepta_el_origin_del_propio_panel(self):
        r = self.pedir("POST", "/api/events/33588/grupo", self.ANA,
                       {"Origin": f"http://127.0.0.1:{self.puerto}"})
        self.assertEqual(r.status, 200)

    def test_peticiones_malformadas(self):
        self.assert_rechazado(400, cuerpo="{no es json",
                              cabeceras={"Content-Type": "application/json"})
        self.assert_rechazado(400, cuerpo=json.dumps([1, 2]), cabeceras={"Content-Type": "application/json"})
        self.assert_rechazado(400, cuerpo={"accion": "añadir"})                  # ni id ni nombre
        self.assert_rechazado(400, cuerpo={"name": "Ana", "accion": "borrar"})
        self.assert_rechazado(400, cuerpo={"name": "x" * 500})
        self.assert_rechazado(400, cuerpo=b"", cabeceras={"Content-Type": "application/json"})
        self.assert_rechazado(400, cuerpo=json.dumps({"name": "a" * 70000}),
                              cabeceras={"Content-Type": "application/json"})
        self.assert_rechazado(400, ruta="/api/events/abc/grupo")

    def test_post_a_otra_ruta_es_404(self):
        self.assertEqual(self.pedir("POST", "/api/events/33588/data", self.ANA).status, 404)
        self.assertEqual(self.pedir("POST", "/", self.ANA).status, 404)


class TestPuertoOcupado(Entorno):
    def test_un_segundo_servidor_en_el_mismo_puerto_falla(self):
        # En Windows, http.server permitía abrirlo dos veces sin error y nadie
        # sabía cuál de los dos contestaba.
        with self.assertRaises(OSError):
            crear_servidor(CFG, "127.0.0.1", self.puerto, self.buscador, self.almacen,
                           self.grupos)


class TestEsPanelLocal(unittest.TestCase):
    @staticmethod
    def handler(ip="127.0.0.1", **cabeceras):
        mensaje = Message()
        mensaje["Host"] = cabeceras.pop("Host", "localhost:8765")
        for clave, valor in cabeceras.items():
            mensaje[clave.replace("_", "-")] = valor
        return SimpleNamespace(client_address=(ip, 50000), headers=mensaje)

    def test_casos_validos(self):
        self.assertTrue(es_panel_local(self.handler()))
        self.assertTrue(es_panel_local(self.handler("::1", Host="[::1]:8765")))
        self.assertTrue(es_panel_local(self.handler("::ffff:127.0.0.1")))
        self.assertTrue(es_panel_local(self.handler(Host="127.0.0.1")))

    def test_ip_que_no_es_local(self):
        for ip in ("192.168.1.20", "10.0.0.5", "203.0.113.9", "no-es-una-ip"):
            self.assertFalse(es_panel_local(self.handler(ip)), ip)

    def test_cabeceras_de_proxy(self):
        self.assertFalse(es_panel_local(self.handler(X_Forwarded_For="1.2.3.4")))
        self.assertFalse(es_panel_local(self.handler(CF_Connecting_IP="1.2.3.4")))

    def test_host_y_origin(self):
        self.assertFalse(es_panel_local(self.handler(Host="evil.com")))
        self.assertFalse(es_panel_local(self.handler(Origin="http://evil.com")))
        self.assertTrue(es_panel_local(self.handler(Origin="http://localhost:8765")))


if __name__ == "__main__":
    unittest.main()
