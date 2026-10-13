"""
Pruebas del almacén de eventos: la caché compartida del servidor.

Sin red ni hilos: el lector de Smoothcomp y el buscador son falsos, el reloj lo
mueve el test y las lecturas encoladas se procesan a mano con
`procesar_pendientes()`.

Uso:  python -m unittest discover -s tests
"""
import gzip
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper import almacen as modulo_almacen  # noqa: E402
from scraper.almacen import Almacen, Saturado, normalizar_ids  # noqa: E402
from scraper.fetch import ErrorOrigen, Lectura  # noqa: E402
from scraper.grupos import Grupos  # noqa: E402

CFG = {"baseUrl": "https://smoothcomp.com", "lang": "en", "refreshSeconds": 75,
       "staleAfterFailures": 3,
       "servidor": {"inactividadMinutos": 30, "maxEventosEnCache": 20, "workers": 0}}
DIA = {"id": 10, "name": "Day 1", "date": "2026-10-17T09:00:00+02:00"}
MAT = {"id": 1, "name": "Mat 1", "dayId": 10, "dayName": "Day 1", "dayDate": DIA["date"]}


def combate(mid, a="Ana Pérez", club_a="Gracie Madrid", b="Otro", club_b="Club B",
            estado="seeded"):
    return {
        "id": mid, "bracket_id": 7, "name": "Final", "round": 1,
        "group": "Men's GI / Black / Adults / 77KG", "state": estado, "match_nr": 1,
        "wonBy": None, "estimated_start": "2026-10-17T10:00:00+02:00",
        "seats": [
            {"type": "registration", "event_registration_id": mid * 10, "name": a,
             "club": club_a, "isWinner": False},
            {"type": "registration", "event_registration_id": mid * 10 + 1, "name": b,
             "club": club_b, "isWinner": False},
        ],
    }


def lectura(*combates, base="https://org.smoothcomp.com"):
    return Lectura([DIA], [MAT], {1: list(combates)}, base)


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class BuscadorFalso:
    def __init__(self, inexistentes=()):
        self.inexistentes = set(inexistentes)
        self.metas = {}

    def conocido(self, event_id):
        return self.metas.get(event_id)

    def evento(self, event_id):
        if event_id in self.inexistentes:
            raise ErrorOrigen("HTTP 404", codigo=404)
        return self.metas.setdefault(event_id, {
            "id": event_id, "title": f"Evento {event_id}",
            "baseUrl": "https://org.smoothcomp.com",
            "url": f"https://org.smoothcomp.com/es/event/{event_id}"})


