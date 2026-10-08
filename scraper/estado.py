"""
Estados que se fabrican sin haber leído el schedule: el evento vacío y el viejo.

Los usan tanto el bucle de `scraper.main` (modo instantánea estática) como el
almacén del servidor, así que viven aquí y no en ninguno de los dos.
"""
from datetime import datetime, timezone

from scraper.parse import construir_estado


def ahora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def estado_vacio(eventos, *, streams=None, grupo=None, base_url, lang="en"):
    """Los eventos anunciados, sin combates, para cuando aún no hay schedule.

    Sin esto, antes de que el organizador publique nada la web se quedaría sin
    nada que enseñar, y la lista del grupo que se va apuntando no llegaría a nadie.
    """
    return construir_estado(
        eventos=eventos or [], datos_por_evento={}, fetched_at=ahora_iso(),
        streams=streams or [], grupo=grupo, base_url=base_url, lang=lang)


def marcar_stale(estado, desde):
    """Reutiliza el último estado bueno, avisando de que ya no está fresco."""
    copia = dict(estado)
    copia["stale"] = True
    copia["staleSince"] = desde
    return copia
