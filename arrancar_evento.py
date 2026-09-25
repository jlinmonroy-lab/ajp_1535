"""
Lanzador para el día del torneo: arráncalo y olvídate.

El scraper corre en este equipo y mañana no habrá nadie delante, así que este
lanzador cubre las dos formas en que la web se quedaría congelada sin que nadie
se entere:

  - **Que Windows suspenda el equipo.** Se le pide al sistema que no lo haga
    mientras esto viva, en vez de cambiar la configuración de energía: al cerrar,
    todo vuelve a su sitio solo. La pantalla sí puede apagarse, y bloquearla no
    afecta.
  - **Que el scraper se caiga.** Si termina por lo que sea, se relanza. Cada
    arranque y cada caída quedan en registro/evento.log con su hora.

Lo que NO puede cubrir: un corte de luz, que Windows reinicie por
actualizaciones o que se caiga el wifi de casa. Merece la pena dejar el equipo
enchufado y posponer las actualizaciones antes de salir.

Uso:  python arrancar_evento.py
      (Ctrl+C para parar)
"""
import ctypes
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
REGISTRO = RAIZ / "registro"

# Banderas de SetThreadExecutionState: mantener el sistema despierto mientras
# este proceso viva, sin tocar el plan de energía del usuario.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

ESPERA_REINICIO = 10  # segundos antes de relanzar si se cae


def log(mensaje, fichero=None):
    linea = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {mensaje}"
    print(linea, flush=True)
    if fichero:
        with open(fichero, "a", encoding="utf-8") as f:
            f.write(linea + "\n")


def evitar_suspension():
    """Pide a Windows que no suspenda el equipo. Devuelve si lo consiguió."""
    try:
        anterior = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        return anterior != 0
    except (AttributeError, OSError):
        return False  # en otro sistema operativo, simplemente no aplica


def permitir_suspension():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except (AttributeError, OSError):
        pass


def main():
    REGISTRO.mkdir(exist_ok=True)
    diario = REGISTRO / "evento.log"

    print()
    log("=" * 62, diario)
    log("Arrancando el seguimiento del torneo", diario)
    log(f"Registro en {diario}", diario)

    if evitar_suspension():
        log("Windows no suspenderá el equipo mientras esto esté abierto.", diario)
    else:
        log("AVISO: no se pudo evitar la suspensión; revisa el plan de energía.", diario)

    log("Web:   https://jlinmonroy-lab.github.io/ajp_1535/", diario)
    log("Panel: http://127.0.0.1:8765  (solo desde este equipo)", diario)
    log("Deja esta ventana abierta. Ctrl+C para parar.", diario)
    log("=" * 62, diario)
    print()

    intentos = 0
    try:
        while True:
            intentos += 1
            if intentos > 1:
                log(f"Reinicio nº {intentos - 1} del scraper", diario)

            proceso = subprocess.run(
                [sys.executable, "-u", "-m", "scraper.main"], cwd=str(RAIZ))

            # Solo se llega aquí si el scraper terminó, y no debería hacerlo.
            log(f"El scraper terminó (código {proceso.returncode}). "
                f"Relanzando en {ESPERA_REINICIO}s…", diario)
            time.sleep(ESPERA_REINICIO)
    except KeyboardInterrupt:
        log("Detenido a mano. La web se quedará con los últimos datos.", diario)
    finally:
        permitir_suspension()
    return 0


if __name__ == "__main__":
    sys.exit(main())
