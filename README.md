# Eventos de Smoothcomp en directo

Seguimiento casi en tiempo real de **cualquier evento de [Smoothcomp](https://smoothcomp.com)**
para un grupo pequeño de personas: buscar el evento, buscar atletas, ver sus combates (hora
estimada, tatami, ronda, rival, resultado, estado) y sus medallas, desde el móvil y sin coste.

Nada va fijado a un evento: se busca el que toque, se abre y ya está. El mismo proyecto vale para
el Madrid BJJ Cup de este mes y para uno de dentro de un año.

## Uso

Requiere solo Python 3 (sin dependencias; `patchright` únicamente para los scripts de `research/`).

```sh
python -m scraper.servidor        # y abrir http://127.0.0.1:8765
```

1. **Busca el evento.** Al abrir salen solo los **próximos eventos en Madrid, España** (el chip
   «📍 Madrid, España ✕»); tócalo para quitarlo y buscar en todo el mundo. Se busca por nombre, ciudad u
   organizador (`Próximos`, `Pasados` o `Todos`), o se pega el enlace o el número de un evento de Smoothcomp.
   Con el chip puesto, lo que escribas se busca dentro de Madrid; si no hay nada, un botón ofrece
   «Buscar en todo el mundo».
2. **Ábrelo.** La primera vez el servidor lee su schedule de Smoothcomp: unos 30-60 segundos en
   un evento grande, porque se respeta una pausa entre peticiones. Luego se refresca solo cada ~75 s
   mientras alguien lo esté mirando.
3. **Busca atletas** por nombre, club o categoría, síguelos y mira sus próximos combates; la pestaña
   *Tatamis* muestra qué toca en cada uno.
4. Si el organizador **aún no ha publicado el schedule** (pasa los días previos), la web lo dice y lo
   vuelve a comprobar sola; todavía no hay atletas ni combates que enseñar.

Cada evento tiene su dirección, `http://servidor/#/evento/33588`, que se puede compartir.
Lo que sigues se guarda en tu navegador y vale para cualquier evento.

## El día del torneo

```sh
python arrancar_evento.py
```

Deja esa ventana abierta y ya está. El lanzador:

- **impide que Windows suspenda el equipo** mientras esté abierto (sin tocar el plan de energía:
  al cerrarlo, todo vuelve a su sitio);
- **relanza el servidor si se cae**, apuntando cada incidencia en `registro/evento.log`.

No puede cubrir un corte de luz, un reinicio por actualizaciones de Windows ni una caída del wifi,
así que conviene dejar el equipo enchufado y posponer las actualizaciones antes de salir.

### Para todo el equipo, con datos móviles

Un móvil con datos propios necesita una dirección pública con HTTPS. Se usa **Tailscale Funnel**,
que ya viene con Tailscale: no hay que instalar nada, no se toca el cortafuegos y la dirección es
fija. El servidor sigue escuchando solo en este equipo (`127.0.0.1`): el túnel conecta desde dentro.

**Una sola vez** (el mapeo se conserva aunque se reinicie el equipo):

```sh
tailscale funnel --bg --https=8443 8765
```

El enlace para el equipo, con el servidor en marcha, es:

> **https://czc52571qd.tail6a0155.ts.net:8443/**

(El nombre `czc52571qd.tail6a0155.ts.net` es el de este equipo; el tuyo sale en `tailscale funnel status`.)
`python arrancar_evento.py` escribe el enlace al arrancar leyendo el estado del túnel, o el comando de
arriba si todavía no está puesto. Pásalo tal cual por el grupo; en el móvil se puede añadir a la pantalla
de inicio.

A tener en cuenta:

- **Puerto 8443, no 443.** En este equipo el 443 de Funnel ya lo usa otro servicio
  (`127.0.0.1:5678`), y Funnel solo admite 443, 8443 y 10000. Por eso la dirección lleva `:8443`.
- **Para quitarlo al acabar:** `tailscale funnel --https=8443 off`. Solo quita este puerto.
  **No uses `tailscale funnel reset`**: borra todos los mapeos, también el del 443.
- **El mapeo sigue activo aunque el servidor esté parado:** quien entre verá un error hasta que se
  vuelva a arrancar.
- **El PC debe seguir encendido, con internet y con el servidor en marcha.** El lanzador evita la
  suspensión; un corte de luz no.
- **El enlace es abierto, no pide clave.** La web lleva `noindex` (meta, `robots.txt` y cabecera
  `X-Robots-Tag`), pero el nombre del equipo consta en los registros públicos de certificados y se puede
  encontrar. Quien lo abra puede usar este PC para consultar Smoothcomp, con los topes de siempre (una
  petición cada 2 s, 10 lecturas en cola), y **leer la lista del grupo**, que es lo que ven los móviles.
  Cambiarla, no: el `POST` se rechaza con 403 porque el `Host` no es local. Si hiciera falta cerrarlo
  más, lo siguiente sería una clave en el enlace.
- **Datos móviles:** la web pesa unos 75 KB la primera vez (después el navegador la reutiliza) y un
  evento de ~450 combates son unos 40 KB por actualización, del orden de 2 MB por hora con la pantalla
  encendida. Con la pantalla apagada o la pestaña en segundo plano no se sondea nada.

Da igual cuántos móviles entren: el servidor lee cada evento **una sola vez por ciclo** y todos
comparten la copia, así que no se multiplican las peticiones a Smoothcomp.

Si solo van a estar en la misma wifi no hace falta túnel: `python arrancar_evento.py --host 0.0.0.0`
y entran por `http://IP-DE-ESTE-EQUIPO:8765` (el cortafuegos de Windows tiene que permitirlo).

### Seguir para todos

En el equipo donde corre el servidor (`http://127.0.0.1:8765`) cada atleta tiene un botón
**«Seguir para todos»**, y hay un formulario para apuntar a alguien a mano antes de que haya schedule.
Eso crea una lista del grupo, **por evento**, que ve todo el mundo al abrirlo sin tener que seguir a
nadie, y que se guarda en `data/grupos.json` (no se versiona: son nombres de personas).

Los móviles ven la lista pero no pueden cambiarla. El servidor solo acepta el cambio si viene de
este equipo, y **también cuando hay un túnel por medio** (el túnel conecta desde `127.0.0.1`, así que
se comprueban además el `Host`, las cabeceras de proxy y el `Origin`). La única excepción es la
[clave de administrador](#alojamiento-fijo-flyio), que solo existe si el servidor se arranca con `ADMIN_TOKEN`.

## Alojamiento fijo (Fly.io)

Alternativa a tener el equipo encendido: el servidor vive en una máquina de [Fly.io](https://fly.io) y la
dirección (`https://eventos-bjj.fly.dev`) funciona a cualquier hora desde cualquier móvil. Cuesta del orden de
2-3 $/mes (máquina `shared-cpu-1x` de 256 MB + un volumen de 1 GB); Fly pide tarjeta y no tiene capa gratuita
para cuentas nuevas. Tailscale Funnel sigue valiendo como respaldo.

La imagen es `Dockerfile` (Python puro, 178 MB) y la configuración `fly.toml`: una **sola** máquina (la caché y el
ritmo de peticiones a Smoothcomp son del proceso, no se puede repartir) en París, con un volumen en `/data`
para `grupos.json`. **La clave no va en ningún fichero**: el repositorio es público.

**Una sola vez:**

```sh
pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"    # instala flyctl (ver fly.io/docs/flyctl/install)
fly auth login                                                 # o `fly auth signup`; pide tarjeta
fly apps create eventos-bjj                                    # el nombre es único en todo Fly: si está cogido,
                                                               # elige otro y cámbialo en `app =` de fly.toml
fly volumes create datos --region cdg --size 1                 # el volumen de grupos.json
python -c "import secrets; print(secrets.token_urlsafe(32))"   # genera una clave larga y guárdala (gestor de contraseñas)
fly secrets set ADMIN_TOKEN=<la clave>
fly deploy --ha=false                                          # --ha=false: una sola máquina
```

**Antes de fiarte, la prueba que importa:** que Smoothcomp conteste a la IP de un servidor en la nube. Todo lo
verificado hasta ahora (`docs/data-source.md`) fue desde una IP residencial. Con la app desplegada:

```sh
curl "https://eventos-bjj.fly.dev/api/events/search?q=madrid&when=past"   # lista de eventos (HTML tras Cloudflare)
curl "https://eventos-bjj.fly.dev/api/events/26416/data"                  # 202 «cargando»; repite hasta el 200
```

Si el buscador da `502` («Smoothcomp está bloqueando la búsqueda») pero abrir un evento por número funciona,
solo falla la lista; si tampoco hay datos del evento, esta IP no sirve y toca otro proveedor o volver al equipo
de casa con Funnel.

**La clave de administrador.** Con `ADMIN_TOKEN` puesto, la pantalla de inicio enseña al pie *Acceso de
administrador*: se escribe la clave una vez por dispositivo (queda en su `localStorage`, nunca en la URL) y desde ahí
sale el botón **«Seguir para todos»** y el formulario de alta, igual que en el equipo del servidor. *Salir* la
borra del dispositivo. Para cambiarla: `fly secrets set ADMIN_TOKEN=<otra>` (reinicia la máquina; los
dispositivos con la clave vieja la olvidan solos al abrir la web). Mínimo 16 caracteres: con menos, el servidor
no arranca.

Día a día: `fly deploy --ha=false` para publicar cambios, `fly logs` para ver qué pasa y `fly status` para ver
si está en marcha. Los avisos de gasto se configuran en el panel de Fly (no tiene tope duro).

## Configuración

Todo en `config.json`:

| Clave | Qué es |
| --- | --- |
| `baseUrl` | sitio de Smoothcomp; `https://smoothcomp.com` redirige al subdominio de cada organizador |
| `lang` | idioma de las rutas (`en`; los nombres de ronda, como `Final`, dependen de él) |
| `refreshSeconds` | cada cuánto se vuelve a leer un evento que alguien mira (75) |
| `requestPauseSeconds` | pausa mínima entre dos peticiones a Smoothcomp, de quien sean (2) |
| `staleAfterFailures` | fallos seguidos tras los que la web avisa de que los datos están viejos (3) |
| `branding` | `teamName` y `logo` de la cabecera |
| `zona` | el sitio al que se acota el buscador por defecto (ver abajo); `null` para desactivarlo |
| `servidor` | `puerto`, `listaEventosTtlSeconds` (caché del buscador, 600), `inactividadMinutos` (30), `maxEventosEnCache` (20), `workers` (2) |

Las opciones de línea de comandos del servidor: `--host`, `--puerto`, `--config`, `--origen`.

Y dos variables de entorno, pensadas para el [alojamiento fijo](#alojamiento-fijo-flyio) y sin efecto si no
se ponen:

| Variable | Qué hace |
| --- | --- |
| `ADMIN_TOKEN` | clave (≥16 caracteres) que permite cambiar la lista del grupo desde cualquier dispositivo, con la cabecera `X-Admin-Token`. Sin ella solo vale el equipo del servidor |
| `DATA_DIR` | carpeta donde se guarda `grupos.json` (por defecto `data/`); en Fly es el volumen `/data` |

### La zona por defecto

```json
"zona": { "nombre": "Madrid, España", "pais": "ES", "texto": "madrid",
          "centro": [40.4168, -3.7038], "radioKm": 50 }
```

Un evento es de la zona si es del `pais` **y**, o bien dice el `texto` en el título o la ciudad, o bien
sus coordenadas (las del organizador en Smoothcomp) caen a menos de `radioKm` de `centro`. Las dos vías
se complementan: el radio encuentra el torneo de Alcalá cuyo título no dice «Madrid», y el texto vale
aunque el organizador no pusiera coordenadas. Hace falta `texto` o `centro` con `radioKm`; para otro sitio
basta cambiar estos valores, sin tocar código. Con `"zona": null` no hay chip y el buscador es global.

Cómo se aplica, porque Smoothcomp solo filtra bien por país: **próximos** se pide la lista del país una
vez y se filtra aquí (el texto que escribas también), así que cambiar de búsqueda no hace más peticiones.
**Pasados** se pide con el `texto` de la zona (`past?countries=ES&search=madrid`), así que un evento pasado
de la zona sin «Madrid» en el título no sale. El chip arranca encendido en cada visita; no se recuerda que
alguien lo apagara.

## Logo y colores del equipo

- **Logo**: `site/img/logo.png`, el logo de FC Team reducido a 160×160 px. Tiene fondo negro, así
  que se funde con la web. Para cambiarlo, sustituye ese fichero:
  cuadrado o casi, de unos 256 px y pocas decenas de KB. El nombre de la cabecera es `branding.teamName`.
- **Colores**: la web es siempre negra con letras blancas. El color de botones y pestaña activa es
  `--equipo` (ahora blanco), y `--equipo-texto` el del texto encima (ahora negro); los dos están al
  principio de `site/style.css`.

## Pruebas

```sh
python -m unittest discover -s tests     # no tocan la red
```

Para ver la web funcionando **sin mandar tráfico a Smoothcomp**, hay un origen simulado con búsqueda,
eventos sin publicar, eventos de otros sitios (Barcelona, Lisboa, un «Madrid Open» de Texas y un torneo
en Alcalá que no dice Madrid, para probar la zona) y un torneo que avanza (`seeded` → `running` → `finished`):

```sh
python research/mock_origen.py --eventos 1535,1526 --simular-vivo --sin-schedule 33588 --estricto --relleno 55
python -m scraper.servidor --origen http://127.0.0.1:8899 --puerto 8766
```

(Con una copia de `config.json` y `requestPauseSeconds` bajo, vía `--config`, para no esperar entre
peticiones al simulador.) `python research/simular_evento.py` reproduce además un torneo completo sobre
una copia aislada de la web, con un banner de SIMULACIÓN.

## Límites que conviene conocer

- **Los atletas solo se conocen con el schedule publicado.** Smoothcomp no ofrece buscador de atletas
  sin iniciar sesión; se derivan de los combates, como siempre.
- **Medallas deducidas del schedule**, sin pedir resultados: oro y plata de la final, bronce del
  combate por el bronce o, si el cuadro no lo tiene, doble bronce para los que pierden la semifinal.
  Los cuadros «todos contra todos» (`Match 1/3`…) no generan medallas.
- **Categorías:** se interpretan las del formato `División / Cinturón / Edad / Peso`. Otras se enseñan
  tal cual, sin desglosar.
- **`ajptour.com` es otra instalación de Smoothcomp**, con sus propios ids (que colisionan con los de
  smoothcomp.com). El buscador no la cubre; para un evento suyo, ver el modo estático de abajo.
- **Cortesía con Smoothcomp.** Su `robots.txt` pide `Crawl-delay: 10`. La lista de eventos se cachea
  10 minutos y los schedules se leen con una pausa de 2 s, una petición a la vez. Sus términos de uso
  no dicen nada del scraping, lo que es una zona gris: para un uso más amplio que un grupo de amigos
  conviene hablar con ellos (`support.smoothcomp.com` ofrece una API privada).
- **Datos personales.** Salen nombres reales de atletas, también menores. La web lleva `noindex` y
  `robots.txt`, los datos solo viven en memoria y las fixtures del repositorio están anonimizadas.
  No publiques capturas con nombres.

## Modo «instantánea estática» (el anterior)

Todavía se puede generar un `site/data.json` de un evento y publicarlo en GitHub Pages, sin servidor:

```sh
python -m scraper.main --event 1257      # un ciclo cada 75 s; --once para uno solo
```

Si la web no encuentra `api/config` (servida como ficheros estáticos), cae a este modo y lee `data.json`.
La publicación por git sale de la clave `publish` de `config.json` (apagada por defecto). Para eventos de
AJP, pon `baseUrl` a `https://ajptour.com`.

## Estructura

| Ruta | Qué hace |
| --- | --- |
| `scraper/servidor.py` | servidor: web, API y guarda del panel local |
| `scraper/eventos.py` | buscador de eventos (lista de Smoothcomp, con caché) y la zona por defecto |
| `scraper/almacen.py` | caché compartida por evento y hilos que leen Smoothcomp |
| `scraper/fetch.py` | cliente de Smoothcomp: ritmo global, reintentos, códigos de error |
| `scraper/parse.py` | normaliza al modelo; atletas y medallas; **puro, sin red** |
| `scraper/grupos.py` | lista del grupo por evento |
| `scraper/main.py`, `panel.py`, `publish.py` | modo instantánea estática |
| `site/` | frontend (HTML/CSS/JS vanilla, sin build): `buscador.js` (inicio), `app.js` (evento) |
| `Dockerfile`, `fly.toml` | imagen y configuración del [alojamiento fijo](#alojamiento-fijo-flyio) |
| `docs/` | `architecture.md`, `data-source.md` |
| `research/` | scripts de investigación y simuladores, no forman parte de la app |
