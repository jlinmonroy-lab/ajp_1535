"""
Publicación del data.json.

Aislado a propósito del resto: si GitHub Pages no diera la latencia necesaria,
esto es lo único que habría que cambiar (ver docs/architecture.md).

El data.json se escribe siempre en local (para poder probar sin publicar) y,
si la publicación está activada, se copia a un worktree de la rama gh-pages y
se sube. El worktree vive fuera de OneDrive a propósito: un commit cada 75s
dentro de una carpeta sincronizada acaba en bloqueos de fichero.

Se usa `commit --amend` + `push --force` para que el historial de datos sea
siempre un único commit y no crezca sin control durante el evento.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Ficheros del sitio que acompañan al data.json en la rama publicada.
ESTATICOS = ("index.html", "app.js", "style.css", "robots.txt", ".nojekyll")


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


def _git(args, cwd, log, silencioso=False):
    resultado = subprocess.run(["git", *args], cwd=str(cwd),
                               capture_output=True, text=True)
    if resultado.returncode != 0 and not silencioso:
        log(f"  git {' '.join(args[:2])}: {resultado.stderr.strip()[:200]}")
    return resultado


def sincronizar_estaticos(origen: Path, worktree: Path, log) -> int:
    """Copia los ficheros del sitio que hayan cambiado. Devuelve cuántos."""
    copiados = 0
    for nombre in ESTATICOS:
        fuente = origen / nombre
        if not fuente.exists():
            continue
        destino = worktree / nombre
        if destino.exists() and destino.read_bytes() == fuente.read_bytes():
            continue
        shutil.copy2(fuente, destino)
        copiados += 1
    if copiados:
        log(f"  {copiados} fichero(s) del sitio actualizados")
    return copiados


def publicar(cfg, data_json: Path, log=print) -> bool:
    """Copia el data.json al worktree de gh-pages y lo sube.

    Devuelve True si se publicó algo. No lanza: un fallo al publicar no debe
    tumbar el bucle del scraper, que seguirá intentándolo en el ciclo siguiente.
    """
    pub = cfg.get("publish") or {}
    if not pub.get("enabled"):
        return False

    worktree = Path(pub["worktree"])
    if not (worktree / ".git").exists():
        log(f"  el worktree {worktree} no existe; revisa config.json")
        return False

    sincronizar_estaticos(data_json.parent, worktree, log)
    shutil.copy2(data_json, worktree / "data.json")

    if _git(["add", "-A"], worktree, log).returncode != 0:
        return False

    # Sin cambios reales no se publica: evita un push por ciclo cuando el
    # schedule está parado, que es justo lo que agota el límite de builds.
    if _git(["diff", "--cached", "--quiet"], worktree, log,
            silencioso=True).returncode == 0:
        log("  sin cambios respecto a lo publicado")
        return False

    mensaje = pub.get("message", "datos del evento")
    if _git(["commit", "--amend", "-m", mensaje], worktree, log).returncode != 0:
        return False
    rama = pub.get("branch", "gh-pages")
    if _git(["push", "--force", "origin", rama], worktree, log).returncode != 0:
        return False

    log(f"  publicado en {rama}")
    return True
