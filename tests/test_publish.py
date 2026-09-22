"""
Pruebas de la decisión de publicar.

Importan porque GitHub Pages reconstruye en cada push y tiene un límite blando
de 10 builds/hora: publicar de más durante el evento acaba en un 429 y en datos
que dejan de actualizarse justo cuando hacen falta.

Se monta un repositorio git de verdad en una carpeta temporal: la lógica
depende de la fecha del último commit, y simularla dejaría sin probar
precisamente lo que puede fallar.

Uso:  python -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.publish import escribir_json, hay_que_publicar  # noqa: E402

ESTADO = {
    "event": {"id": "1", "name": "Prueba"},
    "fetchedAt": "2026-01-01T10:00:00Z",
    "stale": False,
    "staleSince": None,
    "matches": [{"id": "1", "state": "running"}],
    "athletes": [{"registrationId": "900001", "name": "Atleta 1"}],
}


def git(args, cwd, **entorno):
    env = {**os.environ, **entorno}
    return subprocess.run(["git", *args], cwd=str(cwd), env=env,
                          capture_output=True, text=True, check=True)


class TestDecisionDePublicar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.worktree = Path(self.tmp.name) / "publicado"
        self.local = Path(self.tmp.name) / "local"
        self.worktree.mkdir()
        self.local.mkdir()

        git(["init", "-q", "-b", "gh-pages"], self.worktree)
        git(["config", "user.email", "prueba@example.invalid"], self.worktree)
        git(["config", "user.name", "prueba"], self.worktree)

        self.cfg = {"publish": {"enabled": True, "worktree": str(self.worktree),
                                "maxMinutesSinPublish": 5}}
        self.data = self.local / "data.json"
        escribir_json(self.data, ESTADO)

    def tearDown(self):
        self.tmp.cleanup()

    def _publicar(self, estado, hace_minutos=0):
        """Deja `estado` como contenido ya publicado, commiteado hace N minutos."""
        escribir_json(self.worktree / "data.json", estado)
        cuando = f"{int(__import__('time').time()) - hace_minutos * 60} +0000"
        git(["add", "-A"], self.worktree)
        git(["commit", "-q", "-m", "publicado"], self.worktree,
            GIT_COMMITTER_DATE=cuando, GIT_AUTHOR_DATE=cuando)

    def test_primera_publicacion(self):
        procede, motivo = hay_que_publicar(self.cfg, self.data, self.worktree, print)
        self.assertTrue(procede)
        self.assertIn("primera", motivo)

    def test_publica_si_cambia_el_schedule(self):
        self._publicar(ESTADO)
        cambiado = json.loads(json.dumps(ESTADO))
        cambiado["matches"][0]["state"] = "finished"
        cambiado["fetchedAt"] = "2026-01-01T10:01:15Z"
        escribir_json(self.data, cambiado)

        procede, motivo = hay_que_publicar(self.cfg, self.data, self.worktree, print)
        self.assertTrue(procede)
        self.assertIn("cambios", motivo)

    def test_no_publica_si_solo_cambia_la_marca_de_tiempo(self):
        # El caso que hacía inútil la comprobación: entre ciclos sin combates
        # nuevos, lo único distinto es fetchedAt.
        self._publicar(ESTADO)
        solo_hora = {**ESTADO, "fetchedAt": "2026-01-01T10:01:15Z"}
        escribir_json(self.data, solo_hora)

        procede, motivo = hay_que_publicar(self.cfg, self.data, self.worktree, print)
        self.assertFalse(procede)
        self.assertIn("sin cambios", motivo)

    def test_stale_no_cuenta_como_cambio_de_fondo(self):
        self._publicar(ESTADO)
        marcado = {**ESTADO, "stale": True, "staleSince": "2026-01-01T10:05:00Z",
                   "fetchedAt": "2026-01-01T10:06:00Z"}
        escribir_json(self.data, marcado)

        procede, _ = hay_que_publicar(self.cfg, self.data, self.worktree, print)
        self.assertFalse(procede)

    def test_refresco_periodico_aunque_no_cambie_nada(self):
        # La web enseña "actualizado hace X": esa antigüedad tiene que ser real,
        # así que pasado el límite se publica igualmente.
        self._publicar(ESTADO, hace_minutos=9)
        escribir_json(self.data, {**ESTADO, "fetchedAt": "2026-01-01T10:09:00Z"})

        procede, motivo = hay_que_publicar(self.cfg, self.data, self.worktree, print)
        self.assertTrue(procede)
        self.assertIn("refresco", motivo)

    def test_el_limite_es_configurable(self):
        self._publicar(ESTADO, hace_minutos=9)
        escribir_json(self.data, {**ESTADO, "fetchedAt": "2026-01-01T10:09:00Z"})
        self.cfg["publish"]["maxMinutesSinPublish"] = 30

        procede, _ = hay_que_publicar(self.cfg, self.data, self.worktree, print)
        self.assertFalse(procede)



class TestConfigRecargable(unittest.TestCase):
    """La configuración se relee en cada ciclo, y eso puede pillarla a medias.

    Durante el evento se podrá ajustar el ritmo o añadir los enlaces de streams
    sin parar el scraper; leer justo mientras alguien guarda el fichero no debe
    tumbar el bucle.
    """

    def setUp(self):
        from argparse import Namespace
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "config.json"
        self.args = Namespace(config=str(self.ruta), event=None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lee_la_configuracion(self):
        from scraper.main import cargar_config
        self.ruta.write_text(json.dumps({"eventId": "1", "refreshSeconds": 75}),
                             encoding="utf-8")
        cfg = cargar_config(self.args)
        self.assertEqual(cfg["refreshSeconds"], 75)

    def test_json_a_medias_conserva_la_anterior(self):
        from scraper.main import cargar_config
        buena = {"eventId": "1", "refreshSeconds": 75}
        self.ruta.write_text(json.dumps(buena), encoding="utf-8")
        cfg = cargar_config(self.args)

        self.ruta.write_text('{"eventId": "1", "refresh', encoding="utf-8")  # truncado
        self.assertEqual(cargar_config(self.args, anterior=cfg), buena)

    def test_sin_anterior_si_falla_propaga(self):
        from scraper.main import cargar_config
        self.ruta.write_text("{roto", encoding="utf-8")
        with self.assertRaises(ValueError):
            cargar_config(self.args)

if __name__ == "__main__":
    unittest.main(verbosity=2)
