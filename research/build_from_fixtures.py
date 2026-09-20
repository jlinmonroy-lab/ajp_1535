"""
Genera un data.json a partir de los fixtures guardados, sin tocar la red.

Sirve para dos cosas: trabajar en el frontend sin depender del origen, y tener
un data.json de pruebas que no expone nombres reales, porque los fixtures están
anonimizados (ver research/anonymize_fixtures.py).

Uso:  python research/build_from_fixtures.py [event_id] [-o salida]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scraper.parse import construir_estado  # noqa: E402
from scraper.publish import escribir_json  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("event_id", nargs="?", default="1257")
    p.add_argument("-o", "--salida", default="site/data.json")
    args = p.parse_args()

    carpeta = RAIZ / "fixtures" / f"event_{args.event_id}"
    if not carpeta.exists():
        print(f"No existe {carpeta}. Captura antes con research/capture_event.py")
        return 1

    dias = json.loads((carpeta / "days.json").read_text(encoding="utf-8"))
    mats = []
    for d in dias:
        mats += json.loads((carpeta / f"mats_{d['id']}.json").read_text(encoding="utf-8"))
    combates = {
        m["id"]: json.loads((carpeta / f"matches_{m['id']}.json").read_text(encoding="utf-8"))
        for m in mats if (carpeta / f"matches_{m['id']}.json").exists()
    }

    estado = construir_estado(
        evento={"id": args.event_id, "name": f"Datos de prueba (evento {args.event_id})"},
        dias=dias, mats=mats, combates_por_mat=combates,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )

    destino = RAIZ / args.salida
    tam = escribir_json(destino, estado)
    print(f"{destino}: {len(estado['matches'])} combates, "
          f"{len(estado['athletes'])} atletas, {tam / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
