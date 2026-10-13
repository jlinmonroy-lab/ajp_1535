import type { ReactNode } from 'react';
import { Etiqueta } from '@fcteam/ui';

// La librería es de tema oscuro y la tarjeta de previews es blanca: cada story lleva su fondo.
const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16 }}>{children}</div>
);
const Fila = ({ children }: { children: ReactNode }) => (
  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>{children}</div>
);

/** Los seis tonos, con el texto que llevarían en la web. */
export function Tonos() {
  return (
    <Fondo>
      <Fila>
        <Etiqueta>Pendiente</Etiqueta>
        <Etiqueta tono="vivo">EN CURSO</Etiqueta>
        <Etiqueta tono="ganado">Ganó · puntos</Etiqueta>
        <Etiqueta tono="perdido">Perdió</Etiqueta>
        <Etiqueta tono="grupo">grupo</Etiqueta>
        <Etiqueta tono="evento">No-Gi</Etiqueta>
      </Fila>
    </Fondo>
  );
}

/** Dentro de una línea de texto: día, evento y estado junto a la ronda. */
export function EnUnaLinea() {
  return (
    <Fondo>
      <div style={{ fontSize: 13, color: 'var(--texto-tenue)', lineHeight: 2 }}>
        <Etiqueta>sáb 17</Etiqueta> <Etiqueta tono="evento">Gi</Etiqueta> Semifinal · Mat 3{' '}
        <Etiqueta tono="vivo">Hoy</Etiqueta>
      </div>
    </Fondo>
  );
}
