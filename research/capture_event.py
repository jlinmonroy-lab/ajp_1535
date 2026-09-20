"""
Paso 1 — Vuelca el schedule completo de un evento AJP a fixtures/, y resume su
forma real para poder escribir el parser contra datos, no contra suposiciones.

Recorre los tres endpoints públicos de Smoothcomp:
    /en/event/{id}/schedule/new/matcategories.json      -> días
    /en/event/{id}/schedule/new/mats.json/{dayId}       -> tatamis del día
    /en/event/{id}/schedule/new/mat/{matId}/matches.json -> combates del tatami

No necesita cookies: se comprobó (research/probe_events.py) que responden 200 de
forma anónima. Tampoco necesita navegador.

Uso:  python research/capture_event.py 1257
"""
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "https://ajptour.com"
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

PAUSA_S = 2.0  # entre peticiones, por cortesía con el origen


def get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def como_lista(valor):
    """matcategories.json devuelve un objeto si el evento tiene un solo día."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def main():
    if len(sys.argv) < 2:
        print("Falta el id del evento.  Uso: python research/capture_event.py 1257")
        return 2
    event_id = sys.argv[1]
    schedule = f"{BASE}/en/event/{event_id}/schedule/new"
    destino = FIXTURES / f"event_{event_id}"
    destino.mkdir(parents=True, exist_ok=True)

    print(f"=== Evento {event_id}")
    dias = como_lista(get_json(f"{schedule}/matcategories.json"))
    (destino / "days.json").write_text(
        json.dumps(dias, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Días: {len(dias)}")
    for d in dias:
        print(f"  {d.get('id')}  {d.get('name')!r}  {d.get('date')}")

    todos_mats = []
    for d in dias:
        time.sleep(PAUSA_S)
        mats = get_json(f"{schedule}/mats.json/{d['id']}")
        (destino / f"mats_{d['id']}.json").write_text(
            json.dumps(mats, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nTatamis del día {d.get('name')!r}: {len(mats)}")
        for m in mats:
            print(f"  {m.get('id')}  {m.get('name')!r}  "
                  f"visible={m.get('visible')}  inicio={m.get('estimated_start')}")
        todos_mats.extend(mats)

    combates = []
    for m in todos_mats:
        time.sleep(PAUSA_S)
        try:
            lista = get_json(f"{schedule}/mat/{m['id']}/matches.json")
        except urllib.error.HTTPError as e:
            print(f"  [{m.get('name')}] ERROR {e.code}")
            continue
        (destino / f"matches_{m['id']}.json").write_text(
            json.dumps(lista, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  {m.get('name')!r}: {len(lista)} combates")
        combates.extend(lista)

    # ---- Resumen de la forma real de los datos ----
    print(f"\n=== Resumen: {len(combates)} combates en {len(todos_mats)} tatamis")
    if not combates:
        print("Sin combates: el evento no tiene schedule con contenido.")
        return 1

    campos = Counter()
    for c in combates:
        campos.update(c.keys())
    print(f"\nCampos presentes (de {len(combates)} combates):")
    for campo, n in campos.most_common():
        print(f"  {campo:<20} {n}")

    for campo in ("state", "wonBy", "name"):
        valores = Counter(str(c.get(campo)) for c in combates)
        print(f"\n{campo}: {dict(valores.most_common(12))}")

    categorias = sorted({c.get("group", "") for c in combates})
    print(f"\nCategorías distintas: {len(categorias)}. Muestra:")
    for cat in categorias[:12]:
        print(f"  {cat}")

    # Gi / No-Gi: saber si se distingue dentro de los datos o solo en el nombre
    # del evento es lo que decide si hace falta configurarlo a mano.
    marcas = [c for c in categorias if any(
        s in c.lower() for s in ("gi", "no-gi", "nogi"))]
    print(f"\nCategorías que mencionan Gi/No-Gi: {len(marcas)}")

    tipos_seat = Counter()
    for c in combates:
        for s in c.get("seats", []):
            tipos_seat[s.get("type")] += 1
    print(f"\nTipos de seat: {dict(tipos_seat)}")

    con_hora = sum(1 for c in combates if c.get("estimated_start"))
    print(f"Combates con estimated_start: {con_hora}/{len(combates)}")

    resumen = {
        "event_id": event_id,
        "dias": len(dias),
        "tatamis": len(todos_mats),
        "combates": len(combates),
        "campos": dict(campos),
        "categorias": categorias,
    }
    (destino / "_resumen.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFixtures en {destino}")
    print("\nAVISO: lo capturado son datos REALES (nombres y fotos")
    print("de atletas) y el repositorio es publico. Antes de commitear:")
    print("  python research/anonymize_fixtures.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
