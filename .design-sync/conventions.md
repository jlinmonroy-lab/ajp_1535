# FC Team UI: cómo construir con esta librería

Web móvil, en español, de seguimiento de eventos de Smoothcomp (jiu-jitsu brasileño): buscar un evento,
seguir atletas, ver sus combates y los tatamis. **Solo tema oscuro.** Todo sale de `window.FcTeamUI.*`.

## Montaje
- **No hay provider ni tema que envolver.** Carga `styles.css`: define los tokens en `:root` y pone el
  `body` en negro (`background: var(--fondo)`, texto blanco, `system-ui` 16 px). Sin esa hoja los
  componentes salen sin estilo, y sobre un fondo claro se ven mal: están pensados para negro.
- **Diseña para móvil (390 px)**, una sola columna. `main` **no es un componente**: ponle tú
  `padding: 0 16px` y, desde 640 px, `max-width: 720px; margin-inline: auto`. `Cabecera`, `Pestanas` y
  `Aviso` ya se centran solos a 720 px. La excepción es `<Cabecera variante="inicio">`, para la pantalla
  de inicio: ocupa todo el ancho, con el logo y el título más grandes.
- `Cabecera` (`top: 0`) y `Pestanas` (`top: 62px`, justo bajo una cabecera con línea de estado) son
  `position: sticky`: ponlos como primeros hijos de la página, no dentro de un contenedor con overflow.

## Estilo: tokens, no clases
No hay utilidades ni clases que escribir: las `fc-*` son internas. Para tu maquetación usa estilos en
línea con estos tokens (`var(--fondo)`, `var(--texto)`…):

| Token | Para qué |
|---|---|
| `--fondo` `--superficie` `--superficie-2` | página, tarjetas, campos y botones (de más negro a más claro) |
| `--borde` | filetes y contornos |
| `--texto` `--texto-tenue` | texto principal y secundario |
| `--equipo` `--equipo-texto` | color de marca (blanco) y el texto que va encima (negro); `--acento` lo repite |
| `--vivo` `--ok` | rojo de «en curso»/errores y verde de «ganó»/grupo |
| `--oro` `--plata` `--bronce` | medallas y avisos dorados |
| `--radio` | 12 px, esquinas de tarjetas y campos |

Los componentes reciben **textos ya formateados** (`hora="17:30"`, `dia="sáb 17"`) y callbacks
(`onSeguir`, `onCambiar`): no calculan fechas ni leen la red. Los textos de la interfaz van en español.
Un enlace externo (`EnlaceExterno`, `Boton href`) solo se pinta si empieza por `https://`.

## Dónde mirar
`styles.css` (que importa `_ds_bundle.css`) tiene los tokens y todo el CSS. Cada componente trae
`<Nombre>.d.ts` (props) y `<Nombre>.prompt.md` (uso). Las fichas se componen con `Tarjeta` +
`CabeceraTarjeta` + `FilaCombate`; atletas, eventos y tatamis ya tienen su tarjeta hecha
(`TarjetaAtleta`, `TarjetaEvento`, `TarjetaTatami`).

## Ejemplo
```jsx
const { Cabecera, LineaEstado, Pestanas, TarjetaAtleta } = window.FcTeamUI;

<>
  <Cabecera titulo="Madrid BJJ Cup 2026" logo="img/logo.png" onVolver={volver} onRecargar={recargar}>
    <LineaEstado>Actualizado hace 12s · 443 combates · 446 atletas</LineaEstado>
  </Cabecera>
  <Pestanas activa="seguidos" onCambiar={cambiar} pestanas={[
    { id: 'seguidos', etiqueta: 'Mis atletas', contador: 1 },
    { id: 'buscar', etiqueta: 'Buscar' },
    { id: 'tatamis', etiqueta: 'Tatamis' },
  ]} />
  <main style={{ padding: '0 16px' }}>
    <TarjetaAtleta id="ana perez|gracie madrid" nombre="Ana Pérez" club="Gracie Madrid"
      categoria="Women's GI / Blue / 60KG" siguiendo onSeguir={seguir}
      combates={[{ hora: '11:15', titulo: 'vs Luz Díaz', dia: 'sáb 17', evento: 'Gi',
        detalle: 'Semifinal · Mat 3', resultado: { texto: 'EN CURSO', tono: 'vivo' } }]} />
  </main>
</>
```