class LectorFalso:
    """`respuestas`: id -> Lectura, excepción o función sin argumentos que devuelve una."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas = []

    def __call__(self, cfg, event_id, base_url=None, log=print):
        self.llamadas.append((event_id, base_url))
        respuesta = self.respuestas[event_id]
        if callable(respuesta):
            respuesta = respuesta()
        if isinstance(respuesta, BaseException):
            raise respuesta
        return respuesta


class PruebaAlmacen(unittest.TestCase):
    def montar(self, respuestas, inexistentes=(), cfg=None):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.reloj = Reloj()
        self.buscador = BuscadorFalso(inexistentes)
        self.grupos = Grupos(Path(carpeta.name) / "grupos.json")
        self.lector = LectorFalso(respuestas)
        self.avisos = []
        self.almacen = Almacen(cfg or CFG, self.buscador, self.grupos, leer=self.lector,
                               reloj=self.reloj, log=self.avisos.append, workers=0)
        return self.almacen

    def pedir_y_leer(self, ids="33588"):
        """Pide, deja que se lea lo encolado y vuelve a pedir."""
        self.almacen.pedir(ids)
        self.almacen.procesar_pendientes()
        return self.almacen.pedir(ids)

    @staticmethod
    def estado(respuesta):
        return json.loads(respuesta.cuerpo)


class TestIds(unittest.TestCase):
    def test_ids_validos(self):
        self.assertEqual(normalizar_ids("33588"), ("33588", ["33588"]))
        self.assertEqual(normalizar_ids(" 1535 , 1526 "), ("1535,1526", ["1535", "1526"]))
        self.assertEqual(normalizar_ids("7,7,007"), ("7", ["7"]), "sin duplicados ni ceros")
        self.assertEqual(normalizar_ids(33588), ("33588", ["33588"]))

    def test_ids_invalidos(self):
        for malo in ("", None, "abc", "1,,2", "1;2", "../etc", "12 34", "-5", "1234567890",
                     "1,2,3,4", "1/schedule", "1535,"):
            with self.assertRaises(ValueError, msg=repr(malo)):
                normalizar_ids(malo)


class TestPrimeraCarga(PruebaAlmacen):
    def test_la_primera_peticion_no_lee_y_contesta_cargando(self):
        self.montar({"33588": lectura(combate(1))})
        self.buscador.metas["33588"] = {"id": "33588", "title": "MADRID BJJ CUP"}
        r = self.almacen.pedir("33588")
        self.assertEqual(r.fase, "cargando")
        self.assertIsNone(r.cuerpo)
        self.assertEqual(r.eventos[0]["title"], "MADRID BJJ CUP", "se enseña lo que ya se sabe")
        self.assertEqual(self.lector.llamadas, [], "la petición nunca lee Smoothcomp")

    def test_despues_de_leer_se_sirve_el_estado(self):
        self.montar({"33588": lectura(combate(1))})
        r = self.pedir_y_leer()
        self.assertEqual(r.fase, "listo")
        estado = self.estado(r)
        self.assertEqual(len(estado["matches"]), 1)
        self.assertEqual({a["name"] for a in estado["athletes"]}, {"Ana Pérez", "Otro"})
        evento = estado["events"][0]
        self.assertEqual(evento["name"], "Evento 33588")
        self.assertTrue(evento["published"])
        self.assertEqual(evento["baseUrl"], "https://org.smoothcomp.com")
        self.assertEqual(estado["matches"][0]["bracketUrl"],
                         "https://org.smoothcomp.com/en/event/33588/bracket/7")

    def test_se_lee_en_la_base_que_conoce_el_buscador(self):
        self.montar({"33588": lectura(combate(1))})
        self.pedir_y_leer()
        self.assertEqual(self.lector.llamadas, [("33588", "https://org.smoothcomp.com")])

    def test_cuerpo_gzip_y_etag_coherentes(self):
        self.montar({"33588": lectura(combate(1))})
        r = self.pedir_y_leer()
        self.assertEqual(gzip.decompress(r.gz), r.cuerpo)
        self.assertRegex(r.etag, r'^"[0-9a-f]{20}"$')
        self.assertEqual(self.pedir_y_leer().etag, r.etag, "mismo contenido, mismo etag")

    def test_varias_peticiones_a_la_vez_son_una_sola_lectura(self):
        self.montar({"33588": lectura(combate(1))})
        for _ in range(20):
            self.almacen.pedir("33588")    # 20 móviles abriendo el evento
        self.almacen.procesar_pendientes()
        self.assertEqual(len(self.lector.llamadas), 1)


class TestRefresco(PruebaAlmacen):
    def test_dentro_del_ttl_no_se_vuelve_a_leer(self):
        self.montar({"33588": lectura(combate(1))})
        self.pedir_y_leer()
        self.reloj.t += 74
        self.almacen.pedir("33588")
        self.almacen.procesar_pendientes()
        self.assertEqual(len(self.lector.llamadas), 1)

    def test_pasado_el_ttl_sirve_lo_que_hay_y_refresca_en_segundo_plano(self):
        self.montar({"33588": lectura(combate(1, estado="seeded"))})
        antes = self.pedir_y_leer()
        self.lector.respuestas["33588"] = lectura(combate(1, estado="running"))

        self.reloj.t += 75
        durante = self.almacen.pedir("33588")
        self.assertEqual(durante.fase, "listo", "no se hace esperar a nadie")
        self.assertEqual(self.estado(durante)["matches"][0]["state"], "seeded")
        self.assertEqual(durante.etag, antes.etag)

        self.almacen.procesar_pendientes()
        despues = self.almacen.pedir("33588")
        self.assertEqual(self.estado(despues)["matches"][0]["state"], "running")
        self.assertNotEqual(despues.etag, antes.etag)
        self.assertEqual(len(self.lector.llamadas), 2)

    def test_un_evento_que_nadie_mira_se_olvida(self):
        self.montar({"33588": lectura(combate(1))})
        self.pedir_y_leer()
        self.reloj.t += 31 * 60
        r = self.almacen.pedir("33588")
        self.assertEqual(r.fase, "cargando", "empieza de cero")

    def test_mirar_el_evento_lo_mantiene_vivo(self):
        self.montar({"33588": lectura(combate(1))})
        self.pedir_y_leer()
        for _ in range(5):
            self.reloj.t += 20 * 60      # nunca pasan 30 min sin que alguien mire
            self.almacen.pedir("33588")
            self.almacen.procesar_pendientes()
        self.assertEqual(self.almacen.pedir("33588").fase, "listo")


class TestResultadosDeLaLectura(PruebaAlmacen):
    def test_schedule_no_publicado_es_un_evento_sin_combates(self):
        self.montar({"33588": ErrorOrigen("HTTP 403", codigo=403)})
        r = self.pedir_y_leer()
        self.assertEqual(r.fase, "listo")
        estado = self.estado(r)
        self.assertEqual(estado["matches"], [])
        self.assertFalse(estado["events"][0]["published"])
        self.assertEqual(estado["events"][0]["name"], "Evento 33588")

    def test_evento_inexistente(self):
        self.montar({"999": ErrorOrigen("HTTP 404", codigo=404)})
        r = self.pedir_y_leer("999")
        self.assertEqual(r.fase, "no_existe")
        self.assertIsNone(r.cuerpo)

    def test_inexistente_ya_en_los_datos_del_evento(self):
        # getCmsData ya dice 404: ni se intenta leer el schedule.
        self.montar({}, inexistentes=["999"])
        self.assertEqual(self.pedir_y_leer("999").fase, "no_existe")
        self.assertEqual(self.lector.llamadas, [])

    def test_un_inexistente_no_se_vuelve_a_preguntar_enseguida(self):
        self.montar({"999": ErrorOrigen("HTTP 404", codigo=404)})
        self.pedir_y_leer("999")
        self.reloj.t += 200
        self.almacen.pedir("999")
        self.almacen.procesar_pendientes()
        self.assertEqual(len(self.lector.llamadas), 1)
        self.reloj.t += 101
        self.almacen.pedir("999")
        self.almacen.procesar_pendientes()
        self.assertEqual(len(self.lector.llamadas), 2)

    def test_sin_datos_y_con_el_origen_caido_es_un_error_que_se_reintenta_pronto(self):
        self.montar({"33588": ErrorOrigen("HTTP 502 tras 3 intentos", codigo=502)})
        r = self.pedir_y_leer()
        self.assertEqual(r.fase, "error")
        self.assertIn("502", r.mensaje)

        self.lector.respuestas["33588"] = lectura(combate(1))
        self.reloj.t += 15
        self.almacen.pedir("33588")
        self.almacen.procesar_pendientes()
        self.assertEqual(self.almacen.pedir("33588").fase, "listo")

    def test_el_reto_de_cloudflare_se_cuenta_como_bloqueo_no_como_no_publicado(self):
        self.montar({"33588": ErrorOrigen("HTTP 403", codigo=403, desafio=True)})
        r = self.pedir_y_leer()
        self.assertEqual(r.fase, "error")
        self.assertIn("bloqueando", r.mensaje)

    def test_un_fallo_inesperado_no_mata_al_trabajador(self):
        self.montar({"33588": lambda: 1 / 0})
        r = self.pedir_y_leer()      # no debe propagar la excepción
        self.assertEqual(r.fase, "error")
        self.assertTrue(any("ZeroDivisionError" in a for a in self.avisos))
        self.assertTrue(any("Traceback" in a for a in self.avisos),
                        "sin el traceback no hay forma de saber dónde falló")

    def test_si_falla_el_titulo_se_avisa_y_se_lee_igualmente(self):
        self.montar({"33588": lectura(combate(1))})

        def sin_titulo(event_id):
            raise ErrorOrigen("HTTP 502", codigo=502)
        self.buscador.evento = sin_titulo
        r = self.pedir_y_leer()
        self.assertEqual(r.fase, "listo")
        self.assertTrue(any("sin título de 33588" in a for a in self.avisos))

    def test_una_vista_a_medias_deja_constancia_de_lo_que_no_se_pudo_leer(self):
        self.montar({"1535": lectura(combate(1)), "1526": ErrorOrigen("HTTP 502", codigo=502)})
        self.pedir_y_leer("1535,1526")
        self.assertTrue(any("lectura parcial: 1 de 2" in a for a in self.avisos), self.avisos)


class TestResumen(PruebaAlmacen):
    """Lo que enseña /api/health."""

    def test_vacio_no_hay_nada_que_vigilar(self):
        self.montar({})
        r = self.almacen.resumen()
        self.assertEqual((r["eventosEnCache"], r["enCola"], r["eventosStale"],
                          r["eventosConError"]), (0, 0, 0, 0))
        self.assertEqual((r["workers"], r["workersVivos"]), (0, 0))
        self.assertIsNone(r["origen"]["ultimoExitoS"])
        self.assertIsNone(r["origen"]["ultimoErrorCodigo"])

    def test_cuenta_la_cola_y_el_ultimo_exito(self):
        self.montar({"33588": lectura(combate(1))})
        self.almacen.pedir("33588")
        self.assertEqual(self.almacen.resumen()["enCola"], 1)

        self.almacen.procesar_pendientes()
        self.reloj.t += 40
        r = self.almacen.resumen()
        self.assertEqual((r["eventosEnCache"], r["enCola"]), (1, 0))
        self.assertEqual(r["origen"]["ultimoExitoS"], 40)

    def test_un_evento_sin_datos_que_servir_cuenta_como_error_y_guarda_el_codigo(self):
        self.montar({"33588": ErrorOrigen("HTTP 403", codigo=403, desafio=True)})
        self.pedir_y_leer()
        r = self.almacen.resumen()
        self.assertEqual(r["eventosConError"], 1)
        self.assertEqual((r["origen"]["ultimoErrorCodigo"], r["origen"]["ultimoErrorReto"]),
                         (403, True))
        self.assertEqual(r["origen"]["ultimoErrorS"], 0)

    def test_un_403_normal_no_es_un_fallo_de_origen(self):
        self.montar({"33588": ErrorOrigen("HTTP 403", codigo=403)})   # schedule sin publicar
        self.pedir_y_leer()
        r = self.almacen.resumen()
        self.assertEqual((r["eventosConError"], r["eventosStale"]), (0, 0))
        self.assertIsNone(r["origen"]["ultimoErrorCodigo"])

    def test_tras_varios_fallos_el_evento_cuenta_como_stale(self):
        self.montar({"33588": lectura(combate(1))})
        self.pedir_y_leer()
        self.lector.respuestas["33588"] = ErrorOrigen("HTTP 503", codigo=503)
        for _ in range(3):
            self.reloj.t += 75
            self.almacen.pedir("33588")
            self.almacen.procesar_pendientes()
        r = self.almacen.resumen()
        self.assertEqual((r["eventosStale"], r["eventosConError"]), (1, 0))

    def test_un_hilo_vivo_se_cuenta(self):
        self.montar({})
        hilo = threading.Event()
        vivo = threading.Thread(target=hilo.wait, daemon=True)
        vivo.start()
        self.addCleanup(hilo.set)
        self.almacen._hilos.append(vivo)
        r = self.almacen.resumen()
        self.assertEqual((r["workers"], r["workersVivos"]), (1, 1))


class TestStale(PruebaAlmacen):
    def fallar_y_pedir(self):
        self.reloj.t += 75
        self.almacen.pedir("33588")
        self.almacen.procesar_pendientes()
        return self.almacen.pedir("33588")

    def test_tras_varios_fallos_seguidos_se_marca_vieja_y_al_recuperarse_deja_de_estarlo(self):
        self.montar({"33588": lectura(combate(1))})
        self.pedir_y_leer()
        self.lector.respuestas["33588"] = ErrorOrigen("HTTP 503", codigo=503)

        for _ in range(2):    # staleAfterFailures = 3: aún no
            r = self.fallar_y_pedir()
            self.assertFalse(self.estado(r)["stale"])
            self.assertEqual(len(self.estado(r)["matches"]), 1, "sigue sirviendo lo último bueno")

        r = self.fallar_y_pedir()
        estado = self.estado(r)
        self.assertTrue(estado["stale"])
        self.assertIsNotNone(estado["staleSince"])
        self.assertEqual(len(estado["matches"]), 1)

        self.lector.respuestas["33588"] = lectura(combate(1), combate(2, a="Nueva"))
        r = self.fallar_y_pedir()
        self.assertFalse(self.estado(r)["stale"])
        self.assertEqual(len(self.estado(r)["matches"]), 2)

    def test_el_primer_fallo_se_recuerda_para_staleSince(self):
        self.montar({"33588": lectura(combate(1))})
        self.pedir_y_leer()
        self.lector.respuestas["33588"] = ErrorOrigen("HTTP 503", codigo=503)
        for _ in range(3):
            r = self.fallar_y_pedir()
        desde = self.estado(r)["staleSince"]
        r = self.fallar_y_pedir()
        self.assertEqual(self.estado(r)["staleSince"], desde)


class TestGrupo(PruebaAlmacen):
    def test_el_grupo_se_aplica_en_la_lectura(self):
        self.montar({"33588": lectura(combate(1))})
        self.grupos.actualizar("33588", "añadir", nombre="Ana Pérez", club="Gracie Madrid")
        estado = self.estado(self.pedir_y_leer())
        marcados = {a["name"] for a in estado["athletes"] if a["inGroup"]}
        self.assertEqual(marcados, {"Ana Pérez"})

    def test_regrupar_cambia_la_respuesta_sin_releer_smoothcomp(self):
        self.montar({"33588": lectura(combate(1))})
        antes = self.pedir_y_leer()
        self.assertFalse(any(a["inGroup"] for a in self.estado(antes)["athletes"]))

        self.grupos.actualizar("33588", "añadir", nombre="Otro", club="Club B")
        self.almacen.regrupar("33588")
        despues = self.almacen.pedir("33588")
        self.assertEqual({a["name"] for a in self.estado(despues)["athletes"] if a["inGroup"]},
                         {"Otro"})
        self.assertNotEqual(despues.etag, antes.etag)
        self.assertEqual(gzip.decompress(despues.gz), despues.cuerpo)
        self.assertEqual(len(self.lector.llamadas), 1, "ni una petición más a Smoothcomp")

    def test_regrupar_tambien_vale_con_la_copia_vieja(self):
        self.montar({"33588": lectura(combate(1))})
        self.pedir_y_leer()
        self.lector.respuestas["33588"] = ErrorOrigen("HTTP 503", codigo=503)
        for _ in range(3):
            self.reloj.t += 75
            self.almacen.pedir("33588")
            self.almacen.procesar_pendientes()
        self.grupos.actualizar("33588", "añadir", nombre="Ana Pérez")
        self.almacen.regrupar("33588")
        estado = self.estado(self.almacen.pedir("33588"))
        self.assertTrue(estado["stale"])
        self.assertTrue(any(a["inGroup"] for a in estado["athletes"]))

    def test_regrupar_un_evento_que_no_esta_cargado_no_hace_nada(self):
        self.montar({})
        self.almacen.regrupar("12345")   # no debe lanzar


class TestVariosEventos(PruebaAlmacen):
    def test_dos_eventos_combinados_unifican_al_atleta(self):
        self.montar({
            "1535": lectura(combate(1, a="Ana Pérez", club_a="Gracie")),
            "1526": lectura(combate(2, a="ana perez", club_a="gracie", b="Otra", club_b="C")),
        })
        estado = self.estado(self.pedir_y_leer("1535,1526"))
        anas = [a for a in estado["athletes"] if a["id"].startswith("ana perez|")]
        self.assertEqual(len(anas), 1)
        self.assertCountEqual(anas[0]["events"], ["1535", "1526"])
        self.assertEqual(len(estado["events"]), 2)

    def test_si_uno_no_esta_publicado_se_sirve_el_otro(self):
        self.montar({"1535": lectura(combate(1)), "1526": ErrorOrigen("HTTP 403", codigo=403)})
        estado = self.estado(self.pedir_y_leer("1535,1526"))
        publicados = {e["id"]: e["published"] for e in estado["events"]}
        self.assertEqual(publicados, {"1535": True, "1526": False})

    def test_si_uno_falla_de_verdad_se_sirve_el_otro_y_no_se_da_por_perdido(self):
        self.montar({"1535": lectura(combate(1)), "1526": ErrorOrigen("HTTP 502", codigo=502)})
        r = self.pedir_y_leer("1535,1526")
        self.assertEqual(r.fase, "listo")
        self.assertEqual(len(self.estado(r)["matches"]), 1)

    def test_la_vista_combinada_tiene_su_propia_entrada_y_su_propio_grupo(self):
        self.montar({"1535": lectura(combate(1)), "1526": lectura(combate(2))})
        self.grupos.actualizar("1535,1526", "añadir", nombre="Ana Pérez")
        solo = self.estado(self.pedir_y_leer("1535"))
        junto = self.estado(self.pedir_y_leer("1535,1526"))
        self.assertFalse(any(a["inGroup"] for a in solo["athletes"]))
        self.assertTrue(any(a["inGroup"] for a in junto["athletes"]))


class TestLimites(PruebaAlmacen):
    def test_se_echa_al_menos_reciente_cuando_esta_lleno(self):
        cfg = {**CFG, "servidor": {**CFG["servidor"], "maxEventosEnCache": 2}}
        self.montar({str(i): lectura(combate(i)) for i in (1, 2, 3)}, cfg=cfg)
        self.pedir_y_leer("1")
        self.pedir_y_leer("2")
        self.almacen.pedir("1")          # el 2 pasa a ser el menos reciente
        self.pedir_y_leer("3")
        self.assertEqual(self.almacen.pedir("2").fase, "cargando", "el 2 se echó")
        self.assertEqual(self.almacen.pedir("3").fase, "listo")

    def test_no_se_echa_a_quien_aun_se_esta_leyendo(self):
        cfg = {**CFG, "servidor": {**CFG["servidor"], "maxEventosEnCache": 2}}
        self.montar({str(i): lectura(combate(i)) for i in (1, 2, 3)}, cfg=cfg)
        self.almacen.pedir("1")
        self.almacen.pedir("2")          # ambos en cola, ninguno leído
        with self.assertRaises(Saturado):
            self.almacen.pedir("3")

    def test_tope_de_lecturas_pendientes(self):
        self.montar({})
        for i in range(modulo_almacen.MAX_PENDIENTES):
            self.almacen.pedir(str(i + 1))
        with self.assertRaises(Saturado):
            self.almacen.pedir("999")    # alguien sondeando ids no puede inundar la cola
        self.assertEqual(self.almacen.pedir("1").fase, "cargando", "los ya pedidos siguen")

    def test_ids_invalidos_no_crean_entradas(self):
        self.montar({})
        with self.assertRaises(ValueError):
            self.almacen.pedir("../../x")
        self.assertEqual(len(self.almacen._entradas), 0)


if __name__ == "__main__":
    unittest.main()
