"""
Buscador de eventos de Smoothcomp.

La lista de eventos no tiene API: smoothcomp.com/{lang}/events/{upcoming|past}
la incrusta como JSON en el HTML (`var events = [...]`), con un filtro de texto
`?search=` que sí aplica el servidor. `upcoming` no pagina; `past` da 40 por
página con `?page=N`. Detalles y pruebas en docs/data-source.md.

Cada consulta se cachea unos minutos: Smoothcomp pide `Crawl-delay: 10` y la
lista sin filtrar pesa más de un mega. Si Smoothcomp falla se sirve la copia
vieja, avisando, antes que dejar la búsqueda muerta.

El `url` de cada evento trae el subdominio de su organizador. Se recuerda aquí
(`Buscador.evento`) porque es lo que necesita el lector del schedule para
construir los enlaces a las llaves.
"""
import json
import re
import threading
import time
import urllib.parse
from collections import OrderedDict

from scraper import fetch
from scraper.fetch import ErrorOrigen

CUANDO = ("upcoming", "past", "all")
POR_PAGINA = 40                    # tamaño de página de `past`; el de `upcoming` lo ponemos nosotros
MAX_CONSULTA = 80
MAX_PAGINA = 200
REINTENTO_TRAS_FALLO_S = 30        # con una copia vieja a mano, no martillear a Smoothcomp
MAX_CONSULTAS_EN_CACHE = 100
MAX_EVENTOS_CONOCIDOS = 5000

_VAR_EVENTS = re.compile(r"var\s+events\s*=\s*")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def extraer_eventos(html):
    """La lista cruda de `var events = [...]`.

    Se corta con `raw_decode` y no con una expresión regular: el JSON tiene
    corchetes anidados y `raw_decode` sabe dónde termina de verdad.
    """
    m = _VAR_EVENTS.search(html)
    if not m:
        raise ErrorOrigen("la página no trae la lista de eventos",
                          desafio=fetch.es_desafio(html))
    try:
        lista, _ = json.JSONDecoder().raw_decode(html, m.end())
    except ValueError as e:
        raise ErrorOrigen("la lista de eventos no es JSON válido") from e
    if not isinstance(lista, list):
        raise ErrorOrigen("la lista de eventos no es una lista")
    return lista


def host_de_smoothcomp(url):
    """Solo https y solo smoothcomp.com o un subdominio suyo.

    El subdominio viene del propio Smoothcomp, pero a partir de él el servidor
    hace peticiones: no se arriesga a que un dato raro lo mande a otro sitio.
    """
    partes = urllib.parse.urlsplit(url or "")
    host = (partes.hostname or "").lower()
    return partes.scheme == "https" and (host == "smoothcomp.com"
                                         or host.endswith(".smoothcomp.com"))


def normalizar_evento(crudo):
    """Un evento del buscador con los campos que usa la web, o None si no sirve."""
    if not isinstance(crudo, dict):
        return None
    try:
        event_id = str(int(crudo["id"]))
    except (KeyError, TypeError, ValueError):
        return None
    url = crudo.get("url")
    valida = host_de_smoothcomp(url)
    return {
        "id": event_id,
        "title": (crudo.get("title") or "").strip() or f"Evento {event_id}",
        # Se enseña como enlace en la web: solo si es de Smoothcomp.
        "url": url if valida else None,
        "baseUrl": fetch.origen_de(url) if valida else None,
        "startdate": crudo.get("startdate") or None,
        "enddate": crudo.get("enddate") or None,
        "city": (crudo.get("location_city") or "").strip() or None,
        "country": crudo.get("location_country") or None,
        "ended": bool(crudo.get("eventEnded")),
        "cover": crudo.get("cover_image") or None,
    }


def limpiar_consulta(q):
    """Texto de búsqueda sin espacios de más. Lanza ValueError si es inaceptable."""
    q = re.sub(r"\s+", " ", _CONTROL.sub(" ", q or "")).strip()
    if len(q) > MAX_CONSULTA:
        raise ValueError(f"la búsqueda no puede pasar de {MAX_CONSULTA} caracteres")
    return q


