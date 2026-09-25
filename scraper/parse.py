"""
Convierte el JSON de Smoothcomp al modelo que consume el frontend.

Sin red y sin estado: recibe las respuestas crudas y devuelve un diccionario.
Así se puede probar entero contra fixtures/event_1257/ sin tocar el origen.

La forma de los datos de origen está documentada en docs/data-source.md.
"""
import unicodedata
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


def jornada(iso):
    """La fecha local del combate, 'YYYY-MM-DD'.

    El torneo dura dos días y la web solo enseña la hora, así que sin esto un
    combate del domingo a las 12:00 sería indistinguible de uno del sábado. Se
    corta el ISO en seco en vez de convertir zonas: el origen ya da la hora con
    el desfase del propio evento, que es el que ve quien está en el pabellón.
    """
    return (iso or "")[:10] or None


def normalizar(texto):
    """Minúsculas y sin acentos, para comparar nombres y clubes.

    Mismo criterio que usa el buscador del frontend, para que lo que allí se
    considera "el mismo nombre" coincida con lo que aquí se unifica.
    """
    limpio = unicodedata.normalize("NFD", (texto or "").strip().lower())
    return "".join(c for c in limpio if unicodedata.category(c) != "Mn")


def clave_atleta(lado):
    """Identidad de una persona a través de los dos eventos.

    `event_registration_id` es único por evento, así que quien compita en Gi y
    en No-Gi aparece con dos identificadores distintos y no hay nada en los
    datos que los relacione. Se unifica por nombre + club, asumiendo el riesgo
    conocido: si AJP escribe el nombre distinto en cada inscripción saldrá
    duplicado, y dos personas homónimas del mismo club se fusionarían.
    """
    return f"{normalizar(lado.get('name'))}|{normalizar(lado.get('club'))}"


