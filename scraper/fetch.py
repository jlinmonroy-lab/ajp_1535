"""
Lectura de Smoothcomp.

Solo biblioteca estándar: los endpoints son públicos (ver docs/data-source.md),
así que no hacen falta ni cookies ni navegador ni dependencias externas.

Todo el tráfico hacia Smoothcomp pasa por `RITMO`: una sola petición a la vez y
una pausa mínima entre ellas, la pida quien la pida. Con el servidor multi-evento
hay varios hilos hablando con Smoothcomp (eventos que se refrescan, una búsqueda
en medio...) y sin esto las pausas de cada uno se sumarían en vez de repartirse.

Un ciclo cuesta 1 + nº días + nº tatamis peticiones.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple
from contextlib import contextmanager

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

CABECERAS_JSON = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}
CABECERAS_HTML = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Un 429 o un 5xx es el servidor pidiendo que bajemos el ritmo, y una conexión
# caída merece otro intento. Un 403 o un 404 no mejoran repitiendo.
REINTENTABLES = {429, 500, 502, 503, 504}


class ErrorOrigen(Exception):
    """Fallo al leer del origen que el bucle debe contar para marcar stale.

    `codigo` es el HTTP, si lo hubo. `desafio` dice que quien contestó fue el
    anti-bot de Cloudflare y no la aplicación, y la diferencia importa: un 403 de
    la aplicación en el schedule significa "aún no publicado", mientras que el
    del reto significa "nos están bloqueando". Un 404 es "ese evento no existe".
    """

    def __init__(self, mensaje, codigo=None, desafio=False):
        super().__init__(mensaje)
        self.codigo = codigo
        self.desafio = desafio


class Ritmo:
    """Un turno por petición: una a la vez y con una pausa mínima entre ellas."""

    def __init__(self, pausa=2.0):
        self.pausa = pausa
        self._candado = threading.Lock()
        self._ultima_fin = 0.0

    @contextmanager
    def turno(self):
        with self._candado:
            espera = self._ultima_fin + self.pausa - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            try:
                yield
            finally:
                self._ultima_fin = time.monotonic()


RITMO = Ritmo()


def configurar_ritmo(pausa):
    RITMO.pausa = max(0.0, float(pausa))


def es_desafio(texto, cabeceras=None):
    """¿Es la página de reto de Cloudflare en vez de una respuesta de Smoothcomp?"""
    if cabeceras is not None and "challenge" in (cabeceras.get("Cf-Mitigated") or "").lower():
        return True
    return "Just a moment" in texto or "Un momento" in texto


def _retry_after(cabeceras):
    try:
        return float(cabeceras.get("Retry-After") or 0)
    except ValueError:
        return 0.0  # venía como fecha HTTP: se usa la espera exponencial


def _pedir(url, timeout, cabeceras, intentos=3, espera_base=1.0):
    """GET con reintentos. Devuelve (texto, url_final)."""
    ultimo, codigo = None, None
    for intento in range(intentos):
        req = urllib.request.Request(url, headers=cabeceras)
        try:
            with RITMO.turno():
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode("utf-8"), resp.geturl()
        except urllib.error.HTTPError as e:
            codigo = e.code
            if e.code not in REINTENTABLES:
                # 403 en los .json suele significar "schedule no publicado".
                cuerpo = e.read(4096).decode("utf-8", errors="replace")
                raise ErrorOrigen(f"HTTP {e.code} en {url}", codigo=e.code,
                                  desafio=es_desafio(cuerpo, e.headers)) from e
            ultimo = f"HTTP {e.code}"
            espera = _retry_after(e.headers) or espera_base * 2 ** intento
        except Exception as e:  # noqa: BLE001 - red inestable: merece reintento
            codigo = None
            ultimo = f"{type(e).__name__}: {e}"
            espera = espera_base * 2 ** intento

        if intento < intentos - 1:
            time.sleep(espera)

    raise ErrorOrigen(f"{ultimo} tras {intentos} intentos en {url}", codigo=codigo)


def _get(url, timeout, intentos=3, espera_base=1.0):
    """GET de un endpoint JSON. Devuelve (datos, url_final)."""
    texto, final = _pedir(url, timeout, CABECERAS_JSON, intentos, espera_base)
    try:
        return json.loads(texto), final
    except ValueError as e:
        raise ErrorOrigen(f"respuesta que no es JSON en {url}",
                          desafio=es_desafio(texto)) from e


def pedir_json(url, timeout=30):
    """GET de un endpoint JSON suelto. Devuelve (datos, url_final)."""
    return _get(url, timeout)


def pedir_html(url, timeout=30):
    """GET de una página HTML (la lista de eventos). Devuelve (texto, url_final)."""
    return _pedir(url, timeout, CABECERAS_HTML)


def origen_de(url):
    """'https://kimuracup.smoothcomp.com/en/event/1' -> 'https://kimuracup.smoothcomp.com'."""
    partes = urllib.parse.urlsplit(url)
    return f"{partes.scheme}://{partes.netloc}"


def _como_lista(valor):
    """matcategories.json da un objeto si el evento tiene un solo día."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


