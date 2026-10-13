"""
La web compilada (`site/`) y cómo se sirve.

`site/` no está en el repositorio: la genera `npm --prefix web run build` (en Fly, el
Dockerfile). Este módulo reúne lo que comparten quienes la sirven (servidor, panel) o
dependen de ella (el lanzador del día del torneo).
"""
from pathlib import Path

COMPILAR = "npm --prefix web ci && npm --prefix web run build"

# Vite emite la web con <script type="module">, y un módulo se rechaza si llega con un
# tipo que no es JavaScript (con `X-Content-Type-Options: nosniff` no hay segunda
# oportunidad). Python deduce el tipo del registro de Windows, donde un .js puede figurar
# como text/plain: la página quedaría en blanco sin ningún error en el servidor. Se fijan
# aquí, y mandan sobre el registro (`SimpleHTTPRequestHandler.extensions_map`).
TIPOS_MIME = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


def sitio_compilado(sitio: Path) -> bool:
    """¿Hay una web que servir? Basta con su página de entrada."""
    return (Path(sitio) / "index.html").is_file()


def aviso_sin_compilar(sitio: Path) -> str:
    return (f"La web no está compilada: no existe {Path(sitio) / 'index.html'}. "
            f"Compílala con:  {COMPILAR}")
