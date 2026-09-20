"""
Lectura del schedule desde Smoothcomp.

Solo biblioteca estándar: los endpoints son públicos (ver docs/data-source.md),
así que no hacen falta ni cookies ni navegador ni dependencias externas.

Un ciclo cuesta 1 + nº días + nº tatamis peticiones, espaciadas por cortesía.
"""
import json
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# Un 429 o un 5xx es el servidor pidiendo que bajemos el ritmo, y una conexión
# caída merece otro intento. Un 403 o un 404 no mejoran repitiendo.
REINTENTABLES = {429, 500, 502, 503, 504}


class ErrorOrigen(Exception):
    """Fallo al leer del origen que el bucle debe contar para marcar stale."""


def _get(url, timeout, intentos=3, espera_base=1.0):
    ultimo = None
    for intento in range(intentos):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in REINTENTABLES:
                # 403 en estos endpoints suele significar "schedule no publicado".
                raise ErrorOrigen(f"HTTP {e.code} en {url}") from e
            ultimo = f"HTTP {e.code}"
            espera = float(e.headers.get("Retry-After") or 0) or espera_base * 2 ** intento
        except Exception as e:  # noqa: BLE001 - red inestable: merece reintento
            ultimo = f"{type(e).__name__}: {e}"
            espera = espera_base * 2 ** intento

        if intento < intentos - 1:
            time.sleep(espera)

    raise ErrorOrigen(f"{ultimo} tras {intentos} intentos en {url}")


def _como_lista(valor):
    """matcategories.json da un objeto si el evento tiene un solo día."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def leer_schedule(cfg, log=print):
    """Lee días, tatamis y combates. Devuelve (dias, mats, combates_por_mat)."""
    base = f"{cfg['baseUrl']}/{cfg['lang']}/event/{cfg['eventId']}/schedule/new"
    pausa = cfg.get("requestPauseSeconds", 2.0)
    timeout = cfg.get("timeoutSeconds", 30)

    dias = _como_lista(_get(f"{base}/matcategories.json", timeout))
    if not dias:
        raise ErrorOrigen("el evento no devuelve ningún día de competición")

    mats = []
    for d in dias:
        time.sleep(pausa)
        mats.extend(_get(f"{base}/mats.json/{d['id']}", timeout))

    # Un tatami oculto no se muestra en la web del evento; tampoco aquí.
    visibles = [m for m in mats if m.get("visible", 1)]

    combates_por_mat = {}
    for m in visibles:
        time.sleep(pausa)
        try:
            combates_por_mat[m["id"]] = _get(
                f"{base}/mat/{m['id']}/matches.json", timeout)
        except ErrorOrigen as e:
            # Un tatami que falla no invalida el resto del ciclo: se publica lo
            # que sí se pudo leer y se deja constancia.
            log(f"  aviso: tatami {m.get('name')!r} no se pudo leer ({e})")

    if not combates_por_mat:
        raise ErrorOrigen("ningún tatami devolvió combates")

    return dias, visibles, combates_por_mat
