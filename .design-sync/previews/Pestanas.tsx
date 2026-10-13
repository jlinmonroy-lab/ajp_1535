import type { ReactNode } from 'react';
import { Pestanas } from '@fcteam/ui';

const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)' }}>{children}</div>
);

const pestanas = (contador?: number) => [
  { id: 'seguidos', etiqueta: 'Mis atletas', contador },
  { id: 'buscar', etiqueta: 'Buscar' },
  { id: 'tatamis', etiqueta: 'Tatamis' },
];

/** La pestaña activa se rellena con el color del equipo; «Mis atletas» lleva el contador de a quién sigues. */
export function MisAtletasActiva() {
  return <Fondo><Pestanas activa="seguidos" onCambiar={() => {}} pestanas={pestanas(3)} /></Fondo>;
}

/** Otra pestaña activa; el contador sigue visible en la que lo tiene. */
export function BuscarActiva() {
  return <Fondo><Pestanas activa="buscar" onCambiar={() => {}} pestanas={pestanas(3)} /></Fondo>;
}

/** Sin nadie seguido la burbuja del contador queda vacía. */
export function SinSeguidos() {
  return <Fondo><Pestanas activa="tatamis" onCambiar={() => {}} pestanas={pestanas(0)} /></Fondo>;
}
