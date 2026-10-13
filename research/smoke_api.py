"""
Prueba de humo de un servidor ya desplegado: ¿está sirviendo la web y la API de verdad?

Se pasa tras un `fly deploy` (o en CI, contra el contenedor recién construido) para no enterarse
el día del torneo de que algo quedó roto. Solo biblioteca estándar y no necesita navegador. Mira
lo que ya ha fallado alguna vez sin hacer ruido en el servidor:

  - /api/health responde, con la versión que se acaba de desplegar (`--esperar-version`).
  - /api/config da la misma versión (es el mismo proceso).
  - La página principal existe y sus ficheros (JS, CSS) se sirven con el tipo MIME correcto: con
    un .js como text/plain el navegador se niega a ejecutarlo y la web queda en blanco, sin
    ningún error en el servidor (ver scraper/sitio.py).
  - Todo lleva `X-Robots-Tag: noindex`: los datos son nombres reales de atletas.
  - La búsqueda llega a Smoothcomp desde esa IP. Un fallo aquí es un AVISO, no un fallo: es la
    señal de que Cloudflare bloquea al servidor (ver «La prueba que importa» en el README).

Código de salida: 0 todo bien · 1 hay fallos · 2 solo avisos (p. ej. `degradado`, Smoothcomp caído).

Uso:  python research/smoke_api.py https://fcteam-competicion.fly.dev --esperar-version abc1234
      python research/smoke_api.py http://127.0.0.1:8765 --omitir-busqueda
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple

ESPERA_ENTRE_INTENTOS_S = 2
TIMEOUT_BUSQUEDA_S = 30     # la primera búsqueda lee la lista de Smoothcomp: puede tardar
UA = "smoke-api/1.0 (eventos_bjj)"

Respuesta = namedtuple("Respuesta", "estado cabeceras cuerpo ms")


class ErrorDeConexion(Exception):
    """No hubo respuesta HTTP: servidor parado, DNS, tiempo agotado."""


def pedir(url, metodo="GET", timeout=10):
    """Una petición. Un 4xx/5xx es una respuesta, no un error: se devuelve igual."""
    peticion = urllib.request.Request(url, method=metodo, headers={
        "User-Agent": UA, "Accept-Encoding": "identity"})
    inicio = time.monotonic()
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as r:
            estado, cabeceras, cuerpo = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        estado, cabeceras, cuerpo = e.code, e.headers, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise ErrorDeConexion(str(getattr(e, "reason", e))) from e
    return Respuesta(estado, cabeceras, cuerpo, round((time.monotonic() - inicio) * 1000))


def _json(respuesta):
    try:
        datos = json.loads(respuesta.cuerpo.decode("utf-8"))
    except (ValueError, UnicodeError):
        return None
    return datos if isinstance(datos, dict) else None


class Informe:
    def __init__(self, salida):
        self.salida = salida
        self.fallos = 0
        self.avisos = 0

    def ok(self, texto):
        self.salida(f"OK     {texto}")

    def aviso(self, texto):
        self.avisos += 1
        self.salida(f"AVISO  {texto}")

    def fallo(self, texto):
        self.fallos += 1
        self.salida(f"FALLO  {texto}")

    def codigo(self):
        return 1 if self.fallos else 2 if self.avisos else 0


def esperar_health(base, esperar_version, espera, timeout, dormir, reloj):
    """(respuesta, datos) del /api/health cuando contesta 200 (y con la versión pedida), o
    (None, motivo) si no lo consigue en `espera` segundos. Un servidor que está arrancando o
    relevando una máquina falla un rato: se insiste en vez de dar la falsa alarma."""
    limite = reloj() + espera
    while True:
        try:
            r = pedir(f"{base}/api/health", timeout=timeout)
            datos = _json(r)
            version = datos.get("version") if datos else None
            if r.estado == 200 and datos and (not esperar_version or version == esperar_version):
                return r, datos
            motivo = f"HTTP {r.estado}, estado {datos.get('estado') if datos else '?'}, versión {version}"
        except ErrorDeConexion as e:
            motivo = f"sin conexión ({e})"
        if reloj() >= limite:
            return None, motivo
        dormir(ESPERA_ENTRE_INTENTOS_S)


def _recursos(html):
    """(dirección, tipo que debe tener) de lo que la página carga. El tipo lo marca cómo se
    referencia (un <script> es JavaScript lo diga su extensión o no), que es lo que mira el navegador."""
    recursos = [(url, "javascript") for url in re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', html)]
    for etiqueta in re.findall(r"<link\b[^>]*>", html):
        rel = re.search(r'\brel="(stylesheet|modulepreload)"', etiqueta)
        href = re.search(r'\bhref="([^"]+)"', etiqueta)
        if rel and href:
            recursos.append((href.group(1), "text/css" if rel.group(1) == "stylesheet" else "javascript"))
    return recursos


def _tipo(respuesta):
    return (respuesta.cabeceras.get("Content-Type") or "").split(";")[0].strip().lower()


def verificar(base, *, esperar_version=None, espera=30, omitir_busqueda=False, timeout=10,
              salida=print, dormir=time.sleep, reloj=time.monotonic):
    """Ejecuta todas las comprobaciones. Devuelve el código de salida (0, 1 o 2)."""
    base = base.rstrip("/")
    informe = Informe(salida)

    # --- /api/health: sin esto no se puede seguir ---
    r, datos = esperar_health(base, esperar_version, espera, timeout, dormir, reloj)
    if r is None:
        que = f"con la versión {esperar_version} " if esperar_version else ""
        informe.fallo(f"/api/health no llegó a contestar 200 {que}en {espera} s (último intento: {datos})")
        salida(f"Resultado: {informe.fallos} fallo(s), {informe.avisos} aviso(s)")
        return informe.codigo()
    version = datos.get("version")
    estado = datos.get("estado")
    informe.ok(f"/api/health 200 ({r.ms} ms) - estado {estado}, versión {version}")
    if estado == "degradado":
        origen = datos.get("origen") or {}
        informe.aviso(
            f"el servidor está degradado: {datos.get('eventosStale')} evento(s) con datos viejos, "
            f"{datos.get('eventosConError')} sin poder leerse; último error de Smoothcomp: "
            f"{origen.get('ultimoErrorCodigo')} (reto de Cloudflare: {origen.get('ultimoErrorReto')})")
    elif estado != "ok":
        informe.fallo(f"/api/health dice estado «{estado}»")
    if esperar_version and version != esperar_version:
        informe.fallo(f"la versión desplegada es {version}, no {esperar_version}")

    try:
        _comprobar_cabecera(base, version, informe, timeout)
    except ErrorDeConexion as e:
        informe.fallo(f"se perdió la conexión a mitad de la prueba ({e})")
    if not omitir_busqueda:
        try:
            _comprobar_busqueda(base, informe)
        except ErrorDeConexion as e:
            informe.fallo(f"/api/events/search: sin conexión ({e})")

    salida(f"Resultado: {informe.fallos} fallo(s), {informe.avisos} aviso(s)")
    return informe.codigo()


def _comprobar_cabecera(base, version, informe, timeout):
    # HEAD: es lo que usan los monitores de disponibilidad.
    r = pedir(f"{base}/api/health", "HEAD", timeout)
    if r.estado == 200 and not r.cuerpo:
        informe.ok("HEAD /api/health 200")
    else:
        informe.fallo(f"HEAD /api/health devuelve {r.estado} con {len(r.cuerpo)} bytes de cuerpo")

    r = pedir(f"{base}/api/config", timeout=timeout)
    cabeceras_api = r.cabeceras
    config = _json(r)
    if r.estado != 200 or config is None:
        informe.fallo(f"/api/config devuelve {r.estado}, no un JSON")
    elif config.get("version") != version:
        informe.fallo(f"/api/config da la versión {config.get('version')} y /api/health {version}")
    else:
        informe.ok(f"/api/config 200 ({r.ms} ms) - equipo «{config.get('teamName')}»")

    if "noindex" not in (cabeceras_api.get("X-Robots-Tag") or ""):
        informe.fallo("la API no lleva X-Robots-Tag: noindex")

    # La página y lo que carga.
    r = pedir(f"{base}/", timeout=timeout)
    html = r.cuerpo.decode("utf-8", errors="replace")
    if r.estado != 200 or not _tipo(r).startswith("text/html"):
        informe.fallo(f"/ devuelve {r.estado} ({_tipo(r) or 'sin tipo'}): ¿está compilada la web?")
        return
    informe.ok(f"/ 200 ({r.ms} ms)")
    if 'id="raiz"' not in html:
        informe.fallo('la página no tiene <div id="raiz">: no es la web de seguimiento')
    if "noindex" not in (r.cabeceras.get("X-Robots-Tag") or ""):
        informe.fallo("/ no lleva X-Robots-Tag: noindex (los datos llevan nombres reales)")
    recursos = _recursos(html)
    if not any(esperado == "javascript" for _, esperado in recursos):
        informe.fallo("la página no referencia ningún script: saldría en blanco")
    for ref, esperado in recursos:
        recurso = pedir(urllib.parse.urljoin(f"{base}/", ref), timeout=timeout)
        tipo = _tipo(recurso)
        if recurso.estado != 200 or not recurso.cuerpo:
            informe.fallo(f"{ref} devuelve {recurso.estado} con {len(recurso.cuerpo)} bytes")
        elif esperado not in tipo:
            informe.fallo(f"{ref} se sirve como «{tipo}»: el navegador lo rechazaría "
                          f"({'un script' if esperado == 'javascript' else 'una hoja de estilo'})")
        else:
            informe.ok(f"{ref} 200 ({tipo}, {len(recurso.cuerpo) / 1024:.0f} KB)")


def _comprobar_busqueda(base, informe):
    r = pedir(f"{base}/api/events/search?when=upcoming", timeout=TIMEOUT_BUSQUEDA_S)
    datos = _json(r)
    if r.estado == 200 and datos is not None and isinstance(datos.get("events"), list):
        informe.ok(f"/api/events/search 200 ({r.ms} ms) - {len(datos['events'])} evento(s)"
                   + (" (copia vieja: Smoothcomp falló)" if datos.get("stale") else ""))
        if datos.get("stale"):
            informe.aviso("la búsqueda sirve una copia vieja: Smoothcomp no está contestando")
    elif r.estado == 502:
        motivo = (datos or {}).get("error", "sin detalle")
        informe.aviso(f"la búsqueda no llega a Smoothcomp desde ese servidor: {motivo}")
    else:
        informe.fallo(f"/api/events/search devuelve {r.estado}, no una lista de eventos")


def main(argv=None):
    p = argparse.ArgumentParser(description="Prueba de humo de un servidor desplegado")
    p.add_argument("url", help="dirección del servidor, p. ej. https://fcteam-competicion.fly.dev")
    p.add_argument("--esperar-version", metavar="SHA",
                   help="espera a que /api/health diga esta versión (el GIT_SHA recién desplegado)")
    p.add_argument("--espera", type=int, default=30, metavar="S",
                   help="segundos máximos esperando a que el servidor conteste (por defecto 30)")
    p.add_argument("--omitir-busqueda", action="store_true",
                   help="no probar la búsqueda: no tocar Smoothcomp (para CI)")
    p.add_argument("--timeout", type=int, default=10, metavar="S", help="tiempo máximo por petición")
    args = p.parse_args(argv)
    if not args.url.startswith(("http://", "https://")):
        p.error("la dirección debe empezar por http:// o https://")
    # Los mensajes del servidor se citan tal cual: en una consola que no sepa pintar algún
    # carácter, que salga un «?» en vez de abortar la prueba a medias.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    return verificar(args.url, esperar_version=args.esperar_version, espera=args.espera,
                     omitir_busqueda=args.omitir_busqueda, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main())
