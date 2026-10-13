"""
Servidor: la web, la búsqueda de eventos y los datos de cada evento.

Sirve `site/` y una API JSON pequeña. Nunca lee Smoothcomp dentro de una
petición: el buscador contesta de su caché y el almacén de la suya, y son ellos
quienes (con un ritmo global) van a Smoothcomp. Ver docs/architecture.md.

  GET  /api/config                    -> {teamName, logo, zona: {nombre} | null, version}
  GET  /api/health                    -> estado ok | degradado (200) · error (503), contadores
  GET  /api/events/search            -> ?q=&when=upcoming|past|all&page=&zona=1
  GET  /api/events/{ids}/data         -> 202 cargando · 200 estado · 404 · 502
  GET  /api/events/{ids}/grupo        -> la lista del grupo de esa vista
  POST /api/events/{ids}/grupo        -> añadir/quitar; SOLO desde el panel local o
                                         con la clave de administrador (X-Admin-Token)
  GET  /api/admin                     -> 200 si la clave de administrador es válida
  POST /api/client-error              -> 204: un error ocurrido en el navegador, al registro
                                         (máx. 4 KB y 30 por minuto; ver INFORMES_POR_MINUTO)

`{ids}` es un id de evento (`33588`) o varios separados por comas (`1535,1526`).

Uso:  python -m scraper.servidor [--host 127.0.0.1] [--puerto 8765] [--origen URL]

En un alojamiento fijo se configura por entorno: `DATA_DIR` (dónde se guarda
grupos.json) y `ADMIN_TOKEN` (la clave que desbloquea el panel desde cualquier
dispositivo; sin ella solo vale el equipo del servidor). `GIT_SHA` es la versión
que se enseña en /api/health, y `LOG_LEVEL`, `LOG_FORMAT` y `LOG_FILE` el registro
(ver scraper/telemetria.py).
"""
import argparse
import gzip
import hmac
import ipaddress
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.almacen import Almacen, Saturado, normalizar_ids  # noqa: E402
from scraper.eventos import Buscador  # noqa: E402
from scraper.fetch import ErrorOrigen, configurar_ritmo  # noqa: E402
from scraper.grupos import Grupos  # noqa: E402
from scraper.sitio import TIPOS_MIME, aviso_sin_compilar, sitio_compilado  # noqa: E402
from scraper.telemetria import Limitador, configurar_logging, contadores, registro  # noqa: E402

CONFIG = RAIZ / "config.json"
SITIO = RAIZ / "site"
DATOS = RAIZ / "data"
LIMITE_CUERPO = 64 * 1024     # más que de sobra para un atleta
# Un cuerpo que pasa del límite se descarta, hasta este tope, antes de contestar 400:
# cerrar con datos sin leer hace que el sistema aborte la conexión y el cliente no ve el motivo.
MAX_DRENAJE = 1024 * 1024
PUERTO_POR_DEFECTO = 8765
# Código de salida de "no he podido arrancar" (puerto ocupado, config ilegible).
# Distinto de 1, que es lo que da Python al caerse con una excepción: el lanzador
# del día del torneo relanza lo segundo, pero repetir lo primero no arreglaría nada.
SALIDA_NO_ARRANCA = 3
BRANDING = {"teamName": "FC Team", "logo": "img/logo.png"}

RUTA_DATOS = re.compile(r"^/api/events/([^/]+)/data$")
RUTA_GRUPO = re.compile(r"^/api/events/([^/]+)/grupo$")

# Cabeceras que añaden los túneles y proxies. Si llegan, la petición no viene de
# quien está sentado delante del equipo, aunque la conexión salga de 127.0.0.1.
CABECERAS_DE_PROXY = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto",
                      "Forwarded", "X-Real-Ip", "True-Client-IP", "CF-Connecting-IP",
                      "CF-Ray", "Via")
HOSTS_LOCALES = ("localhost", "127.0.0.1", "::1")

