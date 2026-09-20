"""
Publicación del data.json.

Aislado a propósito del resto: si GitHub Pages no diera la latencia necesaria,
esto es lo único que habría que cambiar (ver docs/architecture.md).

Escribe siempre en local y, si está configurado, hace commit y push sobre una
rama dedicada con --amend para no acumular un commit por ciclo.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path


def escribir_json(destino: Path, estado: dict) -> int:
    """Escritura atómica: el frontend nunca debe leer un JSON a medias.

    Se escribe a un temporal en la misma carpeta y se reemplaza de golpe, que en
    el mismo sistema de ficheros es atómico.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(estado, ensure_ascii=False, separators=(",", ":"))

    fd, temporal = tempfile.mkstemp(dir=str(destino.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(temporal, destino)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise
    return len(texto.encode("utf-8"))


def _git(args, cwd, log):
    resultado = subprocess.run(["git", *args], cwd=str(cwd),
                               capture_output=True, text=True)
    if resultado.returncode != 0:
        log(f"  git {' '.join(args)}: {resultado.stderr.strip()[:200]}")
        return False
    return True


def publicar_git(cfg, repo_dir: Path, log=print) -> bool:
    """Commit + push del data.json sobre la rama de publicación.

    Usa --amend y --force sobre una rama dedicada, de modo que el historial de
    datos sea siempre un único commit y no ensucie el del código.
    """
    git_cfg = cfg.get("git") or {}
    if not git_cfg.get("enabled"):
        return False

    rama = git_cfg.get("branch", "gh-pages")
    ruta = git_cfg.get("path", "data.json")

    if not _git(["add", "--", ruta], repo_dir, log):
        return False

    # Sin cambios que publicar: no se toca nada (evita un push por ciclo inútil).
    sin_cambios = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", ruta],
        cwd=str(repo_dir), capture_output=True)
    if sin_cambios.returncode == 0:
        log("  sin cambios respecto a lo publicado")
        return False

    mensaje = git_cfg.get("message", "datos del evento")
    if not _git(["commit", "--amend", "-m", mensaje], repo_dir, log):
        return False
    if not _git(["push", "--force", "origin", rama], repo_dir, log):
        return False

    log(f"  publicado en la rama {rama}")
    return True
