"""
Convierte el JSON de Smoothcomp al modelo que consume el frontend.

Sin red y sin estado: recibe las respuestas crudas y devuelve un diccionario.
Así se puede probar entero contra fixtures/event_1257/ sin tocar el origen.

La forma de los datos de origen está documentada en docs/data-source.md.
"""
from collections import OrderedDict

# Nombres de ronda que deciden las medallas. Son los que usa AJP en su schedule.
RONDA_FINAL = "final"
RONDA_BRONCE = "bronze match"

# Un combate cuenta como terminado solo en este estado; el resto (running,
# seeded, unseeded) significa que aún puede cambiar.
ESTADO_TERMINADO = "finished"


def parse_categoria(group):
    """Desmenuza la categoría de AJP: 'Men's GI / Brown / Master 1 / 62KG'.

    Normalmente son cuatro partes, pero el cinturón puede venir combinado y
    ocupar varias: 'Women's GI / Brown / Black / Master 1 / 49KG'. Por eso se lee
    desde los extremos (división primero, peso y edad al final) y lo que queda en
    medio es el cinturón. Si no hay al menos cuatro partes se conserva el texto
    completo y los campos van a None, que es lo acordado para lo que no existe.
    """
    texto = (group or "").strip()
    partes = [p.strip() for p in texto.split("/")] if texto else []
    vacio = {"division": None, "belt": None, "ageGroup": None, "weight": None, "gi": None}

    if len(partes) < 4:
        return {"raw": texto or None, **vacio}

    division, peso, edad = partes[0], partes[-1], partes[-2]
    belt = " / ".join(partes[1:-2])
    # "NO-GI" contiene "GI", así que se comprueba primero para no clasificarlo mal.
    normalizada = division.upper().replace(" ", "")
    if "NO-GI" in normalizada or "NOGI" in normalizada:
        gi = False
    elif "GI" in normalizada:
        gi = True
    else:
        gi = None

    return {"raw": texto, "division": division, "belt": belt,
            "ageGroup": edad, "weight": peso, "gi": gi}


def parse_combate(crudo, mat):
    """Un combate del origen, con el tatami del endpoint del que procede.

    En el tenant de AJP el combate no trae el nombre del tatami: se conoce
    porque se pidió a /mat/{id}/matches.json.
    """
    plazas = [s for s in crudo.get("seats", []) if s.get("type") == "registration"]
    return {
        "id": str(crudo["id"]),
        "bracketId": str(crudo.get("bracket_id")) if crudo.get("bracket_id") else None,
        "matId": mat["id"],
        "mat": mat.get("name"),
        "round": crudo.get("name"),
        "roundNr": crudo.get("round"),
        "matchNr": crudo.get("match_nr"),
        "matMatchNr": crudo.get("mat_match_nr") or None,
        "category": parse_categoria(crudo.get("group")),
        "estimatedStart": crudo.get("estimated_start"),
        "timePassed": crudo.get("time_passed"),
        "state": crudo.get("state"),
        "wonBy": crudo.get("wonBy"),
        "sides": [{
            "registrationId": str(s.get("event_registration_id")),
            "name": s.get("name"),
            "club": s.get("club") or None,
            "affiliation": s.get("affiliation") or None,
            "country": s.get("country") or None,
            "image": s.get("image") or None,
            "isWinner": bool(s.get("isWinner")),
        } for s in plazas],
    }


def _es_ronda(combate, nombre):
    return (combate.get("round") or "").strip().lower() == nombre


# De mejor a peor, para poder resumir en una sola medalla al atleta que tiene varias.
ORDEN_MEDALLAS = ("gold", "silver", "bronze")