# La clave de administrador viaja en esta cabecera, no en la URL. Al ser propia, el
# navegador pediría un OPTIONS antes de mandarla desde otra web, y aquí no se contesta.
CABECERA_CLAVE = "X-Admin-Token"
CLAVE_MIN_LARGO = 16

# Con cientos de móviles sondeando cada pocos segundos, una línea por petición ahogaría
# el registro: solo salen las que fallan o van lentas. El resto se cuenta y, con
# LOG_LEVEL=DEBUG, también se escribe.
PETICION_LENTA_MS = 1000
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

# Los errores que la web manda desde el navegador (POST /api/client-error). Cualquiera puede
# llamar a esa ruta: el tamaño y el ritmo están acotados para que no llene el registro.
LIMITE_INFORME = 4 * 1024
INFORMES_POR_MINUTO = 30
TIPOS_INFORME = ("render", "js", "promesa", "datos")
LARGO_INFORME = {"mensaje": 300, "ruta": 200, "build": 40, "ua": 150}
MAX_PILA = 1500
MAX_LINEAS_PILA = 6


class _Servidor(ThreadingHTTPServer):
    # En Windows, SO_REUSEADDR deja que dos procesos abran el mismo puerto sin
    # error: el segundo servidor "arrancaría" y nadie sabría cuál contesta. En
    # Linux hace falta para poder reiniciar sin esperar al TIME_WAIT.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


log = registro   # un `log(mensaje)` más, con fecha y nivel: ver scraper/telemetria.py


def version_de_build():
    """El commit con el que se construyó la imagen (`--build-arg GIT_SHA=...`), o "dev"."""
    return os.environ.get("GIT_SHA") or "dev"


def cargar_config(ruta=CONFIG, origen=None):
    cfg = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if origen:
        cfg["baseUrl"] = origen.rstrip("/")
    return cfg


def _es_loopback(ip):
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if getattr(direccion, "ipv4_mapped", None):
        direccion = direccion.ipv4_mapped
    return direccion.is_loopback


def _host_de(cabecera):
    """'localhost:8765' -> 'localhost'; '[::1]:8765' -> '::1'."""
    try:
        return (urllib.parse.urlsplit("//" + (cabecera or "")).hostname or "").lower()
    except ValueError:
        return ""


def es_panel_local(handler):
    """¿Viene esta petición de quien tiene el equipo delante?

    Con un túnel (cloudflared, ngrok) todas las peticiones llegan por 127.0.0.1,
    así que la IP sola no basta. Se exige además que el `Host` sea el local, que
    no haya cabeceras de proxy y, contra las webs que el navegador del operador
    pueda abrir, que un `Origin` presente sea el propio servidor.
    """
    if not _es_loopback(handler.client_address[0]):
        return False
    host = _host_de(handler.headers.get("Host"))
    if host not in HOSTS_LOCALES:
        return False
    if any(handler.headers.get(c) for c in CABECERAS_DE_PROXY):
        return False
    origen = handler.headers.get("Origin")
    if origen is not None and _host_de(origen.split("://", 1)[-1]) != host:
        return False
    return True


def _texto_del_navegador(valor, largo):
    """Lo que manda el navegador es entrada no fiable: texto, corto y sin caracteres de control."""
    return _CONTROL.sub("?", valor[:largo]) if isinstance(valor, str) else ""


def linea_de_informe(informe):
    """El informe de un error del navegador como texto de registro: una línea y su pila."""
    tipo = informe.get("tipo")
    campos = {k: _texto_del_navegador(informe.get(k), n) for k, n in LARGO_INFORME.items()}
    linea = (f"cliente [{tipo if tipo in TIPOS_INFORME else 'otro'}] {campos['mensaje']}"
             f" · {campos['ruta']} · build {campos['build']} · {campos['ua']}")
    pila = informe.get("pila")
    if isinstance(pila, str):
        lineas = pila[:MAX_PILA].splitlines()[:MAX_LINEAS_PILA]
        linea += "".join("\n    " + _texto_del_navegador(p, 200).strip() for p in lineas)
    return linea


