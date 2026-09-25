# Fase 0 — Fuente de datos de AJP Tour / Smoothcomp

Estado: **cerrada**. Hay endpoints JSON públicos con todos los datos que necesita la aplicación.

> **Corrección importante (2026-09-20).** La primera versión de este documento concluía que
> `ajptour.com` era inaccesible de forma automatizada y que la causa era la *reputación de la IP de
> datacenter*. **Ese diagnóstico era incorrecto.** El Cloudflare Managed Challenge afecta solo a las
> páginas **HTML**; los endpoints `.json` de la aplicación no pasan por él y responden **200 de forma
> anónima desde esta misma máquina y red**. La conclusión de que hacía falta un dispositivo en red
> residencial se retira. Lo que sigue es lo verificado con peticiones reales.

Evento de referencia: `1535` = **AJP NO-GI MADRID INTERNATIONAL JIU-JITSU CHAMPIONSHIP 2026**.
Evento usado para capturar datos reales: `1257` (pasado, con schedule publicado).

## Resumen ejecutivo

1. `ajptour.com` es **Smoothcomp white-label**: mismas rutas `/{lang}/event/{id}/...`.
2. Las **páginas HTML** de evento sí están tras el Managed Challenge (`Cf-Mitigated: challenge`).
3. Los **endpoints JSON del schedule no lo están** y no requieren login:

   ```
   /en/event/{id}/schedule/new/matcategories.json        -> días
   /en/event/{id}/schedule/new/mats.json/{dayId}         -> tatamis del día
   /en/event/{id}/schedule/new/mat/{matId}/matches.json  -> combates del tatami
   ```

4. Un combate trae **todo lo que pide el encargo**: hora, tatami, ronda, categoría completa, rival,
   resultado y estado.
5. El evento `1535` devuelve hoy `403 - not allowed` en esos endpoints porque **su schedule aún no
   está publicado** (su página dice literalmente *"Brackets are not published yet"*), no por un
   bloqueo. El mismo 403 se obtiene con sesión iniciada y sin ella.

## 1. ¿HTML en servidor o hace falta JavaScript?

**Ni una cosa ni la otra: no hace falta parsear HTML.** Los datos se obtienen como JSON de los tres
endpoints de arriba, sin navegador y sin ejecutar JavaScript.

## 2. ¿Endpoints JSON internos?

