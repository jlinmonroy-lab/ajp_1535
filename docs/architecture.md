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
| `web/` | frontend: React + TypeScript + Vite (ver «El frontend» más abajo) |
| `site/` | la web compilada, salida de `web/`; no se versiona |
| `tests/test_parse.py` | 19 pruebas contra la captura real del evento 1257 |
| `research/` | scripts de investigación, no forman parte de la app |

El servidor y el scraper no tienen dependencias: todo con biblioteca estándar. `patchright` solo lo usan
los scripts de `research/`. Node solo hace falta para compilar la web.

## El frontend

`web/` es una aplicación React + TypeScript (Vite), partida en dos a propósito:

- `web/src/ui/` — **librería de componentes** (`@fcteam/ui`). Son presentacionales: reciben textos ya
  formateados y callbacks, y no leen la red, `localStorage`, la URL ni el reloj. Colores y medidas salen
  de `tokens.css`. Se compila también como paquete (`npm --prefix web run build:lib` → `web/dist/`: JS,
  `style.css` y los `.d.ts` con las props), que es lo que consume `/design-sync` para llevar el sistema de
  diseño a Claude Design.
- `web/src/app/` — la web: lo que habla con el servidor (`api.ts`), el sondeo con ETag
  (`usarSondeoEvento`), la búsqueda de eventos, la ruta por hash y lo que es de este navegador (a quién
  sigues). `selectores.ts` traduce los datos de la API a las props de `ui`.

La web importa `src/ui` directamente; el paquete solo existe para quien lo consuma desde fuera. Las
direcciones de la API son **relativas** (`api/config`) y Vite compila con `base: './'`, para que la web siga
funcionando colgada de una subcarpeta (GitHub Pages). Con el servidor sirviendo `site/`, los ficheros de
texto salen con gzip y se revalidan con ETag.

## Dos eventos, una sola web

El 26-27 de septiembre coinciden en el Polideportivo José Caballero dos eventos AJP distintos:
**1535** (No-Gi) y **1526** (Europe Continental, Gi). Se sirven combinados para que quien compita
en ambos vea todos sus combates juntos y ordenados por hora.

Eso obliga a tres cosas:

1. **Identidad de los combates y tatamis por evento.** Smoothcomp numera por evento, así que dos
   eventos pueden repetir id de combate, de bracket y de tatami, y los dos tienen un "Mat 1". Los
   ids llevan el evento delante y la clave de un tatami es `eventId:matId`.
2. **Atletas unificados por nombre + club.** `event_registration_id` es único por evento: la misma
   persona llega con dos identificadores y nada en los datos los relaciona. Se agrupa por nombre y
   club normalizados (sin acentos ni mayúsculas), y el atleta guarda sus `registrationIds` y los
   `events` en los que compite. Riesgo asumido: un nombre escrito distinto en cada inscripción
   saldría duplicado, y dos homónimos del mismo club se fusionarían.
3. **Un evento que falle no tumba al otro.** Es lo normal estos días, con uno publicado y el otro
   aún en 403: se publica lo que haya y solo se cuenta como fallo si no se puede leer ninguno.

Coste por ciclo: ~22 peticiones (1 + días + tatamis, por evento). El `data.json` pasa a ~905 KB en
crudo pero **58 KB comprimidos**, que es lo que viaja: Pages sirve con `Content-Encoding: gzip`.

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


---

# Fase 2 — Multi-evento bajo demanda

Estado: **implementada**. Sustituye a la Opción A como forma normal de uso; la Opción A queda como
modo «instantánea estática» (`scraper.main` + `publish.py`).

## Por qué cambia la arquitectura

La Opción A sirve un fichero estático con **un** evento, que alguien eligió de antemano en
`config.json`. Poder buscar cualquier evento de smoothcomp.com rompe esa premisa: ya no se sabe qué
hay que leer hasta que alguien lo pide. Hace falta algo que lea bajo demanda.

## Decisión: servidor con caché compartida, no solo navegador

Smoothcomp contesta con `Access-Control-Allow-Origin` igual al `Origin` que recibe (comprobado), así
que un navegador *podría* leerlo directamente y seguir en GitHub Pages. Se descartó:

