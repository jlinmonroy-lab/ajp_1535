"""
Pruebas de lo que comparten quienes sirven la web compilada (scraper/sitio.py).

Uso:  python -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper import panel, sitio  # noqa: E402


class TestSitioCompilado(unittest.TestCase):
    def test_basta_con_la_pagina_de_entrada(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            self.assertFalse(sitio.sitio_compilado(carpeta))
            (carpeta / "assets").mkdir()
            self.assertFalse(sitio.sitio_compilado(carpeta), "una carpeta sin index.html no es una web")
            (carpeta / "index.html").write_text("<h1>web</h1>", encoding="utf-8")
            self.assertTrue(sitio.sitio_compilado(carpeta))

    def test_el_aviso_dice_donde_falta_y_como_compilarla(self):
        aviso = sitio.aviso_sin_compilar(Path("site"))
        self.assertIn("index.html", aviso)
        self.assertIn("npm --prefix web run build", aviso)


class TestTiposMime(unittest.TestCase):
    def test_javascript_y_css_estan_fijados(self):
        self.assertTrue(sitio.TIPOS_MIME[".js"].startswith("text/javascript"))
        self.assertTrue(sitio.TIPOS_MIME[".mjs"].startswith("text/javascript"))
        self.assertTrue(sitio.TIPOS_MIME[".css"].startswith("text/css"))

    def test_el_panel_tambien_los_usa(self):
        # El panel local sirve la misma web: no puede quedarse con el tipo del registro.
        self.assertEqual(panel.Handler.extensions_map[".js"], sitio.TIPOS_MIME[".js"])
        self.assertNotEqual(SimpleHTTPRequestHandler.extensions_map.get(".js"), sitio.TIPOS_MIME[".js"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
