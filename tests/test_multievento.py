"""
Pruebas de los dos eventos combinados en una sola web.

El 26-27 de septiembre coinciden en el mismo pabellón el AJP No-Gi Madrid
(1535) y el Europe Continental Gi (1526). Se sirven juntos para que quien
compita en ambos vea todos sus combates en una sola ficha.

Eso trae dos riesgos que estas pruebas cubren:

  - `event_registration_id` es único por evento, así que la misma persona llega
    con dos identificadores distintos y hay que unificarla por nombre + club.
  - Los dos eventos pueden tener tatamis y numeración de combates homónimos, y
    no deben pisarse.

Uso:  python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.parse import construir_estado  # noqa: E402

EVENTOS = [
    {"id": "1535", "label": "No-Gi", "name": "AJP NO-GI MADRID"},
    {"id": "1526", "label": "Gi", "name": "AJP EUROPE CONTINENTAL"},
]


def combate(mid, nombre_a, club_a, reg_a, nombre_b, club_b, reg_b,
            *, bracket=1, ronda="Final", estado="finished", gana_a=True, hora=None):
    return {
        "id": mid, "bracket_id": bracket, "name": ronda, "round": 1,
        "group": "Men's GI / Black / Adults / 77KG", "state": estado,
        "match_nr": 1, "wonBy": "points" if estado == "finished" else None,
        "estimated_start": hora or "2026-09-26T10:00:00+02:00",
        "seats": [
            {"type": "registration", "event_registration_id": reg_a,
             "name": nombre_a, "club": club_a, "isWinner": gana_a},
            {"type": "registration", "event_registration_id": reg_b,
             "name": nombre_b, "club": club_b, "isWinner": not gana_a},
        ],
    }


def estado_con(datos_por_evento, eventos=EVENTOS):
    return construir_estado(eventos=eventos, datos_por_evento=datos_por_evento,
                            fetched_at="2026-09-26T09:00:00Z")


class TestUnificacionDeAtletas(unittest.TestCase):
    def test_la_misma_persona_en_dos_eventos_es_una_ficha(self):
        # Mismo nombre y club, inscripciones distintas: es el caso real de quien
        # compite en Gi y en No-Gi.
        nogi = combate(1, "Ana Pérez", "Gracie Madrid", 111, "Otra", "Club B", 222)
        gi = combate(1, "Ana Pérez", "Gracie Madrid", 999, "Tercera", "Club C", 333)
        estado = estado_con({
            "1535": ([], [{"id": 1, "name": "Mat 1"}], {1: [nogi]}),
            "1526": ([], [{"id": 1, "name": "Mat 1"}], {1: [gi]}),
        })

        anas = [a for a in estado["athletes"] if a["name"] == "Ana Pérez"]
        self.assertEqual(len(anas), 1, "debería haber una sola ficha de Ana")
        ana = anas[0]
        self.assertCountEqual(ana["registrationIds"], ["111", "999"])
        self.assertCountEqual(ana["events"], ["1535", "1526"])
        self.assertEqual(len(ana["matchIds"]), 2)

    def test_acentos_y_mayusculas_no_separan_a_la_misma_persona(self):
        a = combate(1, "ANA PÉREZ", "Gracie Madrid", 111, "X", "C", 222)
        b = combate(1, "ana perez", "gracie madrid", 999, "Y", "D", 333)
        estado = estado_con({
            "1535": ([], [{"id": 1, "name": "Mat 1"}], {1: [a]}),
            "1526": ([], [{"id": 1, "name": "Mat 1"}], {1: [b]}),
        })
        self.assertEqual(len([x for x in estado["athletes"]
                              if x["id"].startswith("ana perez|")]), 1)

    def test_mismo_nombre_distinto_club_no_se_fusiona(self):
        # Dos personas homónimas de clubes distintos deben seguir separadas.
        a = combate(1, "Juan García", "Club A", 111, "X", "C", 222)
        b = combate(1, "Juan García", "Club B", 999, "Y", "D", 333)
        estado = estado_con({
            "1535": ([], [{"id": 1, "name": "Mat 1"}], {1: [a]}),
            "1526": ([], [{"id": 1, "name": "Mat 1"}], {1: [b]}),
        })
        juanes = [x for x in estado["athletes"] if x["name"].lower() == "juan garcía"]
        self.assertEqual(len(juanes), 2)

    def test_medalla_en_cada_evento(self):
        # Oro en No-Gi y plata en Gi: dos medallas, una por evento.
        nogi = combate(1, "Ana", "Club", 111, "Rival1", "C1", 222, gana_a=True)
        gi = combate(1, "Ana", "Club", 999, "Rival2", "C2", 333, gana_a=False)
        estado = estado_con({
            "1535": ([], [{"id": 1, "name": "Mat 1"}], {1: [nogi]}),
            "1526": ([], [{"id": 1, "name": "Mat 1"}], {1: [gi]}),
        })
        ana = next(a for a in estado["athletes"] if a["name"] == "Ana")
        self.assertCountEqual([m["medal"] for m in ana["medals"]], ["gold", "silver"])
        self.assertCountEqual([m["eventId"] for m in ana["medals"]], ["1535", "1526"])
        self.assertEqual(ana["bestMedal"], "gold")


class TestSeparacionEntreEventos(unittest.TestCase):
    def setUp(self):
        # Mismo id de combate, de bracket y de tatami en los dos eventos:
        # Smoothcomp numera por evento, así que puede repetirse.
        c = combate(1, "A", "CA", 1, "B", "CB", 2)
        self.estado = estado_con({
            "1535": ([], [{"id": 7, "name": "Mat 1"}], {7: [c]}),
            "1526": ([], [{"id": 7, "name": "Mat 1"}], {7: [dict(c)]}),
        })

    def test_los_combates_no_se_pisan(self):
        self.assertEqual(len(self.estado["matches"]), 2)
        self.assertCountEqual([m["eventId"] for m in self.estado["matches"]],
                              ["1535", "1526"])

    def test_los_tatamis_homonimos_son_distintos(self):
        claves = [m["key"] for m in self.estado["mats"]]
        self.assertEqual(len(claves), len(set(claves)))
        self.assertCountEqual(claves, ["1535:7", "1526:7"])

    def test_cada_combate_sabe_de_qué_evento_es(self):
        for m in self.estado["matches"]:
            self.assertIn(m["eventLabel"], ("Gi", "No-Gi"))
            self.assertTrue(m["matKey"].startswith(m["eventId"] + ":"))


class TestEventoSinPublicar(unittest.TestCase):
    """Lo normal estos días: uno con schedule y el otro todavía en 403."""

    def test_se_publica_lo_que_hay(self):
        c = combate(1, "A", "CA", 1, "B", "CB", 2)
        estado = estado_con({"1535": ([], [{"id": 1, "name": "Mat 1"}], {1: [c]})})

        self.assertEqual(len(estado["matches"]), 1)
        self.assertEqual(len(estado["events"]), 2, "el evento vacío sigue anunciándose")
        vacio = next(e for e in estado["events"] if e["id"] == "1526")
        self.assertEqual(vacio["days"], [])
        self.assertEqual([m for m in estado["mats"] if m["eventId"] == "1526"], [])


class TestJornadas(unittest.TestCase):
    """El torneo dura dos días con los mismos horarios en cada uno.

    Sin la jornada en el modelo, un combate del domingo a las 12:00 sería
    indistinguible de uno del sábado a la misma hora.
    """

    def setUp(self):
        sabado = combate(1, "A", "CA", 1, "B", "CB", 2,
                         hora="2026-09-26T16:40:00+02:00")
        domingo = combate(2, "C", "CC", 3, "D", "CD", 4, bracket=2,
                          hora="2026-09-27T12:00:00+02:00")
        # Los seis tatamis físicos se reutilizan cada día con ids distintos.
        mats = [{"id": 10, "name": "Mat 1", "dayId": 1, "dayName": "Saturday",
                 "dayDate": "2026-09-26T16:40:00+02:00"},
                {"id": 20, "name": "Mat 1", "dayId": 2, "dayName": "Sunday",
                 "dayDate": "2026-09-27T12:00:00+02:00"}]
        self.estado = estado_con({
            "1535": ([], mats, {10: [sabado], 20: [domingo]}),
        })

    def test_cada_combate_sabe_su_jornada(self):
        dias = sorted(m["day"] for m in self.estado["matches"])
        self.assertEqual(dias, ["2026-09-26", "2026-09-27"])

    def test_el_nombre_de_la_jornada_viene_del_tatami(self):
        por_dia = {m["day"]: m["dayName"] for m in self.estado["matches"]}
        self.assertEqual(por_dia["2026-09-26"], "Saturday")
        self.assertEqual(por_dia["2026-09-27"], "Sunday")

    def test_el_mismo_tatami_fisico_en_dos_jornadas_no_se_mezcla(self):
        # Mismo nombre "Mat 1", dos entradas distintas, una por jornada.
        mat1 = [m for m in self.estado["mats"] if m["name"] == "Mat 1"]
        self.assertEqual(len(mat1), 2)
        self.assertEqual(len({m["key"] for m in mat1}), 2)
        self.assertCountEqual([m["day"] for m in mat1],
                              ["2026-09-26", "2026-09-27"])


class TestPlazasPorDeterminar(unittest.TestCase):
    """Un bracket sin empezar tiene plazas 'tbd' esperando al ganador.

    En el torneo real, 291 de los 822 combates no tienen todavía ningún atleta
    conocido, así que la app debe aguantarlo sin romperse.
    """

    def test_combate_con_una_plaza_pendiente(self):
        c = combate(1, "A", "CA", 1, "B", "CB", 2)
        c["seats"][1] = {"type": "tbd", "name": "Winner of 1-2"}
        estado = estado_con({"1535": ([], [{"id": 1, "name": "Mat 1"}], {1: [c]})})

        self.assertEqual(len(estado["matches"][0]["sides"]), 1)
        self.assertEqual(len(estado["athletes"]), 1)

    def test_combate_sin_ningun_atleta_conocido(self):
        c = combate(1, "A", "CA", 1, "B", "CB", 2)
        c["seats"] = [{"type": "tbd", "name": "Winner of 1-2"},
                      {"type": "tbd", "name": "Winner of 3-4"}]
        estado = estado_con({"1535": ([], [{"id": 1, "name": "Mat 1"}], {1: [c]})})

        self.assertEqual(estado["matches"][0]["sides"], [])
        self.assertEqual(estado["athletes"], [])



class TestGrupoCompartido(unittest.TestCase):
    """La lista que ve todo el mundo al abrir la web.

    localStorage vive en cada navegador, así que la única forma de que una
    selección llegue a todos los móviles es publicarla en el data.json.
    """

    def setUp(self):
        a = combate(1, "Ana Pérez", "Gracie Madrid", 111, "Otro", "Club B", 222)
        self.datos = {"1535": ([], [{"id": 1, "name": "Mat 1"}], {1: [a]})}

    def _estado(self, grupo):
        return construir_estado(eventos=EVENTOS, datos_por_evento=self.datos,
                                fetched_at="2026-09-26T09:00:00Z", grupo=grupo)

    def test_marca_a_los_del_grupo(self):
        estado = self._estado({"nombre": "Equipo",
                               "atletas": [{"id": "ana perez|gracie madrid",
                                            "name": "Ana Pérez"}]})
        ana = next(a for a in estado["athletes"] if a["name"] == "Ana Pérez")
        otro = next(a for a in estado["athletes"] if a["name"] == "Otro")
        self.assertTrue(ana["inGroup"])
        self.assertFalse(otro["inGroup"])
        self.assertEqual(estado["group"]["name"], "Equipo")

    def test_sin_grupo_nadie_esta_marcado(self):
        estado = self._estado(None)
        self.assertFalse(any(a["inGroup"] for a in estado["athletes"]))
        self.assertEqual(estado["group"]["athletes"], [])

    def test_un_atleta_que_no_compite_no_rompe_nada(self):
        # Alguien que al final no se inscribió, o un id mal escrito a mano.
        estado = self._estado({"nombre": "Equipo",
                               "atletas": [{"id": "fulano|club fantasma",
                                            "name": "Fulano"}]})
        self.assertFalse(any(a["inGroup"] for a in estado["athletes"]))
        # La entrada se conserva: la lista no debe vaciarse sola.
        self.assertEqual(len(estado["group"]["athletes"]), 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
