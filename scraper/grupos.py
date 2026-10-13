"""
La lista del grupo: a quién ven todos al abrir un evento sin tener que seguirlo.

localStorage vive en cada navegador, así que la única forma de que una selección
llegue a todos los móviles es guardarla en el servidor. Hay una lista por vista
(`33588`, o `1535,1526` si se combinan dos eventos) en `data/grupos.json`.

Solo el panel local puede escribirla (ver `scraper/servidor.py`); leerla es
público porque forma parte de lo que ve cualquiera.
"""
import json
import shutil
import threading
from pathlib import Path

from scraper.parse import clave_atleta
from scraper.publish import escribir_json
from scraper.telemetria import nivel

NOMBRE_POR_DEFECTO = "Nuestro equipo"
ACCIONES = ("añadir", "quitar")

# Topes para que una petición rara no deje el fichero enorme.
MAX_ATLETAS = 500
MAX_TEXTO = 200


class Grupos:
    def __init__(self, ruta, nombre=NOMBRE_POR_DEFECTO, log=None):
        self.ruta = Path(ruta)
        self.nombre = nombre
        self._log = log or (lambda *_: None)
        self._candado = threading.Lock()
        self._ilegible = False    # el fichero existe pero no se pudo leer (siempre con el candado)
        self._avisado = False     # ya se avisó de este estado: no repetirlo en cada lectura

    def _leer_todo(self):
        """Todo el fichero. Uno que no existe aún es normal; uno ilegible se avisa."""
        motivo = None
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except FileNotFoundError:
            datos = {}
        except (OSError, ValueError) as e:
            datos, motivo = {}, f"no se pudo leer ({type(e).__name__})"
        else:
            if not isinstance(datos, dict):
                datos, motivo = {}, "no es un objeto JSON"

        self._ilegible = motivo is not None
        if self._ilegible and not self._avisado:
            nivel(self._log, "error")(f"grupos: {self.ruta.name} {motivo}; se trata como vacío")
        self._avisado = self._ilegible
        return datos

    def leer(self, clave):
        """{"nombre", "atletas"} de una vista; vacío si nunca se tocó."""
        with self._candado:
            grupo = self._leer_todo().get(clave)
        grupo = grupo if isinstance(grupo, dict) else {}
        return {"nombre": grupo.get("nombre") or self.nombre,
                "atletas": grupo.get("atletas") or []}

    def actualizar(self, clave, accion, atleta_id=None, nombre=None, club=None):
        """Añade o quita un atleta. Devuelve la lista nueva.

        Lanza ValueError si la petición no vale. Sin `atleta_id` se calcula con
        la misma identidad que usa el scraper (nombre + club), que es lo que
        permite apuntar a alguien a mano antes de que haya schedule: sin club
        queda "nombre|", que casa con ese nombre en cualquier club.
        """
        if accion not in ACCIONES:
            raise ValueError("acción desconocida")
        atleta_id = (atleta_id or "").strip()
        nombre = (nombre or "").strip()
        club = (club or "").strip() or None
        if any(len(t or "") > MAX_TEXTO for t in (atleta_id, nombre, club)):
            raise ValueError("texto demasiado largo")
        if not atleta_id and nombre:
            atleta_id = clave_atleta({"name": nombre, "club": club})
        if not atleta_id:
            raise ValueError("falta el id o el nombre del atleta")

        with self._candado:
            todo = self._leer_todo()
            if self._ilegible:
                # Escribir ahora lo machacaría: se guarda lo que había para poder recuperarlo.
                try:
                    shutil.copy2(self.ruta, self.ruta.with_name(self.ruta.name + ".bak"))
                except OSError as e:
                    nivel(self._log, "error")(f"grupos: tampoco se pudo copiar la copia de "
                                              f"seguridad ({type(e).__name__})")
            actual = todo.get(clave) if isinstance(todo.get(clave), dict) else {}
            # Quitar desde la ficha manda el id completo ("nombre|club"), pero el
            # atleta puede estar en el grupo por un alta a mano sin club ("nombre|").
            sin_club = atleta_id.split("|", 1)[0] + "|"
            atletas = [a for a in (actual.get("atletas") or [])
                       if a.get("id") != atleta_id
                       and not (accion == "quitar" and a.get("id") == sin_club)]

            if accion == "añadir":
                if len(atletas) >= MAX_ATLETAS:
                    raise ValueError("la lista del grupo está llena")
                entrada = {"id": atleta_id, "name": nombre or atleta_id}
                if club:
                    entrada["club"] = club
                atletas.append(entrada)
                atletas.sort(key=lambda a: (a.get("name") or "").lower())

            grupo = {"nombre": actual.get("nombre") or self.nombre, "atletas": atletas}
            todo[clave] = grupo
            # Atómico: otro hilo puede estar leyendo el fichero justo ahora.
            escribir_json(self.ruta, todo, compacto=False)
            return grupo
