"""
Pruebas del buscador de eventos. No tocan la red: la página de Smoothcomp se
sustituye por una función que devuelve el HTML que haría falta.

`fixtures/busqueda_proximos_madrid.json` es la lista real que devolvió
`/es/events/upcoming?search=madrid` (4 eventos); aquí se envuelve en el HTML
mínimo que la lleva incrustada.

Uso:  python -m unittest discover -s tests
"""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper import eventos  # noqa: E402
from scraper.eventos import Buscador  # noqa: E402
from scraper.fetch import ErrorOrigen  # noqa: E402

FIXTURE = RAIZ / "fixtures" / "busqueda_proximos_madrid.json"
CFG = {"baseUrl": "https://smoothcomp.com", "lang": "en", "timeoutSeconds": 5,
       "servidor": {"listaEventosTtlSeconds": 600}}


def pagina(lista):
    """El HTML mínimo con la lista incrustada, como la sirve Smoothcomp."""
    return ("<html><head><script>\n  var events = "
            f"{json.dumps(lista, ensure_ascii=False)};\n  </script></head><body></body></html>")


def cargar_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def evento_crudo(n, fecha="2026-11-01", **extra):
    return {"id": n, "title": f"Evento {n}", "url": f"https://org{n}.smoothcomp.com/es/event/{n}",
            "startdate": fecha, "enddate": fecha, "location_city": "Madrid",
            "location_country": "ES", "eventEnded": False, **extra}


class TestExtraerEventos(unittest.TestCase):
    def test_lee_la_lista_real(self):
        lista = eventos.extraer_eventos(pagina(cargar_fixture()))
        self.assertEqual([e["id"] for e in lista], [31768, 33588, 33644, 34939])

    def test_los_corchetes_dentro_de_los_textos_no_rompen_el_corte(self):
        # Una regex "hasta el primer ];" se partiría aquí.
        raro = evento_crudo(1, title="Copa ]; var otra = [1, 2];")
        lista = eventos.extraer_eventos(pagina([raro]) + "<script>var otra = [9];</script>")
        self.assertEqual(lista[0]["title"], "Copa ]; var otra = [1, 2];")

    def test_sin_lista_es_un_fallo_del_origen(self):
        with self.assertRaises(ErrorOrigen) as ctx:
            eventos.extraer_eventos("<html>nada</html>")
        self.assertFalse(ctx.exception.desafio)

    def test_el_reto_de_cloudflare_se_reconoce(self):
        with self.assertRaises(ErrorOrigen) as ctx:
            eventos.extraer_eventos("<title>Just a moment...</title>")
        self.assertTrue(ctx.exception.desafio)

    def test_json_roto_o_que_no_es_lista(self):
        with self.assertRaises(ErrorOrigen):
            eventos.extraer_eventos("<script>var events = [{'id': 1}];</script>")
        with self.assertRaises(ErrorOrigen):
            eventos.extraer_eventos('<script>var events = {"id": 1};</script>')


class TestNormalizarEvento(unittest.TestCase):
    def test_campos_del_evento_real(self):
        crudo = next(e for e in cargar_fixture() if e["id"] == 33588)
        e = eventos.normalizar_evento(crudo)
        self.assertEqual(e["id"], "33588")
        self.assertEqual(e["title"], "MADRID BJJ CUP GI & NO-GI 2026")
        self.assertEqual(e["baseUrl"], "https://spainbjjtour.smoothcomp.com")
        self.assertEqual((e["startdate"], e["enddate"]), ("2026-10-17", "2026-10-17"))
        self.assertEqual(e["country"], "ES")
        self.assertFalse(e["ended"])

    def test_solo_se_aceptan_hosts_de_smoothcomp_por_https(self):
        for url in ("https://otro-sitio.com/es/event/1",
                    "http://org.smoothcomp.com/es/event/1",       # sin https
                    "https://smoothcomp.com.malo.com/es/event/1",  # parece, pero no es
                    "javascript:alert(1)", None, ""):
            e = eventos.normalizar_evento(evento_crudo(1, url=url))
            self.assertIsNone(e["baseUrl"], url)
            self.assertIsNone(e["url"], f"{url}: no se ofrece como enlace")
        self.assertEqual(eventos.normalizar_evento(
            evento_crudo(1, url="https://smoothcomp.com/es/event/1"))["baseUrl"],
            "https://smoothcomp.com")

    def test_lo_que_no_es_un_evento_se_descarta(self):
        for basura in (None, 7, "texto", {}, {"id": "abc"}, {"title": "sin id"}):
            self.assertIsNone(eventos.normalizar_evento(basura), basura)

    def test_valores_por_defecto(self):
        e = eventos.normalizar_evento({"id": 5, "title": "  ", "location_city": " "})
        self.assertEqual(e["title"], "Evento 5")
        self.assertIsNone(e["city"])
        self.assertFalse(e["ended"])


