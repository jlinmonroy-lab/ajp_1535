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

## El día del torneo

```sh
python arrancar_evento.py
```

Deja esa ventana abierta y ya está. El lanzador:

- **impide que Windows suspenda el equipo** mientras esté abierto (sin tocar el plan de energía:
  al cerrarlo, todo vuelve a su sitio);
- **relanza el scraper si se cae**, apuntando cada incidencia en `registro/evento.log`;
- levanta también el panel local.

No puede cubrir un corte de luz, un reinicio por actualizaciones de Windows ni una caída del wifi,
así que conviene dejar el equipo enchufado y posponer las actualizaciones antes de salir.

Si prefieres arrancarlo a mano, `python -m scraper.main` hace lo mismo sin supervisión.

El panel sirve la web en <http://127.0.0.1:8765> y **ahí** aparece el botón
**«Seguir para todos»** en cada atleta. Al pulsarlo se añade a la lista del grupo, que viaja en el
`data.json` y la ve todo el mundo sin tener que seguir a nadie. Tarda hasta ~2 minutos en llegar a
los móviles (ciclo del scraper + publicación de Pages + refresco del navegador).

En la web pública ese botón no existe: escribir la lista solo puede hacerse desde el equipo donde
corre el scraper. Cada persona puede, además, seguir a quien quiera en su propio móvil.

El panel escucha únicamente en `127.0.0.1`, para que nadie de la wifi del pabellón pueda cambiar la
lista de todos.

## Ver cómo se comportará durante el torneo

```sh
python research/simular_evento.py
```

Reproduce las dos jornadas en unos minutos sobre una **copia aislada** en `tmp-demo/`, servida en
<http://127.0.0.1:8766>: los combates arrancan y terminan, los horarios se retrasan, los cuadros
avanzan y caen las medallas. Los del grupo tienen guion (oro, plata y bronce) para que se vea el
recorrido completo.

No toca `site/data.json` ni publica nada, y la copia lleva un banner rojo de SIMULACIÓN. Los
resultados son inventados.

## Configuración

Todo en `config.json`: `eventId`, ritmo de refresco, pausa entre peticiones, umbral de `stale`,
mapeo de streams por tatami y opciones de publicación por git.

## Estado

Funciona de punta a punta contra eventos con schedule publicado (probado con el 1257: 443 combates,
446 atletas, 9 tatamis). **El evento 1535 aún no tiene schedule publicado**, así que hasta que AJP
lo publique no se pueden ver sus datos reales.

Pendiente: publicar en GitHub Pages y medir la latencia real de publicación.