class Buscador:
    """Busca eventos, cacheando, y recuerda los que ha visto."""

    def __init__(self, cfg, pedir_html=None, pedir_json=None, reloj=time.monotonic):
        self.cfg = cfg
        self.ttl = (cfg.get("servidor") or {}).get("listaEventosTtlSeconds", 600)
        # Inyectables: las pruebas no tocan la red.
        self._pedir_html = pedir_html or fetch.pedir_html
        self._pedir_json = pedir_json or fetch.pedir_json
        self._reloj = reloj
        self._candado = threading.Lock()
        self._cache = OrderedDict()      # clave -> (momento, valor, vieja)
        self._por_clave = {}             # clave -> candado, para no pedir lo mismo dos veces a la vez
        self._conocidos = OrderedDict()  # id -> evento normalizado

    # ---- lista ----

    def _url(self, cuando, q, pagina):
        raiz = self.cfg["baseUrl"].rstrip("/")
        lang = self.cfg.get("lang", "en")
        params = {}
        if q:
            params["search"] = q
        if cuando == "past" and pagina > 1:
            params["page"] = pagina
        consulta = f"?{urllib.parse.urlencode(params)}" if params else ""
        return f"{raiz}/{lang}/events/{cuando}{consulta}"

    def _leer_lista(self, cuando, q, pagina):
        html, _ = self._pedir_html(self._url(cuando, q, pagina),
                                   self.cfg.get("timeoutSeconds", 30))
        eventos = [e for e in map(normalizar_evento, extraer_eventos(html)) if e]
        if cuando == "upcoming":
            # Los próximos, del más cercano al más lejano.
            eventos.sort(key=lambda e: (e["startdate"] or "9999", int(e["id"])))
        return eventos

    def _lista(self, cuando, q, pagina):
        """(eventos, vieja). `vieja` si Smoothcomp falló y se sirve la copia anterior."""
        clave = (cuando, q.lower(), pagina if cuando == "past" else 1)
        with self._candado:
            candado = self._por_clave.setdefault(clave, threading.Lock())

        with candado:
            ahora = self._reloj()
            with self._candado:
                guardado = self._cache.get(clave)
            if guardado and ahora - guardado[0] < self.ttl:
                return guardado[1], guardado[2]

            try:
                eventos = self._leer_lista(cuando, q, pagina)
            except ErrorOrigen:
                if not guardado:
                    raise
                # Se sigue sirviendo la copia, marcada como vieja, y se vuelve a
                # intentar pronto pero no en cada petición.
                with self._candado:
                    self._cache[clave] = (ahora - self.ttl + REINTENTO_TRAS_FALLO_S,
                                          guardado[1], True)
                return guardado[1], True

            with self._candado:
                self._cache[clave] = (ahora, eventos, False)
                self._cache.move_to_end(clave)
                while len(self._cache) > MAX_CONSULTAS_EN_CACHE:
                    vieja, _ = self._cache.popitem(last=False)
                    self._por_clave.pop(vieja, None)
            return eventos, False

    def buscar(self, q="", cuando="upcoming", pagina=1):
        """Una página de resultados.

        {"events": [...], "page": n, "hasMore": bool, "stale": bool}

        Lanza ValueError si los parámetros no valen y ErrorOrigen si Smoothcomp
        falla y no hay copia anterior.
        """
        q = limpiar_consulta(q)
        if cuando not in CUANDO:
            raise ValueError(f"'when' debe ser uno de {', '.join(CUANDO)}")
        try:
            pagina = int(pagina)
        except (TypeError, ValueError):
            raise ValueError("la página debe ser un número") from None
        if not 1 <= pagina <= MAX_PAGINA:
            raise ValueError(f"la página debe estar entre 1 y {MAX_PAGINA}")

        eventos, hay_mas, vieja = [], False, False

        if cuando in ("upcoming", "all"):
            lista, v = self._lista("upcoming", q, pagina)
            inicio = (pagina - 1) * POR_PAGINA
            eventos += lista[inicio:inicio + POR_PAGINA]
            hay_mas = hay_mas or len(lista) > inicio + POR_PAGINA
            vieja = vieja or v

        if cuando in ("past", "all"):
            lista, v = self._lista("past", q, pagina)
            eventos += lista
            hay_mas = hay_mas or len(lista) >= POR_PAGINA
            vieja = vieja or v

        self._recordar(eventos)
        return {"events": eventos, "page": pagina, "hasMore": hay_mas, "stale": vieja}

    # ---- un evento suelto ----

    def _recordar(self, eventos):
        with self._candado:
            for e in eventos:
                self._conocidos[e["id"]] = e
                self._conocidos.move_to_end(e["id"])
            while len(self._conocidos) > MAX_EVENTOS_CONOCIDOS:
                self._conocidos.popitem(last=False)

    def conocido(self, event_id):
        """El evento si el buscador ya lo ha visto; si no, None (sin tocar la red)."""
        with self._candado:
            return self._conocidos.get(str(event_id))

    def evento(self, event_id):
        """Los datos de un evento: los del buscador si ya los vio, o `getCmsData`.

        Es el caso de quien llega con un enlace directo `#/evento/33588` sin
        haber buscado antes. Lanza ErrorOrigen (con `codigo` 404 si no existe).
        """
        event_id = str(event_id)
        conocido = self.conocido(event_id)
        if conocido:
            return conocido

        raiz = self.cfg["baseUrl"].rstrip("/")
        lang = self.cfg.get("lang", "en")
        datos, final = self._pedir_json(f"{raiz}/{lang}/event/{event_id}/getCmsData",
                                        self.cfg.get("timeoutSeconds", 30))
        propios = (datos.get("eventData") if isinstance(datos, dict) else None) or {}
        base = fetch.origen_de(final)
        evento = {
            "id": event_id,
            "title": (propios.get("title") or "").strip() or f"Evento {event_id}",
            "url": None,
            "baseUrl": base if host_de_smoothcomp(base) else None,
            "startdate": None,   # getCmsData da las fechas como texto sin año ("01 Feb")
            "enddate": None,
            "city": None,
            "country": None,
            "ended": False,
            "cover": None,
        }
        self._recordar([evento])
        return evento
