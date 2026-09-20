"""
Pruebas del parser contra la captura real del evento 1257 (fixtures/event_1257/).

Sin red: todo sale de disco, así que se pueden ejecutar siempre.

Uso:  python -m unittest discover -s tests -v
"""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.parse import (  # noqa: E402
    construir_estado, derivar_medallas, parse_categoria,
)

FIXTURE = RAIZ / "fixtures" / "event_1257"


def cargar_fixture():
    dias = json.loads((FIXTURE / "days.json").read_text(encoding="utf-8"))
    mats = []
    for d in dias:
        mats += json.loads(
            (FIXTURE / f"mats_{d['id']}.json").read_text(encoding="utf-8"))
    combates_por_mat = {
        m["id"]: json.loads(
            (FIXTURE / f"matches_{m['id']}.json").read_text(encoding="utf-8"))
        for m in mats
    }
    return dias, mats, combates_por_mat


class TestCategoria(unittest.TestCase):
    def test_formato_ajp_completo(self):
        c = parse_categoria("Men's GI / Brown / Master 1 / 62KG")
        self.assertEqual(c["division"], "Men's GI")
        self.assertEqual(c["belt"], "Brown")
        self.assertEqual(c["ageGroup"], "Master 1")
        self.assertEqual(c["weight"], "62KG")
        self.assertTrue(c["gi"])

    def test_no_gi_no_se_confunde_con_gi(self):
        # "NO-GI" contiene "GI": es el caso que más fácil se clasifica mal.
        self.assertFalse(parse_categoria("Men's NO-GI / Black / Adults / 77KG")["gi"])
        self.assertFalse(parse_categoria("Women's NOGI / Blue / Adults / 70KG")["gi"])

    def test_cinturon_combinado(self):
        # Aparece de verdad en el evento 1257 y rompía el parseo de cuatro partes.
        c = parse_categoria("Women's GI / Brown / Black / Master 1 / 49KG")
        self.assertEqual(c["division"], "Women's GI")
        self.assertEqual(c["belt"], "Brown / Black")
        self.assertEqual(c["ageGroup"], "Master 1")
        self.assertEqual(c["weight"], "49KG")

    def test_formato_inesperado_conserva_el_texto(self):
        c = parse_categoria("Algo sin barras")
        self.assertEqual(c["raw"], "Algo sin barras")
        self.assertIsNone(c["division"])
        self.assertIsNone(c["gi"])

    def test_vacio(self):
        self.assertIsNone(parse_categoria(None)["raw"])


class TestEventoReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            raise unittest.SkipTest(
                "Falta fixtures/event_1257: ejecuta research/capture_event.py 1257")
        dias, mats, combates = cargar_fixture()
        cls.estado = construir_estado(
            evento={"id": "1257", "name": "AJP evento de prueba"},
            dias=dias, mats=mats, combates_por_mat=combates,
            fetched_at="2026-09-20T12:00:00Z",
        )

    def test_totales(self):
        self.assertEqual(len(self.estado["mats"]), 9)
        self.assertEqual(len(self.estado["matches"]), 443)

    def test_sin_combates_duplicados(self):
        ids = [m["id"] for m in self.estado["matches"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_todo_combate_tiene_tatami_y_hora(self):
        for m in self.estado["matches"]:
            self.assertIsNotNone(m["mat"], f"combate {m['id']} sin tatami")
            self.assertIsNotNone(m["estimatedStart"], f"combate {m['id']} sin hora")

    def test_orden_cronologico(self):
        horas = [m["estimatedStart"] for m in self.estado["matches"]]
        self.assertEqual(horas, sorted(horas))

    def test_dos_atletas_por_combate(self):
        # En el 1257 todos los seats son 'registration'; si apareciera una plaza
        # pendiente ("Loser from 1-91") se descartaría y este número bajaría.
        for m in self.estado["matches"]:
            self.assertEqual(len(m["sides"]), 2, f"combate {m['id']}")

    def test_atletas_y_sus_combates(self):
        atletas = self.estado["athletes"]
        self.assertGreater(len(atletas), 100)
        por_id = {a["registrationId"]: a for a in atletas}
        ids_combate = {m["id"] for m in self.estado["matches"]}
        for a in atletas:
            self.assertTrue(a["matchIds"], f"atleta {a['name']} sin combates")
            for mid in a["matchIds"]:
                self.assertIn(mid, ids_combate)
        # Coherencia inversa: cada lado de cada combate existe como atleta.
        for m in self.estado["matches"]:
            for lado in m["sides"]:
                self.assertIn(lado["registrationId"], por_id)

    def test_medallas(self):
        medallas = derivar_medallas(self.estado["matches"])
        self.assertTrue(medallas)
        reparto = {}
        for entradas in medallas.values():
            for e in entradas:
                reparto[e["medal"]] = reparto.get(e["medal"], 0) + 1
        # El 1257 tiene 85 categorías, 82 finales y 74 combates por el bronce.
        self.assertEqual(reparto.get("gold"), reparto.get("silver"))
        self.assertGreaterEqual(reparto.get("gold", 0), 82)
        self.assertEqual(reparto.get("bronze"), 74)

    def test_una_medalla_por_atleta_y_categoria(self):
        # Un atleta puede competir en varias categorías y tener una medalla en
        # cada una, pero nunca dos en el mismo bracket.
        medallas = derivar_medallas(self.estado["matches"])
        for entradas in medallas.values():
            brackets = [e["bracketId"] for e in entradas]
            self.assertEqual(len(brackets), len(set(brackets)))

    def test_bracket_de_tres_no_da_dos_medallas_al_campeon(self):
        # En los brackets de tres, el "Bronze match" es otra ronda del
        # todos-contra-todos y lo puede ganar el campeón. El bronce debe ir
        # entonces al tercero, no duplicar medalla en el mismo bracket.
        medallas = derivar_medallas(self.estado["matches"])
        bronces = [m for m in self.estado["matches"]
                   if (m["round"] or "").lower() == "bronze match"]
        for bronce in bronces:
            implicados = [l["registrationId"] for l in bronce["sides"]]
            con_bronce = [
                rid for rid in implicados
                if any(e["bracketId"] == bronce["bracketId"] and e["medal"] == "bronze"
                       for e in medallas.get(rid, []))]
            self.assertEqual(len(con_bronce), 1,
                             f"bracket {bronce['bracketId']}: {len(con_bronce)} bronces")

    def test_el_oro_gano_su_final(self):
        finales = [m for m in self.estado["matches"]
                   if (m["round"] or "").lower() == "final"]
        self.assertTrue(finales)
        medallas = derivar_medallas(self.estado["matches"])
        for final in finales:
            for lado in final["sides"]:
                esperado = "gold" if lado["isWinner"] else "silver"
                entrada = next(e for e in medallas[lado["registrationId"]]
                               if e["bracketId"] == final["bracketId"])
                self.assertEqual(entrada["medal"], esperado)

    def test_mejor_medalla_resume_las_varias(self):
        for a in self.estado["athletes"]:
            if a["medals"]:
                self.assertIn(a["bestMedal"], {"gold", "silver", "bronze"})
                self.assertIn(a["bestMedal"], {m["medal"] for m in a["medals"]})
            else:
                self.assertIsNone(a["bestMedal"])

    def test_categorias_parseadas(self):
        # Las 85 categorías del 1257 siguen el formato de cuatro partes.
        for m in self.estado["matches"]:
            self.assertIsNotNone(m["category"]["division"], m["category"]["raw"])
            self.assertIsNotNone(m["category"]["weight"], m["category"]["raw"])
            self.assertIsNotNone(m["category"]["gi"], m["category"]["raw"])


class TestDeduplicacion(unittest.TestCase):
    def test_un_combate_en_dos_tatamis_se_cuenta_una_vez(self):
        # Pasa de verdad: un combate movido de tatami mientras se lee el schedule
        # aparece en las dos listas.
        crudo = {"id": 1, "bracket_id": 9, "name": "Final", "group": "A / B / C / 1KG",
                 "round": 1, "state": "finished", "match_nr": 1, "wonBy": "points",
                 "estimated_start": "2025-01-01T10:00:00+00:00",
                 "seats": [
                     {"type": "registration", "event_registration_id": 11,
                      "name": "Uno", "isWinner": True},
                     {"type": "registration", "event_registration_id": 22,
                      "name": "Dos", "isWinner": False}]}
        estado = construir_estado(
            evento={"id": "x", "name": "x"}, dias=[],
            mats=[{"id": 1, "name": "Mat 1"}, {"id": 2, "name": "Mat 2"}],
            combates_por_mat={1: [crudo], 2: [crudo]},
            fetched_at="2026-01-01T00:00:00Z")
        self.assertEqual(len(estado["matches"]), 1)
        self.assertEqual(len(estado["athletes"]), 2)

    def test_plazas_pendientes_no_son_atletas(self):
        crudo = {"id": 2, "bracket_id": 9, "name": "Semifinals",
                 "group": "A / B / C / 1KG", "round": 1, "state": "seeded",
                 "match_nr": 1, "wonBy": None, "estimated_start": None,
                 "seats": [
                     {"type": "registration", "event_registration_id": 11,
                      "name": "Uno", "isWinner": False},
                     {"type": "winner", "name": "Winner from 1-2"}]}
        estado = construir_estado(
            evento={"id": "x", "name": "x"}, dias=[],
            mats=[{"id": 1, "name": "Mat 1"}], combates_por_mat={1: [crudo]},
            fetched_at="2026-01-01T00:00:00Z")
        self.assertEqual(len(estado["matches"][0]["sides"]), 1)
        self.assertEqual(len(estado["athletes"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
