"""
Pruebas de research/smoke_api.py: la prueba de humo que se pasa tras desplegar.

Se ejecuta contra el servidor de pruebas de test_servidor.py (el de verdad, con un buscador y
un lector de Smoothcomp falsos), así que lo que se comprueba es la prueba contra el servidor y no
contra una maqueta de él.

Uso:  python -m unittest discover -s tests
"""
import contextlib
import importlib.util
import io
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scraper.fetch import ErrorOrigen  # noqa: E402
from test_servidor import Entorno  # noqa: E402

_spec = importlib.util.spec_from_file_location("smoke_api", RAIZ / "research" / "smoke_api.py")
smoke_api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke_api)

# Lo que sirve la web compilada por Vite: un script de tipo módulo y la raíz de React.
INDEX = ('<!doctype html><html><head><script type="module" crossorigin src="./app.js"></script>'
         '<link rel="stylesheet" href="./estilos.css"></head><body><div id="raiz"></div></body></html>')


class RelojFalso:
    """Para no esperar de verdad: dormir adelanta el reloj."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, segundos):
        self.t += segundos


class PruebaHumo(Entorno):
    def setUp(self):
        super().setUp()
        (self.sitio / "index.html").write_text(INDEX, encoding="utf-8")
        (self.sitio / "estilos.css").write_text("body{margin:0}", encoding="utf-8")

    def verificar(self, **opciones):
        """(código de salida, texto de la salida)."""
        reloj = RelojFalso()
        lineas = []
        opciones = {"espera": 0, "dormir": reloj.dormir, "reloj": reloj, **opciones}
        codigo = smoke_api.verificar(f"http://127.0.0.1:{self.puerto}", salida=lineas.append, **opciones)
        return codigo, "\n".join(lineas)


class TestTodoBien(PruebaHumo):
    def test_un_servidor_sano_sale_con_cero(self):
        codigo, salida = self.verificar()
        self.assertEqual(codigo, 0, salida)
        self.assertNotIn("FALLO", salida)
        self.assertNotIn("AVISO", salida)
        for esperado in ("/api/health 200", "HEAD /api/health 200", "/api/config 200", "/ 200",
                         "./app.js 200", "./estilos.css 200", "/api/events/search 200",
                         "versión test"):
            self.assertIn(esperado, salida)

    def test_la_version_esperada_es_la_desplegada(self):
        codigo, salida = self.verificar(esperar_version="test")
        self.assertEqual(codigo, 0, salida)

    def test_la_busqueda_se_puede_omitir_y_entonces_no_se_toca_smoothcomp(self):
        codigo, salida = self.verificar(omitir_busqueda=True)
        self.assertEqual(codigo, 0, salida)
        self.assertNotIn("search", salida)
        self.assertEqual(self.buscador.consultas, [])


class TestFallos(PruebaHumo):
    def test_si_la_version_esperada_no_llega_falla_tras_la_espera(self):
        codigo, salida = self.verificar(esperar_version="otra", espera=6)
        self.assertEqual(codigo, 1)
        self.assertIn("FALLO", salida)
        self.assertIn("con la versión otra en 6 s", salida)
        self.assertIn("versión test", salida, "dice qué versión sí está desplegada")

    def test_espera_a_que_llegue_la_version_antes_de_dar_el_fallo(self):
        # Como un `fly deploy` que releva la máquina: durante unos segundos contesta la vieja.
        real = smoke_api.pedir
        versiones = iter(["vieja", "vieja", "test"])

        def pedir(url, metodo="GET", timeout=10):
            r = real(url, metodo, timeout)
            if url.endswith("/api/health") and metodo == "GET":
                datos = json.loads(r.cuerpo)
                datos["version"] = next(versiones)
                return r._replace(cuerpo=json.dumps(datos).encode())
            return r
        with mock.patch.object(smoke_api, "pedir", pedir):
            codigo, salida = self.verificar(esperar_version="test", espera=10)
        self.assertEqual(codigo, 0, salida)

    def test_tolera_que_el_servidor_no_conteste_mientras_arranca(self):
        real = smoke_api.pedir
        caidas = iter([True, True, False])

        def pedir(url, metodo="GET", timeout=10):
            if url.endswith("/api/health") and metodo == "GET" and next(caidas, False):
                raise smoke_api.ErrorDeConexion("Connection refused")
            return real(url, metodo, timeout)
        with mock.patch.object(smoke_api, "pedir", pedir):
            codigo, salida = self.verificar(espera=10)
        self.assertEqual(codigo, 0, salida)

    def test_sin_web_compilada_el_health_es_503_y_falla(self):
        (self.sitio / "index.html").unlink()
        codigo, salida = self.verificar()
        self.assertEqual(codigo, 1)
        self.assertIn("HTTP 503", salida)

    def test_una_pagina_que_no_es_la_web_falla(self):
        (self.sitio / "index.html").write_text("<h1>hola web</h1>", encoding="utf-8")
        codigo, salida = self.verificar()
        self.assertEqual(codigo, 1)
        self.assertIn('id="raiz"', salida)
        self.assertIn("no referencia ningún script", salida)

    def test_un_script_con_el_tipo_equivocado_falla_porque_el_navegador_no_lo_ejecutaria(self):
        (self.sitio / "datos.txt").write_text("console.log(1)", encoding="utf-8")
        (self.sitio / "index.html").write_text(INDEX.replace("./app.js", "./datos.txt"), encoding="utf-8")
        codigo, salida = self.verificar()
        self.assertEqual(codigo, 1)
        self.assertIn("./datos.txt se sirve como «text/plain»", salida)
        self.assertIn("un script", salida)

    def test_un_fichero_que_falta_falla(self):
        (self.sitio / "estilos.css").unlink()
        codigo, salida = self.verificar()
        self.assertEqual(codigo, 1)
        self.assertIn("./estilos.css devuelve 404", salida)

    def test_un_servidor_que_no_contesta_falla_sin_colgarse(self):
        # Un solo intento real (espera=0): en Windows cada conexión rechazada tarda un par de
        # segundos. Que se insiste durante la espera lo prueba el test de arriba.
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            puerto = s.getsockname()[1]
        lineas = []
        codigo = smoke_api.verificar(f"http://127.0.0.1:{puerto}", espera=0, timeout=3,
                                     salida=lineas.append)
        self.assertEqual(codigo, 1)
        self.assertIn("sin conexión", "\n".join(lineas))


class TestAvisos(PruebaHumo):
    def test_si_smoothcomp_no_contesta_desde_ese_servidor_es_un_aviso_no_un_fallo(self):
        self.buscador.respuesta = ErrorOrigen("HTTP 403", codigo=403, desafio=True)
        codigo, salida = self.verificar()
        self.assertEqual(codigo, 2, salida)
        self.assertIn("AVISO  la búsqueda no llega a Smoothcomp desde ese servidor", salida)
        self.assertNotIn("FALLO", salida)

    def test_con_la_busqueda_omitida_ese_mismo_fallo_no_cuenta(self):
        self.buscador.respuesta = ErrorOrigen("HTTP 403", codigo=403, desafio=True)
        self.assertEqual(self.verificar(omitir_busqueda=True)[0], 0)

    def test_una_busqueda_con_copia_vieja_avisa(self):
        self.buscador.respuesta = {"events": [], "page": 1, "hasMore": False, "stale": True}
        codigo, salida = self.verificar()
        self.assertEqual(codigo, 2, salida)
        self.assertIn("copia vieja", salida)

    def test_un_servidor_degradado_es_un_aviso_con_el_motivo(self):
        self.respuestas_lector["33588"] = ErrorOrigen("HTTP 403", codigo=403, desafio=True)
        self.pedir("GET", "/api/events/33588/data")
        self.almacen.procesar_pendientes()
        codigo, salida = self.verificar(omitir_busqueda=True)
        self.assertEqual(codigo, 2, salida)
        self.assertIn("degradado", salida)
        self.assertIn("1 sin poder leerse", salida)
        self.assertIn("reto de Cloudflare: True", salida)

    def test_un_error_de_la_busqueda_que_no_es_el_502_es_un_fallo(self):
        self.buscador.respuesta = RuntimeError("boom")        # el servidor contesta 500
        codigo, salida = self.verificar()
        self.assertEqual(codigo, 1)
        self.assertIn("/api/events/search devuelve 500", salida)


class TestLineaDeComandos(PruebaHumo):
    def main(self, *opciones):
        with contextlib.redirect_stdout(io.StringIO()):
            return smoke_api.main([f"http://127.0.0.1:{self.puerto}", "--omitir-busqueda",
                                   "--espera", "0", *opciones])

    def test_main_pasa_las_opciones_y_devuelve_el_codigo(self):
        self.assertEqual(self.main("--esperar-version", "test"), 0)
        self.assertEqual(self.main("--esperar-version", "otra"), 1)

    def test_exige_una_direccion_con_esquema(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            smoke_api.main(["127.0.0.1:8765"])


class TestRecursos(unittest.TestCase):
    def test_el_tipo_esperado_lo_marca_como_se_referencia_no_la_extension(self):
        html = ('<script type="module" crossorigin src="./assets/index-ab12.js"></script>'
                '<script src="./raro.txt"></script>'
                '<link rel="modulepreload" href="./assets/vendor.js">'
                '<link rel="stylesheet" crossorigin href="./assets/index-cd34.css">'
                '<link rel="icon" href="./favicon.ico">')
        self.assertEqual(smoke_api._recursos(html), [
            ("./assets/index-ab12.js", "javascript"), ("./raro.txt", "javascript"),
            ("./assets/vendor.js", "javascript"), ("./assets/index-cd34.css", "text/css")])


if __name__ == "__main__":
    unittest.main()
