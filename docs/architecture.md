# Fase 1 — Arquitectura

Estado: **Opción A elegida e implementada**, pendiente de publicar en GitHub.

## Punto de partida (corregido)

La primera versión de este documento partía de que `ajptour.com` bloqueaba todo acceso automatizado
desde IPs de datacenter y que, por tanto, el scraper tenía que ejecutarse desde un dispositivo en red
residencial. **Ese punto de partida era incorrecto** y se ha retirado: ver la corrección en
`docs/data-source.md`.

Lo verificado (2026-09-20):

- Los endpoints JSON del schedule son **públicos**: responden 200 **sin cookies** desde esta misma
  máquina y red. Se comprobó con los eventos AJP 1257, 1216 y 1151.
- El Cloudflare Managed Challenge afecta solo a las **páginas HTML**, que no necesitamos.
- El evento objetivo `1535` devuelve 403 porque **su schedule aún no está publicado**, no por un bloqueo.

Consecuencias sobre el diseño original:

- **No hace falta login.** No hay cookies que caduquen, ni secretos que rotar, ni `auth.py`.
- **No hace falta navegador** en el ciclo de refresco: basta HTTP simple.
- **No hace falta una IP concreta.** El scraper podría correr en cualquier sitio; se ejecuta en el
  PC del usuario porque así se decidió, no porque sea obligatorio.

## Opción A — Relé estático vía GitHub

```
[PC del usuario]                    [GitHub Pages, gratis]        [~20 móviles]
  python -m scraper.main         →    rama gh-pages sirve      →   fetch cada 30s
  cada 75s:                           data.json + frontend         con ETag
  - 1 + días + tatamis peticiones
  - normaliza a data.json
  - commit --amend + push --force
```

- Un ciclo son `1 + nº días + nº tatamis` peticiones (~11 en un evento de 9 tatamis), espaciadas
  2s. La regla original de "una petición por ciclo" no era alcanzable: los combates se piden por
  tatami. Decidido con el usuario.
- El frontend nunca habla con `ajptour.com`: solo con GitHub Pages.
- `commit --amend` + `push --force` sobre `gh-pages` deja el historial de datos en **un solo commit**.

## Estructura

| Ruta | Qué hace |
| --- | --- |
| `config.json` | evento, ritmo de refresco, pausas, streams, publicación |
| `scraper/fetch.py` | lee los tres endpoints; reintenta 429/5xx, nunca 403/404 |
| `scraper/parse.py` | normaliza al modelo; deriva medallas; **puro, sin red** |
| `scraper/publish.py` | escritura atómica + commit/push. Aislado a propósito |
| `scraper/main.py` | bucle, control de `stale` |
| `site/` | frontend estático (HTML/CSS/JS vanilla, sin build) |
| `tests/test_parse.py` | 19 pruebas contra la captura real del evento 1257 |
| `research/` | scripts de investigación, no forman parte de la app |

Sin dependencias: todo con biblioteca estándar. `patchright` solo lo usan los scripts de `research/`.

## Modelo de datos

Ver `docs/data-source.md` para el origen y `scraper/parse.py` para la forma exacta. Dos decisiones
que se apartan de la especificación inicial:

1. **`athletes[].matchIds` en vez de combates anidados.** Cada combate tiene dos atletas; anidarlo
   lo duplicaría. El frontend los presenta anidados igual.
2. **`medals` es una lista** (no un solo campo), porque un atleta puede competir en varias
   categorías. `bestMedal` resume la mejor.

## Riesgo abierto: latencia de publicación

GitHub Pages reconstruye en cada push y recomienda un máximo aproximado de 10 builds/hora; un push
cada 75s son ~48/hora. **Está sin medir.** Si la mediana supera los 2 min exigidos, solo cambia
`publish.py`:

- servir `data.json` desde `raw.githubusercontent.com` (sin build, cache ~5 min), o
- pasar a la Opción B (Cloudflare Worker + KV, escritura sin build).

El parseo y el frontend no cambian en ninguno de los dos casos.

## Pendiente

1. Crear el repo en GitHub, la rama `gh-pages` y activar Pages.
2. **Medir la latencia real** de publicación antes de dar la arquitectura por buena.
3. Repetir la captura contra el evento 1535 cuando publiquen su schedule, y comprobar el
   comportamiento de los estados `running`/`seeded`, que no se ha podido observar en un evento AJP.
4. Streams por tatami: sin fuente automatizable; se configuran a mano en `config.json`.
