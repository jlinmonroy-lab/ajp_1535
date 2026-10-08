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
from scraper.eventos import Buscador, Zona, distancia_km  # noqa: E402
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
    def buscador(self, respuestas, cfg=None):
        self.falso = Falso(respuestas)
        self.reloj = Reloj()
        return Buscador(cfg or CFG, pedir_html=self.falso.pedir_html,
                        pedir_json=self.falso.pedir_json, reloj=self.reloj,
                        hoy=lambda: "2026-10-08")


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

    def test_lo_que_ya_esta_en_marcha_va_despues_de_lo_que_no_ha_empezado(self):
        # Una liga de todo el año no debe tapar los torneos de la semana que viene.
        crudos = [
            evento_crudo(1, "2026-01-01", enddate="2026-12-31"),   # liga anual, ya empezada
            evento_crudo(2, "2026-10-20"),
            evento_crudo(3, "2026-10-08"),                         # empieza hoy: no ha empezado
            evento_crudo(4, "2026-06-01", enddate="2026-11-01"),   # en marcha, acaba antes
            evento_crudo(5, "2027-03-03"),
        ]
        b = self.buscador({f"{self.BASE}/upcoming": crudos})
        self.assertEqual([e["id"] for e in b.buscar("", "upcoming")["events"]],
                         ["3", "2", "5", "4", "1"])

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


# ---------------------------------------------------------------------------
# Zona: «Madrid, España» como filtro por defecto del buscador
# ---------------------------------------------------------------------------
MADRID = {"nombre": "Madrid, España", "pais": "ES", "texto": "madrid",
          "centro": [40.4168, -3.7038], "radioKm": 50}
CFG_ZONA = {**CFG, "zona": MADRID}


def en(n, titulo, ciudad, lat=None, lon=None, pais="ES", fecha="2026-11-01"):
    """Un evento tal como lo manda Smoothcomp: coordenadas como texto."""
    return evento_crudo(n, fecha, title=titulo, location_city=ciudad, location_country=pais,
                        location_lat=None if lat is None else str(lat),
                        location_long=None if lon is None else str(lon))


class TestCoordenadas(unittest.TestCase):
    def test_se_leen_del_texto_que_manda_smoothcomp(self):
        e = eventos.normalizar_evento(evento_crudo(1, location_lat="40.3012", location_long="-3.4402"))
        self.assertEqual((e["lat"], e["lon"]), (40.3012, -3.4402))

    def test_las_del_evento_real(self):
        crudo = next(x for x in cargar_fixture() if x["id"] == 33588)
        e = eventos.normalizar_evento(crudo)
        self.assertTrue(39 < e["lat"] < 42 and -5 < e["lon"] < -2, (e["lat"], e["lon"]))

    def test_lo_que_no_es_una_coordenada_valida_es_none(self):
        # Cada una se valida por separado: una latitud fuera de rango no invalida la longitud.
        for lat, lon, esperado in (
                (None, None, (None, None)), ("", "", (None, None)), ("abc", "x", (None, None)),
                ("nan", "inf", (None, None)),
                ("95", "10", (None, 10.0)), ("10", "200", (10.0, None)), ("-91", "0", (None, 0.0))):
            e = eventos.normalizar_evento(evento_crudo(1, location_lat=lat, location_long=lon))
            self.assertEqual((e["lat"], e["lon"]), esperado, (lat, lon))


