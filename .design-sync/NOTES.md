# Notas de /design-sync (FC Team UI)

El paquete es `web/` (`@fcteam/ui`); la librería es `web/src/ui`, la web que la usa es `web/src/app`.
Comandos desde la raíz del repo (el conversor usa `.design-sync/` relativo al directorio actual):

```sh
npm --prefix web ci && npm --prefix web run build:lib      # compila la librería a web/dist
node .ds-sync/resync.mjs --config .design-sync/config.json --node-modules ./web/node_modules \
  --entry ./web/dist/index.es.js --out ./ds-bundle [--remote .design-sync/.cache/remote-sync.json]
```

`.ds-sync/` (scripts del conversor + `esbuild ts-morph @types/react playwright`) y `ds-bundle/` no se
versionan. `localDir` de `finalize_plan` va con **ruta absoluta**: resuelve `./ds-bundle` desde el
directorio de la shell. Chromium para el chequeo de render está en la caché de Playwright del usuario.

## Cómo está montado
- **Sin provider ni Storybook.** Basta `styles.css` (tokens en `:root` + `body` negro). Detalle en `conventions.md`.
- **Agrupación** por carpeta de stubs `.design-sync/docs/<Nombre>.md` (solo `category:`), enlazada con
  `docsDir`. Para mover un componente de grupo: edita su stub (el nombre del grupo pierde tildes y
  espacios en la carpeta: `Barras y filtros` → `barras-y-filtros`).
- **Previews a mano** en `.design-sync/previews/` para 12 componentes: Boton, Etiqueta, Medalla, Tarjeta,
  TarjetaAtleta, FilaCombate, TarjetaEvento, Pestanas, Filtros, ChipZona, Cabecera, PanelDetalle. Los otros
  20 salen como tarjeta suelo (13) o renderizando bien con las props de relleno (7). Cada story lleva su
  propio fondo `var(--fondo)`: la tarjeta de previews fuerza `body{background:#fff}` y la librería es oscura.
- `PanelDetalle` (hoja `position: fixed`) usa `overrides.PanelDetalle = {cardMode: single, viewport: 390x640}`.

## Gotchas de la herramienta
- El conversor **descarta las props HTML heredadas** (`placeholder`, `value`, `onClick`, `disabled`…) y deja
  solo `className/id/style/children`. Por eso `Boton`, `Campo`, `CampoBusqueda` y `EnlaceInterno` las
  **declaran explícitas** en su interfaz (con JSDoc). Una prop nueva de ese tipo debe declararse igual.
- Corta cada comentario de prop a **120 caracteres**: la explicación larga va al comentario del componente
  (el `.prompt.md` lo copia entero). Convertir las interfaces auxiliares a `type` no ayuda.
- Los tipos auxiliares de objeto (`Pestana`, `Llave`, `ResultadoCombate`…) **no se expanden** en el `.d.ts`.
  Se inlinan a mano con `dtsPropsFor` (ver más abajo).
- `Campo` y `CampoBusqueda` salen como tarjeta suelo: la tarjeta genérica les pasa `children` a un `<input>`
  (error de React, no del componente).
- Cada `Tarjeta` deja un hueco entre título y detalle (`<br>` entre dos bloques). Es idéntico a la web
  original; se conserva a propósito.

## Known render warns
Ninguno al cierre de la primera sincronización (0 `bad`, 0 `thin`, 0 `variantsIdentical`).

## Re-sync risks
- **`dtsPropsFor` está escrito a mano** para Pestanas, Filtros, Llaves, FilaCombate, TarjetaProximo,
  TarjetaTatami, TarjetaAtleta y ListaGrupo. Si cambian sus props en `web/src/ui`, hay que cambiarlas
  también en `config.json`, o el `.d.ts` que lee el agente se desincroniza sin avisar. Idea para quitarlo:
  que el conversor expanda esos tipos (o inlinarlos en la fuente).
- **Los previews tienen datos ficticios inlinados** (nombres, clubes, URLs `https://smoothcomp.com/...`) y
  avatares/logo como SVG en data-URI. Si cambia un tipo o una prop usada, el preview puede dejar de compilar
  (esa tarjeta cae a suelo, el bundle no se ve afectado).
- **`conventions.md` cita nombres reales** (tokens, `top: 62px` de `Pestanas`, `max-width: 720px`,
  componentes y props del ejemplo). Se validaron contra el build al escribirlo; revalidar si cambian.
- **Solo se verificó el escritorio** (viewport del chequeo de render ≥ 640 px); la vista de 390 px de las
  tarjetas se comprobó por geometría contra la web antigua, no con capturas de este conversor.
- Toolchain: Node ^22.12 || ^24, Vite 8 (rolldown), TypeScript 7, React 19 (peer `>=19`; `ref` como prop).
- Pendiente de ampliar con previews a mano (hoy en suelo): Aviso, Campo, CampoBusqueda, Contador,
  EnlaceExterno, EnlaceInterno, CabeceraTarjeta, Foto, LineaEstado, Llaves, TextoTenue, TituloSeccion, Vacio.