**Sí** (los tres de arriba). Descubiertos leyendo `matches.js` de
[smoothcomp-winrate](https://github.com/Mohamed3on/smoothcomp-winrate), una extensión que hace algo
equivalente, y verificados después contra el origen real.

`matcategories.json` devuelve un **objeto** si el evento tiene un solo día y una **lista** si tiene
varios; hay que normalizarlo.

## 3. ¿Qué protección anti-bot hay?

- Las páginas HTML de evento devuelven 403 con `Cf-Mitigated: challenge`
  (`fixtures/http_403_challenge_headers.txt`). Ni Playwright ni `patchright` lo pasan desde aquí.
- **Los `.json` no pasan por el challenge.** Su 403, cuando ocurre, es de la aplicación
  (`<title>403 - not allowed</title>`, `Content-Type: application/json`), que es una señal
  completamente distinta y significa "no hay datos publicados / no tienes acceso".
- `robots.txt` no prohíbe `/event/` (`fixtures/robots.txt`). Se respeta una pausa entre peticiones.

Distinguir estos dos 403 es lo que desatascó la investigación: el primero es anti-bot, el segundo no.

## 4. Buscador de atletas del evento

No hace falta endpoint propio: los atletas se derivan de los `seats` de los combates, cada uno con
`name`, `club`, `country`, `image` y `event_registration_id` (identificador estable dentro del
evento). La búsqueda se hace en el cliente.

## 5. Representación de un combate

Campos reales, presentes en 443/443 combates del evento 1257:

| campo | ejemplo | uso |
| --- | --- | --- |
| `id` | `1040311` | identidad, deduplicación |
| `bracket_id` | `109158` | agrupar por categoría (85 brackets = 85 categorías) |
| `name` | `"Final"`, `"Bronze match"`, `"Semifinals"` | ronda (puede ser `null`) |
| `round` | `1` | número de ronda |
| `group` | `"Men's GI / Brown / Master 1 / 62KG"` | categoría completa |
| `state` | `finished`, `running`, `seeded`, `unseeded` | estado |
| `wonBy` | `points`, `submission`, `decision`, `walkover`, `disqualification`, `stoppage` | resultado |
| `estimated_start` | `"2025-09-05T11:35:30+04:00"` | hora **estimada** |
| `mat_match_nr` | `"8-7"` | orden dentro del tatami |
| `time_passed` | `"05:00"` | duración |
| `seats[]` | `name`, `club`, `country`, `image`, `isWinner`, `status`, `event_registration_id` | rivales |

El tatami no viene como campo propio en este tenant: se conoce por el endpoint del que procede el
combate (en smoothcomp.com sí aparece además un `mat_name`).

Los `seats` con `type != "registration"` son plazas pendientes ("Loser from 1-91") y no son atletas;
en el evento 1257 no apareció ninguno (886 seats = 443 × 2, todos `registration`).

## 6. Medallas y categoría completa

- **Categoría completa** en `group`, con formato AJP de cuatro partes:
  `División (incluye GI/NO-GI) / Cinturón / Grupo de edad / Peso`.
  Ejemplos: `Men's GI / Black / Master 1 / 120KG`, `Women's GI / Blue / Amateur / 70KG`.
  Gi/No-Gi va en la primera parte, así que **no hace falta configurarlo a mano**.
- **Medallas derivables del propio schedule**, sin usar `/results` (que sí está tras el challenge):
  el ganador de `Final` es oro, el perdedor plata, y el ganador de `Bronze match` bronce.
  En el evento 1257: 85 categorías, 82 finales y 74 combates por el bronce; las categorías sin final
  son brackets pequeños, donde el único combate hace de final (`name` puede ser `null`).

## 7. Mapeo de streams de YouTube a tatamis

**Sin resolver.** No existe pestaña `/livestreams` en este tenant (404). El único indicio es que un
tatami se llama `"Mat 5 - TV"`, lo que sugiere que solo se retransmite uno. Mientras no aparezca una
fuente automatizable, el mapeo tatami → URL se configura a mano en `config.json`.

## 8. Nº de atletas/combates típico y paginación

Evento 1257 (AJP, un día): **9 tatamis, 443 combates, 85 categorías, 886 plazas**. Entre 45 y 54
combates por tatami. **No hay paginación**: cada endpoint de tatami devuelve su lista completa.

Un ciclo de refresco cuesta `1 + nº días + nº tatamis` peticiones (~11 para un evento así).

## Fixtures

- `fixtures/event_1257/` — captura real completa: `days.json`, `mats_<día>.json`,
  `matches_<tatami>.json`, `_resumen.json`. Es la base contra la que se escribe y prueba el parser.
  **Anonimizada**: el repositorio es público, así que los nombres se sustituyen por `Atleta N`, se
  eliminan las URLs de foto (llevan el nombre y apellidos dentro) y se renumeran los identificadores
  de inscripción. Se conservan club, país y categoría, que no son datos personales. Lo hace
  `research/anonymize_fixtures.py`, y `tests/test_fixtures_anonimos.py` falla si algo se cuela.
  Reduce la exposición pero no la elimina: cruzando club, categoría y resultado con ajptour.com aún
  se podría reidentificar a alguien.
- `fixtures/event_1535_*.html`, `fixtures/event_1535_tabs.json` — evento objetivo: páginas reales ya
  con sesión, y las pestañas que existen de verdad (`participants`, `results`, `schedule/brackets`,
  `schedule/matchlist`, `schedule/new`; **no** hay `livestreams`, `matches`, `brackets` ni
  `information` como rutas propias).
- `fixtures/robots.txt`, `fixtures/http_403_challenge_headers.txt` — evidencia del challenge en HTML.
- `fixtures/event_1535_home.html`, `event_1535_patchright.html`, `network_log*.json` — material de la
  investigación inicial; son **páginas de challenge**, no contenido de evento.

## Scripts de investigación (no forman parte de la app)

- `research/probe_events.py` — sondea varios eventos con y sin cookies. Es el que demostró que el
  login no hace falta y que el 403 del 1535 es "no publicado".
- `research/capture_event.py` — vuelca el schedule completo de un evento a `fixtures/` y resume su forma.
- `research/explore_event.py` — explora las pestañas reales de un evento con navegador y captura XHR.
- `research/login_once.py` — guarda una sesión en `secrets/` (Chrome con perfil persistente).
  **Ya no es necesario para leer datos**; se conserva por si alguna pestaña futura lo requiere.
- `research/probe_session.py`, `explore.py`, `explore_patchright.py`, `capture_fixtures.py` — pruebas
  anteriores, conservadas para poder auditar el recorrido.

## Datos reales del torneo (capturado el 2026-09-25)

Ambos eventos publicados, dos jornadas cada uno:

| | No-Gi (1535) | Gi (1526) |
| --- | --- | --- |
| Sábado 26 | 16:40 – 19:10 | 10:00 – 17:24 |
| Domingo 27 | desde 12:00 | desde 10:30 |
| Combates | 179 | 643 |

**822 combates, 717 atletas, de los que 134 compiten en los dos eventos** (de ahí que unificar por
nombre + club no fuera un lujo).

Diferencias respecto al evento 1257, que es contra el que se escribió el parser:

- **Plazas `tbd`.** Un bracket sin empezar tiene plazas por determinar esperando al ganador de otra
  ronda: 291 de los 822 combates no tienen todavía ningún atleta conocido y 126 tienen solo uno. El
  parser ya las descarta (solo acepta `type == "registration"`) y la web muestra "Por determinar".
- **`mat_name` sí viene** en este evento, al contrario que en el 1257. Se sigue usando el tatami del
  endpoint, que es fiable en ambos casos.
- **Seis tatamis físicos** ("Mat 1"…"Mat 6") reutilizados en las cuatro combinaciones evento×día con
  ids distintos: 24 entradas para 6 tatamis reales.
- Nivel **"Professional"** además de Amateur y Master, y cinturones combinados con guion
  (`Grey - Yellow`). El parseo de categorías los aguanta.

**Streams:** la ruta es `/en/event/<id>/livestream` (en singular; el plural da 404) y solo contiene
el canal genérico de YouTube de AJP (`UC7m2_Wx33tfrMYYVMVqIOzg`), sin enlaces por tatami. El mapeo
tatami → URL se configura a mano en `config.streams`, y como la configuración se relee en cada
ciclo, se puede añadir con el scraper en marcha.

## Lo que queda abierto

1. **El schedule del evento 1535 no está publicado.** Hasta que AJP lo publique (normalmente días
   antes), no se pueden capturar sus datos reales. Se trabaja contra el 1257.
2. **Streams por tatami** (pregunta 7): sin fuente automatizable conocida.
3. **Estado en vivo**: el 1257 está terminado, así que todos sus combates están `finished`. El
   comportamiento de `running` y `time_passed` durante un evento en curso no se ha observado en AJP
   (sí en el evento `29650` de smoothcomp.com, que mostraba `running`, `seeded` y `unseeded`).
