# Latencia de publicación

Medido el 2026-09-20 20:42 con
`python research/measure_latency.py --ciclos 15 --intervalo 75`.

Se publica un identificador único cada **75s exactos** (el ritmo real del evento,
~48 builds/hora) y en paralelo se sondea cada 2s qué versión sirve el CDN. Push y
sondeo van en hilos separados: encadenarlos hace que esperar al dato retrase el push siguiente,
y se acaba midiendo un ritmo que no es el real.

Sin cache-busting en las peticiones, para medir lo que vería un móvil de verdad.

| vía | medidas | mediana | p90 | máximo | sobrescritos | 429 |
| --- | --- | --- | --- | --- | --- | --- |
| pages | 15 | 21.1s | 23.4s | 24.1s | 0 | 0 |

Requisito del proyecto: **<2 min (120s)**.
*Sobrescritos* = versiones que otro push reemplazó antes de que el CDN llegara a servirlas.

## Incidencias

```
ninguna
```

## Detalle

Publicados: 15 · medidos: 15 · sin resolver al cerrar: 0

```
{
  "n1789928547x1": {
    "pages": 22.9
  },
  "n1789928622x2": {
    "pages": 21.1
  },
  "n1789928697x3": {
    "pages": 19.5
  },
  "n1789928772x4": {
    "pages": 22.1
  },
  "n1789928847x5": {
    "pages": 18.9
  },
  "n1789928922x6": {
    "pages": 23.4
  },
  "n1789928997x7": {
    "pages": 21.8
  },
  "n1789929072x8": {
    "pages": 20.4
  },
  "n1789929147x9": {
    "pages": 21.1
  },
  "n1789929222x10": {
    "pages": 20.0
  },
  "n1789929297x11": {
    "pages": 20.9
  },
  "n1789929372x12": {
    "pages": 24.1
  },
  "n1789929447x13": {
    "pages": 23.3
  },
  "n1789929522x14": {
    "pages": 21.0
  },
  "n1789929597x15": {
    "pages": 19.8
  }
}
```
