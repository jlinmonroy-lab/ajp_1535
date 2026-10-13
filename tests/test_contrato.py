"""
El contrato entre lo que emite Python y lo que espera la web.

La muestra versionada (`web/src/pruebas/estado.contrato.json`) es lo único que leen las dos
mitades: aquí se comprueba que sigue siendo lo que hoy emite `construir_estado`, y en
`web/src/app/contrato.test.ts` que cumple los tipos de la web. Ver tests/contrato.py.

Uso:  python -m unittest discover -s tests
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contrato import COMANDO, DESTINO, muestra, texto  # noqa: E402
from test_fixtures_anonimos import NOMBRE_ANON  # noqa: E402

MAX_BYTES = 40 * 1024
ISO_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


class TestContrato(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Lo que hoy emite Python, pasado por JSON como lo verá la web.
        cls.actual = json.loads(texto(muestra()))

    def test_la_muestra_versionada_es_lo_que_emite_python(self):
        self.assertTrue(DESTINO.exists(), f"Falta {DESTINO.name}. Genérala con:  {COMANDO}")
        versionada = json.loads(DESTINO.read_text(encoding="utf-8"))
        if versionada != self.actual:
            distintas = sorted(k for k in set(versionada) | set(self.actual)
                               if versionada.get(k) != self.actual.get(k))
            self.fail(
                f"{DESTINO.name} ya no es lo que emite construir_estado (cambian: "
                f"{', '.join(distintas)}).\n"
                f"Si el cambio es intencionado, regenera la muestra con:  {COMANDO}\n"
                f"y revisa web/src/tipos.ts: web/src/app/contrato.test.ts dirá si la web lo soporta.")

    def test_pesa_poco_para_poder_versionarla(self):
        self.assertLess(DESTINO.stat().st_size, MAX_BYTES)

    def test_cubre_lo_que_la_web_pinta(self):
        estado = self.actual
        self.assertEqual({m["medal"] for a in estado["athletes"] for m in a["medals"]},
                         {"gold", "silver", "bronze"})
        self.assertGreaterEqual(len(estado["events"]), 2, "una vista de dos eventos")
        self.assertGreater(len({c["state"] for c in estado["matches"]}), 1,
                           "combates en más de un estado")
        self.assertTrue(any(a["inGroup"] for a in estado["athletes"]))
        self.assertTrue(any(not a["inGroup"] for a in estado["athletes"]))
        self.assertTrue(estado["streams"])
        self.assertGreaterEqual(len(estado["group"]["athletes"]), 2)
        self.assertFalse(estado["stale"])

    def test_fetchedAt_es_iso_8601_utc(self):
        self.assertRegex(self.actual["fetchedAt"], ISO_UTC)

    def test_no_lleva_datos_personales(self):
        # El repositorio es público: la muestra sale de las fixtures anonimizadas.
        nombres = {a["name"] for a in self.actual["athletes"]}
        nombres |= {s["name"] for c in self.actual["matches"] for s in c["sides"]}
        nombres |= {a["name"] for a in self.actual["group"]["athletes"]}
        for nombre in nombres:
            self.assertRegex(nombre, NOMBRE_ANON)


if __name__ == "__main__":
    unittest.main()
