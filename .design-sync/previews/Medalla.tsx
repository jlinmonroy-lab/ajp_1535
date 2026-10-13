import type { ReactNode } from 'react';
import { Medalla } from '@fcteam/ui';

const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16, display: 'grid', gap: 10 }}>{children}</div>
);

/** Las tres medallas, junto al nombre de quien las ganó, como en una tarjeta de atleta. */
export function Tipos() {
  return (
    <Fondo>
      <div><span style={{ fontWeight: 650 }}>Ana Pérez</span> <Medalla tipo="oro" /></div>
      <div><span style={{ fontWeight: 650 }}>Eva Gómez</span> <Medalla tipo="plata" /></div>
      <div><span style={{ fontWeight: 650 }}>Luz Díaz</span> <Medalla tipo="bronce" /></div>
    </Fondo>
  );
}

/** En la ficha de un atleta: una medalla por categoría en la que compitió. */
export function EnLaFicha() {
  return (
    <Fondo>
      <div style={{ fontSize: 13, color: 'var(--texto-tenue)', lineHeight: 1.7 }}>
        <Medalla tipo="oro" /> Women's GI / Blue / Adult / 60KG<br />
        <Medalla tipo="plata" /> Women's NO-GI / Blue / Adult / 60KG
      </div>
    </Fondo>
  );
}
