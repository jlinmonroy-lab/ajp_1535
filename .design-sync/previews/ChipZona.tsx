import type { ReactNode } from 'react';
import { ChipZona } from '@fcteam/ui';

const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16 }}>{children}</div>
);

/** Encendido: la lista está filtrada por el lugar; la ✕ avisa de que se puede quitar. */
export function Encendido() {
  return <Fondo><ChipZona nombre="Madrid, España" activo onAlternar={() => {}} /></Fondo>;
}

/** Apagado: discontinuo y sin ✕, a la vista para volver a encenderlo. */
export function Apagado() {
  return <Fondo><ChipZona nombre="Madrid, España" activo={false} onAlternar={() => {}} /></Fondo>;
}
