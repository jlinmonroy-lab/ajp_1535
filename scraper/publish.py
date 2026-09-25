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
import time
from pathlib import Path

# Ficheros del sitio que acompañan al data.json en la rama publicada.
ESTATICOS = ("index.html", "app.js", "style.css", "robots.txt", ".nojekyll")

# Campos que cambian en cada ciclo aunque no haya pasado nada en el tatami.
# Compararlos haría que "no hay cambios" no ahorrase nunca un push.
VOLATILES = ("fetchedAt", "stale", "staleSince", "_nonce")


def escribir_json(destino: Path, estado: dict, intentos: int = 4,
                  compacto: bool = True) -> int:
    """Escritura atómica: el frontend nunca debe leer un JSON a medias.

    Se escribe a un temporal en la misma carpeta y se reemplaza de golpe, que en
    el mismo sistema de ficheros es atómico.

    En Windows, `os.replace` falla si otro proceso tiene el destino abierto en
    ese instante, y aquí pasa de verdad: el scraper relee `config.json` en cada
    ciclo mientras el panel puede estar guardándolo. Es una ventana de
    milisegundos, así que basta con reintentar en lugar de abortar.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Compacto para el data.json, que pesa cerca de un mega y viaja a los
    # móviles; legible para config.json, que se edita a mano.
    texto = (json.dumps(estado, ensure_ascii=False, separators=(",", ":")) if compacto
             else json.dumps(estado, ensure_ascii=False, indent=2) + "\n")

    fd, temporal = tempfile.mkstemp(dir=str(destino.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        for intento in range(intentos):
            try:
                os.replace(temporal, destino)
                break
            except OSError:
                if intento == intentos - 1:
                    raise
                time.sleep(0.15 * (intento + 1))
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


def _sustancia(ruta: Path):
    """El contenido que de verdad importa: sin las marcas de tiempo."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {k: v for k, v in datos.items() if k not in VOLATILES}


def _minutos_desde_ultimo_push(worktree: Path):
    """Edad del commit publicado, en minutos. None si no se puede saber."""
    r = subprocess.run(["git", "log", "-1", "--format=%ct"], cwd=str(worktree),
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip().isdigit():
        return None
    return (time.time() - int(r.stdout.strip())) / 60


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


def hay_que_publicar(cfg, data_json: Path, worktree: Path, log):
    """Decide si este ciclo merece un push.

    GitHub Pages reconstruye en cada push y tiene un límite blando de 10
    builds/hora; a 75s por ciclo serían ~48. Con el schedule parado —de
    madrugada, entre jornadas, o en un evento terminado— lo único que cambia es
    `fetchedAt`, así que publicar por eso gastaría builds sin dar información
    nueva a nadie.

    Aun así se publica de vez en cuando aunque no cambie nada, porque la web
    muestra "actualizado hace X" y esa antigüedad tiene que ser cierta.
    """
    publicado = worktree / "data.json"
    if not publicado.exists():
        return True, "primera publicación"

    if _sustancia(data_json) != _sustancia(publicado):
        return True, "hay cambios en el schedule"

    limite = (cfg.get("publish") or {}).get("maxMinutesSinPublish", 5)
    minutos = _minutos_desde_ultimo_push(worktree)
    if minutos is None:
        return True, "no se pudo leer la fecha del último push"
    if minutos >= limite:
        return True, f"refresco periódico ({minutos:.0f} min sin publicar)"

    return False, f"sin cambios de fondo ({minutos:.1f} min desde el último push)"


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

    # Un cambio en el propio sitio (HTML/CSS/JS) sí justifica publicar aunque
    # los datos estén igual.
    estaticos = sincronizar_estaticos(data_json.parent, worktree, log)

    procede, motivo = hay_que_publicar(cfg, data_json, worktree, log)
    if not procede and not estaticos:
        log(f"  no se publica: {motivo}")
        return False

    shutil.copy2(data_json, worktree / "data.json")

    if _git(["add", "-A"], worktree, log).returncode != 0:
        return False
    if _git(["diff", "--cached", "--quiet"], worktree, log,
            silencioso=True).returncode == 0:
        log("  el contenido publicado ya era idéntico")
        return False

    mensaje = pub.get("message", "datos del evento")
    if _git(["commit", "--amend", "-m", mensaje], worktree, log).returncode != 0:
        return False
    rama = pub.get("branch", "gh-pages")
    if _git(["push", "--force", "origin", rama], worktree, log).returncode != 0:
        return False

    log(f"  publicado en {rama}: {motivo if procede else 'sitio actualizado'}")
    return True
