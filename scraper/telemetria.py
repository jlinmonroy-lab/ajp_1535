"""
Registro y contadores del servidor, solo con la biblioteca estándar.

Todo el proyecto llama a `log(mensaje)` con un único texto, y las pruebas lo
sustituyen por `lambda *_: None` o por `lista.append`. Eso se conserva: `registro`
es un `log` más, pero detrás lleva `logging` (fecha, nivel, fichero con rotación)
y dos métodos, `aviso` y `error`, para quien quiera subir el nivel. Quien reciba
un `log` cualquiera usa `nivel(log, "aviso")` y, si es una función suelta, sale el
propio `log`.

Por entorno:
  LOG_LEVEL   DEBUG | INFO (por defecto) | WARNING | ERROR
  LOG_FORMAT  `json` para una línea JSON por mensaje; por defecto, texto
  LOG_FILE    además de la consola, un fichero con rotación (5 × 1 MB)
"""
import json
import logging
import os
import sys
import threading
import time
from collections import Counter
from logging.handlers import RotatingFileHandler

NOMBRE = "bjj"
FORMATO_TEXTO = "%(asctime)s %(levelname)-7s %(message)s"
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"
FICHERO_MAX_BYTES = 1_000_000
FICHERO_COPIAS = 5

# Sin handlers, `logging` escribiría los avisos por stderr aunque nadie lo haya pedido
# (las pruebas, o quien importe un módulo suelto). Los configura `configurar_logging`.
logging.getLogger(NOMBRE).addHandler(logging.NullHandler())


class _Consola(logging.StreamHandler):
    """Escribe en el `sys.stdout` de cada momento, no en el que había al configurar."""

    def __init__(self):
        super().__init__(sys.stdout)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, _):
        pass


class _FormatoJson(logging.Formatter):
    def format(self, record):
        linea = {"t": self.formatTime(record, FORMATO_FECHA), "nivel": record.levelname,
                 "msg": record.getMessage()}
        return json.dumps(linea, ensure_ascii=False)


def configurar_logging(entorno=None):
    """Deja el registro listo. Se puede llamar más de una vez: solo la última cuenta."""
    entorno = os.environ if entorno is None else entorno
    logger = logging.getLogger(NOMBRE)
    nivel_pedido = (entorno.get("LOG_LEVEL") or "INFO").upper()
    logger.setLevel(getattr(logging, nivel_pedido, logging.INFO))
    logger.propagate = False

    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    if (entorno.get("LOG_FORMAT") or "").lower() == "json":
        formato = _FormatoJson()
    else:
        formato = logging.Formatter(FORMATO_TEXTO, FORMATO_FECHA)

    consola = _Consola()
    consola.setFormatter(formato)
    logger.addHandler(consola)

    fichero = entorno.get("LOG_FILE")
    if fichero:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(fichero)), exist_ok=True)
            handler = RotatingFileHandler(fichero, maxBytes=FICHERO_MAX_BYTES,
                                          backupCount=FICHERO_COPIAS, encoding="utf-8")
        except OSError as e:
            # Sin fichero se sigue por consola: no vale la pena no arrancar por esto.
            logger.warning("no se puede escribir el registro en %s (%s)", fichero, e)
        else:
            handler.setFormatter(formato)
            logger.addHandler(handler)
    return logger


class Registro:
    """Un `log(mensaje)` de nivel INFO con `.aviso` y `.error` para subirlo."""

    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(NOMBRE)

    def __call__(self, mensaje):
        self._logger.info(mensaje)

    def depurar(self, mensaje):
        self._logger.debug(mensaje)

    def aviso(self, mensaje):
        self._logger.warning(mensaje)

    def error(self, mensaje):
        self._logger.error(mensaje)


registro = Registro()


def nivel(log, nombre):
    """El método `nombre` ("depurar", "aviso", "error") de `log`, o `log` si no lo tiene."""
    return getattr(log, nombre, log)


class Contadores:
    """Contadores en memoria. Se pierden al reiniciar, como la caché."""

    def __init__(self):
        self._candado = threading.Lock()
        self._valores = Counter()

    def sumar(self, nombre, n=1):
        with self._candado:
            self._valores[nombre] += n

    def todos(self):
        with self._candado:
            return dict(self._valores)


contadores = Contadores()


class Limitador:
    """Un cubo de fichas: deja pasar hasta `capacidad` avisos y repone `capacidad` cada
    `ventana_s` segundos. Es global, no por cliente: sirve para que un error en bucle de
    cualquier navegador no pueda llenar el registro, no para repartir equitativamente."""

    def __init__(self, capacidad, ventana_s, reloj=time.monotonic):
        self.capacidad = capacidad
        self._ritmo = capacidad / ventana_s       # fichas por segundo
        self._reloj = reloj
        self._candado = threading.Lock()
        self._fichas = float(capacidad)
        self._ultima = reloj()

    def permitir(self):
        with self._candado:
            ahora = self._reloj()
            self._fichas = min(self.capacidad, self._fichas + (ahora - self._ultima) * self._ritmo)
            self._ultima = ahora
            if self._fichas < 1:
                return False
            self._fichas -= 1
            return True
