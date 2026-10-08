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

1. **Busca el evento** por nombre, ciudad u organizador (`Próximos`, `Pasados` o `Todos`), o pega
   el enlace o el número de un evento de Smoothcomp.
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

### Que entren los móviles

El servidor, por defecto, solo escucha en este equipo. Dos formas de abrirlo:

- **Misma wifi:** `python arrancar_evento.py --host 0.0.0.0` y los móviles entran por
  `http://IP-DE-ESTE-EQUIPO:8765` (el cortafuegos de Windows tiene que permitirlo).
- **Desde cualquier sitio:** un túnel gratuito (cloudflared, ngrok…) apuntando a `localhost:8765`.

Da igual cuántos móviles entren: el servidor lee cada evento **una sola vez por ciclo** y todos
comparten la copia, así que no se multiplican las peticiones a Smoothcomp.

### Seguir para todos

En el equipo donde corre el servidor (`http://127.0.0.1:8765`) cada atleta tiene un botón
**«Seguir para todos»**, y hay un formulario para apuntar a alguien a mano antes de que haya schedule.
Eso crea una lista del grupo, **por evento**, que ve todo el mundo al abrirlo sin tener que seguir a
nadie, y que se guarda en `data/grupos.json` (no se versiona: son nombres de personas).

Los móviles ven la lista pero no pueden cambiarla. El servidor solo acepta el cambio si viene de
este equipo, y **también cuando hay un túnel por medio** (el túnel conecta desde `127.0.0.1`, así que
se comprueban además el `Host`, las cabeceras de proxy y el `Origin`).

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
| `servidor` | `puerto`, `listaEventosTtlSeconds` (caché del buscador, 600), `inactividadMinutos` (30), `maxEventosEnCache` (20), `workers` (2) |

Las opciones de línea de comandos del servidor: `--host`, `--puerto`, `--config`, `--origen`.

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
eventos sin publicar y un torneo que avanza (`seeded` → `running` → `finished`):

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
| `scraper/eventos.py` | buscador de eventos (lista de Smoothcomp, con caché) |
| `scraper/almacen.py` | caché compartida por evento y hilos que leen Smoothcomp |
| `scraper/fetch.py` | cliente de Smoothcomp: ritmo global, reintentos, códigos de error |
| `scraper/parse.py` | normaliza al modelo; atletas y medallas; **puro, sin red** |
| `scraper/grupos.py` | lista del grupo por evento |
| `scraper/main.py`, `panel.py`, `publish.py` | modo instantánea estática |
| `site/` | frontend (HTML/CSS/JS vanilla, sin build): `buscador.js` (inicio), `app.js` (evento) |
| `docs/` | `architecture.md`, `data-source.md` |
| `research/` | scripts de investigación y simuladores, no forman parte de la app |
