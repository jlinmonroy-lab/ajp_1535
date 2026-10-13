"""
La muestra del estado que sirve el servidor, para el contrato entre Python y la web.

`construir_estado` (scraper/parse.py) y `web/src/tipos.ts` son dos mitades de lo mismo y
ningún compilador las une: si una renombra un campo, la otra se rompe sin que falle nada.
Esta muestra es el punto de encuentro. Se construye aquí con el código de verdad, a partir de
las fixtures anonimizadas, y se versiona en `web/src/pruebas/estado.contrato.json`:

  - tests/test_contrato.py comprueba que el JSON versionado es lo que hoy emite Python.
    Si no, falla y dice cómo regenerarlo, así que un cambio en parse.py pasa por aquí.
  - web/src/app/contrato.test.ts comprueba que ese JSON cumple los tipos de tipos.ts.

Es una muestra pequeña a propósito (los estados completos pesan cientos de KB): cuadros
enteros del evento 1257, que traen oro, plata y bronce, y unos combates del 1535 para que
sea una vista de dos eventos.

Uso:  python tests/contrato.py        # regenera web/src/pruebas/estado.contrato.json
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.parse import aplicar_grupo, construir_estado  # noqa: E402

FIXTURES = RAIZ / "fixtures"
DESTINO = RAIZ / "web" / "src" / "pruebas" / "estado.contrato.json"
COMANDO = "python tests/contrato.py"
COMBATES_DEL_SEGUNDO_EVENTO = 6


def _cargar(event_id):
    """(días, tatamis, combates por tatami) crudos, como los lee scraper/fetch.py."""
    carpeta = FIXTURES / f"event_{event_id}"
    dias = json.loads((carpeta / "days.json").read_text(encoding="utf-8"))
    mats = []
    for d in dias:
        for m in json.loads((carpeta / f"mats_{d['id']}.json").read_text(encoding="utf-8")):
            m["dayId"], m["dayName"], m["dayDate"] = d["id"], d.get("name"), d.get("date")
            mats.append(m)
    combates = {}
    for m in mats:
        ruta = carpeta / f"matches_{m['id']}.json"
        if ruta.exists():
            combates[m["id"]] = json.loads(ruta.read_text(encoding="utf-8"))
    return dias, mats, combates


def _evento(event_id, label):
    return {"id": event_id, "label": label, "name": f"Evento de prueba {event_id}"}


def _cuadros_elegidos(estado):
    """Los cuadros más pequeños que cubren lo que la web pinta: uno con bronce, uno con
    'Bronze match' y uno de un solo combate. Siempre enteros: la medalla sale de cuadros completos."""
    combates = defaultdict(list)
    for c in estado["matches"]:
        combates[c["bracketId"]].append(c)
    medallas = defaultdict(set)
    for a in estado["athletes"]:
        for m in a["medals"]:
            medallas[m["bracketId"]].add(m["medal"])

    def el_menor(condicion):
        return min((len(combates[b]), b) for b in medallas if condicion(b))[1]

    return {
        el_menor(lambda b: "bronze" in medallas[b]),
        el_menor(lambda b: any(c["round"] == "Bronze match" for c in combates[b])),
        el_menor(lambda b: True),
    }


def muestra():
    """El estado de la muestra: dos eventos, con medallas, una retransmisión y un grupo."""
    dias, mats, combates = _cargar("1257")
    completo = construir_estado(
        eventos=[_evento("1257", "AJP")], datos_por_evento={"1257": (dias, mats, combates)},
        fetched_at="x")
    elegidos = _cuadros_elegidos(completo)
    del_1257 = {mat: [c for c in lista if f"1257-{c['bracket_id']}" in elegidos]
                for mat, lista in combates.items()}
    del_1257 = {mat: lista for mat, lista in del_1257.items() if lista}

    dias2, mats2, combates2 = _cargar("1535")
    primeros = [(mat, c) for mat in sorted(combates2) for c in combates2[mat]]
    primeros = primeros[:COMBATES_DEL_SEGUNDO_EVENTO]
    del_1535 = defaultdict(list)
    for mat, c in primeros:
        del_1535[mat].append(c)

    estado = construir_estado(
        eventos=[_evento("1257", "AJP"), _evento("1535", "Open")],
        datos_por_evento={
            "1257": (dias, [m for m in mats if m["id"] in del_1257], del_1257),
            "1535": (dias2, [m for m in mats2 if m["id"] in del_1535], dict(del_1535)),
        },
        fetched_at="2026-09-20T12:00:00Z",
        streams=[{"mat": "Mat 1", "url": "https://stream.example.test/mat1"}])

    # Un atleta que compite y otro apuntado a mano que no (sin club): las dos formas del grupo.
    primero = estado["athletes"][0]
    return aplicar_grupo(estado, {"nombre": "Nuestro equipo", "atletas": [
        {"id": primero["id"], "name": primero["name"], "club": primero["club"]},
        {"id": "atleta 999999|", "name": "Atleta 999999"},
    ]})


def texto(estado):
    """El JSON tal como se versiona: ordenado y legible, para que los cambios se vean en el diff."""
    return json.dumps(estado, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main():
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    estado = muestra()
    DESTINO.write_text(texto(estado), encoding="utf-8", newline="\n")
    print(f"{DESTINO.relative_to(RAIZ)}: {len(estado['matches'])} combates, "
          f"{len(estado['athletes'])} atletas, {DESTINO.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
