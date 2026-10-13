"""
Almacén de eventos: la caché que comparten todos los que miran la web.

Quien abre un evento no hace que se lea Smoothcomp: pide aquí. El almacén
guarda por evento (o por pareja de eventos combinados) el último estado ya
convertido, serializado y comprimido, y decide cuándo refrescarlo:

  - La primera vez que alguien pide un evento se encola su lectura y se
    contesta "cargando"; la lectura la hace un hilo, nunca la petición.
  - Pasado `refreshSeconds` desde el último intento, la siguiente petición
    encola un refresco y sigue sirviendo lo que hay (stale-while-revalidate).
  - Un evento que nadie mira durante `inactividadMinutos` se olvida. No hay
    ningún bucle por evento: el tráfico hacia Smoothcomp es proporcional a lo
    que se está mirando, no a lo que se ha mirado alguna vez.

Da igual que miren 1 o 200 móviles: cada ciclo de un evento se lee una vez. Las
peticiones concretas pasan por el ritmo global de `scraper/fetch.py`.
"""
import gzip
import hashlib
import json
import queue
import re
import threading
import time
import traceback
from collections import OrderedDict, namedtuple

from scraper import fetch
from scraper.estado import ahora_iso, estado_vacio, marcar_stale
from scraper.fetch import ErrorOrigen
from scraper.parse import METADATOS_EVENTO, aplicar_grupo, construir_estado
from scraper.telemetria import nivel

MAX_EVENTOS_POR_VISTA = 3
MAX_PENDIENTES = 10          # lecturas en cola a la vez: más es que alguien está sondeando ids
TTL_NO_EXISTE_S = 300        # no se vuelve a preguntar por un id inexistente en cinco minutos
TTL_ERROR_S = 15             # sin datos que servir, se reintenta enseguida

_ID = re.compile(r"^\d{1,9}$")

# La respuesta a una petición. `fase`:
#   cargando  -> aún no hay nada que enseñar (HTTP 202)
#   listo     -> `cuerpo` es el estado; si el schedule no está publicado, sin combates
#   no_existe -> Smoothcomp no conoce ese id (404)
#   error     -> no se pudo leer y no hay copia anterior (502)
Respuesta = namedtuple("Respuesta", "fase cuerpo gz etag mensaje eventos")


class Saturado(Exception):
    """Hay demasiadas lecturas en curso o el almacén está lleno de eventos activos."""


def normalizar_ids(valor):
    """'1535, 1526' -> ('1535,1526', ['1535', '1526']). Lanza ValueError si no vale.

    Solo dígitos: el id acaba dentro de la URL que se pide a Smoothcomp, así que
    no se deja pasar nada más.
    """
    ids = []
    for trozo in str(valor or "").split(","):
        trozo = trozo.strip()
        if not _ID.match(trozo):
            raise ValueError("los ids de evento deben ser números separados por comas")
        trozo = str(int(trozo))
        if trozo not in ids:
            ids.append(trozo)
    if len(ids) > MAX_EVENTOS_POR_VISTA:
        raise ValueError(f"como máximo {MAX_EVENTOS_POR_VISTA} eventos a la vez")
    return ",".join(ids), ids


def _es_transitorio(error):
    """¿Merece reintento? Un 403/404 de la aplicación es una respuesta, no un fallo."""
    return not (error.codigo in (403, 404) and not error.desafio)


class Entrada:
    def __init__(self, clave, ids, ahora):
        self.clave = clave
        self.ids = ids
        self.fase = "cargando"
        self.mensaje = None
        self.bueno = None          # último estado leído sin problemas
        self.estado = None         # el que se sirve: el bueno, o ese mismo marcado stale
        self.cuerpo = self.gz = self.etag = None
        self.eventos = []
        self.refrescado = None     # cuándo terminó el último intento
        self.ultimo_acceso = ahora
        self.fallos = 0
        self.primer_fallo = None
        self.en_cola = False