def derivar_medallas(combates):
    """Medallas deducidas del propio schedule, por atleta y categoría.

    La pestaña /results está tras el challenge de Cloudflare, pero no hace falta:
    el ganador de la final es oro, el perdedor plata y quien gana el combate por
    el bronce es bronce. Un bracket pequeño puede no tener combate llamado
    "Final"; en ese caso, si solo tiene un combate, ese hace de final.

    Un atleta puede competir en varias categorías (Gi y No-Gi, adultos y master)
    y ganar una medalla en cada una, así que devuelve una lista por atleta:
    {registrationId: [{"bracketId", "category", "medal"}, ...]}.
    """
    por_bracket = OrderedDict()
    for c in combates:
        por_bracket.setdefault(c["bracketId"], []).append(c)

    medallas = {}

    def medalla_en(rid, bracket_id):
        for entrada in medallas.get(rid, []):
            if entrada["bracketId"] == bracket_id:
                return entrada["medal"]
        return None

    def anotar(lado, combate, medalla):
        entradas = medallas.setdefault(lado["registrationId"], [])
        # Un atleta no puede tener dos medallas en el mismo bracket: gana la mejor
        # (quien pierde la final ya es plata aunque antes ganara otro combate).
        for entrada in entradas:
            if entrada["bracketId"] == combate["bracketId"]:
                if ORDEN_MEDALLAS.index(medalla) < ORDEN_MEDALLAS.index(entrada["medal"]):
                    entrada["medal"] = medalla
                return
        entradas.append({"bracketId": combate["bracketId"],
                         "category": combate["category"].get("raw"),
                         "medal": medalla})

    for combates_bracket in por_bracket.values():
        terminados = [c for c in combates_bracket if c["state"] == ESTADO_TERMINADO]
        if not terminados:
            continue

        finales = [c for c in terminados if _es_ronda(c, RONDA_FINAL)]
        if not finales and len(terminados) == 1:
            finales = terminados  # bracket de dos personas: su único combate es la final

        for final in finales:
            for lado in final["sides"]:
                anotar(lado, final, "gold" if lado["isWinner"] else "silver")

        # El bronce se lo lleva quien gana el "Bronze match"... salvo en los
        # brackets de tres, que Smoothcomp resuelve como un todos-contra-todos y
        # donde ese combate no decide el tercer puesto: ahí su ganador puede ser
        # el propio campeón (visto en el bracket 109215 del evento 1257), y el
        # tercero es el otro. Por eso el bronce va al primer implicado que no
        # tenga ya medalla en ese mismo bracket.
        for bronce in (c for c in terminados if _es_ronda(c, RONDA_BRONCE)):
            ganadores = [l for l in bronce["sides"] if l["isWinner"]]
            perdedores = [l for l in bronce["sides"] if not l["isWinner"]]
            for candidato in ganadores + perdedores:
                if medalla_en(candidato["registrationId"], bronce["bracketId"]) is None:
                    anotar(candidato, bronce, "bronze")
                    break

    return medallas


def mejor_medalla(entradas):
    """La medalla más valiosa de un atleta, para mostrarla de un vistazo."""
    if not entradas:
        return None
    return min((e["medal"] for e in entradas), key=ORDEN_MEDALLAS.index)


def construir_atletas(combates):
    """Un atleta por plaza de inscripción, con sus combates y su medalla.

    Los combates van referenciados por id en vez de anidados: cada combate tiene
    dos atletas y anidarlo lo duplicaría en el JSON que descargan los móviles.
    """
    medallas = derivar_medallas(combates)
    atletas = OrderedDict()

    for c in combates:
        for lado in c["sides"]:
            rid = lado["registrationId"]
            atleta = atletas.get(rid)
            if atleta is None:
                atleta = atletas[rid] = {
                    "registrationId": rid,
                    "name": lado["name"],
                    "club": lado["club"],
                    "country": lado["country"],
                    "image": lado["image"],
                    "categories": [],
                    "matchIds": [],
                    "medals": medallas.get(rid, []),
                    "bestMedal": mejor_medalla(medallas.get(rid, [])),
                }
            atleta["matchIds"].append(c["id"])
            categoria = c["category"].get("raw")
            if categoria and categoria not in atleta["categories"]:
                atleta["categories"].append(categoria)

    return list(atletas.values())


def clave_orden(combate):
    """Orden cronológico, con los que no tienen hora al final."""
    return (combate.get("estimatedStart") is None,
            combate.get("estimatedStart") or "",
            combate.get("mat") or "",
            combate.get("matchNr") or 0)


def construir_estado(*, evento, dias, mats, combates_por_mat, fetched_at,
                     streams=None, stale=False, stale_since=None):
    """Arma el data.json completo a partir de las respuestas crudas.

    `combates_por_mat` es {matId: [combate crudo, ...]}. Los combates se
    deduplican por id: uno movido de tatami a mitad de lectura puede aparecer
    en dos listas.
    """
    mats_por_id = {m["id"]: m for m in mats}

    vistos = {}
    for mat_id, crudos in combates_por_mat.items():
        mat = mats_por_id.get(mat_id, {"id": mat_id, "name": None})
        for crudo in crudos:
            combate = parse_combate(crudo, mat)
            vistos.setdefault(combate["id"], combate)

    combates = sorted(vistos.values(), key=clave_orden)

    return {
        "event": {
            "id": str(evento.get("id")),
            "name": evento.get("name"),
            "days": [{"id": d.get("id"), "name": d.get("name"), "date": d.get("date")}
                     for d in dias],
        },
        "fetchedAt": fetched_at,
        "stale": stale,
        "staleSince": stale_since,
        "mats": [{"id": m.get("id"), "name": m.get("name"),
                  "estimatedStart": m.get("estimated_start"),
                  "estimatedEnd": m.get("estimated_end")} for m in mats],
        "streams": streams or [],
        "matches": combates,
        "athletes": construir_atletas(combates),
    }