| | Servidor con caché (elegida) | Solo navegador |
| --- | --- | --- |
| Peticiones a Smoothcomp con 20 móviles | las de **un** cliente por evento y ciclo | las de 20: ~22 peticiones × 20 cada 75 s |
| En la wifi de un pabellón | una IP, un ritmo controlado | **una sola IP pública para todos** → 429 (se observó uno a ~150 peticiones rápidas) |
| `parse.py`, las medallas y sus pruebas | se reutilizan | hay que portarlos a JavaScript |
| Depende de | nada especial | una cabecera CORS que no está documentada |
| Coste | hay que tener un servidor encendido | ninguno |

El coste del servidor se asume: el equipo que hacía de scraper el día del torneo ya estaba
encendido de todas formas.

Segunda decisión: **biblioteca estándar** (`ThreadingHTTPServer`) en vez de FastAPI, para mantener el
«requiere solo Python 3, sin dependencias». Lo que FastAPI daría gratis (gzip, ETag, rutas) son unas
~100 líneas.

## Piezas

```
móvil ──► scraper/servidor.py ──► Buscador ──────────► smoothcomp.com/…/events/{upcoming|past}
          (web + API JSON)   └─► Almacén ──hilos──► smoothcomp.com/…/schedule/new/…
                                    ▲
                                    └─ fetch.RITMO: una petición a la vez, con pausa
```

| Módulo | Responsabilidad |
| --- | --- |
| `fetch.py` | cliente HTTP; **todo** el tráfico pasa por `RITMO`; distingue 403 «no publicado», 404 «no existe» y reto de Cloudflare |
| `eventos.py` | `Buscador`: lista de eventos con caché (10 min), copia vieja si Smoothcomp falla, y memoria de a qué subdominio pertenece cada evento |
| `almacen.py` | `Almacen`: estado ya convertido, serializado y comprimido por evento; refresco bajo demanda |
| `parse.py` | sin cambios de fondo: puro, sin red |
| `grupos.py` | lista del grupo por evento, en `data/grupos.json` |
| `servidor.py` | rutas, gzip/ETag, y la guarda del panel local |

## Cómo se atiende una petición

La petición **nunca** lee Smoothcomp. Pide al almacén, que contesta con lo que tiene:

1. **Evento nuevo:** se crea la entrada, se encola su lectura y se contesta `202 cargando`. La web
   enseña «Leyendo el schedule…» y vuelve a preguntar a los 3 s.
2. **Entrada fresca** (menos de `refreshSeconds`): se sirve tal cual; si el cliente trae el `ETag`, `304`.
3. **Entrada caducada:** se sirve igual y **se encola un refresco** detrás (*stale-while-revalidate*).
   Nadie espera. Como quien abre un evento que nadie miraba recibiría datos viejos hasta su siguiente
   sondeo, la web vuelve a preguntar a los 5 s si lo recibido es más viejo que un ciclo.
4. **Nadie lo mira** durante `inactividadMinutos`: se olvida. No hay ningún bucle por evento, así que el
   tráfico hacia Smoothcomp es proporcional a lo que se **está** mirando, no a lo que se ha mirado.

Cada lectura la hacen unos hilos (`workers`) que sacan de una cola sin duplicados. Da igual cuántos
hilos haya: `RITMO` deja pasar una petición a la vez, con `requestPauseSeconds` de pausa.

### Estados de un evento

| Situación | Qué pasa |
| --- | --- |
| Schedule publicado | `200` con el estado; `events[].published = true` |
| Aún sin publicar (403 de la aplicación) | `200` sin combates y `published = false`; la web lo explica |
| El id no existe (404) | `404`; no se vuelve a preguntar en 5 min |
| Smoothcomp falla, sin copia | `502`, reintento a los 15 s |
| Smoothcomp falla, con copia | se sigue sirviendo; tras `staleAfterFailures` fallos seguidos, `stale = true` |
| Reto de Cloudflare | se cuenta como fallo («nos bloquean»), **no** como «no publicado» |

### Acotado