class TestZonaDeConfig(unittest.TestCase):
    def test_zona_completa(self):
        z = Zona.de_config(MADRID)
        self.assertEqual((z.nombre, z.pais, z.texto, z.centro, z.radio_km),
                         ("Madrid, España", "ES", "madrid", (40.4168, -3.7038), 50.0))

    def test_el_pais_se_pasa_a_mayusculas(self):
        self.assertEqual(Zona.de_config({**MADRID, "pais": "es"}).pais, "ES")

    def test_vale_con_solo_texto_o_con_solo_radio(self):
        self.assertIsNone(Zona.de_config({"nombre": "N", "pais": "ES", "texto": "madrid"}).centro)
        z = Zona.de_config({"nombre": "N", "pais": "ES", "centro": [40, -3], "radioKm": 10})
        self.assertIsNone(z.texto)

    def test_configuraciones_mal_escritas(self):
        malas = [
            "no es un objeto",
            {**MADRID, "nombre": ""},
            {k: v for k, v in MADRID.items() if k != "pais"},
            {**MADRID, "pais": "ESP"},
            {**MADRID, "pais": "1A"},
            {**MADRID, "centro": [40.4]},
            {**MADRID, "centro": ["a", "b"]},
            {**MADRID, "centro": [95, 0]},
            {**MADRID, "radioKm": 0},
            {**MADRID, "radioKm": -5},
            {**MADRID, "radioKm": True},
            {**MADRID, "radioKm": "50"},
            {"nombre": "N", "pais": "ES", "centro": [40, -3]},       # centro sin radio
            {"nombre": "N", "pais": "ES", "radioKm": 50},            # radio sin centro
            {"nombre": "N", "pais": "ES"},                           # ni texto ni centro
        ]
        for mala in malas:
            with self.assertRaises(ValueError, msg=repr(mala)):
                Zona.de_config(mala)


class TestZonaContiene(unittest.TestCase):
    def setUp(self):
        self.zona = Zona.de_config(MADRID)

    def dentro(self, crudo):
        return self.zona.contiene(eventos.normalizar_evento(crudo))

    def test_por_la_ciudad(self):
        self.assertTrue(self.dentro(en(1, "All Stars BJJ", "Madrid")))
        self.assertTrue(self.dentro(en(2, "Copa", "Arganda del Rey, (Madrid)")))

    def test_por_el_titulo_aunque_la_ciudad_sea_otra(self):
        self.assertTrue(self.dentro(en(1, "ADCC SPAIN MADRID OPEN 2026", "Torrejon de ardoz")))

    def test_por_el_radio_aunque_no_diga_madrid(self):
        # Alcalá de Henares, a unos 26 km: ni el título ni la ciudad dicen Madrid.
        self.assertTrue(self.dentro(en(1, "Open Alcala", "Alcala de Henares", 40.4818, -3.3635)))

    def test_fuera_del_radio(self):
        guadalajara = en(1, "European Cup", "Guadalajara", 40.6286, -3.1618)
        self.assertGreater(distancia_km(40.4168, -3.7038, 40.6286, -3.1618), 50)
        self.assertFalse(self.dentro(guadalajara))
        self.assertFalse(self.dentro(en(2, "Copa", "Barcelona", 41.3874, 2.1686)))

    def test_el_radio_es_configurable(self):
        ancha = Zona.de_config({**MADRID, "radioKm": 60})
        self.assertTrue(ancha.contiene(eventos.normalizar_evento(
            en(1, "European Cup", "Guadalajara", 40.6286, -3.1618))))

    def test_otro_pais_nunca(self):
        # «Madrid» en el título, pero en Texas; y uno a las puertas de Madrid pero de otro país.
        self.assertFalse(self.dentro(en(1, "Madrid Open", "Madrid, TX", 31.0, -100.0, pais="US")))
        self.assertFalse(self.dentro(en(2, "Madrid Cup", "Lisboa", pais="PT")))
        self.assertFalse(self.dentro(en(3, "Madrid Cup", "Madrid", pais=None)))

    def test_sin_coordenadas_ni_texto_no_hay_forma_de_saberlo(self):
        self.assertFalse(self.dentro(en(1, "Open Getafe", "Getafe")))

    def test_sin_acentos_ni_mayusculas(self):
        self.assertTrue(self.dentro(en(1, "COPA MÁDRID", "Sevilla")))
        self.assertTrue(self.dentro(en(2, "Copa", "MÁDRID")))

    def test_un_evento_con_pais_en_minusculas(self):
        self.assertTrue(self.dentro(en(1, "Copa Madrid", "Madrid", pais="es")))

    def test_distancia_entre_ciudades_conocidas(self):
        # Madrid-Barcelona, en línea recta, ronda los 505 km.
        self.assertAlmostEqual(distancia_km(40.4168, -3.7038, 41.3874, 2.1686), 505, delta=10)
        self.assertEqual(distancia_km(40.0, -3.0, 40.0, -3.0), 0)


