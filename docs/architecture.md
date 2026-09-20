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

## Latencia de publicación: medida y validada

Medido el 2026-09-20 con `research/measure_latency.py --ciclos 15 --intervalo 75`
(informe completo en `docs/latencia.md`):

| vía | medidas | mediana | p90 | máximo | sobrescritos | 429 |
| --- | --- | --- | --- | --- | --- | --- |
| **GitHub Pages** | 15 | **21,1s** | 23,4s | 24,1s | 0 | **0** |
| raw.githubusercontent | 1 | 272,9s | — | — | — | 0 |

**Opción A validada.** Pages publica en ~21s de forma muy estable (todas las medidas entre 18,9s
y 24,1s), seis veces por debajo del requisito de 2 min, y aguantó 15 builds seguidos a ritmo de
~48/hora sin un solo 429 pese al límite blando documentado de 10/hora.

`raw.githubusercontent` queda **descartado**: sus 272,9s confirman su cache de ~5 min.

Dos advertencias que conviene no olvidar:

1. **19 minutos no prueban 10 horas.** El límite de Pages es *blando*: que no saltara en 15 builds
   no garantiza que aguante los ~480 de una jornada completa. Durante el evento hay que vigilar
   que `data.json` se siga actualizando; si apareciera un 429, la salida es publicar mediante un
   workflow propio de GitHub Actions, donde ese límite no se aplica.
2. Para reducir el riesgo, `publicar()` **no publica cuando no ha cambiado nada de fondo**
   (comparando sin `fetchedAt`/`stale`), con un refresco de cortesía cada 5 minutos para que la
   antigüedad que muestra la web sea cierta. Subir `refreshSeconds` a 90 o 120 bajaría el ritmo a
   30-40 builds/hora si hiciera falta más margen.

Si algún día hay que cambiar de vía, solo se toca `publish.py`: el parseo y el frontend no se
enteran.

## Pendiente

1. ~~Crear el repo, la rama `gh-pages` y activar Pages.~~ Hecho:
   https://jlinmonroy-lab.github.io/ajp_1535/
2. ~~Medir la latencia real.~~ Hecho: 21,1s de mediana, Opción A validada.
3. **Ensayo general**: dejar el scraper en bucle con `publish.enabled`, comprobando que publica,
   que marca `stale` al perder la red y que se recupera solo.
4. Repetir la captura contra el evento 1535 cuando publiquen su schedule, y comprobar el
   comportamiento de los estados `running`/`seeded`, que no se ha podido observar en un evento AJP.
5. Streams por tatami: sin fuente automatizable; se configuran a mano en `config.json`.
