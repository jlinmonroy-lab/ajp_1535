"""
Pruebas de los estados que se fabrican sin leer el schedule (scraper/estado.py).

`fetchedAt` es lo que hace verdadero el «Actualizado hace X» de la web: si dejara de ser una
fecha UTC válida, o `marcar_stale` lo renovara, la web enseñaría datos viejos como frescos.

Uso:  python -m unittest discover -s tests
"""
import copy
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.estado import ahora_iso, estado_vacio, marcar_stale  # noqa: E402

ISO_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


class TestAhoraIso(unittest.TestCase):
    def test_es_iso_8601_en_utc_con_z_y_sin_fracciones(self):
        self.assertRegex(ahora_iso(), ISO_UTC)

    def test_es_la_hora_actual_en_utc(self):
        antes = datetime.now(timezone.utc).replace(microsecond=0)
        marca = datetime.fromisoformat(ahora_iso().replace("Z", "+00:00"))
        despues = datetime.now(timezone.utc)
        self.assertLessEqual(antes, marca)
        self.assertLessEqual(marca, despues)

    def test_lo_entiende_el_navegador(self):
        # `new Date("2026-09-20T12:00:00Z")` es válido; sin la Z se leería como hora local.
        self.assertTrue(ahora_iso().endswith("Z"))
        self.assertNotIn("+", ahora_iso())


class TestEstadoVacio(unittest.TestCase):
    def test_lleva_fecha_y_no_es_viejo(self):
        estado = estado_vacio([{"id": "1", "label": None, "name": "A"}],
                              base_url="https://smoothcomp.com")
        self.assertRegex(estado["fetchedAt"], ISO_UTC)
        self.assertFalse(estado["stale"])
        self.assertIsNone(estado["staleSince"])


class TestMarcarStale(unittest.TestCase):
    ESTADO = {"events": [], "fetchedAt": "2026-09-20T12:00:00Z", "stale": False,
              "staleSince": None, "matches": [{"id": "1"}], "athletes": []}

    def test_conserva_la_fecha_original_porque_la_edad_que_ve_el_usuario_depende_de_ella(self):
        viejo = marcar_stale(self.ESTADO, "2026-09-20T12:05:00Z")
        self.assertEqual(viejo["fetchedAt"], "2026-09-20T12:00:00Z")
        self.assertTrue(viejo["stale"])
        self.assertEqual(viejo["staleSince"], "2026-09-20T12:05:00Z")
        self.assertEqual(viejo["matches"], [{"id": "1"}])

    def test_no_toca_el_estado_original(self):
        original = copy.deepcopy(self.ESTADO)
        marcar_stale(self.ESTADO, "2026-09-20T12:05:00Z")
        self.assertEqual(self.ESTADO, original)
        self.assertFalse(self.ESTADO["stale"])


if __name__ == "__main__":
    unittest.main()