def parse_combate(crudo, mat, evento):
    """Un combate del origen, con su tatami y el evento al que pertenece.

    En el tenant de AJP el combate no trae el nombre del tatami: se conoce
    porque se pidió a /mat/{id}/matches.json. Y como los dos eventos comparten
    pabellón y pueden tener tatamis con el mismo nombre, la identidad del
    tatami es el par evento + matId, nunca el nombre suelto.
    """
    plazas = [s for s in crudo.get("seats", []) if s.get("type") == "registration"]
    return {
        "id": f"{evento['id']}-{crudo['id']}",
        "eventId": str(evento["id"]),
        "eventLabel": evento.get("label"),
        "bracketId": (f"{evento['id']}-{crudo['bracket_id']}"
                      if crudo.get("bracket_id") else None),
        "matId": mat["id"],
        "matKey": f"{evento['id']}:{mat['id']}",
        "mat": mat.get("name"),
        "round": crudo.get("name"),
        "roundNr": crudo.get("round"),
        "matchNr": crudo.get("match_nr"),
        "matMatchNr": crudo.get("mat_match_nr") or None,
        "category": parse_categoria(crudo.get("group")),
        "estimatedStart": crudo.get("estimated_start"),
        "day": jornada(crudo.get("estimated_start")) or mat.get("dayDate", "")[:10] or None,
        "dayName": mat.get("dayName"),
        "timePassed": crudo.get("time_passed"),
        "state": crudo.get("state"),
        "wonBy": crudo.get("wonBy"),
        "sides": [{
            "athleteId": clave_atleta(s),
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
    y ganar una medalla en cada una, así que devuelve una lista por atleta,
    indexada por su identidad unificada entre eventos:
    {athleteId: [{"bracketId", "category", "medal", "eventId"}, ...]}.
    """
    por_bracket = OrderedDict()
    for c in combates:
        por_bracket.setdefault(c["bracketId"], []).append(c)

    medallas = {}

    def medalla_en(atleta_id, bracket_id):
        for entrada in medallas.get(atleta_id, []):
            if entrada["bracketId"] == bracket_id:
                return entrada["medal"]
        return None

    def anotar(lado, combate, medalla):
        entradas = medallas.setdefault(lado["athleteId"], [])
        # Un atleta no puede tener dos medallas en el mismo bracket: gana la mejor
        # (quien pierde la final ya es plata aunque antes ganara otro combate).
        for entrada in entradas:
            if entrada["bracketId"] == combate["bracketId"]:
                if ORDEN_MEDALLAS.index(medalla) < ORDEN_MEDALLAS.index(entrada["medal"]):
                    entrada["medal"] = medalla
                return
        entradas.append({"bracketId": combate["bracketId"],
                         "eventId": combate["eventId"],
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
                if medalla_en(candidato["athleteId"], bronce["bracketId"]) is None:
                    anotar(candidato, bronce, "bronze")
                    break

    return medallas


def mejor_medalla(entradas):
    """La medalla más valiosa de un atleta, para mostrarla de un vistazo."""
    if not entradas:
        return None
    return min((e["medal"] for e in entradas), key=ORDEN_MEDALLAS.index)


def construir_atletas(combates):
    """Un atleta por persona, aunque compita en los dos eventos.

    Se agrupa por la identidad unificada (nombre + club), no por inscripción:
    quien luche en Gi y en No-Gi tiene dos `event_registration_id` distintos y
    debe salir en una sola ficha, con todos sus combates juntos.

    Los combates van referenciados por id en vez de anidados: cada combate tiene
    dos atletas y anidarlo lo duplicaría en el JSON que descargan los móviles.
    """
    medallas = derivar_medallas(combates)
    atletas = OrderedDict()

    for c in combates:
        for lado in c["sides"]:
            clave = lado["athleteId"]
            atleta = atletas.get(clave)
            if atleta is None:
                atleta = atletas[clave] = {
                    "id": clave,
                    "registrationIds": [],
                    "events": [],
                    "name": lado["name"],
                    "club": lado["club"],
                    "country": lado["country"],
                    "image": lado["image"],
                    "categories": [],
                    "matchIds": [],
                    "medals": medallas.get(clave, []),
                    "bestMedal": mejor_medalla(medallas.get(clave, [])),
                }
            atleta["matchIds"].append(c["id"])
            for lista, valor in (("registrationIds", lado["registrationId"]),
                                 ("events", c["eventId"]),
                                 ("categories", c["category"].get("raw"))):
                if valor and valor not in atleta[lista]:
                    atleta[lista].append(valor)
            # La foto puede faltar en una inscripción y estar en la otra.
            if not atleta["image"] and lado["image"]:
                atleta["image"] = lado["image"]

    return list(atletas.values())


def clave_orden(combate):
    """Orden cronológico, con los que no tienen hora al final."""
    return (combate.get("estimatedStart") is None,
            combate.get("estimatedStart") or "",
            combate.get("mat") or "",
            combate.get("matchNr") or 0)


def construir_estado(*, eventos, datos_por_evento, fetched_at,
                     streams=None, grupo=None, stale=False, stale_since=None):
    """Arma el data.json combinando todos los eventos configurados.

    `eventos` es la lista de {id, label, name} y `datos_por_evento` un
    {event_id: (dias, mats, combates_por_mat)} con las respuestas crudas. Un
    evento sin datos (todavía sin schedule publicado) simplemente no aporta
    nada, sin romper el resto.

    Los combates se deduplican por id: uno movido de tatami a mitad de lectura
    aparece en dos listas. El id lleva el evento delante, así que dos eventos
    no pueden pisarse aunque Smoothcomp repita numeración.
    """
    resumen_eventos = []
    todos_mats = []
    vistos = {}

    for evento in eventos:
        event_id = str(evento["id"])
        dias, mats, combates_por_mat = datos_por_evento.get(event_id, ([], [], {}))

        resumen_eventos.append({
            "id": event_id,
            "label": evento.get("label"),
            "name": evento.get("name"),
            "days": [{"id": d.get("id"), "name": d.get("name"), "date": d.get("date")}
                     for d in dias],
        })

        for m in mats:
            todos_mats.append({
                "key": f"{event_id}:{m.get('id')}",
                "id": m.get("id"),
                "name": m.get("name"),
                "eventId": event_id,
                "eventLabel": evento.get("label"),
                "day": (m.get("dayDate") or "")[:10] or None,
                "dayName": m.get("dayName"),
                "estimatedStart": m.get("estimated_start"),
                "estimatedEnd": m.get("estimated_end"),
            })

        mats_por_id = {m["id"]: m for m in mats}
        for mat_id, crudos in combates_por_mat.items():
            mat = mats_por_id.get(mat_id, {"id": mat_id, "name": None})
            for crudo in crudos:
                combate = parse_combate(crudo, mat, evento)
                vistos.setdefault(combate["id"], combate)

    combates = sorted(vistos.values(), key=clave_orden)
    atletas = construir_atletas(combates)

    # La lista que ve todo el grupo sin tener que seguir a nadie. Se marca aquí
    # para que el frontend no tenga que cruzar listas en cada repintado.
    grupo = grupo or {}
    del_grupo = {a.get("id") for a in (grupo.get("atletas") or []) if a.get("id")}
    for atleta in atletas:
        atleta["inGroup"] = atleta["id"] in del_grupo

    return {
        "events": resumen_eventos,
        "group": {
            "name": grupo.get("nombre") or None,
            # Se conservan tal cual, incluidos los que no compiten (alguien que
            # al final no se inscribió): así la lista no se pierde sola.
            "athletes": grupo.get("atletas") or [],
        },
        "fetchedAt": fetched_at,
        "stale": stale,
        "staleSince": stale_since,
        "mats": todos_mats,
        "streams": streams or [],
        "matches": combates,
        "athletes": atletas,
    }