Un servidor abierto a internet con «cualquier id» invita a sondear. Por eso: ids solo con dígitos (van
dentro de la URL que se pide), como mucho 3 eventos a la vez, `maxEventosEnCache` entradas (se echa la
menos reciente), como mucho 10 lecturas en cola (más es `503`), y el host al que se pide sale de la
lista de Smoothcomp y solo se acepta si es `smoothcomp.com` o un subdominio por https.

## El panel del grupo con un túnel por medio

Escribir la lista del grupo solo se permite desde el equipo del servidor. El panel antiguo lo
resolvía escuchando solo en `127.0.0.1`, pero un túnel (cloudflared, ngrok) **conecta desde
`127.0.0.1`**: con solo mirar la IP, cualquiera con el enlace público podría cambiar la lista. Se
exige a la vez:

1. IP de origen en loopback;
2. `Host` local (`localhost`, `127.0.0.1`, `::1`);
3. ninguna cabecera de proxy (`X-Forwarded-For`, `Forwarded`, `CF-Connecting-IP`…);
4. si hay `Origin`, que sea el propio servidor, y `Content-Type: application/json`. Sin esto, una
   página cualquiera abierta en el navegador del operador podría hacer un `POST` a `127.0.0.1`
   (CSRF); un formulario no puede mandar JSON sin que el navegador pida antes un `OPTIONS`, que no
   se contesta.

Además, en Windows `http.server` abre el puerto con `SO_REUSEADDR`, que allí deja que **dos procesos
compartan puerto sin error**: el segundo servidor «arrancaba» y nadie sabía cuál contestaba. Se
desactiva en Windows, y el lanzador distingue «no pude arrancar» (código 3) de una caída (que
relanza).

## Qué se descartó

- **Un hilo con bucle por evento**, como el scraper antiguo: cuesta tráfico por cada evento visto aunque
  nadie lo mire ya.
- **WebSockets / eventos del servidor:** Smoothcomp no ofrece push; sería polling por dentro igual.
- **Redis u otra caché externa:** un proceso, memoria, ~1 MB por evento; no hace falta.

## Pendiente

1. Probar con un torneo en directo de verdad. El estado `running` real solo se ha visto de pasada
   (un combate que quedó colgado en el Kimura Cup, ya terminado) y en el origen simulado: no se
   ha seguido un torneo entero mientras se jugaba.
2. Cuadros «todos contra todos» (`Match 1/3`…): no generan medallas.
3. Un sondeo `matches.json?upcoming=1` más barato para el «en vivo»: en las pruebas devolvía lo mismo.


## Publicación para móviles con datos (Tailscale Funnel)

Los móviles con datos propios no están en la wifi del equipo: necesitan una dirección pública con HTTPS.
Se usa **Tailscale Funnel**, que ya estaba instalado y activo: dirección fija, sin instalar nada y sin tocar
el cortafuegos. Se descartó `--host 0.0.0.0` (solo vale en la misma wifi), cloudflared (hay que instalarlo y
la dirección cambia en cada arranque) y, por entonces, un hosting (el panel del grupo solo funcionaba desde
el equipo del servidor, y habría que rediseñarlo con una clave de administración; ver «Alojamiento fijo»
más abajo, que es justo eso).

- **El servidor sigue escuchando solo en `127.0.0.1`.** Funnel conecta desde el propio equipo, así que
  no se abre ningún puerto a la red.
- **Puerto 8443.** El 443 de este Funnel lo usa otro servicio del equipo, que no se toca; Funnel admite
  443, 8443 y 10000. La web usa rutas relativas, así que funciona igual en cualquier puerto.
- **La guarda del panel sigue valiendo detrás de Funnel.** Funnel conecta desde `127.0.0.1`, pero reenvía
  el `Host` público (`…ts.net:8443`) y añade cabeceras de proxy; `es_panel_local` exige un `Host` local y
  ninguna cabecera de proxy, así que el `POST` al grupo da 403 por la dirección pública (comprobado con la
  dirección real). Es la razón de que esa comprobación no se pueda relajar «porque ya viene de localhost».