class Almacen:
    def __init__(self, cfg, buscador, grupos, *, leer=None, reloj=time.monotonic,
                 log=print, workers=None):
        self.cfg = cfg
        servidor = cfg.get("servidor") or {}
        self.refresco = cfg.get("refreshSeconds", 75)
        self.limite_fallos = cfg.get("staleAfterFailures", 3)
        self.inactividad = servidor.get("inactividadMinutos", 30) * 60
        self.max_eventos = servidor.get("maxEventosEnCache", 20)
        self.buscador = buscador
        self.grupos = grupos
        self.log = log
        self._leer = leer or fetch.leer_evento   # inyectable: las pruebas no tocan la red
        self._reloj = reloj
        self._candado = threading.Lock()
        self._entradas = OrderedDict()           # clave -> Entrada, de la menos a la más reciente
        self._cola = queue.Queue()
        self._ultimo_exito = None      # cuándo (según `reloj`) se leyó un evento por última vez
        self._ultimo_error = None      # (cuándo, código HTTP, ¿era el reto de Cloudflare?)
        self._hilos = []
        for _ in range(servidor.get("workers", 2) if workers is None else workers):
            hilo = threading.Thread(target=self._trabajar, daemon=True)
            hilo.start()
            self._hilos.append(hilo)

    # ---- lo que usan las peticiones ----

    def pedir(self, ids):
        """La respuesta para un evento (o varios). Nunca toca la red.

        Lanza ValueError si los ids no valen y Saturado si no se puede aceptar
        otro evento nuevo.
        """
        clave, lista = normalizar_ids(ids)
        ahora = self._reloj()
        with self._candado:
            self._podar(ahora)
            entrada = self._entradas.get(clave)
            if entrada is None:
                self._hacer_sitio()
                entrada = self._entradas[clave] = Entrada(clave, lista, ahora)
                self._encolar(entrada)
            else:
                self._entradas.move_to_end(clave)
            entrada.ultimo_acceso = ahora
            if (entrada.refrescado is not None
                    and ahora - entrada.refrescado >= self._ttl(entrada)):
                self._encolar(entrada)
            return self._respuesta(entrada)

    def regrupar(self, clave):
        """El grupo ha cambiado: se reaplica sin releer nada de Smoothcomp."""
        with self._candado:
            entrada = self._entradas.get(clave)
            estado, bueno = (entrada.estado, entrada.bueno) if entrada else (None, None)
        if estado is None:
            return
        if bueno is not estado:
            aplicar_grupo(bueno, self.grupos.leer(clave))
        cuerpo, gz, etag = self._serializar(estado, clave)
        with self._candado:
            if entrada.estado is estado:     # no lo ha sustituido un refresco entretanto
                entrada.cuerpo, entrada.gz, entrada.etag = cuerpo, gz, etag

    def cerrar(self):
        for _ in self._hilos:
            self._cola.put(None)

    def resumen(self):
        """Una foto del estado para `/api/health`. No toca la red.

        Con la caché vacía (nadie mira ningún evento) no hay nada que vigilar: ni
        `eventosStale` ni `eventosConError` suben por un fallo antiguo.
        """
        with self._candado:
            ahora = self._reloj()
            entradas = list(self._entradas.values())
            exito, error = self._ultimo_exito, self._ultimo_error
            resumen = {
                "workers": len(self._hilos),
                "workersVivos": sum(h.is_alive() for h in self._hilos),
                "eventosEnCache": len(entradas),
                "enCola": sum(e.en_cola for e in entradas),
                "eventosStale": sum(bool(e.estado and e.estado.get("stale")) for e in entradas),
                "eventosConError": sum(e.fase == "error" for e in entradas),
            }
        resumen["origen"] = {
            "ultimoExitoS": None if exito is None else round(ahora - exito),
            "ultimoErrorS": None if error is None else round(ahora - error[0]),
            "ultimoErrorCodigo": None if error is None else error[1],
            "ultimoErrorReto": None if error is None else error[2],
        }
        return resumen

    # ---- gestión de entradas (siempre con el candado) ----

    def _ttl(self, entrada):
        if entrada.fase == "no_existe":
            return TTL_NO_EXISTE_S
        if entrada.fase == "error":
            return min(self.refresco, TTL_ERROR_S)
        return self.refresco

    def _encolar(self, entrada):
        if not entrada.en_cola:
            entrada.en_cola = True
            self._cola.put(entrada)

    def _podar(self, ahora):
        for clave, entrada in list(self._entradas.items()):
            if not entrada.en_cola and ahora - entrada.ultimo_acceso > self.inactividad:
                del self._entradas[clave]

    def _hacer_sitio(self):
        if sum(e.en_cola for e in self._entradas.values()) >= MAX_PENDIENTES:
            raise Saturado("hay demasiadas lecturas en curso, prueba en un momento")
        while len(self._entradas) >= self.max_eventos:
            # Se echa al menos reciente de los que no están leyéndose.
            sobrante = next((c for c, e in self._entradas.items() if not e.en_cola), None)
            if sobrante is None:
                raise Saturado("el servidor está atendiendo demasiados eventos a la vez")
            del self._entradas[sobrante]

    def _respuesta(self, entrada):
        if entrada.fase == "cargando":
            # Lo que el buscador ya sabe, para poder enseñar "Cargando <nombre>".
            eventos = [self.buscador.conocido(i) or {"id": i} for i in entrada.ids]
        else:
            eventos = entrada.eventos
        return Respuesta(entrada.fase, entrada.cuerpo, entrada.gz, entrada.etag,
                         entrada.mensaje, eventos)

    # ---- los hilos que leen ----

    def _trabajar(self):
        while True:
            entrada = self._cola.get()
            if entrada is None:
                return
            self._procesar(entrada)

    def procesar_pendientes(self):
        """Lee en este hilo todo lo encolado. Para las pruebas, sin hilos."""
        while True:
            try:
                entrada = self._cola.get_nowait()
            except queue.Empty:
                return
            if entrada is not None:
                self._procesar(entrada)

    def _procesar(self, entrada):
        try:
            self._refrescar(entrada)
        except Exception as e:  # noqa: BLE001 - un hilo que muere dejaría la web sin refresco
            nivel(self.log, "error")(
                f"  [{entrada.clave}] error inesperado: {type(e).__name__}: {e}\n"
                f"{traceback.format_exc().rstrip()}")
            self._fallar(entrada, f"error interno ({type(e).__name__})")
        finally:
            with self._candado:
                entrada.en_cola = False

    def _refrescar(self, entrada):
        inicio = self._reloj()
        eventos, datos, errores = [], {}, []

        for event_id in entrada.ids:
            try:
                meta = self.buscador.evento(event_id)
            except ErrorOrigen as e:
                if e.codigo == 404:
                    errores.append(e)
                    eventos.append({"id": event_id, "label": None, "name": None})
                    continue
                # Sin el título se puede seguir: se lee el schedule igualmente.
                nivel(self.log, "aviso")(
                    f"  [{entrada.clave}] sin título de {event_id} ({e}); se lee igualmente")
                meta = self.buscador.conocido(event_id) or {
                    "id": event_id, "title": f"Evento {event_id}"}

            evento = {"id": event_id, "label": None, "name": meta.get("title")}
            evento.update({k: meta[k] for k in METADATOS_EVENTO if meta.get(k)})
            eventos.append(evento)
            try:
                lectura = self._leer(self.cfg, event_id, base_url=meta.get("baseUrl"),
                                     log=self.log)
            except ErrorOrigen as e:
                errores.append(e)
                continue
            datos[event_id] = (lectura.dias, lectura.mats, lectura.combates_por_mat)
            evento["baseUrl"] = lectura.base_url   # el host al que redirigió smoothcomp.com

        base_url, lang = self.cfg["baseUrl"], self.cfg.get("lang", "en")
        grupo = self.grupos.leer(entrada.clave)

        if datos and errores:
            # Con otro evento de la vista leído esto no llega a `_fallar`: solo esta
            # línea deja constancia de que una parte de la vista no se pudo leer.
            nivel(self.log, "aviso")(
                f"  [{entrada.clave}] lectura parcial: {len(errores)} de "
                f"{len(entrada.ids)} eventos sin leer ({errores[0]})")

        if datos:
            estado = construir_estado(eventos=eventos, datos_por_evento=datos,
                                      fetched_at=ahora_iso(), grupo=grupo,
                                      base_url=base_url, lang=lang)
            for e in estado["events"]:
                e["published"] = e["id"] in datos
            self._guardar(entrada, estado)
            with self._candado:
                self._ultimo_exito = self._reloj()
            en_curso = sum(1 for m in estado["matches"] if m["state"] == "running")
            self.log(f"  [{entrada.clave}] {len(estado['matches'])} combates, "
                     f"{len(estado['athletes'])} atletas, {len(estado['mats'])} tatamis, "
                     f"{en_curso} en curso ({self._reloj() - inicio:.0f}s)")
        elif all(e.codigo == 404 for e in errores):
            self._guardar_inexistente(entrada, eventos)
        elif not any(_es_transitorio(e) for e in errores):
            # Existe pero el organizador aún no ha publicado el schedule.
            estado = estado_vacio(eventos, grupo=grupo, base_url=base_url, lang=lang)
            for e in estado["events"]:
                e["published"] = False
            self._guardar(entrada, estado)
            self.log(f"  [{entrada.clave}] sin schedule publicado")
        else:
            error = next(e for e in errores if _es_transitorio(e))
            mensaje = ("Smoothcomp está bloqueando las peticiones del servidor"
                       if error.desafio else str(error))
            nivel(self.log, "aviso")(f"  [{entrada.clave}] fallo: {error}")
            with self._candado:
                self._ultimo_error = (self._reloj(), error.codigo, bool(error.desafio))
            self._fallar(entrada, mensaje)

    # ---- resultados de una lectura ----

    def _serializar(self, estado, clave):
        """(cuerpo, gz, etag). Reaplica el grupo vigente justo antes de serializar."""
        aplicar_grupo(estado, self.grupos.leer(clave))
        cuerpo = json.dumps(estado, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        etag = '"' + hashlib.sha1(cuerpo).hexdigest()[:20] + '"'
        return cuerpo, gzip.compress(cuerpo, 6, mtime=0), etag

    def _guardar(self, entrada, estado):
        cuerpo, gz, etag = self._serializar(estado, entrada.clave)
        with self._candado:
            entrada.bueno = entrada.estado = estado
            entrada.cuerpo, entrada.gz, entrada.etag = cuerpo, gz, etag
            entrada.eventos = estado["events"]
            entrada.fase = "listo"
            entrada.mensaje = None
            entrada.fallos, entrada.primer_fallo = 0, None
            entrada.refrescado = self._reloj()

    def _guardar_inexistente(self, entrada, eventos):
        with self._candado:
            entrada.fase = "no_existe"
            entrada.mensaje = "Ese evento no existe en Smoothcomp"
            entrada.eventos = eventos
            entrada.refrescado = self._reloj()
        self.log(f"  [{entrada.clave}] no existe")

    def _fallar(self, entrada, mensaje):
        """Un intento fallido. Con copia anterior se sigue sirviendo, y tras unos
        cuantos fallos seguidos se marca como vieja: mejor que la web avise de que
        los datos están viejos a que mienta."""
        with self._candado:
            entrada.fallos += 1
            entrada.primer_fallo = entrada.primer_fallo or ahora_iso()
            entrada.mensaje = mensaje
            entrada.refrescado = self._reloj()
            if entrada.bueno is None:
                entrada.fase = "error"
                return
            marcar = (entrada.fallos >= self.limite_fallos
                      and entrada.estado is entrada.bueno)
            bueno, desde = entrada.bueno, entrada.primer_fallo

        if marcar:
            estado = marcar_stale(bueno, desde)
            cuerpo, gz, etag = self._serializar(estado, entrada.clave)
            with self._candado:
                entrada.estado = estado
                entrada.cuerpo, entrada.gz, entrada.etag = cuerpo, gz, etag
            nivel(self.log, "aviso")(f"  [{entrada.clave}] marcado stale desde {desde}")
