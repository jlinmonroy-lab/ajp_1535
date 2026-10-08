"""
Pruebas de la lista del grupo guardada en el servidor.

Uso:  python -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.grupos import MAX_ATLETAS, Grupos  # noqa: E402


class PruebaGrupos(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.ruta = Path(carpeta.name) / "data" / "grupos.json"   # la carpeta aún no existe
        self.grupos = Grupos(self.ruta)


class TestLeer(PruebaGrupos):
    def test_sin_fichero_la_lista_esta_vacia(self):
        g = self.grupos.leer("33588")
        self.assertEqual(g, {"nombre": "Nuestro equipo", "atletas": []})

    def test_un_fichero_roto_no_tumba_nada(self):
        self.ruta.parent.mkdir(parents=True)
        self.ruta.write_text("{esto no es json", encoding="utf-8")
        self.assertEqual(self.grupos.leer("1")["atletas"], [])
        # y se puede seguir escribiendo encima
        self.grupos.actualizar("1", "añadir", nombre="Ana")
        self.assertEqual(len(self.grupos.leer("1")["atletas"]), 1)


class TestActualizar(PruebaGrupos):
    def test_alta_a_mano_calcula_el_id_como_el_scraper(self):
        g = self.grupos.actualizar("33588", "añadir", nombre="Ana Pérez", club="Gracie Madrid")
        self.assertEqual(g["atletas"], [
            {"id": "ana perez|gracie madrid", "name": "Ana Pérez", "club": "Gracie Madrid"}])

    def test_alta_sin_club_casa_con_cualquier_club(self):
        g = self.grupos.actualizar("33588", "añadir", nombre="Ana Pérez")
        self.assertEqual(g["atletas"][0]["id"], "ana perez|")
        self.assertNotIn("club", g["atletas"][0])

    def test_alta_con_id_de_la_ficha(self):
        g = self.grupos.actualizar("33588", "añadir", atleta_id="ana perez|gracie madrid",
                                   nombre="Ana Pérez")
        self.assertEqual(g["atletas"][0]["id"], "ana perez|gracie madrid")

    def test_no_se_duplica_y_queda_ordenada_por_nombre(self):
        self.grupos.actualizar("1", "añadir", nombre="Zoe")
        self.grupos.actualizar("1", "añadir", nombre="ana")
        g = self.grupos.actualizar("1", "añadir", nombre="Zoe")
        self.assertEqual([a["name"] for a in g["atletas"]], ["ana", "Zoe"])

    def test_quitar_con_el_id_completo_tambien_quita_el_alta_sin_club(self):
        self.grupos.actualizar("1", "añadir", nombre="Ana Pérez")           # "ana perez|"
        g = self.grupos.actualizar("1", "quitar", atleta_id="ana perez|gracie madrid")
        self.assertEqual(g["atletas"], [])

    def test_quitar_a_quien_no_esta_no_hace_nada(self):
        self.grupos.actualizar("1", "añadir", nombre="Ana")
        g = self.grupos.actualizar("1", "quitar", atleta_id="otro|club")
        self.assertEqual(len(g["atletas"]), 1)

    def test_cada_vista_tiene_su_lista(self):
        self.grupos.actualizar("33588", "añadir", nombre="Ana")
        self.assertEqual(self.grupos.leer("26416")["atletas"], [])
        self.assertEqual(self.grupos.leer("1535,1526")["atletas"], [])

    def test_persiste_en_el_fichero(self):
        self.grupos.actualizar("33588", "añadir", nombre="Ana")
        otra = Grupos(self.ruta)    # como tras reiniciar el servidor
        self.assertEqual(otra.leer("33588")["atletas"][0]["name"], "Ana")
        self.assertIn("33588", json.loads(self.ruta.read_text(encoding="utf-8")))

    def test_peticiones_invalidas(self):
        for args, kwargs in (
            (("1", "borrar"), {"nombre": "Ana"}),            # acción desconocida
            (("1", "añadir"), {}),                            # ni id ni nombre
            (("1", "añadir"), {"nombre": "x" * 201}),         # demasiado largo
            (("1", "añadir"), {"nombre": "Ana", "club": "c" * 201}),
        ):
            with self.assertRaises(ValueError, msg=(args, kwargs)):
                self.grupos.actualizar(*args, **kwargs)
        self.assertFalse(self.ruta.exists(), "una petición inválida no escribe nada")

    def test_la_lista_tiene_tope(self):
        for i in range(MAX_ATLETAS):
            self.grupos.actualizar("1", "añadir", atleta_id=f"id{i}|", nombre=f"N{i}")
        with self.assertRaises(ValueError):
            self.grupos.actualizar("1", "añadir", nombre="uno más")
        # quitar sigue funcionando con la lista llena
        self.assertEqual(len(self.grupos.actualizar("1", "quitar", atleta_id="id0|")["atletas"]),
                         MAX_ATLETAS - 1)


if __name__ == "__main__":
    unittest.main()
