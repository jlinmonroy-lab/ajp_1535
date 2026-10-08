"""
Pruebas del panel local y del estado que se publica antes del schedule.

Antes de que el organizador publique el schedule no hay ningún atleta en los
datos, así que la lista del grupo se apunta a mano (nombre y club) y la web
tiene que publicarse igualmente, vacía, para dejar de enseñar el torneo anterior.

Uso:  python -m unittest discover -s tests
"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper import panel  # noqa: E402
from scraper.main import estado_vacio  # noqa: E402


class TestAltaManual(unittest.TestCase):
    """El panel de verdad, en un puerto libre y contra un config.json temporal."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / "config.json"
        self.config.write_text(json.dumps({"grupo": {"nombre": "Equipo", "atletas": []}}),
                               encoding="utf-8")
        self.parche = mock.patch.object(panel, "CONFIG", self.config)
        self.parche.start()
        self.servidor = panel.crear_servidor(0)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}/api/grupo"

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.parche.stop()
        self.tmp.cleanup()

    def _post(self, cuerpo):
        req = urllib.request.Request(self.url, data=json.dumps(cuerpo).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))

    def test_alta_con_club_usa_la_identidad_del_scraper(self):
        grupo = self._post({"name": "Lucía Muelas", "club": "Mathias Ribeiro Team"})
        self.assertEqual(grupo["atletas"], [{"id": "lucia muelas|mathias ribeiro team",
                                             "name": "Lucía Muelas",
                                             "club": "Mathias Ribeiro Team"}])

    def test_alta_sin_club_deja_solo_el_nombre(self):
        grupo = self._post({"name": "Víctor Pérez", "club": ""})
        self.assertEqual(grupo["atletas"], [{"id": "victor perez|", "name": "Víctor Pérez"}])
        guardado = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(guardado["grupo"]["atletas"], grupo["atletas"])

    def test_quitar_desde_la_ficha_borra_el_alta_sin_club(self):
        # La ficha manda el id completo; el alta se hizo sin club.
        self._post({"name": "Víctor Pérez"})
        grupo = self._post({"id": "victor perez|mathias ribeiro team",
                            "name": "Víctor Pérez", "accion": "quitar"})
        self.assertEqual(grupo["atletas"], [])

    def test_sin_id_ni_nombre_es_un_error(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post({"club": "Club"})
        self.assertEqual(ctx.exception.code, 400)
        ctx.exception.close()


class TestEstadoVacio(unittest.TestCase):
    def test_anuncia_el_evento_y_el_grupo_sin_combates(self):
        cfg = {"events": [{"id": "33588", "label": None, "name": "Torneo"}],
               "baseUrl": "https://ejemplo.smoothcomp.com",
               "grupo": {"nombre": "Equipo",
                         "atletas": [{"id": "ana perez|", "name": "Ana Pérez"}]}}
        estado = estado_vacio(cfg)
        self.assertEqual([e["id"] for e in estado["events"]], ["33588"])
        self.assertEqual(estado["matches"], [])
        self.assertEqual(estado["athletes"], [])
        self.assertEqual(estado["group"]["athletes"][0]["name"], "Ana Pérez")
        self.assertFalse(estado["stale"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