Lectura = namedtuple("Lectura", "dias mats combates_por_mat base_url")


def leer_evento(cfg, event_id, base_url=None, log=print):
    """Lee un evento. Devuelve una `Lectura`.

    `base_url` es el sitio donde pedirlo (p. ej. el subdominio del organizador que
    da el buscador); si no se sabe, se usa el de la configuración. smoothcomp.com
    redirige al subdominio correcto, así que la primera petición se hace donde sea
    y el resto ya va al host final, que se devuelve en `base_url` para poder
    construir los enlaces a las llaves.
    """
    raiz = (base_url or cfg["baseUrl"]).rstrip("/")
    lang = cfg.get("lang", "en")
    timeout = cfg.get("timeoutSeconds", 30)
    configurar_ritmo(cfg.get("requestPauseSeconds", 2.0))

    crudo, url_final = _get(
        f"{raiz}/{lang}/event/{event_id}/schedule/new/matcategories.json", timeout)
    base = origen_de(url_final)
    ruta = f"{base}/{lang}/event/{event_id}/schedule/new"

    dias = _como_lista(crudo)
    if not dias:
        raise ErrorOrigen("el evento no devuelve ningún día de competición")

    mats = []
    for d in dias:
        # El JSON del tatami no dice a qué jornada pertenece, y aquí es el único
        # sitio donde se sabe: el torneo puede durar varios días y los mismos
        # tatamis físicos se reutilizan en cada uno con ids distintos.
        for m in _get(f"{ruta}/mats.json/{d['id']}", timeout)[0]:
            m["dayId"] = d.get("id")
            m["dayName"] = d.get("name")
            m["dayDate"] = d.get("date")
            mats.append(m)

    # Un tatami oculto no se muestra en la web del evento; tampoco aquí.
    visibles = [m for m in mats if m.get("visible", 1)]

    combates_por_mat = {}
    for m in visibles:
        try:
            combates_por_mat[m["id"]] = _get(
                f"{ruta}/mat/{m['id']}/matches.json", timeout)[0]
        except ErrorOrigen as e:
            # Un tatami que falla no invalida el resto del ciclo: se publica lo
            # que sí se pudo leer y se deja constancia.
            log(f"  aviso: tatami {m.get('name')!r} no se pudo leer ({e})")

    if not combates_por_mat:
        raise ErrorOrigen("ningún tatami devolvió combates")

    return Lectura(dias, visibles, combates_por_mat, base)


def leer_schedule(cfg, event_id, log=print):
    """Lo mismo que `leer_evento`, como la tupla de siempre (dias, mats, combates)."""
    lectura = leer_evento(cfg, event_id, log=log)
    return lectura.dias, lectura.mats, lectura.combates_por_mat