def ip_cliente(handler):
    """La IP para el registro. Tras Fly o un túnel la conexión llega del proxy, así que
    se prefiere lo que este dice. Solo sirve para leer el registro: no decide nada."""
    for cabecera in ("Fly-Client-IP", "X-Forwarded-For"):
        valor = handler.headers.get(cabecera)
        if valor:
            return _CONTROL.sub("?", valor.split(",")[0].strip())[:45]
    return handler.client_address[0]


def tiene_clave(handler, clave):
    """¿Trae la petición la clave de administrador? Sin clave configurada, nunca."""
    if not clave:
        return False
    recibida = handler.headers.get(CABECERA_CLAVE) or ""
    return hmac.compare_digest(recibida.encode("utf-8"), clave.encode("utf-8"))


# Lo que merece la pena comprimir de la web: texto. Las imágenes ya vienen comprimidas.
COMPRIMIBLES = (".html", ".js", ".mjs", ".css", ".json", ".svg", ".txt")


def _coincide(if_none_match, etag):
    """¿Alguno de los ETag del cliente es este? Se comparan como débiles."""
    debil = lambda e: e.strip().removeprefix("W/")  # noqa: E731
    return any(debil(e) == debil(etag) for e in if_none_match.split(","))


def crear_servidor(cfg, host, puerto, buscador, almacen, grupos, sitio=SITIO,
                   clave_admin=None, version=None, limitador=None):
    """El servidor listo para servir. Lanza OSError si el puerto está ocupado.

    Con `clave_admin`, quien la mande en `X-Admin-Token` puede cambiar la lista del
    grupo desde cualquier sitio, además del equipo del servidor.
    """
    comprimidos = {}     # ruta -> ((mtime, tamaño), gzip): la web comprimida, una vez por versión
    branding = {**BRANDING, **(cfg.get("branding") or {})}
    version = version or version_de_build()
    limitador = limitador or Limitador(INFORMES_POR_MINUTO, 60)
    arrancado = time.monotonic()
    # La web solo necesita saber que hay una zona por defecto y cómo se llama.
    zona = cfg.get("zona")
    config_web = {**branding,
                  "zona": {"nombre": zona.get("nombre")} if isinstance(zona, dict) else None,
                  "version": version}
    if clave_admin:
        config_web["admin"] = True    # la web ofrece entrar con la clave

    class Handler(SimpleHTTPRequestHandler):
        # Sin tiempo máximo, un cliente que declara un cuerpo y no lo manda dejaría
        # un hilo esperando para siempre.
        timeout = 30
        # Los módulos de la web exigen un tipo de JavaScript (ver scraper/sitio.py).
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map, **TIPOS_MIME}

        # ---- el registro de accesos ----

        def parse_request(self):
            self._inicio = time.monotonic()
            self._motivo = None      # lo rellena `_error`: por qué se contestó con un fallo
            return super().parse_request()

        def _ruta_para_log(self):
            """La ruta sin la query (puede llevar lo que se busca) y sin caracteres de control."""
            ruta = urllib.parse.urlsplit(getattr(self, "path", None) or "").path
            return _CONTROL.sub("?", ruta[:200])

        def log_request(self, code="-", size="-"):
            """Una línea por respuesta, con su código y lo que tardó."""
            try:
                codigo = int(code)
            except (TypeError, ValueError):
                codigo = 0
            ms = (time.monotonic() - getattr(self, "_inicio", time.monotonic())) * 1000
            contadores.sumar(f"http_{codigo // 100}xx")
            contadores.sumar(f"http_{codigo}")
            linea = f"{self.command or '-'} {self._ruta_para_log()} {codigo} {ms:.0f}ms"
            motivo = getattr(self, "_motivo", None)
            if motivo and codigo >= 400:
                linea += f" · {motivo}"
            if codigo >= 500:
                registro.aviso(linea)
            elif codigo >= 400 or ms >= PETICION_LENTA_MS:
                registro(linea)
            else:
                registro.depurar(linea)

        def log_message(self, formato, *args):
            """Lo que `http.server` cuenta por su cuenta: peticiones mal formadas, tiempos agotados.
            Los "code 404, message ..." de `send_error` ya salen en `log_request`."""
            try:
                texto = formato % args
            except (TypeError, ValueError):
                texto = str(formato)
            texto = _CONTROL.sub("?", texto)[:300]
            if formato.startswith("code "):
                return registro.depurar(f"http: {texto}")
            registro.aviso(f"http: {texto}")

        def end_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            # Con la web abierta a internet, ningún buscador debe indexarla: nombres de
            # atletas, a veces menores. Complementa el <meta> y el robots.txt de site/.
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            # Sin esto el navegador cachearía el JS y no vería una versión nueva.
            if "Cache-Control" not in self._cabeceras_enviadas:
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def send_header(self, clave, valor):
            self._cabeceras_enviadas.add(clave)
            super().send_header(clave, valor)

        def send_response(self, codigo, mensaje=None):
            self._cabeceras_enviadas = set()
            super().send_response(codigo, mensaje)

        # ---- respuestas ----

        def _json(self, codigo, cuerpo, cabeceras=None):
            datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
            self._enviar(codigo, datos, "application/json; charset=utf-8", cabeceras)

        def _enviar(self, codigo, datos, tipo, cabeceras=None):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(datos)))
            for clave, valor in (cabeceras or {}).items():
                self.send_header(clave, valor)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(datos)

        def _error(self, codigo, mensaje, cabeceras=None):
            self._motivo = mensaje      # `log_request` lo añade a la línea de acceso
            self._json(codigo, {"error": mensaje}, cabeceras)

        # ---- la web estática ----

        def _estatico(self):
            """La web compilada. Si el cliente admite gzip y el fichero es de texto se manda
            comprimida: el JavaScript de React pesa ~250 KB y ~80 KB con gzip, y por datos
            móviles se nota. Cada fichero se comprime una vez por versión; se revalida con
            ETag, porque con `Cache-Control: no-cache` cada visita pregunta si cambió."""
            ruta = self.translate_path(self.path)   # ya impide salir de la carpeta del sitio
            if (os.path.splitext(ruta)[1].lower() not in COMPRIMIBLES
                    or "gzip" not in self.headers.get("Accept-Encoding", "")
                    or not os.path.isfile(ruta)):
                return super().do_GET()

            try:
                estado = os.stat(ruta)
                version = (estado.st_mtime_ns, estado.st_size)
                guardado = comprimidos.get(ruta)
                if guardado is None or guardado[0] != version:
                    with open(ruta, "rb") as f:
                        guardado = (version, gzip.compress(f.read(), compresslevel=9, mtime=0))
                    comprimidos[ruta] = guardado
            except OSError:
                return super().do_GET()

            etag = f'W/"{version[0]:x}-{version[1]:x}"'
            cabeceras = {"ETag": etag, "Vary": "Accept-Encoding"}
            if _coincide(self.headers.get("If-None-Match", ""), etag):
                self.send_response(304)
                for clave, valor in cabeceras.items():
                    self.send_header(clave, valor)
                self.end_headers()
                return
            cabeceras["Content-Encoding"] = "gzip"
            self._enviar(200, guardado[1], self.guess_type(ruta), cabeceras)

        # ---- GET ----

        def do_GET(self):
            self._protegido(self._get)

        def do_POST(self):
            self._protegido(self._post)

        def do_HEAD(self):
            # Los monitores de disponibilidad suelen preguntar con HEAD. Lo demás es la
            # web estática, que ya sabe contestar a HEAD.
            if urllib.parse.urlsplit(self.path).path == "/api/health":
                return self._protegido(self._get)
            super().do_HEAD()

        def _protegido(self, atender):
            """Una excepción inesperada es un 500 con cuerpo, no una conexión cortada."""
            try:
                atender()
            except (BrokenPipeError, ConnectionResetError):
                raise
            except Exception as e:  # noqa: BLE001
                registro.error(f"error atendiendo {self.command} {self._ruta_para_log()}: "
                               f"{type(e).__name__}: {e}\n{traceback.format_exc().rstrip()}")
                self._error(500, "error interno del servidor")

        def _get(self):
            partes = urllib.parse.urlsplit(self.path)
            ruta = urllib.parse.unquote(partes.path)
            if not ruta.startswith("/api/"):
                return self._estatico()

            if ruta == "/api/config":
                return self._json(200, config_web)
            if ruta == "/api/health":
                return self._health()
            if ruta == "/api/admin":
                if tiene_clave(self, clave_admin):
                    return self._json(200, {"admin": True})
                if self.headers.get(CABECERA_CLAVE):
                    registro.aviso("admin: rechazada una clave de administrador incorrecta "
                                   f"({ip_cliente(self)})")
                return self._error(403, "clave de administrador incorrecta")
            if ruta == "/api/events/search":
                return self._buscar(urllib.parse.parse_qs(partes.query))
            if m := RUTA_DATOS.match(ruta):
                return self._datos(m.group(1))
            if m := RUTA_GRUPO.match(ruta):
                return self._ver_grupo(m.group(1))
            self._error(404, "ruta desconocida")

        def _health(self):
            """Para el check de Fly y para un monitor externo. No toca Smoothcomp.

            503 solo si algo está roto de verdad: un hilo del almacén muerto o la web sin
            compilar. Unos datos viejos (Smoothcomp caído o bloqueando) son "degradado"
            con 200, porque reiniciar la máquina no lo arregla y vaciaría la caché.
            """
            resumen = almacen.resumen()
            compilado = sitio_compilado(sitio)
            if resumen["workersVivos"] < resumen["workers"] or not compilado:
                estado = "error"
            elif resumen["eventosStale"] or resumen["eventosConError"]:
                estado = "degradado"
            else:
                estado = "ok"
            self._json(503 if estado == "error" else 200, {
                "estado": estado, "version": version,
                "uptimeS": round(time.monotonic() - arrancado),
                "sitioCompilado": compilado, **resumen,
                "contadores": contadores.todos()})

        def _buscar(self, params):
            def uno(nombre, defecto):
                return (params.get(nombre) or [defecto])[0]

            try:
                resultado = buscador.buscar(uno("q", ""), uno("when", "upcoming"),
                                            uno("page", "1"),
                                            zona=uno("zona", "") in ("1", "true"))
            except ValueError as e:
                return self._error(400, str(e))
            except ErrorOrigen as e:
                if e.desafio:
                    return self._error(502, "Smoothcomp está bloqueando la búsqueda. "
                                            "Puedes abrir el evento pegando su número o su enlace.")
                return self._error(502, f"No se pudo consultar Smoothcomp ({e})")
            self._json(200, resultado)

        def _datos(self, ids):
            try:
                r = almacen.pedir(urllib.parse.unquote(ids))
            except ValueError as e:
                return self._error(400, str(e))
            except Saturado as e:
                return self._error(503, str(e), {"Retry-After": "10"})

            if r.fase == "cargando":
                return self._json(202, {"status": "loading", "events": r.eventos},
                                  {"Retry-After": "3"})
            if r.fase == "no_existe":
                return self._error(404, r.mensaje)
            if r.fase == "error":
                return self._error(502, r.mensaje or "No se pudo leer el evento")

            # Débil: el cuerpo es el mismo con o sin gzip.
            etag = "W/" + r.etag
            if _coincide(self.headers.get("If-None-Match", ""), etag):
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return
            cabeceras = {"ETag": etag, "Vary": "Accept-Encoding"}
            if "gzip" in self.headers.get("Accept-Encoding", ""):
                cabeceras["Content-Encoding"] = "gzip"
                return self._enviar(200, r.gz, "application/json; charset=utf-8", cabeceras)
            self._enviar(200, r.cuerpo, "application/json; charset=utf-8", cabeceras)

        def _ver_grupo(self, ids):
            try:
                clave, _ = normalizar_ids(urllib.parse.unquote(ids))
            except ValueError as e:
                return self._error(400, str(e))
            self._json(200, grupos.leer(clave))

        # ---- POST ----

        def _informe_del_cliente(self, cuerpo):
            """Un error que ha ocurrido en el navegador de alguien, al registro del servidor.

            No hay clave: lo manda la propia web, en cualquier móvil. Se acota lo que se acepta
            (tamaño, origen, ritmo) y se registra solo texto limpio y recortado."""
            if len(cuerpo) > LIMITE_INFORME:
                return self._error(413, "informe demasiado grande")
            origen = self.headers.get("Origin")
            if origen is not None and (_host_de(origen.split("://", 1)[-1])
                                       != _host_de(self.headers.get("Host"))):
                return self._error(403, "solo desde la propia web")
            if not limitador.permitir():
                contadores.sumar("cliente_errores_descartados")
                return self._error(429, "demasiados informes", {"Retry-After": "60"})
            try:
                informe = json.loads(cuerpo.decode("utf-8"))
                if not isinstance(informe, dict):
                    raise ValueError
            except (ValueError, UnicodeError):
                return self._error(400, "JSON inválido")

            contadores.sumar("cliente_errores")
            registro.aviso(linea_de_informe(informe))
            # 204: sin cuerpo y, por eso, sin Content-Length.
            self.send_response(204)
            self.end_headers()

        def _post(self):
            # El cuerpo se lee siempre, aunque la petición vaya a rechazarse (también
            # si la ruta no existe): cerrar la conexión con datos sin leer hace que el
            # sistema la aborte y el cliente se quede sin ver el motivo del rechazo.
            try:
                largo = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                largo = 0
            if largo > LIMITE_CUERPO:
                restante = min(largo, MAX_DRENAJE)
                while restante > 0:
                    trozo = self.rfile.read(min(restante, 64 * 1024))
                    if not trozo:
                        break
                    restante -= len(trozo)
                self.close_connection = True
                return self._error(400, "cuerpo ausente o demasiado grande")
            cuerpo = self.rfile.read(largo) if largo > 0 else b""

            ruta = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            if ruta == "/api/client-error":
                return self._informe_del_cliente(cuerpo)
            m = RUTA_GRUPO.match(ruta)
            if not m:
                return self._error(404, "ruta desconocida")

            if not (es_panel_local(self) or tiene_clave(self, clave_admin)):
                motivo = ("rechazada una clave de administrador incorrecta"
                          if self.headers.get(CABECERA_CLAVE) else "petición sin permiso")
                registro.aviso(f"grupo: {motivo} ({ip_cliente(self)})")
                return self._error(403, "solo se puede cambiar desde el equipo del servidor "
                                        "o con la clave de administrador")
            # Un formulario de otra web no puede mandar JSON sin permiso del servidor
            # (el navegador pediría antes un OPTIONS, que aquí no se contesta).
            tipo = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if tipo != "application/json":
                return self._error(415, "el cuerpo debe ser application/json")
            try:
                clave, _ = normalizar_ids(m.group(1))
            except ValueError as e:
                return self._error(400, str(e))
            if not cuerpo:
                return self._error(400, "cuerpo ausente o demasiado grande")
            try:
                peticion = json.loads(cuerpo.decode("utf-8"))
                if not isinstance(peticion, dict):
                    raise ValueError
            except (ValueError, UnicodeError):
                return self._error(400, "JSON inválido")

            try:
                grupo = grupos.actualizar(
                    clave, peticion.get("accion") or "añadir",
                    atleta_id=peticion.get("id"), nombre=peticion.get("name"),
                    club=peticion.get("club"))
            except ValueError as e:
                return self._error(400, str(e))
            except OSError as e:
                return self._error(500, f"no se pudo guardar: {e}")

            almacen.regrupar(clave)
            # Sin el atleta: son nombres, a veces de menores, y el registro de la
            # plataforma se guarda fuera de nuestro control. La lista está en grupos.json.
            origen = "panel local" if es_panel_local(self) else "clave"
            log(f"[grupo {clave}] {peticion.get('accion') or 'añadir'} "
                f"({len(grupo['atletas'])} en la lista) · {origen} · {ip_cliente(self)}")
            self._json(200, grupo)

    return _Servidor((host, puerto), partial(Handler, directory=str(sitio)))


