"""
Anonimiza los fixtures antes de que lleguen a un repositorio público.

Los datos que devuelve Smoothcomp son reales: nombre y apellidos de cada atleta,
y una URL de foto que **lleva el nombre dentro**
(`.../josimar-domingues-da-silva-junior.jpg`). Que ya sean visibles en
ajptour.com no es lo mismo que republicarlos aquí, así que en `fixtures/` se
sustituyen.

Qué se cambia y qué no:

  name                   -> "Atleta N"
  image                  -> null (no basta renombrar: el nombre va en la URL)
  event_registration_id  -> 900000 + N, un rango claramente ficticio
  club, affiliation, country, group  -> se conservan: son datos de organización,
                            no personales, y mantienen el realismo de las pruebas

La numeración sale de ordenar los identificadores originales, así que es
**determinista** (dos ejecuciones dan lo mismo) e **idempotente** (volver a
pasarlo sobre datos ya anónimos no los altera).

**No se guarda el mapa de equivalencias**: guardarlo haría la anonimización
reversible y no serviría de nada.

Aviso: esto reduce la exposición, no la elimina. Cruzando club, categoría y
resultado con ajptour.com aún se podría reidentificar a alguien.

Uso:  python research/anonymize_fixtures.py [carpeta ...]
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "fixtures"

BASE_ID = 900000
NOMBRE_ANON = re.compile(r"^Atleta \d+$")


def carpetas_de_evento(args):
    if args:
        return [Path(a) if Path(a).is_absolute() else RAIZ / a for a in args]
    return sorted(d for d in FIXTURES.glob("event_*") if d.is_dir())


def anonimizar(carpeta):
    archivos = sorted(carpeta.glob("matches_*.json"))
    if not archivos:
        print(f"  {carpeta.name}: sin ficheros matches_*.json, se omite")
        return 0

    contenido = {f: json.loads(f.read_text(encoding="utf-8")) for f in archivos}

    # Solo las plazas ocupadas por una inscripción son personas; las de tipo
    # "winner"/"loser" son huecos pendientes ("Winner from 1-2") y se dejan.
    def plazas():
        for combates in contenido.values():
            for combate in combates:
                for plaza in combate.get("seats", []):
                    if plaza.get("type") == "registration":
                        yield plaza

    ids = sorted({p["event_registration_id"] for p in plazas()
                  if p.get("event_registration_id") is not None})
    mapa = {rid: BASE_ID + i for i, rid in enumerate(ids, start=1)}

    ya_anonimos = sum(1 for p in plazas() if NOMBRE_ANON.match(p.get("name") or ""))
    fotos = 0
    for plaza in plazas():
        rid = plaza.get("event_registration_id")
        if rid in mapa:
            nuevo = mapa[rid]
            plaza["event_registration_id"] = nuevo
            plaza["name"] = f"Atleta {nuevo - BASE_ID}"
        if plaza.get("image"):
            plaza["image"] = None
            fotos += 1

    # Un nombre podría colarse también aquí si el bracket arrastra al ganador.
    for combates in contenido.values():
        for combate in combates:
            if isinstance(combate.get("winnerFromBracket"), str):
                combate["winnerFromBracket"] = None

    for archivo, combates in contenido.items():
        archivo.write_text(
            json.dumps(combates, indent=2, ensure_ascii=False), encoding="utf-8")

    estado = "ya estaban anónimos" if ya_anonimos == len(list(plazas())) else "anonimizados"
    print(f"  {carpeta.name}: {len(mapa)} atletas {estado}, "
          f"{fotos} fotos eliminadas, {len(archivos)} ficheros reescritos")
    return len(mapa)


def main():
    carpetas = carpetas_de_evento(sys.argv[1:])
    if not carpetas:
        print("No hay carpetas de evento en fixtures/.")
        return 1
    print("Anonimizando fixtures:")
    total = sum(anonimizar(c) for c in carpetas)
    print(f"\nTotal: {total} atletas. Comprueba con:")
    print("  python -m unittest discover -s tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