class TestLimpiarConsulta(unittest.TestCase):
    def test_espacios_y_caracteres_de_control(self):
        self.assertEqual(eventos.limpiar_consulta("  madrid \n\t cup\x00 "), "madrid cup")
        self.assertEqual(eventos.limpiar_consulta(None), "")

    def test_demasiado_larga(self):
        with self.assertRaises(ValueError):
            eventos.limpiar_consulta("x" * 81)
        self.assertEqual(len(eventos.limpiar_consulta("x" * 80)), 80)


class Falso:
    """Un Smoothcomp de mentira que apunta qué se le pidió."""

    def __init__(self, respuestas):
        self.respuestas = respuestas    # url -> lista de eventos crudos (o excepción)
        self.html = []                  # urls pedidas
        self.json = []

    def pedir_html(self, url, timeout):
        self.html.append(url)
        respuesta = self.respuestas[url]
        if isinstance(respuesta, Exception):
            raise respuesta
        return pagina(respuesta), url

    def pedir_json(self, url, timeout):
        self.json.append(url)
        respuesta = self.respuestas[url]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class PruebaBuscador(unittest.TestCase):
    def buscador(self, respuestas):
        self.falso = Falso(respuestas)
        self.reloj = Reloj()
        return Buscador(CFG, pedir_html=self.falso.pedir_html,
                        pedir_json=self.falso.pedir_json, reloj=self.reloj)


class TestBuscar(PruebaBuscador):
    BASE = "https://smoothcomp.com/en/events"

    def test_proximos_con_texto(self):
        b = self.buscador({f"{self.BASE}/upcoming?search=madrid": cargar_fixture()})
        r = b.buscar("madrid", "upcoming")
        self.assertEqual([e["id"] for e in r["events"]], ["31768", "33588", "33644", "34939"])
        self.assertEqual((r["page"], r["hasMore"], r["stale"]), (1, False, False))

    def test_sin_texto_no_hay_query_string(self):
        b = self.buscador({f"{self.BASE}/upcoming": []})
        b.buscar("", "upcoming")
        self.assertEqual(self.falso.html, [f"{self.BASE}/upcoming"])

    def test_el_texto_se_codifica_en_la_url(self):
        b = self.buscador({f"{self.BASE}/upcoming?search=a%26b+%C3%B1": []})
        b.buscar("a&b ñ", "upcoming")   # no debe colarse un segundo parámetro

    def test_proximos_ordenados_del_mas_cercano_al_mas_lejano(self):
        crudos = [evento_crudo(3, "2027-01-01"), evento_crudo(1, "2026-10-20"),
                  evento_crudo(2, "2026-10-20")]
        b = self.buscador({f"{self.BASE}/upcoming": crudos})
        self.assertEqual([e["id"] for e in b.buscar("", "upcoming")["events"]],
                         ["1", "2", "3"])

    def test_proximos_se_paginan_en_el_servidor(self):
        crudos = [evento_crudo(i, f"2026-11-{(i % 28) + 1:02d}") for i in range(1, 96)]
        b = self.buscador({f"{self.BASE}/upcoming": crudos})
        p1, p3 = b.buscar("", "upcoming", 1), b.buscar("", "upcoming", 3)
        self.assertEqual((len(p1["events"]), p1["hasMore"]), (40, True))
        self.assertEqual((len(p3["events"]), p3["hasMore"]), (15, False))
        self.assertEqual(len(self.falso.html), 1, "las tres páginas salen de una sola lectura")

    def test_pasados_paginan_en_origen(self):
        b = self.buscador({
            f"{self.BASE}/past?search=kimura": [evento_crudo(i) for i in range(40)],
            f"{self.BASE}/past?search=kimura&page=2": [evento_crudo(i) for i in range(100, 125)],
        })
        p1, p2 = b.buscar("kimura", "past", 1), b.buscar("kimura", "past", 2)
        self.assertTrue(p1["hasMore"], "40 resultados: puede haber más")
        self.assertFalse(p2["hasMore"], "25 resultados: era la última")

    def test_todos_junta_proximos_y_pasados(self):
        b = self.buscador({
            f"{self.BASE}/upcoming?search=x": [evento_crudo(2, "2026-12-01")],
            f"{self.BASE}/past?search=x": [evento_crudo(1, "2025-01-01", eventEnded=True)],
        })
        r = b.buscar("x", "all")
        self.assertEqual([e["id"] for e in r["events"]], ["2", "1"])
        self.assertEqual([e["ended"] for e in r["events"]], [False, True])

    def test_parametros_invalidos(self):
        b = self.buscador({})
        for args in (("", "mañana", 1), ("", "all", 0), ("", "all", 201), ("", "all", "a"),
                     ("x" * 81, "all", 1)):
            with self.assertRaises(ValueError, msg=args):
                b.buscar(*args)
        self.assertEqual(self.falso.html, [], "ni se llega a pedir nada")