class TestBuscarConZona(PruebaBuscador):
    BASE = "https://smoothcomp.com/en/events"
    PROXIMOS = f"{BASE}/upcoming?countries=ES"

    def lista_de_espana(self):
        """Lo que contestaría `upcoming?countries=ES`."""
        return [
            en(31768, "ADCC SPAIN MADRID OPEN 2026", "Torrejon de ardoz", 40.46, -3.47, fecha="2026-10-10"),
            en(33588, "MADRID BJJ CUP GI & NO-GI 2026", "Arganda del Rey, (Madrid)", 40.30, -3.44, fecha="2026-10-17"),
            en(33001, "Open Alcala", "Alcala de Henares", 40.4818, -3.3635, fecha="2026-10-25"),
            en(33194, "European Cup 2026", "Guadalajara", 40.6286, -3.1618, fecha="2026-11-15"),
            en(35227, "BJJPRO ZARAGOZA 2026", "Zaragoza", 41.6488, -0.8891, fecha="2026-11-15"),
            en(33999, "Madrid Open", "Madrid, TX", 31.0, -100.0, pais="US", fecha="2026-12-01"),
            en(34000, "Open Getafe", "Getafe", fecha="2026-12-02"),                 # sin coordenadas
            en(33644, "All Stars BJJ Madrid", "Madrid", 40.41, -3.70, fecha="2026-12-13"),
        ]

    def ids(self, resultado):
        return [e["id"] for e in resultado["events"]]

    def test_proximos_de_la_zona_en_orden_de_fecha(self):
        b = self.buscador({self.PROXIMOS: self.lista_de_espana()}, CFG_ZONA)
        r = b.buscar("", "upcoming", 1, zona=True)
        self.assertEqual(self.ids(r), ["31768", "33588", "33001", "33644"])
        self.assertFalse(r["hasMore"])

    def test_pide_la_lista_del_pais_entera_y_sin_texto(self):
        b = self.buscador({self.PROXIMOS: self.lista_de_espana()}, CFG_ZONA)
        b.buscar("", "upcoming", 1, zona=True)
        self.assertEqual(self.falso.html, [self.PROXIMOS])     # ni `search` ni nada más

    def test_el_texto_estrecha_aqui_y_comparte_la_peticion(self):
        b = self.buscador({self.PROXIMOS: self.lista_de_espana()}, CFG_ZONA)
        self.assertEqual(self.ids(b.buscar("alcala", "upcoming", 1, zona=True)), ["33001"])
        self.assertEqual(self.ids(b.buscar("madrid", "upcoming", 1, zona=True)),
                         ["31768", "33588", "33644"])
        # El texto sí mira la ciudad aquí, que Smoothcomp no hace.
        self.assertEqual(self.ids(b.buscar("arganda", "upcoming", 1, zona=True)), ["33588"])
        self.assertEqual(self.ids(b.buscar("zaragoza", "upcoming", 1, zona=True)), [],
                         "fuera de la zona, aunque coincida el texto")
        self.assertEqual(len(self.falso.html), 1, "cuatro búsquedas distintas, una sola petición")

    def test_los_proximos_se_paginan_en_local(self):
        muchos = [en(1000 + i, f"Madrid Open {i}", "Madrid", fecha=f"2026-11-{(i % 28) + 1:02d}")
                  for i in range(95)]
        b = self.buscador({self.PROXIMOS: muchos}, CFG_ZONA)
        p1, p3 = b.buscar("", "upcoming", 1, zona=True), b.buscar("", "upcoming", 3, zona=True)
        self.assertEqual((len(p1["events"]), p1["hasMore"]), (40, True))
        self.assertEqual((len(p3["events"]), p3["hasMore"]), (15, False))
        self.assertEqual(len(self.falso.html), 1)

    def test_los_pasados_piden_el_texto_de_la_zona_y_filtran_aqui_lo_escrito(self):
        pasados = [en(26416, "KIMURA CUP MADRID 2026", "Arganda del Rey, (Madrid)", fecha="2026-02-01"),
                   en(30701, "GSLS MADRID INTERNATIONAL", "Madrid", fecha="2026-05-01")]
        b = self.buscador({f"{self.BASE}/past?countries=ES&search=madrid": pasados}, CFG_ZONA)
        self.assertEqual(self.ids(b.buscar("", "past", 1, zona=True)), ["26416", "30701"])
        self.assertEqual(self.ids(b.buscar("kimura", "past", 1, zona=True)), ["26416"])
        self.assertEqual(len(self.falso.html), 1, "lo escrito se filtra aquí: misma petición")

    def test_pasados_pagina_dos(self):
        pagina1 = [en(2000 + i, f"Madrid Cup {i}", "Madrid") for i in range(40)]
        pagina2 = [en(3000, "Madrid Cup final", "Madrid")]
        b = self.buscador({f"{self.BASE}/past?countries=ES&search=madrid": pagina1,
                           f"{self.BASE}/past?countries=ES&search=madrid&page=2": pagina2}, CFG_ZONA)
        self.assertTrue(b.buscar("", "past", 1, zona=True)["hasMore"])
        r2 = b.buscar("", "past", 2, zona=True)
        self.assertFalse(r2["hasMore"])
        self.assertEqual(self.ids(r2), ["3000"])

    def test_hay_mas_se_mide_antes_de_filtrar_lo_escrito(self):
        # 40 en origen y solo uno coincide con lo escrito: aun así hay otra página.
        pagina1 = [en(2000 + i, f"Madrid Cup {i}", "Madrid") for i in range(40)]
        b = self.buscador({f"{self.BASE}/past?countries=ES&search=madrid": pagina1}, CFG_ZONA)
        r = b.buscar("cup 7", "past", 1, zona=True)
        self.assertEqual(self.ids(r), ["2007"])
        self.assertTrue(r["hasMore"])

    def test_todos_junta_proximos_y_pasados_de_la_zona(self):
        b = self.buscador({
            self.PROXIMOS: self.lista_de_espana(),
            f"{self.BASE}/past?countries=ES&search=madrid":
                [en(26416, "KIMURA CUP MADRID 2026", "Arganda del Rey, (Madrid)", fecha="2026-02-01")],
        }, CFG_ZONA)
        self.assertEqual(self.ids(b.buscar("", "all", 1, zona=True)),
                         ["31768", "33588", "33001", "33644", "26416"])

    def test_si_smoothcomp_falla_se_sirve_la_copia_vieja(self):
        b = self.buscador({self.PROXIMOS: self.lista_de_espana()}, CFG_ZONA)
        b.buscar("", "upcoming", 1, zona=True)
        self.falso.respuestas[self.PROXIMOS] = ErrorOrigen("HTTP 502", codigo=502)
        self.reloj.t += 601
        r = b.buscar("", "upcoming", 1, zona=True)
        self.assertTrue(r["stale"])
        self.assertEqual(len(r["events"]), 4)

    def test_sin_zona_en_la_peticion_el_buscador_es_el_de_siempre(self):
        b = self.buscador({f"{self.BASE}/upcoming?search=madrid": self.lista_de_espana()}, CFG_ZONA)
        r = b.buscar("madrid", "upcoming", 1)
        self.assertEqual(self.falso.html, [f"{self.BASE}/upcoming?search=madrid"])
        self.assertEqual(len(r["events"]), 8, "sin filtrar nada")

    def test_pedir_zona_sin_tenerla_configurada_es_un_error(self):
        b = self.buscador({}, CFG)
        with self.assertRaises(ValueError):
            b.buscar("", "upcoming", 1, zona=True)
        self.assertEqual(self.falso.html, [])
        self.assertIsNone(b.zona)

    def test_una_zona_mal_escrita_impide_crear_el_buscador(self):
        with self.assertRaises(ValueError):
            self.buscador({}, {**CFG, "zona": {"nombre": "Madrid"}})

    def test_los_eventos_recordados_incluyen_los_de_la_zona(self):
        b = self.buscador({self.PROXIMOS: self.lista_de_espana()}, CFG_ZONA)
        b.buscar("", "upcoming", 1, zona=True)
        self.assertEqual(b.conocido("33588")["city"], "Arganda del Rey, (Madrid)")
        self.assertIsNone(b.conocido("35227"), "los que se filtran no se enseñan ni se recuerdan")


if __name__ == "__main__":
    unittest.main()
