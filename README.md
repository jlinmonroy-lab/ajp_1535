# AJP en directo

Seguimiento casi en tiempo real de un torneo de AJP Tour para un grupo pequeño de personas:
buscar atletas, ver sus combates (hora estimada, tatami, ronda, rival, resultado, estado) y sus
medallas, desde el móvil y sin coste.

Evento objetivo: **1535 — AJP NO-GI MADRID INTERNATIONAL JIU-JITSU CHAMPIONSHIP 2026**.

## Cómo funciona

Smoothcomp (la plataforma de la que `ajptour.com` es una instancia) expone tres endpoints JSON
públicos con el schedule. El scraper los lee cada ~75s desde un PC, los normaliza a un `data.json`
y lo publica como fichero estático; los móviles solo hablan con esa copia, nunca con AJP.

Detalle de la fuente en [`docs/data-source.md`](docs/data-source.md) y del diseño en
[`docs/architecture.md`](docs/architecture.md).

## Uso

Requiere solo Python 3 (sin dependencias; `patchright` únicamente para los scripts de `research/`).

```sh
python -m scraper.main --once            # un ciclo contra el evento de config.json
python -m scraper.main --once --event 1257   # contra otro evento
python -m scraper.main                   # bucle continuo
```

Ver el frontend en local:

```sh
python -m http.server 8765 --directory site
# y abrir http://localhost:8765/
```

Pruebas (no tocan la red, usan las fixtures del evento 1257):

```sh
python -m unittest discover -s tests
python research/smoke_site.py            # recorre el frontend y captura pantallas
```

## Configuración

Todo en `config.json`: `eventId`, ritmo de refresco, pausa entre peticiones, umbral de `stale`,
mapeo de streams por tatami y opciones de publicación por git.

## Estado

Funciona de punta a punta contra eventos con schedule publicado (probado con el 1257: 443 combates,
446 atletas, 9 tatamis). **El evento 1535 aún no tiene schedule publicado**, así que hasta que AJP
lo publique no se pueden ver sus datos reales.

Pendiente: publicar en GitHub Pages y medir la latencia real de publicación.
