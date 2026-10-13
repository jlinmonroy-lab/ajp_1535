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
import math
import threading
import time
import urllib.parse
from collections import OrderedDict
from datetime import date

from scraper import fetch
from scraper.fetch import ErrorOrigen
from scraper.parse import normalizar
from scraper.telemetria import nivel

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


def _coordenada(valor, maximo):
    """Un número dentro de [-maximo, maximo], o None. Smoothcomp las manda como texto."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) and abs(numero) <= maximo else None


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
        "lat": _coordenada(crudo.get("location_lat"), 90),
        "lon": _coordenada(crudo.get("location_long"), 180),
        "ended": bool(crudo.get("eventEnded")),
        "cover": crudo.get("cover_image") or None,
    }


def distancia_km(lat1, lon1, lat2, lon2):
    """Distancia en línea recta sobre la esfera terrestre (haversine), en km."""
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


class Zona:
    """Un sitio con el que acotar el buscador, p. ej. «Madrid, España».

    Un evento es de la zona si es del país y, o bien dice el texto (en el título o
    en la ciudad), o bien sus coordenadas caen dentro del radio. Las dos vías se
    complementan: el texto no necesita que el organizador haya puesto
    coordenadas, y el radio encuentra el torneo de Alcalá cuyo título no dice Madrid.
    """

    def __init__(self, nombre, pais, texto=None, centro=None, radio_km=None):
        self.nombre = nombre
        self.pais = pais
        self.texto = texto
        self.centro = centro
        self.radio_km = radio_km
        self._texto = normalizar(texto) if texto else None

    @classmethod
    def de_config(cls, datos):
        """La zona de `config.json`. Lanza ValueError si está mal escrita."""
        if not isinstance(datos, dict):
            raise ValueError("'zona' debe ser un objeto")
        nombre = str(datos.get("nombre") or "").strip()
        pais = str(datos.get("pais") or "").strip().upper()
        texto = str(datos.get("texto") or "").strip() or None
        if not nombre:
            raise ValueError("zona: falta 'nombre'")
        if not re.fullmatch(r"[A-Z]{2}", pais):
            raise ValueError("zona: 'pais' debe ser un código de dos letras, como ES")

        centro, radio = datos.get("centro"), datos.get("radioKm")
        if centro is not None or radio is not None:
            if (not isinstance(centro, (list, tuple)) or len(centro) != 2
                    or _coordenada(centro[0], 90) is None
                    or _coordenada(centro[1], 180) is None):
                raise ValueError("zona: 'centro' debe ser [latitud, longitud]")
            if isinstance(radio, bool) or not isinstance(radio, (int, float)) or radio <= 0:
                raise ValueError("zona: 'radioKm' debe ser un número mayor que 0")
            centro = (float(centro[0]), float(centro[1]))
        if not texto and centro is None:
            raise ValueError("zona: hace falta 'texto' o 'centro' con 'radioKm'")
        return cls(nombre, pais, texto, centro, float(radio) if radio is not None else None)

    def contiene(self, evento):
        if (evento.get("country") or "").upper() != self.pais:
            return False
        if self._texto and self._texto in normalizar(
                f"{evento.get('title') or ''} {evento.get('city') or ''}"):
            return True
        if self.centro and evento.get("lat") is not None and evento.get("lon") is not None:
            return distancia_km(*self.centro, evento["lat"], evento["lon"]) <= self.radio_km
        return False


def _coincide(evento, q):
    """¿Aparece lo que se escribió en el título o la ciudad? Sin acentos ni mayúsculas."""
    return not q or normalizar(q) in normalizar(
        f"{evento.get('title') or ''} {evento.get('city') or ''}")


def _finalizado(evento, hoy):
    """¿Smoothcomp lo da por terminado, o su fecha de fin (o de inicio) ya pasó?

    Mismo criterio que el chip «Finalizado» de la web. Sin fechas no cuenta como finalizado.
    """
    fin = evento["enddate"] or evento["startdate"]
    return bool(evento["ended"]) or bool(fin and fin < hoy)


def limpiar_consulta(q):
    """Texto de búsqueda sin espacios de más. Lanza ValueError si es inaceptable."""
    q = re.sub(r"\s+", " ", _CONTROL.sub(" ", q or "")).strip()
    if len(q) > MAX_CONSULTA:
        raise ValueError(f"la búsqueda no puede pasar de {MAX_CONSULTA} caracteres")
    return q


class Buscador:
    """Busca eventos, cacheando, y recuerda los que ha visto."""

    def __init__(self, cfg, pedir_html=None, pedir_json=None, reloj=time.monotonic,
                 hoy=None, log=None):
        self.cfg = cfg
        self._log = log or (lambda *_: None)
        # La zona por defecto del buscador (None si no hay): lanza ValueError si está mal escrita.
        self.zona = Zona.de_config(cfg["zona"]) if cfg.get("zona") else None
        self._hoy = hoy or (lambda: date.today().isoformat())
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

    def _url(self, cuando, q, pagina, pais=None):
        raiz = self.cfg["baseUrl"].rstrip("/")
        lang = self.cfg.get("lang", "en")
        params = {}
        if pais:
            params["countries"] = pais    # Smoothcomp sí filtra por país en el servidor
        if q:
            params["search"] = q
        if cuando == "past" and pagina > 1:
            params["page"] = pagina
        consulta = f"?{urllib.parse.urlencode(params)}" if params else ""
        return f"{raiz}/{lang}/events/{cuando}{consulta}"

    def _leer_lista(self, cuando, q, pagina, pais=None):
        html, _ = self._pedir_html(self._url(cuando, q, pagina, pais),
                                   self.cfg.get("timeoutSeconds", 30))
        eventos = [e for e in map(normalizar_evento, extraer_eventos(html)) if e]
        if cuando == "upcoming":
            eventos.sort(key=self._orden_de_proximos())
        return eventos

    def _orden_de_proximos(self):
        """Primero lo que aún no ha empezado, del más cercano al más lejano.

        `upcoming` incluye también lo que ya está en marcha, y Smoothcomp tiene
        ligas y circuitos que duran todo un año: arriba del todo taparían los
        torneos de verdad. Esos van después, los que acaban antes primero.
        """
        hoy = self._hoy()

        def clave(e):
            empezado = bool(e["startdate"]) and e["startdate"] < hoy
            fecha = (e["enddate"] if empezado else e["startdate"]) or "9999"
            return (empezado, fecha, int(e["id"]))
        return clave

    def _lista(self, cuando, q, pagina, pais=None):
        """(eventos, vieja). `vieja` si Smoothcomp falló y se sirve la copia anterior."""
        clave = (cuando, q.lower(), pagina if cuando == "past" else 1, pais)
        with self._candado:
            candado = self._por_clave.setdefault(clave, threading.Lock())

        with candado:
            ahora = self._reloj()
            with self._candado:
                guardado = self._cache.get(clave)
            if guardado and ahora - guardado[0] < self.ttl:
                return guardado[1], guardado[2]

            try:
                eventos = self._leer_lista(cuando, q, pagina, pais)
            except ErrorOrigen as e:
                if not guardado:
                    raise
                nivel(self._log, "aviso")(
                    f"búsqueda: Smoothcomp falló ({e}); se sirve la copia guardada")
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

    def buscar(self, q="", cuando="upcoming", pagina=1, zona=False):
        """Una página de resultados.

        {"events": [...], "page": n, "hasMore": bool, "stale": bool}

        Con `zona=True` solo salen los eventos de la zona de la configuración. El
        texto `search` de Smoothcomp es una frase exacta sobre el título y no mira
        la ciudad, así que no sirve para acotar por sitio:

          - **próximos:** se pide la lista del país entera, una sola vez y sin
            texto, y se filtra aquí por zona y por lo escrito. Esa lista en caché
            sirve a cualquier búsqueda.
          - **pasados:** son demasiados para filtrar por coordenadas, así que se
            pide el texto de la zona (p. ej. «madrid») y se filtra aquí por lo escrito.

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
        if zona and self.zona is None:
            raise ValueError("no hay ninguna zona configurada")
        z = self.zona if zona else None

        eventos, hay_mas, vieja = [], False, False

        if cuando in ("upcoming", "all"):
            if z:
                pais_entero, v = self._lista("upcoming", "", 1, z.pais)
                lista = [e for e in pais_entero if z.contiene(e) and _coincide(e, q)]
            else:
                lista, v = self._lista("upcoming", q, pagina)
            # Los que ya han terminado van en «pasados»; se quitan antes de paginar.
            hoy = self._hoy()
            lista = [e for e in lista if not _finalizado(e, hoy)]
            inicio = (pagina - 1) * POR_PAGINA
            eventos += lista[inicio:inicio + POR_PAGINA]
            hay_mas = hay_mas or len(lista) > inicio + POR_PAGINA
            vieja = vieja or v

        if cuando in ("past", "all"):
            if z:
                pagina_cruda, v = self._lista("past", z.texto or "", pagina, z.pais)
                lista = [e for e in pagina_cruda if z.contiene(e) and _coincide(e, q)]
                # ¿Hay otra página en origen? Se mide antes de filtrar aquí.
                hay_mas = hay_mas or len(pagina_cruda) >= POR_PAGINA
            else:
                lista, v = self._lista("past", q, pagina)
                hay_mas = hay_mas or len(lista) >= POR_PAGINA
            eventos += lista
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
