"""
Pruebas del registro y los contadores (scraper/telemetria.py).

Uso:  python -m unittest discover -s tests
"""
import contextlib
import io
import json
import logging
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper import telemetria  # noqa: E402
from scraper.telemetria import Contadores, Limitador, Registro, configurar_logging, nivel  # noqa: E402


class PruebaConfiguracion(unittest.TestCase):
    """`configurar_logging` toca el logger global: se deja como estaba al acabar."""

    def setUp(self):
        logger = logging.getLogger(telemetria.NOMBRE)
        antes = (list(logger.handlers), logger.level, logger.propagate)
        self.addCleanup(self._restaurar, logger, antes)

    @staticmethod
    def _restaurar(logger, antes):
        for h in list(logger.handlers):
            logger.removeHandler(h)
            h.close()
        for h in antes[0]:
            logger.addHandler(h)
        logger.setLevel(antes[1])
        logger.propagate = antes[2]

    def carpeta(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        # Se ejecuta antes que el rmtree: en Windows no se borra un fichero abierto.
        self.addCleanup(configurar_logging, {})
        return Path(d)

    def escribir(self, entorno, accion):
        configurar_logging(entorno)
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            accion(Registro())
        return salida.getvalue()


class TestFormato(PruebaConfiguracion):
    def test_cada_linea_lleva_fecha_y_nivel(self):
        salida = self.escribir({}, lambda r: (r("hola"), r.aviso("cuidado"), r.error("mal")))
        lineas = salida.splitlines()
        self.assertEqual(len(lineas), 3)
        self.assertRegex(lineas[0], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d INFO    hola$")
        self.assertRegex(lineas[1], r" WARNING cuidado$")
        self.assertRegex(lineas[2], r" ERROR   mal$")

    def test_el_nivel_se_elige_por_entorno(self):
        salida = self.escribir({"LOG_LEVEL": "warning"},
                               lambda r: (r("no"), r.depurar("no"), r.aviso("sí")))
        self.assertEqual(len(salida.splitlines()), 1)
        self.assertIn("sí", salida)

        salida = self.escribir({"LOG_LEVEL": "DEBUG"}, lambda r: r.depurar("detalle"))
        self.assertIn("DEBUG", salida)

    def test_un_nivel_desconocido_no_impide_arrancar(self):
        salida = self.escribir({"LOG_LEVEL": "ruidoso"}, lambda r: r("hola"))
        self.assertIn("hola", salida)

    def test_formato_json(self):
        salida = self.escribir({"LOG_FORMAT": "json"}, lambda r: r.aviso("ñandú\ncon salto"))
        linea = json.loads(salida)
        self.assertEqual((linea["nivel"], linea["msg"]), ("WARNING", "ñandú\ncon salto"))
        self.assertRegex(linea["t"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")

    def test_escribe_en_el_stdout_de_cada_momento(self):
        # Quien capture la salida después de configurar (como hacen las pruebas) la ve.
        configurar_logging({})
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            Registro()("capturado")
        self.assertIn("capturado", salida.getvalue())

    def test_reconfigurar_no_duplica_las_lineas(self):
        configurar_logging({})
        salida = self.escribir({}, lambda r: r("una vez"))
        self.assertEqual(salida.count("una vez"), 1)


class TestFichero(PruebaConfiguracion):
    def test_ademas_de_la_consola_escribe_en_un_fichero_creando_la_carpeta(self):
        ruta = self.carpeta() / "registro" / "servidor.log"
        salida = self.escribir({"LOG_FILE": str(ruta)}, lambda r: r.aviso("a disco"))
        self.assertIn("a disco", salida)
        self.assertIn("a disco", ruta.read_text(encoding="utf-8"))

    def test_un_fichero_imposible_no_impide_arrancar(self):
        ocupado = self.carpeta() / "es_un_fichero"
        ocupado.write_text("x", encoding="utf-8")
        # La "carpeta" del registro es en realidad un fichero: no se puede crear.
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            configurar_logging({"LOG_FILE": str(ocupado / "servidor.log")})
            Registro()("sigue")
        self.assertIn("no se puede escribir el registro", salida.getvalue())
        self.assertIn("sigue", salida.getvalue())

    def test_rota_al_pasar_del_limite(self):
        ruta = self.carpeta() / "servidor.log"
        with mock.patch.object(telemetria, "FICHERO_MAX_BYTES", 300):
            self.escribir({"LOG_FILE": str(ruta)},
                          lambda r: [r(f"línea {i} " + "x" * 40) for i in range(30)])
        self.assertTrue(ruta.with_name("servidor.log.1").exists())


class TestNivel(unittest.TestCase):
    def test_con_un_registro_usa_el_metodo_del_nivel(self):
        registro = Registro(logging.getLogger("prueba.nivel"))
        with self.assertLogs("prueba.nivel", level="WARNING") as capturado:
            nivel(registro, "aviso")("cuidado")
        self.assertEqual(capturado.output, ["WARNING:prueba.nivel:cuidado"])

    def test_con_una_funcion_suelta_usa_la_propia_funcion(self):
        # Así se inyecta en las pruebas: `lista.append` o `lambda *_: None`.
        recogidos = []
        nivel(recogidos.append, "aviso")("cuidado")
        nivel(recogidos.append, "error")("mal")
        self.assertEqual(recogidos, ["cuidado", "mal"])
        self.assertIs(nivel(print, "aviso"), print)


class TestLimitador(unittest.TestCase):
    def limitador(self, capacidad=3, ventana=60):
        self.t = 0.0
        return Limitador(capacidad, ventana, reloj=lambda: self.t)

    def test_deja_pasar_hasta_su_capacidad_y_luego_no(self):
        l = self.limitador(3)
        self.assertEqual([l.permitir() for _ in range(5)], [True, True, True, False, False])

    def test_repone_con_el_tiempo(self):
        l = self.limitador(3, 60)          # una ficha cada 20 s
        for _ in range(3):
            l.permitir()
        self.t += 19
        self.assertFalse(l.permitir())
        self.t += 1
        self.assertTrue(l.permitir())
        self.assertFalse(l.permitir())

    def test_no_acumula_mas_que_su_capacidad(self):
        l = self.limitador(3)
        self.t += 3600
        self.assertEqual([l.permitir() for _ in range(5)], [True, True, True, False, False])

    def test_es_seguro_entre_hilos(self):
        l = self.limitador(50)
        permitidos = []

        def pedir():
            permitidos.extend(l.permitir() for _ in range(100))
        hilos = [threading.Thread(target=pedir) for _ in range(8)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(sum(permitidos), 50)


class TestContadores(unittest.TestCase):
    def test_suma_y_devuelve_una_copia(self):
        c = Contadores()
        c.sumar("a")
        c.sumar("a", 2)
        c.sumar("b")
        copia = c.todos()
        copia["a"] = 99
        self.assertEqual(c.todos(), {"a": 3, "b": 1})

    def test_es_seguro_entre_hilos(self):
        c = Contadores()

        def trabajar():
            for _ in range(2000):
                c.sumar("n")
        hilos = [threading.Thread(target=trabajar) for _ in range(8)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(c.todos()["n"], 16000)


if __name__ == "__main__":
    unittest.main()