class TestCache(PruebaBuscador):
    URL = "https://smoothcomp.com/en/events/upcoming?search=madrid"

    def test_la_segunda_consulta_sale_de_la_cache(self):
        b = self.buscador({self.URL: cargar_fixture()})
        b.buscar("madrid", "upcoming")
        b.buscar("Madrid", "upcoming")     # mayúsculas: la misma consulta
        self.assertEqual(len(self.falso.html), 1)

        self.reloj.t += 601
        b.buscar("madrid", "upcoming")
        self.assertEqual(len(self.falso.html), 2, "pasado el TTL se vuelve a pedir")

    def test_si_smoothcomp_falla_se_sirve_la_copia_vieja_avisando(self):
        b = self.buscador({self.URL: cargar_fixture()})
        b.buscar("madrid", "upcoming")
        self.falso.respuestas[self.URL] = ErrorOrigen("HTTP 502", codigo=502)

        self.reloj.t += 601
        r = b.buscar("madrid", "upcoming")
        self.assertTrue(r["stale"])
        self.assertEqual(len(r["events"]), 4)
        self.assertEqual(len(self.falso.html), 2)

        # No se insiste en cada petición mientras esté caído, y sigue avisando...
        self.reloj.t += 10
        r = b.buscar("madrid", "upcoming")
        self.assertTrue(r["stale"])
        self.assertEqual(len(self.falso.html), 2)
        # ...pero sí pasado un rato, y al recuperarse deja de estar vieja.
        self.reloj.t += 30
        self.falso.respuestas[self.URL] = cargar_fixture()
        r = b.buscar("madrid", "upcoming")
        self.assertFalse(r["stale"])
        self.assertEqual(len(self.falso.html), 3)

    def test_sin_copia_el_fallo_se_propaga(self):
        b = self.buscador({self.URL: ErrorOrigen("HTTP 403", codigo=403, desafio=True)})
        with self.assertRaises(ErrorOrigen) as ctx:
            b.buscar("madrid", "upcoming")
        self.assertTrue(ctx.exception.desafio)

    def test_la_cache_tiene_tope(self):
        respuestas = {f"https://smoothcomp.com/en/events/upcoming?search=q{i}": []
                      for i in range(eventos.MAX_CONSULTAS_EN_CACHE + 20)}
        b = self.buscador(respuestas)
        for i in range(eventos.MAX_CONSULTAS_EN_CACHE + 20):
            b.buscar(f"q{i}", "upcoming")
        self.assertLessEqual(len(b._cache), eventos.MAX_CONSULTAS_EN_CACHE)


class TestEventoSuelto(PruebaBuscador):
    CMS = "https://smoothcomp.com/en/event/26416/getCmsData"

    def test_un_evento_visto_en_la_busqueda_no_cuesta_otra_peticion(self):
        b = self.buscador({"https://smoothcomp.com/en/events/upcoming?search=madrid":
                           cargar_fixture()})
        b.buscar("madrid", "upcoming")
        e = b.evento("33588")
        self.assertEqual(e["baseUrl"], "https://spainbjjtour.smoothcomp.com")
        self.assertEqual(self.falso.json, [])

    def test_un_id_desconocido_se_resuelve_con_getcmsdata(self):
        final = "https://kimuracup.smoothcomp.com/en/event/26416/getCmsData"
        b = self.buscador({self.CMS: ({"eventData": {"title": "KIMURA CUP MADRID 2026",
                                                     "event_start": "01 Feb"}}, final)})
        e = b.evento(26416)    # también acepta el id como número
        self.assertEqual(e["title"], "KIMURA CUP MADRID 2026")
        self.assertEqual(e["baseUrl"], "https://kimuracup.smoothcomp.com")
        self.assertIsNone(e["startdate"], "getCmsData no da un año: no se inventa")

        b.evento("26416")
        self.assertEqual(len(self.falso.json), 1, "la segunda vez ya lo conoce")

    def test_sin_titulo_se_usa_el_id(self):
        b = self.buscador({self.CMS: ({"eventData": {}}, self.CMS)})
        self.assertEqual(b.evento("26416")["title"], "Evento 26416")

    def test_un_evento_inexistente_propaga_el_404(self):
        b = self.buscador({self.CMS: ErrorOrigen("HTTP 404", codigo=404)})
        with self.assertRaises(ErrorOrigen) as ctx:
            b.evento("26416")
        self.assertEqual(ctx.exception.codigo, 404)

    def test_un_host_ajeno_no_se_recuerda_como_base(self):
        b = self.buscador({self.CMS: ({"eventData": {"title": "X"}},
                                      "https://ajptour.com/en/event/26416/getCmsData")})
        self.assertIsNone(b.evento("26416")["baseUrl"])


if __name__ == "__main__":
    unittest.main()