- **Enlace abierto.** Es una decisión asumida: cualquiera que lo encuentre puede usar el equipo para
  consultar Smoothcomp (ritmo global y topes de cola lo acotan) y leer la lista del grupo. Lo siguiente, si
  hiciera falta, es una clave en el enlace (cookie tras la primera visita), con el panel local exento.
- **Datos móviles.** Con la pestaña oculta no se sondea (`document.hidden`), y al volver a verse se pregunta
  enseguida con el ETag. Sin esto, un móvil en el bolsillo habría seguido gastando datos cada 30 s.

`scraper/publico.py` lee `tailscale funnel status` para que el lanzador diga el enlace; nunca cambia el túnel.

## Alojamiento fijo (Fly.io)

Funnel exige el equipo encendido, sin suspender y con el servidor lanzado. Para tener una dirección que funcione
siempre, el mismo servidor corre en una máquina de Fly.io (`Dockerfile`, `fly.toml`). El código casi no cambia;
lo que cambia es **quién puede escribir**, porque en un alojamiento la guarda «solo el equipo local» no se cumple
nunca (la IP de origen no es loopback y el proxy añade cabeceras).

- **Clave de administrador (`ADMIN_TOKEN`).** `POST /api/events/{ids}/grupo` se acepta desde el panel local **o**
  con la cabecera `X-Admin-Token` correcta (`servidor.tiene_clave`, comparación en tiempo constante). Sin
  `ADMIN_TOKEN`, el comportamiento es el de siempre: la cabecera no abre nada. El resto de comprobaciones
  (`Content-Type: application/json`, tamaño, validación) siguen valiendo con clave.
- **Por qué una cabecera y no una cookie o un parámetro.** Una cabecera propia obliga al navegador a pedir un
  `OPTIONS` antes de mandarla desde otra web, y el servidor no lo contesta: otra página no puede escribir aunque
  conozca la ruta. Con una cookie haría falta además protección CSRF. En la URL acabaría en el historial y en los
  registros.
- **La clave es larga o no hay servidor.** Menos de 16 caracteres impide arrancar (código 3): una clave fácil de
  adivinar dejaría la lista abierta a todo internet. El repositorio es público, así que la clave se pasa como
  secreto del alojamiento (`fly secrets set`), nunca en un fichero.
- **En la web.** `/api/config` añade `admin: true` solo si hay clave. La clave se escribe una vez por
  dispositivo, se guarda en `localStorage` y viaja en `X-Admin-Token`; al abrir la web se comprueba con
  `GET /api/admin` y, si el servidor ya no la acepta, se olvida. En el equipo del servidor no se ofrece: ya
  tiene el panel abierto.
- **Persistencia.** Lo único que se escribe en disco es `grupos.json`; `DATA_DIR` lo lleva a un volumen
  (`/data`). La caché de eventos sigue en memoria y se rehace sola tras un reinicio. Una sola máquina, porque la
  caché y el ritmo de peticiones a Smoothcomp son del proceso (`fly deploy --ha=false`).
- **Sin cambios en el puerto.** El servidor sigue leyendo `--puerto`/`config.json`; no se lee `PORT` del entorno
  porque el lanzador del día del torneo da por hecho el 8765 y una variable suelta en el equipo lo desincronizaría.

**Verificado (2026-10-09, Fly.io, París):** Cloudflare deja pasar a Smoothcomp desde la IP de la nube. La lista de
eventos (HTML) responde 200 y el Kimura Cup Madrid (26416) se lee entero: 712 combates, 661 atletas y 9 tatamis en
25 s; con él cargado el servidor ocupa ~38 MB de los 256 MB de la máquina. `data-source.md` solo lo había
comprobado desde una IP residencial, así que esto es una comprobación de un día en una IP concreta: si Cloudflare
endureciera, las salidas son otro proveedor/región o volver al equipo de casa con Funnel (el buscador degrada
a «abrir por número», ver `ErrorOrigen.desafio`).

**Se mantiene** la decisión de que el enlace sea abierto para leer (`noindex` en meta, `robots.txt` y
`X-Robots-Tag`). Que la dirección sea permanente aumenta el tiempo de exposición de nombres de atletas, algunos
menores; si eso preocupa, el siguiente paso es una clave de lectura en el enlace.
