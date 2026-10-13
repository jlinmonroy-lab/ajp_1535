import type { ReactNode } from 'react';
import { Filtros } from '@fcteam/ui';

const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16 }}>{children}</div>
);

const opciones = [
  { id: 'upcoming', etiqueta: 'Próximos' },
  { id: 'past', etiqueta: 'Pasados' },
  { id: 'all', etiqueta: 'Todos' },
];

/** El filtro por defecto de la pantalla de inicio. */
export function Proximos() {
  return <Fondo><Filtros etiqueta="Cuándo" opciones={opciones} valor="upcoming" onCambiar={() => {}} /></Fondo>;
}

/** Con otra opción elegida. */
export function Pasados() {
  return <Fondo><Filtros etiqueta="Cuándo" opciones={opciones} valor="past" onCambiar={() => {}} /></Fondo>;
}
