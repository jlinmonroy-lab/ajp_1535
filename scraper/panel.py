"""
Panel local: la web, más la capacidad de decidir a quién sigue todo el grupo.

La web publicada es estática, así que desde un móvil no se puede escribir nada.
El único sitio con permiso para cambiar lo que ven todos es este portátil, que
es donde corre el scraper. Este panel sirve la web en local y añade una API
mínima para tocar la lista del grupo en `config.json`; el scraper relee la
configuración en cada ciclo y la publica sin que haya que reiniciar nada.

Va en un proceso aparte del scraper a propósito: si el panel falla, el bucle que
alimenta la web sigue.

  GET  /api/grupo   -> la lista actual
  POST /api/grupo   -> {"id", "name", "accion": "añadir"|"quitar"}

Escucha **solo en 127.0.0.1**: en la wifi de un pabellón, abrirlo a la red
dejaría que cualquiera cambiara la lista de todos.

Uso:  python -m scraper.panel [--puerto 8765]
"""
import argparse
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.publish import escribir_json  # noqa: E402

CONFIG = RAIZ / "config.json"
SITIO = RAIZ / "site"
LIMITE_CUERPO = 64 * 1024  # más que de sobra para un atleta; evita sorpresas


def leer_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def grupo_de(cfg):
    grupo = cfg.get("grupo") or {}
    return {"nombre": grupo.get("nombre") or "Nuestro equipo",
            "atletas": grupo.get("atletas") or []}


def actualizar_grupo(atleta_id, nombre, accion):
    """Añade o quita un atleta de la lista compartida. Devuelve la lista nueva."""
    cfg = leer_config()
    grupo = grupo_de(cfg)
    atletas = [a for a in grupo["atletas"] if a.get("id") != atleta_id]

    if accion == "añadir":
        atletas.append({"id": atleta_id, "name": nombre})
        atletas.sort(key=lambda a: (a.get("name") or "").lower())

    cfg["grupo"] = {"nombre": grupo["nombre"], "atletas": atletas}
    # Atómico: el scraper puede estar releyendo el fichero justo ahora.
    escribir_json(CONFIG, cfg, compacto=False)
    return cfg["grupo"]


class Handler(SimpleHTTPRequestHandler):
    """La web estática, más /api/grupo."""

    def log_message(self, *args):
        pass  # sin ruido: interesa el log del scraper, no el del panel

    def _json(self, codigo, cuerpo):
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        if self.path.rstrip("/") == "/api/grupo":
            try:
                return self._json(200, grupo_de(leer_config()))
            except (OSError, ValueError) as e:
                return self._json(500, {"error": f"no se pudo leer config: {e}"})
        return super().do_GET()

    def do_POST(self):
        if self.path.rstrip("/") != "/api/grupo":
            return self._json(404, {"error": "ruta desconocida"})

        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            largo = 0
        if largo <= 0 or largo > LIMITE_CUERPO:
            return self._json(400, {"error": "cuerpo ausente o demasiado grande"})

        try:
            peticion = json.loads(self.rfile.read(largo).decode("utf-8"))
        except (ValueError, UnicodeError):
            return self._json(400, {"error": "JSON inválido"})

        atleta_id = (peticion.get("id") or "").strip()
        accion = peticion.get("accion") or "añadir"
        if not atleta_id:
            return self._json(400, {"error": "falta el id del atleta"})
        if accion not in ("añadir", "quitar"):
            return self._json(400, {"error": "acción desconocida"})

        try:
            grupo = actualizar_grupo(atleta_id, peticion.get("name") or atleta_id, accion)
        except (OSError, ValueError) as e:
            return self._json(500, {"error": f"no se pudo guardar: {e}"})

        print(f"[grupo] {accion}: {peticion.get('name') or atleta_id} "
              f"({len(grupo['atletas'])} en la lista)", flush=True)
        return self._json(200, grupo)


def crear_servidor(puerto=8765):
    """El servidor listo para servir. Lanza OSError si el puerto está ocupado."""
    handler = partial(Handler, directory=str(SITIO))
    # Solo 127.0.0.1: en la wifi del pabellón, abrirlo a la red dejaría que
    # cualquiera cambiase lo que ve todo el grupo.
    return ThreadingHTTPServer(("127.0.0.1", puerto), handler)


def arrancar_en_hilo(puerto=8765, log=print):
    """Levanta el panel junto al scraper. Devuelve el servidor, o None si falla.

    Va en un hilo daemon para que un Ctrl+C cierre las dos cosas a la vez. Si el
    puerto está ocupado no se aborta nada: lo que no puede faltar es el bucle que
    alimenta la web.
    """
    try:
        servidor = crear_servidor(puerto)
    except OSError as e:
        log(f"  panel no disponible en el puerto {puerto} ({e}); sigo sin él")
        return None

    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    grupo = grupo_de(leer_config())
    log(f"Panel en http://127.0.0.1:{puerto} · grupo «{grupo['nombre']}»: "
        f"{len(grupo['atletas'])} atleta(s)")
    return servidor


def main():
    p = argparse.ArgumentParser(description="Panel local del grupo")
    p.add_argument("--puerto", type=int, default=8765)
    args = p.parse_args()

    servidor = crear_servidor(args.puerto)
    grupo = grupo_de(leer_config())
    print(f"Panel en http://127.0.0.1:{args.puerto}")
    print(f"Grupo «{grupo['nombre']}»: {len(grupo['atletas'])} atleta(s)")
    print("Ahí verás el botón «Seguir para todos»; en la web pública no aparece.")
    print("\nAVISO: esto es SOLO el panel. Sin `python -m scraper.main` corriendo,")
    print("lo que marques se guarda pero no se publica para nadie.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nPanel detenido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
