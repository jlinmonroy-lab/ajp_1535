"""
Pruebas del lanzador del día del torneo (lo que no necesita Windows ni red).

Uso:  python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import arrancar_evento  # noqa: E402
from scraper import servidor  # noqa: E402


class TestPuertoDe(unittest.TestCase):
    def test_por_defecto_es_el_del_servidor(self):
        self.assertEqual(arrancar_evento.puerto_de([]), servidor.PUERTO_POR_DEFECTO)
        self.assertEqual(arrancar_evento.puerto_de(["--host", "0.0.0.0"]),
                         servidor.PUERTO_POR_DEFECTO)

    def test_las_dos_formas_de_pasarlo(self):
        self.assertEqual(arrancar_evento.puerto_de(["--puerto", "9000"]), 9000)
        self.assertEqual(arrancar_evento.puerto_de(["--host", "0.0.0.0", "--puerto=9100"]), 9100)

    def test_un_valor_roto_no_tumba_el_lanzador(self):
        for opciones in (["--puerto"], ["--puerto", "abc"], ["--puerto="], ["--puerto=x"]):
            self.assertEqual(arrancar_evento.puerto_de(opciones), servidor.PUERTO_POR_DEFECTO,
                             opciones)


class TestCodigoDeSalida(unittest.TestCase):
    def test_el_lanzador_y_el_servidor_hablan_del_mismo_codigo(self):
        # Si divergieran, el lanzador relanzaría cada 10 s un servidor que no puede
        # arrancar (puerto ocupado, config rota) en vez de rendirse.
        self.assertEqual(arrancar_evento.SALIDA_NO_ARRANCA, servidor.SALIDA_NO_ARRANCA)
        self.assertNotEqual(servidor.SALIDA_NO_ARRANCA, 1, "1 es lo que da una excepción")


if __name__ == "__main__":
    unittest.main()
