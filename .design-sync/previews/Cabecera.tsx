import type { ReactNode } from 'react';
import { Cabecera, LineaEstado } from '@fcteam/ui';

const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)' }}>{children}</div>
);

// Logo de ejemplo sin red: un cuadrado con las iniciales del equipo.
const logo = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="#000"/>' +
  '<rect x="3" y="3" width="74" height="74" fill="none" stroke="#fff" stroke-width="3"/>' +
  '<text x="40" y="52" font-size="32" font-weight="700" text-anchor="middle" fill="#fff" font-family="sans-serif">FC</text></svg>');

/** Pantalla de inicio (`variante="inicio"`): a todo el ancho, con el logo de 48 px y el nombre del equipo a 1,75 rem. */
export function Inicio() {
  return <Fondo><Cabecera variante="inicio" titulo="FC Team" logo={logo} /></Fondo>;
}

/** La variante normal, sin botones: centrada en 720 px, logo de 40 px y título de una línea. */
export function Normal() {
  return <Fondo><Cabecera titulo="FC Team" logo={logo} /></Fondo>;
}

/** Dentro de un evento: volver, enlace a Smoothcomp, actualizar y la línea de estado con la frescura de los datos. */
export function DentroDeUnEvento() {
  return (
    <Fondo>
      <Cabecera
        titulo="Madrid BJJ Cup 2026"
        logo={logo}
        onVolver={() => {}}
        enlaceEvento="https://smoothcomp.com/es/event/33588"
        onRecargar={() => {}}
      >
        <LineaEstado>Actualizado hace 12s · 443 combates · 446 atletas</LineaEstado>
      </Cabecera>
    </Fondo>
  );
}

/** Con los datos viejos la línea de estado se pone roja y avisa. */
export function DatosViejos() {
  return (
    <Fondo>
      <Cabecera titulo="Madrid BJJ Cup 2026" logo={logo} onVolver={() => {}} onRecargar={() => {}}>
        <LineaEstado vieja>⚠ Sin actualizarse desde hace 5 min · 443 combates · 446 atletas</LineaEstado>
      </Cabecera>
    </Fondo>
  );
}
