# Operación: qué mirar y qué hacer cuando algo falla

Para quien tiene que arreglarlo con el torneo en marcha. Lo que se cuenta aquí es lo que el código hace de
verdad (`scraper/servidor.py`, `scraper/almacen.py`, `scraper/telemetria.py`); el alojamiento está en el
[README](../README.md#alojamiento-fijo-flyio) y la arquitectura en [architecture.md](architecture.md).

## Quién vigila qué

| Qué | Cuándo | Qué detecta |
| --- | --- | --- |
| Check de Fly (`fly.toml`, `/api/health`) | cada 30 s, siempre | proceso colgado, hilo de lectura muerto, web sin compilar (503) |
| **Monitor externo** (lo montas tú, [abajo](#monitor-externo)) | cada 5 min | la app no contesta, o está `degradado` |
| `research/smoke_api.py` | tras cada `fly deploy` | web en blanco, versión que no es la desplegada, Smoothcomp bloqueando a esa IP |
| CI (`.github/workflows/ci.yml`) | en cada push y PR | tests, tipos, contrato Python↔web, imagen Docker que no arranca |
| Informes del navegador (`cliente […]` en el registro) | cuando a alguien se le rompe la web | fallos de pantalla y datos que la web no entiende |

## Dónde mirar

```sh
fly status                      # ¿está en marcha la máquina? ¿pasa el check?
fly logs                        # lo último que ha contado el servidor (Fly guarda poco tiempo)
curl https://fcteam-competicion.fly.dev/api/health
fly ssh console                 # y dentro:  tail -n 200 /data/registro/servidor.log   (si pusiste LOG_FILE)
```

En el PC, el registro del servidor está en `registro/servidor.log` y lo del lanzador (arranques y caídas) en
`registro/evento.log`.

### Leer `/api/health`

```json
{"estado": "ok", "version": "abc1234", "uptimeS": 5230, "sitioCompilado": true,
 "workers": 2, "workersVivos": 2, "eventosEnCache": 1, "enCola": 0,
 "eventosStale": 0, "eventosConError": 0,
 "origen": {"ultimoExitoS": 41, "ultimoErrorS": null, "ultimoErrorCodigo": null, "ultimoErrorReto": null},
 "contadores": {"http_2xx": 1234, "http_200": 1200, "http_202": 34, "origen_reintentos": 2}}
```

- `estado`: **`ok`**; **`degradado`** (200: hay eventos con datos viejos o que no se pueden leer, es decir, el
  servidor está bien pero Smoothcomp falla); **`error`** (503: un hilo de lectura ha muerto o falta `site/index.html`).
- Sin nadie mirando ningún evento (`eventosEnCache: 0`) siempre sale `ok`: no hay nada que se pueda estar
  rompiendo. Un evento que nadie abre durante `inactividadMinutos` (30) se olvida, y con él sus fallos.
- `version` es el `GIT_SHA` con el que se construyó la imagen (`dev` si no se pasó).
- `ultimoExitoS` es hace cuántos segundos se leyó Smoothcomp bien; `ultimoErrorCodigo` el código HTTP del último
  fallo (`null` si fue de red) y `ultimoErrorReto` si fue la página de reto de Cloudflare.
- `contadores`: respuestas por código (`http_200`, `http_502`…), `origen_reintentos`, `cliente_errores` y
  `cliente_errores_descartados`. Se reinician con el proceso.

### Leer el registro

Cada línea lleva fecha y nivel. Normalmente solo salen los fallos; con `LOG_LEVEL=DEBUG` sale cada petición.

| Línea | Qué significa |
| --- | --- |
| `GET /api/events/1/data 502 3ms · motivo` | una respuesta de error, con el motivo que se le dio al cliente |
| `reintento 1/2 en 1s tras HTTP 503: …` | Smoothcomp falló y se vuelve a intentar (3 intentos por petición) |
| `[1535] fallo: …` | no se pudo leer el evento; con copia anterior se sigue sirviendo |
| `[1535] marcado stale desde …` | 3 fallos seguidos: la web avisa de que los datos están viejos |
| `[1535] lectura parcial: 1 de 2 eventos sin leer` | en una vista combinada falta uno de los dos |
| `[1535] error inesperado: …` + traceback | un fallo de código del servidor (no de Smoothcomp) |
| `búsqueda: Smoothcomp falló …; se sirve la copia guardada` | el buscador responde con la lista de antes |
| `cliente [js\|render\|promesa\|datos] …` | un error ocurrido en el navegador de alguien, con build y pila |
| `grupo: …` / `admin: …` | cambios de la lista del grupo, y claves de administrador rechazadas (con IP) |
| `grupos: grupos.json … se trata como vacío` | el fichero de la lista está corrupto (ver más abajo) |

## Si pasa esto, haz esto

### `/api/health` da 503 o la app no contesta

1. `fly status`: ¿la máquina está `started`? Si no, `fly machine restart <id>` (el id sale de `fly status`).
2. Si contesta pero con `error`: mira `sitioCompilado` y `workersVivos` frente a `workers`.
   - `sitioCompilado: false`: la imagen se construyó sin la web. Es un fallo de despliegue: **vuelve a la versión
     anterior** ([deshacer](#deshacer-un-despliegue)) y mira el `docker build`.
   - `workersVivos < workers`: murió un hilo de lectura. Es muy raro (cada hilo atrapa sus errores y los
     cuenta como `error inesperado` con su traceback). Guarda lo que haya en `fly logs` y reinicia la máquina.
3. Reiniciar vacía la caché de eventos: el primer móvil que abra cada evento verá «Leyendo el schedule de
   Smoothcomp…» hasta un minuto, y luego todo vuelve a ir rápido.

### `degradado`: Smoothcomp falla

El servidor está bien, **no lo reinicies**: no lo arregla y vacía la caché.

- `ultimoErrorReto: true` o el código 403: [Cloudflare está bloqueando](#cloudflare-bloquea-a-esa-ip).
- Un 5xx o un error de red (`ultimoErrorCodigo: null`): Smoothcomp está caído o lento. La web sigue enseñando lo
  último que tenía, con «⚠ Datos sin actualizar desde…». Espera y mira `ultimoExitoS` en `/api/health`.
- Con la búsqueda rota pero los eventos funcionando (502 solo en `/api/events/search`): se puede abrir un evento
  pegando su número; la web ya lo ofrece.

### Cloudflare bloquea a esa IP

La web dice «Smoothcomp está bloqueando las peticiones del servidor». Fly (París) funcionó el 2026-10-09, pero
puede cambiar. Comprueba lo que dice el README («La prueba que importa») y, si abrir un evento por número
tampoco da datos, esa IP no sirve: la salida (otra región o proveedor, o volver al equipo de casa con Funnel) está
en la sección de Fly.io de [architecture.md](architecture.md).

### Datos viejos en la web (`stale`) mucho rato

Primero `curl …/api/health`: si `degradado`, es Smoothcomp (arriba). Si dice `ok` pero la web enseña «⚠ Sin
actualizarse desde hace X», el que está mal es el reloj del móvil o su conexión: la edad se calcula con la hora del
servidor frente a la del dispositivo.

### Aparecen líneas `cliente [datos] …`

La web recibió algo que no sabe pintar (`la respuesta no tiene la forma esperada: falta la lista «…»`). Casi
siempre es un cambio en `scraper/parse.py` que no pasó por el contrato con `web/src/tipos.ts`:

```sh
python tests/contrato.py                           # regenera web/src/pruebas/estado.contrato.json
git diff web/src/pruebas/estado.contrato.json      # ¿qué campo cambió?
npm --prefix web run typecheck && npm --prefix web test
```

Si el CI estaba en verde, el contrato se cumplía: entonces es un dato real distinto de las fixtures (p. ej. un
campo que Smoothcomp deja vacío en un evento concreto). El mensaje dice qué campo; la pila, dónde.

### `grupos.json` ilegible

El servidor avisa **una vez** («no se pudo leer grupos.json… se trata como vacío») y la lista aparece vacía. Antes
de que nadie la modifique, copia el fichero de `/data` (`fly ssh console`); si alguien añade un atleta, el servidor
guarda lo que había como `grupos.json.bak` antes de escribir. Se recupera editando el `.bak` y quitando el
`.json` roto. Los volúmenes de Fly tienen instantáneas diarias: `fly volumes list` y `fly volumes snapshots list`.

### Se queda sin memoria

La máquina tiene 256 MB y la prueba de carga ocupó unos 38 MB con un evento cargado. Si `fly logs` muestra el
proceso muerto por falta de memoria: `fly scale memory 512` (cuesta más) y revisa cuántos eventos tienen
abiertos a la vez (`maxEventosEnCache` en `config.json`).

### Muchos `429` en `/api/client-error`

`cliente_errores_descartados` sube cuando se pasan de 30 informes por minuto en total. Es el límite funcionando:
mira las líneas `cliente […]` que sí salieron; probablemente un mismo error en bucle en varios móviles.

## Desplegar, verificar y deshacer

```sh
fly deploy --ha=false --build-arg GIT_SHA=$(git rev-parse --short HEAD)
python research/smoke_api.py https://fcteam-competicion.fly.dev --esperar-version $(git rev-parse --short HEAD)
```

La prueba de humo espera a que `/api/health` diga esa versión (si Fly tarda en relevar la máquina), y comprueba
que la web se sirve, que sus ficheros llevan el tipo correcto y que la búsqueda llega a Smoothcomp. **Salida: 0**
todo bien · **1** algo está roto (deshaz) · **2** solo avisos (p. ej. `degradado`, o Smoothcomp no contesta desde
esa IP: mira la sección de arriba).

### Deshacer un despliegue

```sh
fly releases --image             # la lista de versiones desplegadas, con su imagen
fly deploy --ha=false --image <la imagen de la versión buena>
```

La imagen vieja sigue llevando su propio `GIT_SHA`, así que `/api/health` dirá a qué versión has vuelto.

## Rotar la clave de administrador

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
fly secrets set ADMIN_TOKEN=<la nueva>      # reinicia la máquina
```

Los dispositivos con la clave vieja la olvidan solos al abrir la web. Guárdala en un gestor de contraseñas, no
en un fichero suelto: `localhost.txt` está fuera de git y de Docker, pero sigue siendo texto plano.

## Monitor externo

Lo que avisa de que la app **no contesta** tiene que estar fuera de la app: el check de Fly decide a quién
manda tráfico, pero por sí solo no te avisa a ti. Cualquier servicio de disponibilidad con monitores de
**palabra clave** sirve (UptimeRobot, Better Stack…):

- **Tipo:** HTTP(s) con palabra clave (usa `GET`; con `HEAD` no hay cuerpo que mirar).
- **URL:** `https://fcteam-competicion.fly.dev/api/health`
- **Palabra clave:** `"estado": "ok"` (con las comillas y el espacio tras los dos puntos: es el `json.dumps` de
  Python). Alerta **cuando falta**: salta con un 503 (`error`), con `degradado` y con la app caída.
- **Intervalo:** 5 minutos. Alerta por correo.
- Una alerta suelta durante un `fly deploy` es normal (la máquina se reinicia). Fuera de un torneo la caché está
  vacía y el estado es `ok`, así que no debería haber falsas alarmas el resto del tiempo.

Esto lo tienes que configurar tú: no hay ninguna cuenta de ese tipo creada desde el repositorio.

## Gasto

Fly no tiene tope duro de gasto: configura los avisos en su panel (Billing). Una máquina `shared-cpu-1x` de
256 MB y un volumen de 1 GB cuestan del orden de 2-3 $/mes (ver README).

## Lo que no está verificado

Los comandos de `fly` de esta página son los estándar de `flyctl`, pero **no se han ejecutado** al escribirla (no
había sesión de Fly). Si alguno ya no existe con ese nombre o esas opciones, `fly <comando> --help` lo dice.