def main(argv=None):
    p = argparse.ArgumentParser(description="Servidor del seguimiento de eventos de Smoothcomp")
    p.add_argument("--host", default="127.0.0.1",
                   help="por defecto solo este equipo; 0.0.0.0 para abrirlo a la red local")
    p.add_argument("--puerto", type=int, help=f"por defecto {PUERTO_POR_DEFECTO}")
    p.add_argument("--config", default=str(CONFIG))
    p.add_argument("--origen", help="URL base de Smoothcomp (para ensayar con el origen simulado)")
    args = p.parse_args(argv)

    try:
        cfg = cargar_config(args.config, args.origen)
    except (OSError, ValueError) as e:
        print(f"No se pudo leer la configuración {args.config} ({e}).")
        return SALIDA_NO_ARRANCA
    clave_admin = os.environ.get("ADMIN_TOKEN") or None
    if clave_admin and len(clave_admin) < CLAVE_MIN_LARGO:
        print(f"ADMIN_TOKEN es demasiado corta: mínimo {CLAVE_MIN_LARGO} caracteres. "
              "Una clave fácil de adivinar dejaría la lista del grupo abierta a todo internet.")
        return SALIDA_NO_ARRANCA
    puerto = args.puerto or (cfg.get("servidor") or {}).get("puerto", PUERTO_POR_DEFECTO)
    configurar_logging()
    configurar_ritmo(cfg.get("requestPauseSeconds", 2.0))

    # En un alojamiento fijo el disco del programa se borra en cada despliegue; los
    # datos van a un volumen aparte.
    datos = Path(os.environ.get("DATA_DIR") or DATOS)
    grupos = Grupos(datos / "grupos.json", log=log)
    try:
        buscador = Buscador(cfg, log=log)
    except ValueError as e:      # la zona de config.json está mal escrita
        print(f"Configuración incorrecta en {args.config}: {e}")
        return SALIDA_NO_ARRANCA
    almacen = Almacen(cfg, buscador, grupos, log=log)
    try:
        servidor = crear_servidor(cfg, args.host, puerto, buscador, almacen, grupos,
                                  clave_admin=clave_admin)
    except OSError as e:
        print(f"No se pudo abrir {args.host}:{puerto} ({e}). ¿Ya hay otro servidor en marcha?")
        return SALIDA_NO_ARRANCA

    log(f"Servidor en http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{puerto}"
        f" · origen {cfg['baseUrl']} · versión {version_de_build()}")
    if args.host == "0.0.0.0":
        log("Abierto a la red. El panel de grupo se desbloquea con la clave de administrador."
            if clave_admin else
            "Abierto a la red local. El panel de grupo sigue limitado a este equipo.")
    log(f"Datos del grupo en {datos / 'grupos.json'}")
    if not sitio_compilado(SITIO):
        # La API funciona igual, pero quien abra la dirección verá un 404.
        log(f"AVISO: {aviso_sin_compilar(SITIO)}")
    if buscador.zona:
        log(f"Buscador acotado por defecto a: {buscador.zona.nombre}")
    log(f"Refresco de cada evento: {cfg.get('refreshSeconds', 75)} s · "
        f"pausa entre peticiones a Smoothcomp: {cfg.get('requestPauseSeconds', 2.0)} s")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido.")
    finally:
        almacen.cerrar()
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
