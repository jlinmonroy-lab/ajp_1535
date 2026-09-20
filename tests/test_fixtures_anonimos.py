"""
Guarda de privacidad: impide que vuelvan a colarse datos personales.

El repositorio es público y los fixtures se regeneran con
research/capture_event.py, que baja datos reales. Es fácil recapturar y
commitear sin acordarse de anonimizar; estas pruebas hacen que eso falle en vez
de pasar desapercibido.

Uso:  python -m unittest discover -s tests
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "fixtures"

NOMBRE_ANON = re.compile(r"^Atleta \d+$")
BASE_ID = 900000


def plazas_de_inscripcion():
    for carpeta in sorted(FIXTURES.glob("event_*")):
        for archivo in sorted(carpeta.glob("matches_*.json")):
            for combate in json.loads(archivo.read_text(encoding="utf-8")):
                for plaza in combate.get("seats", []):
                    if plaza.get("type") == "registration":
                        yield archivo, plaza


class TestFixturesAnonimos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plazas = list(plazas_de_inscripcion())
        if not cls.plazas:
            raise unittest.SkipTest("no hay fixtures de evento que comprobar")

    def test_nombres_anonimizados(self):
        for archivo, plaza in self.plazas:
            self.assertRegex(
                plaza.get("name") or "", NOMBRE_ANON,
                f"{archivo.name}: nombre real sin anonimizar. "
                f"Ejecuta research/anonymize_fixtures.py")

    def test_sin_urls_de_foto(self):
        # La URL de la foto lleva el nombre y apellidos dentro, así que basta
        # con que exista para que haya una fuga.
        for archivo, plaza in self.plazas:
            self.assertIsNone(
                plaza.get("image"),
                f"{archivo.name}: queda una URL de foto. "
                f"Ejecuta research/anonymize_fixtures.py")

    def test_ids_renumerados(self):
        for archivo, plaza in self.plazas:
            rid = plaza.get("event_registration_id")
            self.assertGreaterEqual(
                rid, BASE_ID,
                f"{archivo.name}: id de inscripción real ({rid}). "
                f"Ejecuta research/anonymize_fixtures.py")


class TestNadaPersonalVersionado(unittest.TestCase):
    """Lo que git rastrea es lo que acaba siendo público."""

    @classmethod
    def setUpClass(cls):
        try:
            salida = subprocess.run(
                ["git", "ls-files", "-z"], cwd=str(RAIZ),
                capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise unittest.SkipTest("git no disponible")
        if salida.returncode != 0:
            raise unittest.SkipTest("no es un repositorio git")
        cls.ficheros = [RAIZ / p for p in salida.stdout.split("\0") if p]

    def test_sin_rastros_personales(self):
        """Ningún fichero versionado debe llevar datos de una sesión real.

        Se buscan *patrones*, no valores concretos: si aquí se escribiera el id
        de cuenta del usuario para detectarlo, este mismo fichero lo estaría
        publicando. Y se excluye el propio escáner, que si no se encontraría a
        sí mismo.
        """
        rastros = (
            ("URL de foto de atleta", re.compile(r"ajptour[.]com/pictures")),
            ("perfil de usuario", re.compile(r"/[a-z]{2}/user/[0-9]+")),
            ("cookie de sesión", re.compile(r"laravel" + r"_session")),
            ("token CSRF", re.compile(r"""name=["']_token["']""")),
        )
        yo = Path(__file__).resolve()
        for ruta in self.ficheros:
            if ruta.resolve() == yo:
                continue
            try:
                texto = ruta.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeError):
                continue
            for etiqueta, patron in rastros:
                self.assertIsNone(
                    patron.search(texto),
                    f"{ruta.relative_to(RAIZ)} contiene {etiqueta} y está versionado")

    def test_secrets_no_versionado(self):
        for ruta in self.ficheros:
            self.assertFalse(
                str(ruta.relative_to(RAIZ)).replace("\\", "/").startswith("secrets/"),
                f"{ruta} está en secrets/ y no debe versionarse")


if __name__ == "__main__":
    unittest.main(verbosity=2)
