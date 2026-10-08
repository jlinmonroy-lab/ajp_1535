"""
La dirección pública de la web, cuando se publica con Tailscale Funnel.

Este equipo no tiene IP pública, así que para que los móviles entren con sus datos
se usa un túnel. Aquí solo se **lee** su estado (`tailscale funnel status`) para
poder decir cuál es el enlace que repartir y avisar si no está puesto. Nada de esto
cambia la configuración del túnel.

El 443 de este Funnel lo usa otro servicio, así que la web va por el 8443 (Funnel
admite 443, 8443 y 10000). Ver el README, «Para todo el equipo».
"""
import os
import re
import shutil
import subprocess

PUERTO_FUNNEL = 8443

# "https://host:8443 (Funnel on)" y debajo "|-- / proxy http://127.0.0.1:8765".
# Un "(tailnet only)" no cuenta: eso solo lo ven los dispositivos del propio tailnet.
_PUBLICA = re.compile(r"^(https://\S+)\s+\(Funnel on\)", re.IGNORECASE)
_RUTA = re.compile(r"^\|--\s+(\S+)\s+proxy\s+https?://(?:127\.0\.0\.1|localhost|\[::1\]):(\d+)",
                   re.IGNORECASE)
_RUTAS_CONOCIDAS = (r"C:\Program Files\Tailscale\tailscale.exe",)


def enlace_funnel(texto, puerto):
    """La URL pública que apunta al `puerto` local, o None.

    `texto` es la salida de `tailscale funnel status`.
    """
    actual = None
    for linea in (texto or "").splitlines():
        linea = linea.strip()
        if m := _PUBLICA.match(linea):
            actual = m.group(1).rstrip("/")
        elif actual and (m := _RUTA.match(linea)) and int(m.group(2)) == int(puerto):
            ruta = m.group(1)
            if not ruta.startswith("/"):
                ruta = "/" + ruta
            if not ruta.endswith("/"):
                ruta += "/"
            return actual + ruta
    return None


def consultar_funnel(timeout=5):
    """La salida de `tailscale funnel status`, o None si no se puede consultar."""
    exe = shutil.which("tailscale") or next(
        (r for r in _RUTAS_CONOCIDAS if os.path.exists(r)), None)
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "funnel", "status"], capture_output=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout + r.stderr) if r.returncode == 0 else None


def comando_para_publicar(puerto):
    return f"tailscale funnel --bg --https={PUERTO_FUNNEL} {puerto}"


def lineas_de_arranque(puerto, estado=...):
    """Qué contar al arrancar sobre cómo llegan los móviles.

    `estado` es la salida de `tailscale funnel status`; si no se pasa, se consulta.
    """
    if estado is ...:
        estado = consultar_funnel()
    if estado is None:
        return ["Tailscale no está disponible: la web solo se ve desde este equipo."]
    enlace = enlace_funnel(estado, puerto)
    if enlace:
        return [f"Enlace para el equipo (público, desde cualquier red): {enlace}"]
    return ["La web todavía no está publicada para el equipo. Se publica una sola vez con:",
            f"    {comando_para_publicar(puerto)}"]
