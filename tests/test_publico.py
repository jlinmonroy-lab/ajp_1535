"""
Pruebas de la lectura del estado del túnel (Tailscale Funnel).

Nunca se consulta el túnel de verdad: `consultar_funnel` se prueba con una CLI
simulada, y el resto con textos como los que imprime `tailscale funnel status`.

Uso:  python -m unittest discover -s tests
"""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper import publico  # noqa: E402

HOST = "https://czc52571qd.tail6a0155.ts.net"

# Lo que imprimió el equipo del usuario antes de publicar esta web: solo el 443,
# que apunta a otro servicio suyo.
SOLO_EL_443 = f"""
# Funnel on:
#     - {HOST}

{HOST} (Funnel on)
|-- / proxy http://127.0.0.1:5678
"""

# Con esta web publicada además en el 8443.
CON_EL_8443 = f"""
# Funnel on:
#     - {HOST}
#     - {HOST}:8443

{HOST} (Funnel on)
|-- / proxy http://127.0.0.1:5678

{HOST}:8443 (Funnel on)
|-- / proxy http://127.0.0.1:8765
"""


class TestEnlaceFunnel(unittest.TestCase):
    def test_sin_publicar_no_hay_enlace(self):
        # El 443 apunta a otro servicio: no es el nuestro.
        self.assertIsNone(publico.enlace_funnel(SOLO_EL_443, 8765))

    def test_el_enlace_es_el_del_puerto_que_apunta_a_nuestro_servidor(self):
        self.assertEqual(publico.enlace_funnel(CON_EL_8443, 8765), f"{HOST}:8443/")

    def test_no_se_confunde_con_el_otro_servicio(self):
        self.assertEqual(publico.enlace_funnel(CON_EL_8443, 5678), f"{HOST}/")

    def test_el_puerto_puede_ser_texto(self):
        self.assertEqual(publico.enlace_funnel(CON_EL_8443, "8765"), f"{HOST}:8443/")

    def test_localhost_y_ipv6_valen_igual_que_127_0_0_1(self):
        for destino in ("http://localhost:8765", "https://localhost:8765", "http://[::1]:8765"):
            texto = f"{HOST}:8443 (Funnel on)\n|-- / proxy {destino}\n"
            self.assertEqual(publico.enlace_funnel(texto, 8765), f"{HOST}:8443/", destino)

    def test_lo_que_solo_ve_el_tailnet_no_es_publico(self):
        texto = f"{HOST}:8443 (tailnet only)\n|-- / proxy http://127.0.0.1:8765\n"
        self.assertIsNone(publico.enlace_funnel(texto, 8765))

    def test_una_ruta_distinta_de_la_raiz_va_en_el_enlace(self):
        texto = f"{HOST} (Funnel on)\n|-- /equipo proxy http://127.0.0.1:8765\n"
        self.assertEqual(publico.enlace_funnel(texto, 8765), f"{HOST}/equipo/")

    def test_una_ruta_sin_funnel_delante_no_cuenta(self):
        # Una línea de ruta suelta, sin la URL pública encima, no se atribuye a nadie.
        self.assertIsNone(publico.enlace_funnel("|-- / proxy http://127.0.0.1:8765\n", 8765))

    def test_entradas_raras(self):
        for texto in (None, "", "   \n\n", "no es la salida de tailscale", "# Funnel on:\n"):
            self.assertIsNone(publico.enlace_funnel(texto, 8765), repr(texto))


class TestConsultarFunnel(unittest.TestCase):
    def test_sin_la_cli_instalada_es_none(self):
        with mock.patch("scraper.publico.shutil.which", return_value=None), \
                mock.patch("scraper.publico.os.path.exists", return_value=False):
            self.assertIsNone(publico.consultar_funnel())

    def test_lee_la_salida_de_la_cli(self):
        completado = subprocess.CompletedProcess([], 0, stdout=CON_EL_8443, stderr="")
        with mock.patch("scraper.publico.shutil.which", return_value="tailscale"), \
                mock.patch("scraper.publico.subprocess.run", return_value=completado) as run:
            self.assertEqual(publico.consultar_funnel(), CON_EL_8443)
        self.assertEqual(run.call_args.args[0], ["tailscale", "funnel", "status"])
        self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_si_la_cli_falla_o_tarda_es_none(self):
        with mock.patch("scraper.publico.shutil.which", return_value="tailscale"):
            for efecto in (subprocess.TimeoutExpired("tailscale", 5), OSError("no arranca")):
                with mock.patch("scraper.publico.subprocess.run", side_effect=efecto):
                    self.assertIsNone(publico.consultar_funnel(), repr(efecto))
            error = subprocess.CompletedProcess([], 1, stdout="", stderr="Tailscale is stopped")
            with mock.patch("scraper.publico.subprocess.run", return_value=error):
                self.assertIsNone(publico.consultar_funnel())


class TestLineasDeArranque(unittest.TestCase):
    def test_publicada_da_el_enlace(self):
        lineas = publico.lineas_de_arranque(8765, CON_EL_8443)
        self.assertEqual(len(lineas), 1)
        self.assertIn(f"{HOST}:8443/", lineas[0])

    def test_sin_publicar_da_el_comando_exacto_y_no_toca_el_443(self):
        lineas = publico.lineas_de_arranque(8765, SOLO_EL_443)
        self.assertIn("tailscale funnel --bg --https=8443 8765", "\n".join(lineas))
        self.assertNotIn("reset", "\n".join(lineas))

    def test_sin_tailscale_lo_dice(self):
        lineas = publico.lineas_de_arranque(8765, None)
        self.assertIn("solo se ve desde este equipo", lineas[0])

    def test_por_defecto_consulta_el_tunel(self):
        with mock.patch("scraper.publico.consultar_funnel", return_value=CON_EL_8443) as c:
            self.assertIn(":8443/", publico.lineas_de_arranque(8765)[0])
        c.assert_called_once()

    def test_el_comando_usa_el_puerto_indicado(self):
        self.assertEqual(publico.comando_para_publicar(9000),
                         "tailscale funnel --bg --https=8443 9000")


if __name__ == "__main__":
    unittest.main()
